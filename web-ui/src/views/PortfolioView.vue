<script setup lang="ts">
// 组合回测主页面：左配置（多标的 + 策略 + 日期）/ 右报告（组合净值 + 各标的对比）。

import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

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
}
const candRows = ref<CandRow[]>([])
const candLoading = ref(false)
const candMsg = ref('')
const candSort = ref<'return' | 'trust'>('trust')
const sortedCandRows = computed(() => {
  const rows = candRows.value
  if (!rows.length || candSort.value === 'trust') return rows
  return [...rows].sort((a, b) => (b.total_return ?? -Infinity) - (a.total_return ?? -Infinity))
})
async function runCandVerify() {
  if (candLoading.value) return
  let raw: any[] = []
  try { raw = JSON.parse(localStorage.getItem('easy_tdx_global_watchlist') ?? '[]') } catch { raw = [] }
  const watch = raw.filter((w) => w && w.code && w.market).slice(0, 12)
  if (watch.length === 0) {
    candMsg.value = '自选股为空：请先在缠论分析页「加入自选股」'
    setTimeout(() => { candMsg.value = '' }, 3500)
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
          ohlcv: bars,
        })
        const h5 = result.signal_accuracy?.buy?.horizons?.['5']
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
        })
      } catch { /* 单只失败跳过 */ }
    }
    rows.sort((a, b) => (b.trust_score ?? -1) - (a.trust_score ?? -1))
    candRows.value = rows
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
  lines.push('- 标的总数：' + p.total_stocks + ' · 总资金：' + p.total_cash.toLocaleString())
  lines.push('')
  if (r.portfolio_trust) {
    lines.push('## 组合可信度（V103）')
    lines.push('- 综合评分：' + Math.round(r.portfolio_trust.score) + '/100 · ' + r.portfolio_trust.grade + '可信')
    lines.push('- 结论：' + (r.portfolio_trust.verdict || ''))
    lines.push('')
  }
  if (r.accuracy_summary) {
    lines.push('## 组合准确度（V99）')
    lines.push('- ' + (r.accuracy_summary.verdict || ''))
    const pf = r.accuracy_summary.portfolio
    if (pf) {
      lines.push(
        '- 加权5根命中率：' + pct(pf.avg_hit_rate) + ' · 超额：' + pct(pf.avg_excess_hit_rate) +
        ' · 正收益标的：' + pf.positive_symbols + '/' + pf.symbols,
      )
    }
    lines.push('')
  }
  if (r.out_of_sample) {
    lines.push('## 组合样本外验证（V126）')
    lines.push('- ' + (r.out_of_sample.verdict || ''))
    lines.push('- 平均训练段：' + pct(r.out_of_sample.avg_train_return) + ' · 平均样本外：' + pct(r.out_of_sample.avg_test_return))
    lines.push('')
  }
  lines.push('---')
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
  setTimeout(() => { copyMsg.value = '' }, 2500)
}

const strategyLabel = computed(
  () => store.strategies.find((s) => s.name === strategy.value)?.label ?? strategy.value,
)

// 组合评级：从 combined_equity 重算夏普/卡玛/波动率等（组合级净值算不出胜率/利润因子），
// 用 5 维度评分。净值点数过少（< 60 个交易日）视为样本不足。
const grade = computed(() =>
  store.portfolioResult ? gradePortfolio(store.portfolioResult) : null,
)

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
          excess_hit_rate: store.portfolioResult.accuracy_summary?.portfolio?.avg_excess_hit_rate ?? null,
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
        <p class="hint">读全局自选股（最多 12 只），用当前策略逐只回测并按可信度排名，可一键加入组合标的。</p>
        <div class="cand-bar">
          <button class="ghost small" :disabled="candLoading || !store.strategies.length" @click="runCandVerify">
            {{ candLoading ? '批量验证中…' : '🧪 批量验证候选股' }}
          </button>
          <span v-if="candMsg" class="cand-msg">{{ candMsg }}</span>
        </div>
        <div v-if="candRows.length" class="cand-table-wrap">
          <div class="cand-head">
            <span>候选排名（{{ candRows.length }}）</span>
            <span class="cand-sort">
              <button class="ghost small" :class="{ active: candSort === 'return' }" @click="candSort = 'return'">按收益</button>
              <button class="ghost small" :class="{ active: candSort === 'trust' }" @click="candSort = 'trust'">按可信度</button>
              <button class="ghost small" @click="addAllCands">全部加入组合</button>
            </span>
          </div>
          <table class="cand-table">
            <thead>
              <tr><th>#</th><th>标的</th><th class="num">总收益</th><th class="num">5根命中率</th><th class="num">可信度</th><th></th></tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in sortedCandRows" :key="r.symbol">
                <td class="dim">{{ i + 1 }}</td>
                <td>{{ r.symbol }}</td>
                <td class="num" :class="(r.total_return ?? 0) >= 0 ? 'pos' : 'neg'">{{ candPct(r.total_return) }}</td>
                <td class="num">{{ candPct(r.hit_rate) }}</td>
                <td class="num" :class="r.trust_grade === '高' ? 'pos' : r.trust_grade === '低' ? 'neg' : ''">{{ candTrust(r) }}</td>
                <td><button class="ghost small" @click="addCandToPortfolio(r)">加入组合</button></td>
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
          <span v-if="copyMsg" class="save-msg">{{ copyMsg }}</span>
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
              <span class="value">{{ store.portfolioResult.total_performance.total_cash.toFixed(0) }}</span>
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
.cand-table th:first-child, .cand-table td:first-child { text-align: left; }
.cand-table td {
  padding: 4px 6px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  text-align: right;
  font-family: var(--font-mono);
}
.pos { color: var(--up); }
.neg { color: var(--down); }
.dim { color: var(--text-dim); }
</style>
