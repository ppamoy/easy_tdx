<script setup lang="ts">
// 长赢动态选股 + 缠论回测页面
// 功能：选择历史日期 → 长赢模型选股 → 缠论买卖点回测

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import ChanlunChart from '../components/ChanlunChart.vue'
import EquityChart from '../components/EquityChart.vue'
import { formatError } from '../api'
import type { Bar } from '../types'

// ── 状态变量 ────────────────────────────────────────────────────────────
const router = useRouter()
const market = ref<'SZ' | 'SH'>('SZ')
const selectDate = ref('')
const scanning = ref(false)
const scanProgress = ref(0)
const scanTotal = ref(0)
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
  latest_mmd: { type: string; date: string; price: number } | null
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
const chanlunLoading = ref(false)

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

/** 获取操作建议的详细解释 */
function getActionExplanation(stock: StockResult): string {
  const latest = stock.latest_mmd
  const rec = getRecommendation(stock)

  if (!latest) return '暂无缠论买卖点信号，建议持续观察'

  const daysSince = stock.days_since_signal ?? 0

  if (rec.action === 'buy') {
    if (daysSince <= 5) return `最近 ${daysSince} 天前出现${latest.type}信号，建议密切关注，可考虑分批建仓`
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
  } catch (e) {
    error.value = formatError(e)
  } finally {
    scanning.value = false
  }
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
  backtestResult.value = null

  // 获取K线数据
  try {
    const resp = await fetch(`/api/v1/bars?market=${stock.market}&code=${stock.code}&category=DAY&count=500&start=0`)
    
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

async function runChanlunAnalysis(stock: StockResult) {
  chanlunLoading.value = true
  
  try {
    const resp = await fetch('/api/v1/chanlun/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        market: stock.market,
        code: stock.code,
        category: 'DAY',
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
    chanlunZss.value = data.zss ?? []
    chanlunMmds.value = data.mmds ?? []
    chanlunFxs.value = data.fractals ?? []
    chanlunBcs.value = data.bcs ?? []
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
        category: 'DAY',
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
  treeCount: qualifiedStocks.value.filter(s => s.classification === 'tree').length,
  grainCount: qualifiedStocks.value.filter(s => s.classification === 'grain').length,
  vegetableCount: qualifiedStocks.value.filter(s => s.classification === 'vegetable').length,
  avgScore: qualifiedStocks.value.length > 0
    ? (qualifiedStocks.value.reduce((s, st) => s + st.quality_score, 0) / qualifiedStocks.value.length).toFixed(1)
    : '-',
}))

// ── 生命周期 ────────────────────────────────────────────────────────────
onMounted(() => {
  // 默认选择今天前30天
  const d = new Date()
  d.setDate(d.getDate() - 30)
  selectDate.value = d.toISOString().slice(0, 10)
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
      <button 
        class="primary scan-btn" 
        :disabled="scanning" 
        @click="scanStocks"
      >
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

    <!-- 主内容区 -->
    <div class="main-content">
      <!-- 左侧：股票列表 -->
      <div class="stock-panel">
        <div class="panel-header">
          <h3>筛选结果 ({{ qualifiedStocks.length }})</h3>
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
              <span class="stat">质量: <strong>{{ stock.quality_score }}</strong></span>
              <span class="stat">1买: <strong style="color: #22c55e">{{ stock.buy_1_count }}</strong></span>
              <span class="stat">1卖: <strong style="color: #ef4444">{{ stock.sell_1_count }}</strong></span>
            </div>
            <div class="stock-recommendation" :style="{ color: ACTION_COLORS[getRecommendation(stock).action] }">
              {{ getRecommendation(stock).label }}
            </div>
            <div v-if="stock.latest_mmd" class="stock-latest">
              最新: {{ stock.latest_mmd.type }} @ {{ stock.latest_mmd.date }}
              <span v-if="stock.days_since_signal !== undefined && stock.days_since_signal < 999" class="days-since">({{ stock.days_since_signal }}天前)</span>
            </div>
            <div v-if="stock.latest_mmd" class="stock-hint" :style="{ borderColor: ACTION_COLORS[getRecommendation(stock).action] }">
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
              :style="{ background: CLASSIFICATION_COLORS[selectedStock.classification] + '20', color: CLASSIFICATION_COLORS[selectedStock.classification], borderColor: CLASSIFICATION_COLORS[selectedStock.classification] }"
            >
              {{ CLASSIFICATION_LABELS[selectedStock.classification] }}
            </span>
            <span 
              class="action-badge"
              :style="{ background: ACTION_COLORS[getRecommendation(selectedStock).action] + '20', color: ACTION_COLORS[getRecommendation(selectedStock).action], borderColor: ACTION_COLORS[getRecommendation(selectedStock).action] }"
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
          <div class="detail-stat" v-if="selectedStock.days_since_signal !== undefined && selectedStock.days_since_signal < 999">
            <span class="label">距信号</span>
            <span class="value" :style="{ color: selectedStock.days_since_signal <= 10 ? '#22c55e' : '#fbbf24' }">{{ selectedStock.days_since_signal }}天</span>
          </div>
        </div>

        <!-- 操作建议 -->
        <div v-if="selectedStock.latest_mmd" class="action-hint-panel" :style="{ borderColor: ACTION_COLORS[getRecommendation(selectedStock).action] }">
          <div class="hint-title">💡 操作建议</div>
          <div class="hint-text">{{ getActionExplanation(selectedStock) }}</div>
        </div>

        <!-- K线图 -->
        <div v-if="!chanlunLoading && bars.length > 0" class="chart-area">
          <ChanlunChart
            :bars="bars"
            :bis="chanlunBis"
            :xds="chanlunXds"
            :zss="chanlunZss"
            :mmds="chanlunMmds"
            :fxs="chanlunFxs"
            :bcs="chanlunBcs"
            :frequency="'DAY'"
          />
        </div>
        <div v-else-if="chanlunLoading" class="chart-placeholder">
          正在分析缠论结构…
        </div>

        <!-- 快速诊断按钮 -->
        <button
          class="ghost backtest-btn"
          @click="goToDiagnosis(selectedStock!)"
        >
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
              <span class="value" :style="{ color: backtestResult.performance.total_return >= 0 ? '#22c55e' : '#ef4444' }">
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
          <EquityChart v-if="backtestResult.equity_curve.length > 0" :equity="backtestResult.equity_curve" />
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
  background: rgba(255,255,255,0.02);
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
  background: rgba(255,255,255,0.02);
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
</style>
