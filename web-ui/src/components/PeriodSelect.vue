<script setup lang="ts">
/**
 * 统一 K 线周期选择器。
 *
 * 全站 K 线图的周期（日线/周线/月线/5/15/30/60 分钟）只有这一处数据源，
 * 各视图通过 `v-model` 绑定自己的 category ref，保证：
 * - 可选周期、顺序、中文标签全站一致；
 * - 以后新增周期（如 MIN_1）只改这里。
 *
 * 用法：
 *   <PeriodSelect v-model="category" />
 *   <PeriodSelect v-model="category" :options="['DAY','MIN_30']" label="周期" />
 */
import type { Category } from '../types'

const model = defineModel<Category>({ default: 'DAY' })

withDefaults(
  defineProps<{
    /** 可选周期列表；缺省为全量 7 档 */
    options?: Category[]
    /** 左侧标签文案；不传则不渲染 label */
    label?: string
    /** 禁用（如加载中） */
    disabled?: boolean
  }>(),
  { options: undefined, label: undefined, disabled: false },
)

/** 全量周期，顺序与后端 frequency_map 对齐（大周期在前） */
const ALL: Category[] = ['DAY', 'WEEK', 'MONTH', 'MIN_5', 'MIN_15', 'MIN_30', 'MIN_60']

const LABELS: Record<Category, string> = {
  DAY: '日线',
  WEEK: '周线',
  MONTH: '月线',
  MIN_5: '5分钟',
  MIN_15: '15分钟',
  MIN_30: '30分钟',
  MIN_60: '60分钟',
}
</script>

<template>
  <span class="period-select">
    <label v-if="label">{{ label }}</label>
    <select v-model="model" :disabled="disabled" aria-label="K线周期">
      <option v-for="c in options ?? ALL" :key="c" :value="c">{{ LABELS[c] ?? c }}</option>
    </select>
  </span>
</template>

<style scoped>
.period-select {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.period-select label {
  font-size: 12px;
  color: var(--text-secondary, #666);
  white-space: nowrap;
}

.period-select select {
  padding: 3px 6px;
  font-size: 12px;
  border: 1px solid var(--border-color, #d0d7de);
  border-radius: 4px;
  background: var(--bg-input, #fff);
  color: var(--text-primary, #1f2328);
}

.period-select select:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
