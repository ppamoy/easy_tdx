// StockPickView 两步流测试（v590）：Step1 长盈选股 → Step2 缠论择时。
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

import StockPickView from '../StockPickView.vue'

const { stockPickScreen, stockPickTiming } = vi.hoisted(() => ({
  stockPickScreen: vi.fn(),
  stockPickTiming: vi.fn(),
}))

vi.mock('../../api', () => ({
  formatError: (e: unknown) => (e instanceof Error ? e.message : String(e)),
  stockPickScreen,
  stockPickTiming,
}))

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
    const wrapper = shallowMount(StockPickView)
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
    const wrapper = shallowMount(StockPickView)
    const item = { symbol: 'SH:600519', market: 'SH', code: '600519', category: 'tree', quality_score: 88.5 }
    await (wrapper.vm as unknown as { runTiming: (i: unknown) => Promise<void> }).runTiming(item)
    await flushPromises()
    const timing = (wrapper.vm as unknown as { timingResult: { verdict: { action: string } } | null }).timingResult
    expect(timing?.verdict.action).toBe('买入')
  })
})