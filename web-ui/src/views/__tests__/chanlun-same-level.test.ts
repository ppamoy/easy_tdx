// 同级别分解视图测试（V853，第38课分解 + 第105课机械操作，§2.4）。
//
// 后端 to_dict.same_level_segments 已接线（§2.4）。本测试：
// (1) util 逻辑：段方向/走势类型标签 + 末段机械操作（上涨→持有/下跌→避开/空→暂无）；
// (2) real ChanlunView 渲染：分析响应含 same_level_segments → 面板出机械操作横幅 + 段表。

import { afterEach, describe, expect, test, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import {
  slKindLabel,
  slKindClass,
  slTrendLabel,
  slTrendClass,
  slMechanicalHint,
} from '../../utils/sameLevelView'

describe('同级别分解 util（第38课 + 第105课）', () => {
  const segUp = { index: 1, kind: 'up', n_segments: 3, is_panzheng: true, is_trend: false, has_zs: true }
  const segDown = { index: 2, kind: 'down', n_segments: 5, is_trend: true, has_zs: true }
  const segTrend = { index: 3, kind: 'up', is_trend: true, is_panzheng: false, has_zs: true }

  test('kind 标签/类', () => {
    expect(slKindLabel('up')).toBe('↑上涨')
    expect(slKindLabel('down')).toBe('↓下跌')
    expect(slKindLabel('none')).toBe('—未完成')
    expect(slKindClass('up')).toBe('sl-up')
    expect(slKindClass('down')).toBe('sl-down')
  })

  test('走势类型标签（第38课：趋势≥2中枢/盘整1中枢/进行中）', () => {
    expect(slTrendLabel(segUp)).toBe('盘整')
    expect(slTrendLabel(segDown)).toBe('趋势')
    expect(slTrendLabel({ is_trend: false, is_panzheng: false })).toBe('进行中')
    expect(slTrendClass(segTrend)).toBe('slt-trend')
    expect(slTrendClass(segUp)).toBe('slt-panzheng')
  })

  test('末段=上涨盘整 → 机械持有（第105课）', () => {
    const hint = slMechanicalHint([segUp])
    expect(hint.action).toBe('机械持有')
    expect(hint.class).toBe('sl-mech-hold')
    expect(hint.reason).toContain('第105课')
    expect(hint.reason).toContain('上涨盘整')
    expect(hint.reason).toContain('机械卖出')
  })

  test('末段=下跌趋势 → 机械观望（第105课：避开下跌段）', () => {
    const hint = slMechanicalHint([segUp, segDown])
    expect(hint.action).toBe('机械观望')
    expect(hint.class).toBe('sl-mech-sell')
    expect(hint.reason).toContain('下跌')
    expect(hint.reason).toContain('避开')
  })

  test('末段=未完成 → 进行中', () => {
    const hint = slMechanicalHint([segUp, { index: 3, kind: 'none', is_panzheng: false, is_trend: false }])
    expect(hint.action).toBe('进行中')
    expect(hint.class).toBe('sl-mech-watch')
  })

  test('空段列表 → 暂无分段', () => {
    const hint = slMechanicalHint([])
    expect(hint.action).toBe('暂无分段')
    expect(hint.class).toBe('sl-mech-watch')
    const hint2 = slMechanicalHint(null)
    expect(hint2.action).toBe('暂无分段')
  })
})

// ── 真实组件渲染：ChanlunView 出同级别分解面板 ──
const analyzeResponse = {
  mmds: [{ type: '1buy', date: '2025-06-10 00:00:00', msg: '一买', confidence: 0.7, bar_index: 100, anchor_val: 100 }],
  same_level_segments: [
    { index: 1, kind: 'down', n_segments: 3, is_panzheng: true, is_trend: false, has_zs: true,
      start_date: '2025-05-01', end_date: '2025-05-20', start_val: 110, end_val: 95, lines: [], zss: [] },
    { index: 2, kind: 'up', n_segments: 5, is_trend: true, is_panzheng: false, has_zs: true,
      start_date: '2025-05-20', end_date: '2025-06-15', start_val: 95, end_val: 120, lines: [], zss: [] },
  ],
  fractals: [], valid_fractals: [], bis: [], xds: [], zss: [], bcs: [], levels: [],
}

vi.mock('../../api', async () => {
  const actual = await vi.importActual<typeof import('../../api')>('../../api')
  return {
    ...actual,
    fetchBars: vi.fn(async () =>
      Array.from({ length: 800 }, (_, i) => ({
        datetime: `2025-${String(1 + Math.floor(i / 60)).padStart(2, '0')}-${String(1 + (i % 28)).padStart(2, '0')}T15:00:00`,
        open: 1, close: 1, high: 1, low: 1, vol: 1, amount: 1,
      })),
    ),
    loadEarlierBars: vi.fn(async () => []),
  }
})

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), currentRoute: { value: { query: {}, params: {} } } }),
  useRoute: () => ({ query: {}, params: {}, path: '/' }),
}))

describe('ChanlunView 同级别分解面板渲染', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('分析响应含 same_level_segments → 渲染面板 + 机械持有横幅 + 段表', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        new Response(
          JSON.stringify(String(url).includes('/chanlun/analyze') ? analyzeResponse : {}),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
      ),
    )
    const { default: ChanlunView } = await import('../ChanlunView.vue')
    const { createPinia } = await import('pinia')
    const wrapper = shallowMount(ChanlunView, { global: { plugins: [createPinia()] } })
    const vm = wrapper.vm as unknown as { analyze: () => Promise<void>; sameLevelSegments: any[]; error: string }
    await vm.analyze()
    await flushPromises()
    expect(vm.error).toBe('')
    expect(vm.sameLevelSegments.length).toBe(2)
    // 面板渲染
    expect(wrapper.find('.sl-panel').exists()).toBe(true)
    // 末段=上涨趋势 → 机械持有
    const banner = wrapper.find('.sl-mech-banner')
    expect(banner.exists()).toBe(true)
    expect(banner.classes()).toContain('sl-mech-hold')
    expect(banner.text()).toContain('机械持有')
    // 段表 2 行
    const rows = wrapper.findAll('.sl-table tbody tr')
    expect(rows.length).toBe(2)
    const upRow = rows[1] // 第二段 up
    expect(upRow.find('.sl-kind-badge.sl-up').exists()).toBe(true)
    expect(upRow.find('.sl-trend-badge.slt-trend').exists()).toBe(true)
    wrapper.unmount()
  }, 30_000)
})
