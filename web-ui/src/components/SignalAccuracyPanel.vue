<script setup lang="ts">
// 模型准确度验证面板：信号前瞻命中率 + 随机入场基准 + 买入持有基准。
// 让用户通过历史回测核对「模型的买卖点是否真的择时准确」，而不只是看账户盈亏。

import { computed, ref } from 'vue'

import { fmtPct, fmtPf } from '../format'
import type { SignalAccuracyReport, SignalHorizonStat } from '../types'

const props = defineProps<{
  report: SignalAccuracyReport | null | undefined
}>()

// 是否值得展示（有 buy 或 sell 报告）
const hasReport = computed(() => {
  if (!props.report) return false
  return Boolean(props.report.buy || props.report.sell)
})

const HORIZON_ORDER = ['1', '3', '5', '10', '20']

interface HorizonRow {
  horizon: string
  buy: SignalHorizonStat | undefined
  sell: SignalHorizonStat | undefined
}

const rows = computed<HorizonRow[]>(() => {
  const buy = props.report?.buy
  const sell = props.report?.sell
  return HORIZON_ORDER.map((h) => ({
    horizon: h,
    buy: buy?.horizons?.[h],
    sell: sell?.horizons?.[h],
  })).filter((r) => r.buy || r.sell)
})

// verdict 着色：正/负
const verdictClass = computed(() => {
  const v = props.report?.verdict ?? ''
  if (v.includes('显著高于') || v.includes('略高于')) return 'verdict-pos'
  if (v.includes('低于')) return 'verdict-neg'
  return 'verdict-neutral'
})

function hitClass(rate: number | undefined, baseline: number | undefined): string {
  if (rate === undefined || baseline === undefined) return ''
  if (rate - baseline > 0.02) return 'pos'
  if (rate - baseline < -0.02) return 'neg'
  return ''
}

function cell(n: number | undefined): string {
  return n === undefined ? '-' : String(n)
}
// V273: 信号准确度明细导出 CSV（按持有根数分类的买卖信号命中率明细）
const accCsvMsg = ref('')
function exportAccCsv() {
  const r = props.report
  if (!r || !rows.value.length) return
  const header = ['持有根数', '方向', '信号数', '命中率', '随机基准', '平均前瞻收益', '基准收益']
  const data: string[] = []
  rows.value.forEach((row) => {
    if (r.buy && row.buy) {
      data.push(
        [
          row.horizon + ' 根',
          '买入',
          cell(row.buy.count),
          fmtPct(row.buy.hit_rate),
          fmtPct(row.buy.baseline_hit_rate),
          fmtPct(row.buy.avg_return),
          fmtPct(row.buy.baseline_avg_return),
        ].join(','),
      )
    }
    if (r.sell && row.sell) {
      data.push(
        [
          row.horizon + ' 根',
          '卖出',
          cell(row.sell.count),
          fmtPct(row.sell.hit_rate),
          fmtPct(row.sell.baseline_hit_rate),
          fmtPct(row.sell.avg_return),
          fmtPct(row.sell.baseline_avg_return),
        ].join(','),
      )
    }
  })
  const csv = '\uFEFF' + [header.join(','), ...data].join('\n')
  try {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'easy_tdx_signal_accuracy_' + new Date().toISOString().slice(0, 10) + '.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    accCsvMsg.value = '✓ 已导出信号准确度 CSV'
  } catch {
    accCsvMsg.value = '导出失败（浏览器权限）'
  }
  setTimeout(() => {
    accCsvMsg.value = ''
  }, 2500)
}
</script>

<template>
  <div v-if="hasReport" class="accuracy-panel">
    <!-- 结论行 -->
    <div class="verdict" :class="verdictClass">
      <span class="verdict-label">模型准确度判定：</span>
      <span>{{ report?.verdict }}</span>
      <button class="ghost small acc-csv-btn" @click="exportAccCsv">📊 导出 CSV</button>
      <span v-if="accCsvMsg" class="save-msg">{{ accCsvMsg }}</span>
    </div>

    <!-- 基准对比 -->
    <div v-if="report?.benchmark" class="benchmark-row">
      <div class="bench-item">
        <span class="bench-label">策略收益</span>
        <span class="bench-value">{{ fmtPct(report.benchmark.strategy_return) }}</span>
      </div>
      <div class="bench-item">
        <span class="bench-label">同期买入持有</span>
        <span class="bench-value">{{ fmtPct(report.benchmark.buy_hold_return) }}</span>
      </div>
      <div class="bench-item">
        <span class="bench-label">超额收益 (Alpha)</span>
        <span class="bench-value" :class="(report.benchmark.alpha ?? 0) >= 0 ? 'pos' : 'neg'">
          {{ fmtPct(report.benchmark.alpha) }}
        </span>
      </div>
    </div>

    <!-- 前瞻命中率表格 -->
    <table class="accuracy-table">
      <thead>
        <tr>
          <th rowspan="2">持有根数</th>
          <th v-if="report?.buy" colspan="5">买入信号（择时进场）</th>
          <th v-if="report?.sell" colspan="5">卖出信号（回避下跌）</th>
        </tr>
        <tr>
          <template v-if="report?.buy">
            <th>信号数</th>
            <th>命中率</th>
            <th>随机基准</th>
            <th>平均前瞻收益</th>
            <th>中位收益</th>
            <th>盈亏比</th>
          </template>
          <template v-if="report?.sell">
            <th>信号数</th>
            <th>命中率</th>
            <th>随机基准</th>
            <th>平均前瞻收益</th>
            <th>中位收益</th>
            <th>盈亏比</th>
          </template>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.horizon">
          <td class="horizon">{{ r.horizon }} 根</td>
          <template v-if="report?.buy">
            <td>{{ cell(r.buy?.count) }}</td>
            <td :class="hitClass(r.buy?.hit_rate, r.buy?.baseline_hit_rate)">
              {{ fmtPct(r.buy?.hit_rate) }}
            </td>
            <td class="dim">{{ fmtPct(r.buy?.baseline_hit_rate) }}</td>
            <td :class="(r.buy?.avg_return ?? 0) >= 0 ? 'pos' : 'neg'">
              {{ fmtPct(r.buy?.avg_return) }}
            </td>
            <td class="dim">{{ fmtPct(r.buy?.median_return) }}</td>
            <td class="dim">{{ fmtPf(r.buy?.profit_factor) }}</td>
          </template>
          <template v-if="report?.sell">
            <td>{{ cell(r.sell?.count) }}</td>
            <td :class="hitClass(r.sell?.hit_rate, r.sell?.baseline_hit_rate)">
              {{ fmtPct(r.sell?.hit_rate) }}
            </td>
            <td class="dim">{{ fmtPct(r.sell?.baseline_hit_rate) }}</td>
            <td :class="(r.sell?.avg_return ?? 0) >= 0 ? 'pos' : 'neg'">
              {{ fmtPct(r.sell?.avg_return) }}
            </td>
            <td class="dim">{{ fmtPct(r.sell?.median_return) }}</td>
            <td class="dim">{{ fmtPf(r.sell?.profit_factor) }}</td>
          </template>
        </tr>
      </tbody>
    </table>

    <p class="legend">
      命中 = 买入后 N 根收益 &gt; 0（卖出后 N 根下跌）。随机基准 = 同期任意一天进场的平均结果；
      命中率高于随机基准说明择时对收益有正贡献。前瞻收益不含交易成本，与账户盈亏口径不同。
    </p>
  </div>
</template>

<style scoped>
.accuracy-panel {
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
.benchmark-row {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}
.bench-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.bench-label {
  font-size: 12px;
  color: var(--text-dim);
}
.bench-value {
  font-family: var(--font-mono);
  font-weight: 600;
  font-size: 14px;
}
.accuracy-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.accuracy-table th {
  font-size: 12px;
  color: var(--text-dim);
  font-weight: 600;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  text-align: right;
}
.accuracy-table th:first-child {
  text-align: left;
}
.accuracy-table td {
  padding: 5px 8px;
  border-bottom: 1px solid var(--border);
  text-align: right;
  font-family: var(--font-mono);
}
.accuracy-table td.horizon {
  font-family: inherit;
  text-align: left;
  color: var(--text-muted);
}
.dim {
  color: var(--text-dim);
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
