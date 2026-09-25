// V724: K 线本地缓存编排单测。
// IndexedDB 由 src/test-setup.ts 注入 fake-indexeddb（jsdom 未内置）。
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { barsCacheKey, clearAllBarsCache, loadBarsSeries, saveBarsSeries } from '../barsCache'
import { fetchBars } from '../../api'

interface BarLike {
  datetime: string
  open: number
  high: number
  low: number
  close: number
  vol: number
  amount: number
}

function bar(day: string, close: number): BarLike {
  return { datetime: `${day}T15:00:00`, open: close, high: close, low: close, close, vol: 1, amount: 1 }
}

// 工具日历（仅工作日，1200 天，可覆盖跨页量级）
const DAYS: string[] = (() => {
  const out: string[] = []
  const d = new Date(Date.UTC(2018, 0, 2))
  while (out.length < 1200) {
    const wd = d.getUTCDay()
    if (wd !== 0 && wd !== 6) out.push(d.toISOString().slice(0, 10))
    d.setUTCDate(d.getUTCDate() + 1)
  }
  return out
})()

const KEY = barsCacheKey('SZ', '000001', 'DAY')
// fire-and-forget 的 saveBarsSeries 需要在断言前落盘
function flushPending(): Promise<void> {
  return new Promise((r) => setTimeout(r, 25))
}

const cachedBars = (): BarLike[] => DAYS.slice(0, 800).map((d, i) => bar(d, 10 + (i % 7)))

beforeEach(async () => {
  await clearAllBarsCache()
})
afterEach(async () => {
  vi.unstubAllGlobals()
  await flushPending()
  await clearAllBarsCache()
})

describe('barsCache 存储', () => {
  test('save → load 往返，键区分市场/周期', async () => {
    await saveBarsSeries(KEY, [bar('2024-01-02', 10), bar('2024-01-03', 11)])
    const loaded = await loadBarsSeries(KEY)
    expect(loaded).not.toBeNull()
    expect(loaded!.length).toBe(2)
    expect(loaded![1].close).toBe(11)
    expect(await loadBarsSeries(barsCacheKey('SH', '000001', 'DAY'))).toBeNull()
  })

  test('空数组不写入，load 返回 null', async () => {
    await saveBarsSeries(KEY, [])
    expect(await loadBarsSeries(KEY)).toBeNull()
  })
})

describe('fetchBars 缓存编排', () => {
  let fetchCalls: string[] = []
  let respond: ((url: string) => unknown) | null = null

  beforeEach(() => {
    fetchCalls = []
    respond = null
    vi.stubGlobal('fetch', async (url: string) => {
      fetchCalls.push(url)
      const handler = respond
      if (!handler) throw new Error(`unexpected fetch: ${url}`)
      return handler(url) as Response
    })
  })

  function jsonResponse(bars: BarLike[]) {
    return {
      ok: true,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ data: bars, count: bars.length }),
    }
  }

  test('缓存命中 + 增量：1 次小请求合并（无 800 根翻页），窗口全在缓存内则 0 请求', async () => {
    await saveBarsSeries(KEY, cachedBars())
    const lastDay = DAYS[799]
    const incDays = DAYS.slice(800, 805)
    respond = (url) => {
      expect(url).toContain(`start_date=${lastDay}`)
      return jsonResponse(incDays.map((d, i) => bar(d, 20 + i)))
    }
    const bars = await fetchBars('SZ', '000001', 'DAY')
    expect(fetchCalls.length).toBe(1)
    expect(bars.length).toBe(805)
    expect(bars[799].close).toBe(10 + (799 % 7))
    expect(bars[804].close).toBe(24)
    await flushPending()
    // 已回填缓存：再次全量查看仍只 1 次尾部小请求（新末日之后）
    fetchCalls.length = 0
    const last2 = DAYS[804]
    respond = (url) => {
      expect(url).toContain(`start_date=${last2}`)
      return jsonResponse([bar(DAYS[805], 30)])
    }
    const again = await fetchBars('SZ', '000001', 'DAY')
    expect(again.length).toBe(806)
    expect(fetchCalls.length).toBe(1)
    // 有窗口且末端在缓存内：直接用缓存，0 网络请求
    fetchCalls.length = 0
    respond = null
    const win = await fetchBars('SZ', '000001', 'DAY', DAYS[100], DAYS[200])
    expect(win.length).toBe(101)
    expect(fetchCalls.length).toBe(0)
  })

  test('除权重算：重叠日 close 不一致 → 自动整体重取并回写缓存', async () => {
    await saveBarsSeries(KEY, cachedBars())
    const lastDay = DAYS[799]
    respond = (url) => {
      if (url.includes('start_date=')) {
        // 增量里重叠日 close 与缓存不同 = 前复权历史被重算
        return jsonResponse([bar(lastDay, 999), bar(DAYS[800], 1000)])
      }
      // 翻页直取：page0 返回重算后的全新 800 根，其余页空
      if (url.includes('start=0')) return jsonResponse(DAYS.slice(0, 800).map((d, i) => bar(d, 100 + i)))
      return jsonResponse([])
    }
    const bars = await fetchBars('SZ', '000001', 'DAY')
    expect(bars.length).toBe(800)
    expect(bars[0].close).toBe(100) // 重取后的新序列（原缓存 10 起已被替换）
    expect(bars[799].close).toBe(899)
    await flushPending()
    const stored = await loadBarsSeries(KEY)
    expect(stored![0].close).toBe(100)
    expect(stored!.length).toBe(800)
  })

  test('增量请求失败 → 静默降级用缓存渲染', async () => {
    await saveBarsSeries(KEY, cachedBars())
    respond = () => ({
      ok: false,
      status: 503,
      headers: new Headers({ 'content-type': 'application/json' }),
      json: () => Promise.resolve({ detail: 'busy' }),
    })
    const bars = await fetchBars('SZ', '000001', 'DAY')
    expect(bars.length).toBe(800)
    expect(bars[0].datetime.slice(0, 10)).toBe(DAYS[0])
  })

  test('请求窗口早于缓存起点 → 绕过缓存走翻页直取', async () => {
    // 缓存从 DAYS[10] 起，请求 DAYS[0] 起：缓存覆盖不了窗口起点
    await saveBarsSeries(KEY, cachedBars().slice(10))
    const early = DAYS.slice(0, 100)
    respond = (url) => {
      expect(url).toContain('start=0')
      return jsonResponse(early.map((d, i) => bar(d, 5 + i)))
    }
    const bars = await fetchBars('SZ', '000001', 'DAY', DAYS[0])
    expect(bars.length).toBe(100)
    expect(bars[0].close).toBe(5)
  })

  test('maxCount 窄窗口请求不写缓存（避免污染全量序列）', async () => {
    respond = (url) => {
      if (url.includes('start=0')) return jsonResponse(cachedBars())
      return jsonResponse([])
    }
    const bars = await fetchBars('SZ', '000001', 'DAY', undefined, undefined, 500)
    expect(bars.length).toBe(500)
    await flushPending()
    expect(await loadBarsSeries(KEY)).toBeNull()
  })
})
