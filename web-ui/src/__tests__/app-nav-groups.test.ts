// V853 分组导航渲染测试（§1 行为级）：确认 App.vue 的四个分组标签 + 关键链接真渲染。
import { describe, expect, test } from 'vitest'
import { mount } from '@vue/test-utils'
import { router } from '../router'
import App from '../App.vue'

describe('V853 分组导航', () => {
  test('四个分组标签按两模块愿景渲染', async () => {
    await router.push('/learn')
    await router.isReady()
    const w = mount(App, {
      global: {
        plugins: [router],
        stubs: { WatchlistPanel: true, RouterView: true },
      },
    })
    const labels = w.findAll('.nav-label').map((e) => e.text())
    expect(labels).toEqual(['缠论学习回测', '长赢选股', '选股', '工具'])
  })

  test('各分组关键链接存在（href）', async () => {
    await router.push('/learn')
    await router.isReady()
    const w = mount(App, {
      global: {
        plugins: [router],
        stubs: { WatchlistPanel: true, RouterView: true },
      },
    })
    const hrefs = w.findAll('.app-nav a').map((a) => a.attributes('href'))
    // 缠论学习回测
    expect(hrefs).toContain('/learn')
    expect(hrefs).toContain('/')
    expect(hrefs).toContain('/signal-check')
    // 长赢选股（V853：3 散路由收拢为 /changying hub，/fundamental+/hybrid 已并入 tab）
    expect(hrefs).toContain('/changying')
    expect(hrefs).toContain('/today')
    expect(hrefs).not.toContain('/fundamental') // 已重定向，不在导航
    expect(hrefs).not.toContain('/hybrid') // 已重定向，不在导航
    // 选股
    expect(hrefs).toContain('/pick')
    // 工具
    expect(hrefs).toContain('/portfolio')
    expect(hrefs).toContain('/strategies')
  })

  test('软隐藏：/changying hub 在核心路径不显示 banner，/audit 仍软隐藏', async () => {
    await router.push('/changying')
    await router.isReady()
    const w = mount(App, {
      global: { plugins: [router], stubs: { WatchlistPanel: true, RouterView: true } },
    })
    expect(w.find('.soft-hidden-banner').exists()).toBe(false) // /changying 在 CORE_PATHS

    await router.push('/audit')
    await router.isReady()
    await w.vm.$nextTick()
    expect(w.find('.soft-hidden-banner').exists()).toBe(true) // /audit 软隐藏
  })

  test('长赢 hub 重定向：/fundamental→select tab，/hybrid→fusion tab（转发 query）', () => {
    const byPath = (path: string) => router.getRoutes().find((r) => r.path === path)
    expect(byPath('/fundamental')?.redirect).toEqual({ path: '/changying', query: { tab: 'select' } })
    // /hybrid 用函数转发 query，断言 tab + code 透传
    const hybridRedirect = byPath('/hybrid')?.redirect as (to: { query: Record<string, string> }) => unknown
    const out = hybridRedirect({ query: { code: '600519', market: 'SH' } }) as { path: string; query: Record<string, string> }
    expect(out.path).toBe('/changying')
    expect(out.query.tab).toBe('fusion')
    expect(out.query.code).toBe('600519') // query 透传，不丢预填
  })

  test('选股 hub 重定向：/screening→dynback tab，/stock-pick→twostep tab', () => {
    const byPath = (path: string) => router.getRoutes().find((r) => r.path === path)
    expect(byPath('/screening')?.redirect).toEqual({ path: '/pick', query: { tab: 'dynback' } })
    expect(byPath('/stock-pick')?.redirect).toEqual({ path: '/pick', query: { tab: 'twostep' } })
  })
})
