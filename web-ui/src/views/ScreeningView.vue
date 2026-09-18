<script setup lang="ts">
// 长赢动态选股 + 缠论回测页面
// 功能：选择历史日期 → 长赢模型选股 → 缠论买卖点回测

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import ChanlunChart from '../components/ChanlunChart.vue'
import EquityChart from '../components/EquityChart.vue'
import { fetchBars, formatError, saveStrategy } from '../api'
import { fmtPct } from '../format'
import type { Bar } from '../types'

// ── 状态变量 ────────────────────────────────────────────────────────────
const router = useRouter()
const market = ref<'SZ' | 'SH'>('SZ')
const selectDate = ref('')
const scanning = ref(false)
const scanProgress = ref(0)
const scanTotal = ref(0)

// 选股结果前瞻收益验证
const scanPool = ref<string[]>([]) // 本次扫描的全部股票（选中+未选中，symbol 规范为 市场:代码）
const verifyResult = ref<any>(null)
const verifyLoading = ref(false)
const scanCurrent = ref(0)
const error = ref('')

// 选股结果
interface StockResult {
  code: string
  market: string
  symbol: string
  quality_score: number
  kline_count: number
  bi_count: number
  zs_count: number
  buy_1_count: number
  sell_1_count: number
  latest_mmd: {
    type: string
    date: string
    price: number
    v102_signal_quality?: {
      overall_grade: string
      overall_score: number
      strength: string
      confidence_adjust: number
    } | null
    v102_decision_support?: {
      entry_price: number
      stop_loss: number
      take_profit_1: number
      risk_reward_ratio: number
      position_size_pct: number
      action_recommendation: string
    } | null
    v102_pattern_match?: {
      similar_patterns_found: number
      win_rate: number
      avg_return: number
    } | null
  } | null
  classification: string
  // 新增：用于快速操作建议
  days_since_signal?: number
  signal_strength?: string
}

// 计算推荐操作（响应式）

const qualifiedStocks = ref<StockResult[]>([])
const selectedStock = ref<StockResult | null>(null)

// 缠论数据
const bars = ref<Bar[]>([])
const chanlunBis = ref<any[]>([])
const chanlunXds = ref<any[]>([])
const chanlunZss = ref<any[]>([])
const chanlunMmds = ref<any[]>([])
const chanlunFxs = ref<any[]>([])
const chanlunBcs = ref<any[]>([])
const chanlunZsds = ref<any[]>([])
const chanlunQsds = ref<any[]>([])
const chanlunMacd = ref<{ dif: number[]; dea: number[]; hist: number[] } | null>(null)
const chanlunLoading = ref(false)
const chanlunCategory = ref<'DAY' | 'WEEK' | 'MIN_5' | 'MIN_15' | 'MIN_30' | 'MIN_60'>('DAY')

// 回测结果
interface BacktestResult {
  performance: any
  equity_curve: any[]
  trades: any[]
}
const backtestResult = ref<BacktestResult | null>(null)
const backtestLoading = ref(false)

// 股票分类颜色
const CLASSIFICATION_COLORS: Record<string, string> = {
  tree: '#22c55e',
  grain: '#f59e0b',
  vegetable: '#ef4444',
}

const CLASSIFICATION_LABELS: Record<string, string> = {
  tree: '🌳 树型',
  grain: '🌾 粮型',
  vegetable: '🥬 菜型',
}

// 推荐操作颜色
const ACTION_COLORS: Record<string, string> = {
  buy: '#22c55e',
  sell: '#ef4444',
  hold: '#f59e0b',
  wait: '#60a5fa',
}

const ACTION_LABELS: Record<string, string> = {
  buy: '🟢 可买入',
  sell: '🔴 建议卖出',
  hold: '🟡 持有观察',
  wait: '🔵 暂时观望',
}

/**
 * 根据最新买卖点和股票分类，给出操作建议。
 * - 最新是一类买点 + 树型/粮型 → 买入
 * - 最新是一类卖点 + 菜型 → 卖出
 * - 有买卖点但方向不明确 → 持有
 * - 无买卖点信号 → 观望
 */
function getRecommendation(stock: StockResult): { action: string; label: string } {
  const latest = stock.latest_mmd
  if (!latest) return { action: 'wait', label: ACTION_LABELS.wait }

  const isBuy = latest.type.includes('buy')
  const isSell = latest.type.includes('sell')
  const isType1 = latest.type.startsWith('1')

  if (isBuy && isType1 && (stock.classification === 'tree' || stock.classification === 'grain')) {
    return { action: 'buy', label: ACTION_LABELS.buy }
  }
  if (isSell && isType1 && stock.classification === 'vegetable') {
    return { action: 'sell', label: ACTION_LABELS.sell }
  }
  if (isBuy || isSell) {
    return { action: 'hold', label: ACTION_LABELS.hold }
  }
  return { action: 'wait', label: ACTION_LABELS.wait }
}
// V277: 选股清单导出 CSV（筛选结果明细，Excel 友好）
const screenListCsvMsg = ref('')
function screenCsvEscape(v: string): string {
  return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v
}
function exportScreenListCsv() {
  if (!qualifiedStocks.value.length) return
  const header = [
    '代码',
    '分类',
    '质量分',
    '1买数',
    '1卖数',
    '最新信号',
    '信号日期',
    '距今天数',
    '操作建议',
  ]
  const rows = qualifiedStocks.value.map((s) => {
    const rec = getRecommendation(s)
    return [
      screenCsvEscape(s.symbol),
      screenCsvEscape(CLASSIFICATION_LABELS[s.classification] ?? s.classification),
      String(s.quality_score ?? ''),
      String(s.buy_1_count ?? ''),
      String(s.sell_1_count ?? ''),
      screenCsvEscape(s.latest_mmd?.type ?? ''),
      screenCsvEscape(s.latest_mmd?.date ?? ''),
      s.days_since_signal !== undefined && s.days_since_signal < 999
        ? String(s.days_since_signal)
        : '-',
      screenCsvEscape(rec.label),
    ].join(',')
  })
  const csv = '\uFEFF' + [header.join(','), ...rows].join('\n')
  try {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'easy_tdx_screen_list_' + new Date().toISOString().slice(0, 10) + '.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    screenListCsvMsg.value = '✓ 已导出选股清单 CSV'
  } catch {
    screenListCsvMsg.value = '导出失败（浏览器权限）'
  }
  setTimeout(() => {
    screenListCsvMsg.value = ''
  }, 2500)
}
// V283: 选股清单复制 JSON（机器可读，Agent/脚本友好）
const screenListJsonMsg = ref('')
async function copyScreenListJson() {
  if (!qualifiedStocks.value.length) return
  const payload = {
    generated_at: new Date().toISOString(),
    total: qualifiedStocks.value.length,
    stocks: qualifiedStocks.value.map((s) => ({
      symbol: s.symbol,
      classification: s.classification,
      quality_score: s.quality_score,
      buy_1_count: s.buy_1_count,
      sell_1_count: s.sell_1_count,
      latest_mmd: s.latest_mmd,
      days_since_signal: s.days_since_signal,
      recommendation: getRecommendation(s).label,
    })),
  }
  try {
    await navigator.clipboard.writeText(JSON.stringify(payload, null, 2))
    screenListJsonMsg.value = '✓ 已复制选股清单 JSON'
  } catch {
    screenListJsonMsg.value = '复制失败（浏览器权限）'
  }
  setTimeout(() => {
    screenListJsonMsg.value = ''
  }, 2500)
}

/** 获取操作建议的详细解释 */
function getActionExplanation(stock: StockResult): string {
  const latest = stock.latest_mmd
  const rec = getRecommendation(stock)

  if (!latest) return '暂无缠论买卖点信号，建议持续观察'

  const daysSince = stock.days_since_signal ?? 0

  if (rec.action === 'buy') {
    if (daysSince <= 5)
      return `最近 ${daysSince} 天前出现${latest.type}信号，建议密切关注，可考虑分批建仓`
    if (daysSince <= 15) return `信号出现 ${daysSince} 天前，若价格未跌破支撑位，可考虑加仓`
    return `信号出现 ${daysSince} 天前，建议评估当前价格是否仍在支撑位上方`
  }
  if (rec.action === 'sell') {
    if (daysSince <= 5) return `最近 ${daysSince} 天前出现${latest.type}信号，建议减仓或离场`
    return `信号出现 ${daysSince} 天前，建议评估是否需要止盈`
  }
  if (rec.action === 'hold') {
    return `有${latest.type}信号但分类不明确，建议持有观察，等待更明确的趋势确认`
  }
  return '暂无明确信号'
}

// ── 跳转到技术诊断页 ─────────────────────────────────────────────────────
function goToDiagnosis(stock: StockResult) {
  router.push({ path: '/diagnosis', query: { code: stock.code, market: stock.market } })
}

// ── 扫描函数 ────────────────────────────────────────────────────────────
async function scanStocks() {
  if (!selectDate.value) {
    error.value = '请选择历史日期'
    return
  }

  scanning.value = true
  scanProgress.value = 0
  scanTotal.value = 100
  scanCurrent.value = 0
  error.value = ''
  qualifiedStocks.value = []

  try {
    const resp = await fetch('/api/v1/screening/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date: selectDate.value,
        market: market.value,
        min_klines: 100,
        season_filter: true,
        stock_type: 'all',
      }),
    })

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }

    const data = await resp.json()

    if (data.error) {
      throw new Error(data.error)
    }

    qualifiedStocks.value = (data.qualified ?? []).map((s: any) => {
      const daysSince = s.latest_mmd?.date
        ? Math.max(0, Math.floor((Date.now() - new Date(s.latest_mmd.date).getTime()) / 86400000))
        : 999
      return {
        code: s.code,
        market: s.market,
        symbol: s.symbol,
        quality_score: s.quality_score,
        kline_count: s.kline_count,
        bi_count: s.bi_count,
        zs_count: s.zs_count,
        buy_1_count: s.buy_1_count,
        sell_1_count: s.sell_1_count,
        latest_mmd: s.latest_mmd,
        classification: s.classification || 'vegetable',
        days_since_signal: daysSince,
      }
    })

    scanProgress.value = 100
    scanTotal.value = qualifiedStocks.value.length

    // 记录本次扫描的完整池（选中 + 未选中），供「选股效果验证」对比
    const qualifiedSymbols = (data.qualified ?? []).map((s: any) => s.symbol)
    const rejectedCodes = (data.details ?? []).map((d: any) => d.code)
    scanPool.value = [...qualifiedSymbols, ...rejectedCodes.map((c: string) => market.value + c)]
    verifyResult.value = null
  } catch (e) {
    error.value = formatError(e)
  } finally {
    scanning.value = false
  }
}

// ── 选股结果前瞻收益验证 ─────────────────────────────────────────────────
async function verifyScreening() {
  if (!selectDate.value || scanPool.value.length === 0) return
  verifyLoading.value = true
  verifyResult.value = null
  try {
    const resp = await fetch('/api/v1/screening/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date: selectDate.value,
        market: market.value,
        symbols: scanPool.value,
        selected: qualifiedStocks.value.map((s) => s.symbol),
      }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      throw new Error((err as { detail?: string }).detail ?? 'HTTP ' + resp.status)
    }
    verifyResult.value = await resp.json()
  } catch (e) {
    error.value = '选股验证失败: ' + formatError(e)
  } finally {
    verifyLoading.value = false
  }
}
// V281: 选股效果验证导出 CSV（前瞻收益对比明细，Excel 友好）
const verifyCsvMsg = ref('')
function exportVerifyCsv() {
  const r = verifyResult.value
  if (!r || !r.horizons) return
  const header = [
    '持有交易日',
    '选中平均收益',
    '池平均收益',
    '超额收益',
    '选中命中率',
    '池命中率',
    '超额命中率',
    '样本(选/池)',
  ]
  const rows: string[] = []
  for (const h of ['5', '10', '20', '60']) {
    const hd = r.horizons[h]
    if (!hd) continue
    const row: string[] = [
      h + ' 日',
      fmtPct(hd.selected_avg_return),
      fmtPct(hd.pool_avg_return),
      fmtPct(hd.excess_return),
      fmtPct(hd.selected_hit_rate),
      fmtPct(hd.pool_hit_rate),
      fmtPct(hd.excess_hit_rate),
      String(hd.selected_n ?? '') + ' / ' + String(hd.pool_n ?? ''),
    ]
    rows.push(row.join(','))
  }
  const csv = '\uFEFF' + [header.join(','), ...rows].join('\n')
  try {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'easy_tdx_screen_verify_' + new Date().toISOString().slice(0, 10) + '.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    verifyCsvMsg.value = '✓ 已导出选股效果验证 CSV'
  } catch {
    verifyCsvMsg.value = '导出失败（浏览器权限）'
  }
  setTimeout(() => {
    verifyCsvMsg.value = ''
  }, 2500)
}
// V283: 选股效果验证复制 JSON（机器可读，Agent/脚本友好）
const verifyJsonMsg = ref('')
async function copyVerifyJson() {
  const r = verifyResult.value
  if (!r || !r.horizons) return
  const payload = {
    date: r.date,
    pool_size: r.pool_size,
    selected_size: r.selected_size,
    verdict: r.verdict,
    horizons: r.horizons,
  }
  try {
    await navigator.clipboard.writeText(JSON.stringify(payload, null, 2))
    verifyJsonMsg.value = '✓ 已复制选股效果验证 JSON'
  } catch {
    verifyJsonMsg.value = '复制失败（浏览器权限）'
  }
  setTimeout(() => {
    verifyJsonMsg.value = ''
  }, 2500)
}

// ── 批量策略验证（V114）：对筛选出的股票跑同一策略，按模型可信度排名选股 ──
interface BatchRow {
  symbol: string
  market: string
  code: string
  total_return: number | null
  win_rate: number | null
  hit_rate: number | null
  excess_hit_rate: number | null
  trust_score: number | null
  trust_grade: string | null
  trades: number | null
  // V182: 该股样本外验证结论
  oos_degraded: boolean | null
  oos_verdict: string
  // V316: 该股 Walk-Forward 滚动验证结论
  wf_degraded: boolean | null
  wf_verdict: string
}
const batchStrategy = ref('ma_cross')
const batchStrategyLabel = ref('双均线交叉')
const strategyOptions = ref<
  Array<{
    name: string
    label: string
    params: Array<{ name: string; default?: number | string | boolean }>
  }>
>([])
const batchResults = ref<BatchRow[]>([])
const batchLoading = ref(false)
// V221: 选股批量验证结果持久化（与回测页 V217 / 监控页 V219 对齐）
const SCREEN_BATCH_KEY = 'easy_tdx_screen_batch_verify_last'
const lastScreenBatchAt = ref('')
function saveScreenBatchPersist() {
  if (!batchResults.value.length) return
  try {
    localStorage.setItem(
      SCREEN_BATCH_KEY,
      JSON.stringify({
        rows: batchResults.value,
        strategy: batchStrategy.value,
        strategy_label: batchStrategyLabel.value || batchStrategy.value,
        at: new Date().toISOString(),
      }),
    )
  } catch {
    /* localStorage 不可用忽略 */
  }
}
function restoreScreenBatchPersist() {
  try {
    const raw = localStorage.getItem(SCREEN_BATCH_KEY)
    if (!raw) return
    const data = JSON.parse(raw)
    if (Array.isArray(data.rows) && data.rows.length) {
      batchResults.value = data.rows
      lastScreenBatchAt.value = data.at || ''
      error.value = '已恢复上次批量验证（' + (data.strategy_label || '') + '）'
    }
  } catch {
    /* 解析失败忽略 */
  }
}

async function loadBatchStrategies() {
  if (strategyOptions.value.length) return
  try {
    const resp = await fetch('/api/v1/backtest/strategies')
    if (!resp.ok) return
    const data = await resp.json()
    strategyOptions.value = (data.strategies ?? []).map((s: any) => ({
      name: s.name,
      label: s.label,
      params: s.params ?? [],
    }))
    if (strategyOptions.value.length) batchStrategy.value = strategyOptions.value[0].name
  } catch {
    /* ignore */
  }
}

function batchDefaults(): Record<string, number | string | boolean> {
  const opt = strategyOptions.value.find((s) => s.name === batchStrategy.value)
  const out: Record<string, number | string | boolean> = {}
  for (const p of opt?.params ?? []) {
    if (p.default !== undefined) out[p.name] = p.default
  }
  return out
}

async function runBatchVerify() {
  if (qualifiedStocks.value.length === 0) return
  batchLoading.value = true
  batchResults.value = []
  const defaultParams = batchDefaults()
  try {
    const rows: BatchRow[] = []
    const stocks = qualifiedStocks.value.slice(0, 12) // 限制 12 只避免过慢
    for (const st of stocks) {
      try {
        const bars = await fetchBars(st.market, st.code, 'DAY', undefined, undefined, 500)
        if (bars.length < 30) continue
        const resp = await fetch('/api/v1/backtest/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            strategy: batchStrategy.value,
            params: defaultParams,
            cash: 1000000,
            out_of_sample: true,
            use_walk_forward: true,
            step_ratio: 0.1,
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
          symbol: st.symbol,
          market: st.market,
          code: st.code,
          total_return: perf.total_return ?? null,
          win_rate: perf.win_rate ?? null,
          hit_rate: h5 && h5.count > 0 ? h5.hit_rate : null,
          excess_hit_rate: h5 && h5.count > 0 ? h5.excess_hit_rate : null,
          trust_score: result.model_trust?.score ?? null,
          trust_grade: result.model_trust?.grade ?? null,
          trades: perf.total_trades ?? null,
          oos_degraded: oos?.degraded ?? null,
          oos_verdict: oos?.verdict ?? '',
          wf_degraded: result.walk_forward?.degraded ?? null,
          wf_verdict: result.walk_forward?.verdict ?? '',
        })
      } catch {
        /* 单只失败跳过 */
      }
    }
    // 按可信度降序（缺可信度排最后）
    rows.sort((a, b) => (b.trust_score ?? -1) - (a.trust_score ?? -1))
    batchResults.value = rows
    lastScreenBatchAt.value = new Date().toISOString()
    saveScreenBatchPersist()
  } catch (e) {
    error.value = '批量验证失败: ' + formatError(e)
  } finally {
    batchLoading.value = false
  }
}

function batchPct(v: number | null | undefined): string {
  return v === null || v === undefined || !Number.isFinite(v) ? '-' : (v * 100).toFixed(0) + '%'
}
function batchTrust(r: BatchRow): string {
  if (r.trust_score === null || r.trust_score === undefined) return '-'
  return Math.round(r.trust_score) + ' ' + (r.trust_grade ?? '')
}
function batchTrustClass(r: BatchRow): string {
  if (r.trust_grade === '高') return 'pos'
  if (r.trust_grade === '低') return 'neg'
  return ''
}
// V182: 样本外列辅助
function batchOosLabel(r: BatchRow): string {
  if (r.oos_degraded === null || r.oos_degraded === undefined) return '-'
  return r.oos_degraded ? '⚠衰减' : '✅泛化'
}
function batchOosCls(r: BatchRow): string {
  if (r.oos_degraded === null || r.oos_degraded === undefined) return ''
  return r.oos_degraded ? 'neg' : 'pos'
}
function batchOosTitle(r: BatchRow): string {
  return r.oos_verdict || ''
}
// V194: 仅看样本外稳健（过滤掉 oos_degraded=true 的候选股）
const batchOnlyRobust = ref(false)
// V319: 仅看滚验稳健（过滤掉 wf_degraded=true 的候选股）
const batchOnlyWfRobust = ref(false)
const filteredBatchResults = computed(() => {
  let base = batchResults.value
  if (batchOnlyRobust.value) base = base.filter((r) => r.oos_degraded === false)
  if (batchOnlyWfRobust.value) base = base.filter((r) => r.wf_degraded === false)
  return base
})

// V118: 从批量验证排名直接查看该股（单标缠论回测）
function viewBatchStock(r: BatchRow) {
  const st: StockResult = {
    code: r.code,
    market: r.market,
    symbol: r.symbol,
    quality_score: 0,
    kline_count: 0,
    bi_count: 0,
    zs_count: 0,
    buy_1_count: 0,
    sell_1_count: 0,
    latest_mmd: null,
    classification: 'vegetable',
  }
  selectStock(st)
}

// V130: 批量验证排名导出（Markdown 复制）
const batchCopyMsg = ref('')
// V131: 把批量验证选出的股票保存为组合策略（kind=portfolio，可载入组合页复跑）
const batchSaveMsg = ref('')
const batchSaving = ref(false)
async function saveBatchAsPortfolio() {
  if (batchResults.value.length === 0 || batchSaving.value) return
  batchSaving.value = true
  batchSaveMsg.value = ''
  try {
    // V203: 保存遵循「仅看样本外稳健」过滤——开启时只把筛选视图里的 ✅泛化 标的入库
    const visible = batchOnlyRobust.value
      ? batchResults.value.filter((r) => r.oos_degraded === false)
      : batchResults.value
    if (visible.length === 0) {
      batchSaveMsg.value = '没有样本外稳健的候选股可保存（请关闭「仅看样本外稳健」再试）'
      batchSaving.value = false
      setTimeout(() => {
        batchSaveMsg.value = ''
      }, 4000)
      return
    }
    const stocks = visible.map((r) => r.symbol)
    const avgTrust = visible.length
      ? visible.reduce((s, r) => s + (r.trust_score ?? 0), 0) / visible.length
      : 0
    // V197: 样本外聚合（逐只开启 out_of_sample 后统计衰减比例，与 V190 对齐）
    const oosKnown = visible.filter((r) => r.oos_degraded !== null && r.oos_degraded !== undefined)
    const oosDegradedN = oosKnown.filter((r) => r.oos_degraded === true).length
    const oosRatio = oosKnown.length ? oosDegradedN / oosKnown.length : null
    const oosVerdict = oosKnown.length
      ? oosRatio! < 0.5
        ? '✅ ' + (oosKnown.length - oosDegradedN) + '/' + oosKnown.length + ' 只样本外稳健'
        : '⚠ ' + oosDegradedN + '/' + oosKnown.length + ' 只样本外衰减'
      : ''
    await saveStrategy({
      name: batchStrategyLabel.value + ' · 批量验证' + stocks.length + '只',
      kind: 'portfolio',
      strategy: batchStrategy.value,
      strategy_label: batchStrategyLabel.value,
      params: batchDefaults(),
      context: {
        stocks,
        category: 'DAY',
        start_date: selectDate.value || undefined,
        end_date: undefined,
      },
      trade_config: { cash: 1_000_000, execution: 'next_open' },
      snapshot: {
        total_stocks: stocks.length,
        avg_trust_score: avgTrust,
        avg_oos_degraded: oosRatio,
        oos_verdict: oosVerdict,
        source: 'batch-verify',
        saved_at: new Date().toISOString().slice(0, 10),
      },
      tags: ['批量验证'],
      notes: '由动态选股页批量策略验证（按模型可信度排名）生成，可在组合回测页载入复跑。',
    })
    batchSaveMsg.value = '✓ 已保存为组合策略，可在「策略库」载入复跑'
    setTimeout(() => {
      batchSaveMsg.value = ''
    }, 4000)
  } catch (e) {
    batchSaveMsg.value = '保存失败：' + formatError(e)
  } finally {
    batchSaving.value = false
  }
}
function copyBatchRanking() {
  if (batchResults.value.length === 0) return
  const lines: string[] = []
  lines.push('# easy-tdx 批量策略验证（' + (batchStrategyLabel.value || batchStrategy.value) + '）')
  lines.push('')
  lines.push('| 排名 | 标的 | 总收益 | 胜率 | 5根命中率 | 超额命中率 | 可信度 | 样本外 | 交易数 |')
  lines.push('| --- | --- | --- | --- | --- | --- | --- | --- | --- |')
  for (const r of batchResults.value) {
    const trust = batchTrust(r)
    lines.push(
      '| ' +
        (batchResults.value.indexOf(r) + 1) +
        ' | ' +
        r.symbol +
        ' | ' +
        batchPct(r.total_return) +
        ' | ' +
        batchPct(r.win_rate) +
        ' | ' +
        batchPct(r.hit_rate) +
        ' | ' +
        batchPct(r.excess_hit_rate) +
        ' | ' +
        trust +
        ' | ' +
        batchOosLabel(r) +
        ' | ' +
        (r.trades ?? '-') +
        ' |',
    )
  }
  lines.push('')
  lines.push(
    '方法：对筛选出的每只股票独立回测（最近 500 根日线），按模型可信度（V101）降序排名；可信度 = 择时准确度 + 稳健性 + 绩效对比。',
  )
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
    batchCopyMsg.value = '✓ 已复制验证排名'
    setTimeout(() => {
      batchCopyMsg.value = ''
    }, 2500)
  }
  void doCopy()
}
// V168: 批量验证 JSON 导出（机器可读，Agent/脚本友好，与 V157/V166 对齐）
const batchJsonCopyMsg = ref('')
async function copyBatchJson() {
  if (batchResults.value.length === 0) return
  const payload = {
    strategy: batchStrategy.value,
    strategy_label: batchStrategyLabel.value,
    generated_at: new Date().toISOString(),
    rows: batchResults.value.map((r, i) => ({ rank: i + 1, ...r })),
  }
  const json = JSON.stringify(payload, null, 2)
  try {
    await navigator.clipboard.writeText(json)
    batchJsonCopyMsg.value = '✓ 已复制验证 JSON'
  } catch {
    batchJsonCopyMsg.value = '复制失败（浏览器权限）'
  }
  setTimeout(() => {
    batchJsonCopyMsg.value = ''
  }, 2500)
}
// V255: 选股批量验证导出 CSV（Excel 友好，与回测页 V253 对齐）
const batchCsvMsg = ref('')
function batchCsvEscape(v: string): string {
  return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v
}
function exportBatchCsv() {
  if (batchResults.value.length === 0) return
  const header = [
    '排名',
    '标的',
    '总收益',
    '胜率',
    '5根命中率',
    '超额命中率',
    '可信度',
    '样本外',
    '交易数',
  ]
  const lines = [header.join(',')]
  filteredBatchResults.value.forEach((r, i) => {
    const row = [
      i + 1,
      batchCsvEscape(r.symbol),
      batchPct(r.total_return),
      batchPct(r.win_rate),
      batchPct(r.hit_rate),
      batchPct(r.excess_hit_rate),
      batchCsvEscape(batchTrust(r)),
      batchOosLabel(r),
      r.trades ?? '',
    ]
    lines.push(row.join(','))
  })
  const csv = '\uFEFF' + lines.join('\n')
  try {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'easy_tdx_screen_batch_verify_' + new Date().toISOString().slice(0, 10) + '.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    batchCsvMsg.value = '✓ 已导出 CSV'
  } catch {
    batchCsvMsg.value = '导出失败（浏览器权限）'
  }
  setTimeout(() => {
    batchCsvMsg.value = ''
  }, 2500)
}

// ── 选择股票 ────────────────────────────────────────────────────────────
async function selectStock(stock: StockResult) {
  selectedStock.value = stock
  bars.value = []
  chanlunBis.value = []
  chanlunXds.value = []
  chanlunZss.value = []
  chanlunMmds.value = []
  chanlunFxs.value = []
  chanlunBcs.value = []
  chanlunZsds.value = []
  chanlunQsds.value = []
  backtestResult.value = null

  // 获取K线数据
  try {
    const resp = await fetch(
      `/api/v1/bars?market=${stock.market}&code=${stock.code}&category=${chanlunCategory.value}&count=500&start=0`,
    )

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }

    const data = await resp.json()
    bars.value = (data.data ?? []).map((row: any) => ({
      datetime: row.datetime || row.date,
      open: Number(row.open),
      high: Number(row.high),
      low: Number(row.low),
      close: Number(row.close),
      vol: Number(row.vol),
      amount: Number(row.amount),
    }))
  } catch (e) {
    error.value = `获取K线数据失败: ${formatError(e)}`
    return
  }

  // 缠论分析
  await runChanlunAnalysis(stock)
}

async function onChanlunCategoryChange() {
  if (selectedStock.value) {
    await selectStock(selectedStock.value)
  }
}

async function runChanlunAnalysis(stock: StockResult) {
  chanlunLoading.value = true

  try {
    const resp = await fetch('/api/v1/chanlun/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        market: stock.market,
        code: stock.code,
        category: chanlunCategory.value,
        count: bars.value.length,
        start: 0,
      }),
    })

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }

    const data = await resp.json()

    chanlunBis.value = data.bis ?? []
    chanlunXds.value = data.xds ?? []
    chanlunZsds.value = data.zsds ?? []
    chanlunQsds.value = data.qsds ?? []
    chanlunZss.value = data.zss ?? []
    chanlunMmds.value = data.mmds ?? []
    chanlunFxs.value = data.fractals ?? []
    chanlunBcs.value = data.bcs ?? []
    chanlunMacd.value = data.macd && data.macd.dif?.length ? data.macd : null
  } catch (e) {
    console.error('缠论分析失败:', e)
  } finally {
    chanlunLoading.value = false
  }
}

// ── 回测 ────────────────────────────────────────────────────────────────
async function runBacktest() {
  if (!selectedStock.value || bars.value.length === 0) return

  backtestLoading.value = true
  backtestResult.value = null

  try {
    const resp = await fetch('/api/v1/backtest/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        strategy: 'changying_chanlun',
        ohlcv: bars.value,
        symbol: selectedStock.value.symbol,
        category: chanlunCategory.value,
        count: bars.value.length,
        params: {
          use_season_filter: true,
          tree_weight: 0.4,
          grain_weight: 0.3,
          vegetable_weight: 0.3,
        },
      }),
    })

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }

    backtestResult.value = await resp.json()
  } catch (e) {
    error.value = `回测失败: ${formatError(e)}`
  } finally {
    backtestLoading.value = false
  }
}

// ── 统计信息 ────────────────────────────────────────────────────────────
const stats = computed(() => ({
  totalScanned: scanTotal.value,
  qualified: qualifiedStocks.value.length,
  treeCount: qualifiedStocks.value.filter((s) => s.classification === 'tree').length,
  grainCount: qualifiedStocks.value.filter((s) => s.classification === 'grain').length,
  vegetableCount: qualifiedStocks.value.filter((s) => s.classification === 'vegetable').length,
  avgScore:
    qualifiedStocks.value.length > 0
      ? (
          qualifiedStocks.value.reduce((s, st) => s + st.quality_score, 0) /
          qualifiedStocks.value.length
        ).toFixed(1)
      : '-',
}))

// ── 生命周期 ────────────────────────────────────────────────────────────
onMounted(() => {
  // 默认选择今天前30天
  const d = new Date()
  d.setDate(d.getDate() - 30)
  selectDate.value = d.toISOString().slice(0, 10)
  loadBatchStrategies()
  // V221: 恢复上次批量验证结果（如有）
  restoreScreenBatchPersist()
})
</script>

<template>
  <div class="screening-view">
    <!-- 顶部配置栏 -->
    <div class="config-bar">
      <div class="field-group">
        <label>市场</label>
        <select v-model="market" class="market-select">
          <option value="SZ">深圳</option>
          <option value="SH">上海</option>
        </select>
      </div>
      <div class="field-group">
        <label>历史日期</label>
        <input v-model="selectDate" type="date" class="date-input" />
      </div>
      <button class="primary scan-btn" :disabled="scanning" @click="scanStocks">
        {{ scanning ? `扫描中... ${scanProgress}%` : '开始选股' }}
      </button>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="error-banner">⚠ {{ error }}</div>

    <!-- 统计面板 -->
    <div v-if="!scanning && qualifiedStocks.length > 0" class="stats-bar">
      <div class="stat-item">
        <span class="stat-label">总扫描</span>
        <span class="stat-value">{{ stats.totalScanned }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">符合条件</span>
        <span class="stat-value" style="color: #60b4ff">{{ stats.qualified }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">🌳 树型</span>
        <span class="stat-value" style="color: #22c55e">{{ stats.treeCount }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">🌾 粮型</span>
        <span class="stat-value" style="color: #f59e0b">{{ stats.grainCount }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">🥬 菜型</span>
        <span class="stat-value" style="color: #ef4444">{{ stats.vegetableCount }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">平均质量分</span>
        <span class="stat-value">{{ stats.avgScore }}</span>
      </div>
    </div>

    <!-- 选股效果验证 -->
    <div v-if="!scanning && qualifiedStocks.length > 0" class="verify-bar">
      <button class="ghost verify-btn" :disabled="verifyLoading" @click="verifyScreening">
        {{
          verifyLoading
            ? '验证中（回看选股日后 5/10/20/60 日收益）…'
            : '📈 验证选股效果（回测：选中 vs 未选中）'
        }}
      </button>
    </div>
    <div v-if="verifyResult" class="verify-panel">
      <h3>
        📈 选股效果验证（选股日 {{ verifyResult.date }} · 池 {{ verifyResult.pool_size }} 只 · 选中
        {{ verifyResult.selected_size }} 只）
        <button class="ghost small" @click="exportVerifyCsv">📊 导出 CSV</button>
        <button class="ghost small" @click="copyVerifyJson">⚙ 复制 JSON</button>
        <span v-if="verifyCsvMsg" class="save-msg">{{ verifyCsvMsg }}</span>
        <span v-if="verifyJsonMsg" class="save-msg">{{ verifyJsonMsg }}</span>
      </h3>
      <div class="verify-verdict">{{ verifyResult.verdict }}</div>
      <table class="verify-table">
        <thead>
          <tr>
            <th>持有交易日</th>
            <th>选中平均收益</th>
            <th>池平均收益</th>
            <th>超额收益</th>
            <th>选中命中率</th>
            <th>池命中率</th>
            <th>超额命中率</th>
            <th>样本(选/池)</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="h in ['5', '10', '20', '60']" :key="h">
            <tr v-if="verifyResult.horizons[h]">
              <td>{{ h }} 日</td>
              <td :class="(verifyResult.horizons[h].selected_avg_return ?? 0) >= 0 ? 'pos' : 'neg'">
                {{ fmtPct(verifyResult.horizons[h].selected_avg_return) }}
              </td>
              <td class="dim">{{ fmtPct(verifyResult.horizons[h].pool_avg_return) }}</td>
              <td :class="(verifyResult.horizons[h].excess_return ?? 0) >= 0 ? 'pos' : 'neg'">
                {{ fmtPct(verifyResult.horizons[h].excess_return) }}
              </td>
              <td :class="(verifyResult.horizons[h].selected_hit_rate ?? 0) >= 0.5 ? 'pos' : ''">
                {{ fmtPct(verifyResult.horizons[h].selected_hit_rate) }}
              </td>
              <td class="dim">{{ fmtPct(verifyResult.horizons[h].pool_hit_rate) }}</td>
              <td :class="(verifyResult.horizons[h].excess_hit_rate ?? 0) >= 0 ? 'pos' : 'neg'">
                {{ fmtPct(verifyResult.horizons[h].excess_hit_rate) }}
              </td>
              <td class="dim">
                {{ verifyResult.horizons[h].selected_n }} / {{ verifyResult.horizons[h].pool_n }}
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <p class="verify-legend">
        方法：以选股日收盘价为基准，回看其后 5/10/20/60 个交易日的收益； 对比模型选中的股票 vs
        整个扫描池（含未选中）。超额为正且命中率更高说明选股模型具备择股能力。
      </p>
    </div>

    <!-- V114: 批量策略验证（对筛选出的股票跑同一策略，按可信度排名） -->
    <div v-if="!scanning && qualifiedStocks.length > 0" class="batch-verify-bar">
      <select
        v-model="batchStrategy"
        class="strategy-select"
        @change="
          batchStrategyLabel =
            strategyOptions.find((s) => s.name === batchStrategy)?.label ?? batchStrategy
        "
      >
        <option v-for="s in strategyOptions" :key="s.name" :value="s.name">{{ s.label }}</option>
      </select>
      <button
        class="ghost verify-btn"
        :disabled="batchLoading || strategyOptions.length === 0"
        @click="runBatchVerify"
      >
        {{ batchLoading ? '批量验证中…' : '🧪 批量策略验证（对选中的股票逐个回测，按可信度排名）' }}
      </button>
    </div>
    <div v-if="batchResults.length > 0" class="batch-panel">
      <div class="batch-panel-head">
        <h3>
          🧪 批量策略验证：{{ batchStrategyLabel }}（按模型可信度降序）
          <span v-if="lastScreenBatchAt" class="screen-batch-at" :title="'上次验证时间'"
            >🕒 {{ new Date(lastScreenBatchAt).toLocaleString() }}</span
          >
        </h3>
        <div class="batch-actions">
          <button
            class="ghost small"
            :class="{ active: batchOnlyRobust }"
            :title="
              '仅保留样本外 ✅泛化 的候选股（当前 ' +
              batchResults.filter((r: BatchRow) => r.oos_degraded === false).length +
              ' 只）'
            "
            @click="batchOnlyRobust = !batchOnlyRobust"
          >
            ✅ 仅看样本外稳健
          </button>
          <button
            class="ghost small"
            :class="{ active: batchOnlyWfRobust }"
            :title="
              '仅保留滚验 ✅稳 的候选股（当前 ' +
              batchResults.filter((r: BatchRow) => r.wf_degraded === false).length +
              ' 只）'
            "
            @click="batchOnlyWfRobust = !batchOnlyWfRobust"
          >
            ✅ 仅看滚验稳健
          </button>
          <button class="ghost small" @click="copyBatchRanking">📋 复制排名</button>
          <button class="ghost small" @click="copyBatchJson">⚙ 复制 JSON</button>
          <button class="ghost small" @click="exportBatchCsv">📊 导出 CSV</button>
          <button class="ghost small" :disabled="batchSaving" @click="saveBatchAsPortfolio">
            {{ batchSaving ? '保存中…' : '💾 保存为组合策略' }}
          </button>
          <span v-if="batchCopyMsg" class="save-msg">{{ batchCopyMsg }}</span>
          <span v-if="batchJsonCopyMsg" class="save-msg">{{ batchJsonCopyMsg }}</span>
          <span v-if="batchCsvMsg" class="save-msg">{{ batchCsvMsg }}</span>
          <span
            v-if="batchSaveMsg"
            class="save-msg"
            :class="{ err: batchSaveMsg.includes('失败') }"
            >{{ batchSaveMsg }}</span
          >
        </div>
      </div>
      <table class="batch-table">
        <thead>
          <tr>
            <th>#</th>
            <th>标的</th>
            <th class="num">总收益</th>
            <th class="num">胜率</th>
            <th class="num">5根命中率</th>
            <th class="num">超额命中率</th>
            <th class="num">可信度</th>
            <th class="num" title="训练段 vs 未见过数据">样本外</th>
            <th class="num" title="Walk-Forward 滚动验证">滚验</th>
            <th class="num">交易数</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in filteredBatchResults" :key="r.symbol">
            <td class="dim">{{ i + 1 }}</td>
            <td>{{ r.symbol }}</td>
            <td class="num" :class="(r.total_return ?? 0) >= 0 ? 'pos' : 'neg'">
              {{ batchPct(r.total_return) }}
            </td>
            <td class="num">{{ batchPct(r.win_rate) }}</td>
            <td class="num">{{ batchPct(r.hit_rate) }}</td>
            <td class="num" :class="(r.excess_hit_rate ?? 0) >= 0 ? 'pos' : 'neg'">
              {{ batchPct(r.excess_hit_rate) }}
            </td>
            <td class="num" :class="batchTrustClass(r)">{{ batchTrust(r) }}</td>
            <td class="num" :class="batchOosCls(r)" :title="batchOosTitle(r)">
              {{ batchOosLabel(r) }}
            </td>
            <td class="num" :title="r.wf_verdict || ''">
              {{
                r.wf_degraded === null || r.wf_degraded === undefined
                  ? '-'
                  : r.wf_degraded
                    ? '⚠递减'
                    : '✅稳'
              }}
            </td>
            <td class="num">{{ r.trades }}</td>
            <td><button class="ghost small" @click="viewBatchStock(r)">查看该股</button></td>
          </tr>
        </tbody>
      </table>
      <p class="batch-legend">
        对筛选出的每只股票用所选策略做一次独立回测（最近 500 根日线，最新 K 线区间），
        汇总总收益/胜率/5根命中率/模型可信度并降序排名——可信度越高说明该策略在这只标的上「验证过的准确度」越好，可直接用于选股。
      </p>
    </div>

    <!-- 主内容区 -->
    <div class="main-content">
      <!-- 左侧：股票列表 -->
      <div class="stock-panel">
        <div class="panel-header">
          <h3>
            筛选结果 ({{ qualifiedStocks.length }})
            <button
              class="ghost small"
              :disabled="qualifiedStocks.length === 0"
              @click="exportScreenListCsv"
            >
              📊 导出 CSV
            </button>
            <button
              class="ghost small"
              :disabled="qualifiedStocks.length === 0"
              @click="copyScreenListJson"
            >
              ⚙ 复制 JSON
            </button>
            <span v-if="screenListCsvMsg" class="save-msg">{{ screenListCsvMsg }}</span>
            <span v-if="screenListJsonMsg" class="save-msg">{{ screenListJsonMsg }}</span>
          </h3>
        </div>
        <div class="stock-list">
          <div
            v-for="stock in qualifiedStocks"
            :key="stock.symbol"
            class="stock-item"
            :class="{ selected: selectedStock?.symbol === stock.symbol }"
            @click="selectStock(stock)"
          >
            <div class="stock-info">
              <span class="stock-symbol">{{ stock.symbol }}</span>
              <span
                class="stock-classification"
                :style="{ color: CLASSIFICATION_COLORS[stock.classification] }"
              >
                {{ CLASSIFICATION_LABELS[stock.classification] }}
              </span>
            </div>
            <div class="stock-stats">
              <span class="stat"
                >质量: <strong>{{ stock.quality_score }}</strong></span
              >
              <span class="stat"
                >1买: <strong style="color: #22c55e">{{ stock.buy_1_count }}</strong></span
              >
              <span class="stat"
                >1卖: <strong style="color: #ef4444">{{ stock.sell_1_count }}</strong></span
              >
            </div>
            <div
              class="stock-recommendation"
              :style="{ color: ACTION_COLORS[getRecommendation(stock).action] }"
            >
              {{ getRecommendation(stock).label }}
            </div>
            <div v-if="stock.latest_mmd" class="stock-latest">
              最新: {{ stock.latest_mmd.type }} @ {{ stock.latest_mmd.date }}
              <span
                v-if="stock.days_since_signal !== undefined && stock.days_since_signal < 999"
                class="days-since"
                >({{ stock.days_since_signal }}天前)</span
              >
              <!-- V102: 质量评级 + 操作建议摘要 -->
              <span
                v-if="stock.latest_mmd.v102_signal_quality?.overall_grade"
                class="screen-v102-grade"
                :class="'g' + stock.latest_mmd.v102_signal_quality.overall_grade"
              >
                质量{{ stock.latest_mmd.v102_signal_quality.overall_grade }}
              </span>
              <span
                v-if="stock.latest_mmd.v102_decision_support?.action_recommendation"
                class="screen-v102-advice"
                :class="{
                  'adv-buy':
                    stock.latest_mmd.v102_decision_support.action_recommendation.includes('买入'),
                  'adv-sell':
                    stock.latest_mmd.v102_decision_support.action_recommendation.includes('卖出'),
                }"
              >
                {{ stock.latest_mmd.v102_decision_support.action_recommendation }}
              </span>
              <!-- V437: 风险回报比 -->
              <span
                v-if="stock.latest_mmd.v102_decision_support?.risk_reward_ratio"
                class="screen-v102-rr"
              >
                RR {{ stock.latest_mmd.v102_decision_support.risk_reward_ratio.toFixed(1) }}
              </span>
            </div>
            <div
              v-if="stock.latest_mmd"
              class="stock-hint"
              :style="{ borderColor: ACTION_COLORS[getRecommendation(stock).action] }"
            >
              💡 {{ getActionExplanation(stock) }}
            </div>
          </div>
          <div v-if="qualifiedStocks.length === 0 && !scanning" class="empty-state">
            <p>暂无符合条件的股票</p>
            <p class="hint">尝试调整日期或市场</p>
          </div>
        </div>
      </div>

      <!-- 右侧：详情面板 -->
      <div class="detail-panel" v-if="selectedStock">
        <div class="panel-header">
          <h3>{{ selectedStock.symbol }} 分析</h3>
          <div class="header-badges">
            <span
              class="classification-badge"
              :style="{
                background: CLASSIFICATION_COLORS[selectedStock.classification] + '20',
                color: CLASSIFICATION_COLORS[selectedStock.classification],
                borderColor: CLASSIFICATION_COLORS[selectedStock.classification],
              }"
            >
              {{ CLASSIFICATION_LABELS[selectedStock.classification] }}
            </span>
            <span
              class="action-badge"
              :style="{
                background: ACTION_COLORS[getRecommendation(selectedStock).action] + '20',
                color: ACTION_COLORS[getRecommendation(selectedStock).action],
                borderColor: ACTION_COLORS[getRecommendation(selectedStock).action],
              }"
            >
              {{ getRecommendation(selectedStock).label }}
            </span>
          </div>
        </div>

        <!-- 统计信息 -->
        <div class="detail-stats">
          <div class="detail-stat">
            <span class="label">K线</span>
            <span class="value">{{ selectedStock.kline_count }}</span>
          </div>
          <div class="detail-stat">
            <span class="label">笔</span>
            <span class="value">{{ selectedStock.bi_count }}</span>
          </div>
          <div class="detail-stat">
            <span class="label">中枢</span>
            <span class="value">{{ selectedStock.zs_count }}</span>
          </div>
          <div class="detail-stat">
            <span class="label">质量分</span>
            <span class="value">{{ selectedStock.quality_score }}</span>
          </div>
          <div
            class="detail-stat"
            v-if="
              selectedStock.days_since_signal !== undefined && selectedStock.days_since_signal < 999
            "
          >
            <span class="label">距信号</span>
            <span
              class="value"
              :style="{ color: selectedStock.days_since_signal <= 10 ? '#22c55e' : '#fbbf24' }"
              >{{ selectedStock.days_since_signal }}天</span
            >
          </div>
        </div>

        <!-- 操作建议 -->
        <div
          v-if="selectedStock.latest_mmd"
          class="action-hint-panel"
          :style="{ borderColor: ACTION_COLORS[getRecommendation(selectedStock).action] }"
        >
          <div class="hint-title">💡 操作建议</div>
          <div class="hint-text">{{ getActionExplanation(selectedStock) }}</div>
        </div>

        <!-- 缠论周期选择 -->
        <div class="detail-field">
          <label>缠论周期</label>
          <select v-model="chanlunCategory" @change="onChanlunCategoryChange">
            <option value="DAY">日线</option>
            <option value="WEEK">周线</option>
            <option value="MIN_5">5分钟</option>
            <option value="MIN_15">15分钟</option>
            <option value="MIN_30">30分钟</option>
            <option value="MIN_60">60分钟</option>
          </select>
        </div>

        <!-- K线图 -->
        <div v-if="!chanlunLoading && bars.length > 0" class="chart-area">
          <ChanlunChart
            :bars="bars"
            :bis="chanlunBis"
            :xds="chanlunXds"
            :zsds="chanlunZsds"
            :qsds="chanlunQsds"
            :zss="chanlunZss"
            :mmds="chanlunMmds"
            :fxs="chanlunFxs"
            :bcs="chanlunBcs"
            :macd="chanlunMacd ?? undefined"
            :frequency="chanlunCategory"
          />
        </div>
        <div v-else-if="chanlunLoading" class="chart-placeholder">正在分析缠论结构…</div>

        <!-- 快速诊断按钮 -->
        <button class="ghost backtest-btn" @click="goToDiagnosis(selectedStock!)">
          🔍 技术诊断
        </button>

        <!-- 回测按钮 -->
        <button
          class="primary backtest-btn"
          :disabled="backtestLoading || !bars.length"
          @click="runBacktest"
        >
          {{ backtestLoading ? '回测中…' : '运行长赢缠论回测' }}
        </button>

        <!-- 回测结果 -->
        <div v-if="backtestResult" class="backtest-result">
          <h4>回测结果</h4>
          <div class="result-stats">
            <div class="result-stat">
              <span class="label">收益率</span>
              <span
                class="value"
                :style="{
                  color: backtestResult.performance.total_return >= 0 ? '#22c55e' : '#ef4444',
                }"
              >
                {{ (backtestResult.performance.total_return * 100).toFixed(2) }}%
              </span>
            </div>
            <div class="result-stat">
              <span class="label">夏普比率</span>
              <span class="value">{{ backtestResult.performance.sharpe?.toFixed(2) }}</span>
            </div>
            <div class="result-stat">
              <span class="label">最大回撤</span>
              <span class="value" style="color: #ef4444">
                {{ (backtestResult.performance.max_drawdown * 100).toFixed(2) }}%
              </span>
            </div>
            <div class="result-stat">
              <span class="label">交易次数</span>
              <span class="value">{{ backtestResult.performance.total_trades }}</span>
            </div>
          </div>
          <EquityChart
            v-if="backtestResult.equity_curve.length > 0"
            :equity="backtestResult.equity_curve"
          />
        </div>
      </div>

      <!-- 空状态 -->
      <div v-else class="detail-placeholder">
        <p>选择一只股票查看详情</p>
        <p class="hint">左侧列表显示筛选结果，点击股票查看缠论分析和回测</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.screening-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
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

.market-select,
.date-input {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 10px;
  font-size: 13px;
  color: var(--text);
  width: 120px;
}

.scan-btn {
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

.verify-bar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 10px;
}
.verify-btn {
  font-size: 13px;
}
.verify-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  margin-bottom: 12px;
}
.verify-panel h3 {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 10px;
}
.verify-verdict {
  font-size: 13px;
  line-height: 1.6;
  padding: 8px 10px;
  margin-bottom: 10px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.02);
  color: var(--text);
}
.verify-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.verify-table th {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 600;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  text-align: right;
}
.verify-table th:first-child {
  text-align: left;
}
.verify-table td {
  padding: 5px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  text-align: right;
  font-family: var(--font-mono);
}
.verify-table td.dim {
  font-family: inherit;
  color: var(--text-muted);
}
.verify-legend {
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.6;
  margin: 10px 0 0;
}

/* V114: 批量策略验证 */
.batch-verify-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.batch-verify-bar .strategy-select {
  max-width: 260px;
}
.batch-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  margin-bottom: 12px;
}
.batch-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.batch-panel-head h3 {
  /* V221: 上次选股批量验证时间 */
  .screen-batch-at {
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
.batch-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.batch-actions .save-msg {
  font-size: 12px;
  color: var(--up);
}
.batch-actions .save-msg.err {
  color: var(--down);
}
.batch-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.batch-table th {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 600;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  text-align: right;
}
.batch-table th:first-child,
.batch-table td:first-child {
  text-align: left;
}
.batch-table td {
  padding: 5px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  text-align: right;
  font-family: var(--font-mono);
}
.batch-table td.num-row {
  text-align: right;
}
.batch-legend {
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.6;
  margin: 10px 0 0;
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
.main-content {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 16px;
  flex: 1;
  overflow: hidden;
}

.stock-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}

.panel-header h3 {
  font-size: 14px;
  margin: 0;
  color: var(--text);
}

.stock-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.stock-item {
  padding: 10px 12px;
  border-radius: var(--radius);
  cursor: pointer;
  margin-bottom: 4px;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.stock-item:hover {
  background: rgba(255, 255, 255, 0.03);
  border-color: var(--border);
}

.stock-item.selected {
  background: rgba(96, 165, 250, 0.1);
  border-color: #60a5fa;
}

.stock-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.stock-symbol {
  font-weight: 600;
  font-size: 14px;
  color: var(--text);
}

.stock-classification {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid;
}

.stock-stats {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--text-muted);
}

.stock-stats .stat strong {
  color: var(--text);
}

.stock-recommendation {
  margin-top: 4px;
  font-size: 11px;
  font-weight: 600;
}

.stock-latest {
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-dim);
}

.detail-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.detail-panel .panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-badges {
  display: flex;
  gap: 8px;
  align-items: center;
}

.classification-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 12px;
  border: 1px solid;
}

.action-badge {
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 12px;
  border: 1px solid;
  font-weight: 600;
}

.detail-stats {
  display: flex;
  gap: 16px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}

.detail-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.detail-stat .label {
  font-size: 11px;
  color: var(--text-dim);
}

.detail-stat .value {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
}

.detail-field {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
}

.detail-field label {
  font-size: 12px;
  color: var(--text-dim);
}

.detail-field select {
  background: var(--bg-soft, #0f172a);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 12px;
}

.chart-area {
  flex: 1;
  min-height: 400px;
}

.chart-placeholder {
  height: 400px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-dim);
}

.backtest-btn {
  margin: 12px 16px;
  width: calc(100% - 32px);
}

.backtest-result {
  margin: 0 16px 16px;
  padding: 12px;
  background: var(--bg);
  border-radius: var(--radius);
}

.backtest-result h4 {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--text-muted);
}

.result-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}

.result-stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.result-stat .label {
  font-size: 11px;
  color: var(--text-dim);
}

.result-stat .value {
  font-size: 16px;
  font-weight: 600;
}

.detail-placeholder {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-dim);
  gap: 8px;
}

.detail-placeholder .hint {
  font-size: 12px;
  opacity: 0.7;
}

.empty-state {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-dim);
}

.empty-state .hint {
  font-size: 12px;
  margin-top: 8px;
  opacity: 0.7;
}

/* ECharts图表容器 */
:deep(.chanlun-chart) {
  width: 100%;
  height: 400px;
}

/* 操作建议提示 */
.stock-hint {
  font-size: 11px;
  color: var(--text-dim);
  padding: 4px 8px;
  background: rgba(255, 255, 255, 0.02);
  border-left: 2px solid;
  border-radius: 0 4px 4px 0;
  line-height: 1.4;
}

.days-since {
  font-size: 10px;
  color: var(--text-muted);
  margin-left: 4px;
}

.action-hint-panel {
  margin-top: 10px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid;
  border-left: 3px solid;
  border-radius: 6px;
}

.hint-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 4px;
}

.hint-text {
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.5;
}

/* V102: 信号质量评级 + 操作建议摘要 */
.screen-v102-grade {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 8px;
  color: #fff;
  margin-left: 6px;
}
.screen-v102-grade.gA {
  background: #22c55e;
}
.screen-v102-grade.gB {
  background: #4a9eff;
}
.screen-v102-grade.gC {
  background: #f59e0b;
}
.screen-v102-grade.gD {
  background: #ef4444;
}
.screen-v102-advice {
  display: block;
  margin-top: 3px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 280px;
}
.screen-v102-advice.adv-buy {
  color: #22c55e;
}
.screen-v102-advice.adv-sell {
  color: #ef4444;
}
.screen-v102-rr {
  display: block;
  margin-top: 3px;
  font-size: 11px;
  font-weight: 600;
  color: #fbbf24;
}
</style>
