<script setup lang="ts">
// 缠论信号类型准确度面板：按 1buy/2buy/3buy/1sell/... 分组显示前瞻命中率。
// 让用户通过历史回测核对「哪类信号真的准」，而不只是看账户总收益。

import { computed } from 'vue'
import { fmtPct } from '../format'
import type { SignalHorizonStat } from '../types'

const props = defineProps<{
  byType: Record<string, any> | null | undefined
  ranking: Array<{
    type: string
    direction: string
    signals: number
    excess_hit_rate: number
    hit_rate: number
    avg_return: number
    verdict: string
  }> | null | undefined
  summary: string | null | undefined
}>()

const MMD_COLORS: Record<string, string> = {
  '1buy': '#22c55e',
  '2buy': '#4ade80',
  '3buy': '#86efac',
  '2buy_s': '#bbf7d0',
  '1sell': '#ef4444',
  '2sell': '#f87171',
  '3sell': '#fca5a5',
  '2sell_s': '#fecaca',
}

const hasData = computed(() => {
  if (!props.byType || Object.keys(props.byType).length === 0) return false
  return true
})

const HORIZON_ORDER = ['1', '3', '5', '10', '20']

interface TypeRow {
  type: string
  direction: string
  signals: number
  horizons: Record<string, SignalHorizonStat>
  verdict: string
}

const typeRows = computed<TypeRow[]>(() => {
  if (!props.byType) return []
  return Object.values(props.byType) as TypeRow[]
})

function hitClass(rate: number | undefined, baseline: number | undefined): string {
  if (rate === undefined || baseline === undefined) return ''
  if (rate - baseline > 0.02) return 'pos'
  if (rate - baseline < -0.02) return 'neg'
  return ''
}

function cell(n: number | undefined): string {
  return n === undefined ? '–' : String(n)
}

function typeColor(type: string): string {
  return MMD_COLORS[type] ?? '#94a3b8'
}
</script>

<template>
  <div v-if="hasData" class="chanlun-accuracy-panel">
    <!-- 总体结论 -->
    <div v-if="summary" class="summary-banner">
      {{ summary }}
    </div>

    <!-- 排名表 -->
    <div class="ranking-section">
      <h4>📊 信号类型排名（按 5 根超额命中率降序）</h4>
      <table class="ranking-table">
        <thead>
          <tr>
            <th>类型</th>
            <th>方向</th>
            <th>信号数</th>
            <th>5根命中率</th>
            <th>随机基准</th>
            <th>超额命中率</th>
            <th>5根均收益</th>
            <th>判定</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in ranking" :key="r.type" :class="{ 'row-buy': r.direction === 'BUY', 'row-sell': r.direction === 'SELL' }">
            <td>
              <span class="type-badge" :style="{ background: typeColor(r.type) + '22', color: typeColor(r.type), borderColor: typeColor(r.type) }">
                {{ r.type }}
              </span>
            </td>
            <td>{{ r.direction === 'BUY' ? '📈 买入' : '📉 卖出' }}</td>
            <td>{{ r.signals }}</td>
            <td :class="hitClass(r.hit_rate, r.excess_hit_rate >= 0 ? 0.5 : 0.5)">
              {{ fmtPct(r.hit_rate) }}
            </td>
            <td class="dim">{{ fmtPct(r.hit_rate - r.excess_hit_rate) }}</td>
            <td :class="r.excess_hit_rate >= 0 ? 'pos' : 'neg'">
              {{ r.excess_hit_rate >= 0 ? '+' : '' }}{{ fmtPct(r.excess_hit_rate) }}
            </td>
            <td :class="r.avg_return >= 0 ? 'pos' : 'neg'">
              {{ r.avg_return >= 0 ? '+' : '' }}{{ fmtPct(r.avg_return) }}
            </td>
            <td class="verdict">{{ r.verdict }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 各类型详细前瞻命中表 -->
    <div v-for="row in typeRows" :key="row.type" class="type-detail">
      <h4>
        <span class="type-badge" :style="{ background: typeColor(row.type) + '22', color: typeColor(row.type), borderColor: typeColor(row.type) }">
          {{ row.type }}
        </span>
        {{ row.direction === 'BUY' ? '买入' : '卖出' }}信号前瞻命中率
        <span class="signal-count">（{{ row.signals }} 个信号）</span>
      </h4>
      <table class="detail-table">
        <thead>
          <tr>
            <th>持有根数</th>
            <th>信号数</th>
            <th>命中率</th>
            <th>随机基准</th>
            <th>超额命中率</th>
            <th>平均收益</th>
            <th>中位收益</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="h in HORIZON_ORDER" :key="h">
            <td class="horizon">{{ h }} 根</td>
            <template v-if="row.horizons[h]">
              <td>{{ cell(row.horizons[h].count) }}</td>
              <td :class="hitClass(row.horizons[h].hit_rate, row.horizons[h].baseline_hit_rate)">
                {{ fmtPct(row.horizons[h].hit_rate) }}
              </td>
              <td class="dim">{{ fmtPct(row.horizons[h].baseline_hit_rate) }}</td>
              <td :class="row.horizons[h].excess_hit_rate >= 0 ? 'pos' : 'neg'">
                {{ row.horizons[h].excess_hit_rate >= 0 ? '+' : '' }}{{ fmtPct(row.horizons[h].excess_hit_rate) }}
              </td>
              <td :class="row.horizons[h].avg_return >= 0 ? 'pos' : 'neg'">
                {{ row.horizons[h].avg_return >= 0 ? '+' : '' }}{{ fmtPct(row.horizons[h].avg_return) }}
              </td>
              <td class="dim">{{ fmtPct(row.horizons[h].median_return) }}</td>
            </template>
            <td v-else colspan="6" class="dim">—</td>
          </tr>
        </tbody>
      </table>
    </div>

    <p class="legend">
      命中 = 买入后 N 根收益 &gt; 0（卖出后 N 根下跌）。随机基准 = 同期任意一天进场的平均结果；
      命中率高于随机基准说明该信号类型择时有正贡献。绿色 = 显著优于随机，红色 = 弱于随机。
    </p>
  </div>
</template>

<style scoped>
.chanlun-accuracy-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.summary-banner {
  font-size: 13px;
  line-height: 1.6;
  padding: 10px 14px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
  color: var(--text);
}

.ranking-section h4,
.type-detail h4 {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  margin: 0 0 8px 0;
}

.signal-count {
  font-weight: 400;
  color: var(--text-dim);
}

.ranking-table,
.detail-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.ranking-table th,
.detail-table th {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 500;
  padding: 5px 8px;
  border-bottom: 1px solid var(--border);
  text-align: right;
}

.ranking-table th:first-child,
.detail-table th:first-child {
  text-align: left;
}

.ranking-table td,
.detail-table td {
  padding: 4px 8px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  text-align: right;
  font-family: var(--font-mono);
}

.ranking-table td:first-child,
.detail-table td:first-child {
  text-align: left;
}

.row-buy { background: rgba(34, 197, 94, 0.03); }
.row-sell { background: rgba(239, 65, 70, 0.03); }

.type-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  border: 1px solid;
  letter-spacing: 0.5px;
}

.horizon {
  font-family: inherit;
  text-align: left;
  color: var(--text-muted);
}

.dim { color: var(--text-dim); }
.pos { color: var(--up); }
.neg { color: var(--down); }

.verdict {
  font-family: inherit;
  font-size: 11px;
  color: var(--text-dim);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.legend {
  font-size: 11px;
  color: var(--text-dim);
  line-height: 1.6;
  margin: 0;
  padding: 8px 0;
  border-top: 1px solid var(--border);
}
</style>
