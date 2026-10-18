<script setup lang="ts">
// chanlun2 缠论模型2 分析+回测页面（严格按108课原文实现）
// 功能：输入股票 → 缠论2分析(图表) → 一键回测(策略参数可调) → 收益对比
import { ref, computed, onMounted } from 'vue'
import ChanlunChart from '../components/ChanlunChart.vue'
import type { Bar } from '../types'

const API = '/api/v1'

// ── 输入 ──
const market = ref('SH')
const code = ref('600036')
const category = ref('DAY')
const loading = ref(false)
const error = ref('')

// ── 分析结果 ──
const rawData = ref<any>(null)

// ── 图表数据（适配到 ChanlunChart props）──
const chartBars = ref<Bar[]>([])
const chartBis = ref<any[]>([])
const chartXds = ref<any[]>([])
const chartZss = ref<any[]>([])
const chartMmds = ref<any[]>([])
const chartFxs = ref<any[]>([])

// ── 回测 ──
const backtestLoading = ref(false)
const backtestResult = ref<any>(null)
const trendFilter = ref(true)
const trendHold = ref(true)
const trailingStop = ref(true)
const stopPct = ref(22)

// ── 统计卡片 ──
const stats = computed(() => {
  if (!rawData.value) return null
  const d = rawData.value
  return {
    fractals: d.fractals?.length ?? 0,
    moves: d.moves?.length ?? 0,
    zs_lowest: d.zs_lowest?.length ?? 0,
    zs_moves: d.zs_from_moves?.length ?? 0,
    segments: d.segments?.length ?? 0,
    mmds: d.mmds?.length ?? 0,
  }
})

const mmdTypeLabel: Record<string, string> = {
  buy1: '1买(趋势背驰)', buy2: '2买(回踩不破)', buy3: '3买(突破中枢)',
  sell1: '1卖(趋势背驰)', sell2: '2卖(回试不破)', sell3: '3卖(跌破中枢)',
  panzheng_buy: '盘整背驰买', panzheng_sell: '盘整背驰卖',
}

const mmdColor: Record<string, string> = {
  buy1: '#e74c3c', buy2: '#e67e22', buy3: '#f39c12',
  sell1: '#2ecc71', sell2: '#1abc9c', sell3: '#16a085',
  panzheng_buy: '#9b59b6', panzheng_sell: '#8e44ad',
}

// ── 分析 ──
async function analyze() {
  if (!code.value) return
  loading.value = true
  error.value = ''
  rawData.value = null
  backtestResult.value = null
  try {
    const resp = await fetch(`${API}/chanlun2/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        market: market.value,
        code: code.value,
        category: category.value,
        count: 3000,
      }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const d = await resp.json()
    rawData.value = d
    adaptToChart(d)
  } catch (e: any) {
    error.value = `分析失败: ${e.message}`
  } finally {
    loading.value = false
  }
}

// ── 适配 chanlun2 API → ChanlunChart props ──
function adaptToChart(d: any) {
  // bars
  chartBars.value = (d.bars || []).map((b: any) => ({
    datetime: b.datetime,
    open: b.open, high: b.high, low: b.low, close: b.close, vol: b.vol ?? 0, amount: 0,
  }))

  // moves → bis (笔)
  chartBis.value = (d.moves || []).map((m: any) => ({
    index: m.index,
    direction: m.direction,
    start_date: m.start_dt,
    end_date: m.end_dt,
    high: m.high,
    low: m.low,
    start_index: m.start_k,
    end_index: m.end_k,
    done: true,
  }))

  // segments → xds (线段/走势段)
  chartXds.value = (d.segments || []).map((s: any) => ({
    index: s.index,
    direction: s.direction || (s.kind === 'up' ? 'up' : 'down'),
    start_date: '',
    end_date: '',
    high: s.high,
    low: s.low,
    start_index: s.start_k,
    end_index: s.end_k,
  }))
  // 填充日期
  for (const xd of chartXds.value) {
    const sk = xd.start_index
    const ek = xd.end_index
    if (sk >= 0 && sk < chartBars.value.length) xd.start_date = chartBars.value[sk].datetime
    if (ek >= 0 && ek < chartBars.value.length) xd.end_date = chartBars.value[ek].datetime
  }

  // 中枢：合并 zs_lowest + zs_from_moves
  const zsLowest = (d.zs_lowest || []).map((z: any) => ({
    index: z.index,
    zg: z.zg, zd: z.zd, gg: z.gg, dd: z.dd,
    line_count: z.end_k - z.start_k + 1,
    start_date: chartBars.value[z.start_k]?.datetime ?? '',
    end_date: chartBars.value[z.end_k]?.datetime ?? '',
    start_index: z.start_k,
    end_index: z.end_k,
    done: true,
    level: 0,
  }))
  const zsMoves = (d.zs_from_moves || []).map((z: any) => ({
    index: z.index + 10000,
    zg: z.zg, zd: z.zd, gg: z.gg, dd: z.dd,
    line_count: z.z_moves_count,
    start_date: chartBars.value[z.start_k]?.datetime ?? '',
    end_date: chartBars.value[z.end_k]?.datetime ?? '',
    start_index: z.start_k,
    end_index: z.end_k,
    done: true,
    level: 1,
  }))
  chartZss.value = [...zsLowest, ...zsMoves]

  // 买卖点 → mmds
  chartMmds.value = (d.mmds || []).map((m: any) => ({
    type: m.type,
    date: m.dt,
    msg: m.note || mmdTypeLabel[m.type] || m.type,
    bar_index: m.k_index,
    anchor_val: m.price,
  }))

  // 分型 → fxs
  chartFxs.value = (d.fractals || []).map((f: any) => ({
    fx_type: f.kind === 'bottom' ? 'di' : 'ding',
    date: f.dt,
    val: f.value,
    bar_index: f.k_index,
  }))
}

// ── 回测 ──
async function runBacktest() {
  if (!rawData.value) return
  backtestLoading.value = true
  try {
    const params = new URLSearchParams({
      trend_filter: String(trendFilter.value),
      trend_hold: String(trendHold.value),
      trailing_stop: String(trailingStop.value),
      stop_pct: String(stopPct.value / 100),
    })
    const resp = await fetch(`${API}/chanlun2/backtest?${params}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        market: market.value,
        code: code.value,
        category: category.value,
        count: 3000,
      }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    backtestResult.value = await resp.json()
  } catch (e: any) {
    error.value = `回测失败: ${e.message}`
  } finally {
    backtestLoading.value = false
  }
}

// ── 快捷：常用股票 ──
const quickStocks = [
  { m: 'SH', c: '600036', n: '招商银行' },
  { m: 'SH', c: '601318', n: '中国平安' },
  { m: 'SH', c: '600030', n: '中信证券' },
  { m: 'SZ', c: '000333', n: '美的集团' },
  { m: 'SZ', c: '300750', n: '宁德时代' },
  { m: 'SZ', c: '002415', n: '海康威视' },
]

function pickStock(m: string, c: string) {
  market.value = m
  code.value = c
  analyze()
}

onMounted(() => analyze())
</script>

<template>
  <div class="chanlun2-view">
    <!-- 输入区 -->
    <section class="input-section">
      <h2>缠论模型2 · 108课原文严格实现</h2>
      <div class="input-row">
        <select v-model="market" class="market-select">
          <option value="SH">沪市</option>
          <option value="SZ">深市</option>
        </select>
        <input v-model="code" class="code-input" placeholder="股票代码" @keyup.enter="analyze" />
        <select v-model="category" class="period-select">
          <option value="DAY">日线</option>
          <option value="MIN_30">30分钟</option>
          <option value="MIN_5">5分钟</option>
          <option value="MIN_15">15分钟</option>
          <option value="MIN_60">60分钟</option>
          <option value="WEEK">周线</option>
        </select>
        <button class="btn-primary" @click="analyze" :disabled="loading">
          {{ loading ? '分析中…' : '🔍 分析' }}
        </button>
      </div>
      <div class="quick-stocks">
        <span class="quick-label">快捷：</span>
        <button v-for="s in quickStocks" :key="s.c" class="quick-btn"
          @click="pickStock(s.m, s.c)">{{ s.n }}</button>
      </div>
    </section>

    <!-- 错误 -->
    <div v-if="error" class="error-msg">{{ error }}</div>

    <!-- 统计卡片 -->
    <section v-if="stats" class="stats-section">
      <div class="stat-card">
        <div class="stat-num">{{ stats.fractals }}</div>
        <div class="stat-label">分型</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.moves }}</div>
        <div class="stat-label">笔</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.zs_lowest }}</div>
        <div class="stat-label">K线重叠中枢</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.zs_moves }}</div>
        <div class="stat-label">走势重叠中枢</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.segments }}</div>
        <div class="stat-label">走势段</div>
      </div>
      <div class="stat-card highlight">
        <div class="stat-num">{{ stats.mmds }}</div>
        <div class="stat-label">买卖点</div>
      </div>
    </section>

    <!-- 图表区 -->
    <section v-if="rawData" class="chart-section">
      <div class="chart-header">
        <h3>{{ market }}{{ code }} 缠论2分析图</h3>
      </div>
      <ChanlunChart
        v-if="chartBars.length > 0"
        :bars="chartBars"
        :bis="chartBis"
        :xds="chartXds"
        :zss="chartZss"
        :mmds="chartMmds"
        :fxs="chartFxs"
        :show-mmd-labels="true"
        :frequency="category"
      />
    </section>

    <!-- 买卖点列表 -->
    <section v-if="rawData?.mmds?.length" class="mmd-section">
      <h3>买卖点明细（{{ rawData.mmds.length }}个）</h3>
      <table class="mmd-table">
        <thead>
          <tr>
            <th>#</th><th>类型</th><th>日期</th><th>价格</th><th>方向</th><th>说明</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in rawData.mmds.slice().reverse().slice(0, 30)" :key="m.index">
            <td>{{ m.index }}</td>
            <td>
              <span class="mmd-badge" :style="{ background: mmdColor[m.type] || '#888' }">
                {{ mmdTypeLabel[m.type] || m.type }}
              </span>
            </td>
            <td>{{ m.dt }}</td>
            <td class="price">{{ m.price?.toFixed(2) }}</td>
            <td>{{ m.direction === 'up' ? '↑' : '↓' }}</td>
            <td>{{ m.note }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="rawData.mmds.length > 30" class="more-hint">仅显示最近30个，共{{ rawData.mmds.length }}个</p>
    </section>

    <!-- 回测区 -->
    <section v-if="rawData" class="backtest-section">
      <div class="bt-header">
        <h3>历史回测</h3>
        <div class="bt-params">
          <label class="toggle"><input type="checkbox" v-model="trendFilter" /> 趋势过滤</label>
          <label class="toggle"><input type="checkbox" v-model="trendHold" /> 趋势持有</label>
          <label class="toggle"><input type="checkbox" v-model="trailingStop" /> 移动止损</label>
          <label class="stop-input">止损率
            <input type="number" v-model.number="stopPct" min="5" max="40" step="1" />%
          </label>
        </div>
      </div>

      <button class="btn-primary bt-btn" @click="runBacktest" :disabled="backtestLoading">
        {{ backtestLoading ? '回测中…' : '📊 运行回测' }}
      </button>

      <div v-if="backtestResult?.summary" class="bt-result">
        <div class="bt-cards">
          <div class="bt-card" :class="backtestResult.summary.total_return >= backtestResult.summary.buy_hold_return ? 'win' : 'lose'">
            <div class="bt-num">{{ backtestResult.summary.total_return }}%</div>
            <div class="bt-label">策略收益</div>
          </div>
          <div class="bt-card">
            <div class="bt-num">{{ backtestResult.summary.buy_hold_return }}%</div>
            <div class="bt-label">买入持有</div>
          </div>
          <div class="bt-card" :class="backtestResult.summary.excess >= 0 ? 'win' : 'lose'">
            <div class="bt-num">{{ backtestResult.summary.excess }}%</div>
            <div class="bt-label">超额收益</div>
          </div>
          <div class="bt-card">
            <div class="bt-num">{{ backtestResult.summary.max_drawdown }}%</div>
            <div class="bt-label">最大回撤</div>
          </div>
          <div class="bt-card">
            <div class="bt-num">{{ backtestResult.summary.trades }}</div>
            <div class="bt-label">交易次数</div>
          </div>
          <div class="bt-card">
            <div class="bt-num">{{ backtestResult.summary.win_rate }}%</div>
            <div class="bt-label">胜率</div>
          </div>
        </div>

        <div class="bt-conclusion">
          <span v-if="backtestResult.summary.total_return >= backtestResult.summary.buy_hold_return" class="conclusion-win">
            ✅ 策略跑赢买入持有 {{ (backtestResult.summary.total_return - backtestResult.summary.buy_hold_return).toFixed(1) }}%
          </span>
          <span v-else class="conclusion-lose">
            ❌ 策略跑输买入持有 {{ (backtestResult.summary.buy_hold_return - backtestResult.summary.total_return).toFixed(1) }}%
          </span>
        </div>
      </div>
    </section>

    <!-- 空状态 -->
    <section v-if="!rawData && !loading" class="empty-state">
      <p>输入股票代码，点击「分析」开始</p>
      <p class="hint">或点击上方快捷股票按钮</p>
    </section>
  </div>
</template>

<style scoped>
.chanlun2-view { max-width: 1400px; margin: 0 auto; padding: 16px; }

.input-section { margin-bottom: 16px; }
.input-section h2 { margin: 0 0 12px; font-size: 18px; }
.input-row { display: flex; gap: 8px; align-items: center; }
.market-select, .code-input, .period-select {
  padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px;
}
.code-input { width: 120px; }
.market-select { width: 80px; }
.period-select { width: 100px; }
.btn-primary {
  padding: 8px 20px; background: #3498db; color: #fff; border: none;
  border-radius: 6px; font-size: 14px; cursor: pointer; white-space: nowrap;
}
.btn-primary:hover { background: #2980b9; }
.btn-primary:disabled { background: #95a5a6; cursor: not-allowed; }

.quick-stocks { margin-top: 8px; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.quick-label { color: #888; font-size: 13px; }
.quick-btn {
  padding: 4px 10px; border: 1px solid #ddd; border-radius: 4px;
  background: #f8f9fa; font-size: 13px; cursor: pointer;
}
.quick-btn:hover { background: #e8eaed; }

.error-msg { color: #e74c3c; padding: 12px; background: #fdf2f2; border-radius: 6px; margin-bottom: 16px; }

.stats-section { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.stat-card {
  flex: 1; min-width: 100px; padding: 12px; text-align: center;
  background: #fff; border: 1px solid #eee; border-radius: 8px;
}
.stat-card.highlight { border-color: #f39c12; background: #fff8e1; }
.stat-num { font-size: 24px; font-weight: bold; color: #333; }
.stat-card.highlight .stat-num { color: #e67e22; }
.stat-label { font-size: 12px; color: #888; margin-top: 4px; }

.chart-section { margin-bottom: 20px; }
.chart-header h3 { margin: 0 0 8px; font-size: 16px; }

.mmd-section { margin-bottom: 20px; }
.mmd-section h3 { font-size: 16px; margin-bottom: 8px; }
.mmd-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.mmd-table th, .mmd-table td { padding: 6px 10px; text-align: left; border-bottom: 1px solid #eee; }
.mmd-table th { background: #f5f5f5; font-weight: 600; }
.mmd-badge {
  display: inline-block; padding: 2px 8px; border-radius: 4px;
  color: #fff; font-size: 12px; font-weight: 500;
}
.price { font-family: monospace; font-weight: 600; }
.more-hint { color: #888; font-size: 12px; margin-top: 4px; }

.backtest-section { margin-top: 20px; }
.bt-header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.bt-header h3 { margin: 0; font-size: 16px; }
.bt-params { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.toggle { font-size: 14px; display: flex; align-items: center; gap: 4px; cursor: pointer; }
.stop-input { font-size: 14px; display: flex; align-items: center; gap: 4px; }
.stop-input input { width: 50px; padding: 4px 6px; border: 1px solid #ddd; border-radius: 4px; }
.bt-btn { margin: 12px 0; }

.bt-result { margin-top: 12px; }
.bt-cards { display: flex; gap: 12px; flex-wrap: wrap; }
.bt-card {
  flex: 1; min-width: 110px; padding: 12px; text-align: center;
  background: #fff; border: 1px solid #eee; border-radius: 8px;
}
.bt-card.win { border-color: #2ecc71; background: #eafaf1; }
.bt-card.lose { border-color: #e74c3c; background: #fdf2f2; }
.bt-num { font-size: 22px; font-weight: bold; color: #333; }
.bt-card.win .bt-num { color: #27ae60; }
.bt-card.lose .bt-num { color: #e74c3c; }
.bt-label { font-size: 12px; color: #888; margin-top: 4px; }
.bt-conclusion { margin-top: 12px; font-size: 16px; font-weight: 600; }
.conclusion-win { color: #27ae60; }
.conclusion-lose { color: #e74c3c; }

.empty-state { text-align: center; padding: 60px 0; color: #888; }
.empty-state .hint { font-size: 13px; margin-top: 4px; }
</style>
