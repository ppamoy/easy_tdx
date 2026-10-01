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
