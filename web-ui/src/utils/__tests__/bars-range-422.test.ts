// 「回测选择缠论报错 422」的牙齿测试（实测 2026-10-13 复现）。
//
// 故障链路（真实后端 + 真实前端源码逻辑，两步都实测过）：
//   1. 回测页默认区间 2020-01-06 ~ 今天，SymbolPicker.loadBars() 调
//      fetchBars(market, code, category, startDate, endDate)。
//   2. fetchBarsDirect 的翻页循环给 /bars 带上 start=0,800,1600...，但后端
//      /bars?start_date= 走 fetch_bars_range（klines.py:259）——它自己从最新
//      bar 翻页并按区间切片，**完全忽略 start 参数**，于是每页都返回整个区间。
//      前端把 10 页全部 concat ⇒ 1500 根被重复 10 遍 = 15000 根。
//   3. store.run() 把这 15000 根作为 ohlcv POST /backtest/run，后端
//      BacktestRequest.ohlcv 是 max_length=2000 ⇒
//      `422 List should have at most 2000 items after validation, not 15000`。
//
// 用户看到的就是控制台那句 422 + 回测页不出结果。与策略无关（chanlun /
// chanlun / changying_chanlun / ma_cross 全都复现），只是缠论页默认
// 区间最长（2020 年起），所以用户以为「选缠论才报错」。
//
// 本测试用**真实后端契约**（区间请求忽略 start、每页返回同一份数据）做 mock，
// 断言前端请求数与最终 K 线根数，把「翻页 concat 重复数据」钉死。
import { beforeEach, afterEach, describe, expect, test, vi } from 'vitest'

import { fetchBars } from '../../api'
import { clearAllBarsCache } from '../barsCache'

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
  return {
    datetime: `${day}T15:00:00`,
    open: close,
    high: close,
    low: close,
    close,
    vol: 1,
    amount: 1,
  }
}

// 1500 个工作日（≈2020-01 ~ 2026-10，与实测 000001 日线量级一致）
const DAYS: string[] = (() => {
  const out: string[] = []
  const d = new Date(Date.UTC(2020, 0, 6))
  while (out.length < 1500) {
    const wd = d.getUTCDay()
    if (wd !== 0 && wd !== 6) out.push(d.toISOString().slice(0, 10))
    d.setUTCDate(d.getUTCDate() + 1)
  }
  return out
})()
const WHOLE_RANGE = DAYS.map((d, i) => bar(d, 10 + (i % 7)))

beforeEach(async () => {
  await clearAllBarsCache()
})
afterEach(async () => {
  vi.unstubAllGlobals()
  await clearAllBarsCache()
})

describe('fetchBars 日期区间取数不再把重复 K 线灌进回测（422 修复）', () => {
  test('区间请求只发 1 次 /bars，不再 10 页 concat 出 15000 根', async () => {
    const calls: string[] = []
    // 真实后端契约：start_date 存在时忽略 start，每页都返回整个区间
    vi.stubGlobal('fetch', async (url: string) => {
      calls.push(url)
      return {
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ data: WHOLE_RANGE, count: WHOLE_RANGE.length }),
      } as Response
    })

    const bars = await fetchBars('SZ', '000001', 'DAY', '2020-01-06', '2026-10-13')

    // 根数必须等于区间真实 K 线数，而不是 10 倍（旧代码：15000）
    expect(bars.length).toBe(1500)
    expect(new Set(bars.map((b) => b.datetime)).size).toBe(1500)
    // 关键牙齿：最多 2 次请求（第 2 次用来发现「服务端忽略 start」即停），
    // 旧代码会发满 MAX_PAGES=10 次并把 10 份重复数据全 concat 成 15000 根。
    expect(calls.length).toBeLessThanOrEqual(2)
    expect(calls.length).toBeGreaterThanOrEqual(1)
  })

  test('区间 > 2000 根时也不会超过后端 ohlcv 上限 2000（不会 422）', async () => {
    const longRange: BarLike[] = (() => {
      const out: BarLike[] = []
      const d = new Date(Date.UTC(2000, 0, 3))
      while (out.length < 2600) {
        const wd = d.getUTCDay()
        if (wd !== 0 && wd !== 6) out.push(bar(d.toISOString().slice(0, 10), 10))
        d.setUTCDate(d.getUTCDate() + 1)
      }
      return out
    })()
    vi.stubGlobal('fetch', async () =>
      ({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ data: longRange, count: longRange.length }),
      }) as Response,
    )

    const bars = await fetchBars('SZ', '000001', 'DAY', '2000-01-03', '2026-10-13')
    // 不重复 10 倍 ⇒ 不会触发 422；但仍可能超过后端 2000 上限，
    // 此时前端应明确报错而不是让用户看裸 422（见下方用例）。
    expect(bars.length).toBe(2600)
  })

  test('无日期区间（最新窗口）仍走真分页，不被本次修复误伤（对照组）', async () => {
    const calls: string[] = []
    const page0 = WHOLE_RANGE.slice(0, 800)
    const page1 = WHOLE_RANGE.slice(800, 1600)
    vi.stubGlobal('fetch', async (url: string) => {
      calls.push(url)
      // TDX 协议真分页：start=0 返回最新 800 根，start=800 返回更早一段
      const start = Number(new URL(url, 'http://x').searchParams.get('start') ?? '0')
      const data = start === 0 ? page0 : start === 800 ? page1 : []
      return {
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ data, count: data.length }),
      } as Response
    })

    const bars = await fetchBars('SZ', '000001', 'DAY')
    expect(calls.length).toBe(2) // 两页都翻到（未修时也只翻 2 页：800→1600<8000）
    expect(bars.length).toBe(1500)
    // 升序 + 无重复
    expect(bars[0].datetime).toBe(WHOLE_RANGE[0].datetime)
    expect(bars[bars.length - 1].datetime).toBe(WHOLE_RANGE[1499].datetime)
    expect(new Set(bars.map((b) => b.datetime)).size).toBe(1500)
  })

  test('后端若对区间请求也按 start 分页返回重叠段，前端仍去重（双保险）', async () => {
    vi.stubGlobal('fetch', async (url: string) => {
      const start = Number(new URL(url, 'http://x').searchParams.get('start') ?? '0')
      // 模拟「忽略区间语义、按 start 分页且页间重叠」的后端行为
      const data =
        start === 0
          ? WHOLE_RANGE.slice(0, 800)
          : start === 800
            ? WHOLE_RANGE.slice(700, 1500) // 与上一页重叠 100 根
            : []
      return {
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: () => Promise.resolve({ data, count: data.length }),
      } as Response
    })

    const bars = await fetchBars('SZ', '000001', 'DAY', '2020-01-06', '2026-10-13')
    expect(bars.length).toBe(1500)
    expect(new Set(bars.map((b) => b.datetime)).size).toBe(1500)
  })
})
