<script setup lang="ts">
// Walk-Forward 滚动验证报告面板（V123）：展示滚动窗口训练/测试表现与防过拟合结论。

import { computed } from 'vue'

import type { WalkForwardReport } from '../types'

const props = defineProps<{
  report: WalkForwardReport | null | undefined
}>()

const verdictClass = computed(() => {
  if (!props.report) return ''
  return props.report.degraded ? 'verdict-neg' : 'verdict-pos'
})

function pct(v: number | null | undefined): string {
  return v === null || v === undefined || !Number.isFinite(v) ? '-' : (v * 100).toFixed(1) + '%'
}
</script>

<template>
  <div v-if="report" class="wf-panel">
    <div class="verdict" :class="verdictClass">
      <span class="verdict-label">Walk-Forward 判定：</span>
      <span>{{ report.verdict }}</span>
    </div>

    <div class="wf-summary">
      <div class="wf-item"><span class="k">窗口数</span><span class="v">{{ report.windows }}</span></div>
      <div class="wf-item"><span class="k">训练段均值收益</span><span class="v">{{ pct(report.train_mean) }}</span></div>
      <div class="wf-item"><span class="k">测试段均值收益</span><span class="v" :class="(report.test_mean ?? 0) >= 0 ? 'pos' : 'neg'">{{ pct(report.test_mean) }}</span></div>
      <div class="wf-item"><span class="k">正收益测试窗口</span><span class="v" :class="report.positive_test_windows >= Math.max(1, report.windows * 0.5) ? 'pos' : 'neg'">{{ report.positive_test_windows }}/{{ report.windows }}</span></div>
    </div>

    <table class="wf-table">
      <thead>
        <tr>
          <th>窗口</th><th>参数</th><th class="num">训练收益</th><th class="num">测试收益</th>
          <th class="num">测试夏普</th><th class="num">测试胜率</th><th class="num">交易数</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="w in report.windows_detail" :key="w.window">
          <td class="dim">{{ w.window + 1 }}</td>
          <td class="params">{{ JSON.stringify(w.params) }}</td>
          <td class="num" :class="(w.train_return ?? 0) >= 0 ? 'pos' : 'neg'">{{ pct(w.train_return) }}</td>
          <td class="num" :class="(w.test_return ?? 0) >= 0 ? 'pos' : 'neg'">{{ pct(w.test_return) }}</td>
          <td class="num">{{ (w.test_sharpe ?? 0).toFixed(2) }}</td>
          <td class="num">{{ pct(w.test_win_rate) }}</td>
          <td class="num">{{ w.test_trades }}</td>
        </tr>
      </tbody>
    </table>

    <p class="wf-legend">方法：把区间滚动切分成训练窗口，在每段训练上独立寻优，再在随后的未见过测试段验证——
      若多数测试窗口仍正收益且不较训练段明显衰减，说明所选参数具备泛化能力；否则提示过拟合风险，选参需谨慎。</p>
  </div>
</template>

<style scoped>
.wf-panel {
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
.verdict-label { font-weight: 600; margin-right: 4px; }
.verdict-pos { color: var(--up); }
.verdict-neg { color: var(--down); }
.wf-summary {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  font-size: 12px;
}
.wf-item { display: flex; flex-direction: column; gap: 2px; }
.wf-item .k { color: var(--text-dim); font-size: 11px; }
.wf-item .v { font-family: var(--font-mono); font-weight: 600; }
.wf-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.wf-table th {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 600;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  text-align: right;
}
.wf-table th:first-child, .wf-table td:first-child { text-align: left; }
.wf-table td {
  padding: 5px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  text-align: right;
  font-family: var(--font-mono);
}
.wf-table td.params { font-size: 11px; color: var(--text-muted); }
.wf-legend { font-size: 11px; color: var(--text-dim); line-height: 1.6; margin: 0; }
.pos { color: var(--up); }
.neg { color: var(--down); }
.dim { color: var(--text-dim); }
</style>
