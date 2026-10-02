<script setup lang="ts">
// 缠论分析视图：输入标的代码，调用后端缠论分析 API，
// 在 K 线图上叠加显示笔、线段、中枢、买卖点。

import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ChanlunChart from '../components/ChanlunChart.vue'
import PeriodSelect from '../components/PeriodSelect.vue'
import V102DecisionCard from '../components/V102DecisionCard.vue'
import { formatError } from '../api'
import type { Bar } from '../types'
import { fetchBars, loadEarlierBars } from '../api'
import { useTimeJump } from '../composables/useTimeJump'

const router = useRouter()
const code = ref('000001')
const category = ref<'DAY' | 'WEEK' | 'MONTH' | 'MIN_5' | 'MIN_15' | 'MIN_30' | 'MIN_60'>('DAY')
const count = ref(800)
const multiLevel = ref(false)
const lowLevel = ref<'MIN_5' | 'MIN_15' | 'MIN_30' | 'MIN_60'>('MIN_30')
const loading = ref(false)
const error = ref('')

interface ChanlunBi {
  index: number
  direction: 'up' | 'down'
  start_date: string
  end_date: string
  high: number
  low: number
  start_val?: number
  end_val?: number
  start_index?: number
  end_index?: number
  done: boolean
}

interface ChanlunXd {
  index: number
  direction: 'up' | 'down'
  start_date: string
  end_date: string
  high: number
  low: number
  start_val?: number
  end_val?: number
  start_index?: number
  end_index?: number
}

interface ChanlunZs {
  index: number
  zg: number
  zd: number
  gg: number
  dd: number
  line_count: number
  start_date: string
  end_date: string
  start_index?: number
  end_index?: number
  done: boolean
}

interface ChanlunMmdQuality {
  grade: 'S' | 'A' | 'B' | 'C' | 'D' | null
  score: number | null
  reasons: string[] | null
}

interface ChanlunMmd {
  type: string
  date: string | null
  msg: string
  confidence: number
  bar_index?: number
  quality: ChanlunMmdQuality | null
  // V102 缠论决策支持（条件264-267）
  v102_multi_signal_correlation?: {
    nearby_signals: number
    signal_density: string
    confidence_adjust: number
    msg: string
  } | null
  v102_signal_quality?: {
    tech_score: number
    volume_score: number
    trend_score: number
    volatility_score: number
    overall_grade: string
    overall_score: number
    strength: string
    confidence_adjust: number
    msg: string
  } | null
  v102_decision_support?: {
    entry_price: number
    stop_loss: number
    take_profit_1: number
    take_profit_2: number
    risk_reward_ratio: number
    position_size_pct: number
    action_recommendation: string
    risk_notes: string
    confidence_adjust: number
  } | null
  v102_pattern_match?: {
    similar_patterns_found: number
    win_rate: number
    avg_return: number
    max_drawdown: number
    confidence_adjust: number
    msg: string
  } | null
  // 区间套（缠论原文语义：低周期同向背驰/买卖点确认）。
  // nested=true 才算确认；但**是否"真"取决于 method**：
  //   method='cross_period' = 真实双周期数据 → 原文意义的真区间套；
  //   method='recursive'/'single' = 同序列递归或单级别近似 → 实测确认率
  //   仅 3%（真跨周期 50%），只能作参考，不得呈现为"已确认"
  //   （见 docs/区间套现状说明与统一方案.md §七）。渲染时据此区分徽章。
  qujiantao?: {
    nested: boolean
    score: number
    method: string
    confidence_adjust: number
    msg: string
    detail?: {
      low_bi_count?: number
      low_zs_count?: number
      low_bc_same_dir?: boolean
      low_mmd_same_dir?: boolean
      hi_bar_window?: number[]
    } | null
  } | null
}

interface ChanlunFx {
  fx_type: 'ding' | 'di'
  date: string
  val: number
  bar_index?: number
}

interface ChanlunBc {
  type: 'bi' | 'pz' | 'qs'
  bc: boolean
  date: string | null
  msg: string
  bar_index?: number
  anchor_val?: number | null
  anchor_bar_index?: number | null
}

const bars = ref<Bar[]>([])
const bis = ref<ChanlunBi[]>([])
const xds = ref<ChanlunXd[]>([])
const zss = ref<ChanlunZs[]>([])
const mmds = ref<ChanlunMmd[]>([])
const fxs = ref<ChanlunFx[]>([])
// 缠论有效分型（笔端点分型，交替且不重叠），用于消除「底-顶-底」挤在连续K线的
// 重叠分型噪声。展示层优先使用它，原始 fractals 仍保留用于买卖点等计算。
const validFxs = ref<ChanlunFx[]>([])
const bcs = ref<ChanlunBc[]>([])
const zsds = ref<ChanlunXd[]>([])
const qsds = ref<ChanlunXd[]>([])
const macd = ref<{ dif: number[]; dea: number[]; hist: number[] } | null>(null)

// 买卖点分类准确度验证（由 /chanlun/analyze 返回的 signal_accuracy）
const signalAccuracy = ref<any>(null)
// V458: 准确度验证持有期切换（3/5/10/20 根）
const accHorizon = ref<'3' | '5' | '10' | '20'>('5')

interface ChanlunBoll {
  upper: number[]
  mid: number[]
  lower: number[]
  width: number[]
  percent_b: number[]
  latest_upper: number
  latest_mid: number
  latest_lower: number
  latest_percent_b: number
  latest_width: number
}

const boll = ref<ChanlunBoll | null>(null)

// ── 级别切换：把顶层笔级别或 levels.xd 线段级别映射到图表/择时数组 ──
function mapBis(raw: any[]): ChanlunBi[] {
  return (raw ?? []).map((b: any) => ({
    index: b.index,
    direction: b.direction,
    start_date: b.start_date,
    end_date: b.end_date,
    high: b.high,
    low: b.low,
    start_val: b.start_val,
    end_val: b.end_val,
    start_index: b.start_index,
    end_index: b.end_index,
    done: b.done ?? true,
  }))
}

function mapXds(raw: any[]): ChanlunXd[] {
  return (raw ?? []).map((x: any) => ({
    index: x.index,
    direction: x.direction,
    start_date: x.start_date,
    end_date: x.end_date,
    high: x.high,
    low: x.low,
    start_val: x.start_val,
    end_val: x.end_val,
    start_index: x.start_index,
    end_index: x.end_index,
  }))
}

function mapZss(raw: any[]): ChanlunZs[] {
  return (raw ?? []).map((z: any) => ({
    index: z.index,
    zg: z.zg,
    zd: z.zd,
    gg: z.gg,
    dd: z.dd,
    line_count: z.line_count,
    start_date: z.start_date,
    end_date: z.end_date,
    start_index: z.start_index,
    end_index: z.end_index,
    done: z.done,
  }))
}

function mapMmds(raw: any[]): ChanlunMmd[] {
  return (raw ?? []).map((m: any) => ({
    type: m.type,
    date: m.date,
    msg: m.msg,
    confidence: m.confidence ?? 0,
    bar_index: m.bar_index,
    // V731 修复：anchor_val 是买卖点标记价格的唯一真源（= 触发笔终点分型的
    // 极值价：买点取底分型低点、卖点取顶分型高点）。此前漏映射，导致
    // ChanlunChart 走 fallback（该K线 low*0.995 / high*1.005）——图上画的
    // 价格并非模型识别出的买卖点价格，而是带视觉偏移的近似值。
    anchor_val: m.anchor_val ?? null,
    quality: m.quality
      ? {
          grade: m.quality.grade ?? null,
          score: m.quality.score ?? null,
          reasons: m.quality.reasons ?? null,
        }
      : null,
    v102_multi_signal_correlation: m.v102_multi_signal_correlation ?? null,
    v102_signal_quality: m.v102_signal_quality ?? null,
    v102_decision_support: m.v102_decision_support ?? null,
    v102_pattern_match: m.v102_pattern_match ?? null,
    qujiantao: m.qujiantao ?? null,
  }))
}

function mapBcs(raw: any[]): ChanlunBc[] {
  return (raw ?? []).map((bc: any) => ({
    type: bc.type,
    bc: bc.bc,
    date: bc.date ?? bc.curr_date,
    msg: bc.msg,
    bar_index: bc.bar_index ?? bc.anchor_bar_index,
    anchor_val: bc.anchor_val,
    anchor_bar_index: bc.anchor_bar_index,
  }))
}

/** 把后端的分型字典映射成图表所需结构（顶层 fractals / valid_fractals 同构）。 */
function mapFxs(raw: any[]): ChanlunFx[] {
  return (raw ?? []).map((f: any) => ({
    fx_type: f.fx_type,
    date: f.date,
    val: f.val,
    bar_index: f.bar_index,
  }))
}

function applyAnalysisLevel(level: AnalysisLevel, data: any) {
  if (level !== 'bi' && data?.levels?.[level]) {
    const lvl = data.levels[level]
    // 递归级别：高级别「笔」= 上一级线段；本级别不再叠加更高级别线段，避免双线重叠。
    bis.value = mapBis(lvl.bis)
    xds.value = []
    zsds.value = mapXds(lvl.zsds)
    qsds.value = mapXds(lvl.qsds)
    zss.value = mapZss(lvl.zss)
    mmds.value = mapMmds(lvl.mmds)
    bcs.value = mapBcs(lvl.bcs)
    // 递归级别（xd/xd_lN）：后端 levels 里**没有**分型字段（只有 bis/xds/zss/mmds/bcs），
    // 若不同步清空，图上会残留上一级别（bi）的分型——与本级别笔/中枢不匹配，
    // 用户会看到「按 xd 笔划分」却标着「bi 的分型」这种自相矛盾的画面。
    fxs.value = []
    validFxs.value = []
    return
  }

  bis.value = mapBis(data?.bis)
  xds.value = mapXds(data?.xds)
  zsds.value = mapXds(data?.zsds)
  qsds.value = mapXds(data?.qsds)
  zss.value = mapZss(data?.zss)
  mmds.value = mapMmds(data?.mmds)
  bcs.value = mapBcs(data?.bcs)
  // 回到笔级别：分型只存在于顶层数据（levels 里没有），必须恢复，
  // 否则从 xd 切回 bi 后图上将永久丢失分型标注。
  fxs.value = mapFxs(data?.fractals)
  validFxs.value = mapFxs(data?.valid_fractals)
}

// 由后端 levels 键推导分析级别选项与展示标签（bi / xd / xd_l2 / xd_l3…）。
const levelName = (key: string): string => {
  if (key === 'bi') return '笔级别'
  if (key === 'xd') return '线段级别'
  const m = /^xd_l(\d+)$/.exec(key)
  return m ? `递归${Number(m[1])}级` : key
}

// 分析完成后根据后端 levels 刷新可选级别，并把当前级别校正到有效值。
function syncAvailableLevels(data: any) {
  const keys = Object.keys(data?.levels ?? {})
  const ordered = keys.filter((k) => k === 'bi' || k.startsWith('xd'))
  const next: AnalysisLevel[] = ordered.length ? (ordered as AnalysisLevel[]) : ['bi']
  availableLevels.value = next.map((k) => ({ key: k, label: levelName(k) }))
  if (!next.includes(analysisLevel.value)) analysisLevel.value = 'bi'
}

function onAnalysisLevelChange() {
  if (rawResult.value) applyAnalysisLevel(analysisLevel.value, rawResult.value)
}

// V535: 基本面估值（PE/PB，诊断/缠论同源，无缓存财报时为 null）
// V589: pe 为动态市盈率（年化 EPS 计算），pb 为静态市净率（每股净资产 point-in-time，不年化）
const valuation = ref<{ pe: number | null; pb: number | null } | null>(null)

// 多级别分析结果
const multiLevelResult = ref<any>(null)

// 递归级别切换：bi=笔级别，xd=线段级别（以低级别线段作为高级别笔），
// 更高级别（xd_l2、xd_l3…）在 recursion_depth>=2 且数据支持时动态出现。
type AnalysisLevel = 'bi' | 'xd' | `xd_l${number}`
const analysisLevel = ref<AnalysisLevel>('bi')
// 当前分析结果中可用的级别（后端 levels 键，bi + 递归链 xd/xd_l2…）。
const availableLevels = ref<{ key: AnalysisLevel; label: string }[]>([
  { key: 'bi', label: '笔级别' },
])
// 多级别递归深度（<=8，后端经 ChanlunRequest.recursion_depth 解析）。
const recursionDepth = ref(1)
const rawResult = ref<any>(null)
function loadBool(key: string, def: boolean): boolean {
  try {
    const v = localStorage.getItem(key)
    if (v === null) return def
    return v === '1'
  } catch {
    return def
  }
}
const showZsds = ref(loadBool('chanlun.showZsds', true))
const showFractals = ref(loadBool('chanlun.showFractals', true))
const showMmds = ref(loadBool('chanlun.showMmds', true))
const showBcs = ref(loadBool('chanlun.showBcs', true))
const showZss = ref(loadBool('chanlun.showZss', true))
const showMmdLabels = ref(loadBool('chanlun.showMmdLabels', false))

const analysisLevelLabel = computed(() => {
  if (analysisLevel.value === 'bi') return '笔级别'
  const lvl = availableLevels.value.find((x) => x.key === analysisLevel.value)
  return lvl?.label ?? '线段级别'
})

// 统计信息
const stats = computed(() => {
  const buy1 = mmds.value.filter((m) => m.type === '1buy')
  const sell1 = mmds.value.filter((m) => m.type === '1sell')
  const highConfBuy = mmds.value.filter(
    (m) => m.confidence >= 0.7 && (m.type === '1buy' || m.type === '2buy'),
  )
  const highConfSell = mmds.value.filter(
    (m) => m.confidence >= 0.7 && (m.type === '1sell' || m.type === '2sell'),
  )
  // 按类型统计
  const typeCounts: Record<string, number> = {}
  const gradeCounts: Record<string, number> = { S: 0, A: 0, B: 0, C: 0, D: 0 }
  for (const m of mmds.value) {
    typeCounts[m.type] = (typeCounts[m.type] ?? 0) + 1
    if (m.quality?.grade)
      gradeCounts[m.quality.grade] =
        (gradeCounts[m.quality.grade as keyof typeof gradeCounts] ?? 0) + 1
  }
  return {
    klineCount: bars.value.length,
    biCount: bis.value.length,
    xdCount: xds.value.length,
    zsdCount: zsds.value.length,
    qsdCount: qsds.value.length,
    zsCount: zss.value.length,
    mmdCount: mmds.value.length,
    buy1Count: buy1.length,
    sell1Count: sell1.length,
    highConfBuyCount: highConfBuy.length,
    highConfSellCount: highConfSell.length,
    lastBuyConf: buy1.length > 0 ? Math.max(...buy1.map((m) => m.confidence)) : 0,
    lastSellConf: sell1.length > 0 ? Math.max(...sell1.map((m) => m.confidence)) : 0,
    typeCounts,
    gradeCounts,
  }
})

// 高置信度信号（用于告警）
const strongSignals = computed(() => mmds.value.filter((m) => m.confidence >= 0.75))

// 最新买卖点（用于快速详情展示）
const latestMmd = computed(() => (mmds.value.length > 0 ? mmds.value[mmds.value.length - 1] : null))

// V341: 信号历史回溯 —— 每个 3买/3卖 信号的 V102 建议 + 事后 5/10/20 日表现
interface SignalHistoryRow {
  type: string
  date: string | null
  grade: string | null
  advice: string | null
  entry: number | null
  stop: number | null
  tp1: number | null
  ret5: number | null
  ret10: number | null
  ret20: number | null
  hit20: boolean
}
const signalHistory = computed<SignalHistoryRow[]>(() => {
  const bs = bars.value
  if (bs.length === 0) return []
  const closes = bs.map((b) => b.close)
  const rows: SignalHistoryRow[] = []
  for (const m of mmds.value) {
    const idx = m.bar_index
    if (idx == null || idx < 0 || idx >= closes.length) continue
    const fwd = (h: number): number | null => {
      const j = idx + h
      if (j >= closes.length || closes[idx] <= 0) return null
      return Math.round((closes[j] / closes[idx] - 1) * 1000) / 10
    }
    const ret5 = fwd(5)
    const ret10 = fwd(10)
    const ret20 = fwd(20)
    rows.push({
      type: m.type,
      date: m.date,
      grade: m.v102_signal_quality?.overall_grade ?? null,
      advice: m.v102_decision_support?.action_recommendation ?? null,
      entry: m.v102_decision_support?.entry_price ?? null,
      stop: m.v102_decision_support?.stop_loss ?? null,
      tp1: m.v102_decision_support?.take_profit_1 ?? null,
      ret5,
      ret10,
      ret20,
      hit20: ret20 != null && (m.type.includes('buy') ? ret20 > 0 : ret20 < 0),
    })
  }
  // 按信号时间倒序（最新在前）
  return rows.reverse()
})

// V343: 信号历史回溯导出 CSV
const historyCsvMsg = ref('')
function exportHistoryCsv() {
  const rows = signalHistory.value
  if (rows.length === 0) return
  const esc = (v: string): string => (/[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v)
  const lines: string[] = []
  lines.push('type,date,v102_grade,advice,entry,stop,tp1,ret5,ret10,ret20,hit20')
  for (const s of rows) {
    lines.push(
      [
        esc(s.type),
        esc(s.date ?? ''),
        esc(s.grade ?? ''),
        esc(s.advice ?? ''),
        s.entry != null ? String(s.entry) : '',
        s.stop != null ? String(s.stop) : '',
        s.tp1 != null ? String(s.tp1) : '',
        s.ret5 != null ? String(s.ret5) : '',
        s.ret10 != null ? String(s.ret10) : '',
        s.ret20 != null ? String(s.ret20) : '',
        s.hit20 ? '1' : '0',
      ].join(','),
    )
  }
  const csv = '\uFEFF' + lines.join('\n')
  try {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download =
      'easy_tdx_signal_history_' + code.value + '_' + new Date().toISOString().slice(0, 10) + '.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    historyCsvMsg.value = '✓ 已导出信号历史 CSV'
  } catch {
    historyCsvMsg.value = '导出失败（浏览器权限）'
  }
  setTimeout(() => {
    historyCsvMsg.value = ''
  }, 2500)
}

// 判断最新信号类型
const latestSignalType = computed(() => {
  if (!latestMmd.value) return null
  const type = latestMmd.value.type
  if (type.includes('buy')) return 'buy'
  if (type.includes('sell')) return 'sell'
  return 'unknown'
})

// 最新完成笔（判断当前走势位置）
const lastDoneBi = computed(() => bis.value.find((b) => b.done) ?? null)
const lastUnfinishedBi = computed(() => bis.value.find((b) => !b.done) ?? null)

// 最新中枢
const lastZs = computed(() => zss.value.filter((z) => z.done).pop() ?? null)

// 最新买点
const latestBuy = computed(() => mmds.value.filter((m) => m.type.includes('buy')).pop() ?? null)
// 最新卖点
const latestSell = computed(() => mmds.value.filter((m) => m.type.includes('sell')).pop() ?? null)

// 当前最新K线价格
const latestPrice = computed(() =>
  bars.value.length > 0 ? bars.value[bars.value.length - 1].close : 0,
)

// 市场状态判断
const marketState = computed(() => {
  if (bars.value.length === 0) return null

  const price = latestPrice.value
  const lastBuy = latestBuy.value
  const lastSell = latestSell.value
  const lastBi = lastDoneBi.value
  const lastZsItem = lastZs.value
  const unfinished = lastUnfinishedBi.value

  // 最近信号距今的K线条数
  const daysSinceBuy = lastBuy?.date
    ? Math.max(
        0,
        Math.floor(
          (new Date(bars.value[bars.value.length - 1].datetime.slice(0, 10)).getTime() -
            new Date(lastBuy.date).getTime()) /
            86400000,
        ),
      )
    : 999
  const daysSinceSell = lastSell?.date
    ? Math.max(
        0,
        Math.floor(
          (new Date(bars.value[bars.value.length - 1].datetime.slice(0, 10)).getTime() -
            new Date(lastSell.date).getTime()) /
            86400000,
        ),
      )
    : 999

  // 中枢上下沿
  const zsHigh = lastZsItem?.zg ?? 0
  const zsLow = lastZsItem?.zd ?? 0
  const zsMid = lastZsItem ? (zsHigh + zsLow) / 2 : 0
  const zsRange = lastZsItem ? zsHigh - zsLow : 0

  // 当前笔方向
  const biDir = lastBi?.direction ?? unfinished?.direction ?? 'unknown'
  const isUpBi = biDir === 'up'
  const isDownBi = biDir === 'down'

  // 价格相对于中枢的位置
  let priceZone = 'outside'
  if (lastZsItem && zsRange > 0) {
    if (price >= zsHigh) priceZone = 'above'
    else if (price <= zsLow) priceZone = 'below'
    else priceZone = 'inside'
  }

  // 计算综合建议
  let advice: string = ''
  let adviceColor: string = '#94a3b8'
  let adviceDetail: string = ''
  let action: string = '观望'
  let actionColor: string = '#94a3b8'
  let trend: string = '盘整'
  let trendColor: string = '#94a3b8'

  const buyConf = lastBuy?.confidence ?? 0
  const sellConf = lastSell?.confidence ?? 0

  // 判断当前趋势（基于最近5根K线收盘价）
  if (bars.value.length >= 5) {
    const recentCloses = bars.value.slice(-5).map((b) => b.close)
    if (isUpBi) {
      trend = recentCloses[4] > recentCloses[0] ? '上升' : '盘整'
      trendColor = recentCloses[4] > recentCloses[0] ? '#22c55e' : '#fbbf24'
    } else if (isDownBi) {
      trend = recentCloses[4] < recentCloses[0] ? '下降' : '盘整'
      trendColor = recentCloses[4] < recentCloses[0] ? '#ef4444' : '#fbbf24'
    }
  }

  // 核心判断逻辑
  const nearBuySignal = buyConf >= 0.7 && daysSinceBuy <= 10
  const nearSellSignal = sellConf >= 0.7 && daysSinceSell <= 10

  if (nearBuySignal && priceZone !== 'above') {
    action = '买入'
    actionColor = '#22c55e'
    advice = `最近 ${daysSinceBuy} 天前出现${lastBuy?.type}信号（置信度${(buyConf * 100).toFixed(0)}%），`
    if (priceZone === 'below') {
      advice += `当前价格在中枢下方，可考虑分批建仓。`
    } else if (priceZone === 'inside') {
      advice += `当前价格接近中枢下沿，关注支撑有效性。`
    } else {
      advice += `建议密切关注价格是否站稳中枢上方。`
    }
    adviceDetail = lastBuy?.msg ?? ''
    adviceColor = '#22c55e'
  } else if (nearSellSignal) {
    action = '卖出'
    actionColor = '#ef4444'
    advice = `最近 ${daysSinceSell} 天前出现${lastSell?.type}信号（置信度${(sellConf * 100).toFixed(0)}%），`
    if (daysSinceSell <= 3) {
      advice += '信号较新，建议尽快减仓或离场。'
    } else {
      advice += '建议评估是否需要止盈或止损。'
    }
    adviceDetail = lastSell?.msg ?? ''
    adviceColor = '#ef4444'
  } else if (isUpBi && price > zsHigh && priceZone === 'above') {
    action = '持有'
    actionColor = '#4ade80'
    advice = `当前处于上升趋势，价格在中枢上方（突破确认），趋势良好，建议继续持有。`
    adviceColor = '#4ade80'
  } else if (isDownBi && price < zsLow && priceZone === 'below') {
    action = '观望'
    actionColor = '#f97316'
    advice = `当前处于下降趋势，价格在中枢下方，等待底部背驰信号出现后再考虑介入。`
    adviceColor = '#f97316'
  } else if (priceZone === 'inside' && lastZsItem) {
    action = '震荡'
    actionColor = '#fbbf24'
    advice = `价格在中枢区间 [${zsLow.toFixed(2)}, ${zsHigh.toFixed(2)}] 内震荡，等待方向选择。`
    adviceDetail = `中枢宽度: ${((zsRange / price) * 100).toFixed(1)}%`
    adviceColor = '#fbbf24'
  } else {
    action = '观望'
    advice = '暂无明确信号，建议持续关注缠论结构变化。'
    adviceColor = '#94a3b8'
  }

  // 补充当前未完成笔信息
  if (unfinished) {
    const biRange = unfinished.high - unfinished.low
    const biPct = biRange > 0 ? (((price - unfinished.low) / biRange) * 100).toFixed(0) : '—'
    adviceDetail += ` 当前${isUpBi ? '上升' : '下降'}笔：低点${unfinished.low.toFixed(2)} 高点${unfinished.high.toFixed(2)} 当前位置${biPct}%`
  }

  return {
    action,
    actionColor,
    advice,
    adviceColor,
    adviceDetail,
    priceZone,
    zsHigh,
    zsLow,
    zsMid,
    zsRange,
    daysSinceBuy,
    daysSinceSell,
    biDir,
    price,
    trend,
    trendColor,
  }
})

// 置信度颜色
function confidenceColor(c: number): string {
  if (c >= 0.85) return '#22c55e'
  if (c >= 0.7) return '#eab308'
  if (c >= 0.55) return '#f97316'
  return '#6b7280'
}

// 质量评级颜色
function qualityColor(grade: string | null): string {
  if (!grade) return '#94a3b8'
  const map: Record<string, string> = {
    S: '#f59e0b',
    A: '#22c55e',
    B: '#3b82f6',
    C: '#f97316',
    D: '#ef4444',
  }
  return map[grade] ?? '#94a3b8'
}

// 一致性评分颜色
function mlConfColor(score: number): string {
  if (score >= 0.7) return '#22c55e'
  if (score >= 0.5) return '#eab308'
  if (score >= 0.3) return '#f97316'
  return '#6b7280'
}

function mlConfLabel(score: number): string {
  if (score >= 0.7) return '高度一致，信号可信度高'
  if (score >= 0.5) return '中度一致，可参考'
  if (score >= 0.3) return '低度一致，需谨慎'
  return '不一致，信号不可靠'
}
// 买卖点准确度验证辅助
function fmtAccPct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  return (v * 100).toFixed(1) + '%'
}
function fmtAccSigned(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  const sign = v >= 0 ? '+' : ''
  return sign + (v * 100).toFixed(1) + '%'
}
function fmtPf(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  if (v >= 999) return '∞'
  return v.toFixed(2)
}
// 取某类型指定持有期的统计（缺则回退 5/3 根）
function byTypeHorizon(
  type: string,
): { baseline_hit_rate?: number; profit_factor?: number } | null {
  const rep = signalAccuracy.value?.by_type?.[type]
  const h = rep?.horizons?.[accHorizon.value]
  return h ?? rep?.horizons?.['5'] ?? rep?.horizons?.['3'] ?? null
}

// 买卖点图例颜色
const MMD_COLORS: Record<string, string> = {
  '1buy': '#22c55e',
  '2buy': '#4ade80',
  '3buy': '#86efac',
  '2buy_s': '#bbf7d0',
  '1sell': '#ef4444',
  '2sell': '#f87171',
  '3sell': '#fca5a5',
  '2sell_s': '#fecaca',
}

// 中枢位置标签
function zoneLabel(zone: string): string {
  const labels: Record<string, string> = {
    above: '中枢上方',
    inside: '中枢内部',
    below: '中枢下方',
    outside: '无中枢',
  }
  return labels[zone] ?? zone
}

// 中枢位置颜色
function zoneColor(zone: string): string {
  const colors: Record<string, string> = {
    above: '#22c55e',
    inside: '#fbbf24',
    below: '#ef4444',
    outside: '#94a3b8',
  }
  return colors[zone] ?? '#94a3b8'
}

// BOLL辅助计算属性
const bollInfo = computed(() => {
  if (!boll.value || bars.value.length === 0) return null
  const pb = boll.value.latest_percent_b
  let bollZone: string = 'middle'
  if (pb > 0.8) bollZone = 'above'
  else if (pb < 0.2) bollZone = 'below'
  return {
    zone: bollZone,
    percent_b: pb,
    upper: boll.value.latest_upper,
    mid: boll.value.latest_mid,
    lower: boll.value.latest_lower,
    width: boll.value.latest_width,
  }
})

// BOLL与缠论结合判断
const bollConfluence = computed(() => {
  const bi = bollInfo.value
  if (!bi || bars.value.length === 0) return '无数据'
  const price = latestPrice.value
  const lastZsItem = lastZs.value
  let priceZone = 'outside'
  if (lastZsItem) {
    if (price >= lastZsItem.zg) priceZone = 'above'
    else if (price <= lastZsItem.zd) priceZone = 'below'
    else priceZone = 'inside'
  }
  const isSupport = Math.abs(price - bi.lower) / price < 0.02
  const isResistance = Math.abs(price - bi.upper) / price < 0.02
  if (priceZone === 'below' && isSupport) return '强支撑'
  if (priceZone === 'above' && isResistance) return '强压力'
  return '中性'
})

// ── V722: 全历史回溯（加载更早 / 回最新）─────────────────────────
const loadingEarlier = ref(false)
/** 当前窗口的起始日期（最早一根），用于增量翻页定位。 */
const windowEarliest = computed(() =>
  bars.value.length ? bars.value[0].datetime.slice(0, 10) : '',
)
const hasEarlier = ref(false)

// ── V723: 任意日期区间跳转（时间旅行）────────────────────────────────
const {
  jumpStart,
  jumpEnd,
  jumping,
  jumpError,
  fetchRange,
  resetToLatest: resetTimeJump,
} = useTimeJump({ code: () => code.value, category: () => category.value, detectMarket })

/** 当前窗口是否处于日期跳转模式（有别于默认「最新 count 根」窗口）。 */
const isTimeJump = ref(false)

/** 跳转到指定日期区间：服务端直达取数 + 全窗口缠论分析。 */
async function jumpToRange() {
  if (jumping.value || loading.value) return
  const rangeBars = await fetchRange()
  if (!rangeBars) return
  loading.value = true
  try {
    bars.value = rangeBars
    hasEarlier.value = false // 跳转窗口内不再向前翻页（区间外起点即用户所选）
    await reanalyseForWindow()
    isTimeJump.value = true
  } catch (e) {
    error.value = formatError(e)
  } finally {
    loading.value = false
  }
}

/** 回到最新窗口：清空跳转状态并重新按 count 取最新数据。 */
async function backToLatestFromJump() {
  if (loading.value) return
  isTimeJump.value = false
  resetTimeJump()
  await analyze()
}


async function loadEarlier() {
  if (loadingEarlier.value || !windowEarliest.value) return
  loadingEarlier.value = true
  error.value = ''
  try {
    const market = detectMarket(code.value)
    const earlier = await loadEarlierBars(
      market,
      code.value,
      category.value,
      windowEarliest.value,
      800,
    )
    if (earlier.length === 0) {
      hasEarlier.value = false
      return
    }
    // 新窗口 = 更早段 + 原窗口；重新分析保持叠加层全窗口覆盖
    bars.value = [...earlier, ...bars.value]
    hasEarlier.value = earlier.length >= 800
    await reanalyseForWindow()
  } catch (e) {
    error.value = formatError(e)
  } finally {
    loadingEarlier.value = false
  }
}

/** 窗口变化后对完整窗口重跑缠论分析（叠加层覆盖全部已加载 bar）。
 *
 * 复用 analyze() 的请求构造但把 count 换成当前窗口长度：直接调单级别
 * /chanlun/analyze（多级别联立不支持历史扩窗，扩窗后回落单级别视图）。
 * V723: 跳转模式下透传窗口起止日期——服务端 fetch_bars_range 直达历史
 * 区间取数，叠加层与展示窗口精确对齐（此前缺日期会错切到最新窗口）。
 */
async function reanalyseForWindow() {
  const market = detectMarket(code.value)
  const resp = await fetch('/api/v1/chanlun/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      market,
      code: code.value,
      category: category.value,
      count: bars.value.length,
      start: 0,
      recursion_depth: recursionDepth.value,
      ...(isTimeJump.value
        ? { start_date: bars.value[0]?.datetime.slice(0, 10), end_date: bars.value[bars.value.length - 1]?.datetime.slice(0, 10) }
        : {}),
    }),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}))
    throw new Error((err as { detail?: string }).detail ?? `HTTP ${resp.status}`)
  }
  const data = await resp.json()
  valuation.value = data.valuation ?? null
  if (data.boll) {
    boll.value = data.boll
  }
  rawResult.value = data
  syncAvailableLevels(data)
  analysisLevel.value = 'bi'
  applyAnalysisLevel('bi', data)
  fxs.value = (data.fractals ?? []).map((f: any) => ({
    fx_type: f.fx_type,
    date: f.date,
    val: f.val,
    bar_index: f.bar_index,
  }))
  validFxs.value = (data.valid_fractals ?? []).map((f: any) => ({
    fx_type: f.fx_type,
    date: f.date,
    val: f.val,
    bar_index: f.bar_index,
  }))
  macd.value = data.macd && data.macd.dif?.length ? data.macd : null
  signalAccuracy.value = data.signal_accuracy ?? null
}

/** 回到最新窗口（恢复 count 根 + 重分析）。 */
async function backToLatest() {
  if (loading.value) return
  hasEarlier.value = true
  await analyze()
}

async function analyze() {
  loading.value = true
  error.value = ''
  multiLevelResult.value = null
  signalAccuracy.value = null
  try {
    // 1. 取行情 —— 只取最新 count 根，与研究分析的窗口保持一致，
    //    否则图表会显示 8000 根历史而笔/线段/中枢/买卖点只覆盖最近 800 根。
    const market = detectMarket(code.value)
    const allBars = await fetchBars(
      market,
      code.value,
      category.value,
      undefined,
      undefined,
      count.value,
    )
    if (allBars.length === 0) {
      error.value = `未取到 ${market}:${code.value} 的 ${category.value} 数据`
      return
    }
    bars.value = allBars
    hasEarlier.value = allBars.length >= count.value // 拉满窗口才可能有更早历史

    // 2. 调用缠论分析 API
    let data: any
    if (multiLevel.value) {
      const resp = await fetch('/api/v1/chanlun/multi-level', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          market,
          code: code.value,
          category: category.value,
          count: count.value,
          start: 0,
          low_level: lowLevel.value,
        }),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error((err as { detail?: string }).detail ?? `HTTP ${resp.status}`)
      }
      data = await resp.json()
      // 使用高级别结果
      const hr = data.high_level?.result ?? data
      rawResult.value = hr
      syncAvailableLevels(hr)
      analysisLevel.value = 'bi'
      applyAnalysisLevel('bi', hr)
      // BOLL数据
      if (hr.boll) {
        boll.value = hr.boll
      }
      fxs.value = (hr.fractals ?? []).map((f: any) => ({
        fx_type: f.fx_type,
        date: f.date,
        val: f.val,
        bar_index: f.bar_index,
      }))
      validFxs.value = (hr.valid_fractals ?? []).map((f: any) => ({
        fx_type: f.fx_type,
        date: f.date,
        val: f.val,
        bar_index: f.bar_index,
      }))
      macd.value = hr.macd && hr.macd.dif?.length ? hr.macd : null
      signalAccuracy.value = hr.signal_accuracy ?? null
      valuation.value = hr.valuation ?? null
      // 保存多级别结果
      multiLevelResult.value = {
        confluence: data.confluence,
        low_level_qs: data.low_level_qs,
        low_level: data.low_level?.result,
      }
    } else {
      const resp = await fetch('/api/v1/chanlun/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          market,
          code: code.value,
          category: category.value,
          count: count.value,
          start: 0,
          recursion_depth: recursionDepth.value,
        }),
      })
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error((err as { detail?: string }).detail ?? `HTTP ${resp.status}`)
      }
      data = await resp.json()
      valuation.value = data.valuation ?? null

      // 3. 转换数据格式（单级别也完整映射中枢/买卖点/分型/背驰，避免图表只显示笔和线段）
      // BOLL数据
      if (data.boll) {
        boll.value = data.boll
      }
      rawResult.value = data
      syncAvailableLevels(data)
      analysisLevel.value = 'bi'
      applyAnalysisLevel('bi', data)
      fxs.value = (data.fractals ?? []).map((f: any) => ({
        fx_type: f.fx_type,
        date: f.date,
        val: f.val,
        bar_index: f.bar_index,
      }))
      validFxs.value = (data.valid_fractals ?? []).map((f: any) => ({
        fx_type: f.fx_type,
        date: f.date,
        val: f.val,
        bar_index: f.bar_index,
      }))
      macd.value = data.macd && data.macd.dif?.length ? data.macd : null
      signalAccuracy.value = data.signal_accuracy ?? null
    }
  } catch (e) {
    error.value = formatError(e)
  } finally {
    loading.value = false
  }
}

function detectMarket(code6: string): string {
  // 简单规则：60开头=SH，0开头=SZ，其余默认SZ
  if (code6.startsWith('6')) return 'SH'
  if (code6.startsWith('0') || code6.startsWith('3')) return 'SZ'
  return 'SZ'
}

// 快速跳转到回测页面（携带当前标的和参数）
function goToBacktest() {
  router.push({
    path: '/',
    query: {
      symbol: code.value,
      category: category.value,
    },
  })
}

// 快速跳转到回测页面（预选择缠论策略，用于回测验证）
function goToBacktestWithChanlun() {
  router.push({
    path: '/',
    query: {
      symbol: code.value,
      category: category.value,
      strategy: 'chanlun',
    },
  })
}

// 快速加入监控
function quickWatch(direction: 'buy' | 'sell') {
  const market = detectMarket(code.value)
  // 保存到 localStorage 供监控页面使用
  const watchList = JSON.parse(localStorage.getItem('easy_tdx_watchlist') ?? '[]')
  const item = {
    code: code.value,
    market,
    direction,
    signal_type: latestMmd.value?.type ?? '',
    timestamp: Date.now(),
  }
  // 去重
  const filtered = watchList.filter(
    (w: any) => !(w.code === item.code && w.direction === item.direction),
  )
  filtered.unshift(item)
  localStorage.setItem('easy_tdx_watchlist', JSON.stringify(filtered.slice(0, 50)))

  // 同时加入全局自选股
  const globalWatch = JSON.parse(localStorage.getItem('easy_tdx_global_watchlist') ?? '[]')
  const exists = globalWatch.some((w: any) => w.code === item.code && w.market === item.market)
  if (!exists) {
    globalWatch.unshift({
      code: item.code,
      market: item.market,
      symbol: `${item.market}${item.code}`,
      category: '缠论信号',
    })
    localStorage.setItem('easy_tdx_global_watchlist', JSON.stringify(globalWatch.slice(0, 50)))
  }

  showToast(`${market}${item.code} 已加入监控和自选`, 'success')
}

// 加入自选股（不关联信号）
function addToWatchlist() {
  const market = detectMarket(code.value)
  const globalWatch = JSON.parse(localStorage.getItem('easy_tdx_global_watchlist') ?? '[]')
  const exists = globalWatch.some((w: any) => w.code === code.value && w.market === market)
  if (exists) {
    showToast('该股票已在自选股中', 'info')
    return
  }
  globalWatch.unshift({
    code: code.value,
    market,
    symbol: `${market}${code.value}`,
    category: category.value,
  })
  localStorage.setItem('easy_tdx_global_watchlist', JSON.stringify(globalWatch.slice(0, 50)))
  showToast(`${market}${code.value} 已加入自选`, 'success')
}

// 复制当前带 query 的分享链接
function copyShareLink() {
  if (navigator.clipboard?.writeText) {
    navigator.clipboard
      .writeText(window.location.href)
      .then(() => showToast('已复制分享链接'))
      .catch(() => showToast('复制链接失败'))
  } else {
    showToast('复制链接失败')
  }
}

// 导出缠论分析结果为 JSON/CSV
function exportAnalysis() {
  if (bars.value.length === 0) return
  const market = detectMarket(code.value)
  const data = {
    exported_at: new Date().toISOString(),
    symbol: `${market}${code.value}`,
    category: category.value,
    kline_count: bars.value.length,
    bis: bis.value,
    xds: xds.value,
    zsds: zsds.value,
    qsds: qsds.value,
    zsd_count: zsds.value.length,
    qsd_count: qsds.value.length,
    zss: zss.value,
    mmds: mmds.value,
    fractals: fxs.value,
    divergences: bcs.value,
    analysis_level: analysisLevel.value,
    market_state: marketState.value,
  }
  // 下载 JSON
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `chanlun_${market}_${code.value}_${category.value}_${Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
}

// Toast 通知状态
const toast = ref<{ message: string; type: 'success' | 'error' | 'info' } | null>(null)
let toastTimer: number | null = null

function showToast(message: string, type: 'success' | 'error' | 'info' = 'info') {
  toast.value = { message, type }
  if (toastTimer !== null) clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => {
    toast.value = null
  }, 3000)
}

// 实时价格轮询（每30秒刷新一次最新K线价格）
let pricePollInterval: number | null = null

function startPricePoll() {
  if (pricePollInterval !== null) return
  pricePollInterval = window.setInterval(async () => {
    if (bars.value.length === 0) return
    try {
      const market = detectMarket(code.value)
      const lastBar = bars.value[bars.value.length - 1]
      const resp = await fetch(`/api/v1/bars/${market}/${code.value}/${category.value}?count=1`)
      if (resp.ok) {
        const data = await resp.json()
        if (data.bars && data.bars.length > 0) {
          const latest = data.bars[data.bars.length - 1]
          bars.value[bars.value.length - 1] = {
            ...lastBar,
            open: latest.close ?? lastBar.open,
            close: latest.close ?? lastBar.close,
            high: latest.high ?? lastBar.high,
            low: latest.low ?? lastBar.low,
          }
        }
      }
    } catch {
      // 静默失败
    }
  }, 30000)
}

function stopPricePoll() {
  if (pricePollInterval !== null) {
    clearInterval(pricePollInterval)
    pricePollInterval = null
  }
}

// URL 同步：周期与分析级别保持在 query 中，刷新/分享/回退后可复现
const route = useRoute()
const _qCat = String(route.query.category || '')
if (['DAY', 'WEEK', 'MIN_5', 'MIN_15', 'MIN_30', 'MIN_60'].includes(_qCat)) {
  category.value = _qCat as typeof category.value
}
if (route.query.level === 'xd' || String(route.query.level).startsWith('xd_l')) {
  analysisLevel.value = String(route.query.level) as AnalysisLevel
}
const _qDepth = Number(route.query.depth)
if (Number.isInteger(_qDepth) && _qDepth >= 1 && _qDepth <= 8) recursionDepth.value = _qDepth
watch([category, analysisLevel, recursionDepth], () => {
  router.replace({
    query: { category: category.value, level: analysisLevel.value, depth: recursionDepth.value },
  })
})

// 显隐开关偏好持久化：跨会话记住用户设置
watch([showZsds, showFractals, showMmds, showBcs, showZss, showMmdLabels], () => {
  try {
    localStorage.setItem('chanlun.showZsds', showZsds.value ? '1' : '0')
    localStorage.setItem('chanlun.showFractals', showFractals.value ? '1' : '0')
    localStorage.setItem('chanlun.showMmds', showMmds.value ? '1' : '0')
    localStorage.setItem('chanlun.showBcs', showBcs.value ? '1' : '0')
    localStorage.setItem('chanlun.showZss', showZss.value ? '1' : '0')
    localStorage.setItem('chanlun.showMmdLabels', showMmdLabels.value ? '1' : '0')
  } catch {
    // localStorage 不可用（隐私模式）时忽略持久化失败
  }
})

onMounted(() => {
  analyze()
  startPricePoll()
})

onUnmounted(() => {
  stopPricePoll()
})
</script>

<template>
  <div class="chanlun-view">
    <!-- 顶部配置栏 -->
    <div class="config-bar">
      <div class="field-group">
        <label>代码</label>
        <input v-model="code" type="text" placeholder="如 000001" maxlength="6" />
      </div>
      <div class="field-group">
        <label>周期</label>
        <PeriodSelect v-model="category" :options="['DAY', 'WEEK', 'MONTH', 'MIN_5', 'MIN_15', 'MIN_30', 'MIN_60']" />
      </div>
      <div class="field-group">
        <label>K 线根数</label>
        <input v-model.number="count" type="number" min="100" max="2000" step="100" />
      </div>
      <!-- V722: 全历史回溯 -->
      <div class="field-group">
        <button class="btn btn-secondary" :disabled="loadingEarlier || !hasEarlier" @click="loadEarlier">
          {{ loadingEarlier ? '加载中…' : '加载更早 ⏮' }}
        </button>
        <button v-if="bars.length > count || isTimeJump" class="btn btn-secondary" :disabled="loading" @click="isTimeJump ? backToLatestFromJump() : backToLatest()">
          回最新 ⏭
        </button>
      </div>
      <!-- V723: 任意日期区间跳转（时间旅行） -->
      <div class="field-group time-jump-group">
        <label>从</label>
        <input v-model="jumpStart" type="date" @keyup.enter="jumpToRange" />
        <label>到</label>
        <input v-model="jumpEnd" type="date" @keyup.enter="jumpToRange" />
        <button class="btn btn-secondary" :disabled="jumping || loading" @click="jumpToRange">
          {{ jumping ? '跳转中…' : '跳转 📅' }}
        </button>
        <span v-if="jumpError" class="jump-error">{{ jumpError }}</span>
      </div>
      <div class="field-group">
        <label> <input type="checkbox" v-model="multiLevel" /> 多级别联立 </label>
      </div>
      <div v-if="multiLevel" class="field-group">
        <label>低级别</label>
        <select v-model="lowLevel">
          <option value="MIN_5">5分钟</option>
          <option value="MIN_15">15分钟</option>
          <option value="MIN_30" selected>30分钟</option>
          <option value="MIN_60">60分钟</option>
        </select>
      </div>
      <div class="field-group">
        <label>分析级别</label>
        <select v-model="analysisLevel" @change="onAnalysisLevelChange">
          <option v-for="lvl in availableLevels" :key="lvl.key" :value="lvl.key">
            {{ lvl.label }}
          </option>
        </select>
      </div>
      <div class="field-group">
        <label>递归深度</label>
        <select v-model.number="recursionDepth">
          <option :value="1">1（线段级别）</option>
          <option :value="2">2</option>
          <option :value="3">3</option>
          <option :value="4">4</option>
          <option :value="5">5</option>
        </select>
      </div>
      <div class="field-group">
        <label> <input type="checkbox" v-model="showZsds" /> 走势段/趋势段 </label>
      </div>
      <div class="field-group">
        <label> <input type="checkbox" v-model="showFractals" /> 分型 </label>
      </div>
      <div class="field-group">
        <label> <input type="checkbox" v-model="showMmds" /> 买卖点 </label>
      </div>
      <div class="field-group">
        <label> <input type="checkbox" v-model="showBcs" /> 背驰 </label>
      </div>
      <div class="field-group">
        <label> <input type="checkbox" v-model="showZss" /> 中枢 </label>
      </div>
      <div class="field-group">
        <label> <input type="checkbox" v-model="showMmdLabels" /> 买卖点文字 </label>
      </div>
      <button class="primary analyze-btn" :disabled="loading" @click="analyze">
        {{ loading ? '分析中…' : '开始分析' }}
      </button>
      <button class="ghost" :disabled="loading || bars.length === 0" @click="goToBacktest">
        📈 去回测
      </button>
      <button
        class="ghost"
        :disabled="loading || bars.length === 0"
        @click="goToBacktestWithChanlun"
      >
        🔬 回测验证
      </button>
      <button v-if="!loading && bars.length > 0" class="ghost" @click="exportAnalysis">
        💾 导出分析
      </button>
      <button class="ghost" @click="copyShareLink">🔗 复制链接</button>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="error-banner">⚠ {{ error }}</div>

    <!-- Toast 通知 -->
    <transition name="toast">
      <div v-if="toast" class="toast" :class="toast.type">
        {{ toast.type === 'success' ? '✓' : toast.type === 'error' ? '✗' : 'ℹ' }}
        {{ toast.message }}
      </div>
    </transition>

    <!-- 最新信号详情卡片 -->
    <div
      v-if="!loading && latestMmd"
      class="latest-signal-card"
      :style="{ borderColor: MMD_COLORS[latestMmd.type] ?? '#94a3b8' }"
    >
      <div class="signal-card-header">
        <span class="signal-card-type" :style="{ color: MMD_COLORS[latestMmd.type] ?? '#fff' }">
          {{ latestMmd.type.toUpperCase() }}
        </span>
        <span class="signal-card-conf" :style="{ color: confidenceColor(latestMmd.confidence) }">
          置信度 {{ (latestMmd.confidence * 100).toFixed(0) }}%
        </span>
        <span class="signal-card-date">{{ latestMmd.date ?? '—' }}</span>
      </div>
      <div class="signal-card-body">{{ latestMmd.msg }}</div>
      <!-- V102: 决策支持卡片（条件264-267） -->
      <V102DecisionCard :mmd="latestMmd" />
      <div class="signal-card-actions">
        <button v-if="latestSignalType === 'buy'" class="ghost small" @click="quickWatch('buy')">
          👁 加入监控
        </button>
        <button v-if="latestSignalType === 'sell'" class="ghost small" @click="quickWatch('sell')">
          ⏰ 设置提醒
        </button>
        <button class="ghost small" @click="addToWatchlist">⭐ 加入自选</button>
        <button class="ghost small" @click="goToBacktest">📊 回测验证</button>
      </div>
    </div>

    <!-- 高置信度信号告警 -->
    <div v-if="!loading && strongSignals.length > 0" class="signal-alert">
      <div class="alert-title">🔔 高置信度信号（≥75%）</div>
      <div class="alert-items">
        <div
          v-for="s in strongSignals"
          :key="s.date + s.type"
          class="alert-item"
          :style="{ borderLeftColor: MMD_COLORS[s.type] ?? '#fff' }"
        >
          <span class="alert-type" :style="{ color: MMD_COLORS[s.type] ?? '#fff' }">{{
            s.type
          }}</span>
          <span class="alert-date">{{ s.date ?? '-' }}</span>
          <span class="alert-conf" :style="{ color: confidenceColor(s.confidence) }"
            >{{ (s.confidence * 100).toFixed(0) }}%</span
          >
          <span class="alert-msg">{{ s.msg }}</span>
        </div>
      </div>
    </div>

    <!-- 统计面板 -->
    <div v-if="!loading && bars.length > 0" class="stats-bar">
      <div class="stat-item">
        <span class="stat-label">K线</span>
        <span class="stat-value">{{ stats.klineCount }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">级别</span>
        <span class="stat-value" style="color: #60b4ff">{{ analysisLevelLabel }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">{{ analysisLevel === 'bi' ? '笔' : '本级段' }}</span>
        <span class="stat-value" style="color: #60b4ff">{{ stats.biCount }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">{{ analysisLevel === 'bi' ? '线段' : '递归段' }}</span>
        <span class="stat-value" style="color: #c878ff">{{ stats.xdCount }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">走势段</span>
        <span class="stat-value" style="color: #86efac">{{ stats.zsdCount }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">趋势段</span>
        <span class="stat-value" style="color: #fca5a5">{{ stats.qsdCount }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">中枢</span>
        <span class="stat-value" style="color: #ffc832">{{ stats.zsCount }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">一类买点</span>
        <span class="stat-value" style="color: #22c55e">{{ stats.buy1Count }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">一类卖点</span>
        <span class="stat-value" style="color: #ef4444">{{ stats.sell1Count }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">强买信号</span>
        <span class="stat-value" style="color: #22c55e">{{ stats.highConfBuyCount }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">强卖信号</span>
        <span class="stat-value" style="color: #ef4444">{{ stats.highConfSellCount }}</span>
      </div>
    </div>

    <!-- 市场状态 + 操作建议面板 -->
    <div
      v-if="!loading && marketState"
      class="advice-panel"
      :style="{ borderColor: marketState.actionColor }"
    >
      <div class="advice-header">
        <span class="advice-action" :style="{ color: marketState.actionColor }">
          {{ marketState.action }}
        </span>
        <span class="advice-price">当前价: {{ marketState.price.toFixed(2) }}</span>
        <span class="advice-zone" :style="{ color: zoneColor(marketState.priceZone) }">
          中枢位置: {{ zoneLabel(marketState.priceZone) }}
        </span>
        <span class="advice-trend" :style="{ color: marketState.trendColor }">
          趋势: {{ marketState.trend }}
        </span>
        <span v-if="valuation?.pe != null || valuation?.pb != null" class="advice-trend">
          <template v-if="valuation?.pe != null">动态PE {{ valuation.pe }}</template>
          <template v-if="valuation?.pe != null && valuation?.pb != null"> · </template>
          <template v-if="valuation?.pb != null">PB {{ valuation.pb }}</template>
        </span>
      </div>
      <div class="advice-body">
        <p class="advice-text" :style="{ color: marketState.adviceColor }">
          {{ marketState.advice }}
        </p>
        <p v-if="marketState.adviceDetail" class="advice-detail">{{ marketState.adviceDetail }}</p>
      </div>
      <div class="advice-meta">
        <span class="meta-item"> 最近买点: {{ marketState.daysSinceBuy }} 天前 </span>
        <span class="meta-item"> 最近卖点: {{ marketState.daysSinceSell }} 天前 </span>
        <span class="meta-item" v-if="marketState.zsRange > 0">
          中枢区间: {{ marketState.zsLow.toFixed(2) }} ~ {{ marketState.zsHigh.toFixed(2) }}
        </span>
      </div>
      <!-- 风险提示 -->
      <div
        v-if="marketState.daysSinceBuy > 30 || marketState.daysSinceSell > 30"
        class="risk-warning"
      >
        ⚠️ 距离最近信号已超过30天，市场环境可能已发生变化，请谨慎操作。
      </div>
      <div v-if="latestBuy && latestBuy.confidence < 0.6" class="risk-warning">
        ⚠️ 最近买入信号置信度较低（{{
          (latestBuy.confidence * 100).toFixed(0)
        }}%），建议结合其他指标确认。
      </div>
      <!-- 关键价位参考 -->
      <div v-if="marketState.zsRange > 0" class="price-levels">
        <div class="price-levels-title">📌 关键价位参考</div>
        <div class="price-levels-grid">
          <div class="price-level" :style="{ borderColor: '#22c55e' }">
            <span class="level-label">支撑位</span>
            <span class="level-value" style="color: #22c55e">{{
              marketState.zsLow.toFixed(2)
            }}</span>
          </div>
          <div class="price-level" :style="{ borderColor: '#fbbf24' }">
            <span class="level-label">中枢中轴</span>
            <span class="level-value" style="color: #fbbf24">{{
              marketState.zsMid.toFixed(2)
            }}</span>
          </div>
          <div class="price-level" :style="{ borderColor: '#ef4444' }">
            <span class="level-label">压力位</span>
            <span class="level-value" style="color: #ef4444">{{
              marketState.zsHigh.toFixed(2)
            }}</span>
          </div>
          <div
            class="price-level"
            :style="{
              borderColor: marketState.price >= marketState.zsHigh ? '#22c55e' : '#f97316',
            }"
          >
            <span class="level-label">当前价</span>
            <span class="level-value">{{ marketState.price.toFixed(2) }}</span>
          </div>
        </div>
      </div>
      <!-- BOLL辅助信息 -->
      <div v-if="bollInfo" class="boll-info">
        <div class="boll-title">📊 BOLL 辅助分析</div>
        <div class="boll-grid">
          <div class="boll-item">
            <span class="boll-label">价格位置</span>
            <span
              class="boll-value"
              :style="{
                color:
                  bollInfo.zone === 'above'
                    ? '#22c55e'
                    : bollInfo.zone === 'below'
                      ? '#ef4444'
                      : '#fbbf24',
              }"
            >
              {{
                bollInfo.zone === 'above'
                  ? '上轨上方'
                  : bollInfo.zone === 'below'
                    ? '下轨下方'
                    : '轨道内'
              }}
            </span>
            <span class="boll-pb">%B: {{ (bollInfo.percent_b * 100).toFixed(0) }}%</span>
          </div>
          <div class="boll-item">
            <span class="boll-label">上轨</span>
            <span class="boll-val-up">{{ bollInfo.upper.toFixed(2) }}</span>
            <span class="boll-label">中轨</span>
            <span class="boll-val-mid">{{ bollInfo.mid.toFixed(2) }}</span>
            <span class="boll-label">下轨</span>
            <span class="boll-val-low">{{ bollInfo.lower.toFixed(2) }}</span>
          </div>
          <div class="boll-item">
            <span class="boll-label">带宽</span>
            <span class="boll-value">{{ (bollInfo.width * 100).toFixed(2) }}%</span>
            <span class="boll-confluence">{{ bollConfluence }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 缠论图表 -->
    <div v-if="!loading && bars.length > 0" class="chart-area">
      <ChanlunChart
        :bars="bars"
        :bis="bis"
        :xds="xds"
        :zsds="zsds"
        :qsds="qsds"
        :show-zsds="showZsds"
        :show-fractals="showFractals"
        :show-mmds="showMmds"
        :show-bcs="showBcs"
        :show-zss="showZss"
        :show-mmd-labels="showMmdLabels"
        :zss="zss"
        :mmds="mmds"
        :fxs="fxs"
        :validFxs="validFxs"
        :bcs="bcs"
        :macd="macd ?? undefined"
        :frequency="category"
      />
    </div>

    <!-- 买卖点列表 -->
    <div v-if="!loading && mmds.length > 0" class="mmd-list">
      <h3>买卖点明细（{{ mmds.length }} 个）</h3>
      <!-- 信号统计摘要 -->
      <div class="signal-summary">
        <div class="summary-item" v-for="(count, type) in stats.typeCounts" :key="type">
          <span class="summary-type" :style="{ color: MMD_COLORS[type] ?? '#fff' }">{{
            type
          }}</span>
          <span class="summary-count">{{ count }}</span>
        </div>
        <div class="summary-sep"></div>
        <div
          class="summary-item"
          v-for="(count, grade) in stats.gradeCounts"
          :key="grade"
          v-if="count > 0"
        >
          <span class="summary-grade" :style="{ color: qualityColor(grade), fontWeight: 700 }">{{
            grade
          }}</span>
          <span class="summary-count">{{ count }}</span>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th>类型</th>
            <th>日期</th>
            <th>置信度</th>
            <th>质量</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="m in mmds"
            :key="m.date + m.type"
            :style="{ color: MMD_COLORS[m.type] ?? '#fff' }"
          >
            <td>
              <strong>{{ m.type }}</strong>
            </td>
            <td>{{ m.date ?? '-' }}</td>
            <td>
              <span
                class="conf-badge"
                :style="{
                  background: confidenceColor(m.confidence) + '22',
                  color: confidenceColor(m.confidence),
                }"
              >
                {{ (m.confidence * 100).toFixed(0) }}%
              </span>
            </td>
            <td>
              <span
                v-if="m.quality"
                class="quality-badge"
                :style="{
                  background: qualityColor(m.quality.grade) + '22',
                  color: qualityColor(m.quality.grade),
                  borderColor: qualityColor(m.quality.grade),
                }"
              >
                {{ m.quality.grade }} · {{ m.quality.score }}分
              </span>
              <span
                v-else
                class="quality-badge"
                style="background: #33415522; color: #94a3b8; border: 1px solid #475569"
                >-</span
              >
              <!-- V102: 信号质量评分卡评级 -->
              <span
                v-if="m.v102_signal_quality?.overall_grade"
                class="v102-grade-badge"
                :class="'g' + m.v102_signal_quality.overall_grade"
              >
                V102·{{ m.v102_signal_quality.overall_grade }}
              </span>
              <!-- 区间套徽章（口径区分）
                   method='cross_period' = 真实双周期数据（缠论原文语义，可用）；
                   其他（recursive/single）= 同序列递归或单级别近似，
                   实测确认率仅 3%（真跨周期 50%），不得当作"真区间套"呈现。
                   见 docs/区间套现状说明与统一方案.md §七 实测证伪。 -->
              <span
                v-if="m.qujiantao"
                class="qt-badge"
                :class="
                  m.qujiantao.method === 'cross_period'
                    ? m.qujiantao.nested
                      ? 'qt-ok'
                      : 'qt-no'
                    : m.qujiantao.nested
                      ? 'qt-recursive'
                      : 'qt-no'
                "
                :title="
                  m.qujiantao.method === 'cross_period'
                    ? m.qujiantao.msg
                    : '⚠ 非真跨周期：本标记来自同序列递归级别（或单级别近似），实测确认率约 3%，不能等同于缠论原文的区间套。' + m.qujiantao.msg
                "
              >
                {{
                  m.qujiantao.method === 'cross_period'
                    ? m.qujiantao.nested
                      ? '🔗 套'
                      : '🔗✗'
                    : m.qujiantao.nested
                      ? '🔗 级?'
                      : '🔗✗'
                }}{{ (m.qujiantao.score * 100).toFixed(0) }}
              </span>
            </td>
            <td>{{ m.msg }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- V341: 信号历史回溯（V102 建议 + 事后 N 日表现） -->
    <div v-if="!loading && signalHistory.length > 0" class="mmd-history">
      <h3>
        🕰 信号历史回溯（V102 建议 + 事后表现）
        <button class="ghost small" @click="exportHistoryCsv">📊 导出 CSV</button>
      </h3>
      <table>
        <thead>
          <tr>
            <th>类型</th>
            <th>日期</th>
            <th>V102质量</th>
            <th>建议（入场/止损/止盈）</th>
            <th>5日后</th>
            <th>10日后</th>
            <th>20日后</th>
            <th>20日命中</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(s, i) in signalHistory"
            :key="i"
            :style="{ color: MMD_COLORS[s.type] ?? '#fff' }"
          >
            <td>
              <strong>{{ s.type }}</strong>
            </td>
            <td>{{ s.date ?? '-' }}</td>
            <td>
              <span v-if="s.grade" class="v102-grade-badge" :class="'g' + s.grade"
                >V102·{{ s.grade }}</span
              >
              <span v-else class="dim">-</span>
            </td>
            <td class="hist-advice">
              <span v-if="s.entry != null"
                >{{ s.entry.toFixed(2) }} / {{ s.stop != null ? s.stop.toFixed(2) : '-' }} /
                {{ s.tp1 != null ? s.tp1.toFixed(2) : '-' }}</span
              >
              <span
                v-if="s.advice"
                class="hist-advice-text"
                :class="{
                  'adv-buy': s.advice.includes('买入'),
                  'adv-sell': s.advice.includes('卖出'),
                }"
                >{{ s.advice }}</span
              >
              <span v-if="s.entry == null" class="dim">非3买/3卖，无建议</span>
            </td>
            <td :class="s.ret5 != null ? (s.ret5 >= 0 ? 'acc-pos' : 'acc-neg') : 'dim'">
              {{ s.ret5 != null ? (s.ret5 >= 0 ? '+' : '') + s.ret5 + '%' : '-' }}
            </td>
            <td :class="s.ret10 != null ? (s.ret10 >= 0 ? 'acc-pos' : 'acc-neg') : 'dim'">
              {{ s.ret10 != null ? (s.ret10 >= 0 ? '+' : '') + s.ret10 + '%' : '-' }}
            </td>
            <td :class="s.ret20 != null ? (s.ret20 >= 0 ? 'acc-pos' : 'acc-neg') : 'dim'">
              {{ s.ret20 != null ? (s.ret20 >= 0 ? '+' : '') + s.ret20 + '%' : '-' }}
            </td>
            <td>
              <span :class="['verdict', s.hit20 ? 'ok' : 'miss']">{{ s.hit20 ? '✓' : '✗' }}</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p class="acc-legend">
        逐笔买卖点信号：显示 V102 建议（入场/止损/止盈，仅 3买/3卖 有）与信号后 5/10/20
        根K线的实际表现； 20日命中 = 买点后 20 根收涨 / 卖点后 20
        根收跌。用历史逐笔验证模型建议是否可靠。
      </p>
    </div>

    <!-- 买卖点分类准确度验证 -->
    <div v-if="!loading && signalAccuracy && signalAccuracy.ranking?.length" class="mmd-accuracy">
      <h3>🎯 买卖点准确度验证（命中率 vs 随机基准）</h3>
      <div class="acc-horizon">
        <label>持有期</label>
        <select v-model="accHorizon">
          <option value="3">3 根</option>
          <option value="5">5 根</option>
          <option value="10">10 根</option>
          <option value="20">20 根</option>
        </select>
      </div>
      <div v-if="signalAccuracy.summary" class="accuracy-summary">{{ signalAccuracy.summary }}</div>
      <table>
        <thead>
          <tr>
            <th>信号类型</th>
            <th>信号数</th>
            <th>5根命中率</th>
            <th>随机基准</th>
            <th>超额命中率</th>
            <th>5根均值收益</th>
            <th>盈亏比</th>
            <th>结论</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="rank in signalAccuracy.ranking"
            :key="rank.type"
            :style="{ color: MMD_COLORS[rank.type] ?? '#fff' }"
          >
            <td>
              <strong>{{ rank.type }}</strong>
            </td>
            <td>{{ rank.signals }}</td>
            <td>{{ fmtAccPct(rank.hit_rate) }}</td>
            <td class="dim">{{ fmtAccPct(byTypeHorizon(rank.type)?.baseline_hit_rate) }}</td>
            <td
              :class="
                rank.excess_hit_rate >= 0.02
                  ? 'acc-pos'
                  : rank.excess_hit_rate <= -0.02
                    ? 'acc-neg'
                    : ''
              "
            >
              {{ fmtAccSigned(rank.excess_hit_rate) }}
            </td>
            <td :class="rank.avg_return >= 0 ? 'acc-pos' : 'acc-neg'">
              {{ fmtAccPct(rank.avg_return) }}
            </td>
            <td>
              {{ rank.profit_factor != null ? fmtPf(rank.profit_factor) : '—' }}
            </td>
            <td class="verdict-cell">{{ rank.verdict }}</td>
          </tr>
        </tbody>
      </table>
      <p class="acc-legend">
        命中 = 买点后 5 根上涨 / 卖点后 5 根下跌。随机基准 = 同期任意一天进场的平均命中率；
        超额命中率 &gt; 0 说明该类型信号比随机择时更准。前瞻收益不含交易成本。
      </p>
    </div>

    <!-- 多级别联立分析结果 -->
    <div v-if="!loading && multiLevelResult" class="multi-level-panel">
      <h3>📊 多级别区间套分析（{{ category }} ↔ {{ lowLevel }}）</h3>
      <div class="ml-grid">
        <div
          class="ml-card"
          :style="{ borderColor: mlConfColor(multiLevelResult.confluence?.score ?? 0) }"
        >
          <div class="ml-card-title">一致性评分</div>
          <div
            class="ml-card-value"
            :style="{ color: mlConfColor(multiLevelResult.confluence?.score ?? 0) }"
          >
            {{ ((multiLevelResult.confluence?.score ?? 0) * 100).toFixed(0) }}%
          </div>
          <div class="ml-card-desc">{{ mlConfLabel(multiLevelResult.confluence?.score ?? 0) }}</div>
        </div>
        <div class="ml-card">
          <div class="ml-card-title">趋势对齐</div>
          <div
            class="ml-card-value"
            :style="{ color: multiLevelResult.confluence?.trend_aligned ? '#22c55e' : '#ef4444' }"
          >
            {{ multiLevelResult.confluence?.trend_aligned ? '✓ 一致' : '✗ 不一致' }}
          </div>
          <div class="ml-card-desc">高低级别买卖点方向是否相同</div>
        </div>
        <div class="ml-card">
          <div class="ml-card-title">中枢对齐</div>
          <div
            class="ml-card-value"
            :style="{ color: multiLevelResult.confluence?.zs_aligned ? '#22c55e' : '#94a3b8' }"
          >
            {{ multiLevelResult.confluence?.zs_aligned ? '✓ 有重叠' : '✗ 无重叠' }}
          </div>
          <div class="ml-card-desc">低级别中枢是否与高级别信号时间重叠</div>
        </div>
        <div class="ml-card">
          <div class="ml-card-title">时间对齐</div>
          <div
            class="ml-card-value"
            :style="{ color: multiLevelResult.confluence?.time_aligned ? '#22c55e' : '#fbbf24' }"
          >
            {{ multiLevelResult.confluence?.time_aligned ? '✓ 同步' : '○ 滞后' }}
          </div>
          <div class="ml-card-desc">高低级别信号是否在相近时间窗口</div>
        </div>
      </div>
      <!-- 低级别走势信息 -->
      <div v-if="multiLevelResult.low_level_qs" class="ml-detail">
        <div class="ml-detail-title">低级别（{{ lowLevel }}）走势结构</div>
        <div class="ml-detail-grid">
          <span class="ml-detail-item">笔数: {{ multiLevelResult.low_level_qs.bi_count }}</span>
          <span class="ml-detail-item">中枢数: {{ multiLevelResult.low_level_qs.zs_count }}</span>
          <span class="ml-detail-item">
            趋势:
            <span
              :style="{
                color:
                  multiLevelResult.low_level_qs.trend_direction === 'up'
                    ? '#22c55e'
                    : multiLevelResult.low_level_qs.trend_direction === 'down'
                      ? '#ef4444'
                      : '#94a3b8',
              }"
            >
              {{
                multiLevelResult.low_level_qs.trend_direction === 'up'
                  ? '↑ 上升'
                  : multiLevelResult.low_level_qs.trend_direction === 'down'
                    ? '↓ 下降'
                    : '— 盘整'
              }}
            </span>
          </span>
          <span class="ml-detail-item"
            >背驰可能: {{ multiLevelResult.low_level_qs.divergence_possible ? '是' : '否' }}</span
          >
        </div>
      </div>
      <!-- 低级别买卖点预览 -->
      <div v-if="multiLevelResult.low_level?.mmds?.length" class="ml-low-signals">
        <div class="ml-detail-title">低级别买卖点（最近5个）</div>
        <div class="ml-signal-list">
          <div
            v-for="m in multiLevelResult.low_level.mmds.slice(-5).reverse()"
            :key="m.date + m.type"
            class="ml-signal-item"
            :style="{ borderLeftColor: MMD_COLORS[m.type] ?? '#fff' }"
          >
            <span class="ml-signal-type" :style="{ color: MMD_COLORS[m.type] ?? '#fff' }">{{
              m.type
            }}</span>
            <span class="ml-signal-date">{{ m.date ?? '-' }}</span>
            <span class="ml-signal-conf" :style="{ color: confidenceColor(m.confidence ?? 0) }"
              >{{ ((m.confidence ?? 0) * 100).toFixed(0) }}%</span
            >
            <span class="ml-signal-msg">{{ m.msg }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!loading && bars.length === 0 && !error" class="placeholder">
      <p>输入股票代码后点击「开始分析」</p>
      <p class="hint">支持 A 股日线/周线/分钟线，如 000001（平安银行）、600519（茅台）</p>
    </div>
  </div>
</template>

<style scoped>
.chanlun-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
  padding: 16px 20px;
  gap: 16px;
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

.field-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.field-group label {
  font-size: 11px;
  color: var(--text-muted);
}

.field-group input,
.field-group select {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 10px;
  font-size: 13px;
  color: var(--text);
  width: 110px;
}

.field-group input[type='text'] {
  width: 90px;
}

/* V723: 日期跳转行——横向排列的日期选择器（与其他纵向 field-group 区分） */
.time-jump-group {
  flex-direction: row;
  align-items: center;
  gap: 6px;
}

.time-jump-group label {
  margin: 0;
  white-space: nowrap;
}

.time-jump-group input[type='date'] {
  width: 130px;
  padding: 6px 8px;
  height: 34px;
}

.jump-error {
  font-size: 11px;
  color: var(--up);
  max-width: 200px;
  white-space: normal;
}

.analyze-btn {
  padding: 7px 20px;
  font-size: 13px;
  height: 34px;
}

.error-banner {
  background: rgba(239, 65, 70, 0.12);
  border: 1px solid var(--up);
  color: var(--up);
  padding: 10px 14px;
  border-radius: var(--radius);
  font-size: 13px;
}

.stats-bar {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 16px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.stat-label {
  font-size: 11px;
  color: var(--text-dim);
}

.stat-value {
  font-size: 18px;
  font-weight: 600;
  color: var(--text);
}

.chart-area {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.mmd-list {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
}

.mmd-list h3 {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 10px;
}

.signal-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}

.summary-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 4px;
  font-size: 12px;
}

.summary-type {
  font-weight: 600;
}

.summary-grade {
  font-weight: 700;
  letter-spacing: 0.5px;
}

.summary-sep {
  width: 1px;
  background: var(--border);
  margin: 0 4px;
}

.summary-count {
  font-weight: 700;
  color: var(--text);
  background: rgba(255, 255, 255, 0.08);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 11px;
}

.mmd-list table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.mmd-list th {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  color: var(--text-dim);
  font-weight: 500;
}

.mmd-list td {
  padding: 5px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  color: var(--text);
}

.mmd-list tr:last-child td {
  border-bottom: none;
}

.placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 300px;
  color: var(--text-dim);
  gap: 8px;
}
/* V341: 信号历史回溯面板 */
.mmd-history {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
}
.mmd-history h3 {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 10px;
}
.mmd-history table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.mmd-history th {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  color: var(--text-dim);
  font-weight: 500;
}
.mmd-history td {
  padding: 5px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  color: var(--text);
}
.mmd-history tr:last-child td {
  border-bottom: none;
}
.mmd-history .dim {
  color: var(--text-dim);
}
.hist-advice {
  font-family: var(--font-mono);
}
.hist-advice-text {
  display: block;
  font-family: inherit;
  font-size: 11px;
  font-weight: 600;
  max-width: 260px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hist-advice-text.adv-buy {
  color: #22c55e;
}
.hist-advice-text.adv-sell {
  color: #ef4444;
}
.mmd-history .verdict.ok {
  color: var(--up);
}
.mmd-history .verdict.miss {
  color: var(--down);
}
.mmd-accuracy {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
}
.acc-horizon {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0;
}
.acc-horizon label {
  font-size: 12px;
  color: var(--text-dim);
}
.acc-horizon select {
  background: #111827;
  border: 1px solid #2a2e3a;
  color: #e5e7eb;
  padding: 4px 8px;
  border-radius: 4px;
}
.mmd-accuracy h3 {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 10px;
}
.accuracy-summary {
  font-size: 13px;
  color: var(--text);
  padding: 8px 10px;
  margin-bottom: 10px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
  line-height: 1.5;
}
.mmd-accuracy table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.mmd-accuracy th {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  color: var(--text-dim);
  font-weight: 500;
}
.mmd-accuracy td {
  padding: 5px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  color: var(--text);
}
.mmd-accuracy tr:last-child td {
  border-bottom: none;
}
.mmd-accuracy .dim {
  color: var(--text-dim);
}
.acc-pos {
  color: var(--up);
}
.acc-neg {
  color: var(--down);
}
.acc-legend {
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.6;
  margin: 10px 0 0;
}
.verdict-cell {
  color: var(--text-muted) !important;
}

.hint {
  font-size: 12px;
  color: var(--text-dim);
  opacity: 0.7;
}

/* 最新信号详情卡片 */
.latest-signal-card {
  background: var(--bg-panel);
  border: 1px solid;
  border-left: 4px solid;
  border-radius: var(--radius);
  padding: 14px 18px;
}

.signal-card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.signal-card-type {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 1px;
}

.signal-card-conf {
  font-size: 13px;
  font-weight: 600;
}

.signal-card-date {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: auto;
}

.signal-card-body {
  font-size: 13px;
  color: var(--text);
  line-height: 1.5;
  margin-bottom: 10px;
}

.signal-card-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.signal-card-actions .ghost {
  font-size: 12px;
  padding: 4px 10px;
}

.signal-alert {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 16px;
}

.alert-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 8px;
}

.alert-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.alert-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 6px;
  border-left: 3px solid;
  font-size: 12px;
}

.alert-type {
  font-weight: 700;
  min-width: 48px;
}

.alert-date {
  color: var(--text-muted);
  min-width: 90px;
}

.alert-conf {
  font-weight: 600;
  min-width: 40px;
}

.alert-msg {
  color: var(--text-dim);
  flex: 1;
}

.conf-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}

.quality-badge {
  display: inline-block;
  padding: 1px 7px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  border: 1px solid;
  letter-spacing: 0.5px;
}

/* V102: 信号质量评分卡评级徽章 */
.v102-grade-badge {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 0.3px;
}
.v102-grade-badge.gA {
  background: #22c55e;
}
.v102-grade-badge.gB {
  background: #3b82f6;
}
.v102-grade-badge.gC {
  background: #f59e0b;
}
.v102-grade-badge.gD {
  background: #ef4444;
}

/* 区间套徽章：qt-ok(青)=真实双周期确认；qt-recursive(橙)=递归/单级别近似，
   仅作参考；qt-no(灰)=未确认。三种口径必须视觉可辨，见 §七 实测证伪。 */
.qt-badge {
  display: inline-block;
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.3px;
  cursor: help;
}
.qt-badge.qt-ok {
  background: #0e7490;
  color: #a5f3fc;
}
.qt-badge.qt-no {
  background: #334155;
  color: #94a3b8;
}
/* 同序列递归/单级别近似口径：与"真跨周期"（qt-ok）视觉上区分开，
   避免用户把它当成缠论原文的区间套确认（实测确认率 3% vs 50%）。 */
.qt-badge.qt-recursive {
  background: #78350f;
  color: #fcd34d;
}

/* 操作建议面板 */
.advice-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-left: 4px solid;
  border-radius: var(--radius);
  padding: 14px 18px;
}

.advice-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.advice-action {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: 2px;
}

.advice-price {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}

.advice-zone {
  font-size: 12px;
  font-weight: 500;
}

.advice-trend {
  font-size: 12px;
  font-weight: 500;
  margin-left: auto;
}

.advice-body {
  margin-bottom: 8px;
}

.advice-text {
  font-size: 13px;
  line-height: 1.6;
  margin: 0 0 4px 0;
}

.advice-detail {
  font-size: 12px;
  color: var(--text-dim);
  margin: 0;
  line-height: 1.5;
}

.advice-meta {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.meta-item {
  font-size: 11px;
  color: var(--text-muted);
  background: rgba(255, 255, 255, 0.04);
  padding: 2px 8px;
  border-radius: 4px;
}

/* 多级别联立分析面板 */
.multi-level-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 18px;
}

.multi-level-panel h3 {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 12px;
}

.ml-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.ml-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid;
  border-radius: 8px;
  padding: 10px 12px;
  text-align: center;
}

.ml-card-title {
  font-size: 11px;
  color: var(--text-dim);
  margin-bottom: 4px;
}

.ml-card-value {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 2px;
}

.ml-card-desc {
  font-size: 10px;
  color: var(--text-muted);
  line-height: 1.3;
}

.ml-detail {
  border-top: 1px solid var(--border);
  padding-top: 10px;
  margin-top: 4px;
}

.ml-detail-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.ml-detail-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: var(--text);
}

.ml-detail-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.ml-low-signals {
  border-top: 1px solid var(--border);
  padding-top: 10px;
  margin-top: 8px;
}

.ml-signal-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ml-signal-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 4px;
  border-left: 3px solid;
  font-size: 11px;
}

.ml-signal-type {
  font-weight: 700;
  min-width: 40px;
}

.ml-signal-date {
  color: var(--text-muted);
  min-width: 80px;
}

.ml-signal-conf {
  font-weight: 600;
  min-width: 36px;
}

.ml-signal-msg {
  color: var(--text-dim);
  flex: 1;
}

/* 关键价位参考 */
.price-levels {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

.price-levels-title {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.price-levels-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 6px;
}

.price-level {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 6px 4px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 4px;
  border-left: 2px solid;
}

.level-label {
  font-size: 10px;
  color: var(--text-dim);
  margin-bottom: 2px;
}

.level-value {
  font-size: 14px;
  font-weight: 700;
  font-family: var(--font-mono);
}

/* 风险提示 */
.risk-warning {
  margin-top: 8px;
  padding: 6px 10px;
  background: rgba(239, 65, 70, 0.08);
  border: 1px solid rgba(239, 65, 70, 0.3);
  border-radius: 4px;
  font-size: 11px;
  color: #fca5a5;
  line-height: 1.4;
}

/* BOLL辅助信息 */
.boll-info {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

.boll-title {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 6px;
}

.boll-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.boll-item {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 11px;
}

.boll-label {
  color: var(--text-dim);
  font-size: 10px;
}

.boll-value {
  font-weight: 600;
  color: var(--text);
}

.boll-val-up {
  color: #22c55e;
  font-weight: 600;
}
.boll-val-mid {
  color: #f59e0b;
  font-weight: 600;
}
.boll-val-low {
  color: #ef4444;
  font-weight: 600;
}

.boll-pb {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-muted);
}

.boll-confluence {
  margin-left: auto;
  font-size: 10px;
  padding: 1px 6px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 3px;
  color: var(--text-muted);
}

/* Toast 通知 */
.toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  padding: 10px 20px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  z-index: 1000;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  gap: 8px;
}
.toast.success {
  background: rgba(34, 197, 94, 0.9);
  color: #fff;
}
.toast.error {
  background: rgba(239, 65, 70, 0.9);
  color: #fff;
}
.toast.info {
  background: rgba(59, 130, 246, 0.9);
  color: #fff;
}
.toast-enter-active,
.toast-leave-active {
  transition:
    opacity 0.3s,
    transform 0.3s;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translate(-50%, 10px);
}
</style>
