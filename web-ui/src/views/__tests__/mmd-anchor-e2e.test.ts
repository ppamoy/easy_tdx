/**
 * 买卖点「端到端字段契约」测试（V731 审计）。
 *
 * 目标：锁死「后端输出的 anchor_val 必须一路传到视图状态（进而传到图上）」。
 *
 * 为什么需要这个测试：V731 之前 ChanlunView.mapMmds 漏映射 anchor_val
 * （而同文件的 mapBcs 却映射了），导致图上买卖点标记静默退化成
 * 「该K线 low*0.995 / high*1.005」的视觉偏移值 —— 用户看到的标记价格
 * 并不是模型识别出的买卖点真实价格。既有单测全绿（1722 个 chanlun 测试通过），
 * 因为它们只断言「画了标记」，从不断言「画在哪个价格上」。
 *
 * 本测试用**真实后端 payload 字段集**（对齐 src/easy_tdx/chanlun/analyser.py
 * ::_mmd_dict_core 输出）驱动 ChanlunView 的 analyze() → mapMmds 链路，
 * 断言 anchor_val 不丢失。anchor_val 一旦从映射链上掉下来，本测试立刻失败。
 *
 * 手法参照同目录 chanlun-qt-badge.test.ts（shallowMount + fetch stub）。
 */

import { afterEach, describe, expect, test, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'

/** 对齐 analyser._mmd_dict_core 的字段集（anchor_val = 分型极值价）。 */
const analyzeResponse = {
  mmds: [
    {
      type: '1buy', date: '2025-06-10 00:00:00', msg: '一买', confidence: 0.7,
      bar_index: 100,
      // ↓↓↓ 画图纵轴的唯一真源；被 mapMmds 丢弃则标记价格失真
      anchor_val: 8.88,
    },
    {
      type: '1sell', date: '2025-07-01 00:00:00', msg: '一卖', confidence: 0.5,
      bar_index: 130,
      anchor_val: 13.21,
    },
    {
      type: '3buy', date: '2025-07-20 00:00:00', msg: '三买', confidence: 0.6,
      bar_index: 150,
      anchor_val: 9.99,
    },
  ],
  fractals: [], valid_fractals: [], bis: [], xds: [], zss: [], bcs: [], levels: [],
}

vi.mock('../../api', async () => {
  const actual = await vi.importActual<typeof import('../../api')>('../../api')
  return {
    ...actual,
    // 800 根合成 K 线（与 analyze 返回的 bar_index 同尺度）
    fetchBars: vi.fn(async () =>
      Array.from({ length: 800 }, (_, i) => ({
        datetime: `2025-${String(1 + Math.floor(i / 60)).padStart(2, '0')}-${String(1 + (i % 28)).padStart(2, '0')}T15:00:00`,
        open: 10, close: 10, high: 11, low: 9, vol: 1, amount: 1,
      })),
    ),
    loadEarlierBars: vi.fn(async () => []),
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

describe('ChanlunView anchor_val 透传（买卖点画图价格真源）', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('analyze 响应里的 anchor_val 经 mapMmds 后不丢失', async () => {
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
    const wrapper = shallowMount(ChanlunView, {
      global: { plugins: [createPinia()] },
    })
    const vm = wrapper.vm as unknown as {
      analyze: () => Promise<void>
      mmds: any[]
      error: string
    }
    await vm.analyze()
    await flushPromises()
    expect(vm.error).toBe('')
    expect(vm.mmds.length).toBe(3)

    // 核心断言：每个买卖点都必须保留 anchor_val，且数值与后端一致
    const expected: Record<string, number> = {
      '1buy': 8.88,
      '1sell': 13.21,
      '3buy': 9.99,
    }
    for (const m of vm.mmds) {
      expect(
        m.anchor_val,
        `mapMmds 丢弃了 anchor_val（${m.type}）→ 图上标记会退化为 low*0.995 / high*1.005 的偏移价，`
          + '不再是模型识别的买卖点价格',
      ).not.toBeUndefined()
      expect(m.anchor_val).not.toBeNull()
      expect(m.anchor_val).toBeCloseTo(expected[m.type], 6)
    }
    wrapper.unmount()
  }, 30000)

  test('bar_index 同样必须透传（横轴锚定）', async () => {
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
    const wrapper = shallowMount(ChanlunView, {
      global: { plugins: [createPinia()] },
    })
    const vm = wrapper.vm as unknown as { analyze: () => Promise<void>; mmds: any[] }
    await vm.analyze()
    await flushPromises()
    expect(vm.mmds.map((m: any) => m.bar_index)).toEqual([100, 130, 150])
    wrapper.unmount()
  }, 30000)
})
