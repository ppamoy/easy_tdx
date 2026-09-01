<script setup lang="ts">
// 多 task 指标横向对比表（每个 task 一列或一行）。

import type { BacktestResult } from '../types'

const props = defineProps<{
  items: Array<{ label: string; result: BacktestResult }>
}>()

interface Row {
  label: string
  key: keyof BacktestResult['performance']
  format: 'percent' | 'ratio' | 'int'
}

const ROWS: Row[] = [
  { label: '总收益', key: 'total_return', format: 'percent' },
  { label: '年化收益', key: 'annual_return', format: 'percent' },
  { label: '夏普', key: 'sharpe', format: 'ratio' },
  { label: '最大回撤', key: 'max_drawdown', format: 'percent' },
  { label: '胜率', key: 'win_rate', format: 'percent' },
  { label: '盈亏比', key: 'profit_factor', format: 'ratio' },
  { label: '交易数', key: 'total_trades', format: 'int' },
  { label: '波动率', key: 'volatility', format: 'percent' },
]

function fmt(row: Row, v: number | undefined): string {
  if (v === undefined || !Number.isFinite(v)) return '-'
  if (row.format === 'percent') return '' + (v * 100).toFixed(2) + '%'
  if (row.format === 'int') return String(Math.round(v))
  return v.toFixed(3)
}

// ── 准确度/可信度横向对比行（V102：按历史回测验证的准确度比较策略） ────────────

function trustScore(item: { result: BacktestResult }): string {
  const t = item.result.model_trust
  if (!t || t.score === undefined) return '-'
  return Math.round(t.score) + '/100 ' + t.grade
}

function trustClass(item: { result: BacktestResult }): string {
  const t = item.result.model_trust
  if (!t) return ''
  if (t.grade === '高') return 'pos'
  if (t.grade === '低') return 'neg'
  return ''
}

function hitRate(item: { result: BacktestResult }): string {
  const h = item.result.signal_accuracy?.buy?.horizons?.['5']
  if (!h || h.count === 0) return '-'
  return (h.hit_rate * 100).toFixed(0) + '%'
}

function excessHit(item: { result: BacktestResult }): string {
  const h = item.result.signal_accuracy?.buy?.horizons?.['5']
  if (!h || h.count === 0) return '-'
  const sign = h.excess_hit_rate >= 0 ? '+' : ''
  return sign + (h.excess_hit_rate * 100).toFixed(1) + '%'
}

// V125: 样本外 / 稳健性 横向对比
function oosText(item: { result: BacktestResult }): string {
  const o = item.result.out_of_sample
  if (!o || !o.verdict) return '-'
  return o.degraded ? '⚠ 样本外衰减' : '✅ 样本外稳健'
}
function oosClass(item: { result: BacktestResult }): string {
  const o = item.result.out_of_sample
  if (!o || !o.verdict) return ''
  return o.degraded ? 'neg' : 'pos'
}
function robustText(item: { result: BacktestResult }): string {
  const r = item.result.segment_robustness
  if (!r || !r.verdict) return '-'
  return r.overfit_likely ? '⚠ 疑似过拟合' : '✅ 分段稳健'
}
function robustClass(item: { result: BacktestResult }): string {
  const r = item.result.segment_robustness
  if (!r || !r.verdict) return ''
  return r.overfit_likely ? 'neg' : 'pos'
}
</script>

<template>
  <table class="compare-table">
    <thead>
      <tr>
        <th>指标</th>
        <th v-for="item in props.items" :key="item.label" class="col">{{ item.label }}</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="row in ROWS" :key="row.key">
        <td class="metric-label">{{ row.label }}</td>
        <td v-for="item in props.items" :key="item.label" class="num">
          {{ fmt(row, item.result.performance[row.key] as number) }}
        </td>
      </tr>
      <!-- 准确度/可信度行 -->
      <tr>
        <td class="metric-label">📊 可信度</td>
        <td v-for="item in props.items" :key="item.label" class="num" :class="trustClass(item)">
          {{ trustScore(item) }}
        </td>
      </tr>
      <tr>
        <td class="metric-label">🎯 5根命中率</td>
        <td v-for="item in props.items" :key="item.label" class="num">
          {{ hitRate(item) }}
        </td>
      </tr>
      <tr>
        <td class="metric-label">🎯 超额命中率</td>
        <td v-for="item in props.items" :key="item.label" class="num">
          {{ excessHit(item) }}
        </td>
      </tr>
      <!-- V125: 过拟合风险行 -->
      <tr>
        <td class="metric-label">🔬 样本外验证</td>
        <td v-for="item in props.items" :key="item.label" class="num" :class="oosClass(item)">
          {{ oosText(item) }}
        </td>
      </tr>
      <tr>
        <td class="metric-label">🧱 稳健性</td>
        <td v-for="item in props.items" :key="item.label" class="num" :class="robustClass(item)">
          {{ robustText(item) }}
        </td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
.compare-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.compare-table th,
.compare-table td {
  padding: 7px 12px;
  border-bottom: 1px solid var(--border);
  text-align: left;
}
.compare-table th {
  color: var(--text-dim);
  font-size: 12px;
  font-weight: 600;
}
.compare-table th.col {
  color: var(--accent);
  font-family: var(--font-mono);
}
.metric-label {
  color: var(--text-muted);
  white-space: nowrap;
}
.num {
  font-family: var(--font-mono);
  text-align: right;
}
</style>
