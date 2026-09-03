<script setup lang="ts">
// 参数寻优「验证总结」卡片（V124）：把最优点可信度（V101）+ 5根命中率（V95）
// + Walk-Forward 判定（V123）聚合成一览，回答「按验证过的准确度该选哪组参数」。

import { computed, ref } from 'vue'

import type { OptimizeResult } from '../types'

const props = defineProps<{
  result: OptimizeResult | null | undefined
}>()

const best = computed(() => props.result?.best ?? null)

const overallClass = computed(() => {
  const g = best.value?.trust_grade
  if (g === '高') return 'pos'
  if (g === '低') return 'neg'
  return g ? 'warn' : 'neutral'
})

const trustText = computed(() => {
  const b = best.value
  if (!b || b.trust_score === null || b.trust_score === undefined) return '未评估'
  return Math.round(b.trust_score) + '/100 · ' + (b.trust_grade ?? '') + '可信'
})

const rows = computed<Array<{ label: string; text: string; cls: string }>>(() => {
  const b = best.value
  const wf = props.result?.walk_forward
  const out: Array<{ label: string; text: string; cls: string }> = []
  if (b) {
    if (b.trust_score !== null && b.trust_score !== undefined) {
      out.push({ label: '📊 最佳参数可信度', text: trustText.value, cls: overallClass.value })
    }
    if (b.hit_rate !== null && b.hit_rate !== undefined) {
      const excess = b.excess_hit_rate ?? 0
      out.push({
        label: '🎯 5根命中率',
        text:
          (b.hit_rate * 100).toFixed(0) +
          '% · 超额 ' +
          (excess >= 0 ? '+' : '') +
          (excess * 100).toFixed(1) +
          '%',
        cls: excess > 0 ? 'pos' : excess < 0 ? 'neg' : 'neutral',
      })
    }
  }
  if (wf?.verdict) {
    out.push({ label: '🔁 Walk-Forward', text: wf.verdict, cls: wf.degraded ? 'neg' : 'pos' })
  }
  if (props.result?.walk_forward && !wf) {
    out.push({ label: '🔁 Walk-Forward', text: '未启用', cls: 'neutral' })
  }
  return out
})

// V305: 寻优验证总结复制 Markdown（与回测 V301 对齐）
const ovCopyMsg = ref('')
async function copyOptimizeSummary() {
  if (!rows.value.length) return
  const lines = ['# easy-tdx 寻优验证总结']
  lines.push('')
  lines.push('- 最佳参数：' + (best.value ? JSON.stringify(best.value.params ?? {}) : '-'))
  rows.value.forEach((r) => {
    lines.push('- ' + r.label + '：' + r.text)
  })
  lines.push('')
  lines.push('生成时间：' + new Date().toLocaleString('zh-CN'))
  const text = lines.join('\n')
  try {
    await navigator.clipboard.writeText(text)
    ovCopyMsg.value = '✓ 已复制验证总结'
  } catch {
    ovCopyMsg.value = '复制失败（浏览器权限）'
  }
  setTimeout(() => {
    ovCopyMsg.value = ''
  }, 2500)
}
</script>

<template>
  <div v-if="best && rows.length" class="ov-summary">
    <div class="ov-head">
      <span class="ov-title">✅ 验证总结（最优点）</span>
      <button class="ghost small ov-copy-btn" @click="copyOptimizeSummary">📋 复制验证总结</button>
      <span v-if="ovCopyMsg" class="save-msg">{{ ovCopyMsg }}</span>
      <span v-if="trustText !== '未评估'" class="ov-overall" :class="overallClass">{{
        trustText
      }}</span>
    </div>
    <div class="ov-rows">
      <div v-for="row in rows" :key="row.label" class="ov-row" :class="row.cls">
        <span class="ov-label">{{ row.label }}</span>
        <span class="ov-text">{{ row.text }}</span>
      </div>
    </div>
    <p class="ov-legend">
      最优点按寻优排序取第一位；配合 Walk-Forward 滚动验证判断参数是否过拟合。勾选「Walk-Forward
      验证」可看到逐窗口训练/测试表现。
    </p>
  </div>
</template>

<style scoped>
.ov-summary {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
}
.ov-head {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.ov-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
}
.ov-overall {
  font-size: 12px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}
.ov-overall.pos {
  color: var(--up);
  background: rgba(34, 197, 94, 0.12);
}
.ov-overall.warn {
  color: var(--warn, #f59e0b);
  background: rgba(245, 158, 11, 0.12);
}
.ov-overall.neg {
  color: var(--down);
  background: rgba(239, 68, 68, 0.12);
}
.ov-rows {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ov-row {
  display: flex;
  gap: 10px;
  align-items: baseline;
  font-size: 12px;
  padding-left: 8px;
  border-left: 3px solid var(--border);
}
.ov-row.pos {
  border-left-color: var(--up);
}
.ov-row.warn {
  border-left-color: var(--warn, #f59e0b);
}
.ov-row.neg {
  border-left-color: var(--down);
}
.ov-label {
  color: var(--text-muted);
  font-weight: 600;
  white-space: nowrap;
  min-width: 108px;
}
.ov-text {
  color: var(--text);
  line-height: 1.5;
}
.ov-legend {
  font-size: 11px;
  color: var(--text-dim);
  line-height: 1.6;
  margin: 0;
}
</style>
