<script setup lang="ts">
// 分段稳健性 / 过拟合检查面板：把回测区间均分为 N 段逐段重跑同一策略，
// 对比各段的收益/胜率/命中率，帮助用户判断模型是「真稳健」还是「只在一段行情里被调准」。

import { computed } from 'vue'

import { fmtPct } from '../format'
import type { SegmentRobustnessReport } from '../types'

const props = defineProps<{
  report: SegmentRobustnessReport | null | undefined
}>()

const hasReport = computed(() => Boolean(props.report?.segments?.length))

const verdictClass = computed(() => {
  if (!props.report) return ''
  if (props.report.overfit_likely) return 'verdict-neg'
  if ((props.report.consistency?.positive_segment_ratio ?? 0) >= 0.6) return 'verdict-pos'
  return 'verdict-neutral'
})

const rows = computed(() => (props.report?.segments ?? []).filter((s) => !s.skipped))
</script>

<template>
  <div v-if="hasReport" class="robustness-panel">
    <!-- 结论行 -->
    <div class="verdict" :class="verdictClass">
      <span class="verdict-label">稳健性判定：</span>
      <span>{{ report?.verdict }}</span>
    </div>

    <!-- 一致性汇总 -->
    <div v-if="report?.consistency && report.consistency.segments_analyzed" class="summary-row">
      <div class="summary-item">
        <span class="s-label">有效分段</span>
        <span class="s-value">{{ report.consistency.segments_analyzed }}</span>
      </div>
      <div class="summary-item">
        <span class="s-label">正收益段占比</span>
        <span class="s-value" :class="(report.consistency.positive_segment_ratio ?? 0) >= 0.6 ? 'pos' : 'neg'">
          {{ fmtPct(report.consistency.positive_segment_ratio) }}
        </span>
      </div>
      <div class="summary-item">
        <span class="s-label">跑赢买入持有占比</span>
        <span class="s-value" :class="(report.consistency.beats_buy_hold_ratio ?? 0) >= 0.6 ? 'pos' : 'neg'">
          {{ fmtPct(report.consistency.beats_buy_hold_ratio) }}
        </span>
      </div>
      <div class="summary-item">
        <span class="s-label">平均胜率</span>
        <span class="s-value">{{ fmtPct(report.consistency.win_rate_mean) }}</span>
      </div>
      <div class="summary-item">
        <span class="s-label">胜率离散度(CV)</span>
        <span class="s-value">{{ (report.consistency.win_rate_cv ?? 0).toFixed(2) }}</span>
      </div>
    </div>

    <!-- 各段明细表 -->
    <table class="seg-table">
      <thead>
        <tr>
          <th>分段</th>
          <th>区间</th>
          <th>K线数</th>
          <th>收益率</th>
          <th>胜率</th>
          <th>5根命中率</th>
          <th>夏普</th>
          <th>买入持有</th>
          <th>超额</th>
          <th>交易数</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in rows" :key="s.label">
          <td class="dim">{{ s.label }}</td>
          <td class="dim">{{ s.start }} ~ {{ s.end }}</td>
          <td>{{ s.bars }}</td>
          <td :class="(s.total_return ?? 0) >= 0 ? 'pos' : 'neg'">{{ fmtPct(s.total_return) }}</td>
          <td>{{ fmtPct(s.win_rate) }}</td>
          <td>{{ fmtPct(s.hit_rate) }}</td>
          <td>{{ (s.sharpe ?? 0).toFixed(2) }}</td>
          <td class="dim">{{ fmtPct(s.buy_hold_return) }}</td>
          <td :class="(s.alpha ?? 0) >= 0 ? 'pos' : 'neg'">{{ fmtPct(s.alpha) }}</td>
          <td>{{ s.trades }}</td>
        </tr>
      </tbody>
    </table>

    <p class="legend">
      方法：把回测区间均分为 N 段，对每段用同一策略 + 同一参数独立重跑（每段全新实例，避免状态串扰）。
      若各段收益/胜率/命中率一致、多数分段正收益并跑赢买入持有，说明模型稳健；
      若某段一枝独秀而其余段亏损，或胜率/命中率离散度大，提示可能存在过拟合，全时段成绩需谨慎对待。
    </p>
  </div>
</template>

<style scoped>
.robustness-panel {
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
.seg-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.seg-table th {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 600;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  text-align: right;
}
.seg-table th:first-child {
  text-align: left;
}
.seg-table td {
  padding: 5px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  text-align: right;
  font-family: var(--font-mono);
}
.seg-table td.dim {
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
