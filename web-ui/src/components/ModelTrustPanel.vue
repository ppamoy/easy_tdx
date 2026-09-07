<script setup lang="ts">
// 模型可信度综合评分面板：把回测里的信号准确度、稳健性、绩效对比
// 融合成一个 0-100 分，让用户一眼判断「这个模型的历史回测成绩可不可信」。

import { computed } from 'vue'

import type { ModelTrustReport } from '../types'

const props = defineProps<{
  report: ModelTrustReport | null | undefined
}>()

const hasReport = computed(() => Boolean(props.report && props.report.score !== undefined))

const gradeClass = computed(() => {
  if (!props.report) return ''
  if (props.report.grade === '高') return 'grade-high'
  if (props.report.grade === '中') return 'grade-mid'
  return 'grade-low'
})

const barColor = computed(() => {
  if (!props.report) return ''
  if (props.report.score >= 70) return 'var(--up)'
  if (props.report.score >= 50) return 'var(--warn, #f59e0b)'
  return 'var(--down)'
})
</script>

<template>
  <div v-if="hasReport" class="trust-panel">
    <div class="trust-head">
      <div class="score-block">
        <span class="score-num" :style="{ color: barColor }">{{ Math.round(report!.score) }}</span>
        <span class="score-max">/100</span>
        <span class="grade-badge" :class="gradeClass">{{ report!.grade }}可信</span>
      </div>
      <div class="trust-verdict">{{ report!.verdict }}</div>
    </div>

    <div class="bar-track">
      <div class="bar-fill" :style="{ width: report!.score + '%', background: barColor }"></div>
    </div>

    <div class="dims">
      <div class="dim-row">
        <span class="dim-label">择时准确度</span>
        <span class="dim-note" v-if="report!.components?.accuracy?.note">
          {{ report!.components.accuracy.note }}
        </span>
        <template v-else>
          <span class="dim-sub"
            >5根命中
            {{ ((report!.components?.accuracy?.hit_rate as number) ?? 0 * 100).toFixed(0) }}% · 超额
            {{
              ((report!.components?.accuracy?.excess_hit_rate as number) ?? 0).toFixed(1)
            }}%<template v-if="(report!.components?.accuracy?.profit_factor as number) > 0">
              · 盈亏比
              {{ (report!.components?.accuracy?.profit_factor as number).toFixed(2) }}
            </template></span
          >
        </template>
      </div>
      <div class="dim-row">
        <span class="dim-label">分段稳健性</span>
        <span class="dim-note" v-if="report!.components?.robustness?.overfit_likely === true">
          ⚠ 存在过拟合/行情依赖风险
        </span>
        <span class="dim-note" v-else-if="report!.components?.robustness?.overfit_likely === false">
          分段表现较一致
        </span>
        <span class="dim-note" v-else>未做分段检查</span>
      </div>
      <div class="dim-row">
        <span class="dim-label">绩效对比</span>
        <span class="dim-sub"
          >总收益 {{ ((report!.components?.performance?.total_return as number) ?? 0).toFixed(1) }}%
          · 超额 alpha
          {{ ((report!.components?.performance?.alpha as number) ?? 0).toFixed(1) }}%</span
        >
      </div>
    </div>

    <p class="legend">
      综合可信度 = 40% 择时准确度（信号命中率 vs 随机基准）+ 35% 分段稳健性（过拟合/行情依赖风险） +
      25% 绩效对比（相对买入持有）。分数越高说明「历史回测验证过的准确度」越扎实、越可持续。
    </p>
  </div>
</template>

<style scoped>
.trust-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.trust-head {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.score-block {
  display: flex;
  align-items: baseline;
  gap: 2px;
}
.score-num {
  font-family: var(--font-mono);
  font-size: 40px;
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
  flex: 1;
  min-width: 220px;
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
  transition: width 0.4s ease;
}
.dims {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
}
.dim-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: baseline;
}
.dim-label {
  color: var(--text-muted);
  font-weight: 600;
  min-width: 84px;
}
.dim-sub {
  color: var(--text-dim);
  font-family: var(--font-mono);
}
.dim-note {
  color: var(--text-dim);
}
.legend {
  font-size: 11px;
  color: var(--text-dim);
  line-height: 1.6;
  margin: 0;
}
</style>
