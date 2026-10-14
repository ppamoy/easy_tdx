/**
 * 前端买卖点方向判定的牙齿测试。
 *
 * 背景：后端曾因 `t.endswith("buy")` 把 `2buy_s`（类二买）判成卖点、
 * 收益取反，产出稳定的假反向信号（本项目**踩过两次**，见
 * docs/CHANLUN_CORRECTNESS_50STOCKS.md「已证伪」）。
 *
 * 前端 `SignalCheckView.vue` 里有一份同名的 `isBuyType`，用于决定
 * 「最新买卖点」卡片显示**买入**还是**卖出**。如果它退回
 * `endsWith('buy')`，类二买会被显示成"卖出" —— 用户照着做就反了。
 *
 * 这里把判定逻辑复制一份并锁定：必须与后端 `signal_stats.is_buy_type`
 * （权威口径 `'buy' in t`）行为一致。
 */

import { describe, expect, it } from 'vitest'

/** 与 SignalCheckView.vue 中的实现保持一致 */
const isBuyType = (t: string) => t.includes('buy')

describe('买卖点类型判定（前端口径，必须与后端一致）', () => {
  const buys = ['1buy', '2buy', '2buy_s', '3buy']
  const sells = ['1sell', '2sell', '2sell_s', '3sell']

  it.each(buys)('%s 必须是买点', (t) => {
    expect(isBuyType(t)).toBe(true)
  })

  it.each(sells)('%s 必须是卖点', (t) => {
    expect(isBuyType(t)).toBe(false)
  })

  it('牙齿：endsWith(\'buy\') 版本必须漏判 _s 后缀类型', () => {
    // 前提：坏版本确实会把 2buy_s 判成非买点
    expect('2buy_s'.endsWith('buy')).toBe(false)
    // 而正确口径能识别
    expect(isBuyType('2buy_s')).toBe(true)
  })

  it('2sell_s 不能被误判为买点', () => {
    // 反向对照：'2sell_s' 里没有 'buy' 子串
    expect('2sell_s'.includes('buy')).toBe(false)
    expect(isBuyType('2sell_s')).toBe(false)
  })
})
