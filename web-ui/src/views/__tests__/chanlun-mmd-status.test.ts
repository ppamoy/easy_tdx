// 1买/1卖背驰确立 + 3买/3卖ZG安全距离 状态徽章测试（V853 工具①③）。
//
// 工具①（第29课后置验证）：rebound_verified True→✓背驰确立 / False→⚠疑似背驰 / null→?待验证。
// 工具③（第20课）：3买回踩 anchor_val vs zs_zg → 不破ZG✅+安全距离；3卖对称（vs zs_zd）。

import { afterEach, describe, expect, test, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import {
  mmd1Status,
  mmd1StatusLabel,
  mmd1StatusClass,
  mmd1StatusTitle,
  mmd3Status,
} from '../../utils/mmdStatusBadge'

describe('工具① 1买背驰确立状态（第29课）', () => {
  test('rebound_verified=true → confirmed ✓背驰确立', () => {
    const m = { type: '1buy', rebound_verified: true, anchor_val: 100, zs_zg: 95 }
    expect(mmd1Status(m)).toBe('confirmed')
    expect(mmd1StatusLabel(mmd1Status(m))).toBe('✓背驰确立')
    expect(mmd1StatusClass(mmd1Status(m))).toBe('b1-confirmed')
    expect(mmd1StatusTitle(mmd1Status(m))).toContain('第29课')
    expect(mmd1StatusTitle(mmd1Status(m))).toContain('背驰确立')
  })

  test('rebound_verified=false → suspect ⚠疑似背驰', () => {
    const m = { type: '1buy', rebound_verified: false }
    expect(mmd1Status(m)).toBe('suspect')
    expect(mmd1StatusLabel(mmd1Status(m))).toBe('⚠疑似背驰')
    expect(mmd1StatusClass(mmd1Status(m))).toBe('b1-suspect')
    expect(mmd1StatusTitle(mmd1Status(m))).toContain('疑似')
  })

  test('rebound_verified=null → pending ?待验证', () => {
    const m = { type: '1sell', rebound_verified: null }
    expect(mmd1Status(m)).toBe('pending')
    expect(mmd1StatusLabel(mmd1Status(m))).toBe('?待验证')
  })

  test('非 1买/1卖 → null（不渲染）', () => {
    expect(mmd1Status({ type: '2buy', rebound_verified: true })).toBeNull()
    expect(mmd1Status({ type: '3buy', rebound_verified: true })).toBeNull()
  })

  test('1卖也走同样三态（对称）', () => {
    expect(mmd1Status({ type: '1sell', rebound_verified: true })).toBe('confirmed')
  })
})

describe('工具③ 3买/3卖 ZG安全距离（第20课）', () => {
  test('3买回踩 > ZG → 不破ZG✅ + 正安全距离', () => {
    const m = { type: '3buy', anchor_val: 102, zs_zg: 100, zs_zd: 95 }
    const st = mmd3Status(m)!
    expect(st.ok).toBe(true)
    expect(st.gap).toBe(2)
    expect(st.class).toBe('b3-ok')
    expect(st.label).toContain('102')
    expect(st.label).toContain('100')
    expect(st.title).toContain('第20课')
    expect(st.title).toContain('不破ZG')
  })

  test('3买回踩 < ZG → 破ZG❌（理论上检测已过滤，但徽章如实标）', () => {
    const m = { type: '3buy', anchor_val: 99, zs_zg: 100 }
    const st = mmd3Status(m)!
    expect(st.ok).toBe(false)
    expect(st.gap).toBe(-1)
    expect(st.class).toBe('b3-bad')
    expect(st.title).toContain('跌破')
  })

  test('3卖对称：回踩 < ZD → 不破ZD✅', () => {
    const m = { type: '3sell', anchor_val: 93, zs_zg: 100, zs_zd: 95 }
    const st = mmd3Status(m)!
    expect(st.ok).toBe(true) // ZD95 - 回踩93 = +2 > 0
    expect(st.gap).toBe(2)
    expect(st.class).toBe('b3-ok')
    expect(st.title).toContain('ZD')
  })

  test('非 3买/3卖 → null', () => {
    expect(mmd3Status({ type: '1buy', anchor_val: 100, zs_zg: 95 })).toBeNull()
    expect(mmd3Status({ type: '2buy' })).toBeNull()
  })

  test('缺 anchor_val/zs_zg → null', () => {
    expect(mmd3Status({ type: '3buy', zs_zg: 100 })).toBeNull()
    expect(mmd3Status({ type: '3buy', anchor_val: 100 })).toBeNull()
  })
})

// ── 真实组件渲染 ──
const analyzeResponse = {
  mmds: [
    { type: '1buy', date: '2025-06-10 00:00:00', msg: '一买', confidence: 0.7, bar_index: 100, anchor_val: 100, zs_zg: 110, rebound_verified: true },
    { type: '1sell', date: '2025-06-20 00:00:00', msg: '一卖', confidence: 0.6, bar_index: 120, anchor_val: 120, zs_zg: 115, rebound_verified: false },
    { type: '3buy', date: '2025-07-01 00:00:00', msg: '三买', confidence: 0.5, bar_index: 140, anchor_val: 108, zs_zg: 105, zs_zd: 100 },
    { type: '2buy', date: '2025-07-10 00:00:00', msg: '二买', confidence: 0.4, bar_index: 150, anchor_val: 102, zs_zg: 105 }, // 非1/3买，无状态徽章
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

describe('ChanlunView 1买/3买状态徽章渲染', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('1buy→✓背驰确立(b1-confirmed)；1sell→⚠疑似背驰(b1-suspect)；3buy→不破ZG(b3-ok)；2buy→无徽章', async () => {
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
    // 1买 背驰确立
    const b1 = wrapper.findAll('.b1-status-badge')
    expect(b1.length).toBe(2) // 1buy + 1sell
    const confirmed = b1.find((b) => b.classes().includes('b1-confirmed'))
    expect(confirmed?.text()).toBe('✓背驰确立')
    const suspect = b1.find((b) => b.classes().includes('b1-suspect'))
    expect(suspect?.text()).toBe('⚠疑似背驰')
    // 3买 不破ZG
    const b3 = wrapper.findAll('.b3-status-badge')
    expect(b3.length).toBe(1) // 仅 3buy
    expect(b3[0].classes()).toContain('b3-ok')
    expect(b3[0].text()).toContain('108')
    // 2buy 无 1买/3买 状态徽章（mmd1Status/mmd3Status 都 null）
    // 已由 b1.length===2 / b3.length===1 隐含验证（2buy 不计入）
    wrapper.unmount()
  }, 30_000)
})
