// v590 导航收敛测试：三大主导航路由存在，旧路由软重定向到 /learn Tab。
import { describe, expect, test } from 'vitest'
import { router } from '../router'

describe('v590 导航收敛', () => {
  test('三大模块路由存在', () => {
    const names = router.getRoutes().map((r) => r.name)
    expect(router.hasRoute('backtest')).toBe(true) // 回测 /
    expect(router.hasRoute('stock-pick')).toBe(true) // 选股
    expect(router.hasRoute('learn')).toBe(true) // 缠论测试学习
  })

  test('旧路由软隐藏但可解析（不抛错）', () => {
    const cands = ['/portfolio', '/optimize', '/diagnosis', '/monitor', '/settings', '/changying']
    for (const path of cands) {
      const resolved = router.resolve(path)
      expect(resolved.matched.length).toBeGreaterThanOrEqual(1)
    }
  })

  test('/chanlun /train /verify 重定向到 /learn 对应 Tab', () => {
    const byPath = (path: string) => router.getRoutes().find((r) => r.path === path)
    expect(byPath('/chanlun')?.redirect).toEqual({ path: '/learn', query: { tab: 'analysis' } })
    expect(byPath('/train')?.redirect).toEqual({ path: '/learn', query: { tab: 'train' } })
    expect(byPath('/verify')?.redirect).toEqual({ path: '/learn', query: { tab: 'verify' } })
  })
})
