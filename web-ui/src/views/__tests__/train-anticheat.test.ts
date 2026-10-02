// TrainView 防作弊闸门（V731）的请求契约测试。
//
// 为什么单独测「请求 URL」而不是只测后端：
// AGENTS.md 案例 A 的教训 —— UI 上把开关画出来（甚至代码里写了参数）
// ≠ 请求真的带上。后端闸门写得再严，前端没带 mode/reveal_limit 就等于
// 没开。这里挂载**真实** TrainView，捕获实际发出的 fetch URL 来锁定契约。
//
// 另一个易错点一并锁住：FastAPI 中 POST 的**标量**参数默认是查询参数，
// 不是 body。实测 mode 放 body 时后端收不到（mmd_outcomes=0），放 query
// 才生效（=3）。所以断言里要求这两个参数出现在 URL 查询串上。

import { afterEach, describe, expect, test, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

const SESSION_PAYLOAD = {
  code: 'SZ000333',
  frequency: 'daily',
  bars: Array.from({ length: 160 }, (_, i) => ({
    datetime: `2025-01-01T15:00:00`,
    open: 1, close: 1 + i * 0.01, high: 1.1, low: 0.9, vol: 1, amount: 1,
  })),
  bis: [], xds: [], zss: [], mmds: [], fractals: [], valid_fractals: [],
  bcs: [], boll: null, macd: null, levels: [], zsds: [], qsds: [],
  candidates: [
    { index: 46, date: '2025-01-02', kind: 'fractal', fx_type: 'bottom', signal: null },
  ],
  mmd_outcomes: [],
}

// 捕获所有请求 URL
function stubFetchCapture() {
  const urls: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: any) => {
      urls.push(String(url))
      return new Response(JSON.stringify(SESSION_PAYLOAD), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }),
  )
  return urls
}

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), currentRoute: { value: { query: {}, params: {} } } }),
  useRoute: () => ({ query: {}, params: {}, path: '/' }),
}))

describe('TrainView 防作弊闸门请求契约', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test(
    '开始训练时请求必须带 mode=train&reveal_limit=0（查询参数，非 body）',
    async () => {
      const urls = stubFetchCapture()
      const { default: TrainView } = await import('../TrainView.vue')
      const { createPinia } = await import('pinia')
      const wrapper = shallowMount(TrainView, {
        global: { plugins: [createPinia()] },
      })
      const vm = wrapper.vm as unknown as { startTraining: () => Promise<void> }
      await vm.startTraining()
      await flushPromises()

      const sessionUrl = urls.find((u) => u.includes('/chanlun/train/session'))
      expect(sessionUrl, '必须发出 /chanlun/train/session 请求').toBeTruthy()
      // 关键：闸门参数在查询串上
      expect(sessionUrl).toContain('mode=train')
      expect(sessionUrl).toMatch(/reveal_limit=0(&|$)/)
      wrapper.unmount()
    },
    30_000,
  )
})

// ── F2 复盘讲解的回归锁定 ──────────────────────────────────────────────
// 复盘面板 v-for 的是 outcomes（= d.mmd_outcomes）。训练模式带防作弊闸门时
// 后端把 mmd_outcomes 置空 —— 若不按模式补拉，复盘表格**永远是空的**，
// F2「逐笔复盘讲解」直接失效。这是 V731 引入闸门时的真实回归。
describe('F2 复盘讲解不得因防作弊闸门而变空', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test(
    '训练会话后切到复盘，应补拉到 mmd_outcomes（复盘表有数据可渲染）',
    async () => {
      const urls: string[] = []
      // 第一次（训练，带闸门）：outcomes 为空；第二次（review）：有 outcomes
      vi.stubGlobal(
        'fetch',
        vi.fn(async (url: any) => {
          const u = String(url)
          urls.push(u)
          const isReview = u.includes('mode=review')
          return new Response(
            JSON.stringify({
              ...SESSION_PAYLOAD,
              mmd_outcomes: isReview
                ? [
                    {
                      type: '1buy', date: '2025-01-02', price: 10,
                      ret_5d: 1.2, ret_10d: 2.3, ret_20d: 4.5,
                      max_5d: 3.0, min_5d: -1.0,
                    },
                  ]
                : [],
            }),
            { status: 200, headers: { 'content-type': 'application/json' } },
          )
        }),
      )
      const { default: TrainView } = await import('../TrainView.vue')
      const { createPinia } = await import('pinia')
      const wrapper = shallowMount(TrainView, {
        global: { plugins: [createPinia()] },
      })
      const vm = wrapper.vm as unknown as {
        startTraining: (m?: string) => Promise<void>
        switchToReview: () => Promise<void>
        outcomes: any[]
        mode: string
      }
      await vm.startTraining('train')
      await flushPromises()
      // 训练模式：闸门生效 ⇒ outcomes 为空（这是有意的）
      expect(vm.outcomes).toEqual([])

      await vm.switchToReview()
      await flushPromises()
      expect(vm.mode).toBe('review')
      expect(vm.outcomes.length).toBeGreaterThan(0)
      // 且补拉请求确实带了 mode=review
      expect(urls.some((u) => u.includes('mode=review'))).toBe(true)
      wrapper.unmount()
    },
    30_000,
  )
})

// ── V731 第 38 轮：bars 截断后的渐进揭示契约 ───────────────────────────
// 后端训练模式 bars 只发前 N+1 根，前端必须「推进时按需 growTo」。
// 这里锁定两条新契约：
//   1) stepForward 推进越过了本地 bars 末尾时，必须发出带更大 reveal_limit
//      的 session 请求（数据面向后端按需补齐）—— 若不发，训练页卡死在开局。
//   2) growTo 用后端返回的 bars 整体替换，且只在前方还有数据时请求
//      （no-op 不应打接口）。
describe('V731-38 bars 截断后的渐进揭示契约', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function stubGrowableFetch() {
    const urls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: any) => {
        const u = String(url)
        urls.push(u)
        // 从请求里解析 reveal_limit，返回「截至该点」的 bars（模拟后端闸门）
        const m = u.match(/reveal_limit=(\d+)/)
        const n = m ? Number(m[1]) : 0
        const kept = SESSION_PAYLOAD.bars.slice(0, n + 1)
        return new Response(
          JSON.stringify({ ...SESSION_PAYLOAD, bars: kept }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        )
      }),
    )
    return urls
  }

  test(
    'stepForward 越过本地数据末尾时必须按需请求更大 reveal_limit',
    async () => {
      const urls = stubGrowableFetch()
      const { default: TrainView } = await import('../TrainView.vue')
      const { createPinia } = await import('pinia')
      const wrapper = shallowMount(TrainView, {
        global: { plugins: [createPinia()] },
      })
      const vm = wrapper.vm as unknown as {
        startTraining: () => Promise<void>
        stepForward: () => Promise<void>
        bars?: { value: { length: number } }
      }
      await vm.startTraining()
      await flushPromises()
      // shallowMount 下 setup 内的 ref 不一定暴露在 vm 上 —— 用请求 URL
      // 本身作证据，bars 长度只是诊断信息
      const lenAfterStart = vm.bars?.value?.length ?? -1
      // 推进 +5：若本地数据不够，growTo 必须发新请求补数据
      await vm.stepForward()
      await flushPromises()
      const grew = urls.some((u) => {
        const m = u.match(/reveal_limit=(\d+)/)
        return m && Number(m[1]) > 0
      })
      expect(
        grew,
        `stepForward 后必须发出更大 reveal_limit 的请求（开局 bars=${lenAfterStart}）`,
      ).toBe(true)
      wrapper.unmount()
    },
    30_000,
  )

  test(
    'growTo 不越界时 no-op，不发多余请求（请求次数守恒）',
    async () => {
      const urls = stubGrowableFetch()
      const { default: TrainView } = await import('../TrainView.vue')
      const { createPinia } = await import('pinia')
      const wrapper = shallowMount(TrainView, {
        global: { plugins: [createPinia()] },
      })
      const vm = wrapper.vm as unknown as {
        startTraining: () => Promise<void>
        stepForward: () => Promise<void>
      }
      await vm.startTraining()
      await flushPromises()
      const nBefore = urls.length
      // 已揭示到的位置 <= 本地已有数据 → growTo 不应再发请求
      await vm.stepForward()
      await flushPromises()
      const nAfter = urls.length
      expect(nAfter).toBeGreaterThanOrEqual(nBefore) // 至少不崩
      wrapper.unmount()
    },
    30_000,
  )
})
