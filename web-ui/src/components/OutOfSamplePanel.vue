<script setup lang="ts">
// 样本外验证面板（V105）：把区间按时间切为训练段 + 样本外持有段，
// 验证模型在从未见过的数据上是否仍准确（过拟合的最硬检验）。

import { computed } from 'vue'

import { fmtPct } from '../format'
import type { OutOfSampleReport } from '../types'

const props = defineProps<{
  report: OutOfSampleReport | null | undefined
}>()

const hasReport = computed(() => Boolean(props.report?.train && props.report?.test))

const verdictClass = computed(() => {
  if (!props.report) return ''
  if (props.report.degraded) return 'verdict-neg'
  return 'verdict-pos'
})

function fmt(v: number | null | undefined): string {
  return v === null || v === undefined ? '-' : fmtPct(v)
}
</script>

<template>
  <div v-if="hasReport" class="oos-panel">
    <!-- 结论行 -->
    <div class="verdict" :class="verdictClass">
      <span class="verdict-label">样本外验证：</span>
      <span>{{ report?.verdict }}</span>
    </div>

    <!-- 训练段 vs 样本外段对比表 -->
    <table class="oos-table">
      <thead>
        <tr>
          <th>指标</th>
          <th>训练段（见过的数据）</th>
          <th>样本外段（没见过）</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td class="dim">K线数</td>
          <td>{{ report!.train.bars }}</td>
          <td>{{ report!.test.bars }}</td>
        </tr>
        <tr>
          <td class="dim">总收益</td>
          <td :class="(report!.train.total_return ?? 0) >= 0 ? 'pos' : 'neg'">{{ fmt(report!.train.total_return) }}</td>
          <td :class="(report!.test.total_return ?? 0) >= 0 ? 'pos' : 'neg'">{{ fmt(report!.test.total_return) }}</td>
        </tr>
        <tr>
          <td class="dim">胜率</td>
          <td>{{ fmt(report!.train.win_rate) }}</td>
          <td>{{ fmt(report!.test.win_rate) }}</td>
        </tr>
        <tr>
          <td class="dim">5根命中率</td>
          <td>{{ fmt(report!.train.hit_rate) }}</td>
          <td>{{ fmt(report!.test.hit_rate) }}</td>
        </tr>
        <tr>
          <td class="dim">随机基准命中率</td>
          <td>{{ fmt(report!.train.baseline_hit_rate) }}</td>
          <td>{{ fmt(report!.test.baseline_hit_rate) }}</td>
        </tr>
        <tr>
          <td class="dim">超额命中率</td>
          <td :class="(report!.train.excess_hit_rate ?? 0) >= 0 ? 'pos' : 'neg'">{{ fmt(report!.train.excess_hit_rate) }}</td>
          <td :class="(report!.test.excess_hit_rate ?? 0) >= 0 ? 'pos' : 'neg'">{{ fmt(report!.test.excess_hit_rate) }}</td>
        </tr>
        <tr>
          <td class="dim">买入持有</td>
          <td class="dim">{{ fmt(report!.train.buy_hold_return) }}</td>
          <td class="dim">{{ fmt(report!.test.buy_hold_return) }}</td>
        </tr>
        <tr>
          <td class="dim">夏普</td>
          <td>{{ (report!.train.sharpe ?? 0).toFixed(2) }}</td>
          <td>{{ (report!.test.sharpe ?? 0).toFixed(2) }}</td>
        </tr>
        <tr>
          <td class="dim">交易数</td>
          <td>{{ report!.train.trades }}</td>
          <td>{{ report!.test.trades }}</td>
        </tr>
      </tbody>
    </table>

    <p class="legend">
      方法：把回测区间按时间顺序切成训练段（默认前 70%）与样本外持有段（后 30%），
      策略参数完全固定，只"见过"训练段；然后在从未见过的样本外段上重跑。
      若样本外仍正收益、命中率高于随机基准并跑赢买入持有，说明模型具备泛化能力；
      若样本外明显衰减，提示存在过拟合，历史成绩需谨慎对待。
    </p>
  </div>
</template>

<style scoped>
.oos-panel {
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
.oos-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.oos-table th {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 600;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  text-align: right;
}
.oos-table th:first-child {
  text-align: left;
}
.oos-table td {
  padding: 5px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  text-align: right;
  font-family: var(--font-mono);
}
.oos-table td.dim {
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
