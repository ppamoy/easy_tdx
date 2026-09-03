<script setup lang="ts">
// 组合级样本外验证面板（V126）：逐标训练/持有切分后聚合，
// 回答「这套策略组合在没见过的数据上是否仍准确」。

import { computed } from 'vue'

import { fmtPct } from '../format'
import type { PortfolioOutOfSampleReport } from '../types'

const props = defineProps<{
  report: PortfolioOutOfSampleReport | null | undefined
}>()

const hasReport = computed(() => Boolean(props.report?.per_symbol))

const verdictClass = computed(() => {
  if (!props.report) return ''
  return props.report.degraded ? 'verdict-neg' : 'verdict-pos'
})

const symbolRows = computed(() => {
  const per = props.report?.per_symbol ?? {}
  return Object.entries(per).map(([sym, v]) => ({ symbol: sym, ...v }))
})
</script>

<template>
  <div v-if="hasReport" class="poos-panel">
    <div class="verdict" :class="verdictClass">
      <span class="verdict-label">组合样本外判定：</span>
      <span>{{ report?.verdict }}</span>
    </div>

    <div class="summary-row">
      <div class="summary-item">
        <span class="s-label">标的数</span>
        <span class="s-value">{{ report?.symbols }}</span>
      </div>
      <div class="summary-item">
        <span class="s-label">样本外稳健标的</span>
        <span
          class="s-value"
          :class="
            (report?.symbols ?? 0) - (report?.degraded_symbols ?? 0) >= (report?.symbols ?? 0) * 0.5
              ? 'pos'
              : 'neg'
          "
        >
          {{ (report?.symbols ?? 0) - (report?.degraded_symbols ?? 0) }}/{{ report?.symbols }}
        </span>
      </div>
      <div class="summary-item">
        <span class="s-label">平均训练段收益</span>
        <span class="s-value">{{ fmtPct(report?.avg_train_return) }}</span>
      </div>
      <div class="summary-item">
        <span class="s-label">平均样本外收益</span>
        <span class="s-value" :class="(report?.avg_test_return ?? 0) >= 0 ? 'pos' : 'neg'">{{
          fmtPct(report?.avg_test_return)
        }}</span>
      </div>
    </div>

    <table class="poos-table">
      <thead>
        <tr>
          <th>标的</th>
          <th>训练段收益</th>
          <th>样本外收益</th>
          <th>判定</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in symbolRows" :key="r.symbol">
          <td class="dim">{{ r.symbol }}</td>
          <td class="num">{{ fmtPct(r.train_return) }}</td>
          <td class="num" :class="(r.test_return ?? 0) >= 0 ? 'pos' : 'neg'">
            {{ fmtPct(r.test_return) }}
          </td>
          <td class="dim" :class="r.degraded ? 'neg' : 'pos'">
            {{ r.degraded ? '⚠ 衰减' : '✅ 稳健' }}
          </td>
        </tr>
      </tbody>
    </table>

    <p class="legend">
      方法：对组合内每只标的按时间切训练段（默认前 70%）+ 样本外持有段（后 30%），
      策略参数固定，在没见过的数据上重跑——多数标的样本外仍正收益且不过度衰减，说明组合策略具备泛化能力。
    </p>
  </div>
</template>

<style scoped>
.poos-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.verdict {
  font-size: 14px;
  line-height: 1.5;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
}
.verdict-label {
  font-weight: 600;
  margin-right: 4px;
}
.verdict-pos {
  color: var(--up);
}
.verdict-neg {
  color: var(--down);
}
.summary-row {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  font-size: 12px;
}
.summary-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.s-label {
  color: var(--text-dim);
  font-size: 11px;
}
.s-value {
  font-family: var(--font-mono);
  font-weight: 600;
}
.poos-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.poos-table th {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 600;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  text-align: right;
}
.poos-table th:first-child,
.poos-table td:first-child {
  text-align: left;
}
.poos-table td {
  padding: 5px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  text-align: right;
  font-family: var(--font-mono);
}
.legend {
  font-size: 11px;
  color: var(--text-dim);
  line-height: 1.6;
  margin: 0;
}
.pos {
  color: var(--up);
}
.neg {
  color: var(--down);
}
.dim {
  color: var(--text-dim);
}
</style>
