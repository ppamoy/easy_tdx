<script setup lang="ts">
// 成交记录表。展示每笔成交的方向/数量/价格/费用/盈亏/收益率。
// 增加：收益率列、连胜/连负统计、最优/最差交易高亮。

import { computed } from 'vue'
import type { Trade } from '../types'

const props = defineProps<{
  trades: Trade[]
  initialCash: number
}>()

function fmtDate(s: string): string {
  return s.slice(0, 10)
}
function fmtNum(v: number, digits = 2): string {
  return Number.isFinite(v) ? v.toFixed(digits) : '-'
}

// 计算每笔交易的收益率（相对于初始资金的百分比）
const tradesWithPct = computed(() =>
  props.trades.map((t) => ({
    ...t,
    pnlPct: t.pnl !== 0 ? (t.pnl / props.initialCash) * 100 : 0,
  })),
)

// 交易统计
const stats = computed(() => {
  const executed = props.trades.filter((t) => !t.rejected && t.pnl !== 0)
  if (executed.length === 0) return null

  const wins = executed.filter((t) => t.pnl > 0)
  const losses = executed.filter((t) => t.pnl < 0)
  const totalPnl = executed.reduce((s, t) => s + t.pnl, 0)
  const avgWin = wins.length > 0 ? wins.reduce((s, t) => s + t.pnl, 0) / wins.length : 0
  const avgLoss = losses.length > 0 ? losses.reduce((s, t) => s + t.pnl, 0) / losses.length : 0
  const profitFactor =
    losses.length > 0 && Math.abs(avgLoss) > 0
      ? wins.reduce((s, t) => s + t.pnl, 0) / Math.abs(losses.reduce((s, t) => s + t.pnl, 0))
      : Infinity
  const bestTrade = executed.reduce((a, b) => (b.pnl > a.pnl ? b : a), executed[0])
  const worstTrade = executed.reduce((a, b) => (b.pnl < a.pnl ? b : a), executed[0])

  // 最大连续亏损
  let maxConsecLoss = 0
  let currentStreak = 0
  for (const t of executed) {
    if (t.pnl < 0) {
      currentStreak++
      maxConsecLoss = Math.max(maxConsecLoss, currentStreak)
    } else {
      currentStreak = 0
    }
  }

  return {
    total: executed.length,
    winCount: wins.length,
    lossCount: losses.length,
    winRate: wins.length / executed.length,
    totalPnl,
    avgWin,
    avgLoss,
    profitFactor,
    bestTrade,
    worstTrade,
    maxConsecLoss,
  }
})

// 操作建议
const tradingAdvice = computed(() => {
  if (!stats.value) return null
  const s = stats.value
  if (s.winRate >= 0.6 && s.profitFactor >= 1.5 && s.totalPnl > 0) {
    return {
      text: '策略表现优秀：胜率高、盈亏比合理，可加大仓位或延长持有周期。',
      color: '#22c55e',
    }
  }
  if (s.winRate >= 0.5 && s.totalPnl > 0) {
    return {
      text: '策略基本有效：胜率尚可且整体盈利，建议优化止损参数减少大额亏损。',
      color: '#eab308',
    }
  }
  if (s.totalPnl < 0) {
    return {
      text: '策略当前亏损：建议检查市场环境是否适合该策略，或调整参数重新回测。',
      color: '#ef4444',
    }
  }
  return { text: '交易样本不足，无法给出可靠建议。', color: '#94a3b8' }
})
</script>

<template>
  <div class="trade-table-wrap">
    <!-- 交易统计摘要 -->
    <div v-if="stats" class="trade-summary">
      <div class="summary-grid">
        <div class="summary-item">
          <span class="summary-label">总交易</span>
          <span class="summary-value">{{ stats.total }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">胜率</span>
          <span
            class="summary-value"
            :style="{ color: stats.winRate >= 0.5 ? '#22c55e' : '#ef4444' }"
          >
            {{ (stats.winRate * 100).toFixed(1) }}%
          </span>
        </div>
        <div class="summary-item">
          <span class="summary-label">盈亏比</span>
          <span
            class="summary-value"
            :style="{ color: stats.profitFactor >= 1.5 ? '#22c55e' : '#f97316' }"
          >
            {{ isFinite(stats.profitFactor) ? stats.profitFactor.toFixed(2) : '∞' }}
          </span>
        </div>
        <div class="summary-item">
          <span class="summary-label">总盈亏</span>
          <span
            class="summary-value"
            :style="{ color: stats.totalPnl >= 0 ? '#22c55e' : '#ef4444' }"
          >
            {{ fmtNum(stats.totalPnl, 0) }}
          </span>
        </div>
        <div class="summary-item">
          <span class="summary-label">最优交易</span>
          <span class="summary-value" style="color: #22c55e">
            +{{ fmtNum(stats.bestTrade.pnl, 0) }}
          </span>
        </div>
        <div class="summary-item">
          <span class="summary-label">最差交易</span>
          <span class="summary-value" style="color: #ef4444">
            {{ fmtNum(stats.worstTrade.pnl, 0) }}
          </span>
        </div>
        <div class="summary-item">
          <span class="summary-label">最大连亏</span>
          <span
            class="summary-value"
            :style="{ color: stats.maxConsecLoss <= 2 ? '#22c55e' : '#f97316' }"
          >
            {{ stats.maxConsecLoss }} 笔
          </span>
        </div>
      </div>
      <!-- 操作建议 -->
      <div v-if="tradingAdvice" class="trade-advice" :style="{ borderColor: tradingAdvice.color }">
        <span class="advice-icon">💡</span>
        <span class="advice-text" :style="{ color: tradingAdvice.color }">{{
          tradingAdvice.text
        }}</span>
      </div>
    </div>

    <p v-if="trades.length === 0" class="empty">无成交记录</p>
    <table v-else class="trade-table">
      <thead>
        <tr>
          <th>日期</th>
          <th>方向</th>
          <th class="num">数量</th>
          <th class="num">价格</th>
          <th class="num">手续费</th>
          <th class="num">盈亏</th>
          <th class="num">收益率</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(t, i) in tradesWithPct"
          :key="i"
          :class="{
            rejected: t.rejected,
            best: t === stats?.bestTrade,
            worst: t === stats?.worstTrade,
          }"
        >
          <td>{{ fmtDate(t.datetime) }}</td>
          <td :class="t.direction">{{ t.direction }}</td>
          <td class="num">{{ fmtNum(t.size, 0) }}</td>
          <td class="num">{{ fmtNum(t.price, 3) }}</td>
          <td class="num muted">{{ fmtNum(t.commission, 2) }}</td>
          <td class="num" :class="{ pos: t.pnl > 0, neg: t.pnl < 0 }">
            {{ t.pnl === 0 ? '-' : fmtNum(t.pnl, 2) }}
          </td>
          <td class="num" :class="{ pos: t.pnlPct > 0, neg: t.pnlPct < 0 }">
            {{ t.pnl === 0 ? '-' : fmtNum(t.pnlPct, 2) + '%' }}
          </td>
        </tr>
      </tbody>
    </table>
    <p v-if="stats" class="legend">
      <span class="legend-item"
        ><span class="dot" style="background: #22c55e"></span>绿色=最优交易</span
      >
      <span class="legend-item"
        ><span class="dot" style="background: #ef4444"></span>红色=最差交易</span
      >
    </p>
  </div>
</template>

<style scoped>
.trade-table-wrap {
  overflow-x: auto;
}
.empty {
  color: var(--text-dim);
  font-size: 13px;
  padding: 16px 0;
}
.trade-summary {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  margin-bottom: 10px;
}
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(90px, 1fr));
  gap: 8px;
  margin-bottom: 8px;
}
.summary-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.summary-label {
  font-size: 10px;
  color: var(--text-dim);
}
.summary-value {
  font-size: 15px;
  font-weight: 700;
  font-family: var(--font-mono);
}
.trade-advice {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.4;
}
.advice-icon {
  font-size: 14px;
}
.advice-text {
  flex: 1;
}
.trade-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.trade-table th,
.trade-table td {
  padding: 7px 10px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}
.trade-table th {
  color: var(--text-dim);
  font-weight: 600;
  font-size: 12px;
  position: sticky;
  top: 0;
  background: var(--bg-panel);
}
.num {
  text-align: right;
  font-family: var(--font-mono);
}
.muted {
  color: var(--text-dim);
}
.BUY {
  color: var(--up);
  font-weight: 600;
}
.SELL {
  color: var(--down);
  font-weight: 600;
}
.pos {
  color: var(--up);
}
.neg {
  color: var(--down);
}
.rejected td {
  opacity: 0.4;
  text-decoration: line-through;
}
.best td {
  background: rgba(34, 197, 94, 0.08);
}
.worst td {
  background: rgba(239, 65, 70, 0.08);
}
.legend {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 6px;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}
</style>
