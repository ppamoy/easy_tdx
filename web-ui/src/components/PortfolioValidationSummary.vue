<script setup lang="ts">
// 组合「验证总结」卡片（V112）：把组合可信度（V103）+ 组合准确度聚合（V99）
// + 逐标可信度 Top/Bottom（V110）浓缩成一张可一览的卡片，与单标的 V106 对齐。

import { computed } from 'vue'

import type { PortfolioResult } from '../types'

const props = defineProps<{
  result: PortfolioResult | null | undefined
}>()

const hasData = computed(() => Boolean(props.result?.portfolio_trust || props.result?.accuracy_summary))

const trust = computed(() => props.result?.portfolio_trust ?? null)

const accuracy = computed(() => props.result?.accuracy_summary ?? null)

const symbolRows = computed(() => {
  const rows = props.result?.accuracy_summary?.symbols ?? []
  // 只看有可信度的标的
  return rows.filter((r) => r.trust_score !== null && r.trust_score !== undefined)
})

const topBottom = computed(() => {
  const rows = symbolRows.value
  if (rows.length < 2) return { top: rows[0] ?? null, bottom: rows[rows.length - 1] ?? null }
  const sorted = [...rows].sort((a, b) => (b.trust_score ?? 0) - (a.trust_score ?? 0))
  return { top: sorted[0], bottom: sorted[sorted.length - 1] }
})

const overallClass = computed(() => {
  const t = trust.value
  if (!t) return ''
  if (t.grade === '高') return 'pos'
  if (t.grade === '低') return 'neg'
  return 'warn'
})

function trustText(r: { trust_score?: number | null; trust_grade?: string | null } | null | undefined): string {
  if (!r || r.trust_score === null || r.trust_score === undefined) return '-'
  return Math.round(r.trust_score) + ' ' + (r.trust_grade ?? '')
}
</script>

<template>
  <div v-if="hasData" class="pv-summary">
    <div class="pv-head">
      <span class="pv-title">✅ 组合验证总结</span>
      <span v-if="trust" class="pv-overall" :class="overallClass">
        组合可信度 {{ Math.round(trust.score) }}/100 · {{ trust.grade }}可信
      </span>
    </div>

    <div class="pv-rows">
      <div v-if="trust?.verdict" class="pv-row" :class="overallClass">
        <span class="pv-label">组合可信度</span>
        <span class="pv-text">{{ trust.verdict }}</span>
      </div>
      <div v-if="accuracy?.verdict" class="pv-row neutral">
        <span class="pv-label">组合准确度</span>
        <span class="pv-text">{{ accuracy.verdict }}</span>
      </div>
      <div v-if="accuracy?.portfolio" class="pv-row neutral">
        <span class="pv-label">聚合统计</span>
        <span class="pv-text">
          {{ accuracy.portfolio.symbols }} 只标的 · 加权5根命中率
          {{ ((accuracy.portfolio.avg_hit_rate ?? 0) * 100).toFixed(1) }}% ·
          {{ accuracy.portfolio.positive_symbols }}/{{ accuracy.portfolio.symbols }} 正收益 ·
          {{ accuracy.portfolio.hit_above_baseline }}/{{ accuracy.portfolio.symbols_with_accuracy }} 命中率高于基准
        </span>
      </div>
      <div v-if="topBottom.top || topBottom.bottom" class="pv-row neutral">
        <span class="pv-label">逐标可信度</span>
        <span class="pv-text">
          最强 <b>{{ topBottom.top?.symbol ?? '-' }}</b>（{{ trustText(topBottom.top) }}）
          <template v-if="topBottom.bottom && topBottom.bottom.symbol !== topBottom.top?.symbol">
            · 最弱 <b>{{ topBottom.bottom.symbol }}</b>（{{ trustText(topBottom.bottom) }}）
          </template>
        </span>
      </div>
    </div>

    <p class="pv-legend">组合可信度＝组合加权超额命中率（40%）＋跨标一致性（35%）＋组合加权绩效（25%）；配合组合准确度聚合与逐标可信度，回答「同一策略放在这批标的上，整体验证是否可信、哪些标的最可信」。</p>
  </div>
</template>

<style scoped>
.pv-summary {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
}
.pv-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.pv-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
}
.pv-overall {
  font-size: 12px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}
.pv-overall.pos {
  color: var(--up);
  background: rgba(34, 197, 94, 0.12);
}
.pv-overall.warn {
  color: var(--warn, #f59e0b);
  background: rgba(245, 158, 11, 0.12);
}
.pv-overall.neg {
  color: var(--down);
  background: rgba(239, 68, 68, 0.12);
}
.pv-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pv-row {
  display: flex;
  gap: 10px;
  align-items: baseline;
  font-size: 12px;
  padding-left: 8px;
  border-left: 3px solid var(--border);
}
.pv-row.pos {
  border-left-color: var(--up);
}
.pv-row.warn {
  border-left-color: var(--warn, #f59e0b);
}
.pv-row.neg {
  border-left-color: var(--down);
}
.pv-row.neutral {
  border-left-color: var(--border);
}
.pv-label {
  color: var(--text-muted);
  font-weight: 600;
  white-space: nowrap;
  min-width: 96px;
}
.pv-text {
  color: var(--text);
  line-height: 1.5;
}
.pv-legend {
  font-size: 11px;
  color: var(--text-dim);
  line-height: 1.6;
  margin: 0;
}
</style>
