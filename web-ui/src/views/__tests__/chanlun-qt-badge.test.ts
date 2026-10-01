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

// ── 与 ChanlunView.vue 1741-1747 行同构的徽章模板 ──
// （若原模板改动，此处 fixture 需同步；契约测试的价值在于改动必须被双处看见）
const QtBadgeRow = defineComponent({
  props: { m: { type: Object, required: true } },
  template: `
    <span
      v-if="m.qujiantao"
      class="qt-badge"
      :class="m.qujiantao.nested ? 'qt-ok' : 'qt-no'"
      :title="m.qujiantao.msg"
    >{{ m.qujiantao.nested ? '🔗 套' : '🔗✗' }}{{ (m.qujiantao.score * 100).toFixed(0) }}</span>
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

  test('analyze 响应里的 qujiantao 字段经 mapMmds 后不丢失', async () => {
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
  })
})
