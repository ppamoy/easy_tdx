<script setup lang="ts">
// 回测「验证总结」聚合卡片（V106）：把 V95 信号准确度、V97 分段稳健性、
// V101 模型可信度、V105 样本外验证的结论浓缩成一张可一览的卡片，
// 让用户快速判断「这个模型经过历史回测验证后到底可不可信」。

import { computed } from 'vue'

import type { BacktestResult } from '../types'

const props = defineProps<{
  result: BacktestResult | null | undefined
}>()

interface VerdictRow {
  key: string
  label: string
  text: string
  state: 'pos' | 'warn' | 'neg' | 'neutral'
}

const rows = computed<VerdictRow[]>(() => {
  const r = props.result
  if (!r) return []

  const out: VerdictRow[] = []

  // V101 模型可信度
  if (r.model_trust) {
    out.push({
      key: 'trust',
      label: '📊 模型可信度',
      text: Math.round(r.model_trust.score) + '/100 · ' + r.model_trust.grade + '可信',
      state: r.model_trust.grade === '高' ? 'pos' : r.model_trust.grade === '低' ? 'neg' : 'warn',
    })
  }

  // V95 信号准确度
  if (r.signal_accuracy?.verdict) {
    const v = r.signal_accuracy.verdict
    const state = v.includes('显著') || v.includes('具备') ? 'pos' : v.includes('低于') ? 'neg' : 'neutral'
    out.push({ key: 'accuracy', label: '🎯 信号准确度', text: v, state })
  }

  // V97 分段稳健性
  if (r.segment_robustness?.verdict) {
    const v = r.segment_robustness.verdict
    const state = r.segment_robustness.overfit_likely ? 'neg' : v.includes('较一致') ? 'pos' : 'neutral'
    out.push({ key: 'robust', label: '🧱 分段稳健性', text: v, state })
  }

  // V105 样本外验证
  if (r.out_of_sample?.verdict) {
    const v = r.out_of_sample.verdict
    const state = r.out_of_sample.degraded ? 'neg' : 'pos'
    out.push({ key: 'oos', label: '🔬 样本外验证', text: v, state })
  }

  return out
})

const overall = computed(() => {
  const r = props.result
  if (!r?.model_trust) return { text: '', state: 'neutral' as const }
  return { text: '综合可信度 ' + Math.round(r.model_trust.score) + '/100', state: r.model_trust.grade === '高' ? 'pos' as const : r.model_trust.grade === '低' ? 'neg' as const : 'warn' as const }
})
</script>

<template>
  <div v-if="rows.length" class="validation-summary">
    <div class="vs-head">
      <span class="vs-title">✅ 验证总结</span>
      <span v-if="overall.text" class="vs-overall" :class="overall.state">{{ overall.text }}</span>
    </div>
    <div class="vs-rows">
      <div v-for="row in rows" :key="row.key" class="vs-row" :class="row.state">
        <span class="vs-label">{{ row.label }}</span>
        <span class="vs-text">{{ row.text }}</span>
      </div>
    </div>
    <p class="vs-legend">综合可信度（V101）＝择时准确度＋分段稳健性＋绩效对比；配合信号准确度（V95）、分段稳健性（V97）、样本外验证（V105）共同回答「模型经过历史回测验证是否可信、是否可持续」。</p>
  </div>
</template>

<style scoped>
.validation-summary {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
}
.vs-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.vs-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
}
.vs-overall {
  font-size: 12px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}
.vs-overall.pos {
  color: var(--up);
  background: rgba(34, 197, 94, 0.12);
}
.vs-overall.warn {
  color: var(--warn, #f59e0b);
  background: rgba(245, 158, 11, 0.12);
}
.vs-overall.neg {
  color: var(--down);
  background: rgba(239, 68, 68, 0.12);
}
.vs-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.vs-row {
  display: flex;
  gap: 10px;
  align-items: baseline;
  font-size: 12px;
  padding-left: 8px;
  border-left: 3px solid var(--border);
}
.vs-row.pos {
  border-left-color: var(--up);
}
.vs-row.warn {
  border-left-color: var(--warn, #f59e0b);
}
.vs-row.neg {
  border-left-color: var(--down);
}
.vs-label {
  color: var(--text-muted);
  font-weight: 600;
  white-space: nowrap;
  min-width: 108px;
}
.vs-text {
  color: var(--text);
  line-height: 1.5;
}
.vs-legend {
  font-size: 11px;
  color: var(--text-dim);
  line-height: 1.6;
  margin: 0;
}
</style>
