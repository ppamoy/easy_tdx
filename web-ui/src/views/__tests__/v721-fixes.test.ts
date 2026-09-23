// V721 修复回归测试：D16 api.ts 非 JSON 响应防御 + D18 DiagnosisView error 分支。
import { beforeAll, beforeEach, describe, expect, test, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

import { fetchDiagnosis, fetchStrategies, runBacktest } from '../../api'

// D18：DiagnosisView 仅依赖 fetchDiagnosis / fetchBars（本用例不触发 fetchBars 路径）。
const { fetchDiagnosisMock } = vi.hoisted(() => ({ fetchDiagnosisMock: vi.fn() }))
vi.mock('../../api', async () => {
  const actual = await vi.importActual<typeof import('../../api')>('../../api')
  return { ...actual, fetchDiagnosis: fetchDiagnosisMock }
})

// DiagnosisView onMounted 读取 route.query，jsdom 下无真实 router，须桩化。
vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    currentRoute: { value: { query: {}, params: {} } },
  }),
  useRoute: () => ({ query: {}, params: {}, path: '/' }),
}))

function htmlResponse(): Response {
  // 模拟重启窗口内网关/SPA 兜底返回的 index.html（200 + text/html）
  return new Response('<!DOCTYPE html><html><body>spa</body></html>', {
    status: 200,
    headers: { 'content-type': 'text/html' },
  })
}

describe('V721 D16：api.ts 非 JSON 响应防御', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  test('GET 主路径返回 text/html → 抛「服务正在重启」而非 JSON.parse 报错', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(htmlResponse())
    await expect(fetchStrategies()).rejects.toThrow('服务正在重启，请稍候重试')
  })

  test('POST 主路径（runBacktest）返回 text/html → 同样抛友好错误', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(htmlResponse())
    await expect(runBacktest({ strategy: 'ma_cross' } as never)).rejects.toThrow(
      '服务正在重启，请稍候重试',
    )
  })

  test('错误路径（!ok + text/html）→ throwError 也给友好信息', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(htmlResponse())
    await expect(fetchStrategies()).rejects.toThrow(/服务正在重启/)
  })

  test('JSON 响应不受影响（守卫不误伤）', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ strategies: [], count: 0 }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    )
    await expect(fetchStrategies()).resolves.toEqual({ strategies: [], count: 0 })
  })
})

describe('V721 D18：DiagnosisView error 分支', () => {
  // DiagnosisView.vue 体积大，动态 import 放 beforeAll（不计入单用例时钟）
  let DiagnosisView: (typeof import('../DiagnosisView.vue'))['default']
  beforeAll(
    async () => {
      ;({ default: DiagnosisView } = await import('../DiagnosisView.vue'))
    },
    // V722: 视图体积 1.5w 行，jsdom 冷 import 在 CI 波动会超 10s 默认值
    30_000,
  )

  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('200+{"error"} → error 展示后端消息且不渲染诊断结果', async () => {
    fetchDiagnosisMock.mockResolvedValue({ error: '该股票无K线数据' })
    const wrapper = shallowMount(DiagnosisView)
    await (wrapper.vm as unknown as { runDiagnosis: () => Promise<void> }).runDiagnosis()
    await flushPromises()
    const vm = wrapper.vm as unknown as { error: string; diagnosis: unknown }
    expect(vm.error).toBe('该股票无K线数据')
    expect(vm.diagnosis).toBeNull()
  }, 20_000)

  test('正常响应 → error 为空、diagnosis 有值（不误伤）', async () => {
    // 模板直接访问 diagnosis.chanlun.* 等嵌套字段，mock 需给全空对象占位
    fetchDiagnosisMock.mockResolvedValue({
      symbol: 'SZ000001',
      date: '2026-01-01',
      close: 10,
      score: 80,
      action: 'buy',
      action_label: '买入',
      action_color: '#22c55e',
      reason: 'r',
      chanlun: { bi_count: 0, zs_count: 0, mmds: [], recent_signals: [] },
      macd: {},
      boll: {},
      kdj: {},
      rsi: {},
      adx: {},
      obv: {},
      volume: {},
      moving_averages: {},
      candlestick: {},
      fibonacci: {},
      divergence: {},
      risk: {},
      valuation: {},
      position_suggestion: {},
    })
    const wrapper = shallowMount(DiagnosisView)
    await (wrapper.vm as unknown as { runDiagnosis: () => Promise<void> }).runDiagnosis()
    await flushPromises()
    const vm = wrapper.vm as unknown as { error: string; diagnosis: unknown }
    expect(vm.error).toBe('')
    expect(vm.diagnosis).not.toBeNull()
  }, 20_000)
})
