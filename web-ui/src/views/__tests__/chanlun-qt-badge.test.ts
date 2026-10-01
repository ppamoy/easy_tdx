// 真·区间套徽章渲染测试（V-29，补 R21 徽章的组件级单测——当时仅 e2e 验证）。
//
// 策略：ChanlunView 是重页面（echarts/router 依赖多），徽章本身是
// 「数据形态 → 展示」的纯映射。用两层测试覆盖：
// 1. 契约测试：用与 ChanlunView 模板同构的 fixture 组件锁定徽章行为
//    （nested→qt-ok + 🔗套 + score 百分比；未确认→qt-no + 🔗✗；null→不渲染；
//     title=完整 msg）——防止有人改徽章模板时丢语义。
// 2. 数据透传测试：mock api 模块的 fetchBars（组件测试里 IndexedDB 缓存
//    快速路径不可靠），全局 fetch stub 接 /chanlun/analyze，shallowMount
//    真实 ChanlunView，断言 mapMmds 透传 qujiantao 字段不丢失。

import { afterEach, describe, expect, test, vi } from 'vitest'
import { flushPromises, mount, shallowMount } from '@vue/test-utils'
import { defineComponent } from 'vue'

// ── 与 ChanlunView.vue 区间套徽章同构的模板 ──
// （若原模板改动，此处 fixture 需同步；契约测试的价值在于改动必须被双处看见）
//
// V731 口径区分：method='cross_period' 才是「真实双周期」（缠论原文语义）；
// 其他（recursive/单级别近似）实测确认率仅 3%，不得呈现为"已确认的区间套"，
// 故用 qt-recursive 类 + 「🔗 级?」文字与 qt-ok 视觉区分。
// 见 docs/区间套现状说明与统一方案.md §七 实测证伪。
const QtBadgeRow = defineComponent({
  props: { m: { type: Object, required: true } },
  template: `
    <span
      v-if="m.qujiantao"
      class="qt-badge"
      :class="
        m.qujiantao.method === 'cross_period'
          ? m.qujiantao.nested ? 'qt-ok' : 'qt-no'
          : m.qujiantao.nested ? 'qt-recursive' : 'qt-no'
      "
      :title="
        m.qujiantao.method === 'cross_period'
          ? m.qujiantao.msg
          : '⚠ 非真跨周期：本标记来自同序列递归级别（或单级别近似），实测确认率约 3%，不能等同于缠论原文的区间套。' + m.qujiantao.msg
      "
    >{{
      m.qujiantao.method === 'cross_period'
        ? m.qujiantao.nested ? '🔗 套' : '🔗✗'
        : m.qujiantao.nested ? '🔗 级?' : '🔗✗'
    }}{{ (m.qujiantao.score * 100).toFixed(0) }}</span>
  `,
})

describe('区间套徽章渲染契约', () => {
  test('nested=true → qt-ok + 🔗套 + score 百分比 + title=msg', () => {
    const w = mount(QtBadgeRow, {
      props: {
        m: {
          qujiantao: {
            nested: true, score: 0.8, method: 'cross_period',
            confidence_adjust: 0.0, msg: '区间套确认 | 低周期窗口内出现同方向底背驰(买)确认',
          },
        },
      },
    })
    const badge = w.find('.qt-badge')
    expect(badge.exists()).toBe(true)
    expect(badge.classes()).toContain('qt-ok')
    expect(badge.text()).toContain('🔗 套')
    expect(badge.text()).toContain('80') // 0.8 → 80
    expect(badge.attributes('title')).toContain('区间套确认')
  })

  test('nested=false → qt-no + 🔗✗（未确认仍可见，score 低）', () => {
    const w = mount(QtBadgeRow, {
      props: {
        m: {
          qujiantao: {
            nested: false, score: 0.2, method: 'recursive',
            confidence_adjust: -0.02, msg: '区间套未确认 | 低级别窗口内无同方向背驰/买卖点确认',
          },
        },
      },
    })
    const badge = w.find('.qt-badge')
    expect(badge.classes()).toContain('qt-no')
    expect(badge.text()).toContain('🔗✗')
    expect(badge.text()).not.toContain('🔗 套')
    expect(badge.attributes('title')).toContain('未确认')
  })

  test('qujiantao=null（无递归级别/无低周期）→ 徽章不渲染', () => {
    const w = mount(QtBadgeRow, { props: { m: { qujiantao: null } } })
    expect(w.find('.qt-badge').exists()).toBe(false)
  })
})

// V731：口径区分 —— 递归/单级别近似不得呈现为"已确认的真区间套"。
// 背景：analyser.py 把 qujiantao_for_result（递归级别，method='recursive'）
// 的结果写进 mmd._qujiantao，前端据此渲染。实测递归确认率 3%（真跨周期 50%），
// 若一律显示「🔗 套」，用户会把"高一级别趋势参考"误当成原文意义的区间套。
describe('区间套徽章口径区分（V731）', () => {
  const qt = (nested: boolean, method: string) => ({
    m: { qujiantao: { nested, score: 0.8, method, confidence_adjust: 0, msg: 'msg-x' } },
  })

  test('method=cross_period 且 nested → qt-ok「🔗 套」（真实双周期，可用）', () => {
    const badge = mount(QtBadgeRow, { props: qt(true, 'cross_period') }).find('.qt-badge')
    expect(badge.classes()).toContain('qt-ok')
    expect(badge.text()).toContain('🔗 套')
  })

  test('method=recursive 且 nested → qt-recursive「🔗 级?」，不是 qt-ok', () => {
    const badge = mount(QtBadgeRow, { props: qt(true, 'recursive') }).find('.qt-badge')
    expect(badge.classes()).toContain('qt-recursive')
    expect(badge.classes()).not.toContain('qt-ok')
    expect(badge.text()).toContain('🔗 级?')
    expect(badge.text()).not.toContain('🔗 套')
  })

  test('method=single 且 nested → 同样按非跨周期口径处理', () => {
    const badge = mount(QtBadgeRow, { props: qt(true, 'single') }).find('.qt-badge')
    expect(badge.classes()).toContain('qt-recursive')
    expect(badge.text()).toContain('🔗 级?')
  })

  test('非跨周期口径的 title 必须带来源警告（用户 hover 可见）', () => {
    const badge = mount(QtBadgeRow, { props: qt(true, 'recursive') }).find('.qt-badge')
    const title = badge.attributes('title') ?? ''
    expect(title).toContain('非真跨周期')
    expect(title).toContain('3%')
  })

  test('对照：跨周期口径的 title 就是原始 msg，不带警告', () => {
    const badge = mount(QtBadgeRow, { props: qt(true, 'cross_period') }).find('.qt-badge')
    expect(badge.attributes('title')).toBe('msg-x')
  })

  test('nested=false → 一律 qt-no「🔗✗」，与 method 无关', () => {
    for (const method of ['cross_period', 'recursive', 'single']) {
      const badge = mount(QtBadgeRow, { props: qt(false, method) }).find('.qt-badge')
      expect(badge.classes()).toContain('qt-no')
      expect(badge.text()).toContain('🔗✗')
      expect(badge.classes()).not.toContain('qt-recursive')
    }
  })
})

// ── 真实组件透传：/chanlun/analyze 返回带 qujiantao → ChanlunView 状态不丢字段 ──
// mmds 赋值链：analyze() → applyAnalysisLevel('bi', data) → mapMmds(data.mmds)。
// fetchBars 走 api 模块 mock（组件测试里 IndexedDB 缓存快速路径不可靠），
// analyze 请求走全局 fetch stub（组件内是原生 fetch 调 /chanlun/analyze）。

const analyzeResponse = {
  mmds: [
    {
      type: '1buy', date: '2025-06-10 00:00:00', msg: '一买', confidence: 0.7,
      bar_index: 100,
      qujiantao: {
        nested: true, score: 0.8, method: 'recursive',
        confidence_adjust: 0.0, msg: 'ok-msg',
        detail: { low_bi_count: 3, low_zs_count: 1 },
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
    // 800 根合成 K 线（与 analyze 返回的 bar_index 同尺度）
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

describe('ChanlunView qujiantao 透传', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  // V731：本用例构造 800 根 bar 并挂载**真实** ChanlunView，单次约 4s；
  // 全量并发跑实测到 6s，超过 vitest 默认 5000ms 而失败 —— 那是**超时**
  // 而非功能缺陷（单独跑 3 次均通过）。显式放宽到 30s，避免把性能抖动
  // 误报成「qujiantao 透传坏了」。
  test(
    'analyze 响应里的 qujiantao 字段经 mapMmds 后不丢失',
    async () => {
      // 用真实 Response（带 headers.get，api 层 V721 的 parseJson 要检查 content-type）
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
    const withQt = vm.mmds.find((m: any) => m.type === '1buy')
      expect(withQt?.qujiantao).toBeTruthy()
      expect(withQt.qujiantao.nested).toBe(true)
      expect(withQt.qujiantao.method).toBe('recursive')
      expect(withQt.qujiantao.detail?.low_bi_count).toBe(3)
      // 无 qujiantao 的信号 → null（mapMmds 的 `?? null` 契约）
      const noQt = vm.mmds.find((m: any) => m.type === '2sell')
      expect(noQt?.qujiantao).toBeNull()
      wrapper.unmount()
    },
    30_000,
  )
})
