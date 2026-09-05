/**
 * 视图冒烟测试（V389）：13 个视图页各挂载一次，验证不抛运行时错误并渲染根容器。
 *
 * 策略：shallowMount 桩掉所有子组件（echarts 图表组件不会真实 init），
 * 同时 mock api / echarts-setup / vue-router，stub 全局 fetch——
 * 保证 jsdom 环境纯离线、无 DOM canvas 依赖，挂载稳定。
 */

import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { createPinia } from 'pinia'
import { shallowMount } from '@vue/test-utils'

import BacktestView from '../BacktestView.vue'
import ChangyingView from '../ChangyingView.vue'
import ChanlunView from '../ChanlunView.vue'
import CompareView from '../CompareView.vue'
import DiagnosisView from '../DiagnosisView.vue'
import FundamentalView from '../FundamentalView.vue'
import MonitorView from '../MonitorView.vue'
import OptimizeView from '../OptimizeView.vue'
import PortfolioView from '../PortfolioView.vue'
import ScreeningView from '../ScreeningView.vue'
import ServerSettingsView from '../ServerSettingsView.vue'
import StrategiesView from '../StrategiesView.vue'
import TrainView from '../TrainView.vue'
import SignalVerifyView from '../SignalVerifyView.vue'

vi.mock('../../api', () => {
  const fn = vi.fn(async () => undefined)
  return {
    formatError: (e: unknown) => (e instanceof Error ? e.message : String(e)),
    fetchStrategies: fn,
    fetchBars: fn,
    runBacktest: fn,
    submitBacktestTask: fn,
    submitPortfolioTask: fn,
    submitMultiStrategyTask: fn,
    submitOptimizeTask: fn,
    submitOptimizeAllTask: fn,
    fetchTask: fn,
    fetchTaskList: fn,
    runBacktestWithPolling: fn,
    fetchSavedStrategies: fn,
    fetchSavedStrategy: fn,
    saveStrategy: fn,
    deleteSavedStrategy: fn,
    updateStrategySnapshot: fn,
    fetchServerHosts: fn,
    testServerHosts: fn,
    switchServerHost: fn,
    fetchDiagnosis: fn,
    fetchAdviceSimulate: fn,
    fetchMultiStockComparison: fn,
  }
})

vi.mock('../../echarts-setup', () => {
  const noop = () => undefined
  const stub = {
    init: () => ({ setOption: noop, resize: noop, dispose: noop }),
    use: noop,
    registerTheme: noop,
  }
  return {
    default: stub,
    UP_COLOR: '#ef4146',
    DOWN_COLOR: '#18a058',
  }
})

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    currentRoute: { value: { query: {}, params: {} } },
  }),
  useRoute: () => ({ query: {}, params: {}, path: '/' }),
}))

const VIEWS = [
  BacktestView,
  ChangyingView,
  ChanlunView,
  CompareView,
  DiagnosisView,
  FundamentalView,
  MonitorView,
  OptimizeView,
  PortfolioView,
  ScreeningView,
  ServerSettingsView,
  StrategiesView,
  TrainView,
  SignalVerifyView,
] as const

describe('视图冒烟测试', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          bars: [],
          mmds: [],
          stocks: [],
          hosts: [],
          tasks: [],
          strategies: [],
          results: [],
          signals: [],
          rows: [],
        }),
      })),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  for (const View of VIEWS) {
    test(`${View.__name || View.name || 'View'} 挂载不抛错`, () => {
      const wrapper = shallowMount(View as never, {
        global: { plugins: [createPinia()] },
      })
      expect(wrapper.element).toBeTruthy()
    })
  }
})
