<script setup lang="ts">
// 今日可操作（V717）：选股池 + 批量择时 + 四季仓位聚合的一屏决策看板。
// 后台聚合任务（选股→逐票择时→四季→行动榜），进度条 + 按可操作性排序，
// 点击任意标的在同一屏下钻缠论图。
import { computed, ref } from 'vue'
import ChanlunChart from '../components/ChanlunChart.vue'
import {
  formatError,
  stockPickDashboardAsync,
  stockPickDashboardTask,
  type DashboardAction,
  type DashboardResult,
  type SeasonInfo,
} from '../api'

const selectDate = ref(new Date().toISOString().slice(0, 10))
const poolScope = ref<'pool' | 'full'>('pool')
const timeN = ref(20)
const recursionDepth = ref(2)
const loading = ref(false)
const error = ref('')
const progress = ref<number | null>(null)
const progressNote = ref('')
const result = ref<DashboardResult | null>(null)
const selected = ref<DashboardAction | null>(null)

const season = computed<SeasonInfo | null>(() => result.value?.season ?? null)
const summary = computed(() => result.value?.summary)

const categoryLabel: Record<string, string> = {
  tree: '🌳 树',
  grain: '🌾 粮',
  vegetable: '🥬 菜',
}

const actionClass = (a: string): string =>
  a === '买入' ? 'row-buy' : a === '卖出' ? 'row-sell' : ''

async function runDashboard() {
  error.value = ''
  result.value = null
  selected.value = null
  progress.value = null
  loading.value = true
  try {
    const { task_id } = await stockPickDashboardAsync({
      date: selectDate.value,
      pool_scope: poolScope.value,
      top_n: 50,
      time_n: timeN.value,
      recursion_depth: recursionDepth.value,
    })
    for (;;) {
      const st = await stockPickDashboardTask(task_id)
      progress.value = st.progress ?? null
      progressNote.value = st.progress_note ?? ''
      if (st.status === 'done') {
        result.value = (st.result ?? null) as DashboardResult | null
        break
      }
      if (st.status === 'failed') throw new Error(st.error ?? '看板任务失败')
      await new Promise((r) => setTimeout(r, 800))
    }
  } catch (e) {
    error.value = formatError(e)
  } finally {
    loading.value = false
  }
}

function pickRow(row: DashboardAction) {
  selected.value = selected.value?.symbol === row.symbol ? null : row
}
</script>

<template>
  <section class="today-view">
    <h2>今日可操作（选股池 → 批量择时 → 四季仓位）</h2>

    <div class="controls">
      <label>
        目标日期
        <input v-model="selectDate" type="date" />
      </label>
      <label>
        择时数量
        <select v-model.number="timeN">
          <option :value="10">10</option>
          <option :value="20">20</option>
          <option :value="30">30</option>
        </select>
      </label>
      <label>
        数据范围
        <select v-model="poolScope">
          <option value="pool">自选池/热门池</option>
          <option value="full">全市场扫描</option>
        </select>
      </label>
      <button class="primary" :disabled="loading" @click="runDashboard">
        {{ loading ? '生成中…' : '生成今日看板' }}
      </button>
    </div>

    <div v-if="loading && progress !== null" class="scan-progress">
      <div class="scan-progress-bar" :style="{ width: `${progress}%` }"></div>
      <span class="scan-progress-text">{{ Math.round(progress) }}% {{ progressNote }}</span>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <template v-if="result">
      <div v-if="season" class="season-banner" :style="{ borderColor: season.color ?? '#4ade80' }">
        <div class="season-head">
          <strong :style="{ color: season.color ?? '#4ade80' }">{{ season.label }}</strong>
          <span v-if="season.position_range" class="season-pos"
            >建议仓位 {{ season.position_range[0] }}%~{{ season.position_range[1] }}%</span
          >
        </div>
        <p v-if="season.description">{{ season.description }}</p>
        <p v-if="season.strategy" class="season-strategy">策略：{{ season.strategy }}</p>
      </div>

      <div v-if="summary" class="summary-bar">
        <div class="summary-item">
          <span class="summary-label">买入信号</span>
          <span class="summary-value buy">{{ summary.buy }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">卖出信号</span>
          <span class="summary-value sell">{{ summary.sell }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">观望</span>
          <span class="summary-value">{{ summary.wait }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">已择时/池内</span>
          <span class="summary-value">{{ summary.timed }}/{{ summary.pool }}</span>
        </div>
      </div>

      <div class="actions-panel">
        <h3>行动榜（按可操作性排序）</h3>
        <table v-if="(result.actions ?? []).length">
          <thead>
            <tr>
              <th>标的</th>
              <th>分类</th>
              <th>建议</th>
              <th>信号</th>
              <th>置信</th>
              <th>历史胜率</th>
              <th>递归</th>
              <th>入场</th>
              <th>止损</th>
              <th>目标</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in result.actions"
              :key="row.symbol"
              :class="[actionClass(row.action), { active: selected?.symbol === row.symbol }]"
            >
              <td class="symbol-cell">{{ row.symbol }}</td>
              <td>{{ categoryLabel[row.category ?? ''] ?? row.category ?? '—' }}</td>
              <td class="action-cell">{{ row.action }}</td>
              <td>{{ row.verdict?.signal ?? '—' }}</td>
              <td>{{ Math.round(row.confidence * 100) }}%</td>
              <td :class="{ ok: row.top_hit_good }">{{ row.top_hit_label ?? '—' }}</td>
              <td :class="{ ok: row.alignLabel === '同向', warn: row.alignLabel === '背离' }">
                {{ row.alignLabel }}
              </td>
              <td>{{ row.novice_advice?.entry ?? '—' }}</td>
              <td>{{ row.novice_advice?.stop ?? '—' }}</td>
              <td>{{ row.novice_advice?.target ?? '—' }}</td>
              <td><button class="ghost" @click="pickRow(row)">图表</button></td>
            </tr>
          </tbody>
        </table>
        <p v-else class="hint">该日期暂无可操作的标的（或数据不足），换个日期/池试试。</p>
      </div>

      <div v-if="selected" class="detail-panel">
        <h3>{{ selected.symbol }} 缠论图</h3>
        <p v-if="selected.novice_advice?.explanation" class="hint">
          {{ selected.novice_advice.explanation }}
        </p>
        <ChanlunChart
          v-if="(selected.bars ?? []).length"
          :bars="(selected.bars as any) ?? []"
          :bis="(selected.bis as any) ?? []"
          :xds="(selected.xds as any) ?? []"
          :zss="(selected.zss as any) ?? []"
          :mmds="(selected.mmds as any) ?? []"
          :fxs="(selected.fractals as any) ?? []"
          :bcs="(selected.bcs as any) ?? []"
          :macd="(selected.macd as any) ?? undefined"
          frequency="daily"
          compact
        />
        <p v-else class="hint">该标的无足够 K 线数据。</p>
      </div>
    </template>
    <p v-else-if="!loading && !error" class="hint">
      选择日期后点击「生成今日看板」，一屏聚合选股池、批量择时与四季仓位建议。
    </p>
  </section>
</template>

<style scoped>
.today-view {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.controls {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}
.scan-progress {
  display: flex;
  align-items: center;
  gap: 8px;
}
.scan-progress-bar {
  height: 6px;
  min-width: 4px;
  border-radius: 3px;
  background: linear-gradient(90deg, #60b4ff, #22c55e);
  transition: width 0.4s ease;
}
.scan-progress-text {
  font-size: 12px;
  color: #94a3b8;
  white-space: nowrap;
}
.season-banner {
  border: 1px solid #4ade80;
  border-radius: 10px;
  padding: 10px 12px;
  background: rgba(74, 222, 128, 0.06);
}
.season-banner p {
  margin: 6px 0 0;
  font-size: 12px;
  color: #94a3b8;
}
.season-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.season-pos {
  font-size: 12px;
  color: #e2e8f0;
}
.season-strategy {
  color: #cbd5e1;
}
.summary-bar {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
}
.summary-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.summary-label {
  font-size: 11px;
  color: #94a3b8;
}
.summary-value {
  font-size: 18px;
  font-weight: 700;
  color: #e2e8f0;
}
.summary-value.buy {
  color: #22c55e;
}
.summary-value.sell {
  color: #f87171;
}
.actions-panel table,
.detail-panel {
  width: 100%;
}
.actions-panel table {
  font-size: 12px;
  border-collapse: collapse;
}
.actions-panel th {
  color: #94a3b8;
  font-weight: 500;
  text-align: left;
  padding: 4px 6px;
}
.actions-panel td {
  padding: 5px 6px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.actions-panel .symbol-cell {
  font-weight: 600;
  color: #e2e8f0;
}
.actions-panel .row-buy .symbol-cell {
  color: #22c55e;
}
.actions-panel .row-sell .symbol-cell {
  color: #f87171;
}
.actions-panel .action-cell {
  font-weight: 600;
}
.actions-panel .row-buy .action-cell {
  color: #22c55e;
}
.actions-panel .row-sell .action-cell {
  color: #f87171;
}
.actions-panel tr.active td {
  background: rgba(96, 180, 255, 0.08);
}
.ok {
  color: #22c55e;
  font-weight: 600;
}
.warn {
  color: #f59e0b;
  font-weight: 600;
}
.hint {
  color: var(--text-dim);
}
.error {
  color: #f87171;
}
</style>
