// 区间套徽章渲染测试（V853，第61课状态机三态）。
//
// 策略：徽章三态逻辑抽到 utils/qtBadge.ts（单一真源），本文件直接测真实逻辑
// （非重复一份 fixture 模板——避免「改模板忘改 fixture」的沉默回归）。
// 三态（原文第61课）：
//   CONFIRMED → 🔗 套（qt-ok 绿）= 本重背驰确认，可交易转折点；
//   REJECTED  → 🔗✗（qt-reject 红）= 背驰段不成立（力度未衰减，别交易）；
//   ASSUMED   → 🔗?（qt-assumed 灰）= 待观察（暂无证据）。
// 口径区分（V731）：method='cross_period' 才是真实双周期；其他实测确认率 ~3%，
// 标 qt-recursive「🔗 级?」与真跨周期区分，title 前置来源警告。
// 兼容：旧响应无 state 时按 nested 回退（nested→CONFIRMED，否则 ASSUMED）。

import { afterEach, describe, expect, test, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import {
  qtBadgeClass,
  qtBadgeLabel,
  qtBadgeTitle,
  qtResolvedState,
  qtStateColor,
  qtStateMark,
} from '../../utils/qtBadge'

describe('区间套徽章三态（真跨周期口径，V853 第61课）', () => {
  const cp = (state: string, score = 0.6) => ({
    state,
    nested: state === 'CONFIRMED',
    score,
    method: 'cross_period',
    msg: `区间套[${state}] | 测试`,
  })

  test('CONFIRMED → qt-ok + 🔗 套 + score 百分比 + title=msg', () => {
    const qt = cp('CONFIRMED', 0.8)
    expect(qtBadgeClass(qt)).toBe('qt-ok')
    expect(qtBadgeLabel(qt)).toBe('🔗 套')
    expect(qtBadgeTitle(qt)).toBe(qt.msg)
    expect(qtResolvedState(qt)).toBe('CONFIRMED')
  })

  test('REJECTED → qt-reject（红）+ 🔗✗ + title=msg（背驰段不成立，与 ASSUMED 区分）', () => {
    const qt = cp('REJECTED', 0.4)
    expect(qtBadgeClass(qt)).toBe('qt-reject')
    expect(qtBadgeLabel(qt)).toBe('🔗✗')
    expect(qtResolvedState(qt)).toBe('REJECTED')
    // 关键：REJECTED 不应被并入 ASSUMED 的灰类
    expect(qtBadgeClass(qt)).not.toBe('qt-assumed')
  })

  test('ASSUMED → qt-assumed（灰）+ 🔗?（待观察，与 REJECTED 区分）', () => {
    const qt = cp('ASSUMED', 0.0)
    expect(qtBadgeClass(qt)).toBe('qt-assumed')
    expect(qtBadgeLabel(qt)).toBe('🔗?')
    expect(qtResolvedState(qt)).toBe('ASSUMED')
    expect(qtBadgeClass(qt)).not.toBe('qt-reject')
  })

  test('旧响应无 state 字段 → 按 nested 回退（nested=true→CONFIRMED，false→ASSUMED）', () => {
    // nested=true 旧响应 → CONFIRMED（回退）
    const oldOk = { nested: true, score: 0.8, method: 'cross_period', msg: 'ok' }
    expect(qtResolvedState(oldOk)).toBe('CONFIRMED')
    expect(qtBadgeClass(oldOk)).toBe('qt-ok')
    expect(qtBadgeLabel(oldOk)).toBe('🔗 套')
    // nested=false 旧响应 → ASSUMED（回退，不是 REJECTED——旧数据无「不成立」概念）
    const oldNo = { nested: false, score: 0.2, method: 'cross_period', msg: 'no' }
    expect(qtResolvedState(oldNo)).toBe('ASSUMED')
    expect(qtBadgeClass(oldNo)).toBe('qt-assumed')
    expect(qtBadgeLabel(oldNo)).toBe('🔗?')
  })

  test('null/undefined → 空串（徽章不渲染时的安全回退）', () => {
    expect(qtBadgeClass(null)).toBe('')
    expect(qtBadgeLabel(undefined)).toBe('')
    expect(qtResolvedState(null)).toBe('')
  })
})

describe('区间套徽章口径区分（V731：递归/单级别近似不得冒充真区间套）', () => {
  const rec = (state: string) => ({
    state,
    nested: state === 'CONFIRMED',
    score: 0.8,
    method: state === 'CONFIRMED' ? 'recursive' : 'recursive',
    msg: 'rec-msg',
  })

  test('method=recursive 且 CONFIRMED → qt-recursive「🔗 级?」，不是 qt-ok', () => {
    const qt = rec('CONFIRMED')
    expect(qtBadgeClass(qt)).toBe('qt-recursive')
    expect(qtBadgeClass(qt)).not.toBe('qt-ok')
    expect(qtBadgeLabel(qt)).toBe('🔗 级?')
    expect(qtBadgeLabel(qt)).not.toContain('🔗 套')
  })

  test('method=single 同样按非跨周期口径（qt-recursive 或 qt-no）', () => {
    const qt = { state: 'CONFIRMED', nested: true, score: 0.8, method: 'single', msg: 'x' }
    expect(qtBadgeClass(qt)).toBe('qt-recursive')
  })

  test('非跨周期口径 title 必须带来源警告（hover 可见）', () => {
    const qt = rec('CONFIRMED')
    const title = qtBadgeTitle(qt)
    expect(title).toContain('非真跨周期')
    expect(title).toContain('3%')
    expect(title).toContain('rec-msg')
  })

  test('对照：跨周期口径 title 就是原始 msg，不带警告', () => {
    const qt = { state: 'CONFIRMED', nested: true, score: 0.8, method: 'cross_period', msg: 'real-msg' }
    expect(qtBadgeTitle(qt)).toBe('real-msg')
  })
})

// ── V853 图表 overlay：qtStateColor / qtStateMark（ChanlunChart markPoint ring + ✓/✕/?）──
describe('区间套图表 overlay 色/标记（真跨周期三态 + 递归降级）', () => {
  test('真跨周期 CONFIRMED → 绿 ring + ✓', () => {
    const qt = { state: 'CONFIRMED', nested: true, score: 0.8, method: 'cross_period', msg: 'ok' }
    expect(qtStateColor(qt)).toBe('#2ecc71')
    expect(qtStateMark(qt)).toBe('✓')
  })
  test('真跨周期 REJECTED → 红 ring + ✕（背驰段不成立，别交易）', () => {
    const qt = { state: 'REJECTED', nested: false, score: 0.4, method: 'cross_period', msg: 'rej' }
    expect(qtStateColor(qt)).toBe('#e74c3c')
    expect(qtStateMark(qt)).toBe('✕')
  })
  test('真跨周期 ASSUMED → 灰 ring + ?（待观察）', () => {
    const qt = { state: 'ASSUMED', nested: false, score: 0.0, method: 'cross_period', msg: 'as' }
    expect(qtStateColor(qt)).toBe('#95a5a6')
    expect(qtStateMark(qt)).toBe('?')
  })
  test('递归口径 CONFIRMED → amber ring + ✓?（存疑，不冒充真跨周期绿）', () => {
    const qt = { state: 'CONFIRMED', nested: true, score: 0.8, method: 'recursive', msg: 'rec' }
    expect(qtStateColor(qt)).toBe('#f39c12') // amber，不是 #2ecc71 绿
    expect(qtStateMark(qt)).toBe('✓?')
  })
  test('递归口径 REJECTED/ASSUMED → muted 灰 ring + ✕/?（与 qt-no 同口径，不冒充真跨周期红）', () => {
    expect(qtStateColor({ state: 'REJECTED', method: 'recursive' })).toBe('#95a5a6')
    expect(qtStateMark({ state: 'REJECTED', method: 'recursive' })).toBe('✕')
    expect(qtStateColor({ state: 'ASSUMED', method: 'recursive' })).toBe('#95a5a6')
    expect(qtStateMark({ state: 'ASSUMED', method: 'recursive' })).toBe('?')
  })
  test('旧响应无 state：nested=true→CONFIRMED(绿✓)，false→ASSUMED(灰?)', () => {
    expect(qtStateColor({ nested: true, method: 'cross_period' })).toBe('#2ecc71')
    expect(qtStateMark({ nested: true, method: 'cross_period' })).toBe('✓')
    expect(qtStateColor({ nested: false, method: 'cross_period' })).toBe('#95a5a6')
    expect(qtStateMark({ nested: false, method: 'cross_period' })).toBe('?')
  })
  test('null/undefined → 空串（单级别视图不加 ring，回落 ⚠ 或隐藏）', () => {
    expect(qtStateColor(null)).toBe('')
    expect(qtStateMark(undefined)).toBe('')
  })
})

// ── 真实组件透传：/chanlun/analyze 返回带 qujiantao(state) → ChanlunView 不丢字段 ──
const analyzeResponse = {
  mmds: [
    {
      type: '1buy', date: '2025-06-10 00:00:00', msg: '一买', confidence: 0.7,
      bar_index: 100,
      qujiantao: {
        state: 'CONFIRMED', nested: true, score: 0.8, method: 'recursive',
        confidence_adjust: 0.0, msg: 'ok-msg',
        detail: { low_bi_count: 3, low_zs_count: 1 },
        chain: [{ level: '次级别', state: 'CONFIRMED', bi_count: 3, zs_count: 1 }],
      },
    },
    {
      type: '1sell', date: '2025-07-15 00:00:00', msg: '一卖', confidence: 0.4,
      bar_index: 145,
      qujiantao: {
        state: 'REJECTED', nested: false, score: 0.4, method: 'cross_period',
        confidence_adjust: -0.02, msg: 'rejected-msg',
        detail: { low_bi_count: 5, low_zs_count: 1 },
        chain: [{ level: '次周期', state: 'REJECTED', bi_count: 5, zs_count: 1 }],
      },
    },
    { type: '2sell', date: '2025-07-01 00:00:00', msg: '二卖', confidence: 0.5, bar_index: 130 },
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

describe('ChanlunView qujiantao(state) 透传', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test(
    'analyze 响应里的 qujiantao.state/chain 经 mapMmds 后不丢失',
    async () => {
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
      const vm = wrapper.vm as unknown as { analyze: () => Promise<void>; mmds: any[]; error: string }
      await vm.analyze()
      await flushPromises()
      expect(vm.error).toBe('')
      expect(vm.mmds.length).toBeGreaterThanOrEqual(2)
      // CONFIRMED 透传
      const confirmed = vm.mmds.find((m: any) => m.type === '1buy')
      expect(confirmed?.qujiantao).toBeTruthy()
      expect(confirmed.qujiantao.state).toBe('CONFIRMED')
      expect(confirmed.qujiantao.method).toBe('recursive')
      expect(confirmed.qujiantao.detail?.low_bi_count).toBe(3)
      expect(confirmed.qujiantao.chain?.[0]?.state).toBe('CONFIRMED')
      // REJECTED 透传（V853 新增——此前 backend 无 state 字段）
      const rejected = vm.mmds.find((m: any) => m.type === '1sell')
      expect(rejected?.qujiantao).toBeTruthy()
      expect(rejected.qujiantao.state).toBe('REJECTED')
      expect(rejected.qujiantao.nested).toBe(false)
      expect(rejected.qujiantao.chain?.[0]?.state).toBe('REJECTED')
      // 无 qujiantao 的信号 → null
      const noQt = vm.mmds.find((m: any) => m.type === '2sell')
      expect(noQt?.qujiantao).toBeNull()
      // ── 渲染层断言（template 真的调了 util，非只测函数）──
      // 1sell REJECTED(cross_period) → 渲染 <span class="qt-badge qt-reject">🔗✗40
      const badges = wrapper.findAll('.qt-badge')
      expect(badges.length).toBeGreaterThanOrEqual(1)
      const rejBadge = badges.find((b) => b.classes().includes('qt-reject'))
      expect(rejBadge, '应有一个 REJECTED 红徽章').toBeTruthy()
      expect(rejBadge!.text()).toContain('🔗✗')
      expect(rejBadge!.attributes('title')).toBe('rejected-msg')
      // 1buy recursive CONFIRMED → qt-recursive（非真跨周期口径）
      const recBadge = badges.find((b) => b.classes().includes('qt-recursive'))
      expect(recBadge).toBeTruthy()
      expect(recBadge!.text()).toContain('🔗 级?')
      wrapper.unmount()
    },
    30_000,
  )
})
