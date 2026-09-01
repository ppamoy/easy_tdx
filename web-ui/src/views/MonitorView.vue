<script setup lang="ts">
// 信号监控视图：订阅一批股票，实时检查高置信度缠论买卖点信号。

import { computed, onMounted, onUnmounted, ref } from 'vue'
import { fetchBars, formatError, saveStrategy } from '../api'

interface MonitoredStock {
  market: string
  code: string
}

interface MonitorTask {
  task_id: string
  stocks: MonitoredStock[]
  category: string
  threshold: number
  last_check: number
  running: boolean
}

interface Signal {
  stock: string
  type: string
  date: string | null
  confidence: number
  msg: string
}

const stocks = ref<MonitoredStock[]>([
  { market: 'SZ', code: '000001' },
  { market: 'SH', code: '600519' },
])

// 从 localStorage 加载用户自定义的监控股票
const _savedStocks = localStorage.getItem('easy_tdx_monitor_stocks')
if (_savedStocks) {
  try {
    stocks.value = JSON.parse(_savedStocks)
  } catch {
    // 忽略解析错误
  }
}

// 从 ChanlunView 快速加入的 watchlist
interface WatchListItem {
  code: string
  market: string
  direction: 'buy' | 'sell' | 'unknown'
  signal_type: string
  timestamp: number
}
const watchList = ref<WatchListItem[]>([])

function loadWatchList() {
  try {
    const raw = localStorage.getItem('easy_tdx_watchlist')
    if (raw) watchList.value = JSON.parse(raw)
  } catch {
    // ignore
  }
}

function addFromWatchlist(item: WatchListItem) {
  const exists = stocks.value.some(s => s.code === item.code)
  if (!exists) {
    stocks.value.push({ market: item.market, code: item.code })
    saveStocks()
  }
}

function removeWatchlist(index: number) {
  watchList.value.splice(index, 1)
  try {
    localStorage.setItem('easy_tdx_watchlist', JSON.stringify(watchList.value))
  } catch { /* ignore */ }
}

// ── 自选股历史信号准确度（V107：复用 /chanlun/analyze 的 signal_accuracy） ──
interface WatchAccuracy {
  loading: boolean
  error: string
  summary: string
  ranking: Array<{
    type: string
    direction: string
    signals: number
    hit_rate: number
    excess_hit_rate: number
    avg_return: number
    verdict: string
  }>
}
const watchAccuracy = ref<Record<string, WatchAccuracy>>({})

async function toggleWatchAccuracy(item: WatchListItem) {
  const key = item.market + item.code
  const cur = watchAccuracy.value[key]
  if (cur && !cur.loading) {
    // 已有结果则再次点击收起
    delete watchAccuracy.value[key]
    watchAccuracy.value = { ...watchAccuracy.value }
    return
  }
  watchAccuracy.value[key] = { loading: true, error: '', summary: '', ranking: [] }
  try {
    const resp = await fetch('/api/v1/chanlun/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        market: item.market,
        code: item.code,
        category: 'DAY',
        count: 300,
      }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error((err as { detail?: string }).detail ?? ('HTTP ' + resp.status))
    }
    const data = await resp.json()
    const sa = data.signal_accuracy
    watchAccuracy.value[key] = {
      loading: false,
      error: sa?.ranking?.length ? '' : '该股无足够历史信号，无法评估',
      summary: sa?.summary ?? '',
      ranking: sa?.ranking ?? [],
    }
  } catch (e) {
    watchAccuracy.value[key] = {
      loading: false,
      error: formatError(e),
      summary: '',
      ranking: [],
    }
  }
}

function accPct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  return (v * 100).toFixed(0) + '%'
}
function accSigned(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  const sign = v >= 0 ? '+' : ''
  return sign + (v * 100).toFixed(1) + '%'
}


// ── 主监控列表每股历史信号准确度（V121：复用 /chanlun/analyze signal_accuracy） ──
const stockAcc = ref<Record<string, WatchAccuracy>>({})

async function toggleStockAcc(s: MonitoredStock) {
  const key = s.market + s.code
  const cur = stockAcc.value[key]
  if (cur && !cur.loading) {
    delete stockAcc.value[key]
    stockAcc.value = { ...stockAcc.value }
    return
  }
  stockAcc.value[key] = { loading: true, error: '', summary: '', ranking: [] }
  try {
    const resp = await fetch('/api/v1/chanlun/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        market: s.market,
        code: s.code,
        category: 'DAY',
        count: 300,
      }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error((err as { detail?: string }).detail ?? ('HTTP ' + resp.status))
    }
    const data = await resp.json()
    const sa = data.signal_accuracy
    stockAcc.value[key] = {
      loading: false,
      error: sa?.ranking?.length ? '' : '该股无足够历史信号，无法评估',
      summary: sa?.summary ?? '',
      ranking: sa?.ranking ?? [],
    }
  } catch (e) {
    stockAcc.value[key] = {
      loading: false,
      error: formatError(e),
      summary: '',
      ranking: [],
    }
  }
}

function saveStocks() {
  localStorage.setItem('easy_tdx_monitor_stocks', JSON.stringify(stocks.value))
}
const newMarket = ref('SZ')
const newCode = ref('')
const category = ref('DAY')
const threshold = ref(0.7)
const tasks = ref<MonitorTask[]>([])
const loading = ref(false)
const error = ref('')
const newSignals = ref<Signal[]>([])
let checkInterval: number | null = null

function addStock() {
  if (!newCode.value.match(/^\d{6}$/)) return
  const exists = stocks.value.some(s => s.code === newCode.value)
  if (exists) return
  stocks.value.push({ market: newMarket.value, code: newCode.value })
  newCode.value = ''
  saveStocks()
}

function removeStock(index: number) {
  stocks.value.splice(index, 1)
  saveStocks()
}

async function createMonitor() {
  if (stocks.value.length === 0) {
    error.value = '请至少添加一只股票'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const resp = await fetch('/api/v1/monitor/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        stocks: stocks.value,
        category: category.value,
        confidence_threshold: threshold.value,
      }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error((err as { detail?: string }).detail ?? `HTTP ${resp.status}`)
    }
    const data = await resp.json()
    tasks.value.push({
      task_id: data.task_id,
      stocks: stocks.value,
      category: category.value,
      threshold: threshold.value,
      last_check: 0,
      running: false,
    })
    newSignals.value = []
    startAutoCheck(data.task_id)
  } catch (e) {
    error.value = formatError(e)
  } finally {
    loading.value = false
  }
}

function startAutoCheck(taskId: string) {
  if (checkInterval !== null) clearInterval(checkInterval)
  // 每30秒自动检查一次
  checkInterval = window.setInterval(() => checkSignals(taskId), 30000)
}

async function checkSignals(taskId: string) {
  try {
    const resp = await fetch(`/api/v1/monitor/${taskId}/check`, { method: 'POST' })
    if (!resp.ok) return
    const data = await resp.json()
    if (data.new_signals && data.new_signals.length > 0) {
      newSignals.value = [...data.new_signals, ...newSignals.value].slice(0, 20)
      // 浏览器通知
      if (Notification.permission === 'granted') {
        new Notification('easy-tdx 信号提醒', {
          body: `${data.new_signals.length} 个新信号`,
        })
      }
    }
    // 更新任务状态
    const task = tasks.value.find(t => t.task_id === taskId)
    if (task) task.last_check = Date.now() / 1000
  } catch {
    // 静默失败
  }
}

async function loadTasks() {
  try {
    const resp = await fetch('/api/v1/monitor/list')
    if (!resp.ok) return
    const data = await resp.json()
    tasks.value = data.tasks ?? []
  } catch {
    // 静默失败
  }
}

async function stopTask(taskId: string) {
  await fetch(`/api/v1/monitor/${taskId}/stop`, { method: 'POST' })
  tasks.value = tasks.value.filter(t => t.task_id !== taskId)
  if (checkInterval !== null) {
    clearInterval(checkInterval)
    checkInterval = null
  }
}

function fmtTime(ts: number): string {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  const now = new Date()
  const diff = (now.getTime() - d.getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  return d.toLocaleString()
}

const MMD_COLORS: Record<string, string> = {
  '1buy': '#22c55e', '2buy': '#4ade80', '3buy': '#86efac',
  '1sell': '#ef4444', '2sell': '#f87171', '3sell': '#fca5a5',
}
// V143: 批量验证监控股（对已选监控标的跑所选策略，按可信度排名）
const batchStrategy = ref('ma_cross')
const batchStrategyLabel = ref('双均线交叉')
const strategyOptions = ref<Array<{ name: string; label: string; params: Array<{ name: string; default?: number | string | boolean }> }>>([])
interface MonBatchRow {
  symbol: string; market: string; code: string
  total_return: number | null; win_rate: number | null; hit_rate: number | null
  excess_hit_rate: number | null; trust_score: number | null; trust_grade: string | null
  trades: number | null
  // V180: 该股样本外验证结论
  oos_degraded: boolean | null; oos_verdict: string
}
const monBatchRows = ref<MonBatchRow[]>([])
const monBatchLoading = ref(false)
const monBatchMsg = ref('')
// V219: 监控批量验证结果持久化（与回测页 V217 对齐）
const MON_BATCH_KEY = 'easy_tdx_mon_batch_verify_last'
const lastMonBatchAt = ref('')
function saveMonBatchPersist() {
  if (!monBatchRows.value.length) return
  try {
    localStorage.setItem(MON_BATCH_KEY, JSON.stringify({
      rows: monBatchRows.value,
      strategy: batchStrategy.value,
      strategy_label: batchStrategyLabel.value || batchStrategy.value,
      at: new Date().toISOString(),
    }))
  } catch { /* localStorage 不可用忽略 */ }
}
function restoreMonBatchPersist() {
  try {
    const raw = localStorage.getItem(MON_BATCH_KEY)
    if (!raw) return
    const data = JSON.parse(raw)
    if (Array.isArray(data.rows) && data.rows.length) {
      monBatchRows.value = data.rows
      lastMonBatchAt.value = data.at || ''
      monBatchMsg.value = '已恢复上次监控批量验证（' + (data.strategy_label || '') + '）'
    }
  } catch { /* 解析失败忽略 */ }
}

async function loadMonitorStrategies() {
  if (strategyOptions.value.length) return
  try {
    const resp = await fetch('/api/v1/backtest/strategies')
    if (!resp.ok) return
    const data = await resp.json()
    strategyOptions.value = (data.strategies ?? []).map((s: any) => ({
      name: s.name, label: s.label, params: s.params ?? [],
    }))
    if (strategyOptions.value.length) batchStrategy.value = strategyOptions.value[0].name
  } catch { /* ignore */ }
}

function monBatchDefaults(): Record<string, number | string | boolean> {
  const opt = strategyOptions.value.find((s) => s.name === batchStrategy.value)
  const out: Record<string, number | string | boolean> = {}
  for (const p of opt?.params ?? []) {
    if (p.default !== undefined) out[p.name] = p.default
  }
  return out
}

async function runMonitorBatchVerify() {
  if (stocks.value.length === 0 || monBatchLoading.value) return
  monBatchLoading.value = true
  monBatchMsg.value = ''
  monBatchRows.value = []
  const defaultParams = monBatchDefaults()
  try {
    const rows: typeof monBatchRows.value = []
    for (const s of stocks.value.slice(0, 12)) {
      try {
        const bars = await fetchBars(s.market, s.code, 'DAY', undefined, undefined, 500)
        if (bars.length < 30) continue
        const resp = await fetch('/api/v1/backtest/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            strategy: batchStrategy.value,
            params: defaultParams,
            cash: 1000000,
            out_of_sample: true,
            oos_train_ratio: 0.7,
            ohlcv: bars,
          }),
        })
        if (!resp.ok) continue
        const result = await resp.json()
        const perf = result.performance
        const h5 = result.signal_accuracy?.buy?.horizons?.['5']
        const oos = result.out_of_sample
        rows.push({
          symbol: s.market + s.code,
          market: s.market,
          code: s.code,
          total_return: perf.total_return ?? null,
          win_rate: perf.win_rate ?? null,
          hit_rate: h5 && h5.count > 0 ? h5.hit_rate : null,
          excess_hit_rate: h5 && h5.count > 0 ? h5.excess_hit_rate : null,
          trust_score: result.model_trust?.score ?? null,
          trust_grade: result.model_trust?.grade ?? null,
          trades: perf.total_trades ?? null,
          oos_degraded: oos?.degraded ?? null,
          oos_verdict: oos?.verdict ?? '',
        })
      } catch { /* 单只失败跳过 */ }
    }
    rows.sort((a, b) => (b.trust_score ?? -1) - (a.trust_score ?? -1))
    monBatchRows.value = rows
    lastMonBatchAt.value = new Date().toISOString()
    saveMonBatchPersist()
    if (rows.length === 0) monBatchMsg.value = '批量验证无结果（行情取数失败或数据不足）'
  } catch (e) {
    monBatchMsg.value = '批量验证失败：' + formatError(e)
  } finally {
    monBatchLoading.value = false
  }
}
function monPct(v: number | null | undefined): string {
  return v === null || v === undefined || !Number.isFinite(v) ? '-' : (v * 100).toFixed(1) + '%'
}
function monTrust(r: typeof monBatchRows.value[number]): string {
  if (r.trust_score === null || r.trust_score === undefined) return '-'
  return Math.round(r.trust_score) + ' ' + (r.trust_grade ?? '')
}
// V180: 样本外列辅助
function monOosLabel(r: typeof monBatchRows.value[number]): string {
  if (r.oos_degraded === null || r.oos_degraded === undefined) return '-'
  return r.oos_degraded ? '⚠衰减' : '✅泛化'
}
function monOosCls(r: typeof monBatchRows.value[number]): string {
  if (r.oos_degraded === null || r.oos_degraded === undefined) return ''
  return r.oos_degraded ? 'neg' : 'pos'
}
function monOosTitle(r: typeof monBatchRows.value[number]): string {
  return r.oos_verdict || ''
}
// V151: 监控批量验证排序方式（收益 / 可信度）
const monBatchSort = ref<'return' | 'trust'>('trust')
// V193: 仅看样本外稳健（过滤掉 oos_degraded=true 的监控股）
const monBatchOnlyRobust = ref(false)
const sortedMonBatchRows = computed(() => {
  const base = monBatchOnlyRobust.value
    ? monBatchRows.value.filter((r) => r.oos_degraded === false)
    : monBatchRows.value
  if (!base.length || monBatchSort.value === 'trust') return base
  return [...base].sort((a, b) => (b.total_return ?? -Infinity) - (a.total_return ?? -Infinity))
})
// V145: 监控批量验证导出（复制排名）与入库（保存为组合策略）
const monBatchCopyMsg = ref('')
const monBatchSaving = ref(false)
const monBatchSaveMsg = ref('')
function copyMonBatchRanking() {
  if (monBatchRows.value.length === 0) return
  const lines: string[] = []
  lines.push('# easy-tdx 监控批量验证（' + (batchStrategyLabel.value || batchStrategy.value) + '）')
  lines.push('')
  lines.push('| 排名 | 标的 | 总收益 | 胜率 | 5根命中率 | 超额命中率 | 可信度 | 样本外 | 交易数 |')
  lines.push('| --- | --- | --- | --- | --- | --- | --- | --- | --- |')
  monBatchRows.value.forEach((r, i) => {
    lines.push(
      '| ' + (i + 1) + ' | ' + r.symbol + ' | ' + monPct(r.total_return) +
      ' | ' + monPct(r.win_rate) + ' | ' + monPct(r.hit_rate) + ' | ' + monPct(r.excess_hit_rate) +
      ' | ' + monTrust(r) + ' | ' + monOosLabel(r) + ' | ' + (r.trades ?? '-') + ' |',
    )
  })
  lines.push('')
  lines.push('方法：对已选监控标的（最多 12 只）用所选策略独立回测（最近 500 根日线），按模型可信度（V101）降序排名。')
  const text = lines.join('\n')
  const doCopy = async () => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      const ta = document.createElement('textarea')
      ta.value = text
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    monBatchCopyMsg.value = '✓ 已复制批量验证排名'
    setTimeout(() => { monBatchCopyMsg.value = '' }, 2500)
  }
  void doCopy()
}
// V166: 监控批量验证 JSON 导出（机器可读，Agent/脚本友好，与 V153/V157/V158/V162 对齐）
const monBatchJsonCopyMsg = ref('')
async function copyMonBatchJson() {
  if (monBatchRows.value.length === 0) return
  const payload = {
    strategy: batchStrategy.value,
    strategy_label: batchStrategyLabel.value,
    generated_at: new Date().toISOString(),
    rows: monBatchRows.value.map((r, i) => ({ rank: i + 1, ...r })),
  }
  const json = JSON.stringify(payload, null, 2)
  try {
    await navigator.clipboard.writeText(json)
    monBatchJsonCopyMsg.value = '✓ 已复制批量验证 JSON'
  } catch {
    monBatchJsonCopyMsg.value = '复制失败（浏览器权限）'
  }
  setTimeout(() => { monBatchJsonCopyMsg.value = '' }, 2500)
}
async function saveMonBatchAsPortfolio() {
  if (monBatchRows.value.length === 0 || monBatchSaving.value) return
  monBatchSaving.value = true
  monBatchSaveMsg.value = ''
  try {
    // V203: 保存遵循「仅看样本外稳健」过滤——开启时只把筛选视图里的 ✅泛化 标的入库
    const visible = monBatchOnlyRobust.value
      ? monBatchRows.value.filter((r) => r.oos_degraded === false)
      : monBatchRows.value
    if (visible.length === 0) {
      monBatchSaveMsg.value = '没有样本外稳健的监控股可保存（请关闭「仅看样本外稳健」再试）'
      monBatchSaving.value = false
      setTimeout(() => { monBatchSaveMsg.value = '' }, 4000)
      return
    }
    const stocks = visible.map((r) => r.market + ':' + r.code)
    const avgTrust = visible.length
      ? visible.reduce((s, r) => s + (r.trust_score ?? 0), 0) / visible.length
      : 0
    // V190: 样本外聚合（逐只开启 out_of_sample 后统计衰减比例）
    const oosKnown = visible.filter((r) => r.oos_degraded !== null && r.oos_degraded !== undefined)
    const oosDegradedN = oosKnown.filter((r) => r.oos_degraded === true).length
    const oosRatio = oosKnown.length ? oosDegradedN / oosKnown.length : null
    const oosVerdict = oosKnown.length
      ? (oosRatio! < 0.5 ? '✅ ' + (oosKnown.length - oosDegradedN) + '/' + oosKnown.length + ' 只样本外稳健' : '⚠ ' + oosDegradedN + '/' + oosKnown.length + ' 只样本外衰减')
      : ''
    await saveStrategy({
      name: (batchStrategyLabel.value || batchStrategy.value) + ' · 监控验证' + stocks.length + '只',
      kind: 'portfolio',
      strategy: batchStrategy.value,
      strategy_label: batchStrategyLabel.value,
      params: monBatchDefaults(),
      context: {
        stocks,
        category: 'DAY',
      },
      trade_config: { cash: 1_000_000, execution: 'next_open' },
      snapshot: {
        total_stocks: stocks.length,
        avg_trust_score: avgTrust,
        avg_oos_degraded: oosRatio,
        oos_verdict: oosVerdict,
        source: 'batch-verify-monitor',
        saved_at: new Date().toISOString().slice(0, 10),
      },
      tags: ['监控验证'],
      notes: '由信号监控页批量验证监控股（按模型可信度排名）生成，可在组合回测页载入复跑。',
    })
    monBatchSaveMsg.value = '✓ 已保存为组合策略，可在「策略库」载入复跑'
    setTimeout(() => { monBatchSaveMsg.value = '' }, 4000)
  } catch (e) {
    monBatchSaveMsg.value = '保存失败：' + formatError(e)
  } finally {
    monBatchSaving.value = false
  }
}

onMounted(async () => {
  loadWatchList()
  await loadTasks()
  await loadMonitorStrategies()
  // V219: 恢复上次监控批量验证结果（如有）
  restoreMonBatchPersist()
  // 请求通知权限
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission()
  }
})

onUnmounted(() => {
  if (checkInterval !== null) clearInterval(checkInterval)
})
</script>

<template>
  <div class="monitor-view">
    <!-- 添加股票 -->
    <div class="config-bar">
      <div class="field-group">
        <label>市场</label>
        <select v-model="newMarket">
          <option value="SZ">深市</option>
          <option value="SH">沪市</option>
        </select>
      </div>
      <div class="field-group">
        <label>代码</label>
        <input v-model="newCode" type="text" placeholder="6位代码" maxlength="6"
               @keyup.enter="addStock" />
      </div>
      <button class="ghost" @click="addStock">+ 添加</button>

      <div class="divider"></div>

      <div class="field-group">
        <label>周期</label>
        <select v-model="category">
          <option value="DAY">日线</option>
          <option value="MIN_30">30分钟</option>
          <option value="MIN_60">60分钟</option>
        </select>
      </div>
      <div class="field-group">
        <label>置信度阈值</label>
        <input v-model.number="threshold" type="range" min="0.5" max="0.95" step="0.05" />
        <span>{{ (threshold * 100).toFixed(0) }}%</span>
      </div>

      <button class="primary" :disabled="loading || stocks.length === 0" @click="createMonitor">
        {{ loading ? '创建中…' : '开始监控' }}
      </button>
    </div>

    <!-- 股票列表 -->
    <div v-if="stocks.length > 0" class="stock-list">
      <span class="stock-count">已选 {{ stocks.length }} 只</span>
      <div class="stock-tags">
        <span v-for="(s, i) in stocks" :key="s.code" class="stock-tag">
          {{ s.market }}{{ s.code }}
          <button class="acc-mini" :class="{ active: stockAcc[s.market + s.code] }" title="历史信号准确度" @click="toggleStockAcc(s)">🎯</button>
          <button class="remove-btn" @click="removeStock(i)">×</button>
        </span>
      </div>
      <!-- V121: 主监控列表每股历史信号准确度面板 -->
      <template v-for="(s, i) in stocks" :key="'stock-acc-' + i">
        <div v-if="stockAcc[s.market + s.code]" class="watch-acc-panel stock-acc">
          <template v-if="stockAcc[s.market + s.code].loading">
            <span class="dim">分析 {{ s.market }}{{ s.code }} 历史信号命中率…</span>
          </template>
          <template v-else-if="stockAcc[s.market + s.code].error">
            <span class="neg">⚠ {{ stockAcc[s.market + s.code].error }}</span>
          </template>
          <template v-else>
            <div v-if="stockAcc[s.market + s.code].summary" class="acc-summary">
              <b>{{ s.market }}{{ s.code }}</b>：{{ stockAcc[s.market + s.code].summary }}
            </div>
            <table class="acc-table">
              <thead><tr><th>信号类型</th><th>信号数</th><th>5根命中率</th><th>超额命中率</th><th>5根均值</th><th>结论</th></tr></thead>
              <tbody>
                <tr v-for="rank in stockAcc[s.market + s.code].ranking" :key="rank.type"
                    :style="{ color: MMD_COLORS[rank.type] ?? '#fff' }">
                  <td><strong>{{ rank.type }}</strong></td>
                  <td>{{ rank.signals }}</td>
                  <td>{{ accPct(rank.hit_rate) }}</td>
                  <td :class="rank.excess_hit_rate >= 0 ? 'pos' : 'neg'">{{ accSigned(rank.excess_hit_rate) }}</td>
                  <td :class="rank.avg_return >= 0 ? 'pos' : 'neg'">{{ accPct(rank.avg_return) }}</td>
                  <td class="dim verdict-cell">{{ rank.verdict }}</td>
                </tr>
              </tbody>
            </table>
          </template>
        </div>
      </template>
    </div>


    <!-- V143: 批量验证监控股（对已选标的跑所选策略，按可信度排名） -->
    <div v-if="stocks.length > 0" class="mon-batch-bar">
      <select v-model="batchStrategy" class="strategy-select"
              @change="batchStrategyLabel = strategyOptions.find(s => s.name === batchStrategy)?.label ?? batchStrategy">
        <option v-for="s in strategyOptions" :key="s.name" :value="s.name">{{ s.label }}</option>
      </select>
      <button class="ghost small" :disabled="monBatchLoading || strategyOptions.length === 0" @click="runMonitorBatchVerify">
        {{ monBatchLoading ? '批量验证中…' : '🧪 批量验证监控股（按可信度排名）' }}
      </button>
      <span v-if="monBatchMsg" class="mon-batch-msg">{{ monBatchMsg }}</span>
    </div>
    <div v-if="monBatchRows.length > 0" class="mon-batch-panel">
      <div class="mon-batch-head">
        <h4>🧪 批量验证监控股：{{ batchStrategyLabel }}
          <span v-if="lastMonBatchAt" class="mon-batch-at" :title="'上次验证时间'">🕒 {{ new Date(lastMonBatchAt).toLocaleString() }}</span>
        </h4>
        <div class="mon-batch-actions">
          <button class="ghost small" :class="{ active: monBatchSort === 'return' }" @click="monBatchSort = 'return'">按收益</button>
          <button class="ghost small" :class="{ active: monBatchSort === 'trust' }" @click="monBatchSort = 'trust'">按可信度</button>
          <button class="ghost small" :class="{ active: monBatchOnlyRobust }" :title="'仅保留样本外 ✅泛化 的监控股（当前 ' + monBatchRows.filter((r: MonBatchRow) => r.oos_degraded === false).length + ' 只）'" @click="monBatchOnlyRobust = !monBatchOnlyRobust">
            ✅ 仅看样本外稳健
          </button>
          <button class="ghost small" @click="copyMonBatchRanking">📋 复制排名</button>
          <button class="ghost small" @click="copyMonBatchJson">⚙ 复制 JSON</button>
          <button class="ghost small" :disabled="monBatchSaving" @click="saveMonBatchAsPortfolio">
            {{ monBatchSaving ? '保存中…' : '💾 保存为组合策略' }}
          </button>
          <span v-if="monBatchCopyMsg" class="save-msg">{{ monBatchCopyMsg }}</span>
          <span v-if="monBatchJsonCopyMsg" class="save-msg">{{ monBatchJsonCopyMsg }}</span>
          <span v-if="monBatchSaveMsg" class="save-msg" :class="{ err: monBatchSaveMsg.includes('失败') }">{{ monBatchSaveMsg }}</span>
        </div>
      </div>
      <table class="mon-batch-table">
        <thead>
          <tr><th>#</th><th>标的</th><th class="num">总收益</th><th class="num">胜率</th>
              <th class="num">5根命中率</th><th class="num">超额命中率</th><th class="num">可信度</th>
              <th class="num" title="训练段 vs 未见过数据">样本外</th><th class="num">交易数</th></tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in sortedMonBatchRows" :key="r.symbol">
            <td class="dim">{{ i + 1 }}</td>
            <td>{{ r.symbol }}</td>
            <td class="num" :class="(r.total_return ?? 0) >= 0 ? 'pos' : 'neg'">{{ monPct(r.total_return) }}</td>
            <td class="num">{{ monPct(r.win_rate) }}</td>
            <td class="num">{{ monPct(r.hit_rate) }}</td>
            <td class="num" :class="(r.excess_hit_rate ?? 0) >= 0 ? 'pos' : 'neg'">{{ monPct(r.excess_hit_rate) }}</td>
            <td class="num" :class="r.trust_grade === '高' ? 'pos' : r.trust_grade === '低' ? 'neg' : ''">{{ monTrust(r) }}</td>
            <td class="num" :class="monOosCls(r)" :title="monOosTitle(r)">{{ monOosLabel(r) }}</td>
            <td class="num">{{ r.trades ?? '-' }}</td>
          </tr>
        </tbody>
      </table>
      <p class="mon-batch-legend">对已选监控标的（最多 12 只）用所选策略独立回测（最近 500 根日线），按 V101 模型可信度降序排名——
        可信度 = 择时准确度 + 稳健性 + 绩效对比，用于挑「策略验证最可信」的监控标的。</p>
    </div>

    <!-- 快速加入的 watchlist -->
    <div v-if="watchList.length > 0" class="watchlist-section">
      <div class="watchlist-header">
        <span class="watchlist-title">📌 快速加入的信号</span>
        <span class="watchlist-count">{{ watchList.length }} 条</span>
      </div>
      <div class="watchlist-items">
        <template v-for="(item, i) in watchList" :key="'wl-' + i">
          <div class="watchlist-item">
            <span class="wl-symbol">{{ item.market }}{{ item.code }}</span>
            <span class="wl-type" :style="{ color: item.direction === 'buy' ? '#22c55e' : '#ef4444' }">
              {{ item.signal_type }}
            </span>
            <button class="ghost small" @click="addFromWatchlist(item)">+ 加入监控</button>
            <button class="ghost small" @click="toggleWatchAccuracy(item)">🎯 准确度</button>
            <button class="ghost small danger" @click="removeWatchlist(i)">删除</button>
          </div>
          <!-- V107: 自选股历史信号准确度面板 -->
          <div v-if="watchAccuracy[item.market + item.code]" class="watch-acc-panel">
            <template v-if="watchAccuracy[item.market + item.code].loading">
              <span class="dim">分析 {{ item.market }}{{ item.code }} 历史信号命中率…</span>
            </template>
            <template v-else-if="watchAccuracy[item.market + item.code].error">
              <span class="neg">⚠ {{ watchAccuracy[item.market + item.code].error }}</span>
            </template>
            <template v-else>
              <div v-if="watchAccuracy[item.market + item.code].summary" class="acc-summary">
                {{ watchAccuracy[item.market + item.code].summary }}
              </div>
              <table class="acc-table">
                <thead>
                  <tr>
                    <th>信号类型</th><th>信号数</th><th>5根命中率</th>
                    <th>超额命中率</th><th>5根均值</th><th>结论</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="rank in watchAccuracy[item.market + item.code].ranking" :key="rank.type"
                      :style="{ color: MMD_COLORS[rank.type] ?? '#fff' }">
                    <td><strong>{{ rank.type }}</strong></td>
                    <td>{{ rank.signals }}</td>
                    <td>{{ accPct(rank.hit_rate) }}</td>
                    <td :class="rank.excess_hit_rate >= 0 ? 'pos' : 'neg'">{{ accSigned(rank.excess_hit_rate) }}</td>
                    <td :class="rank.avg_return >= 0 ? 'pos' : 'neg'">{{ accPct(rank.avg_return) }}</td>
                    <td class="dim verdict-cell">{{ rank.verdict }}</td>
                  </tr>
                </tbody>
              </table>
              <p class="acc-legend">命中 = 买点后 5 根上涨 / 卖点后 5 根下跌；超额命中率 &gt; 0 说明该类型信号比随机择时更准。
                数据来自缠论分析接口对最近 300 根日线的历史回看。</p>
            </template>
          </div>
        </template>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="error-banner">{{ error }}</div>

    <!-- 新信号提醒 -->
    <div v-if="newSignals.length > 0" class="signals-panel">
      <div class="panel-header">
        <span class="panel-title">🔔 新信号（{{ newSignals.length }} 条）</span>
        <button class="ghost small" @click="newSignals = []">清除</button>
      </div>
      <div class="signal-items">
        <div v-for="(s, i) in newSignals" :key="i" class="signal-item"
             :style="{ borderLeftColor: MMD_COLORS[s.type] ?? '#fff' }">
          <span class="signal-type" :style="{ color: MMD_COLORS[s.type] ?? '#fff' }">{{ s.type }}</span>
          <span class="signal-stock">{{ s.stock }}</span>
          <span class="signal-date">{{ s.date ?? '-' }}</span>
          <span class="signal-conf">{{ (s.confidence * 100).toFixed(0) }}%</span>
          <span class="signal-msg">{{ s.msg }}</span>
        </div>
      </div>
    </div>

    <!-- 监控任务列表 -->
    <div v-if="tasks.length > 0" class="tasks-panel">
      <h3>监控任务</h3>
      <div class="task-list">
        <div v-for="task in tasks" :key="task.task_id" class="task-card">
          <div class="task-info">
            <span class="task-id">{{ task.task_id }}</span>
            <span class="task-stocks">{{ task.stocks.length }} 只股票</span>
            <span class="task-category">{{ task.category }}</span>
            <span class="task-threshold">≥{{ (task.threshold * 100).toFixed(0) }}%</span>
          </div>
          <div class="task-actions">
            <span class="task-last-check">上次检查: {{ fmtTime(task.last_check) }}</span>
            <button class="ghost small" @click="checkSignals(task.task_id)">立即检查</button>
            <button class="danger small" @click="stopTask(task.task_id)">停止</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!loading && tasks.length === 0 && !error" class="placeholder">
      <p>添加股票后点击「开始监控」</p>
      <p class="hint">系统将每30秒自动检查缠论买卖点信号，出现高置信度信号时通知</p>
    </div>
  </div>
</template>

<style scoped>
.monitor-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px 20px;
  height: 100%;
  overflow-y: auto;
}

.config-bar {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex-wrap: wrap;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 16px;
}

.divider {
  width: 1px;
  height: 32px;
  background: var(--border);
}

.field-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-group label {
  font-size: 11px;
  color: var(--text-muted);
}

.field-group input[type="text"] {
  width: 90px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 10px;
  font-size: 13px;
  color: var(--text);
}

.field-group input[type="range"] {
  width: 100px;
}

.field-group select {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 10px;
  font-size: 13px;
  color: var(--text);
}

.stock-list {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.stock-count {
  font-size: 12px;
  color: var(--text-muted);
}

.stock-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.stock-tag {
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(255,255,255,0.05);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 12px;
  font-family: var(--font-mono);
}

.remove-btn {
  background: none;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
  font-size: 14px;
  line-height: 1;
  padding: 0 2px;
}
.remove-btn:hover { color: var(--up); }

.error-banner {
  background: rgba(239, 65, 70, 0.12);
  border: 1px solid var(--up);
  color: var(--up);
  padding: 10px 14px;
  border-radius: var(--radius);
  font-size: 13px;
}

.signals-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 16px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.panel-title {
  font-size: 13px;
  font-weight: 600;
}

.signal-items {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.signal-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: rgba(255,255,255,0.02);
  border-radius: 4px;
  border-left: 3px solid;
  font-size: 12px;
}

.signal-type { font-weight: 700; min-width: 40px; }
.signal-stock { font-family: var(--font-mono); min-width: 80px; }
.signal-date { color: var(--text-muted); min-width: 80px; }
.signal-conf { font-weight: 600; min-width: 36px; }
.signal-msg { color: var(--text-dim); flex: 1; }

.tasks-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
}

.tasks-panel h3 {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 10px;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: rgba(255,255,255,0.02);
  border-radius: 6px;
  border: 1px solid var(--border);
  flex-wrap: wrap;
  gap: 8px;
}

.task-info {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.task-id {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
}

.task-stocks, .task-category, .task-threshold {
  font-size: 12px;
  color: var(--text);
}

.task-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.task-last-check {
  font-size: 11px;
  color: var(--text-dim);
}

.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--text-dim);
  gap: 8px;
}

.hint { font-size: 12px; opacity: 0.7; }

/* 快速加入的 watchlist */
.watchlist-section {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 16px;
}

.watchlist-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.watchlist-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.watchlist-count {
  font-size: 11px;
  color: var(--text-muted);
  background: rgba(255,255,255,0.05);
  padding: 2px 6px;
  border-radius: 4px;
}

.watchlist-items {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 150px;
  overflow-y: auto;
}

.watchlist-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: rgba(255,255,255,0.02);
  border-radius: 4px;
  font-size: 12px;
}

.wl-symbol {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--text);
  min-width: 80px;
}

.wl-type {
  font-weight: 600;
  min-width: 50px;
}

/* V107: 自选股历史信号准确度面板 */
.watch-acc-panel {
  padding: 10px 12px;
  background: rgba(255,255,255,0.03);
  border-radius: 6px;
  border: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.acc-summary {
  font-size: 12px;
  color: var(--text);
  line-height: 1.5;
}
.acc-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}
.acc-table th {
  text-align: left;
  padding: 4px 6px;
  border-bottom: 1px solid var(--border);
  color: var(--text-dim);
  font-weight: 500;
}
.acc-table td {
  padding: 3px 6px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  color: var(--text);
}
.acc-legend {
  font-size: 11px;
  color: var(--text-dim);
  line-height: 1.6;
  margin: 0;
}
.pos {
  color: var(--up);
}
.neg {
  color: var(--down);
}
.dim {
  color: var(--text-dim);
}
.verdict-cell {
  color: var(--text-muted) !important;
}

/* V121: 主监控列表每股历史信号准确度 */
.acc-mini {
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  padding: 0 2px;
  opacity: 0.7;
  border-radius: 3px;
}
.acc-mini:hover, .acc-mini.active {
  opacity: 1;
  background: rgba(255, 255, 255, 0.08);
}
.stock-acc {
  margin-top: 6px;
  margin-bottom: 2px;
}

/* V143: 批量验证监控股 */
.mon-batch-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 10px 0;
  flex-wrap: wrap;
}
.mon-batch-bar .strategy-select {
  max-width: 240px;
}
.mon-batch-msg {
  font-size: 12px;
  color: var(--warn, #f59e0b);
}
.mon-batch-panel {
  padding: 12px 14px;
  background: rgba(255,255,255,0.03);
  border-radius: 6px;
  border: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 10px;
}
.mon-batch-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.mon-batch-head h4 {
/* V219: 上次监控批量验证时间 */
.mon-batch-at {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 400;
  margin-left: 8px;
}
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  margin: 0;
}
.mon-batch-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.mon-batch-actions .save-msg {
  font-size: 12px;
  color: var(--up);
}
.mon-batch-actions .save-msg.err {
  color: var(--down);
}
.mon-batch-actions .ghost.active {
  background: rgba(96, 165, 250, 0.18);
  color: var(--accent);
  border-color: var(--accent);
}
.mon-batch-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.mon-batch-table th {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 600;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  text-align: right;
}
.mon-batch-table th:first-child, .mon-batch-table td:first-child { text-align: left; }
.mon-batch-table td {
  padding: 5px 8px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  text-align: right;
  font-family: var(--font-mono);
}
.mon-batch-legend {
  font-size: 11px;
  color: var(--text-dim);
  line-height: 1.6;
  margin: 0;
}
</style>
