// TrainView F3 训练数据（V731）回归测试。
//
// 需求 F3 有两条，实测此前**两条都没实现**：
//   1. 任意历史区间回放 —— 后端 train/session 支持 start_date/end_date，
//      ChanlunView「时光跳转」已在使用，但训练页既不提供输入、请求也不传。
//   2. 训练会话可保存/续练 —— 全项目 localStorage 只用于自选股/新手引导/
//      阅读记录/最近浏览，训练页零使用。
//
// 另有一条**安全约束**必须锁住：存档里绝不能出现 candidates[].signal 或
// mmd_outcomes（答案 + 未来走势）。否则 localStorage 就成了防作弊闸门
// （4fe2bbb）的旁路：用户 F12 → Application 就能读到全部答案。

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
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
  mmd_outcomes: [] as unknown[],
}

function mountView() {
  return import('../TrainView.vue').then(async ({ default: TrainView }) => {
    const { createPinia } = await import('pinia')
    const wrapper = shallowMount(TrainView, {
      global: { plugins: [createPinia()] },
    })
    await flushPromises()
    return { wrapper, vm: wrapper.vm as unknown as Record<string, any> }
  })
}

function stubFetch(bodies: unknown[] = []) {
  const captured: { url: string; body: any }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: any, opts: any) => {
      captured.push({ url: String(url), body: JSON.parse(opts?.body ?? '{}') })
      return new Response(JSON.stringify(SESSION_PAYLOAD), {
        status: 200, headers: { 'content-type': 'application/json' },
      })
    }),
  )
  return captured
}

describe('F3 训练数据：任意历史区间回放', () => {
  afterEach(() => vi.unstubAllGlobals())

  test(
    '填了历史区间后，train/session 请求必须带上 start_date/end_date',
    async () => {
      const captured = stubFetch()
      const { wrapper, vm } = await mountView()
      // 两个都填才启用（只填一半不应生效，避免歧义）
      vm.startDate = '2024-01-01'
      vm.endDate = '2024-06-30'
      await flushPromises()
      await vm.startTraining()
      await flushPromises()

      // 注意：onMounted 会自动跑一次 startTraining（不带区间），
      // 所以要断言**最后一次**请求，不能 find 到挂载时那一次。
      const req = captured.filter((c) => c.url.includes('train/session')).at(-1)
      expect(req).toBeTruthy()
      expect(req!.body.start_date).toBe('2024-01-01')
      expect(req!.body.end_date).toBe('2024-06-30')
      wrapper.unmount()
    },
    30_000,
  )

  test('只填起始日不填结束日时不应发区间参数（保持按根数取数的原行为）', async () => {
    const captured = stubFetch()
    const { wrapper, vm } = await mountView()
    vm.startDate = '2024-01-01'
    vm.endDate = ''
    await flushPromises()
    await vm.startTraining()
    await flushPromises()

    const req = captured.filter((c) => c.url.includes('train/session')).at(-1)
    expect(req!.body.start_date).toBeUndefined()
    expect(req!.body.end_date).toBeUndefined()
    wrapper.unmount()
  }, 30_000)
})

describe('F3 训练数据：会话保存/续练', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
  })

  test('保存进度后，存档能恢复出参数与计分', async () => {
    stubFetch()
    const { wrapper, vm } = await mountView()
    vm.code = '600519'
    vm.count = 500
    vm.totalAsked = 7
    vm.hitCount = 5
    vm.score = 11
    vm.revealIndex = 88
    await flushPromises()
    vm.saveSession()

    const raw = localStorage.getItem('easy_tdx_train_session_v1')
    expect(raw).toBeTruthy()
    const s = JSON.parse(raw!)
    expect(s.code).toBe('600519')
    expect(s.count).toBe(500)
    expect(s.totalAsked).toBe(7)
    expect(s.score).toBe(11)
    wrapper.unmount()
  }, 30_000)

  test(
    '【安全】存档绝不能包含答案或未来走势（防作弊闸门不得旁路）',
    async () => {
      stubFetch()
      const { wrapper, vm } = await mountView()
      // 构造一版带答案的数据（复盘/全量拉到时的形态）
      vm.candidates = [
        { index: 46, kind: 'mmd', signal: { type: '1buy', confidence: 0.8 } },
      ]
      vm.outcomes = [{ type: '1buy', ret_20d: 13.17 }]
      await flushPromises()
      vm.saveSession()

      const raw = localStorage.getItem('easy_tdx_train_session_v1') ?? ''
      const s = JSON.parse(raw)
      // 存档里不得出现任何 signal / outcome 字段
      expect(JSON.stringify(s)).not.toContain('1buy')
      expect(JSON.stringify(s)).not.toContain('13.17')
      expect(s.signal).toBeUndefined()
      expect(s.mmd_outcomes).toBeUndefined()
      expect(s.candidates).toBeUndefined()
      wrapper.unmount()
    },
    30_000,
  )

  test('续练：存档存在时按钮可用，resumeSession 会恢复参数并重新拉题', async () => {
    const captured = stubFetch()
    const { wrapper, vm } = await mountView()
    vm.code = '000651'
    vm.count = 600
    vm.totalAsked = 4
    vm.score = 6
    vm.revealIndex = 70
    vm.currentCandidateIdx = 0
    await flushPromises()
    vm.saveSession()

    // 改乱当前状态，验证续练能把它恢复回来
    vm.code = '000001'
    vm.count = 100
    vm.totalAsked = 0
    vm.score = 0
    await flushPromises()

    expect(vm.hasSavedSession).toBe(true)
    const before = captured.length
    await vm.resumeSession()
    await flushPromises()
    expect(vm.code).toBe('000651')
    expect(vm.count).toBe(600)
    expect(vm.totalAsked).toBe(4)
    expect(vm.score).toBe(6)
    // 必须重新拉题（不能复用带答案的缓存）
    expect(captured.length).toBeGreaterThan(before)
    wrapper.unmount()
  }, 30_000)
})
