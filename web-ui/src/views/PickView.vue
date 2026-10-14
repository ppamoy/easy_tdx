<script setup lang="ts">
// 缠论选股：按日期+级别查找买点标的，点击查看缠论分析图（K线+笔+中枢+买卖点+背驰+MACD）
// V810: 图表数据从 /chanlun/chart-data 获取（与选股缓存同源），全量加载 + dataZoom缩放
import { ref, onMounted, watch } from 'vue'
import ChanlunChart from '../components/ChanlunChart.vue'
import type { Bar, Category } from '../types'

// ── ChanlunChart prop types ──
interface ChanlunBi {
  index: number; direction: 'up' | 'down'
  start_date: string; end_date: string
  high: number; low: number
  start_val: number; end_val: number
  start_index: number; end_index: number
  done: boolean
}
interface ChanlunXd {
  index: number; direction: 'up' | 'down'
  start_date: string; end_date: string
  high: number; low: number
  start_val: number; end_val: number
  start_index: number; end_index: number
}
interface ChanlunZs {
  index: number; zg: number; zd: number; gg: number; dd: number
  line_count: number; start_date: string; end_date: string
  start_index: number; end_index: number; done: boolean
}
interface ChanlunMmd {
  type: string; date: string; msg: string
  confidence: number; bar_index: number
  anchor_val: number | null
  quality: { grade: string | null; score: number | null; reasons: string[] | null } | null
}
interface ChanlunBc {
  type: string; bc: string; date: string; msg: string
  bar_index: number; anchor_val: number; anchor_bar_index: number
}
interface ChanlunFx {
  fx_type: string; date: string; val: number; bar_index: number
}

interface PickResult {
  code: string
  market: string
  category: string
  signal_type: string
  signal_dt: string
  confidence: number
  zg: number | null
  zd: number | null
  zz: number | null
}

interface PickResponse {
  date: string; category: string; total: number
  results: PickResult[]; available_dates: string[]; error?: string
}

const API = '/api/v1'

// 表单
const selectedDate = ref('')
const selectedLevel = ref<Category>('MIN_30')
const availableDates = ref<string[]>([])
const loading = ref(false)
const error = ref('')

// 结果
const results = ref<PickResult[]>([])

// ── 缠论图弹窗（全屏） ──
const chartVisible = ref(false)
const chartCode = ref('')
const chartMarket = ref('SH')
const chartLevel = ref<Category>('MIN_30')
const chartLoading = ref(false)
const chartZG = ref<number | null>(null)
const chartZD = ref<number | null>(null)
const chartZZ = ref<number | null>(null)
const chartSignalType = ref('')
const chartCached = ref(false)
const cacheCount = ref(0)

// ChanlunChart 数据
const chartBars = ref<Bar[]>([])
const chartBis = ref<ChanlunBi[]>([])
const chartXds = ref<ChanlunXd[]>([])
const chartZss = ref<ChanlunZs[]>([])
const chartMmds = ref<ChanlunMmd[]>([])
const chartBcs = ref<ChanlunBc[]>([])
const chartFxs = ref<ChanlunFx[]>([])
const chartValidFxs = ref<ChanlunFx[]>([])
const chartMacd = ref<{ dif: number[]; dea: number[]; hist: number[] } | null>(null)
const chartFrequency = ref('30min')

const levelOptions: { value: Category; label: string; freq: string }[] = [
  { value: 'MIN_30', label: '30分钟', freq: '30min' },
  { value: 'DAY', label: '日线', freq: 'daily' },
]

const categoryLabel = (cat: string) => {
  const m: Record<string, string> = { tree: '🌳 树', grain: '🌾 粮', vegetable: '🥬 菜' }
  return m[cat] || cat
}

const signalLabel = (t: string) => {
  const m: Record<string, string> = {
    '1buy': '1买', '2buy': '2买', '3buy': '3买',
    '1sell': '1卖', '2sell': '2卖', '3sell': '3卖',
    '2buy_s': '2买(强)',
  }
  return m[t] || t
}

const recommendReason = (r: PickResult) => {
  const sigMap: Record<string, string> = {
    '1buy': '缠论一买信号（趋势底背驰）',
    '2buy': '缠论二买信号（中枢回踩不破）',
    '3buy': '缠论三买信号（突破中枢上沿）',
  }
  const catMap: Record<string, string> = {
    tree: '树类标的（长期成长，不轻易卖）',
    grain: '粮类标的（波段操作）',
  }
  return [sigMap[r.signal_type] || r.signal_type, catMap[r.category] || ''].filter(Boolean).join(' + ')
}

async function fetchPick() {
  loading.value = true
  error.value = ''
  results.value = []
  try {
    const params = new URLSearchParams({ date: selectedDate.value, category: selectedLevel.value })
    const resp = await fetch(`${API}/chanlun/pick?${params}`)
    const data: PickResponse = await resp.json()
    if (data.error) {
      error.value = data.error
    } else {
      results.value = data.results || []
      availableDates.value = data.available_dates || []
      if (results.value.length === 0) {
        error.value = `${selectedDate.value} 无买点标的`
      }
    }
  } catch (e: any) {
    error.value = `请求失败: ${e.message}`
  } finally {
    loading.value = false
  }
}

// ── 打开缠论图 ──
async function openChart(r: PickResult) {
  chartCode.value = r.code
  chartMarket.value = r.market
  chartLevel.value = selectedLevel.value
  chartZG.value = r.zg
  chartZD.value = r.zd
  chartZZ.value = r.zz
  chartSignalType.value = r.signal_type
  const opt = levelOptions.find(o => o.value === chartLevel.value)
  chartFrequency.value = opt?.freq || '30min'
  chartVisible.value = true
  chartLoading.value = true
  error.value = ''
  chartBars.value = []
  chartBis.value = []
  chartXds.value = []
  chartZss.value = []
  chartMmds.value = []
  chartBcs.value = []
  chartFxs.value = []
  chartValidFxs.value = []
  chartMacd.value = null
  chartCached.value = false
  await fetchChartData()
}

// ── 获取图表数据：/chanlun/chart-data（与选股缓存同源，全量加载） ──
async function fetchChartData() {
  chartLoading.value = true
  error.value = ''
  try {
    const params = new URLSearchParams({
      market: chartMarket.value,
      code: chartCode.value,
      category: chartLevel.value,
    })
    const resp = await fetch(`${API}/chanlun/chart-data?${params}`)
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error((err as any).detail ?? `HTTP ${resp.status}`)
    }
    const data = await resp.json()

    chartCached.value = data.cached === true

    // bars 来自与分析同一 df，索引天然对齐
    chartBars.value = (data.bars || []).map((b: any) => ({
      datetime: b.datetime || b.date,
      open: Number(b.open), high: Number(b.high),
      low: Number(b.low), close: Number(b.close),
      vol: Number(b.vol || 0), amount: Number(b.amount || 0),
    }))

    chartBis.value = (data.bis || []).map((b: any) => ({
      index: b.index, direction: b.direction,
      start_date: b.start_date, end_date: b.end_date,
      high: b.high, low: b.low,
      start_val: b.start_val, end_val: b.end_val,
      start_index: b.start_index, end_index: b.end_index,
      done: b.done ?? true,
    }))

    chartXds.value = (data.xds || []).map((x: any) => ({
      index: x.index, direction: x.direction,
      start_date: x.start_date, end_date: x.end_date,
      high: x.high, low: x.low,
      start_val: x.start_val, end_val: x.end_val,
      start_index: x.start_index, end_index: x.end_index,
    }))

    chartZss.value = (data.zss || []).map((z: any) => ({
      index: z.index, zg: z.zg, zd: z.zd, gg: z.gg, dd: z.dd,
      line_count: z.line_count,
      start_date: z.start_date, end_date: z.end_date,
      start_index: z.start_index, end_index: z.end_index,
      done: z.done,
    }))

    chartMmds.value = (data.mmds || []).map((m: any) => ({
      type: m.type, date: m.date, msg: m.msg,
      confidence: m.confidence ?? 0,
      bar_index: m.bar_index,
      anchor_val: m.anchor_val ?? null,
      quality: m.quality ? {
        grade: m.quality.grade ?? null,
        score: m.quality.score ?? null,
        reasons: m.quality.reasons ?? null,
      } : null,
    }))

    chartBcs.value = (data.bcs || []).map((bc: any) => ({
      type: bc.type, bc: bc.bc,
      date: bc.date ?? bc.curr_date, msg: bc.msg,
      bar_index: bc.bar_index ?? bc.anchor_bar_index,
      anchor_val: bc.anchor_val,
      anchor_bar_index: bc.anchor_bar_index ?? 0,
    }))

    chartFxs.value = (data.fractals || []).map((f: any) => ({
      fx_type: f.fx_type, date: f.date, val: f.val,
      bar_index: f.bar_index,
    }))

    chartValidFxs.value = (data.valid_fractals || []).map((f: any) => ({
      fx_type: f.fx_type, date: f.date, val: f.val,
      bar_index: f.bar_index,
    }))

    chartMacd.value = data.macd && data.macd.dif?.length ? {
      dif: data.macd.dif,
      dea: data.macd.dea,
      hist: data.macd.hist,
    } : null

    // 更新缓存计数（不阻塞渲染）
    fetchCacheCount()
  } catch (e: any) {
    error.value = `缠论分析失败: ${e.message}`
  } finally {
    chartLoading.value = false
  }
}

// ── 缓存管理 ──
async function fetchCacheCount() {
  try {
    const resp = await fetch(`${API}/chanlun/cache/list?category=${chartLevel.value}`)
    const data = await resp.json()
    cacheCount.value = data.total || 0
  } catch { /* ignore */ }
}

async function deleteCache() {
  if (!confirm(`确认删除 ${chartMarket.value}${chartCode.value} 的缠论缓存？下次打开需重新分析。`)) return
  try {
    await fetch(`${API}/chanlun/cache?market=${chartMarket.value}&code=${chartCode.value}&category=${chartLevel.value}`, { method: 'DELETE' })
    await fetchChartData()  // 重新分析
  } catch (e: any) {
    error.value = `删除缓存失败: ${e.message}`
  }
}

async function deleteAllCache() {
  if (!confirm(`确认删除全部缠论缓存（${chartLevel.value}）？`)) return
  try {
    await fetch(`${API}/chanlun/cache?category=${chartLevel.value}`, { method: 'DELETE' })
    await fetchCacheCount()
  } catch (e: any) {
    error.value = `删除失败: ${e.message}`
  }
}

// 初始化
onMounted(async () => {
  selectedDate.value = '2025-08-28'
  await fetchPick()
  if (availableDates.value.length > 0) {
    selectedDate.value = availableDates.value[0]
    await fetchPick()
  }
})

watch(selectedLevel, () => { fetchPick() })
</script>

<template>
  <div class="pick-page">
    <div class="pick-header">
      <h2>缠论选股 · 买点推荐</h2>
      <p class="subtitle">选择日期和交易级别，查看有缠论买点(1买/2买/3买)的标的，点击查看完整缠论分析图</p>
    </div>

    <div class="pick-controls">
      <div class="control-group">
        <label>日期</label>
        <input v-model="selectedDate" type="date" class="date-input" />
      </div>
      <div class="control-group">
        <label>级别</label>
        <select v-model="selectedLevel" class="level-select">
          <option v-for="opt in levelOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
      </div>
      <button class="btn-search" @click="fetchPick" :disabled="loading">
        {{ loading ? '查询中...' : '查询买点' }}
      </button>
    </div>

    <div class="quick-dates" v-if="availableDates.length > 0">
      <span class="quick-label">有买点的日期：</span>
      <button
        v-for="d in availableDates.slice(0, 15)"
        :key="d"
        class="date-chip"
        :class="{ active: d === selectedDate }"
        @click="selectedDate = d; fetchPick()"
      >{{ d }}</button>
    </div>

    <div v-if="error && !chartVisible" class="error-msg">{{ error }}</div>

    <div class="results-section" v-if="results.length > 0">
      <div class="results-header">
        <span>{{ selectedDate }} 共 <strong>{{ results.length }}</strong> 只买点标的</span>
      </div>
      <table class="results-table">
        <thead>
          <tr>
            <th>#</th>
            <th>代码</th>
            <th>分类</th>
            <th>买点</th>
            <th>推荐理由</th>
            <th>置信度</th>
            <th>支撑ZD</th>
            <th>压力ZG</th>
            <th>中线ZZ</th>
            <th>信号时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in results" :key="r.code + r.signal_dt" class="result-row">
            <td>{{ i + 1 }}</td>
            <td class="code-cell">{{ r.market }}{{ r.code }}</td>
            <td>
              <span class="cat-tag" :class="`cat-${r.category}`">{{ categoryLabel(r.category) }}</span>
            </td>
            <td>
              <span class="signal-tag" :class="`sig-${r.signal_type}`">{{ signalLabel(r.signal_type) }}</span>
            </td>
            <td class="reason-cell">{{ recommendReason(r) }}</td>
            <td>{{ (r.confidence * 100).toFixed(0) }}%</td>
            <td class="price-cell support">{{ r.zd?.toFixed(2) || '—' }}</td>
            <td class="price-cell resistance">{{ r.zg?.toFixed(2) || '—' }}</td>
            <td class="price-cell center">{{ r.zz?.toFixed(2) || '—' }}</td>
            <td class="time-cell">{{ r.signal_dt.slice(11) || '—' }}</td>
            <td>
              <button class="btn-chart" @click="openChart(r)">📊 缠论图</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 缠论图弹窗（全屏，可缩放） -->
    <div class="chart-modal" v-if="chartVisible">
      <div class="chart-container">
        <div class="chart-header">
          <div class="chart-title">
            <span>{{ chartMarket }}{{ chartCode }}</span>
            <span class="chart-signal" v-if="chartSignalType">{{ signalLabel(chartSignalType) }}</span>
            <span class="chart-level">{{ levelOptions.find(o => o.value === chartLevel)?.label }}</span>
            <span class="cache-badge" v-if="chartCached" title="来自SQLite缓存">⚡缓存</span>
          </div>
          <div class="chart-header-right">
            <button @click="deleteCache" :disabled="chartLoading" class="btn-cache" title="删除此标的缓存并重新分析">
              🗑 刷新缓存
            </button>
            <button class="btn-close" @click="chartVisible = false">✕ 关闭</button>
          </div>
        </div>
        <div class="chart-info">
          <span class="info-item">压力 ZG: <strong class="resistance">{{ chartZG?.toFixed(2) || '—' }}</strong></span>
          <span class="info-item">支撑 ZD: <strong class="support">{{ chartZD?.toFixed(2) || '—' }}</strong></span>
          <span class="info-item">中线 ZZ: <strong class="center">{{ chartZZ?.toFixed(2) || '—' }}</strong></span>
          <span class="info-item" v-if="chartBars.length > 0">{{ chartBars.length }} 根K线 | {{ chartBis.length }}笔 {{ chartZss.length }}中枢 {{ chartMmds.length }}买卖点</span>
          <span class="info-item hint" v-if="!chartCached && chartLoading">首次分析约15秒，之后秒开</span>
        </div>
        <div class="chart-body">
          <div v-if="chartLoading" class="chart-loading">
            <div class="spinner"></div>
            <div>缠论分析中...{{ chartCached ? '(缓存)' : '首次约15秒' }}</div>
          </div>
          <div v-if="error && chartVisible" class="chart-error">{{ error }}</div>
          <ChanlunChart
            v-if="chartBars.length > 0"
            :bars="chartBars"
            :bis="chartBis"
            :xds="chartXds"
            :zss="chartZss"
            :mmds="chartMmds"
            :bcs="chartBcs"
            :fxs="chartFxs"
            :valid-fxs="chartValidFxs"
            :macd="chartMacd ?? undefined"
            :frequency="chartFrequency"
            :show-mmd-labels="true"
            style="height: 100%; min-height: 500px;"
          />
        </div>
        <div class="chart-footer">
          <span class="footer-hint">💡 滚轮缩放 · 拖动平移 · 底部滑块快速跳转 · 显示全部{{ chartBars.length }}根K线</span>
          <button @click="deleteAllCache" class="btn-cache-all" title="删除当前级别全部缓存">
            清空全部缓存 ({{ cacheCount }})
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.pick-page { padding: 16px; max-width: 1200px; margin: 0 auto; color: #e0e0e0; }
.pick-header h2 { margin: 0 0 4px; font-size: 20px; }
.subtitle { margin: 0 0 16px; color: #888; font-size: 13px; }

.pick-controls { display: flex; gap: 12px; align-items: end; margin-bottom: 12px; flex-wrap: wrap; }
.control-group { display: flex; flex-direction: column; gap: 4px; }
.control-group label { font-size: 12px; color: #888; }
.date-input, .level-select { background: #1a1a1a; border: 1px solid #333; color: #e0e0e0; padding: 6px 10px; border-radius: 4px; font-size: 13px; }
.btn-search { background: #2563eb; color: #fff; border: none; padding: 7px 18px; border-radius: 4px; cursor: pointer; font-size: 13px; }
.btn-search:hover { background: #1d4ed8; }
.btn-search:disabled { opacity: 0.5; }

.quick-dates { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; align-items: center; }
.quick-label { color: #888; font-size: 12px; }
.date-chip { background: #1a1a1a; border: 1px solid #333; color: #aaa; padding: 3px 8px; border-radius: 3px; cursor: pointer; font-size: 11px; }
.date-chip:hover { border-color: #555; }
.date-chip.active { background: #2563eb; color: #fff; border-color: #2563eb; }

.error-msg { color: #e74c3c; padding: 12px; background: #1a0a0a; border-radius: 4px; margin-bottom: 12px; font-size: 13px; }

.results-header { margin-bottom: 8px; color: #aaa; font-size: 13px; }
.results-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.results-table th { text-align: left; padding: 8px; background: #1a1a1a; color: #888; font-weight: 500; border-bottom: 1px solid #333; }
.results-table td { padding: 8px; border-bottom: 1px solid #222; }
.result-row:hover { background: #1a1a2a; }
.code-cell { font-family: monospace; color: #6cb4f0; }
.price-cell.support { color: #27ae60; }
.price-cell.resistance { color: #e74c3c; }
.price-cell.center { color: #f39c12; }
.time-cell { color: #888; font-size: 12px; }
.reason-cell { color: #aaa; font-size: 12px; max-width: 180px; }

.cat-tag { padding: 2px 6px; border-radius: 3px; font-size: 11px; }
.cat-tree { background: #1a3a1a; color: #4a8; }
.cat-grain { background: #3a3a1a; color: #ca8; }
.cat-vegetable { background: #3a1a1a; color: #c8a; }

.signal-tag { padding: 2px 8px; border-radius: 3px; font-weight: 600; font-size: 12px; }
.sig-1buy { background: #1a4a1a; color: #2d8; }
.sig-2buy, .sig-2buy_s { background: #1a3a2a; color: #4c8; }
.sig-3buy { background: #1a2a3a; color: #6af; }

.btn-chart { background: #333; color: #ccc; border: 1px solid #444; padding: 4px 10px; border-radius: 3px; cursor: pointer; font-size: 12px; }
.btn-chart:hover { background: #444; }

/* 缠论图弹窗（全屏） */
.chart-modal {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.92);
  z-index: 9999;
  display: flex; flex-direction: column;
  padding: 8px;
}
.chart-container {
  background: #111;
  border-radius: 8px;
  flex: 1;
  display: flex; flex-direction: column;
  overflow: hidden;
  border: 1px solid #333;
}
.chart-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 16px;
  border-bottom: 1px solid #333;
  flex-shrink: 0;
}
.chart-title { display: flex; gap: 10px; align-items: center; font-size: 16px; font-weight: 600; }
.chart-signal { background: #1a4a1a; color: #2d8; padding: 2px 8px; border-radius: 3px; font-size: 12px; }
.chart-level { color: #888; font-size: 13px; }
.cache-badge { background: #1a2a1a; color: #4a8; padding: 1px 6px; border-radius: 3px; font-size: 11px; }
.chart-header-right { display: flex; gap: 8px; align-items: center; }
.btn-cache { background: #333; color: #ca8; border: 1px solid #444; padding: 5px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; }
.btn-cache:hover { background: #444; }
.btn-cache:disabled { opacity: 0.4; }
.btn-close { background: #333; color: #ccc; border: 1px solid #444; padding: 5px 12px; border-radius: 4px; cursor: pointer; font-size: 13px; }
.btn-close:hover { background: #444; color: #fff; }

.chart-info {
  display: flex; gap: 16px; padding: 6px 16px;
  font-size: 13px; flex-wrap: wrap;
  border-bottom: 1px solid #222;
  flex-shrink: 0;
}
.info-item { color: #888; }
.info-item strong { font-size: 14px; }
.info-item .resistance { color: #e74c3c; }
.info-item .support { color: #27ae60; }
.info-item .center { color: #f39c12; }
.info-item.hint { color: #6af; font-style: italic; }

.chart-body {
  flex: 1;
  background: #0a0a0a;
  position: relative;
  min-height: 400px;
  overflow: hidden;
}
.chart-loading {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  color: #888; font-size: 14px; z-index: 10; text-align: center;
}
.spinner {
  width: 32px; height: 32px; border: 3px solid #333; border-top-color: #2563eb;
  border-radius: 50%; margin: 0 auto 12px; animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.chart-error {
  position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
  color: #e74c3c; font-size: 13px; z-index: 10; text-align: center; max-width: 400px;
}

.chart-footer {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 16px;
  border-top: 1px solid #222;
  flex-shrink: 0;
}
.footer-hint { color: #666; font-size: 12px; }
.btn-cache-all { background: #2a1a1a; color: #c88; border: 1px solid #433; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; }
.btn-cache-all:hover { background: #3a2a2a; }
</style>
