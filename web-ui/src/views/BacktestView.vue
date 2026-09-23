<script setup lang="ts">
// 回测主页面：左配置面板 / 右报告面板。
// 编排：点击「开始回测」→ 自动取行情 → 回测 → 展示 K线+净值+指标+成交。
// 取行情已整合进「开始回测」（不再有单独的取行情按钮）。

import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import ChanlunChart from '../components/ChanlunChart.vue'
// BUILD_TEST_MARKER_67890
import EquityChart from '../components/EquityChart.vue'
import GradeDetails from '../components/GradeDetails.vue'
import ModelTrustPanel from '../components/ModelTrustPanel.vue'
import SignalAccuracyPanel from '../components/SignalAccuracyPanel.vue'
import ChanlunAccuracyPanel from '../components/ChanlunAccuracyPanel.vue'
import OutOfSamplePanel from '../components/OutOfSamplePanel.vue'
import SegmentRobustnessPanel from '../components/SegmentRobustnessPanel.vue'
import WalkForwardPanel from '../components/WalkForwardPanel.vue'
import ValidationSummaryPanel from '../components/ValidationSummaryPanel.vue'
import KlineChart from '../components/KlineChart.vue'
import MetricTable from '../components/MetricTable.vue'
import StrategyPicker from '../components/StrategyPicker.vue'
import SymbolPicker from '../components/SymbolPicker.vue'
import TradeTable from '../components/TradeTable.vue'
import { fetchBars, formatError, runBacktest, saveStrategy } from '../api'
import { useEarlierBars } from '../composables/useEarlierBars'
import { detectMarket } from '../market'
import { gradePerformance } from '../grading'
import type { Category, ExecutionMode } from '../types'
import { useBacktestStore } from '../stores/backtest'

const store = useBacktestStore()
const route = useRoute()

// SymbolPicker 实例引用，用于触发取行情
const symbolPicker = ref<InstanceType<typeof SymbolPicker> | null>(null)

// 镜像 SymbolPicker 的代码/周期/日期，与 SymbolPicker 通过 v-model 双向同步。
// 初始值与 SymbolPicker 默认一致；onMounted 时若 URL query 带了寻优页传来的值则覆盖。
const code = ref('000001')
const category = ref<Category>('DAY')
function isoDaysFromNow(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}
const startDate = ref('2020-01-06')
const endDate = ref(isoDaysFromNow(0))

// 表单状态（v-model 给子组件）
const strategy = ref('ma_cross')
const params = ref<Record<string, number | string | boolean>>({})
const cash = ref(1000000)
const commission = ref(0.0003)
const slippage = ref(0)
const execution = ref<ExecutionMode>('next_open')
// 分段稳健性/过拟合检查：false=不检查；true=按 robustnessSegmentCount 分段重跑
const checkRobustness = ref(false)
const robustnessSegmentCount = ref(3)
// 样本外验证（V105）：把区间切成训练段 + 样本外持有段验证模型泛化能力
const checkOutOfSample = ref(false)
// V287: Walk-Forward 滚动窗口验证（逐窗口回测聚合防过拟合判定）
const checkWalkForward = ref(false)
const oosTrainRatio = ref(0.7)

// 缠论相关状态
const chanlunLoading = ref(false)
const chanlunError = ref('')
const chanlunBis = ref<any[]>([])
const chanlunXds = ref<any[]>([])
const chanlunZss = ref<any[]>([])
const chanlunMmds = ref<any[]>([])
const chanlunFxs = ref<any[]>([])
const chanlunBcs = ref<any[]>([])
const chanlunZsds = ref<any[]>([])
const chanlunQsds = ref<any[]>([])
const chanlunMacd = ref<{ dif: number[]; dea: number[]; hist: number[] } | null>(null)
const chanlunLevel = ref<'bi' | 'xd'>('bi')
const chanlunRaw = ref<any>(null)

// 成交价模式（精简为 开盘价/收盘价）
const EXECUTIONS: { value: ExecutionMode; label: string }[] = [
  { value: 'next_open', label: '开盘价' },
  { value: 'next_close', label: '收盘价' },
]

// ── 最近浏览股票（localStorage 持久化）────────────────────────────
interface RecentStock {
  code: string
  market: string
  category: Category
  timestamp: number
}
const RECENT_KEY = 'easy_tdx_recent_stocks'
const recentStocks = ref<RecentStock[]>([])

function loadRecentStocks() {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    if (raw) recentStocks.value = JSON.parse(raw)
  } catch {
    /* ignore */
  }
}

function saveRecentStock(code: string, cat: Category) {
  const market = detectMarket(code)
  // 去重：移除已存在的
  recentStocks.value = recentStocks.value.filter((s) => s.code !== code)
  // 添加至头部
  recentStocks.value.unshift({ code, market, category: cat, timestamp: Date.now() })
  // 只保留最近20条
  recentStocks.value = recentStocks.value.slice(0, 20)
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(recentStocks.value))
  } catch {
    /* ignore */
  }
}

function clearRecentStocks() {
  recentStocks.value = []
  try {
    localStorage.removeItem(RECENT_KEY)
  } catch {
    /* ignore */
  }
}

function selectRecent(stock: RecentStock) {
  code.value = stock.code
  category.value = stock.category
}

onMounted(async () => {
  loadRecentStocks()
  await store.loadStrategies().catch((e) => {
    store.error = `加载策略列表失败：${e instanceof Error ? e.message : e}`
  })

  // 从 URL query 读取寻优页传来的 strategy + params（跳转自动填充）
  const qStrategy = route.query.strategy as string | undefined
  const qParams = route.query.params as string | undefined
  if (qStrategy) {
    strategy.value = qStrategy
    // 等待 StrategyPicker 的 watch(selectedSchema) 触发完默认值重置后，
    // 再用 query 的 params 覆盖，避免被 watch 重置掉
    await nextTick()
  }
  if (qParams) {
    try {
      params.value = JSON.parse(qParams) as Record<string, number | string | boolean>
    } catch {
      // query 参数解析失败，忽略
    }
  }

  // 从 URL query 回填标的代码 / 周期 / 日期范围（寻优页「查看」跳转带来）。
  // 各字段独立 if 守卫：老书签（只有 strategy/params）仍保持默认值，向后兼容。
  const qSymbol = route.query.symbol as string | undefined
  const qStartDate = route.query.startDate as string | undefined
  const qEndDate = route.query.endDate as string | undefined
  const qCategory = route.query.category as Category | undefined
  if (qSymbol) code.value = qSymbol
  if (qStartDate) startDate.value = qStartDate
  if (qEndDate) endDate.value = qEndDate
  if (qCategory) category.value = qCategory

  // V217: 恢复上次批量验证结果（如有）
  restoreBatchVerifyPersist()
})

// 取行情 + 回测 串联（点击「开始回测」触发）
async function onRun() {
  store.error = ''
  // 1. 先取行情（SymbolPicker.loadBars 会校验并填充 store.ohlcv）
  const ok = await symbolPicker.value?.loadBars()
  if (!ok) return // 校验/取数失败，错误已在 store.error
  // 记录最近浏览
  saveRecentStock(code.value, category.value)
  // 2. 再回测
  await store.run({
    strategy: strategy.value,
    params: params.value,
    cash: cash.value,
    commission: commission.value,
    slippage: slippage.value,
    execution: execution.value,
    robustness_segments: checkRobustness.value ? robustnessSegmentCount.value : null,
    out_of_sample: checkOutOfSample.value,
    use_walk_forward: checkWalkForward.value,
    step_ratio: 0.1,
    oos_train_ratio: oosTrainRatio.value,
  })
  // 3. 如果选择了缠论策略，运行缠论分析
  if (strategy.value === 'chanlun' && store.ohlcv.length > 0) {
    await runChanlunAnalysis()
  }
}

function applyChanlunLevel(level: 'bi' | 'xd', data: any) {
  if (level === 'xd' && data?.levels?.xd) {
    const xdLevel = data.levels.xd
    chanlunBis.value = xdLevel.bis ?? []
    chanlunXds.value = []
    chanlunZsds.value = xdLevel.zsds ?? []
    chanlunQsds.value = xdLevel.qsds ?? []
    chanlunZss.value = xdLevel.zss ?? []
    chanlunMmds.value = xdLevel.mmds ?? []
    chanlunBcs.value = xdLevel.bcs ?? []
    return
  }

  chanlunBis.value = data?.bis ?? []
  chanlunXds.value = data?.xds ?? []
  chanlunZsds.value = data?.zsds ?? []
  chanlunQsds.value = data?.qsds ?? []
  chanlunZss.value = data?.zss ?? []
  chanlunMmds.value = data?.mmds ?? []
  chanlunBcs.value = data?.bcs ?? []
}

function onChanlunLevelChange() {
  if (chanlunRaw.value) {
    applyChanlunLevel(chanlunLevel.value, chanlunRaw.value)
  }
}

// 缠论分析
// V722: chanlun strategy chart full-history backfill.
// store.ohlcv is the backtest window (SymbolPicker); loading earlier bars
// prepends real history and re-runs chanlun analysis over the new window.
const {
  loading: earlierLoading,
  canLoad: earlierCanLoad,
  error: earlierError,
  fetchEarlier,
  resetToLatest: resetEarlier,
} = useEarlierBars({
  code: () => code.value,
  category: () => category.value,
  earliest: () => (store.ohlcv.length ? store.ohlcv[0].datetime.slice(0, 10) : ''),
  detectMarket: (c) => detectMarket(c),
})

async function loadEarlierForChanlun() {
  const earlier = await fetchEarlier()
  if (earlier.length) {
    store.setOhlcv([...earlier, ...store.ohlcv], store.barsSource + ' +earlier')
    await runChanlunAnalysis()
  }
}

async function backToLatestChanlun() {
  resetEarlier()
  await symbolPicker.value?.loadBars()
  await runChanlunAnalysis()
}

async function runChanlunAnalysis() {
  chanlunLoading.value = true
  chanlunBis.value = []
  chanlunXds.value = []
  chanlunZss.value = []
  chanlunMmds.value = []
  try {
    const market = detectMarket(code.value)
    const categoryMap: Record<string, string> = {
      DAY: 'DAY',
      WEEK: 'WEEK',
      MIN_5: 'MIN_5',
      MIN_15: 'MIN_15',
      MIN_30: 'MIN_30',
      MIN_60: 'MIN_60',
    }
    const resp = await fetch('/api/v1/chanlun/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        market,
        code: code.value,
        category: categoryMap[category.value] ?? 'DAY',
        count: Math.min(store.ohlcv.length, CHANLUN_MAX_COUNT),
        start: 0,
        start_date: startDate.value || undefined,
        end_date: endDate.value || undefined,
      }),
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      const detail = err?.detail
      let msg: string
      if (Array.isArray(detail)) {
        // Pydantic validation error: detail is [{type, msg, loc}, ...]
        msg = detail.map((e: any) => e.msg ?? JSON.stringify(e)).join('; ')
      } else if (typeof detail === 'string') {
        msg = detail
      } else {
        msg = `HTTP ${resp.status}`
      }
      throw new Error(msg)
    }
    const data = await resp.json()
    chanlunRaw.value = data
    chanlunLevel.value = 'bi'
    applyChanlunLevel('bi', data)
    chanlunFxs.value = data.fractals ?? []
    chanlunMacd.value = data.macd && data.macd.dif?.length ? data.macd : null
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    chanlunError.value = msg
    console.error('缠论分析失败:', e)
  } finally {
    chanlunLoading.value = false
  }
}

// ── 保存策略（把当前结果 + 配置 + 上下文存进策略库）──────────────────────────
const showSaveForm = ref(false)
const saving = ref(false)
const saveName = ref('')
const saveTags = ref('')
const saveNotes = ref('')
const saveMsg = ref('') // 保存后提示（成功/失败）

const strategyLabel = computed(
  () => store.strategies.find((s) => s.name === strategy.value)?.label ?? strategy.value,
)

// 评级：基于完整 Performance，6 维度评分 + 一票否决。
// total_return 不直接计入评分（只通过卡玛/夏普间接体现），
// 体现「哪怕近期收益率高，长期风险大也该低评」的产品诉求。
const grade = computed(() => (store.result ? gradePerformance(store.result.performance) : null))

// 操作建议
const tradingAdvice = computed(() => {
  if (!store.result) return null
  const perf = store.result.performance
  const trades = store.result.trades
  const executed = trades.filter((t) => !t.rejected && t.pnl !== 0)

  if (executed.length === 0) {
    return { text: '暂无成交记录，无法给出操作建议。', color: '#94a3b8', details: [] }
  }

  const wins = executed.filter((t) => t.pnl > 0)
  const losses = executed.filter((t) => t.pnl < 0)
  const winRate = wins.length / executed.length
  const totalPnl = executed.reduce((s, t) => s + t.pnl, 0)
  const avgLoss =
    losses.length > 0 ? Math.abs(losses.reduce((s, t) => s + t.pnl, 0)) / losses.length : 0
  const profitFactor = avgLoss > 0 ? wins.reduce((s, t) => s + t.pnl, 0) / avgLoss : Infinity
  const maxDrawdown = perf.max_drawdown ?? 0

  // 判断建议
  if (winRate >= 0.6 && profitFactor >= 1.5 && totalPnl > 0 && maxDrawdown < 0.2) {
    return {
      text: '策略表现优秀：胜率高、盈亏比合理、回撤可控。建议：可加大仓位或延长持有周期。',
      color: '#22c55e',
      details: [
        { label: '胜率', value: `${(winRate * 100).toFixed(1)}%`, color: '#22c55e' },
        {
          label: '盈亏比',
          value: profitFactor === Infinity ? '∞' : profitFactor.toFixed(2),
          color: '#22c55e',
        },
        {
          label: '总收益',
          value: `${totalPnl > 0 ? '+' : ''}${totalPnl.toFixed(0)}元`,
          color: '#22c55e',
        },
        {
          label: '最大回撤',
          value: `${(maxDrawdown * 100).toFixed(1)}%`,
          color: maxDrawdown < 0.15 ? '#22c55e' : '#fbbf24',
        },
      ],
    }
  } else if (winRate >= 0.5 && totalPnl > 0) {
    return {
      text: '策略基本有效：胜率尚可且整体盈利。建议：优化止损参数减少大额亏损，或调整仓位控制风险。',
      color: '#eab308',
      details: [
        {
          label: '胜率',
          value: `${(winRate * 100).toFixed(1)}%`,
          color: winRate >= 0.5 ? '#22c55e' : '#ef4444',
        },
        {
          label: '总收益',
          value: `${totalPnl > 0 ? '+' : ''}${totalPnl.toFixed(0)}元`,
          color: '#eab308',
        },
        {
          label: '最大回撤',
          value: `${(maxDrawdown * 100).toFixed(1)}%`,
          color: maxDrawdown < 0.2 ? '#fbbf24' : '#ef4444',
        },
      ],
    }
  } else if (totalPnl < 0) {
    return {
      text: '策略当前亏损：建议检查市场环境是否适合该策略，或调整参数重新回测。考虑暂停实盘交易。',
      color: '#ef4444',
      details: [
        { label: '总收益', value: `${totalPnl.toFixed(0)}元`, color: '#ef4444' },
        { label: '胜率', value: `${(winRate * 100).toFixed(1)}%`, color: '#ef4444' },
        { label: '交易次数', value: `${executed.length}笔`, color: '#94a3b8' },
      ],
    }
  } else {
    return {
      text: '样本不足，建议增加回测周期或扩大交易标的后再评估。',
      color: '#94a3b8',
      details: [{ label: '交易次数', value: `${executed.length}笔`, color: '#94a3b8' }],
    }
  }
})

// 当前股票完整代码（市场:6位），从 SymbolPicker 同步来的 code 是纯数字，
// 需要带上市场前缀。复用 market.ts 的 detectMarket（与 SymbolPicker /
// StocksPicker 同一套规则），避免分叉导致 ETF/基金（5 开头）等被错判市场。
function fullSymbol(code6: string): string {
  return `${detectMarket(code6)}:${code6}`
}

// 判断是否为缠论策略
const isChanlunStrategy = computed(() => {
  return strategy.value === 'chanlun' || strategy.value === 'changying_chanlun'
})

// 计算 bars（用于 ChanlunChart）
// 缠论图表必须与后端分析窗口对齐：分析接口最多取最近 CHANLUN_MAX_COUNT 根，
// 若把全部回测 K 线（可能远超 800 根）传给图表，叠加层（笔/线段/中枢/分型/
// 买卖点/背驰）会全部挤在右侧少数 K 线上，左侧一片空白，视觉上乱七八糟。
// 仅对真正运行缠论分析并填充结构数据的 'chanlun' 策略截断窗口；
// changying_chanlun 不做缠论结构图（onRun 只对 'chanlun' 调 runChanlunAnalysis），
// 保持全量 K 线由 KlineChart 展示，避免丢失回测区间。
// V722: 后端 /chanlun/analyze count 上限已放宽到 8000（fetch_paged_bars 分页），
// 窗口跟随已加载 K 线；前端上限 2000（>2000 叠加层过密且分析耗时显著上升）。
const CHANLUN_MAX_COUNT = 2000
const bars = computed(() => {
  if (strategy.value !== 'chanlun') return store.ohlcv
  return store.ohlcv.length > CHANLUN_MAX_COUNT
    ? store.ohlcv.slice(store.ohlcv.length - CHANLUN_MAX_COUNT)
    : store.ohlcv
})

// ── 回测报告导出（一键复制 Markdown 摘要） ────────────────────────────────
// 把绩效 + 信号准确度 + 稳健性 + 可信度汇总成一份可粘贴/存档的文本报告。
const copyMsg = ref('')
function buildReportText(): string {
  const r = store.result
  if (!r) return ''
  const pct = (v: number | null | undefined) =>
    v === undefined || v === null || !Number.isFinite(v) ? '-' : (v * 100).toFixed(2) + '%'
  const lines: string[] = []
  lines.push('# easy-tdx 回测报告')
  lines.push('')
  lines.push('- 策略：' + (strategyLabel.value || strategy.value))
  lines.push('- 标的：' + fullSymbol(code.value) + ' · ' + category.value)
  lines.push('- 区间：' + startDate.value + ' ~ ' + endDate.value)
  lines.push('- 初始资金：' + cash.value.toLocaleString())
  lines.push('')
  lines.push('## 绩效')
  const perf = r.performance
  lines.push('- 总收益：' + pct(perf.total_return) + ' · 年化：' + pct(perf.annual_return))
  lines.push('- 夏普：' + (perf.sharpe ?? 0).toFixed(2) + ' · 最大回撤：' + pct(perf.max_drawdown))
  lines.push('- 胜率：' + pct(perf.win_rate) + ' · 交易数：' + (perf.total_trades ?? 0))
  lines.push('')
  if (r.model_trust) {
    lines.push('## 模型可信度（历史回测验证）')
    lines.push(
      '- 综合评分：' + Math.round(r.model_trust.score) + '/100 · ' + r.model_trust.grade + '可信',
    )
    lines.push('- 结论：' + (r.model_trust.verdict || ''))
    lines.push('')
  }
  if (r.signal_accuracy) {
    lines.push('## 信号准确度（vs 随机基准）')
    lines.push('- ' + (r.signal_accuracy.verdict || ''))
    const h5 = r.signal_accuracy.buy?.horizons?.['5']
    if (h5 && h5.count > 0) {
      lines.push(
        '- 5根命中率：' +
          pct(h5.hit_rate) +
          ' · 随机基准：' +
          pct(h5.baseline_hit_rate) +
          ' · 超额：' +
          (h5.excess_hit_rate >= 0 ? '+' : '') +
          pct(h5.excess_hit_rate),
      )
    }
    lines.push('')
  }
  if (r.segment_robustness) {
    lines.push('## 分段稳健性（过拟合检查）')
    lines.push('- ' + (r.segment_robustness.verdict || ''))
    lines.push('')
  }
  if (r.out_of_sample) {
    lines.push('## 样本外验证（训练段 vs 未见过数据）')
    lines.push('- ' + (r.out_of_sample.verdict || ''))
    lines.push(
      '- 训练段收益：' +
        pct(r.out_of_sample.train?.total_return) +
        ' · 样本外收益：' +
        pct(r.out_of_sample.test?.total_return),
    )
    lines.push(
      '- 样本外5根命中率：' +
        pct(r.out_of_sample.test?.hit_rate) +
        ' · 超额：' +
        (r.out_of_sample.test?.excess_hit_rate != null
          ? (r.out_of_sample.test.excess_hit_rate >= 0 ? '+' : '') +
            pct(r.out_of_sample.test.excess_hit_rate)
          : '-'),
    )
    lines.push('')
  }
  // V287: Walk-Forward 滚动窗口验证段
  const wfr = (r as any).walk_forward
  if (wfr) {
    lines.push('## Walk-Forward 滚动窗口验证（防过拟合）')
    lines.push('- ' + (wfr.verdict || ''))
    lines.push(
      '- 窗口数：' +
        (wfr.windows ?? '-') +
        ' · 训练段均值：' +
        pct(wfr.train_mean) +
        ' · 样本外均值：' +
        pct(wfr.test_mean),
    )
    lines.push('')
  }
  lines.push('---')
  lines.push('生成时间：' + new Date().toLocaleString('zh-CN'))
  return lines.join('\n')
}
async function copyReport() {
  const text = buildReportText()
  try {
    await navigator.clipboard.writeText(text)
    copyMsg.value = '✓ 已复制报告'
  } catch {
    copyMsg.value = '复制失败（浏览器权限），已弹出报告'
    window.alert(text)
  }
  setTimeout(() => {
    copyMsg.value = ''
  }, 2500)
}
// V153: 机器可读 JSON 报告导出（Agent/脚本/存档友好）
const jsonCopyMsg = ref('')
async function copyJsonReport() {
  if (!store.result) return
  const json = JSON.stringify(store.result, null, 2)
  try {
    await navigator.clipboard.writeText(json)
    jsonCopyMsg.value = '✓ 已复制 JSON 报告'
  } catch {
    jsonCopyMsg.value = '复制失败（浏览器权限）'
  }
  setTimeout(() => {
    jsonCopyMsg.value = ''
  }, 2500)
}
// V261: 交易明细导出 CSV（成交记录，帮助核对模型触发的买卖点）
const tradesCsvMsg = ref('')
function tradeCsvEscape(v: string): string {
  return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v
}
function exportTradesCsv() {
  const r = store.result
  const trades = r?.trades as Array<Record<string, unknown>> | undefined
  if (!r || !Array.isArray(trades) || trades.length === 0) {
    tradesCsvMsg.value = '没有可导出的成交记录'
    setTimeout(() => {
      tradesCsvMsg.value = ''
    }, 2500)
    return
  }
  const header = [
    '时间',
    '方向',
    '数量',
    '价格',
    '手续费',
    '滑点',
    '已实现盈亏',
    '成本基数',
    '是否拒绝',
  ]
  const lines = [header.join(',')]
  trades.forEach((t) => {
    if (t.rejected) return
    lines.push(
      [
        String(t.datetime ?? ''),
        tradeCsvEscape(String(t.direction ?? '')),
        String(t.size ?? ''),
        String(t.price ?? ''),
        String(t.commission ?? ''),
        String(t.slippage ?? ''),
        String(t.pnl ?? ''),
        String(t.cost_basis ?? ''),
        String(t.rejected ?? false),
      ].join(','),
    )
  })
  const csv = '\uFEFF' + lines.join('\n')
  try {
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'easy_tdx_trades_' + new Date().toISOString().slice(0, 10) + '.csv'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    tradesCsvMsg.value = '✓ 已导出交易明细 CSV'
  } catch {
    tradesCsvMsg.value = '导出失败（浏览器权限）'
  }
  setTimeout(() => {
    tradesCsvMsg.value = ''
  }, 2500)
}

// V137: 批量验证自选股（对全局自选股用当前策略各跑一次回测，按可信度排名）
interface BatchVerifyRow {
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
  // V178: 该股样本外验证结论（训练/持有切分）
  oos_degraded: boolean | null
  oos_verdict: string
  // V313: 该股 Walk-Forward 滚动验证结论（逐窗口回测聚合）
  wf_degraded: boolean | null
  wf_verdict: string
}
const batchRows = ref<BatchVerifyRow[]>([])
const batchLoading = ref(false)
const batchMsg = ref('')
// V217: 批量验证结果持久化（localStorage 记住上次结果，重进页面自动恢复）
const BATCH_VERIFY_KEY = 'easy_tdx_batch_verify_last'
const lastBatchVerifyAt = ref('')
function saveBatchVerifyPersist() {
  if (!batchRows.value.length) return
  try {
    localStorage.setItem(
      BATCH_VERIFY_KEY,
      JSON.stringify({
        rows: batchRows.value,
        strategy: strategy.value,
        strategy_label: strategyLabel.value || strategy.value,
        at: new Date().toISOString(),
      }),
    )
  } catch {
    /* localStorage 不可用忽略 */
  }
}
function restoreBatchVerifyPersist() {
  try {
    const raw = localStorage.getItem(BATCH_VERIFY_KEY)
    if (!raw) return
    const data = JSON.parse(raw)
    if (Array.isArray(data.rows) && data.rows.length) {
      batchRows.value = data.rows
      lastBatchVerifyAt.value = data.at || ''
      batchMsg.value = '已恢复上次批量验证（' + (data.strategy_label || '') + '）'
    }
  } catch {
    /* 解析失败忽略 */
  }
}
// V149: 批量验证结果排序方式（收益 / 可信度）
const batchSort = ref<'return' | 'trust'>('trust')
// V192: 仅看样本外稳健（过滤掉 oos_degraded=true 的候选股）
const batchOnlyRobust = ref(false)
// V318: 仅看滚验稳健（过滤掉 wf_degraded=true 的候选股）
const batchOnlyWfRobust = ref(false)
const sortedBatchRows = computed(() => {
  let base = batchRows.value
  if (batchOnlyRobust.value) base = base.filter((r) => r.oos_degraded === false)
  if (batchOnlyWfRobust.value) base = base.filter((r) => r.wf_degraded === false)
  const filtered = base
  if (!filtered.length || batchSort.value === 'trust') return filtered
  return [...filtered].sort((a, b) => (b.total_return ?? -Infinity) - (a.total_return ?? -Infinity))
})

async function runBatchVerifyWatchlist() {
  if (batchLoading.value) return
  let raw: any[] = []
  try {
    raw = JSON.parse(localStorage.getItem('easy_tdx_global_watchlist') ?? '[]')
  } catch {
    raw = []
  }
  const watch = raw.filter((w) => w && w.code && w.market).slice(0, 12)
  if (watch.length === 0) {
    batchMsg.value = '自选股为空：请先在缠论分析页「加入自选股」'
    setTimeout(() => {
      batchMsg.value = ''
    }, 3500)
    return
  }
  batchLoading.value = true
  batchMsg.value = ''
  const rows: BatchVerifyRow[] = []
  try {
    for (const w of watch) {
      try {
        const bars = await fetchBars(
          w.market,
          w.code,
          category.value as Category,
          undefined,
          undefined,
          500,
        )
        if (bars.length < 30) continue
        const result = await runBacktest({
          strategy: strategy.value,
          params: params.value,
          cash: cash.value,
          commission: commission.value,
          slippage: slippage.value,
          execution: execution.value,
          out_of_sample: true,
          oos_train_ratio: 0.7,
          use_walk_forward: true,
          step_ratio: 0.1,
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
          wf_degraded: (result as any).walk_forward?.degraded ?? null,
          wf_verdict: (result as any).walk_forward?.verdict ?? '',
        })
      } catch {
        /* 单只失败跳过 */
      }
    }
    rows.sort((a, b) => (b.trust_score ?? -1) - (a.trust_score ?? -1))
    batchRows.value = rows
    lastBatchVerifyAt.value = new Date().toISOString()
    saveBatchVerifyPersist()
  } catch (e) {
    batchMsg.value = '批量验证失败：' + formatError(e)
  } finally {
    batchLoading.value = false
  }
}

function viewBatchStockV137(r: BatchVerifyRow) {
  code.value = r.code
  category.value = 'DAY'
  void onRun()
}
function batchPctV137(v: number | null | undefined): string {
  return v === null || v === undefined || !Number.isFinite(v) ? '-' : (v * 100).toFixed(1) + '%'
}
function batchTrustV137(r: BatchVerifyRow): string {
  if (r.trust_score === null || r.trust_score === undefined) return '-'
  return Math.round(r.trust_score) + ' ' + (r.trust_grade ?? '')
}
// V178: 样本外列辅助——显示泛化/衰减结论
function batchOosLabel(r: BatchVerifyRow): string {
  if (r.oos_degraded === null || r.oos_degraded === undefined) return '-'
  return r.oos_degraded ? '⚠衰减' : '✅泛化'
}
function batchOosCls(r: BatchVerifyRow): string {
  if (r.oos_degraded === null || r.oos_degraded === undefined) return ''
  return r.oos_degraded ? 'neg' : 'pos'
}
function batchOosTitle(r: BatchVerifyRow): string {
  return (
    r.oos_verdict || (r.oos_degraded === null || r.oos_degraded === undefined ? '' : '样本外验证')
  )
}
// V139: 批量验证排名导出（Markdown 复制）
const batchCopyMsg = ref('')
function copyBatchRanking() {
  if (batchRows.value.length === 0) return
  const lines: string[] = []
  lines.push('# easy-tdx 批量验证自选股（' + (strategyLabel.value || strategy.value) + '）')
  lines.push('')
  lines.push('| 排名 | 标的 | 总收益 | 胜率 | 5根命中率 | 超额命中率 | 可信度 | 样本外 | 交易数 |')
  lines.push('| --- | --- | --- | --- | --- | --- | --- | --- | --- |')
  batchRows.value.forEach((r, i) => {
    lines.push(
      '| ' +
        (i + 1) +
        ' | ' +
        r.symbol +
        ' | ' +
        batchPctV137(r.total_return) +
        ' | ' +
        batchPctV137(r.win_rate) +
        ' | ' +
        batchPctV137(r.hit_rate) +
        ' | ' +
        batchPctV137(r.excess_hit_rate) +
        ' | ' +
        batchTrustV137(r) +
        ' | ' +
        batchOosLabel(r) +
        ' | ' +
        (r.trades ?? '-') +
        ' |',
    )
  })
  lines.push('')
  lines.push(
    '方法：对全局自选股（最多 12 只）用当前策略与参数独立回测（最近 500 根日线），按模型可信度（V101）降序排名。',
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
    batchCopyMsg.value = '✓ 已复制批量验证排名'
    setTimeout(() => {
      batchCopyMsg.value = ''
    }, 2500)
  }
  void doCopy()
}
// V157: 批量验证结果 JSON 导出（机器可读，Agent/脚本友好，与 V153 对齐）
const batchJsonCopyMsg = ref('')
async function copyBatchJson() {
  if (batchRows.value.length === 0) return
  const payload = {
    strategy: strategy.value,
    strategy_label: strategyLabel.value,
    params: params.value,
    generated_at: new Date().toISOString(),
    rows: batchRows.value.map((r, i) => ({ rank: i + 1, ...r })),
  }
  const json = JSON.stringify(payload, null, 2)
  try {
    await navigator.clipboard.writeText(json)
    batchJsonCopyMsg.value = '✓ 已复制批量验证 JSON'
  } catch {
    batchJsonCopyMsg.value = '复制失败（浏览器权限）'
  }
  setTimeout(() => {
    batchJsonCopyMsg.value = ''
  }, 2500)
}
// V253: 批量验证结果导出 CSV（Excel 友好）
const batchCsvMsg = ref('')
function csvEscape(v: string): string {
  return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v
}
function exportBatchCsv() {
  if (batchRows.value.length === 0) return
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
  sortedBatchRows.value.forEach((r, i) => {
    const row = [
      i + 1,
      csvEscape(r.symbol),
      batchPctV137(r.total_return),
      batchPctV137(r.win_rate),
      batchPctV137(r.hit_rate),
      batchPctV137(r.excess_hit_rate),
      csvEscape(batchTrustV137(r)),
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
    a.download = 'easy_tdx_batch_verify_' + new Date().toISOString().slice(0, 10) + '.csv'
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
// V141: 把批量验证选出的股票保存为组合策略（kind=portfolio，可在策略库载入后组合页复跑）
const batchSaveMsg = ref('')
const batchSaving = ref(false)
async function saveBatchAsPortfolio() {
  if (batchRows.value.length === 0 || batchSaving.value) return
  batchSaving.value = true
  batchSaveMsg.value = ''
  try {
    // V203: 保存遵循「仅看样本外稳健」过滤——开启时只把筛选视图里的 ✅泛化 标的入库
    const visible = batchOnlyRobust.value
      ? batchRows.value.filter((r) => r.oos_degraded === false)
      : batchRows.value
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
    // V190: 样本外聚合（逐只开启 out_of_sample 后统计衰减比例）
    const oosKnown = visible.filter((r) => r.oos_degraded !== null && r.oos_degraded !== undefined)
    const oosDegradedN = oosKnown.filter((r) => r.oos_degraded === true).length
    const oosRatio = oosKnown.length ? oosDegradedN / oosKnown.length : null
    const oosVerdict = oosKnown.length
      ? oosRatio! < 0.5
        ? '✅ ' + (oosKnown.length - oosDegradedN) + '/' + oosKnown.length + ' 只样本外稳健'
        : '⚠ ' + oosDegradedN + '/' + oosKnown.length + ' 只样本外衰减'
      : ''
    await saveStrategy({
      name: (strategyLabel.value || strategy.value) + ' · 批量验证' + stocks.length + '只',
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
        source: 'batch-verify-backtest',
        saved_at: new Date().toISOString().slice(0, 10),
      },
      tags: ['批量验证'],
      notes: '由回测页批量验证自选股（按模型可信度排名）生成，可在组合回测页载入复跑。',
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
function openSaveForm() {
  saveName.value = `${strategyLabel.value} · ${code.value}`
  saveTags.value = ''
  saveNotes.value = ''
  saveMsg.value = ''
  showSaveForm.value = true
}

async function onSave() {
  if (!store.result || !saveName.value.trim()) return
  saving.value = true
  saveMsg.value = ''
  try {
    await saveStrategy({
      name: saveName.value.trim(),
      kind: 'single',
      strategy: strategy.value,
      strategy_label: strategyLabel.value,
      params: params.value,
      context: {
        symbol: fullSymbol(code.value),
        category: category.value,
        start_date: startDate.value,
        end_date: endDate.value,
      },
      trade_config: {
        cash: cash.value,
        commission: commission.value,
        min_commission: 5,
        stamp_tax: 0.001,
        slippage: slippage.value,
        execution: execution.value,
      },
      snapshot: {
        total_return: store.result.performance.total_return,
        annual_return: store.result.performance.annual_return,
        max_drawdown: store.result.performance.max_drawdown,
        sharpe: store.result.performance.sharpe,
        win_rate: store.result.performance.win_rate,
        trades_count: store.result.performance.total_trades,
        // V100: 持久化历史回测验证的准确度/稳健性结论，策略库按「验证过准不准」比较
        accuracy: {
          hit_rate: store.result.signal_accuracy?.buy?.horizons?.['5']?.hit_rate ?? null,
          excess_hit_rate:
            store.result.signal_accuracy?.buy?.horizons?.['5']?.excess_hit_rate ?? null,
          verdict: store.result.signal_accuracy?.verdict ?? '',
        },
        robustness: {
          overfit_likely: store.result.segment_robustness?.overfit_likely ?? false,
          verdict: store.result.segment_robustness?.verdict ?? '',
        },
        // V122: 模型可信度（V101）与样本外验证（V105）结论一并入快照
        trust: {
          score: store.result.model_trust?.score ?? null,
          grade: store.result.model_trust?.grade ?? '',
          verdict: store.result.model_trust?.verdict ?? '',
        },
        out_of_sample: {
          degraded: store.result.out_of_sample?.degraded ?? false,
          verdict: store.result.out_of_sample?.verdict ?? '',
          train_return: store.result.out_of_sample?.train?.total_return ?? null,
          test_return: store.result.out_of_sample?.test?.total_return ?? null,
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
  <div class="backtest-view">
    <!-- 左栏：配置 -->
    <aside class="config-panel">
      <section class="panel-section">
        <h3>行情数据</h3>
        <SymbolPicker
          ref="symbolPicker"
          v-model:code="code"
          v-model:category="category"
          v-model:start-date="startDate"
          v-model:end-date="endDate"
        />
      </section>

      <section class="panel-section">
        <h3>策略</h3>
        <StrategyPicker
          v-if="store.strategies.length"
          :strategies="store.strategies"
          v-model:strategy="strategy"
          v-model:params="params"
        />
        <p v-else class="loading-text">加载策略中…</p>
      </section>

      <!-- 最近浏览股票 -->
      <section v-if="recentStocks.length > 0" class="panel-section recent-section">
        <div class="recent-header">
          <h3>最近浏览</h3>
          <button class="ghost small" @click="clearRecentStocks">清空</button>
        </div>
        <div class="recent-list">
          <div
            v-for="s in recentStocks"
            :key="s.code + s.timestamp"
            class="recent-item"
            :class="{ active: s.code === code && s.category === category }"
            @click="selectRecent(s)"
          >
            <span class="recent-symbol">{{ s.market }}{{ s.code }}</span>
            <span class="recent-cat">{{ s.category }}</span>
          </div>
        </div>
      </section>

      <section class="panel-section">
        <h3>资金与成本</h3>
        <div class="field">
          <label>初始资金</label>
          <input v-model.number="cash" type="number" min="1000" step="10000" />
        </div>
        <div class="row">
          <div class="field">
            <label>佣金率</label>
            <input v-model.number="commission" type="number" min="0" step="0.0001" />
          </div>
          <div class="field">
            <label>滑点</label>
            <input v-model.number="slippage" type="number" min="0" step="0.001" />
          </div>
        </div>
        <div class="field">
          <label>成交价</label>
          <select v-model="execution">
            <option v-for="e in EXECUTIONS" :key="e.value" :value="e.value">{{ e.label }}</option>
          </select>
        </div>
        <div class="field">
          <label>
            <input type="checkbox" v-model="checkRobustness" />
            分段稳健性检查（过拟合验证）
          </label>
          <select v-if="checkRobustness" v-model.number="robustnessSegmentCount" class="seg-count">
            <option :value="2">2 段</option>
            <option :value="3">3 段</option>
            <option :value="4">4 段</option>
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
          <label title="V287: 逐窗口回测聚合，评估参数在未见数据上的稳定性/过拟合风险">
            <input type="checkbox" v-model="checkWalkForward" />
            Walk-Forward 滚动验证（防过拟合）
          </label>
        </div>
      </section>

      <button class="primary run-btn" :disabled="store.running" @click="onRun">
        {{ store.running ? '取行情+回测中…' : '开始回测' }}
      </button>
    </aside>

    <!-- 右栏：报告 -->
    <main class="report-panel">
      <div v-if="store.error" class="error-banner">⚠ {{ store.error }}</div>

      <div v-if="!store.result && !store.running && !store.error" class="placeholder">
        <p>输入代码、配置策略后点击「开始回测」（自动取行情）</p>
      </div>

      <div v-if="store.result" class="report-content">
        <div class="result-toolbar">
          <button class="ghost" @click="openSaveForm">💾 保存策略</button>
          <button class="ghost" @click="copyReport">📋 复制报告</button>
          <button class="ghost" @click="copyJsonReport">⚙ 复制 JSON</button>
          <button class="ghost" @click="exportTradesCsv">📊 交易明细 CSV</button>
          <button class="ghost" :disabled="batchLoading" @click="runBatchVerifyWatchlist">
            {{ batchLoading ? '批量验证自选股中…' : '🗳️ 批量验证自选股' }}
          </button>
          <span v-if="copyMsg" class="save-msg">{{ copyMsg }}</span>
          <span v-if="jsonCopyMsg" class="save-msg">{{ jsonCopyMsg }}</span>
          <span v-if="saveMsg" class="save-msg">{{ saveMsg }}</span>
          <span v-if="batchMsg" class="save-msg">{{ batchMsg }}</span>
        </div>

        <!-- V106 验证总结（可信度 + 准确度 + 稳健性 + 样本外 一览） -->
        <section v-if="store.result" class="report-section">
          <ValidationSummaryPanel :result="store.result" />
        </section>

        <section class="report-section">
          <h3>
            K线 + 买卖点
            <span v-if="strategy === 'chanlun'" class="chanlun-badge">缠论</span>
          </h3>
          <div v-if="strategy === 'chanlun'" class="chanlun-level-switch">
            <label>分析级别</label>
            <select v-model="chanlunLevel" @change="onChanlunLevelChange">
              <option value="bi">笔级别</option>
              <option value="xd">线段级别</option>
            </select>
          </div>
          <!-- V722: 全历史回溯 -->
          <div v-if="isChanlunStrategy" class="chanlun-history-bar">
            <button class="ghost" :disabled="!earlierCanLoad" @click="loadEarlierForChanlun">
              {{ earlierLoading ? '加载中…' : '加载更早 ⏮' }}
            </button>
            <button v-if="store.ohlcv.length > CHANLUN_MAX_COUNT" class="ghost" @click="backToLatestChanlun">
              回最新 ⏭
            </button>
            <span v-if="earlierError" class="chanlun-error-text">{{ earlierError }}</span>
          </div>
          <!-- 缠论策略：显示缠论结构图 -->
          <ChanlunChart
            v-if="isChanlunStrategy && !chanlunLoading && bars.length > 0"
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
            :frequency="category"
            compact
          />
          <!-- 缠论分析中 -->
          <div v-else-if="strategy === 'chanlun' && chanlunLoading" class="chanlun-loading">
            正在分析缠论结构…
          </div>
          <!-- 缠论分析失败 -->
          <div v-else-if="chanlunError" class="chanlun-error">
            ⚠ 缠论分析失败：{{ chanlunError }}
          </div>
          <!-- 普通策略：显示普通K线图 -->
          <KlineChart v-else :bars="bars" :trades="store.result.trades" />
        </section>

        <section class="report-section">
          <h3>净值曲线与回撤</h3>
          <EquityChart :equity="store.result.equity_curve" />
        </section>

        <section v-if="store.result.model_trust" class="report-section trust-section">
          <h3>📊 模型可信度综合评分（历史回测验证结论）</h3>
          <ModelTrustPanel :report="store.result.model_trust" />
        </section>

        <section v-if="grade" class="report-section">
          <h3>评级</h3>
          <GradeDetails :result="grade" expanded />
        </section>

        <!-- 操作建议 -->
        <section v-if="store.result && tradingAdvice" class="report-section trading-advice">
          <h3>💡 操作建议</h3>
          <div class="advice-content" :style="{ borderColor: tradingAdvice.color }">
            <div class="advice-main" :style="{ color: tradingAdvice.color }">
              {{ tradingAdvice.text }}
            </div>
            <div v-if="tradingAdvice.details?.length" class="advice-details">
              <div v-for="(d, i) in tradingAdvice.details" :key="i" class="advice-detail-item">
                <span class="detail-label">{{ d.label }}:</span>
                <span class="detail-value" :style="{ color: d.color }">{{ d.value }}</span>
              </div>
            </div>
          </div>
        </section>

        <section class="report-section">
          <h3>绩效指标</h3>
          <MetricTable :perf="store.result.performance" />
        </section>

        <section v-if="store.result.signal_accuracy" class="report-section">
          <h3>🎯 模型准确度验证（信号命中率 vs 随机基准）</h3>
          <SignalAccuracyPanel :report="store.result.signal_accuracy" />
        </section>

        <section
          v-if="isChanlunStrategy && store.result.signal_accuracy?.chanlun_by_type"
          class="report-section"
        >
          <h3>📊 缠论买卖点类型准确度（按 1buy/2buy/3buy/... 分组验证）</h3>
          <ChanlunAccuracyPanel
            :by-type="store.result.signal_accuracy.chanlun_by_type"
            :ranking="store.result.signal_accuracy.chanlun_ranking"
            :summary="store.result.signal_accuracy.chanlun_summary"
          />
        </section>

        <section v-if="store.result.segment_robustness" class="report-section">
          <h3>🧱 分段稳健性检查（过拟合验证）</h3>
          <SegmentRobustnessPanel :report="store.result.segment_robustness" />
        </section>

        <section v-if="store.result.out_of_sample" class="report-section">
          <h3>🔬 样本外验证（训练段 vs 未见过数据）</h3>
          <OutOfSamplePanel :report="store.result.out_of_sample" />
        </section>

        <!-- V287: Walk-Forward 滚动窗口验证（勾选后显示） -->
        <section v-if="(store.result as any).walk_forward" class="report-section">
          <h3>🔁 Walk-Forward 滚动窗口验证（防过拟合）</h3>
          <WalkForwardPanel :report="(store.result as any).walk_forward" />
        </section>

        <section class="report-section">
          <h3>成交记录（{{ store.result.trades.length }} 笔）</h3>
          <TradeTable :trades="store.result.trades" :initial-cash="cash" />
        </section>
      </div>
      <!-- V137 批量验证自选股（对全局自选股跑当前策略，按可信度排名） -->
      <section v-if="batchRows.length" class="report-section">
        <div class="batch-panel-head">
          <h3>
            🗳️ 批量验证自选股（策略 {{ strategyLabel }}）
            <span v-if="lastBatchVerifyAt" class="batch-verify-at" :title="'上次验证时间'"
              >🕒 {{ new Date(lastBatchVerifyAt).toLocaleString() }}</span
            >
          </h3>
          <div class="batch-actions">
            <button
              class="ghost small"
              :class="{ active: batchSort === 'return' }"
              @click="batchSort = 'return'"
            >
              按收益
            </button>
            <button
              class="ghost small"
              :class="{ active: batchSort === 'trust' }"
              @click="batchSort = 'trust'"
            >
              按可信度
            </button>
            <button
              class="ghost small"
              :class="{ active: batchOnlyRobust }"
              :title="
                '仅保留样本外 ✅泛化 的候选股（当前 ' +
                batchRows.filter((r: BatchVerifyRow) => r.oos_degraded === false).length +
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
                batchRows.filter((r: BatchVerifyRow) => r.wf_degraded === false).length +
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
            <tr v-for="(r, i) in sortedBatchRows" :key="r.symbol">
              <td class="dim">{{ i + 1 }}</td>
              <td>{{ r.symbol }}</td>
              <td class="num" :class="(r.total_return ?? 0) >= 0 ? 'pos' : 'neg'">
                {{ batchPctV137(r.total_return) }}
              </td>
              <td class="num">{{ batchPctV137(r.win_rate) }}</td>
              <td class="num">{{ batchPctV137(r.hit_rate) }}</td>
              <td class="num" :class="(r.excess_hit_rate ?? 0) >= 0 ? 'pos' : 'neg'">
                {{ batchPctV137(r.excess_hit_rate) }}
              </td>
              <td
                class="num"
                :class="r.trust_grade === '高' ? 'pos' : r.trust_grade === '低' ? 'neg' : ''"
              >
                {{ batchTrustV137(r) }}
              </td>
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
              <td class="num">{{ r.trades ?? '-' }}</td>
              <td><button class="ghost small" @click="viewBatchStockV137(r)">查看该股</button></td>
            </tr>
          </tbody>
        </table>
        <p class="legend">
          对全局自选股（最多 12 只）用当前策略与参数各做一次独立回测（最近 500 根日线），按 V101
          模型可信度降序排名；点「查看该股」直接切换目标重新回测。
        </p>
      </section>
    </main>

    <!-- 保存策略对话框 -->
    <div v-if="showSaveForm" class="modal-overlay" @click.self="showSaveForm = false">
      <div class="modal">
        <h3>保存到策略库</h3>
        <p class="modal-desc">
          将当前策略 + 标的上下文 + 成绩快照存下，下次可在「策略库」载入或重跑。
        </p>
        <div class="field">
          <label>名称</label>
          <input v-model="saveName" type="text" placeholder="给这个策略起个名" />
        </div>
        <div class="field">
          <label>标签（逗号分隔，可选）</label>
          <input v-model="saveTags" type="text" placeholder="如：银行,长线观察" />
        </div>
        <div class="field">
          <label>备注（可选）</label>
          <textarea v-model="saveNotes" rows="2" placeholder="为什么觉得它好？"></textarea>
        </div>
        <div class="modal-summary">
          {{ strategyLabel }} · {{ code }} ·
          {{ store.result ? (store.result.performance.total_return * 100).toFixed(2) + '%' : '' }}
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
.backtest-view {
  display: flex;
  height: 100%;
}

/* 左栏配置面板 */
.config-panel {
  width: 320px;
  flex-shrink: 0;
  background: var(--bg-panel);
  border-right: 1px solid var(--border);
  padding: 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
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
  color: var(--text);
  margin-bottom: 12px;
}
.loading-text {
  color: var(--text-dim);
  font-size: 12px;
}
.run-btn {
  margin-top: auto;
  width: 100%;
  padding: 10px;
  font-size: 14px;
}

/* 右栏报告面板 */
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
.batch-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.batch-panel-head h3 {
  /* V217: 上次批量验证时间 */
  .batch-verify-at {
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
.batch-actions .ghost.active {
  background: rgba(96, 165, 250, 0.18);
  color: var(--accent);
  border-color: var(--accent);
}
.batch-actions .save-msg.err {
  color: var(--down);
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
.modal .field textarea {
  font-family: inherit;
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

/* 缠论徽章和加载状态 */
.chanlun-badge {
  display: inline-block;
  margin-left: 8px;
  padding: 1px 6px;
  font-size: 10px;
  font-weight: 500;
  color: #c878ff;
  background: rgba(200, 120, 255, 0.15);
  border: 1px solid rgba(200, 120, 255, 0.3);
  border-radius: 4px;
  vertical-align: middle;
}
.chanlun-level-switch {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0;
  font-size: 12px;
  color: var(--text-dim);
}
.chanlun-level-switch select {
  background: var(--bg-soft, #0f172a);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 12px;
}
.chanlun-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 400px;
  color: var(--text-dim);
  font-size: 13px;
}
.chanlun-error {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 400px;
  color: var(--up);
  font-size: 13px;
  text-align: center;
  padding: 20px;
}

/* 最近浏览股票 */
.recent-section {
  border-top: 1px solid var(--border);
  padding-top: 10px;
  margin-top: 4px;
}
.recent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.recent-header h3 {
  margin: 0;
}
.recent-header .ghost {
  font-size: 11px;
  padding: 2px 6px;
}
.recent-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-height: 160px;
  overflow-y: auto;
}
.recent-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  transition: background 0.1s;
}
.recent-item:hover {
  background: rgba(255, 255, 255, 0.06);
}
.recent-item.active {
  background: rgba(74, 158, 255, 0.12);
  border: 1px solid rgba(74, 158, 255, 0.3);
}
.recent-symbol {
  font-family: var(--font-mono);
  font-weight: 600;
  color: var(--text);
}
.recent-cat {
  font-size: 10px;
  color: var(--text-muted);
  background: rgba(255, 255, 255, 0.05);
  padding: 1px 4px;
  border-radius: 3px;
}

/* 操作建议 */
.trading-advice .advice-content {
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid;
  border-left: 3px solid;
  border-radius: 6px;
}

.trading-advice .advice-main {
  font-size: 13px;
  line-height: 1.6;
  margin-bottom: 8px;
}

.trading-advice .advice-details {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.trading-advice .advice-detail-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  padding: 4px 8px;
  background: rgba(255, 255, 255, 0.04);
  border-radius: 4px;
}

.trading-advice .detail-label {
  color: var(--text-muted);
}

.trading-advice .detail-value {
  font-weight: 600;
  font-family: var(--font-mono);
}
</style>
// BUILD_TEST_MARKER_12345
