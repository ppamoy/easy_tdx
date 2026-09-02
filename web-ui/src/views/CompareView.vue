<script setup lang="ts">
// 结果对比页面：选 2-4 个已完成的回测 task，叠加净值曲线 + 横向指标对比。
// 支持单标的回测（equity_curve）和组合回测（combined_equity）的混合对比。

import { onMounted, ref, watch } from 'vue'

import CompareChart from '../components/CompareChart.vue'
import CompareTable from '../components/CompareTable.vue'
import { fetchTask, fetchTaskList, formatError } from '../api'
import type { BacktestResult, EquityPoint, TaskSummary } from '../types'

/** 统一的可对比项：无论单标的还是组合，都归一化为 equity + performance。 */
interface CompareItem {
  label: string
  equity: EquityPoint[]
  performance: Record<string, number>
  // V102: 透传准确度/可信度字段，让对比表展示「验证过的准确度」而非只比收益
  model_trust?: BacktestResult['model_trust']
  signal_accuracy?: BacktestResult['signal_accuracy']
  // V125: 透传稳健性/样本外字段，对比「过不过拟合」
  segment_robustness?: BacktestResult['segment_robustness']
  out_of_sample?: BacktestResult['out_of_sample']
}

const taskList = ref<TaskSummary[]>([])
const loading = ref(false)
const error = ref('')
const selectedIds = ref<Set<string>>(new Set())
const details = ref<Map<string, CompareItem>>(new Map())

onMounted(loadTasks)

async function loadTasks() {
  loading.value = true
  error.value = ''
  try {
    const resp = await fetchTaskList(20)
    taskList.value = resp.tasks.filter((t) => t.status === 'done')
  } catch (e) {
    error.value = formatError(e)
  } finally {
    loading.value = false
  }
}

/** 从 task result 提取可对比的 equity + performance。
 * 支持单标的（equity_curve/performance）和组合（combined_equity/total_performance）。 */
function extractComparable(
  result: Record<string, unknown> | null,
): {
  equity: EquityPoint[]
  performance: Record<string, number>
  model_trust?: BacktestResult['model_trust']
  signal_accuracy?: BacktestResult['signal_accuracy']
  segment_robustness?: BacktestResult['segment_robustness']
  out_of_sample?: BacktestResult['out_of_sample']
} | null {
  if (!result) return null
  // 单标的回测
  if (result.performance && result.equity_curve) {
    return {
      equity: result.equity_curve as EquityPoint[],
      performance: result.performance as Record<string, number>,
      model_trust: result.model_trust as BacktestResult['model_trust'],
      signal_accuracy: result.signal_accuracy as BacktestResult['signal_accuracy'],
      segment_robustness: result.segment_robustness as BacktestResult['segment_robustness'],
      out_of_sample: result.out_of_sample as BacktestResult['out_of_sample'],
    }
  }
  // 组合回测
  if (result.total_performance && result.combined_equity) {
    return {
      equity: result.combined_equity as EquityPoint[],
      performance: result.total_performance as Record<string, number>,
      model_trust: result.model_trust as BacktestResult['model_trust'],
      signal_accuracy: result.signal_accuracy as BacktestResult['signal_accuracy'],
      segment_robustness: result.segment_robustness as BacktestResult['segment_robustness'],
      out_of_sample: result.out_of_sample as BacktestResult['out_of_sample'],
    }
  }
  return null
}

async function toggle(taskId: string) {
  if (selectedIds.value.has(taskId)) {
    selectedIds.value.delete(taskId)
    details.value.delete(taskId)
  } else {
    if (selectedIds.value.size >= 4) return
    selectedIds.value.add(taskId)
    try {
      const state = await fetchTask(taskId)
      const comparable = extractComparable(state.result as Record<string, unknown> | null)
      if (!comparable) {
        throw new Error('该任务结果不含净值曲线（寻优任务等不可对比）')
      }
      details.value.set(taskId, { label: state.description, ...comparable })
    } catch (e) {
      selectedIds.value.delete(taskId)
      error.value = e instanceof Error ? e.message : String(e)
    }
  }
  selectedIds.value = new Set(selectedIds.value)
  details.value = new Map(details.value)
}

const compareItems = ref<Array<{ label: string; result: BacktestResult }>>([])
function refreshItems() {
  // CompareChart/CompareTable 期望 { label, result: BacktestResult }，
  // 这里把归一化的 equity/performance 包装回去
  compareItems.value = Array.from(details.value.values()).map((item) => ({
    label: item.label,
    result: {
      equity_curve: item.equity,
      performance: item.performance,
      model_trust: item.model_trust,
      signal_accuracy: item.signal_accuracy,
      segment_robustness: item.segment_robustness,
      out_of_sample: item.out_of_sample,
    } as unknown as BacktestResult,
  }))
}

watch(details, refreshItems, { deep: true })
// V267: 指标对比导出 CSV（行=指标、列=对比任务，Excel 友好）
const compareCsvMsg = ref('')
function cmpPct(v: number | undefined | null): string {
  return v === undefined || v === null || !Number.isFinite(v) ? '-' : (v * 100).toFixed(2) + '%'
}
function cmpNum(v: number | undefined | null): string {
  return v === undefined || v === null || !Number.isFinite(v) ? '-' : v.toFixed(3)
}
function cmpCsvEscape(v: string): string {
  return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v
}
function exportCompareCsv() {
  if (compareItems.value.length < 2) return
  const perf = (i: { label: string; result: BacktestResult }) =>
    (i.result.performance || {}) as unknown as Record<string, number>
  const rows: string[][] = [['指标', ...compareItems.value.map((i) => cmpCsvEscape(i.label))]]
  const metricRows: Array<[string, string, (p: Record<string, number>) => string]> = [
    ['总收益', 'pct', (p) => cmpPct(p.total_return)],
    ['年化收益', 'pct', (p) => cmpPct(p.annual_return)],
    ['夏普', 'num', (p) => cmpNum(p.sharpe)],
    ['最大回撤', 'pct', (p) => cmpPct(p.max_drawdown)],
    ['胜率', 'pct', (p) => cmpPct(p.win_rate)],
    ['盈亏比', 'num', (p) => cmpNum(p.profit_factor)],
    ['交易数', 'num', (p) => String(p.total_trades ?? '-')],
    ['波动率', 'pct', (p) => cmpPct(p.volatility)],
  ]
  metricRows.forEach(([label, , fmt]) => {
    rows.push([label, ...compareItems.value.map((i) => fmt(perf(i)))])
  })
  // 验证维度行：可信度 / 5根命中率 / 超额命中率 / 样本外 / 稳健性
  rows.push(['可信度', ...compareItems.value.map((i) => {
    const t = i.result.model_trust
    return t && t.score !== undefined ? Math.round(t.score) + '/100 ' + t.grade : '-'
  })])
  rows.push(['5根命中率', ...compareItems.value.map((i) => {
    const h = i.result.signal_accuracy?.buy?.horizons?.['5']
    return h && h.count > 0 ? cmpPct(h.hit_rate) : '-'
  })])
  rows.push(['超额命中率', ...compareItems.value.map((i) => {
    const h = i.result.signal_accuracy?.buy?.horizons?.['5']
    return h && h.count > 0 ? cmpPct(h.excess_hit_rate) : '-'
  })])
  rows.push(['样本外验证', ...compareItems.value.map((i) => {
    const o = i.result.out_of_sample
    return o ? (o.degraded ? '⚠ 衰减' : '✅ 泛化') : '-'
  })])
  rows.push(['稳健性', ...compareItems.value.map((i) => {
    const s = i.result.segment_robustness
    return s ? (s.overfit_likely ? '⚠ 过拟合' : '✅ 稳健') : '-'
  })])
  const csv = '\uFEFF' + rows.map((r) => r.join(',')).join('\n')
  try {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'easy_tdx_compare_' + new Date().toISOString().slice(0, 10) + '.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    compareCsvMsg.value = '✓ 已导出对比 CSV'
  } catch {
    compareCsvMsg.value = '导出失败（浏览器权限）'
  }
  setTimeout(() => { compareCsvMsg.value = '' }, 2500)
}
// V275: 对比结果复制 JSON（机器可读，Agent/脚本友好，与全站 JSON 系列对齐）
const compareJsonMsg = ref('')
async function copyCompareJson() {
  if (compareItems.value.length < 2) return
  const payload = {
    generated_at: new Date().toISOString(),
    items: compareItems.value.map((i) => ({
      label: i.label,
      performance: i.result.performance,
      model_trust: i.result.model_trust ?? null,
      signal_accuracy: i.result.signal_accuracy ?? null,
      segment_robustness: i.result.segment_robustness ?? null,
      out_of_sample: i.result.out_of_sample ?? null,
    })),
  }
  const json = JSON.stringify(payload, null, 2)
  try {
    await navigator.clipboard.writeText(json)
    compareJsonMsg.value = '✓ 已复制对比 JSON'
  } catch {
    compareJsonMsg.value = '复制失败（浏览器权限）'
  }
  setTimeout(() => { compareJsonMsg.value = '' }, 2500)
}
</script>

<template>
  <div class="compare-view">
    <aside class="config-panel">
      <section class="panel-section">
        <h3>选择对比任务</h3>
        <button class="refresh-btn" :disabled="loading" @click="loadTasks">
          {{ loading ? '加载中…' : '刷新列表' }}
        </button>
        <p class="hint">勾选 2-4 个已完成的回测任务进行对比：</p>
        <div v-if="taskList.length === 0" class="empty">暂无已完成的任务</div>
        <div v-for="t in taskList" :key="t.task_id" class="task-item">
          <label class="check">
            <input
              type="checkbox"
              :checked="selectedIds.has(t.task_id)"
              :disabled="!selectedIds.has(t.task_id) && selectedIds.size >= 4"
              @change="toggle(t.task_id)"
            />
            <span class="task-desc">{{ t.description || t.task_id.slice(0, 8) }}</span>
          </label>
          <span class="task-meta">{{ t.elapsed.toFixed(1) }}s</span>
        </div>
      </section>
    </aside>

    <main class="report-panel">
      <div v-if="error" class="error-banner">⚠ {{ error }}</div>

      <div v-if="compareItems.length < 2" class="placeholder">
        <p>勾选至少 2 个任务进行对比</p>
      </div>

      <div v-else class="report-content">
        <section class="report-section">
          <h3>净值曲线对比（归一化）</h3>
          <CompareChart :items="compareItems" />
        </section>

        <section class="report-section">
          <h3>指标对比
            <button class="ghost small" @click="exportCompareCsv">📊 导出 CSV</button>
            <button class="ghost small" @click="copyCompareJson">⚙ 复制 JSON</button>
            <span v-if="compareCsvMsg" class="save-msg">{{ compareCsvMsg }}</span>
            <span v-if="compareJsonMsg" class="save-msg">{{ compareJsonMsg }}</span>
          </h3>
          <CompareTable :items="compareItems" />
        </section>
      </div>
    </main>
  </div>
</template>

<style scoped>
.compare-view {
  display: flex;
  height: 100%;
}
.config-panel {
  width: 320px;
  flex-shrink: 0;
  background: var(--bg-panel);
  border-right: 1px solid var(--border);
  padding: 16px;
  overflow-y: auto;
}
.panel-section h3 {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 12px;
}
.refresh-btn {
  width: 100%;
  margin-bottom: 12px;
}
.hint {
  color: var(--text-muted);
  font-size: 12px;
  margin-bottom: 10px;
}
.empty {
  color: var(--text-dim);
  font-size: 13px;
  padding: 16px 0;
}
.task-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
}
.check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.check input[type='checkbox'] {
  width: auto;
}
.task-desc {
  color: var(--text);
  font-family: var(--font-mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}
.task-meta {
  color: var(--text-dim);
  font-size: 11px;
  flex-shrink: 0;
}
.report-panel {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}
.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-dim);
}
.error-banner {
  background: rgba(239, 65, 70, 0.12);
  border: 1px solid var(--up);
  color: var(--up);
  padding: 10px 14px;
  border-radius: var(--radius);
  margin-bottom: 16px;
  font-size: 13px;
}
.report-section {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  margin-bottom: 16px;
}
.report-section h3 {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 12px;
}
</style>
