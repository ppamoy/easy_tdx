<script setup lang="ts">
// 买卖点实证复盘页（V419）：后台预跑 20 只大市值标的，逐一呈现（一次一只），
// 展示买卖点 + 买卖点后逐根 K 线揭示 + 同级别中枢（MMD.zs 引用）。
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ChanlunChart from '../components/ChanlunChart.vue'
import { useEarlierBars } from '../composables/useEarlierBars'
import { useTimeJump } from '../composables/useTimeJump'
import { shiftStructure } from '../utils/shiftStructure'
import { formatError } from '../api'
import type { Bar } from '../types'

interface StockItem {
  code: string
  name: string
  market: string
  status: string
  mmd_count: number | null
}
interface MmdItem {
  type: string
  date: string | null
  bar_index: number | null
  msg: string
  confidence: number
  zs_index: number | null
}
interface ZsItem {
  index: number
  zg: number
  zd: number
  gg: number
  dd: number
  line_count: number
  start_date: string | null
  end_date: string | null
  start_index: number | null
  end_index: number | null
  done: boolean
}
interface BiItem {
  index: number
  direction: 'up' | 'down'
  start_date: string
  end_date: string
  high: number
  low: number
  start_index?: number
  end_index?: number
  done: boolean
}
interface XdItem {
  index: number
  direction: 'up' | 'down'
  start_date: string
  end_date: string
  high: number
  low: number
  start_index?: number
  end_index?: number
}
interface FxItem {
  fx_type: 'ding' | 'di'
  date: string
  val: number
  bar_index: number
}

const stocks = ref<StockItem[]>([])
const currentCode = ref('')
const loading = ref(false)
const prerunning = ref(false)
const error = ref('')
const category = ref<'DAY' | 'WEEK' | 'MIN_5' | 'MIN_15' | 'MIN_30' | 'MIN_60'>('DAY')
const analysisLevel = ref<'bi' | 'xd'>('bi')
const rawDetail = ref<any>(null)

// 详情数据
const bars = ref<Bar[]>([])
const bis = ref<BiItem[]>([])
const xds = ref<XdItem[]>([])
const zsds = ref<XdItem[]>([])
const qsds = ref<XdItem[]>([])
const zss = ref<ZsItem[]>([])
const mmds = ref<MmdItem[]>([])
const fxs = ref<FxItem[]>([])
const name = ref('')
const market = ref('')

// 当前选中的买卖点（同级别中枢 + 逐根揭示锚点）
const selectedMmdIdx = ref(-1)
const revealCursor = ref<number | undefined>(undefined) // undefined=显示全部

// V722: signal verify chart full-history backfill (view only; server window unchanged).
const {
  loading: earlierLoading,
  canLoad: earlierCanLoad,
  error: earlierError,
  fetchEarlier,
} = useEarlierBars({
  code: () => currentCode.value,
  category: () => category.value,
  earliest: () => (bars.value.length ? bars.value[0].datetime.slice(0, 10) : ''),
  detectMarket: () => (market.value as 'SZ' | 'SH') || 'SZ',
})

async function loadEarlierVerify() {
  const earlier = await fetchEarlier()
  if (earlier.length) {
    const shift = earlier.length
    bars.value = [...earlier, ...bars.value]
    // V723: 本地扩窗不重跑分析，结构索引整体 +shift。
    // mmds.bar_index 驱动逐根揭示游标，必须同步平移，否则揭示起点错位。
    bis.value = shiftStructure(bis.value as any[], shift)
    xds.value = shiftStructure(xds.value as any[], shift)
    zsds.value = shiftStructure(zsds.value as any[], shift)
    qsds.value = shiftStructure(qsds.value as any[], shift)
    zss.value = shiftStructure(zss.value as any[], shift)
    mmds.value = shiftStructure(mmds.value as any[], shift)
    fxs.value = shiftStructure(fxs.value as any[], shift)
    if (revealCursor.value !== undefined) {
      revealCursor.value += shift
    }
  }
}

// ── V723: 任意日期区间跳转（区间直达取数 + 现场缠论分析）──────────────
// detail 端点日线走预跑缓存，跳转时带 start_date/end_date 强制现场分析。
const {
  jumpStart,
  jumpEnd,
  jumping,
  jumpError,
  fetchRange,
  resetToLatest: resetTimeJump,
} = useTimeJump({
  code: () => currentCode.value,
  category: () => category.value,
  detectMarket: () => (market.value as 'SZ' | 'SH') || 'SZ',
})
const isTimeJump = ref(false)

async function jumpVerifyRange() {
  if (!currentCode.value || jumping.value) return
  const rangeBars = await fetchRange()
  if (!rangeBars) return
  loading.value = true
  try {
    const resp = await fetch(
      `/api/v1/verify/signals/detail?code=${currentCode.value}&category=${category.value}` +
        `&start_date=${rangeBars[0].datetime.slice(0, 10)}` +
        `&end_date=${rangeBars[rangeBars.length - 1].datetime.slice(0, 10)}`,
    )
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const d = await resp.json()
    if (d.error) throw new Error(d.error)
    bars.value = rangeBars
    rawDetail.value = d
    analysisLevel.value = 'bi'
    applyAnalysisLevel('bi', d)
    fxs.value = (d.fractals ?? []).map((f: any) => ({
      fx_type: f.fx_type,
      date: f.date,
      val: f.val,
      bar_index: f.bar_index,
    }))
    selectedMmdIdx.value = -1
    revealCursor.value = undefined
    isTimeJump.value = true
  } catch (e) {
    jumpError.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function backToLatestVerify() {
  if (!currentCode.value) return
  isTimeJump.value = false
  resetTimeJump()
  await selectStock(currentCode.value)
}


const selectedMmd = computed<MmdItem | null>(() =>
  selectedMmdIdx.value >= 0 ? (mmds.value[selectedMmdIdx.value] ?? null) : null,
)

// 同级别中枢 index：选中买卖点的 zs_index
const singleZsIndex = computed<number | undefined>(() => {
  const m = selectedMmd.value
  return m && m.zs_index !== null && m.zs_index !== undefined ? m.zs_index : undefined
})

async function prerun() {
  prerunning.value = true
  error.value = ''
  try {
    const resp = await fetch('/api/v1/verify/signals/prerun', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force: true }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    await loadList()
  } catch (e) {
    error.value = formatError(e)
  } finally {
    prerunning.value = false
  }
}

async function loadList() {
  try {
    const resp = await fetch('/api/v1/verify/signals/list')
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const d = await resp.json()
    stocks.value = d.items ?? []
    // 默认选中第一只 ready 的标的
    if (!currentCode.value && stocks.value.length > 0) {
      await selectStock(stocks.value[0].code)
    }
  } catch (e) {
    error.value = formatError(e)
  }
}

function applyAnalysisLevel(level: 'bi' | 'xd', data: any) {
  if (level === 'xd' && data?.levels?.xd) {
    const xdLevel = data.levels.xd
    bis.value = xdLevel.bis ?? []
    xds.value = []
    zsds.value = xdLevel.zsds ?? []
    qsds.value = xdLevel.qsds ?? []
    zss.value = xdLevel.zss ?? []
    mmds.value = (xdLevel.mmds ?? []).map((m: any) => ({
      type: m.type,
      date: m.date,
      bar_index: m.bar_index ?? null,
      msg: m.msg ?? '',
      confidence: m.confidence ?? 0,
      zs_index: m.zs_index ?? null,
    }))
    return
  }

  bis.value = data?.bis ?? []
  xds.value = data?.xds ?? []
  zsds.value = data?.zsds ?? []
  qsds.value = data?.qsds ?? []
  zss.value = data?.zss ?? []
  mmds.value = (data?.mmds ?? []).map((m: any) => ({
    type: m.type,
    date: m.date,
    bar_index: m.bar_index ?? null,
    msg: m.msg ?? '',
    confidence: m.confidence ?? 0,
    zs_index: m.zs_index ?? null,
  }))
}

function onAnalysisLevelChange() {
  if (rawDetail.value) {
    applyAnalysisLevel(analysisLevel.value, rawDetail.value)
  }
}

async function selectStock(code: string) {
  currentCode.value = code
  loading.value = true
  error.value = ''
  selectedMmdIdx.value = -1
  revealCursor.value = undefined
  isTimeJump.value = false
  resetTimeJump()
  try {
    const resp = await fetch(
      `/api/v1/verify/signals/detail?code=${code}&category=${category.value}`,
    )
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const d = await resp.json()
    if (d.error) throw new Error(d.error)
    name.value = d.name ?? ''
    market.value = d.market ?? ''
    bars.value = d.bars ?? []
    rawDetail.value = d
    analysisLevel.value = 'bi'
    applyAnalysisLevel('bi', d)
    fxs.value = (d.fractals ?? []).map((f: any) => ({
      fx_type: f.fx_type,
      date: f.date,
      val: f.val,
      bar_index: f.bar_index,
    }))
  } catch (e) {
    error.value = formatError(e)
  } finally {
    loading.value = false
  }
}

async function onCategoryChange() {
  if (currentCode.value) {
    await selectStock(currentCode.value)
  }
}

function selectMmd(idx: number) {
  selectedMmdIdx.value = idx
  const m = mmds.value[idx]
  // 逐根揭示游标从买卖点 bar_index 起
  if (m && m.bar_index !== null && m.bar_index !== undefined) {
    revealCursor.value = m.bar_index
  } else {
    revealCursor.value = undefined
  }
}

function stepForward() {
  if (revealCursor.value === undefined) return
  revealCursor.value = Math.min(revealCursor.value + 1, bars.value.length - 1)
}
function stepForward10() {
  if (revealCursor.value === undefined) return
  revealCursor.value = Math.min(revealCursor.value + 10, bars.value.length - 1)
}
function jumpToEnd() {
  revealCursor.value = bars.value.length - 1
}
function resetReveal() {
  revealCursor.value = undefined
}

function prevStock() {
  const idx = stocks.value.findIndex((s) => s.code === currentCode.value)
  if (idx > 0) selectStock(stocks.value[idx - 1].code)
}
function nextStock() {
  const idx = stocks.value.findIndex((s) => s.code === currentCode.value)
  if (idx >= 0 && idx < stocks.value.length - 1) selectStock(stocks.value[idx + 1].code)
}

function copyShareLink() {
  if (navigator.clipboard?.writeText) {
    navigator.clipboard
      .writeText(window.location.href)
      .then(() => {
        error.value = ''
      })
      .catch(() => {
        error.value = '复制链接失败'
      })
  } else {
    error.value = '复制链接失败'
  }
}

function mmdClass(m: MmdItem): string {
  return m.type.includes('buy') ? 'mmd-buy' : 'mmd-sell'
}

// URL 同步：周期与分析级别保持在 query 中，刷新/分享后可复现
const route = useRoute()
const router = useRouter()
const _qCat = String(route.query.category || '')
if (['DAY', 'WEEK', 'MIN_5', 'MIN_15', 'MIN_30', 'MIN_60'].includes(_qCat)) {
  category.value = _qCat as typeof category.value
}
if (route.query.level === 'xd') analysisLevel.value = 'xd'
watch([category, analysisLevel], () => {
  router.replace({ query: { category: category.value, level: analysisLevel.value } })
})

onMounted(() => {
  loadList()
})
</script>

<template>
  <div class="verify-view">
    <div class="verify-header">
      <h2>买卖点实证复盘</h2>
      <button class="primary" :disabled="prerunning" @click="prerun">
        {{ prerunning ? '预跑中…' : '🔄 后台预跑 20 只标的' }}
      </button>
      <span class="hint"
        >后台预跑 20 只大市值标的（无需选日期），逐一呈现买卖点，逐根看事后走势验证模型精准度</span
      >
    </div>

    <div v-if="error" class="error-banner">⚠ {{ error }}</div>

    <div class="verify-layout">
      <!-- 左列表（20 只标的） -->
      <aside class="stock-list">
        <div class="list-head">标的（{{ stocks.length }} 只）</div>
        <div
          v-for="s in stocks"
          :key="s.code"
          class="stock-item"
          :class="{ active: s.code === currentCode }"
          @click="selectStock(s.code)"
        >
          <span class="stock-code">{{ s.code }}</span>
          <span class="stock-name">{{ s.name }}</span>
          <span class="stock-status" :class="'st-' + s.status">
            {{ s.status === 'ready' ? '✓' : s.status === 'failed' ? '✗' : '…' }}
          </span>
          <span class="stock-mmd">{{ s.mmd_count ?? '—' }} 信号</span>
        </div>
      </aside>

      <!-- 右详情（一次一只） -->
      <main class="detail">
        <template v-if="currentCode">
          <div class="detail-head">
            <button class="ghost" @click="prevStock">◀ 上一只</button>
            <span class="detail-title">{{ name }}（{{ market }}{{ currentCode }}）</span>
            <select v-model="category" class="period-select" @change="onCategoryChange">
              <option value="DAY">日线</option>
              <option value="WEEK">周线</option>
              <option value="MIN_5">5分钟</option>
              <option value="MIN_15">15分钟</option>
              <option value="MIN_30">30分钟</option>
              <option value="MIN_60">60分钟</option>
            </select>
            <select v-model="analysisLevel" class="period-select" @change="onAnalysisLevelChange">
              <option value="bi">笔级别</option>
              <option value="xd">线段级别</option>
            </select>
            <button class="ghost" @click="copyShareLink">🔗 复制链接</button>
            <button class="ghost" @click="nextStock">下一只 ▶</button>
          </div>

          <div v-if="loading" class="loading">加载中…</div>
          <template v-else>
            <ChanlunChart
              :bars="bars"
              :bis="bis"
              :xds="xds"
              :zsds="zsds as any"
              :qsds="qsds as any"
              :zss="zss as any"
              :mmds="mmds as any"
              :fxs="fxs as any"
              :frequency="category"
              :reveal-index="revealCursor"
              :single-zs-index="singleZsIndex"
            />

            <!-- 买卖点列表 + 逐根揭示控件 -->
            <div class="mmd-panel">
              <div class="mmd-panel-head">买卖点（点击查看同级别中枢 + 逐根揭示）</div>
              <div class="mmd-list">
                <button
                  v-for="(m, i) in mmds"
                  :key="i"
                  class="mmd-item"
                  :class="{ active: i === selectedMmdIdx }"
                  @click="selectMmd(i)"
                >
                  <span :class="['mmd-type', mmdClass(m)]">{{ m.type }}</span>
                  <span class="mmd-date">{{ m.date }}</span>
                  <span class="mmd-conf">{{ (m.confidence * 100).toFixed(0) }}%</span>
                  <span v-if="m.zs_index !== null" class="mmd-zs">中枢#{{ m.zs_index }}</span>
                  <span v-else class="mmd-zs none">无同级别中枢</span>
                </button>
                <div v-if="mmds.length === 0" class="empty">该标的无买卖点</div>
              </div>

              <div v-if="selectedMmd" class="reveal-controls">
                <span class="reveal-label">从「{{ selectedMmd.type }}」后逐根看走势：</span>
                <button class="ghost" @click="stepForward">下一根</button>
                <button class="ghost" @click="stepForward10">快进 10 根</button>
                <button class="ghost" @click="jumpToEnd">跳到末尾</button>
                <button class="ghost" @click="resetReveal">显示全部</button>
                <span v-if="revealCursor !== undefined" class="reveal-pos"
                  >已揭示到第 {{ revealCursor + 1 }} / {{ bars.length }} 根</span
                >
                <button class="ghost" :disabled="!earlierCanLoad" @click="loadEarlierVerify">
                  {{ earlierLoading ? '加载中…' : '加载更早 ⏮' }}
                </button>
                <!-- V723: 任意日期区间跳转（区间重取 + 现场分析） -->
                <input v-model="jumpStart" type="date" title="开始日期" />
                <input v-model="jumpEnd" type="date" title="结束日期" />
                <button class="ghost" :disabled="jumping" @click="jumpVerifyRange">
                  {{ jumping ? '跳转中…' : '跳转 📅' }}
                </button>
                <button v-if="isTimeJump" class="ghost" @click="backToLatestVerify">回最新 ⏭</button>
                <span v-if="jumpError" class="reveal-label">{{ jumpError }}</span>
                <span v-if="earlierError" class="reveal-label">{{ earlierError }}</span>
              </div>
            </div>
          </template>
        </template>
        <div v-else class="empty">正在加载标的列表…</div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.verify-view {
  padding: 16px;
}
.verify-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.verify-header h2 {
  margin: 0;
}
.verify-header .hint {
  color: #94a3b8;
  font-size: 12px;
}
.error-banner {
  background: #7f1d1d;
  color: #fecaca;
  padding: 8px 12px;
  border-radius: 6px;
  margin-bottom: 12px;
}
.verify-layout {
  display: flex;
  gap: 12px;
}
.stock-list {
  width: 200px;
  flex-shrink: 0;
  border: 1px solid #2a2e3a;
  border-radius: 8px;
  overflow-y: auto;
  max-height: 80vh;
}
.list-head {
  padding: 8px 12px;
  font-weight: 600;
  border-bottom: 1px solid #2a2e3a;
}
.stock-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  cursor: pointer;
}
.stock-item:hover {
  background: #1f2937;
}
.stock-item.active {
  background: #1e3a5f;
}
.stock-code {
  font-family: monospace;
  color: #60a5fa;
}
.stock-name {
  flex: 1;
}
.stock-mmd {
  font-size: 11px;
  color: #94a3b8;
}
.stock-status {
  font-size: 11px;
  font-weight: 700;
}
.stock-status.st-ready {
  color: #22c55e;
}
.stock-status.st-failed {
  color: #ef4444;
}
.stock-status.st-pending {
  color: #94a3b8;
}
.detail {
  flex: 1;
  min-width: 0;
}
.detail-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.detail-title {
  font-size: 16px;
  font-weight: 600;
  flex: 1;
}
.period-select {
  background: #0f172a;
  color: #e2e8f0;
  border: 1px solid #2a2e3a;
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 12px;
}
.loading,
.empty {
  color: #94a3b8;
  padding: 24px;
  text-align: center;
}
.mmd-panel {
  margin-top: 8px;
  border: 1px solid #2a2e3a;
  border-radius: 8px;
}
.mmd-panel-head {
  padding: 8px 12px;
  font-weight: 600;
  border-bottom: 1px solid #2a2e3a;
}
.mmd-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 12px;
}
.mmd-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid #2a2e3a;
  border-radius: 6px;
  cursor: pointer;
  background: transparent;
  color: #e5e7eb;
}
.mmd-item:hover {
  background: #1f2937;
}
.mmd-item.active {
  border-color: #60a5fa;
  background: #1e3a5f;
}
.mmd-type {
  font-weight: 600;
}
.mmd-buy {
  color: #22c55e;
}
.mmd-sell {
  color: #ef4444;
}
.mmd-date {
  font-size: 11px;
  color: #94a3b8;
}
.mmd-conf {
  font-size: 11px;
  color: #fbbf24;
}
.mmd-zs {
  font-size: 11px;
  color: #60a5fa;
}
.mmd-zs.none {
  color: #6b7280;
}
.reveal-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-top: 1px solid #2a2e3a;
  flex-wrap: wrap;
}
.reveal-label {
  color: #e5e7eb;
}
.reveal-pos {
  color: #94a3b8;
  font-size: 12px;
}
button.primary {
  background: #2563eb;
  color: white;
  border: none;
  padding: 8px 14px;
  border-radius: 6px;
  cursor: pointer;
}
button.ghost {
  background: transparent;
  border: 1px solid #2a2e3a;
  color: #e5e7eb;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
}
button.ghost:hover {
  background: #1f2937;
}
</style>
