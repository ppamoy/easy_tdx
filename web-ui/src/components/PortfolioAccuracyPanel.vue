<script setup lang="ts">
// 组合级准确度验证面板：把组合内每只标的的 signal_accuracy 聚合展示，
// 回答「这个策略放在多只股票上，整体择时/选股是否仍然靠谱」。

import { computed } from 'vue'

import { fmtPct } from '../format'
import type { ModelTrustReport, PortfolioAccuracyReport } from '../types'

const props = defineProps<{
  report: PortfolioAccuracyReport | null | undefined
  trust?: ModelTrustReport | null | undefined
}>()

const hasReport = computed(() => Boolean(props.report?.portfolio?.symbols))

const verdictClass = computed(() => {
  const p = props.report?.portfolio
  if (!p) return ''
  if ((p.avg_excess_hit_rate ?? 0) > 0.03) return 'verdict-pos'
  if ((p.avg_excess_hit_rate ?? 0) > 0) return 'verdict-neutral'
  return 'verdict-neg'
})

const rows = computed(() => props.report?.symbols ?? [])

const trustGradeClass = computed(() => {
  if (!props.trust) return ''
  if (props.trust.grade === '高') return 'grade-high'
  if (props.trust.grade === '中') return 'grade-mid'
  return 'grade-low'
})
const trustBarColor = computed(() => {
  if (!props.trust) return ''
  if (props.trust.score >= 70) return 'var(--up)'
  if (props.trust.score >= 50) return 'var(--warn, #f59e0b)'
  return 'var(--down)'
})

// V110: 单标的可信度展示辅助
function trustText(r: { trust_score?: number | null; trust_grade?: string | null }): string {
  if (r.trust_score === null || r.trust_score === undefined) return '-'
  return Math.round(r.trust_score) + ' ' + (r.trust_grade ?? '')
}
function trustClass(r: { trust_grade?: string | null }): string {
  if (r.trust_grade === '高') return 'pos'
  if (r.trust_grade === '低') return 'neg'
  return ''
}
</script>

<template>
  <div v-if="hasReport" class="portfolio-accuracy-panel">
    <!-- 组合可信度（V103） -->
    <div v-if="trust" class="trust-banner">
      <div class="trust-score">
        <span class="score-num" :style="{ color: trustBarColor }">{{
          Math.round(trust.score)
        }}</span>
        <span class="score-max">/100</span>
        <span class="grade-badge" :class="trustGradeClass">{{ trust.grade }}可信</span>
      </div>
      <div class="trust-verdict">{{ trust.verdict }}</div>
      <div class="bar-track">
        <div
          class="bar-fill"
          :style="{ width: trust.score + '%', background: trustBarColor }"
        ></div>
      </div>
    </div>

    <!-- 结论行 -->
    <div class="verdict" :class="verdictClass">
      <span class="verdict-label">组合准确度判定：</span>
      <span>{{ report?.verdict }}</span>
    </div>

    <!-- 组合级汇总 -->
    <div v-if="report?.portfolio" class="summary-row">
      <div class="summary-item">
        <span class="s-label">标的数</span>
        <span class="s-value">{{ report.portfolio.symbols }}</span>
      </div>
      <div class="summary-item">
        <span class="s-label">加权5根命中率</span>
        <span class="s-value" :class="report.portfolio.avg_excess_hit_rate > 0 ? 'pos' : 'neg'">
          {{ fmtPct(report.portfolio.avg_hit_rate) }}
        </span>
      </div>
      <div class="summary-item">
        <span class="s-label">加权超额命中率</span>
        <span class="s-value" :class="report.portfolio.avg_excess_hit_rate >= 0 ? 'pos' : 'neg'">
          {{ fmtPct(report.portfolio.avg_excess_hit_rate) }}
        </span>
      </div>
      <div class="summary-item">
        <span class="s-label">正收益标的</span>
        <span class="s-value"
          >{{ report.portfolio.positive_symbols }}/{{ report.portfolio.symbols }}</span
        >
      </div>
      <div class="summary-item">
        <span class="s-label">命中率高于基准标的</span>
        <span class="s-value"
          >{{ report.portfolio.hit_above_baseline }}/{{
            report.portfolio.symbols_with_accuracy
          }}</span
        >
      </div>
      <div class="summary-item">
        <span class="s-label">加权平均收益</span>
        <span class="s-value" :class="report.portfolio.avg_total_return >= 0 ? 'pos' : 'neg'">
          {{ fmtPct(report.portfolio.avg_total_return) }}
        </span>
      </div>
    </div>

    <!-- 逐标的明细表 -->
    <table class="sym-table">
      <thead>
        <tr>
          <th>标的</th>
          <th>资金占比</th>
          <th>总收益</th>
          <th>胜率</th>
          <th>5根命中率</th>
          <th>随机基准</th>
          <th>超额命中率</th>
          <th>可信度</th>
          <th>夏普</th>
          <th>交易数</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.symbol">
          <td class="dim">{{ r.symbol }}</td>
          <td>{{ fmtPct(r.allocation) }}</td>
          <td :class="r.total_return >= 0 ? 'pos' : 'neg'">{{ fmtPct(r.total_return) }}</td>
          <td>{{ fmtPct(r.win_rate) }}</td>
          <td
            :class="
              r.excess_hit_rate !== null && r.excess_hit_rate > 0
                ? 'pos'
                : r.excess_hit_rate !== null && r.excess_hit_rate < 0
                  ? 'neg'
                  : ''
            "
          >
            {{ fmtPct(r.hit_rate) }}
          </td>
          <td class="dim">{{ fmtPct(r.baseline_hit_rate) }}</td>
          <td :class="(r.excess_hit_rate ?? 0) >= 0 ? 'pos' : 'neg'">
            {{ fmtPct(r.excess_hit_rate) }}
          </td>
          <td :class="trustClass(r)">{{ trustText(r) }}</td>
          <td>{{ (r.sharpe ?? 0).toFixed(2) }}</td>
          <td>{{ r.trades }}</td>
        </tr>
      </tbody>
    </table>

    <p class="legend">
      命中 = 买入后 5 根收益 &gt; 0。随机基准 = 同期任意一天进场的平均命中率；加权超额命中率 &gt; 0
      说明该策略在组合层面具备择时/选股能力，而非只在单只标的上成立。多策略组合场景按槽位聚合。
    </p>
  </div>
</template>

<style scoped>
.portfolio-accuracy-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.trust-banner {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
}
.trust-score {
  display: flex;
  align-items: baseline;
  gap: 2px;
}
.score-num {
  font-family: var(--font-mono);
  font-size: 36px;
  font-weight: 700;
  line-height: 1;
}
.score-max {
  color: var(--text-dim);
  font-size: 13px;
}
.grade-badge {
  margin-left: 10px;
  font-size: 12px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}
.grade-high {
  color: var(--up);
  background: rgba(34, 197, 94, 0.12);
}
.grade-mid {
  color: var(--warn, #f59e0b);
  background: rgba(245, 158, 11, 0.12);
}
.grade-low {
  color: var(--down);
  background: rgba(239, 68, 68, 0.12);
}
.trust-verdict {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text);
}
.bar-track {
  height: 8px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  border-radius: 4px;
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
.verdict-neutral {
  color: var(--text-muted);
}
.summary-row {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}
.summary-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.s-label {
  font-size: 12px;
  color: var(--text-dim);
}
.s-value {
  font-family: var(--font-mono);
  font-weight: 600;
  font-size: 14px;
}
.sym-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.sym-table th {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 600;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  text-align: right;
}
.sym-table th:first-child {
  text-align: left;
}
.sym-table td {
  padding: 5px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  text-align: right;
  font-family: var(--font-mono);
}
.sym-table td.dim {
  font-family: inherit;
  color: var(--text-muted);
}
.pos {
  color: var(--up);
}
.neg {
  color: var(--down);
}
.legend {
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.6;
  margin: 0;
}
</style>
