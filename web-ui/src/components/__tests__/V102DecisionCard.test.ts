/**
 * V102DecisionCard 组件测试（V389）。
 *
 * 三类数据形态契约：
 * - 完整 V102 建议：决策支持 + 质量评分卡 + 模式匹配全部渲染
 * - 字段缺失：止损/止盈为 null/undefined 时渲染占位符，不抛异常
 * - 无建议：mmd=null 或不含任何 v102 字段时渲染空态（不渲染卡片）
 */

import { describe, expect, test } from 'vitest'
import { mount } from '@vue/test-utils'

import V102DecisionCard from '../V102DecisionCard.vue'
import type { DiagnosisChanlunMmd } from '../../types'

function fullMmd(): DiagnosisChanlunMmd {
  return {
    type: '3buy',
    confidence: 0.82,
    msg: '三买信号',
    quality: { grade: 'B', score: 78, reasons: ['量价配合', '趋势向上'] },
    v102_multi_signal_correlation: {
      nearby_signals: 2,
      signal_density: '密集',
      confidence_adjust: 0.03,
      msg: '附近 5 根 K 线有 2 个同向信号',
    },
    v102_signal_quality: {
      tech_score: 3.2,
      volume_score: 1.6,
      trend_score: 1.8,
      volatility_score: 0.8,
      overall_grade: 'B',
      overall_score: 76,
      strength: 'strong',
      confidence_adjust: 0.05,
      msg: '信号质量良好',
    },
    v102_decision_support: {
      entry_price: 12.5,
      stop_loss: 11.8,
      take_profit_1: 13.6,
      take_profit_2: 14.8,
      risk_reward_ratio: 2.5,
      position_size_pct: 30,
      action_recommendation: '建议买入',
      risk_notes: '注意控制仓位',
      confidence_adjust: 0.04,
    },
    v102_pattern_match: {
      similar_patterns_found: 3,
      win_rate: 66.7,
      avg_return: 8.5,
      max_drawdown: -4.2,
      confidence_adjust: 0.02,
      msg: '历史相似形态胜率较高',
    },
  }
}

describe('V102DecisionCard', () => {
  test('完整建议：渲染全部 V102 区块', () => {
    const wrapper = mount(V102DecisionCard, { props: { mmd: fullMmd() } })
    const text = wrapper.text()
    expect(wrapper.find('.v102-card').exists()).toBe(true)
    expect(text).toContain('V102 决策支持')
    expect(text).toContain('建议买入')
    expect(text).toContain('入场价')
    expect(text).toContain('12.50')
    expect(text).toContain('信号质量评分卡')
    expect(text).toContain('历史模式匹配')
    expect(text).toContain('66.7%')
  })

  test('字段缺失：止损/止盈为 null 渲染占位符不崩溃', () => {
    const mmd = fullMmd()
    // 用类型断言模拟后端遗漏可选数值字段（NaN/None 序列化后的边界）
    mmd.v102_decision_support = {
      ...mmd.v102_decision_support!,
      stop_loss: null as unknown as number,
      take_profit_1: null as unknown as number,
      take_profit_2: undefined as unknown as number,
    }
    const wrapper = mount(V102DecisionCard, { props: { mmd } })
    const text = wrapper.text()
    // fmt(null/undefined) → '—'
    expect(text).toContain('—')
    expect(wrapper.find('.v102-card').exists()).toBe(true)
  })

  test('无建议：mmd=null 渲染空态', () => {
    const wrapper = mount(V102DecisionCard, { props: { mmd: null } })
    expect(wrapper.find('.v102-card').exists()).toBe(false)
  })

  test('无建议：mmd 不含任何 v102 字段渲染空态', () => {
    const mmd: DiagnosisChanlunMmd = {
      type: '3buy',
      confidence: 0.6,
      msg: '普通三买',
      quality: null,
    }
    const wrapper = mount(V102DecisionCard, { props: { mmd } })
    expect(wrapper.find('.v102-card').exists()).toBe(false)
  })

  test('操作建议分类：买入/卖出/持有分别着色', () => {
    const buy = mount(V102DecisionCard, { props: { mmd: fullMmd() } })
    expect(buy.find('.action-buy').exists()).toBe(true)

    const sellMmd = fullMmd()
    sellMmd.v102_decision_support!.action_recommendation = '建议卖出'
    const sell = mount(V102DecisionCard, { props: { mmd: sellMmd } })
    expect(sell.find('.action-sell').exists()).toBe(true)

    const holdMmd = fullMmd()
    holdMmd.v102_decision_support!.action_recommendation = '观望'
    const hold = mount(V102DecisionCard, { props: { mmd: holdMmd } })
    expect(hold.find('.action-hold').exists()).toBe(true)
  })
})
