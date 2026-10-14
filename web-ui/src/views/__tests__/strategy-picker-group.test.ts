// 策略下拉「缠论类 / 技术指标类」分组的牙齿测试。
//
// 背景：回测页策略下拉里有 **3 个** 缠论策略（chanlun / chanlun_pair /
// changying_chanlun），混在 28 条普通策略里难找，且名字相近容易选错 ——
// 而它们行为差异很大（chanlun 默认带 8%/25% 百分比止损止盈，
// chanlun_pair 只认同级别卖点出场）。
//
// 本文件锁两件事：① 渲染成 optgroup 分组；② 缠论三个都归到「缠论类」。
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import StrategyPicker from '../../components/StrategyPicker.vue'
import type { StrategySchema } from '../../types'

function strat(name: string, label: string): StrategySchema {
  return { name, label, description: '', params: [] } as StrategySchema
}

// 真实后端返回的 28 条里挑有代表性的：3 个缠论 + 若干普通
const STRATEGIES: StrategySchema[] = [
  strat('ma_cross', '双均线交叉'),
  strat('macd', 'MACD 金叉'),
  strat('changying_chanlun', '长赢缠论综合'),
  strat('chanlun', '缠论买卖点'),
  strat('chanlun_pair', '缠论买卖点配对'),
  strat('boll_breakout', '布林带突破'),
]

function render() {
  return mount(StrategyPicker, {
    props: { strategies: STRATEGIES, strategy: 'chanlun', params: {} },
  })
}

describe('StrategyPicker 策略分组', () => {
  it('渲染成 optgroup，不是平铺的 option', () => {
    const w = render()
    const groups = w.findAll('optgroup')
    expect(groups.length).toBeGreaterThanOrEqual(2)
  })

  it('三个缠论策略全部归入「缠论类」，普通策略不在该组', () => {
    const w = render()
    const groups = w.findAll('optgroup')
    const byLabel = new Map<string, string[]>()
    for (const g of groups) {
      const label = g.attributes('label') ?? ''
      byLabel.set(
        label,
        g.findAll('option').map((o) => o.attributes('value') ?? ''),
      )
    }
    expect(byLabel.has('缠论类')).toBe(true)
    const chan = byLabel.get('缠论类') ?? []
    expect(chan).toContain('chanlun')
    expect(chan).toContain('chanlun_pair')
    expect(chan).toContain('changying_chanlun')
    // 普通策略不能被误分进缠论类
    expect(chan).not.toContain('ma_cross')
    expect(chan).not.toContain('macd')
  })

  it('每条策略都还在（分组不能弄丢选项）', () => {
    const w = render()
    const all = w.findAll('option').map((o) => o.attributes('value'))
    expect(all.sort()).toEqual(STRATEGIES.map((s) => s.name).sort())
  })

  it('选中缠论策略时显示三个策略的差异说明（不再只对 chanlun 生效）', () => {
    const w = mount(StrategyPicker, {
      props: { strategies: STRATEGIES, strategy: 'chanlun_pair', params: {} },
    })
    // 原来写死 === 'chanlun' 时，选 chanlun_pair 这块不显示
    expect(w.find('.chanlun-diff').exists()).toBe(true)
  })
})
