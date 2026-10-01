// StockPickView 两步流测试（v590）：Step1 长盈选股 → Step2 缠论择时。
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

import StockPickView from '../StockPickView.vue'

const { stockPickScreen, stockPickTiming, chanlunScreen } = vi.hoisted(() => ({
  stockPickScreen: vi.fn(),
  stockPickTiming: vi.fn(),
  chanlunScreen: vi.fn(),
}))

vi.mock('../../api', () => ({
  formatError: (e: unknown) => (e instanceof Error ? e.message : String(e)),
  stockPickScreen,
  stockPickTiming,
  chanlunScreen,
}))

const testRouter = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/', component: { template: '<div/>' } }],
})

describe('StockPickView 两步流', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  test('Step1 选股后填充基本面标的池', async () => {
    stockPickScreen.mockResolvedValue({
      date: '2025-01-02',
      total: 1,
      results: [
        {
          symbol: 'SH:600519',
          market: 'SH',
          code: '600519',
          category: 'tree',
          quality_score: 88.5,
        },
      ],
    })
    const wrapper = shallowMount(StockPickView, { global: { plugins: [testRouter] } })
    await (wrapper.vm as unknown as { runScreen: () => Promise<void> }).runScreen()
    await flushPromises()
    const pool = (wrapper.vm as unknown as { pool: unknown[] }).pool
    expect(pool).toHaveLength(1)
    expect((pool[0] as { symbol: string }).symbol).toBe('SH:600519')
  })

  test('Step2 择时后展示结论', async () => {
    stockPickTiming.mockResolvedValue({
      date: '2025-01-02',
      results: [
        {
          symbol: 'SH:600519',
          bars: [],
          verdict: { action: '买入', signal: '1buy', confidence: 0.9, reason: 'r' },
        },
      ],
    })
    const wrapper = shallowMount(StockPickView, { global: { plugins: [testRouter] } })
    const item = {
      symbol: 'SH:600519',
      market: 'SH',
      code: '600519',
      category: 'tree',
      quality_score: 88.5,
    }
    await (wrapper.vm as unknown as { runTiming: (i: unknown) => Promise<void> }).runTiming(item)
    await flushPromises()
    const timing = (
      wrapper.vm as unknown as { timingResult: { verdict: { action: string } } | null }
    ).timingResult
    expect(timing?.verdict.action).toBe('买入')
  })

  test('缠论选股标签页调用 chanlunScreen 并渲染结果', async () => {
    chanlunScreen.mockResolvedValue({
      market: 'SZ',
      total_scanned: 4,
      qualified: [
        {
          code: '000001',
          symbol: 'SZ:000001',
          close: 11.32,
          latest_signal: { type: '3buy', is_buy: true, date: '2024-12-01', price: 11.0, confidence: 0.8 },
          trend: 'up',
          zs_position: 'inside',
          has_beichi: true,
          quality_score: 100,
          bi_count: 40,
          zs_count: 7,
          bc_count: 3,
          classification: 'tree',
        },
      ],
      errors: [],
      elapsed: 1.5,
    })
    const wrapper = shallowMount(StockPickView, { global: { plugins: [testRouter] } })
    const vm = wrapper.vm as unknown as {
      activeTab: string
      runChanlunScreen: () => Promise<void>
      clResults: unknown[]
    }
    vm.activeTab = 'chanlun'
    await vm.runChanlunScreen()
    await flushPromises()
    expect(chanlunScreen).toHaveBeenCalledOnce()
    expect(vm.clResults.length).toBe(1)
    expect(vm.clResults[0]).toHaveProperty('code', '000001')
  })
})
