// 2买/2卖 形态徽章测试（V853，第101课三情况，§2.3 修复可视化）。
//
// 原文第101课：2买有三情况——一般(高于1买)/最强(2-3买合一)/最弱(跌破1买，原文允许)。
// §2.3 修复（mmd_2nd_max_pullback=None 默认原文）前，「跌破1买」被 50% 回撤门槛吞掉；
// 修复后可达，本徽章把它在 UI 上显式标出。
// 实测 8 只日线：2买/2卖 55 个，最弱 21（38%）、一般 34——「跌破1买」14 个即修复后才可见。
//
// 测两层：(1) util 逻辑（最弱/一般/null）；(2) real ChanlunView 渲染出徽章 DOM。

import { afterEach, describe, expect, test, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import {
  mmd2Form,
  mmd2FormClass,
  mmd2FormLabel,
  mmd2FormTitle,
} from '../../utils/mmd2Form'

describe('2买形态识别（util，第101课）', () => {
  // 1买 low=100，2买 low=95（跌破）⇒ 最弱
  const mmdsWeakest = [
    { type: '1buy', bar_index: 10, anchor_val: 100 },
    { type: '2buy', bar_index: 30, anchor_val: 95 },
  ]
  // 1买 low=100，2买 low=110（高于）⇒ 一般
  const mmdsGeneral = [
    { type: '1buy', bar_index: 10, anchor_val: 100 },
    { type: '2buy', bar_index: 30, anchor_val: 110 },
  ]

  test('2买 anchor_val < 配对1买 ⇒ 最弱·跌破1买', () => {
    const m = mmdsWeakest[1]
    expect(mmd2Form(mmdsWeakest, m)).toBe('weakest_break_1')
    expect(mmd2FormLabel(mmd2Form(mmdsWeakest, m))).toBe('⚠最弱·破1买')
    expect(mmd2FormClass(mmd2Form(mmdsWeakest, m))).toBe('m2-weakest')
    const title = mmd2FormTitle(mmd2Form(mmdsWeakest, m))
    expect(title).toContain('第101课')
    expect(title).toContain('跌破1买')
    expect(title).toContain('§2.3')
  })

  test('2买 anchor_val > 配对1买 ⇒ 一般', () => {
    const m = mmdsGeneral[1]
    expect(mmd2Form(mmdsGeneral, m)).toBe('general')
    expect(mmd2FormLabel(mmd2Form(mmdsGeneral, m))).toBe('一般')
    expect(mmd2FormClass(mmd2Form(mmdsGeneral, m))).toBe('m2-general')
  })

  test('2卖对称：anchor_val > 配对1卖 ⇒ 最弱·突破1卖', () => {
    const mmds = [
      { type: '1sell', bar_index: 10, anchor_val: 50 },
      { type: '2sell', bar_index: 30, anchor_val: 55 }, // 创新高 ⇒ 最弱
    ]
    expect(mmd2Form(mmds, mmds[1])).toBe('weakest_break_1')
    // 2卖 anchor_val < 1卖 ⇒ 一般
    const mmds2 = [
      { type: '1sell', bar_index: 10, anchor_val: 50 },
      { type: '2sell', bar_index: 30, anchor_val: 45 },
    ]
    expect(mmd2Form(mmds2, mmds2[1])).toBe('general')
  })

  test('取最近的配对1买（多个1买时取前一个最近）', () => {
    const mmds = [
      { type: '1buy', bar_index: 5, anchor_val: 90 },
      { type: '1buy', bar_index: 20, anchor_val: 105 }, // 最近，2买跟它比
      { type: '2buy', bar_index: 40, anchor_val: 100 },
    ]
    // 2买=100 < 最近1买=105 ⇒ 最弱
    expect(mmd2Form(mmds, mmds[2])).toBe('weakest_break_1')
  })

  test('非 2买/2卖 ⇒ null（不渲染）', () => {
    expect(mmd2Form([{ type: '1buy', bar_index: 1, anchor_val: 1 }], { type: '1buy', bar_index: 2, anchor_val: 2 })).toBeNull()
    expect(mmd2Form([{ type: '3buy', bar_index: 1, anchor_val: 1 }], { type: '3buy', bar_index: 2, anchor_val: 2 })).toBeNull()
  })

  test('无配对1买（2买前面没1买）⇒ null', () => {
    expect(mmd2Form([{ type: '2buy', bar_index: 10, anchor_val: 95 }], { type: '2buy', bar_index: 10, anchor_val: 95 })).toBeNull()
  })
})

// ── 真实组件渲染：ChanlunView 买卖点明细出形态徽章 ──
const analyzeResponse = {
  mmds: [
    { type: '1buy', date: '2025-06-10 00:00:00', msg: '一买', confidence: 0.7, bar_index: 100, anchor_val: 100 },
    // 2买跌破1买（95<100）⇒ 最弱·破1买（§2.3 修复后可见）
    { type: '2buy', date: '2025-06-25 00:00:00', msg: '二买', confidence: 0.6, bar_index: 130, anchor_val: 95 },
    { type: '2buy', date: '2025-07-10 00:00:00', msg: '二买', confidence: 0.5, bar_index: 160, anchor_val: 108 }, // 高于 ⇒ 一般
    { type: '3buy', date: '2025-07-20 00:00:00', msg: '三买', confidence: 0.4, bar_index: 180, anchor_val: 110 },
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

describe('ChanlunView 2买形态徽章渲染', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('2买跌破1买 → 渲染 ⚠最弱·破1买 红徽章；2买高于1买 → 一般灰徽章；非2买无徽章', async () => {
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
    const vm = wrapper.vm as unknown as { analyze: () => Promise<void>; mmds: any[]; error: string }
    await vm.analyze()
    await flushPromises()
    expect(vm.error).toBe('')
    const badges = wrapper.findAll('.m2-form-badge')
    // 2 个 2买 → 2 个徽章；1buy/3buy 无徽章
    expect(badges.length).toBe(2)
    const weakest = badges.find((b) => b.classes().includes('m2-weakest'))
    expect(weakest, '应有一个最弱红徽章').toBeTruthy()
    expect(weakest!.text()).toBe('⚠最弱·破1买')
    expect(weakest!.attributes('title')).toContain('第101课')
    const general = badges.find((b) => b.classes().includes('m2-general'))
    expect(general).toBeTruthy()
    expect(general!.text()).toBe('一般')
    wrapper.unmount()
  }, 30_000)
})
