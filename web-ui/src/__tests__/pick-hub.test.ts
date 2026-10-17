// V853 选股 hub 行为测试（§1）：验证 PickHubView 真渲染 + 点 tab 切换内容。
// stub 掉 3 个重子 view（API 依赖），专注 hub 切换机制。
import { describe, expect, test } from 'vitest'
import { mount } from '@vue/test-utils'
import { router } from '../router'
import PickHubView from '../views/PickHubView.vue'

const stubs = {
  PickView: { name: 'PickStub', template: '<div data-stub="buy">缠论买点占位</div>' },
  StockPickView: { name: 'StockPickStub', template: '<div data-stub="twostep">长盈两步占位</div>' },
  ScreeningView: { name: 'ScreeningStub', template: '<div data-stub="dynback">动态回测占位</div>' },
}

describe('V853 选股 hub 行为', () => {
  test('默认渲染缠论买点 tab（保留原 /pick 行为）', async () => {
    await router.push('/pick')
    await router.isReady()
    const w = mount(PickHubView, { global: { plugins: [router], stubs } })
    expect(w.find('[data-stub="buy"]').exists()).toBe(true)
    expect(w.find('[data-stub="twostep"]').exists()).toBe(false)
  })

  test('点「长盈两步」tab 切换', async () => {
    await router.push('/pick')
    await router.isReady()
    const w = mount(PickHubView, { global: { plugins: [router], stubs } })
    const btn = w.findAll('.hub-tabs .tab').find((t) => t.text().includes('长盈基本面'))
    await btn!.trigger('click')
    expect(w.find('[data-stub="twostep"]').exists()).toBe(true)
    expect(w.find('[data-stub="buy"]').exists()).toBe(false)
  })

  test('点「动态选股」tab 切换', async () => {
    await router.push('/pick')
    await router.isReady()
    const w = mount(PickHubView, { global: { plugins: [router], stubs } })
    const btn = w.findAll('.hub-tabs .tab').find((t) => t.text().includes('动态选股'))
    await btn!.trigger('click')
    expect(w.find('[data-stub="dynback"]').exists()).toBe(true)
  })

  test('?tab=dynback 初值切到动态回测 tab', async () => {
    await router.push('/pick?tab=dynback')
    await router.isReady()
    const w = mount(PickHubView, { global: { plugins: [router], stubs } })
    expect(w.find('[data-stub="dynback"]').exists()).toBe(true)
  })
})
