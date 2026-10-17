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

// ── 策略分组（optgroup）───────────────────────────────────────────
// 缠论类策略有 2 个（chanlun / changying_chanlun），
// 混在普通策略里很难找，而且名字相近容易选错（实测它们行为差异
// 很大：chanlun 默认带百分比止损止盈，changying_chanlun 叠加四季周期过滤）。
// 这里按「缠论类 / 其他」分组，让缠论的聚在一起。
//
// ⚠️ 历史：曾有第三个策略 `chanlun_pair`（同级别买卖点配对，不带止损止盈）。
//    已废弃删除 —— 它的区间套过滤用 level_synth 合成数据，是伪区间套，
//    不符合原文；真区间套将放前端页面用真实双周期数据实现。
//
// ⚠️ 判定口径：name 含 'chanlun' 或 label 含 '缠'。新增缠论策略会自动归入。
const CHANLUN_GROUP = '缠论类'
const OTHER_GROUP = '技术指标类'

function isChanlun(s: StrategySchema): boolean {
  return s.name.toLowerCase().includes('chanlun') || s.label.includes('缠')
}

const grouped = computed(() => {
  const chan: StrategySchema[] = []
  const other: StrategySchema[] = []
  for (const s of props.strategies) (isChanlun(s) ? chan : other).push(s)
  return [
    { label: CHANLUN_GROUP, items: chan },
    { label: OTHER_GROUP, items: other },
  ].filter((g) => g.items.length > 0)
})

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
        <optgroup v-for="g in grouped" :key="g.label" :label="g.label">
          <option v-for="s in g.items" :key="s.name" :value="s.name">
            {{ s.label }}（{{ s.name }}）
          </option>
        </optgroup>
      </select>
    </div>

    <p v-if="selectedSchema" class="desc">{{ selectedSchema.description }}</p>

    <!-- V102: 缠论策略按建议止损止盈提示 -->
    <!-- ⚠️ 原来写死 `=== 'chanlun'`，选到 changying_chanlun
         时提示不显示。改用 isChanlun() 覆盖全部缠论策略。
         （历史：曾有第三个缠论策略 chanlun_pair，已废弃删除） -->
    <div v-if="selectedSchema && isChanlun(selectedSchema)" class="v102-tip">
      💡 勾选「3买按V102建议止损止盈」：3买 首仓将按 V102
      决策支持的止损价/第一止盈价动态出场（优先于固定百分比止损）。
    </div>

    <!-- 缠论策略的差异说明（避免用户选错） -->
    <div v-if="selectedSchema && isChanlun(selectedSchema)" class="chanlun-diff">
      <strong>缠论策略的区别：</strong>
      <ul>
        <li><code>chanlun</code> 缠论买卖点 —— 默认<strong>开启</strong>百分比止损止盈
          （止损 8% / 止盈 25%），可能在同级别卖点出现前就被截断。</li>
        <li><code>changying_chanlun</code> 长赢缠论综合 —— 叠加吴伟志四季周期
          （播种/成长/收获/储藏）做仓位与过滤。</li>
      </ul>
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
.chanlun-diff {
  margin: 0 0 12px;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid var(--border, #30363d);
  background: rgba(255, 255, 255, 0.03);
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted);
}
.chanlun-diff strong {
  color: var(--text);
}
.chanlun-diff ul {
  margin: 4px 0 0;
  padding-left: 18px;
}
.chanlun-diff code {
  background: rgba(255, 255, 255, 0.08);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 11px;
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
