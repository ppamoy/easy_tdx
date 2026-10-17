// V853 长赢 hub 行为测试（§1）：验证 ChangyingHubView 真渲染 + 点 tab 切换内容，
// 不只重定向配置。stub 掉 3 个重子 view（它们有 API 依赖，单测里另测），专注 hub 切换机制。
import { describe, expect, test } from 'vitest'
import { mount } from '@vue/test-utils'
import { router } from '../router'
import ChangyingHubView from '../views/ChangyingHubView.vue'

// 用真 router（hub 读 route.query.tab 定初值），stub 3 个重 view 为带标识的占位
const stubs = {
  FundamentalView: { name: 'FundamentalStub', template: '<div data-stub="select">历史时点选股占位</div>' },
  ChangyingView: { name: 'ChangyingStub', template: '<div data-stub="overview">投资概览占位</div>' },
  HybridView: { name: 'HybridStub', template: '<div data-stub="fusion">融合信号占位</div>' },
}

describe('V853 长赢 hub 行为', () => {
  test('默认渲染历史时点选股 tab（P1 核心）', async () => {
    await router.push('/changying')
    await router.isReady()
    const w = mount(ChangyingHubView, { global: { plugins: [router], stubs } })
    expect(w.find('[data-stub="select"]').exists()).toBe(true)
    expect(w.find('[data-stub="overview"]').exists()).toBe(false)
  })

  test('点「投资概览」tab 切换到概览内容', async () => {
    await router.push('/changying')
    await router.isReady()
    const w = mount(ChangyingHubView, { global: { plugins: [router], stubs } })
    // 初始是 select
    expect(w.find('[data-stub="select"]').exists()).toBe(true)
    // 点概览 tab
    const tabs = w.findAll('.hub-tabs .tab')
    const overviewBtn = tabs.find((t) => t.text().includes('投资概览'))
    await overviewBtn!.trigger('click')
    expect(w.find('[data-stub="overview"]').exists()).toBe(true)
    expect(w.find('[data-stub="select"]').exists()).toBe(false)
  })

  test('点「融合信号」tab 切换到融合内容', async () => {
    await router.push('/changying')
    await router.isReady()
    const w = mount(ChangyingHubView, { global: { plugins: [router], stubs } })
    const tabs = w.findAll('.hub-tabs .tab')
    const fusionBtn = tabs.find((t) => t.text().includes('融合信号'))
    await fusionBtn!.trigger('click')
    expect(w.find('[data-stub="fusion"]').exists()).toBe(true)
  })

  test('?tab=overview 初值切到概览 tab', async () => {
    await router.push('/changying?tab=overview')
    await router.isReady()
    const w = mount(ChangyingHubView, { global: { plugins: [router], stubs } })
    expect(w.find('[data-stub="overview"]').exists()).toBe(true)
  })
})
