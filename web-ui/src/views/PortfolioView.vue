<script setup lang="ts">
// 组合回测主页面：左配置（多标的 + 策略 + 日期）/ 右报告（组合净值 + 各标的对比）。

import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import EquityChart from '../components/EquityChart.vue'
import GradeDetails from '../components/GradeDetails.vue'
import PortfolioAccuracyPanel from '../components/PortfolioAccuracyPanel.vue'
import PortfolioCompareChart from '../components/PortfolioCompareChart.vue'
import PortfolioOutOfSamplePanel from '../components/PortfolioOutOfSamplePanel.vue'
import PortfolioValidationSummary from '../components/PortfolioValidationSummary.vue'
import PortfolioSummaryTable from '../components/PortfolioSummaryTable.vue'
import StocksPicker from '../components/StocksPicker.vue'
import StrategyPicker from '../components/StrategyPicker.vue'
import { fetchBars, formatError, runBacktest, saveStrategy } from '../api'
import { gradePortfolio } from '../grading'
import type { Category, ExecutionMode } from '../types'
import { useBacktestStore } from '../stores/backtest'

const store = useBacktestStore()
const route = useRoute()
const router = useRouter()

const stocks = ref<string[]>(['SZ:000001', 'SH:600519'])
const strategy = ref('ma_cross')
const params = ref<Record<string, number | string | boolean>>({})
const cash = ref(1000000)
const category = ref<Category>('DAY')
const execution = ref<ExecutionMode>('next_open')

// 成交价模式（精简为 开盘价/收盘价）
const EXECUTIONS: { value: ExecutionMode; label: string }[] = [
  { value: 'next_open', label: '开盘价' },
  { value: 'next_close', label: '收盘价' },
]
// V126: 组合级样本外验证（逐标训练/持有切分）
const checkOutOfSample = ref(false)
// V299: 组合级 Walk-Forward 滚动窗口验证（逐槽回测聚合防过拟合判定）
const checkWalkForward = ref(false)
const oosTrainRatio = ref(0.7)
const CATEGORIES: Category[] = ['DAY', 'WEEK', 'MONTH', 'MIN_5', 'MIN_15', 'MIN_30', 'MIN_60']

// 日期默认（复用单标的逻辑）
function isoDaysFromNow(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}
const startDate = ref('2020-01-06')
const endDate = ref(isoDaysFromNow(0))

onMounted(async () => {
  store.loadStrategies().catch((e) => {
    store.error = `加载策略列表失败：${e instanceof Error ? e.message : e}`
  })

  // 从 URL query 回填（策略库「载入」组合策略跳转带来）
  const qStrategy = route.query.strategy as string | undefined
  const qParams = route.query.params as string | undefined
  const qStocks = route.query.stocks as string | undefined
  const qStartDate = route.query.startDate as string | undefined
  const qEndDate = route.query.endDate as string | undefined
  const qCategory = route.query.category as Category | undefined
  if (qStrategy) {
    strategy.value = qStrategy
    await nextTick()
  }
  if (qParams) {
    try {
      params.value = JSON.parse(qParams) as Record<string, number | string | boolean>
    } catch {
      // 解析失败忽略
    }
  }
  if (qStocks) {
    stocks.value = qStocks
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
  }
  if (qStartDate) startDate.value = qStartDate
  if (qEndDate) endDate.value = qEndDate
  if (qCategory) category.value = qCategory

  // V223: 恢复上次候选批量验证结果（如有）
  restoreCandBatchPersist()
})

async function onRun() {
  await store.runPortfolio({
    strategy: strategy.value,
    params: params.value,
    cash: cash.value,
    execution: execution.value,
    stocks: stocks.value,
    category: category.value,
    start_date: startDate.value,
    end_date: endDate.value,
    out_of_sample: checkOutOfSample.value,
    oos_train_ratio: oosTrainRatio.value,
    use_walk_forward: checkWalkForward.value,
    step_ratio: 0.1,
  })
}

// V160: 批量验证候选股（对全局自选股用当前策略各跑一次回测，按可信度排名）
interface CandRow {
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
  // V184: 该候选股样本外验证结论
  oos_degraded: boolean | null
  oos_verdict: string
  // V316: 该候选股 Walk-Forward 滚动验证结论
  wf_degraded: boolean | null
  wf_verdict: string
}
const candRows = ref<CandRow[]>([])
const candLoading = ref(false)
const candMsg = ref('')
// V223: 组合候选批量验证结果持久化（与回测 V217 / 监控 V219 / 选股 V221 对齐）
const CAND_BATCH_KEY = 'easy_tdx_cand_batch_verify_last'
const lastCandBatchAt = ref('')
function saveCandBatchPersist() {
  if (!candRows.value.length) return
  try {
    localStorage.setItem(
      CAND_BATCH_KEY,
      JSON.stringify({
        rows: candRows.value,
        strategy: strategy.value,
        strategy_label: strategyLabel.value || strategy.value,
        at: new Date().toISOString(),
      }),
    )
  } catch {
    /* localStorage 不可用忽略 */
  }
}
function restoreCandBatchPersist() {
  try {
    const raw = localStorage.getItem(CAND_BATCH_KEY)
    if (!raw) return
    const data = JSON.parse(raw)
    if (Array.isArray(data.rows) && data.rows.length) {
      candRows.value = data.rows
      lastCandBatchAt.value = data.at || ''
      candMsg.value = '已恢复上次候选批量验证（' + (data.strategy_label || '') + '）'
    }
  } catch {
    /* 解析失败忽略 */
  }
}
const candSort = ref<'return' | 'trust'>('trust')
// V195: 仅看样本外稳健（过滤掉 oos_degraded=true 的候选股）
const candOnlyRobust = ref(false)
// V319: 仅看滚验稳健（过滤掉 wf_degraded=true 的候选股）
const candOnlyWfRobust = ref(false)
const sortedCandRows = computed(() => {
  let base = candRows.value
  if (candOnlyRobust.value) base = base.filter((r) => r.oos_degraded === false)
  if (candOnlyWfRobust.value) base = base.filter((r) => r.wf_degraded === false)
  const filtered = base
  if (!filtered.length || candSort.value === 'trust') return filtered
  return [...filtered].sort((a, b) => (b.total_return ?? -Infinity) - (a.total_return ?? -Infinity))
})
async function runCandVerify() {
  if (candLoading.value) return
  let raw: any[] = []
  try {
    raw = JSON.parse(localStorage.getItem('easy_tdx_global_watchlist') ?? '[]')
  } catch {
    raw = []
  }
  const watch = raw.filter((w) => w && w.code && w.market).slice(0, 12)
  if (watch.length === 0) {
    candMsg.value = '自选股为空：请先在缠论分析页「加入自选股」'
    setTimeout(() => {
      candMsg.value = ''
    }, 3500)
    return
  }
  candLoading.value = true
  candMsg.value = ''
  const rows: CandRow[] = []
  try {
    for (const w of watch) {
      try {
        const bars = await fetchBars(w.market, w.code, category.value, undefined, undefined, 500)
        if (bars.length < 30) continue
        const result = await runBacktest({
          strategy: strategy.value,
          params: params.value,
          cash: cash.value / Math.max(stocks.value.length, 1),
          commission: 0.0003,
          slippage: 0,
          execution: execution.value,
          out_of_sample: true,
          use_walk_forward: true,
          step_ratio: 0.1,
          oos_train_ratio: 0.7,
          ohlcv: bars,
        })
        const h5 = result.signal_accuracy?.buy?.horizons?.['5']
        const oos = result.out_of_sample
        rows.push({
          symbol: w.symbol || w.market + w.code,
          market: w.market,
          code: w.code,
          total_return: result.performance.total_return ?? null,
          win_rate: result.performance.win_rate ?? null,
          hit_rate: h5 && h5.count > 0 ? h5.hit_rate : null,
          excess_hit_rate: h5 && h5.count > 0 ? h5.excess_hit_rate : null,
          trust_score: result.model_trust?.score ?? null,
          trust_grade: result.model_trust?.grade ?? null,
          trades: result.performance.total_trades ?? null,
          oos_degraded: oos?.degraded ?? null,
          oos_verdict: oos?.verdict ?? '',
          wf_degraded: result.walk_forward?.degraded ?? null,
          wf_verdict: result.walk_forward?.verdict ?? '',
        })
      } catch {
        /* 单只失败跳过 */
      }
    }
    rows.sort((a, b) => (b.trust_score ?? -1) - (a.trust_score ?? -1))
    candRows.value = rows
    lastCandBatchAt.value = new Date().toISOString()
    saveCandBatchPersist()
    if (rows.length === 0) candMsg.value = '批量验证无结果（行情取数失败或数据不足）'
  } catch (e) {
    candMsg.value = '批量验证失败：' + formatError(e)
  } finally {
    candLoading.value = false
  }
}
function addCandToPortfolio(r: CandRow) {
  const sym = r.market + ':' + r.code
  if (!stocks.value.includes(sym)) stocks.value.push(sym)
}
// V237: 从候选排名直达该股单标缠论回测（与选股 V118 / 回测 V137 对齐）
function viewCandStock(r: CandRow) {
  router.push({
    path: '/',
    query: {
      symbol: r.market + r.code,
      category: 'DAY',
      strategy: strategy.value,
      params: JSON.stringify(params.value ?? {}),
    },
  })
}
function addAllCands() {
  for (const r of candRows.value) {
    const sym = r.market + ':' + r.code
    if (!stocks.value.includes(sym)) stocks.value.push(sym)
  }
}
function candPct(v: number | null | undefined): string {
  return v === null || v === undefined || !Number.isFinite(v) ? '-' : (v * 100).toFixed(1) + '%'
}
function candTrust(r: CandRow): string {
  if (r.trust_score === null || r.trust_score === undefined) return '-'
  return Math.round(r.trust_score) + ' ' + (r.trust_grade ?? '')
}
// V184: 样本外列辅助
function candOosLabel(r: CandRow): string {
  if (r.oos_degraded === null || r.oos_degraded === undefined) return '-'
  return r.oos_degraded ? '⚠衰减' : '✅泛化'
}
function candOosCls(r: CandRow): string {
  if (r.oos_degraded === null || r.oos_degraded === undefined) return ''
  return r.oos_degraded ? 'neg' : 'pos'
}
function candOosTitle(r: CandRow): string {
  return r.oos_verdict || ''
}
// V188: 把候选批量验证选出的股票保存为组合策略（kind=portfolio，与 V131/V141/V145 对齐）
const candSaveMsg = ref('')
const candSaving = ref(false)
async function saveCandAsPortfolio() {
  if (candRows.value.length === 0 || candSaving.value) return
  candSaving.value = true
  candSaveMsg.value = ''
  try {
    // V203: 保存遵循「仅看样本外稳健」过滤——开启时只把筛选视图里的 ✅泛化 标的入库
    const visible = candOnlyRobust.value
      ? candRows.value.filter((c) => c.oos_degraded === false)
      : candRows.value
    if (visible.length === 0) {
      candSaveMsg.value = '没有样本外稳健的候选股可保存（请关闭「仅看样本外稳健」再试）'
      candSaving.value = false
      setTimeout(() => {
        candSaveMsg.value = ''
      }, 4000)
      return
    }
    const stocks = visible.map((c) => c.market + ':' + c.code)
    const avgTrust = visible.length
      ? visible.reduce((s, c) => s + (c.trust_score ?? 0), 0) / visible.length
      : 0
    // V190: 样本外聚合（逐只开启 out_of_sample 后统计衰减比例）
    const oosKnown = visible.filter((c) => c.oos_degraded !== null && c.oos_degraded !== undefined)
    const oosDegradedN = oosKnown.filter((c) => c.oos_degraded === true).length
    const oosRatio = oosKnown.length ? oosDegradedN / oosKnown.length : null
    const oosVerdict = oosKnown.length
      ? oosRatio! < 0.5
        ? '✅ ' + (oosKnown.length - oosDegradedN) + '/' + oosKnown.length + ' 只样本外稳健'
        : '⚠ ' + oosDegradedN + '/' + oosKnown.length + ' 只样本外衰减'
      : ''
    await saveStrategy({
      name: (strategyLabel.value || strategy.value) + ' · 候选验证' + stocks.length + '只',
      kind: 'portfolio',
      strategy: strategy.value,
      strategy_label: strategyLabel.value,
      params: params.value,
      context: {
        stocks,
        category: category.value,
        start_date: startDate.value || undefined,
        end_date: endDate.value || undefined,
      },
      trade_config: { cash: cash.value, execution: execution.value },
      snapshot: {
        total_stocks: stocks.length,
        avg_trust_score: avgTrust,
        avg_oos_degraded: oosRatio,
        oos_verdict: oosVerdict,
        source: 'batch-verify-cand',
        saved_at: new Date().toISOString().slice(0, 10),
      },
      tags: ['候选验证'],
      notes: '由组合回测页候选批量验证生成，可在策略库载入后组合页复跑。',
    })
    candSaveMsg.value = '✓ 已保存为组合策略，可在「策略库」载入复跑'
    setTimeout(() => {
      candSaveMsg.value = ''
    }, 4000)
  } catch (e) {
    candSaveMsg.value = '保存失败：' + formatError(e)
  } finally {
    candSaving.value = false
  }
}
// V170: 候选批量验证导出（复制排名 / 复制 JSON，与其它批量验证入口对齐）
const candCopyMsg = ref('')
function copyCandRanking() {
  if (candRows.value.length === 0) return
  const lines: string[] = []
  lines.push('# easy-tdx 组合候选批量验证（' + (strategyLabel.value || strategy.value) + '）')
  lines.push('')
  lines.push('| 排名 | 标的 | 总收益 | 胜率 | 5根命中率 | 超额命中率 | 可信度 | 样本外 | 交易数 |')
  lines.push('| --- | --- | --- | --- | --- | --- | --- | --- | --- |')
  sortedCandRows.value.forEach((r, i) => {
    lines.push(
      '| ' +
        (i + 1) +
        ' | ' +
        r.symbol +
        ' | ' +
        candPct(r.total_return) +
        ' | ' +
        candPct(r.win_rate) +
        ' | ' +
        candPct(r.hit_rate) +
        ' | ' +
        candPct(r.excess_hit_rate) +
        ' | ' +
        candTrust(r) +
        ' | ' +
        candOosLabel(r) +
        ' | ' +
        (r.trades ?? '-') +
        ' |',
    )
  })
  lines.push('')
  lines.push(
    '方法：读全局自选股（最多 12 只），用当前策略独立回测（最近 500 根日线），按模型可信度（V101）降序排名。',
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
    candCopyMsg.value = '✓ 已复制候选排名'
    setTimeout(() => {
      candCopyMsg.value = ''
    }, 2500)
  }
  void doCopy()
}
const candJsonMsg = ref('')
async function copyCandJson() {
  if (candRows.value.length === 0) return
  const payload = {
    strategy: strategy.value,
    strategy_label: strategyLabel.value,
    params: params.value,
    generated_at: new Date().toISOString(),
    rows: sortedCandRows.value.map((r, i) => ({ rank: i + 1, ...r })),
  }
  const json = JSON.stringify(payload, null, 2)
  try {
    await navigator.clipboard.writeText(json)
    candJsonMsg.value = '✓ 已复制候选 JSON'
  } catch {
    candJsonMsg.value = '复制失败（浏览器权限）'
  }
  setTimeout(() => {
    candJsonMsg.value = ''
  }, 2500)
}
// V255: 候选批量验证导出 CSV（Excel 友好，与回测页 V253 对齐）
const candCsvMsg = ref('')
function candCsvEscape(v: string): string {
  return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v
}
function exportCandCsv() {
  if (candRows.value.length === 0) return
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
  sortedCandRows.value.forEach((r, i) => {
    const row = [
      i + 1,
      candCsvEscape(r.symbol),
      candPct(r.total_return),
      candPct(r.win_rate),
      candPct(r.hit_rate),
      candPct(r.excess_hit_rate),
      candCsvEscape(candTrust(r)),
      candOosLabel(r),
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
    a.download = 'easy_tdx_cand_batch_verify_' + new Date().toISOString().slice(0, 10) + '.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    candCsvMsg.value = '✓ 已导出 CSV'
  } catch {
    candCsvMsg.value = '导出失败（浏览器权限）'
  }
  setTimeout(() => {
    candCsvMsg.value = ''
  }, 2500)
}

// ── 保存策略（把当前组合结果 + 配置 + 上下文存进策略库）──────────────────────
const showSaveForm = ref(false)
const saving = ref(false)
const saveName = ref('')
const saveTags = ref('')
const saveNotes = ref('')
const saveMsg = ref('')
// V127: 组合报告导出（Markdown 复制）
const copyMsg = ref('')
function buildPortfolioReportText(): string {
  const r = store.portfolioResult
  if (!r) return ''
  const pct = (v: number | null | undefined) =>
    v === null || v === undefined || !Number.isFinite(v) ? '-' : (v * 100).toFixed(2) + '%'
  const lines: string[] = []
  lines.push('# easy-tdx 组合回测报告')
  lines.push('')
  lines.push('- 策略：' + (strategyLabel.value || strategy.value))
  lines.push('- 标的：' + stocks.value.join(' '))
  lines.push('- 初始资金：' + cash.value.toLocaleString())
  lines.push('')
  const p = r.total_performance
  lines.push('## 组合绩效')
  lines.push('- 总收益：' + pct(p.total_return) + ' · 年化：' + pct(p.annual_return))
  lines.push(
    '- 最大回撤：' +
      pct(p.max_drawdown) +
      ' · 夏普：' +
      (p.sharpe ?? 0).toFixed(2) +
      ' · 胜率：' +
      pct(p.win_rate),
  )
  lines.push('- 标的总数：' + p.total_stocks + ' · 总资金：' + p.total_cash.toLocaleString())
  lines.push('')
  if (r.portfolio_trust) {
    lines.push('## 组合可信度（V103）')
    lines.push(
      '- 综合评分：' +
        Math.round(r.portfolio_trust.score) +
        '/100 · ' +
        r.portfolio_trust.grade +
        '可信',
    )
    lines.push('- 结论：' + (r.portfolio_trust.verdict || ''))
    lines.push('')
  }
  if (r.accuracy_summary) {
    lines.push('## 组合准确度（V99）')
    lines.push('- ' + (r.accuracy_summary.verdict || ''))
    const pf = r.accuracy_summary.portfolio
    if (pf) {
      lines.push(
        '- 加权5根命中率：' +
          pct(pf.avg_hit_rate) +
          ' · 超额：' +
          pct(pf.avg_excess_hit_rate) +
          ' · 正收益标的：' +
          pf.positive_symbols +
          '/' +
          pf.symbols,
      )
    }
    lines.push('')
  }
  if (r.out_of_sample) {
    lines.push('## 组合样本外验证（V126）')
    lines.push('- ' + (r.out_of_sample.verdict || ''))
    lines.push(
      '- 平均训练段：' +
        pct(r.out_of_sample.avg_train_return) +
        ' · 平均样本外：' +
        pct(r.out_of_sample.avg_test_return),
    )
    lines.push('')
  }
  // V303: 组合级 Walk-Forward 滚动验证段
  const wfr = (r as any).walk_forward
  if (wfr) {
    lines.push('## 组合 Walk-Forward 滚动验证（防过拟合）')
    lines.push('- ' + (wfr.verdict || ''))
    if (wfr.per_symbol) {
      const per = Object.entries(wfr.per_symbol as Record<string, { degraded?: boolean }>)
        .map(([sym, v]) => sym + (v.degraded ? ' ⚠' : ' ✅'))
        .join(' · ')
      lines.push('- ' + per)
    }
    lines.push('')
  }
  lines.push('---')
  lines.push(
    '> 💡 各标的的 V102 缠论决策支持（入场/止损/止盈/仓位/RRR）请到「诊断」页查看，或运行 easy-tdx advice MARKET CODE 一键回放。',
  )
  lines.push('生成时间：' + new Date().toLocaleString('zh-CN'))
  return lines.join('\n')
}
async function copyReport() {
  const text = buildPortfolioReportText()
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // 降级：document.execCommand
    const ta = document.createElement('textarea')
    ta.value = text
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
  }
  copyMsg.value = '✓ 已复制组合报告'
  setTimeout(() => {
    copyMsg.value = ''
  }, 2500)
}
// V162: 组合回测报告 JSON 导出（机器可读，Agent/脚本友好，与 V153/V157/V158 对齐）
const jsonCopyMsg = ref('')
async function copyPortfolioJson() {
  if (!store.portfolioResult) return
  const json = JSON.stringify(store.portfolioResult, null, 2)
  try {
    await navigator.clipboard.writeText(json)
    jsonCopyMsg.value = '✓ 已复制组合报告 JSON'
  } catch {
    jsonCopyMsg.value = '复制失败（浏览器权限）'
  }
  setTimeout(() => {
    jsonCopyMsg.value = ''
  }, 2500)
}
// V259: 组合报告导出 CSV（组合绩效 + 各标的对比表，Excel 友好）
const portCsvMsg = ref('')
function portPctV(v: number | null | undefined): string {
  return v === null || v === undefined || !Number.isFinite(v) ? '-' : (v * 100).toFixed(2) + '%'
}
function portCsvEscape(v: string): string {
  return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v
}
function exportPortfolioCsv() {
  const r = store.portfolioResult
  if (!r) return
  const lines: string[] = []
  // 组合绩效块
  const p = r.total_performance
  lines.push('# 组合绩效')
  lines.push(['指标', '值'].join(','))
  lines.push(['总收益', portPctV(p.total_return)].join(','))
  lines.push(['年化收益', portPctV(p.annual_return)].join(','))
  lines.push(['最大回撤', portPctV(p.max_drawdown)].join(','))
  lines.push(['夏普比率', p.sharpe != null ? p.sharpe.toFixed(2) : ''].join(','))
  lines.push(['胜率', portPctV(p.win_rate)].join(','))
  lines.push(['标的总数', String(p.total_stocks ?? '')].join(','))
  lines.push(['总资金', String(p.total_cash ?? '')].join(','))
  if (r.portfolio_trust) {
    lines.push(
      [
        '组合可信度',
        String(r.portfolio_trust.grade ?? '') +
          '（' +
          Math.round(r.portfolio_trust.score) +
          '/100）',
      ].join(','),
    )
  }
  if (r.accuracy_summary) {
    const pf = r.accuracy_summary.portfolio
    lines.push(['加权5根命中率', pf ? portPctV(pf.avg_hit_rate) : '-'].join(','))
    lines.push(['超额命中率', pf ? portPctV(pf.avg_excess_hit_rate) : '-'].join(','))
  }
  if (r.out_of_sample) {
    lines.push(['样本外结论', portCsvEscape(r.out_of_sample.verdict || '')].join(','))
    lines.push(
      [
        '样本外稳健数',
        String(r.out_of_sample.symbols - (r.out_of_sample.degraded_symbols || 0)) +
          '/' +
          String(r.out_of_sample.symbols),
      ].join(','),
    )
  }
  lines.push('')
  // 各标的对比块
  lines.push('# 各标的对比')
  lines.push(
    ['标的', '总收益', '年化收益', '最大回撤', '夏普', '胜率', '交易次数', '盈亏比'].join(','),
  )
  Object.entries(r.individual_results || {}).forEach(([key, res]) => {
    const perf = res.performance || {}
    lines.push(
      [
        portCsvEscape(key),
        portPctV(perf.total_return),
        portPctV(perf.annual_return),
        portPctV(perf.max_drawdown),
        perf.sharpe != null ? perf.sharpe.toFixed(2) : '',
        portPctV(perf.win_rate),
        String(perf.total_trades ?? ''),
        perf.profit_factor != null ? perf.profit_factor.toFixed(2) : '',
      ].join(','),
    )
  })
  const csv = '\uFEFF' + lines.join('\n')
  try {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'easy_tdx_portfolio_' + new Date().toISOString().slice(0, 10) + '.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    portCsvMsg.value = '✓ 已导出组合报告 CSV'
  } catch {
    portCsvMsg.value = '导出失败（浏览器权限）'
  }
  setTimeout(() => {
    portCsvMsg.value = ''
  }, 2500)
}
// V285: 组合交易明细导出 CSV（聚合各标的成交记录，带标的列，与回测页 V261 对齐）
const portTradesCsvMsg = ref('')
function portTradesEscape(v: string): string {
  return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v
}
function exportPortfolioTradesCsv() {
  const r = store.portfolioResult
  if (!r) return
  const ind = r.individual_results as unknown as
    Record<string, { trades?: Array<Record<string, unknown>> }> | undefined
  if (!ind || Object.keys(ind).length === 0) {
    portTradesCsvMsg.value = '没有可导出的成交记录'
    setTimeout(() => {
      portTradesCsvMsg.value = ''
    }, 2500)
    return
  }
  const header = [
    '标的',
    '时间',
    '方向',
    '数量',
    '价格',
    '手续费',
    '滑点',
    '已实现盈亏',
    '成本基数',
  ]
  const rows: string[] = []
  Object.entries(ind).forEach(([key, res]) => {
    const trades = res.trades || []
    trades.forEach((t) => {
      if (t.rejected) return
      rows.push(
        [
          portTradesEscape(key),
          String(t.datetime ?? ''),
          portTradesEscape(String(t.direction ?? '')),
          String(t.size ?? ''),
          String(t.price ?? ''),
          String(t.commission ?? ''),
          String(t.slippage ?? ''),
          String(t.pnl ?? ''),
          String(t.cost_basis ?? ''),
        ].join(','),
      )
    })
  })
  const csv = '\uFEFF' + [header.join(','), ...rows].join('\n')
  try {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'easy_tdx_portfolio_trades_' + new Date().toISOString().slice(0, 10) + '.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    portTradesCsvMsg.value = '✓ 已导出组合交易明细 CSV'
  } catch {
    portTradesCsvMsg.value = '导出失败（浏览器权限）'
  }
  setTimeout(() => {
    portTradesCsvMsg.value = ''
  }, 2500)
}

const strategyLabel = computed(
  () => store.strategies.find((s) => s.name === strategy.value)?.label ?? strategy.value,
)

// 组合评级：从 combined_equity 重算夏普/卡玛/波动率等（组合级净值算不出胜率/利润因子），
// 用 5 维度评分。净值点数过少（< 60 个交易日）视为样本不足。
const grade = computed(() => (store.portfolioResult ? gradePortfolio(store.portfolioResult) : null))

function openSaveForm() {
  saveName.value = `${strategyLabel.value} · 组合${stocks.value.length}只`
  saveTags.value = ''
  saveNotes.value = ''
  saveMsg.value = ''
  showSaveForm.value = true
}

// 从自选股加载标的
function loadFromWatchlist() {
  try {
    const raw = localStorage.getItem('easy_tdx_global_watchlist')
    if (!raw) return
    const watchlist: any[] = JSON.parse(raw)
    const symbols = watchlist.map((w: any) => `${w.market}:${w.code}`)
    if (symbols.length > 0) {
      stocks.value = symbols
    }
  } catch {
    // ignore
  }
}

// 清空所有标的
function clearAll() {
  stocks.value = []
}

async function onSave() {
  if (!store.portfolioResult || !saveName.value.trim()) return
  saving.value = true
  saveMsg.value = ''
  try {
    const perf = store.portfolioResult.total_performance
    await saveStrategy({
      name: saveName.value.trim(),
      kind: 'portfolio',
      strategy: strategy.value,
      strategy_label: strategyLabel.value,
      params: params.value,
      context: {
        stocks: stocks.value,
        category: category.value,
        start_date: startDate.value,
        end_date: endDate.value,
      },
      trade_config: {
        cash: cash.value,
        execution: execution.value,
      },
      snapshot: {
        total_return: perf.total_return,
        annual_return: perf.annual_return,
        total_stocks: perf.total_stocks,
        // V134: 组合验证结论一并入快照（字段与单标 V122 对齐，策略库卡片可展示）
        accuracy: {
          hit_rate: store.portfolioResult.accuracy_summary?.portfolio?.avg_hit_rate ?? null,
          excess_hit_rate:
            store.portfolioResult.accuracy_summary?.portfolio?.avg_excess_hit_rate ?? null,
          verdict: store.portfolioResult.accuracy_summary?.verdict ?? '',
        },
        trust: {
          score: store.portfolioResult.portfolio_trust?.score ?? null,
          grade: store.portfolioResult.portfolio_trust?.grade ?? '',
          verdict: store.portfolioResult.portfolio_trust?.verdict ?? '',
        },
        out_of_sample: {
          degraded: store.portfolioResult.out_of_sample?.degraded ?? false,
          verdict: store.portfolioResult.out_of_sample?.verdict ?? '',
          train_return: store.portfolioResult.out_of_sample?.avg_train_return ?? null,
          test_return: store.portfolioResult.out_of_sample?.avg_test_return ?? null,
        },
      },
      tags: saveTags.value
        .split(/[,，]/)
        .map((t) => t.trim())
        .filter(Boolean),
      notes: saveNotes.value,
    })
    saveMsg.value = '✓ 已保存到策略库'
    showSaveForm.value = false
  } catch (e) {
    saveMsg.value = `保存失败：${formatError(e)}`
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="portfolio-view">
    <aside class="config-panel">
      <section class="panel-section">
        <h3>标的列表</h3>
        <StocksPicker v-model="stocks" />
        <div class="watchlist-load">
          <button class="ghost small" @click="loadFromWatchlist">📌 从自选股加载</button>
          <button class="ghost small" @click="clearAll">清空</button>
        </div>
      </section>
      <section class="panel-section">
        <h3>批量验证候选股（选股验证）</h3>
        <p class="hint">
          读全局自选股（最多 12 只），用当前策略逐只回测并按可信度排名，可一键加入组合标的。
        </p>
        <div class="cand-bar">
          <button
            class="ghost small"
            :disabled="candLoading || !store.strategies.length"
            @click="runCandVerify"
          >
            {{ candLoading ? '批量验证中…' : '🧪 批量验证候选股' }}
          </button>
          <span v-if="candMsg" class="cand-msg">{{ candMsg }}</span>
        </div>
        <div v-if="candRows.length" class="cand-table-wrap">
          <div class="cand-head">
            <span
              >候选排名（{{ candRows.length }}）
              <span v-if="lastCandBatchAt" class="cand-batch-at" :title="'上次验证时间'"
                >🕒 {{ new Date(lastCandBatchAt).toLocaleString() }}</span
              >
            </span>
            <span class="cand-sort">
              <button
                class="ghost small"
                :class="{ active: candSort === 'return' }"
                @click="candSort = 'return'"
              >
                按收益
              </button>
              <button
                class="ghost small"
                :class="{ active: candSort === 'trust' }"
                @click="candSort = 'trust'"
              >
                按可信度
              </button>
              <button
                class="ghost small"
                :class="{ active: candOnlyRobust }"
                :title="
                  '仅保留样本外 ✅泛化 的候选股（当前 ' +
                  candRows.filter((r: CandRow) => r.oos_degraded === false).length +
                  ' 只）'
                "
                @click="candOnlyRobust = !candOnlyRobust"
              >
                ✅ 仅看样本外稳健
              </button>
              <button
                class="ghost small"
                :class="{ active: candOnlyWfRobust }"
                :title="
                  '仅保留滚验 ✅稳 的候选股（当前 ' +
                  candRows.filter((r: CandRow) => r.wf_degraded === false).length +
                  ' 只）'
                "
                @click="candOnlyWfRobust = !candOnlyWfRobust"
              >
                ✅ 仅看滚验稳健
              </button>
              <button class="ghost small" @click="copyCandRanking">📋 复制排名</button>
              <button class="ghost small" @click="copyCandJson">⚙ 复制 JSON</button>
              <button class="ghost small" @click="exportCandCsv">📊 导出 CSV</button>
              <button class="ghost small" :disabled="candSaving" @click="saveCandAsPortfolio">
                {{ candSaving ? '保存中…' : '💾 保存为组合策略' }}
              </button>
              <button class="ghost small" @click="addAllCands">全部加入组合</button>
              <span v-if="candSaveMsg" class="cand-msg">{{ candSaveMsg }}</span>
              <span v-if="candCsvMsg" class="cand-msg">{{ candCsvMsg }}</span>
            </span>
          </div>
          <table class="cand-table">
            <thead>
              <tr>
                <th>#</th>
                <th>标的</th>
                <th class="num">总收益</th>
                <th class="num">5根命中率</th>
                <th class="num" title="训练段 vs 未见过数据">样本外</th>
                <th class="num" title="Walk-Forward 滚动验证">滚验</th>
                <th class="num">可信度</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in sortedCandRows" :key="r.symbol">
                <td class="dim">{{ i + 1 }}</td>
                <td>{{ r.symbol }}</td>
                <td class="num" :class="(r.total_return ?? 0) >= 0 ? 'pos' : 'neg'">
                  {{ candPct(r.total_return) }}
                </td>
                <td class="num">{{ candPct(r.hit_rate) }}</td>
                <td class="num" :class="candOosCls(r)" :title="candOosTitle(r)">
                  {{ candOosLabel(r) }}
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
                <td
                  class="num"
                  :class="r.trust_grade === '高' ? 'pos' : r.trust_grade === '低' ? 'neg' : ''"
                >
                  {{ candTrust(r) }}
                </td>
                <td>
                  <button class="ghost small" @click="viewCandStock(r)">查看该股</button>
                  <button class="ghost small" @click="addCandToPortfolio(r)">加入组合</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel-section">
        <h3>策略</h3>
        <StrategyPicker
          v-if="store.strategies.length"
          v-model:strategy="strategy"
          v-model:params="params"
          :strategies="store.strategies"
        />
        <p v-else class="loading-text">加载策略中…</p>
      </section>

      <section class="panel-section">
        <h3>周期与日期</h3>
        <div class="field">
          <label>周期</label>
          <select v-model="category">
            <option v-for="c in CATEGORIES" :key="c" :value="c">{{ c }}</option>
          </select>
        </div>
        <div class="row">
          <div class="field">
            <label>开始</label>
            <input v-model="startDate" type="date" />
          </div>
          <div class="field">
            <label>结束</label>
            <input v-model="endDate" type="date" />
          </div>
        </div>
      </section>

      <section class="panel-section">
        <h3>资金</h3>
        <div class="field">
          <label>组合总资金</label>
          <input v-model.number="cash" type="number" min="1000" step="10000" />
        </div>
        <div class="field">
          <label>成交价</label>
          <select v-model="execution">
            <option v-for="e in EXECUTIONS" :key="e.value" :value="e.value">{{ e.label }}</option>
          </select>
        </div>
        <div class="field">
          <label>
            <input type="checkbox" v-model="checkOutOfSample" />
            样本外验证（训练/持有切分）
          </label>
          <select v-if="checkOutOfSample" v-model.number="oosTrainRatio" class="seg-count">
            <option :value="0.6">训练 60%</option>
            <option :value="0.7">训练 70%</option>
            <option :value="0.8">训练 80%</option>
          </select>
        </div>
        <div class="field">
          <label title="V299: 对组合内每只标的逐窗口回测聚合，评估组合参数防过拟合风险">
            <input type="checkbox" v-model="checkWalkForward" />
            Walk-Forward 滚动验证（防过拟合）
          </label>
        </div>
      </section>

      <button
        class="primary run-btn"
        :disabled="store.portfolioRunning || stocks.length === 0"
        @click="onRun"
      >
        {{ store.portfolioRunning ? '组合回测中…' : '开始组合回测' }}
      </button>
    </aside>

    <main class="report-panel">
      <div v-if="store.error" class="error-banner">⚠ {{ store.error }}</div>

      <div
        v-if="!store.portfolioResult && !store.portfolioRunning && !store.error"
        class="placeholder"
      >
        <p>添加多只标的，选择策略后点击「开始组合回测」</p>
      </div>

      <div v-if="store.portfolioResult" class="report-content">
        <div class="result-toolbar">
          <button class="ghost" @click="openSaveForm">💾 保存策略</button>
          <button class="ghost" @click="copyReport">📋 复制报告</button>
          <button class="ghost" @click="copyPortfolioJson">⚙ 复制 JSON</button>
          <button class="ghost" @click="exportPortfolioCsv">📊 导出 CSV</button>
          <button class="ghost" @click="exportPortfolioTradesCsv">📊 交易明细 CSV</button>
          <span v-if="copyMsg" class="save-msg">{{ copyMsg }}</span>
          <span v-if="jsonCopyMsg" class="save-msg">{{ jsonCopyMsg }}</span>
          <span v-if="portCsvMsg" class="save-msg">{{ portCsvMsg }}</span>
          <span v-if="portTradesCsvMsg" class="save-msg">{{ portTradesCsvMsg }}</span>
          <span v-if="saveMsg" class="save-msg">{{ saveMsg }}</span>
        </div>

        <!-- V112 组合验证总结 -->
        <section v-if="store.portfolioResult" class="report-section">
          <PortfolioValidationSummary :result="store.portfolioResult" />
        </section>

        <section v-if="grade" class="report-section">
          <h3>组合评级</h3>
          <GradeDetails :result="grade" expanded />
        </section>

        <section class="report-section">
          <h3>组合整体绩效</h3>
          <div class="perf-summary">
            <div class="perf-item">
              <span class="label">组合总收益</span>
              <span
                class="value"
                :class="store.portfolioResult.total_performance.total_return > 0 ? 'pos' : 'neg'"
              >
                {{ (store.portfolioResult.total_performance.total_return * 100).toFixed(2) }}%
              </span>
            </div>
            <div class="perf-item">
              <span class="label">标的数量</span>
              <span class="value">{{ store.portfolioResult.total_performance.total_stocks }}</span>
            </div>
            <div class="perf-item">
              <span class="label">组合总资金</span>
              <span class="value">{{
                store.portfolioResult.total_performance.total_cash.toFixed(0)
              }}</span>
            </div>
            <div class="perf-item">
              <span class="label">最大回撤</span>
              <span class="value neg"
                >{{
                  ((store.portfolioResult.total_performance.max_drawdown ?? 0) * 100).toFixed(2)
                }}%</span
              >
            </div>
            <div class="perf-item">
              <span class="label">夏普比率</span>
              <span class="value">{{
                (store.portfolioResult.total_performance.sharpe ?? 0).toFixed(2)
              }}</span>
            </div>
            <div class="perf-item">
              <span class="label">胜率</span>
              <span class="value"
                >{{
                  ((store.portfolioResult.total_performance.win_rate ?? 0) * 100).toFixed(1)
                }}%</span
              >
            </div>
          </div>
        </section>

        <section class="report-section">
          <h3>组合净值曲线</h3>
          <EquityChart :equity="store.portfolioResult.combined_equity" />
        </section>

        <section class="report-section">
          <h3>各标的绩效对比</h3>
          <PortfolioSummaryTable
            :results="store.portfolioResult.individual_results"
            :allocation="store.portfolioResult.equity_allocation"
          />
        </section>

        <!-- V299: 组合级 Walk-Forward 滚动窗口验证 -->
        <section v-if="(store.portfolioResult as any)?.walk_forward" class="report-section">
          <h3>🔁 组合 Walk-Forward 滚动验证（防过拟合）</h3>
          <div
            class="verdict-cell"
            :class="
              (store.portfolioResult as any).walk_forward.degraded_symbols >=
              Math.max(1, (store.portfolioResult as any).walk_forward.symbols * 0.5)
                ? 'neg'
                : 'pos'
            "
          >
            {{ (store.portfolioResult as any).walk_forward.verdict }}
          </div>
          <table class="cand-table wf-table">
            <thead>
              <tr>
                <th>标的</th>
                <th>窗口数</th>
                <th class="num">结论</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(v, sym, i) in (store.portfolioResult as any).walk_forward.per_symbol"
                :key="i"
              >
                <td>{{ sym }}</td>
                <td class="num">{{ v.windows ?? '-' }}</td>
                <td :class="v.degraded ? 'neg' : 'pos'" class="dim">{{ v.verdict }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <!-- V126: 组合级样本外验证（训练/持有切分） -->
        <section v-if="store.portfolioResult.out_of_sample" class="report-section">
          <h3>🔬 组合样本外验证（训练段 vs 未见过数据）</h3>
          <PortfolioOutOfSamplePanel :report="store.portfolioResult.out_of_sample" />
        </section>

        <section v-if="store.portfolioResult.accuracy_summary" class="report-section">
          <h3>🎯 组合准确度验证（逐标的命中率聚合 vs 随机基准）</h3>
          <PortfolioAccuracyPanel
            :report="store.portfolioResult.accuracy_summary"
            :trust="store.portfolioResult.portfolio_trust"
          />
        </section>

        <section class="report-section">
          <h3>各标的净值叠加（归一化）</h3>
          <PortfolioCompareChart :results="store.portfolioResult.individual_results" />
        </section>
      </div>
    </main>

    <!-- 保存策略对话框 -->
    <div v-if="showSaveForm" class="modal-overlay" @click.self="showSaveForm = false">
      <div class="modal">
        <h3>保存到策略库</h3>
        <p class="modal-desc">
          将当前组合策略 + 标的列表 + 成绩快照存下，下次可在「策略库」载入或重跑。
        </p>
        <div class="field">
          <label>名称</label>
          <input v-model="saveName" type="text" placeholder="给这个组合策略起个名" />
        </div>
        <div class="field">
          <label>标签（逗号分隔，可选）</label>
          <input v-model="saveTags" type="text" placeholder="如：消费,长线观察" />
        </div>
        <div class="field">
          <label>备注（可选）</label>
          <textarea v-model="saveNotes" rows="2" placeholder="为什么觉得它好？"></textarea>
        </div>
        <div class="modal-summary">
          {{ strategyLabel }} · {{ stocks.length }} 只 ·
          {{
            store.portfolioResult
              ? (store.portfolioResult.total_performance.total_return * 100).toFixed(2) + '%'
              : ''
          }}
        </div>
        <div class="modal-actions">
          <button class="ghost" :disabled="saving" @click="showSaveForm = false">取消</button>
          <button class="primary" :disabled="saving || !saveName.trim()" @click="onSave">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.portfolio-view {
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
.panel-section {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}
.panel-section:last-of-type {
  border-bottom: none;
}
.panel-section h3 {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 12px;
}
.loading-text {
  color: var(--text-dim);
  font-size: 12px;
}
.run-btn {
  width: 100%;
  padding: 10px;
  font-size: 14px;
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
.perf-summary {
  display: flex;
  gap: 32px;
}
.perf-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.perf-item .label {
  font-size: 12px;
  color: var(--text-dim);
}
.perf-item .value {
  font-size: 20px;
  font-weight: 600;
  font-family: var(--font-mono);
}
.pos {
  color: var(--up);
}
.neg {
  color: var(--down);
}

/* 结果工具条 + 保存对话框 */
.result-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.result-toolbar .ghost {
  font-size: 12px;
  padding: 6px 12px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  cursor: pointer;
}
.result-toolbar .ghost:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.save-msg {
  font-size: 12px;
  color: var(--up);
}
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.modal {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  width: 380px;
  max-width: 90vw;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.modal h3 {
  font-size: 15px;
  font-weight: 600;
}
.modal-desc {
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.5;
}
.modal .field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.modal .field label {
  font-size: 12px;
  color: var(--text-muted);
}
.modal .field input,
.modal .field textarea {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 7px 9px;
  font-size: 13px;
  color: var(--text);
  font-family: inherit;
  resize: vertical;
}
.modal-summary {
  font-size: 12px;
  color: var(--text-dim);
  font-family: var(--font-mono);
  padding: 8px 10px;
  background: var(--bg);
  border-radius: var(--radius);
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
.modal-actions .ghost {
  font-size: 13px;
  padding: 7px 16px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  cursor: pointer;
}
.modal-actions .primary {
  font-size: 13px;
  padding: 7px 16px;
  cursor: pointer;
}
.modal-actions .primary:disabled,
.modal-actions .ghost:disabled {
  opacity: 0.5;
  cursor: default;
}

/* 自选股加载按钮 */
.watchlist-load {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}
.watchlist-load .ghost {
  font-size: 11px;
  padding: 3px 8px;
}

/* V160: 批量验证候选股 */
.cand-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.cand-msg {
  font-size: 12px;
  color: var(--warn, #f59e0b);
}
.cand-table-wrap {
  margin-top: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px;
}
.cand-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 6px;
}
/* V223: 上次组合候选批量验证时间 */
.cand-batch-at {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 400;
  margin-left: 8px;
}
.cand-sort {
  display: flex;
  gap: 4px;
  align-items: center;
}
.cand-sort .ghost.active {
  background: rgba(96, 165, 250, 0.18);
  color: var(--accent);
  border-color: var(--accent);
}
.cand-msg {
  font-size: 11px;
  color: var(--up);
}
.cand-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.cand-table th {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 600;
  padding: 4px 6px;
  border-bottom: 1px solid var(--border);
  text-align: right;
}
.cand-table th:first-child,
.cand-table td:first-child {
  text-align: left;
}
.cand-table td {
  padding: 4px 6px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  text-align: right;
  font-family: var(--font-mono);
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
</style>
