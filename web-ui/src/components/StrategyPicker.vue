<script setup lang="ts">
// 策略选择 + 动态参数表单。
// 核心能力：选中策略后，按后端 params schema 动态渲染表单控件
// （int/float→number、str+choices→select、bool→checkbox），带 min/max/default。

import { computed, watch } from 'vue'

import type { ParamSchema, StrategySchema } from '../types'

const props = defineProps<{
  strategies: StrategySchema[]
  strategy: string
  params: Record<string, number | string | boolean>
}>()

const emit = defineEmits<{
  'update:strategy': [value: string]
  'update:params': [value: Record<string, number | string | boolean>]
}>()

// 当前选中策略的 schema（用于渲染参数表单）
const selectedSchema = computed(
  () => props.strategies.find((s) => s.name === props.strategy) ?? null,
)

// 切换策略时重置参数为默认值
watch(
  selectedSchema,
  (schema) => {
    if (!schema) return
    const defaults: Record<string, number | string | boolean> = {}
    for (const p of schema.params) defaults[p.name] = p.default
    emit('update:params', defaults)
  },
  { immediate: true },
)

function paramValue(p: ParamSchema) {
  return props.params[p.name] ?? p.default
}

function updateParam(p: ParamSchema, raw: string | boolean) {
  let v: number | string | boolean = raw
  if (p.type === 'int' || p.type === 'float') {
    // 空字符串（用户清空输入框中）：不 emit，保留旧值，避免把 0 回填打断输入
    if (raw === '') return
    const num = Number(raw)
    if (!Number.isFinite(num)) return // 非法中间态（如 "1."、"1e"）：不更新
    v = num
  }
  emit('update:params', { ...props.params, [p.name]: v })
}
</script>

<template>
  <div class="strategy-picker">
    <div class="field">
      <label>策略</label>
      <select
        :value="strategy"
        @change="emit('update:strategy', ($event.target as HTMLSelectElement).value)"
      >
        <option v-for="s in strategies" :key="s.name" :value="s.name">
          {{ s.label }}（{{ s.name }}）
        </option>
      </select>
    </div>

    <p v-if="selectedSchema" class="desc">{{ selectedSchema.description }}</p>

    <!-- V102: 缠论策略按建议止损止盈提示 -->
    <div v-if="selectedSchema?.name === 'chanlun'" class="v102-tip">
      💡 勾选「3买按V102建议止损止盈」：3买 首仓将按 V102
      决策支持的止损价/第一止盈价动态出场（优先于固定百分比止损）。
    </div>

    <!-- 动态参数表单：按 schema 渲染 -->
    <div v-if="selectedSchema?.params.length" class="params">
      <div v-for="p in selectedSchema.params" :key="p.name" class="field">
        <label>{{ p.label }}</label>
        <!-- str + choices → 下拉 -->
        <select
          v-if="p.type === 'str' && p.choices"
          :value="String(paramValue(p))"
          @change="updateParam(p, ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="c in p.choices" :key="c" :value="c">{{ c }}</option>
        </select>
        <!-- bool → 复选 -->
        <input
          v-else-if="p.type === 'bool'"
          type="checkbox"
          :checked="Boolean(paramValue(p))"
          @change="updateParam(p, ($event.target as HTMLInputElement).checked)"
        />
        <!-- int/float → 数字输入（带 min/max） -->
        <input
          v-else
          type="number"
          :value="paramValue(p)"
          :min="p.min_value"
          :max="p.max_value"
          :step="p.type === 'float' ? 'any' : '1'"
          @input="updateParam(p, ($event.target as HTMLInputElement).value)"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.desc {
  color: var(--text-muted);
  font-size: 12px;
  margin: -4px 0 12px;
  line-height: 1.4;
}
.params {
  display: flex;
  flex-direction: column;
}
input[type='checkbox'] {
  width: auto;
}
.v102-tip {
  margin: -2px 0 10px;
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px dashed var(--accent, #4a9eff);
  background: rgba(74, 158, 255, 0.06);
  color: var(--text);
  font-size: 12px;
  line-height: 1.5;
}
</style>
