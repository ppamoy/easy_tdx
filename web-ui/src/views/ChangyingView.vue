<script setup lang="ts">
// 长赢投资页面：基于吴伟志《长赢：穿越股市的牛熊周期》投资体系
// 核心功能：四季周期判断、树粮菜三维选股、仓位配置建议、交易纪律提醒

import { computed, onMounted, ref, watch } from 'vue'
import { fetchBars } from '../api'
import { detectMarket } from '../market'
import type { Bar } from '../types'
import echarts, { UP_COLOR, DOWN_COLOR } from '../echarts-setup'
import { fmt2 } from '../format'

// ── 四季周期状态 ────────────────────────────────────────────────────────
type Season = 'spring' | 'summer' | 'autumn' | 'winter' | 'unknown'

interface SeasonInfo {
  season: Season
  label: string
  color: string
  desc: string
  strategy: string
  position: string
  action: string
}

const SEASON_MAP: Record<Season, SeasonInfo> = {
  spring: {
    season: 'spring',
    label: '春季 · 播种期',
    color: '#4ade80',
    desc: '熊末牛初，估值见底，市场情绪极致绝望，行情在绝望中诞生',
    strategy: '春播：分批逆向布局，精选优质成长标的，逐步建仓',
    position: '30%-50%',
    action: '买入优质成长股，不恐慌割肉',
  },
  summer: {
    season: 'summer',
    label: '夏季 · 成长期',
    color: '#22c55e',
    desc: '牛市主升，赚钱效应扩散，行情在犹豫中发展，主线持续走强',
    strategy: '夏长：坚定满仓持有，拥抱核心主线，杜绝频繁换股',
    position: '80%-100%',
    action: '满仓持有核心标的，让利润奔跑',
  },
  autumn: {
    season: 'autumn',
    label: '秋季 · 收获期',
    color: '#f59e0b',
    desc: '牛市末期，情绪狂热，估值透支，行情在乐观中见顶',
    strategy: '秋收：分批减仓落袋，收缩战线，剔除劣质标的',
    position: '20%-40%',
    action: '分批止盈，锁定收益',
  },
  winter: {
    season: 'winter',
    label: '冬季 · 蛰伏期',
    color: '#60a5fa',
    desc: '熊市主跌，恐慌蔓延，流动性收缩，普跌行情为主',
    strategy: '冬藏：轻仓空仓为主，现金为王，耐心等待市场出清',
    position: '0%-20%',
    action: '轻仓观望，保存本金',
  },
  unknown: {
    season: 'unknown',
    label: '分析中…',
    color: '#94a3b8',
    desc: '数据不足，无法判断当前周期阶段',
    strategy: '观望',
    position: '-',
    action: '等待更多数据',
  },
}

// ── 树粮菜分类 ──────────────────────────────────────────────────────────
type StockType = 'tree' | 'grain' | 'vegetable'

interface StockTypeConfig {
  type: StockType
  label: string
  icon: string
  color: string
  desc: string
  holdPeriod: string
  riskLevel: string
  allocation: Record<Season, string>
}

const STOCK_TYPE_MAP: Record<StockType, StockTypeConfig> = {
  tree: {
    type: 'tree',
    label: '树型企业',
    icon: '🌳',
    color: '#22c55e',
    desc: '质地顶尖、护城河深厚、具备长期持续成长能力的龙头企业',
    holdPeriod: '长期持有，穿越牛熊',
    riskLevel: '中等',
    allocation: { spring: '40%', summer: '50%', autumn: '30%', winter: '20%', unknown: '30%' },
  },
  grain: {
    type: 'grain',
    label: '粮型企业',
    icon: '🌾',
    color: '#f59e0b',
    desc: '基本面稳定、业绩确定性高、分红稳定、估值合理的成熟企业',
    holdPeriod: '稳健持有，震荡市配置',
    riskLevel: '较低',
    allocation: { spring: '20%', summer: '20%', autumn: '30%', winter: '40%', unknown: '30%' },
  },
  vegetable: {
    type: 'vegetable',
    label: '菜型企业',
    icon: '🥬',
    color: '#ef4444',
    desc: '贴合行业高景气、短期弹性大、行情爆发力强的赛道标的',
    holdPeriod: '波段操作，快进快出',
    riskLevel: '较高',
    allocation: { spring: '30%', summer: '30%', autumn: '20%', winter: '10%', unknown: '20%' },
  },
}

// ── 状态变量 ────────────────────────────────────────────────────────────
const code = ref('000001')
const category = ref<'DAY' | 'WEEK'>('DAY')
const loading = ref(false)
const error = ref('')
const bars = ref<Bar[]>([])
const currentSeason = ref<Season>('unknown')
const filterType = ref<'all' | 'tree' | 'grain' | 'vegetable'>('all')

interface StockItem {
  code: string
  name: string
  price: number
  change: number
  pe: number
  pb: number
  dividend: number
  growth: number
  moat: string
  type: StockType
  seasonAllocation: Record<Season, string>
}

const stockPool = ref<StockItem[]>([
  {
    code: '600519',
    name: '贵州茅台',
    price: 1680,
    change: 1.2,
    pe: 28,
    pb: 10,
    dividend: 1.5,
    growth: 15,
    moat: '品牌护城河极深',
    type: 'tree',
    seasonAllocation: {
      spring: '40%',
      summer: '50%',
      autumn: '30%',
      winter: '20%',
      unknown: '30%',
    },
  },
  {
    code: '000858',
    name: '五粮液',
    price: 145,
    change: -0.5,
    pe: 20,
    pb: 4,
    dividend: 2.0,
    growth: 12,
    moat: '浓香龙头',
    type: 'tree',
    seasonAllocation: {
      spring: '40%',
      summer: '50%',
      autumn: '30%',
      winter: '20%',
      unknown: '30%',
    },
  },
  {
    code: '000333',
    name: '美的集团',
    price: 68,
    change: 0.8,
    pe: 12,
    pb: 2.5,
    dividend: 3.5,
    growth: 10,
    moat: '家电龙头',
    type: 'tree',
    seasonAllocation: {
      spring: '40%',
      summer: '50%',
      autumn: '30%',
      winter: '20%',
      unknown: '30%',
    },
  },
  {
    code: '601318',
    name: '中国平安',
    price: 48,
    change: -1.2,
    pe: 9,
    pb: 1.2,
    dividend: 4.0,
    growth: 8,
    moat: '金融综合平台',
    type: 'grain',
    seasonAllocation: {
      spring: '20%',
      summer: '20%',
      autumn: '30%',
      winter: '40%',
      unknown: '30%',
    },
  },
  {
    code: '600036',
    name: '招商银行',
    price: 35,
    change: 0.3,
    pe: 6,
    pb: 0.9,
    dividend: 5.0,
    growth: 6,
    moat: '零售银行龙头',
    type: 'grain',
    seasonAllocation: {
      spring: '20%',
      summer: '20%',
      autumn: '30%',
      winter: '40%',
      unknown: '30%',
    },
  },
  {
    code: '600900',
    name: '长江电力',
    price: 28,
    change: 0.1,
    pe: 18,
    pb: 2,
    dividend: 3.8,
    growth: 5,
    moat: '水电垄断',
    type: 'grain',
    seasonAllocation: {
      spring: '20%',
      summer: '20%',
      autumn: '30%',
      winter: '40%',
      unknown: '30%',
    },
  },
  {
    code: '300750',
    name: '宁德时代',
    price: 195,
    change: 2.5,
    pe: 25,
    pb: 5,
    dividend: 0.5,
    growth: 35,
    moat: '电池龙头',
    type: 'vegetable',
    seasonAllocation: {
      spring: '30%',
      summer: '30%',
      autumn: '20%',
      winter: '10%',
      unknown: '20%',
    },
  },
  {
    code: '002594',
    name: '比亚迪',
    price: 265,
    change: 1.8,
    pe: 22,
    pb: 4,
    dividend: 0.3,
    growth: 40,
    moat: '新能源整车',
    type: 'vegetable',
    seasonAllocation: {
      spring: '30%',
      summer: '30%',
      autumn: '20%',
      winter: '10%',
      unknown: '20%',
    },
  },
  {
    code: '601012',
    name: '隆基绿能',
    price: 25,
    change: -3.5,
    pe: 8,
    pb: 1.5,
    dividend: 1.0,
    growth: -10,
    moat: '光伏龙头',
    type: 'vegetable',
    seasonAllocation: {
      spring: '30%',
      summer: '30%',
      autumn: '20%',
      winter: '10%',
      unknown: '20%',
    },
  },
])

// 周期判断指标
const marketMetrics = ref({
  pePercentile: 45,
  pbPercentile: 38,
  volumeRatio: 1.0,
  advanceDecline: 0.15,
  newHighNewLow: 0.8,
  fearGreedIndex: 55,
  ma200: 5.2,
  trendStrength: 0.6,
})

// 组合配置
const portfolio = ref({
  treeWeight: 40,
  grainWeight: 30,
  vegetableWeight: 30,
  cashWeight: 0,
})

// ── 周期判断逻辑 ────────────────────────────────────────────────────────
function analyzeSeason(): Season {
  if (bars.value.length < 100) return 'unknown'

  const last = bars.value[bars.value.length - 1]
  const prev100 = bars.value[Math.max(0, bars.value.length - 100)]

  const priceChange = (last.close - prev100.open) / prev100.open
  const avgVol = bars.value.slice(-20).reduce((s, b) => s + b.vol, 0) / 20
  const volRatio = avgVol / (bars.value.slice(-60).reduce((s, b) => s + b.vol, 0) / 60)

  if (priceChange > 0.3 && volRatio > 1.2) return 'summer'
  if (priceChange > 0.1 && volRatio > 1.0) return 'spring'
  if (priceChange < -0.3 && volRatio > 1.5) return 'winter'
  if (priceChange < -0.1) return 'autumn'
  if (Math.abs(priceChange) < 0.05) return 'summer'

  return 'unknown'
}

// ── 图表渲染 ────────────────────────────────────────────────────────────
const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function renderChart() {
  if (!chartRef.value || bars.value.length === 0) return
  if (!chart) chart = echarts.init(chartRef.value, 'dark')

  const dates = bars.value.map((b) => b.datetime.slice(0, 10))
  const ohlc = bars.value.map((b) => [b.open, b.close, b.low, b.high])

  chart.setOption(
    {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        formatter: (params: any) => {
          const p = params[0]
          const d = p.value
          return `${p.axisValue}<br/>O:${fmt2(d[1])} C:${fmt2(d[2])} H:${fmt2(d[3])} L:${fmt2(d[4])}`
        },
      },
      grid: { left: '5%', right: '3%', top: '10%', bottom: '15%' },
      xAxis: {
        type: 'category',
        data: dates,
        axisLine: { lineStyle: { color: '#2a2e3a' } },
        axisLabel: { color: '#5c6370', formatter: (v: string) => v },
      },
      yAxis: {
        type: 'value',
        scale: true,
        splitLine: { lineStyle: { color: '#2a2e3a' } },
        axisLabel: { formatter: fmt2, color: '#5c6370' },
      },
      dataZoom: [{ type: 'slider', bottom: 10, start: 50, end: 100 }],
      series: [
        {
          name: 'K线',
          type: 'candlestick',
          data: ohlc,
          itemStyle: {
            color: UP_COLOR,
            color0: DOWN_COLOR,
            borderColor: UP_COLOR,
            borderColor0: DOWN_COLOR,
          },
        },
      ],
    },
    true,
  )
}

function resize() {
  chart?.resize()
}

// ── 操作方法 ────────────────────────────────────────────────────────────
async function analyze() {
  loading.value = true
  error.value = ''
  try {
    const market = detectMarket(code.value)
    const allBars = await fetchBars(market, code.value, category.value)
    if (allBars.length === 0) {
      error.value = `未取到 ${market}:${code.value} 的 ${category.value} 数据`
      return
    }
    bars.value = allBars.slice(-500)
    currentSeason.value = analyzeSeason()
    renderChart()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function getSeasonStrategy(): string {
  const season = currentSeason.value
  if (season === 'spring') return '重树菜，轻粮，逐步建仓'
  if (season === 'summer') return '满仓树菜，让利润奔跑'
  if (season === 'autumn') return '逐步减仓，转向粮类防守'
  if (season === 'winter') return '空仓或极低仓位，现金为王'
  return '观望，等待周期明确'
}

// ── 计算属性 ────────────────────────────────────────────────────────────
const filteredStocks = computed(() => {
  if (filterType.value === 'all') return stockPool.value
  return stockPool.value.filter((s) => s.type === filterType.value)
})

// ── 生命周期 ────────────────────────────────────────────────────────────
onMounted(() => {
  analyze()
  window.addEventListener('resize', resize)
  // 阻止图表容器吞没滚轮事件，确保页面可以滚动
  const el = chartRef.value
  if (el) {
    el.addEventListener('wheel', (e: WheelEvent) => e.stopPropagation(), {
      passive: false,
      capture: true,
    })
  }
})

watch([code, category], () => {
  if (code.value) analyze()
})
</script>

<template>
  <div class="changying-view">
    <!-- 顶部标题区 -->
    <div class="hero-section">
      <div class="hero-content">
        <h1>🌱 长赢投资</h1>
        <p class="hero-desc">穿越牛熊 · 四季轮回 · 长期主义</p>
        <p class="hero-source">基于吴伟志《长赢：穿越股市的牛熊周期》投资体系</p>
      </div>
      <div
        class="season-badge"
        :style="{
          borderColor: SEASON_MAP[currentSeason].color,
          color: SEASON_MAP[currentSeason].color,
        }"
      >
        {{ SEASON_MAP[currentSeason].label }}
      </div>
    </div>

    <!-- 四季周期卡片 -->
    <div class="season-cards">
      <div
        v-for="(info, key) in SEASON_MAP"
        :key="key"
        class="season-card"
        :class="{ active: currentSeason === key }"
        :style="{ borderTopColor: info.color }"
      >
        <div class="season-icon">
          {{ key === 'spring' ? '🌱' : key === 'summer' ? '☀️' : key === 'autumn' ? '🍂' : '❄️' }}
        </div>
        <div class="season-label">{{ info.label }}</div>
        <div class="season-desc">{{ info.desc }}</div>
        <div class="season-strategy">{{ info.strategy }}</div>
        <div class="season-position">
          建议仓位: <span :style="{ color: info.color }">{{ info.position }}</span>
        </div>
      </div>
    </div>

    <!-- 当前周期详解 -->
    <div v-if="currentSeason !== 'unknown'" class="season-detail">
      <div class="detail-header">
        <h2>{{ SEASON_MAP[currentSeason].label }}</h2>
        <span class="detail-color" :style="{ color: SEASON_MAP[currentSeason].color }">●</span>
      </div>
      <div class="detail-content">
        <div class="detail-text">{{ SEASON_MAP[currentSeason].desc }}</div>
        <div class="detail-action">
          <strong>当前操作:</strong> {{ SEASON_MAP[currentSeason].action }}
        </div>
      </div>
    </div>

    <!-- 图表 + 市场指标 -->
    <div class="main-content">
      <div class="chart-panel">
        <div class="panel-header">
          <h3>📈 行情分析</h3>
          <div class="chart-controls">
            <input
              v-model="code"
              type="text"
              placeholder="股票代码"
              maxlength="6"
              class="code-input"
            />
            <select v-model="category" class="category-select">
              <option value="DAY">日线</option>
              <option value="WEEK">周线</option>
            </select>
            <button class="primary analyze-btn" :disabled="loading" @click="analyze">
              {{ loading ? '分析中…' : '开始分析' }}
            </button>
          </div>
        </div>
        <div v-if="error" class="error-banner">⚠ {{ error }}</div>
        <div ref="chartRef" class="chart-container" v-if="!loading && bars.length > 0"></div>
        <div v-else-if="loading" class="chart-placeholder">正在分析行情…</div>
        <div v-else class="chart-placeholder">输入股票代码后点击「开始分析」</div>
      </div>

      <!-- 市场指标面板 -->
      <div class="metrics-panel">
        <div class="panel-header"><h3>📊 市场指标</h3></div>
        <div class="metrics-grid">
          <div class="metric-item">
            <span class="metric-label">PE分位数</span>
            <span class="metric-value">{{ marketMetrics.pePercentile.toFixed(1) }}%</span>
            <div class="metric-bar">
              <div
                class="metric-fill"
                :style="{
                  width: marketMetrics.pePercentile + '%',
                  background:
                    marketMetrics.pePercentile < 30
                      ? '#22c55e'
                      : marketMetrics.pePercentile > 70
                        ? '#ef4444'
                        : '#f59e0b',
                }"
              ></div>
            </div>
          </div>
          <div class="metric-item">
            <span class="metric-label">PB分位数</span>
            <span class="metric-value">{{ marketMetrics.pbPercentile.toFixed(1) }}%</span>
            <div class="metric-bar">
              <div
                class="metric-fill"
                :style="{
                  width: marketMetrics.pbPercentile + '%',
                  background:
                    marketMetrics.pbPercentile < 30
                      ? '#22c55e'
                      : marketMetrics.pbPercentile > 70
                        ? '#ef4444'
                        : '#f59e0b',
                }"
              ></div>
            </div>
          </div>
          <div class="metric-item">
            <span class="metric-label">成交量比率</span>
            <span class="metric-value">{{ marketMetrics.volumeRatio.toFixed(2) }}</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">涨跌比</span>
            <span
              class="metric-value"
              :style="{ color: marketMetrics.advanceDecline > 0 ? UP_COLOR : DOWN_COLOR }"
              >{{ marketMetrics.advanceDecline > 0 ? '+' : ''
              }}{{ marketMetrics.advanceDecline.toFixed(2) }}</span
            >
          </div>
          <div class="metric-item">
            <span class="metric-label">恐慌贪婪</span>
            <span
              class="metric-value"
              :style="{
                color:
                  marketMetrics.fearGreedIndex < 30
                    ? '#22c55e'
                    : marketMetrics.fearGreedIndex > 70
                      ? '#ef4444'
                      : '#f59e0b',
              }"
              >{{ marketMetrics.fearGreedIndex }}</span
            >
          </div>
          <div class="metric-item">
            <span class="metric-label">距200日均线</span>
            <span
              class="metric-value"
              :style="{ color: marketMetrics.ma200 > 0 ? UP_COLOR : DOWN_COLOR }"
              >{{ marketMetrics.ma200 > 0 ? '+' : '' }}{{ marketMetrics.ma200.toFixed(2) }}%</span
            >
          </div>
        </div>
      </div>
    </div>

    <!-- 树粮菜三维选股 -->
    <div class="stock-section">
      <div class="section-title">
        <h2>🌲🌾🥬 树粮菜三维选股模型</h2>
        <p class="section-desc">不同市场四季阶段，调整三类标的仓位配比，实现攻守平衡</p>
      </div>

      <!-- 类型说明卡片 -->
      <div class="stock-types">
        <div
          v-for="(config, key) in STOCK_TYPE_MAP"
          :key="key"
          class="stock-type-card"
          :style="{ borderTopColor: config.color }"
        >
          <div class="type-header">
            <span class="type-icon">{{ config.icon }}</span>
            <span class="type-label" :style="{ color: config.color }">{{ config.label }}</span>
            <span class="type-risk">风险: {{ config.riskLevel }}</span>
          </div>
          <div class="type-desc">{{ config.desc }}</div>
          <div class="type-meta">
            <span>持有周期: {{ config.holdPeriod }}</span>
          </div>
          <div class="type-allocation">
            <div
              v-for="s in ['spring', 'summer', 'autumn', 'winter'] as Season[]"
              :key="s"
              class="alloc-item"
            >
              <span class="alloc-season">{{
                s === 'spring' ? '春' : s === 'summer' ? '夏' : s === 'autumn' ? '秋' : '冬'
              }}</span>
              <span class="alloc-value" :style="{ color: SEASON_MAP[s].color }">{{
                config.allocation[s]
              }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 股票列表 -->
      <div class="stock-table">
        <div class="table-header">
          <h3>精选标的池（{{ stockPool.length }} 只）</h3>
          <div class="table-filter">
            <button class="filter-btn active" @click="filterType = 'all'">全部</button>
            <button
              class="filter-btn"
              :style="{
                borderColor: STOCK_TYPE_MAP.tree.color,
                color: filterType === 'tree' ? STOCK_TYPE_MAP.tree.color : '',
              }"
              @click="filterType = 'tree'"
            >
              树
            </button>
            <button
              class="filter-btn"
              :style="{
                borderColor: STOCK_TYPE_MAP.grain.color,
                color: filterType === 'grain' ? STOCK_TYPE_MAP.grain.color : '',
              }"
              @click="filterType = 'grain'"
            >
              粮
            </button>
            <button
              class="filter-btn"
              :style="{
                borderColor: STOCK_TYPE_MAP.vegetable.color,
                color: filterType === 'vegetable' ? STOCK_TYPE_MAP.vegetable.color : '',
              }"
              @click="filterType = 'vegetable'"
            >
              菜
            </button>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th>代码</th>
              <th>名称</th>
              <th>类型</th>
              <th>价格</th>
              <th>涨跌</th>
              <th>PE</th>
              <th>股息率</th>
              <th>成长性</th>
              <th>护城河</th>
              <th>当前配置</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="stock in filteredStocks" :key="stock.code">
              <td class="code-cell">{{ stock.code }}</td>
              <td class="name-cell">{{ stock.name }}</td>
              <td>
                <span
                  class="type-badge"
                  :style="{
                    background: STOCK_TYPE_MAP[stock.type].color + '20',
                    color: STOCK_TYPE_MAP[stock.type].color,
                    borderColor: STOCK_TYPE_MAP[stock.type].color,
                  }"
                >
                  {{ STOCK_TYPE_MAP[stock.type].icon }} {{ STOCK_TYPE_MAP[stock.type].label }}
                </span>
              </td>
              <td>{{ fmt2(stock.price) }}</td>
              <td :style="{ color: stock.change >= 0 ? UP_COLOR : DOWN_COLOR }">
                {{ stock.change >= 0 ? '+' : '' }}{{ stock.change.toFixed(2) }}%
              </td>
              <td>{{ stock.pe }}</td>
              <td>{{ stock.dividend }}%</td>
              <td :style="{ color: stock.growth >= 0 ? UP_COLOR : DOWN_COLOR }">
                {{ stock.growth >= 0 ? '+' : '' }}{{ stock.growth }}%
              </td>
              <td class="moat-cell">{{ stock.moat }}</td>
              <td>
                <div class="season-allocation">
                  <span
                    v-for="(s, key) in SEASON_MAP"
                    :key="key"
                    class="season-dot"
                    :style="{ background: s.color, opacity: currentSeason === key ? 1 : 0.4 }"
                    :title="s.label + ': ' + stock.seasonAllocation[key]"
                  >
                    {{ stock.seasonAllocation[key] }}
                  </span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 组合配置 -->
    <div class="portfolio-section">
      <div class="section-title">
        <h2>💼 长赢组合配置</h2>
        <p class="section-desc">根据当前四季阶段动态调整三类标的仓位配比</p>
      </div>
      <div class="portfolio-content">
        <div class="portfolio-chart">
          <div ref="pieChartRef" class="pie-chart"></div>
        </div>
        <div class="portfolio-config">
          <div class="config-item">
            <div class="config-label">
              <span class="config-dot" style="background: #22c55e"></span>
              树型企业（核心底仓）
            </div>
            <input
              v-model.number="portfolio.treeWeight"
              type="number"
              min="0"
              max="100"
              class="config-input"
            />
            <span class="config-percent">{{ portfolio.treeWeight }}%</span>
          </div>
          <div class="config-item">
            <div class="config-label">
              <span class="config-dot" style="background: #f59e0b"></span>
              粮型企业（稳健收益）
            </div>
            <input
              v-model.number="portfolio.grainWeight"
              type="number"
              min="0"
              max="100"
              class="config-input"
            />
            <span class="config-percent">{{ portfolio.grainWeight }}%</span>
          </div>
          <div class="config-item">
            <div class="config-label">
              <span class="config-dot" style="background: #ef4444"></span>
              菜型企业（波段收益）
            </div>
            <input
              v-model.number="portfolio.vegetableWeight"
              type="number"
              min="0"
              max="100"
              class="config-input"
            />
            <span class="config-percent">{{ portfolio.vegetableWeight }}%</span>
          </div>
          <div class="config-item">
            <div class="config-label">
              <span class="config-dot" style="background: #60a5fa"></span>
              现金（防守仓位）
            </div>
            <input
              v-model.number="portfolio.cashWeight"
              type="number"
              min="0"
              max="100"
              class="config-input"
            />
            <span class="config-percent">{{ portfolio.cashWeight }}%</span>
          </div>
        </div>
      </div>
      <div class="portfolio-summary">
        <div class="summary-item">
          <span class="summary-label">当前季节</span>
          <span class="summary-value" :style="{ color: SEASON_MAP[currentSeason].color }">{{
            SEASON_MAP[currentSeason].label
          }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">建议股票仓位</span>
          <span class="summary-value">{{ 100 - portfolio.cashWeight }}%</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">配置原则</span>
          <span class="summary-value">{{ getSeasonStrategy() }}</span>
        </div>
      </div>
    </div>

    <!-- 长赢纪律 -->
    <div class="discipline-section">
      <div class="section-title">
        <h2>📜 长赢核心纪律</h2>
        <p class="section-desc">所有理论最终落地为实操，规避散户核心亏损误区</p>
      </div>
      <div class="discipline-grid">
        <div class="discipline-card">
          <div class="discipline-icon">🔄</div>
          <div class="discipline-title">逆向布局，拒绝从众</div>
          <div class="discipline-desc">
            底部绝望时敢布局，顶部狂热时敢离场，市场共识极强的方向往往是风险拐点
          </div>
        </div>
        <div class="discipline-card">
          <div class="discipline-icon">🎯</div>
          <div class="discipline-title">不预测终点，只应对周期</div>
          <div class="discipline-desc">
            不精准猜测牛市顶、熊市底，只根据当下市场四季状态，匹配对应的仓位和策略
          </div>
        </div>
        <div class="discipline-card">
          <div class="discipline-icon">🛡️</div>
          <div class="discipline-title">本金优先，容错第一</div>
          <div class="discipline-desc">
            长赢的前提是"活着"，熊市严控仓位、守住本金，拒绝重仓博弈、满仓抄底
          </div>
        </div>
        <div class="discipline-card">
          <div class="discipline-icon">⚖️</div>
          <div class="discipline-title">动态均衡，不偏执单一风格</div>
          <div class="discipline-desc">
            不固守价值、不迷信成长，根据市场周期轮动切换风格，适配A股结构性行情
          </div>
        </div>
        <div class="discipline-card">
          <div class="discipline-icon">🎓</div>
          <div class="discipline-title">赚认知内的钱</div>
          <div class="discipline-desc">
            看不懂的赛道、估值透支的标的坚决不碰，所有收益都是认知的变现
          </div>
        </div>
        <div class="discipline-card">
          <div class="discipline-icon">⏰</div>
          <div class="discipline-title">长期主义，复利前行</div>
          <div class="discipline-desc">短期靠运气，长期靠规律，控制回撤比追逐超额收益更重要</div>
        </div>
      </div>
    </div>

    <!-- 核心理念 -->
    <div class="philosophy-section">
      <div class="section-title">
        <h2>💡 长赢核心理念</h2>
      </div>
      <div class="philosophy-grid">
        <div class="philosophy-card">
          <h3>🌾 投资是种庄稼，不是种天气</h3>
          <p>
            短期市场波动是不可控的"天气"，企业成长、周期轮回是可把握的"庄稼生长规律"。拒绝投机博弈，坚持价值成长长期主义。
          </p>
        </div>
        <div class="philosophy-card">
          <h3>🔄 唯一永恒的投资信仰：相信周期</h3>
          <p>
            市场永远遵循盛极而衰、否极泰来的轮回规律。所有市场狂热、极致恐慌都是周期的极端拐点，唯有周期规律恒定不变。
          </p>
        </div>
        <div class="philosophy-card">
          <h3>📐 投资只需要解两道核心题</h3>
          <p>
            一是企业题：筛选优质、有持续成长空间的好公司；二是市场题：识别市场周期阶段、顺势而为、逆向布局。两道题缺一不可。
          </p>
        </div>
        <div class="philosophy-card">
          <h3>🎋 术道结合，知行合一</h3>
          <p>
            选股、择时、仓位等技巧是"术"，周期思维、价值思维、敬畏市场是"道"。长赢的本质是用规律指导操作，用纪律落地认知。
          </p>
        </div>
      </div>
    </div>

    <!-- 终极结论 -->
    <div class="conclusion-section">
      <div class="conclusion-box">
        <h2>🏆 长赢终极结论</h2>
        <div class="conclusion-items">
          <div class="conclusion-item">
            <span class="conclusion-num">1</span>
            <span>短期靠运气，长期靠规律</span>
          </div>
          <div class="conclusion-item">
            <span class="conclusion-num">2</span>
            <span>长赢不是年年大胜，而是岁岁不亏、复利前行</span>
          </div>
          <div class="conclusion-item">
            <span class="conclusion-num">3</span>
            <span>投资的最高境界：顺势、守质、自律</span>
          </div>
        </div>
        <div class="conclusion-quote">
          "行情在绝望中产生、在犹豫中发展、在乐观中成熟、在疯狂中终结"
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.changying-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
  padding: 16px 20px;
  gap: 20px;
  background: var(--bg);
}

/* 英雄区 */
.hero-section {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px;
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.1) 0%, rgba(59, 130, 246, 0.1) 100%);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.hero-content h1 {
  font-size: 24px;
  margin: 0 0 8px 0;
  background: linear-gradient(90deg, #22c55e, #3b82f6);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}
.hero-desc {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0 0 4px 0;
}
.hero-source {
  font-size: 12px;
  color: var(--text-dim);
  margin: 0;
}
.season-badge {
  padding: 12px 24px;
  border: 2px solid;
  border-radius: var(--radius);
  font-size: 16px;
  font-weight: 600;
}

/* 四季卡片 */
.season-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.season-card {
  padding: 16px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-top: 3px solid;
  border-radius: var(--radius);
  opacity: 0.6;
  transition: all 0.3s;
}
.season-card.active {
  opacity: 1;
  transform: scale(1.02);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}
.season-icon {
  font-size: 24px;
  margin-bottom: 8px;
}
.season-label {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 8px;
}
.season-desc {
  font-size: 11px;
  color: var(--text-dim);
  margin-bottom: 8px;
  line-height: 1.4;
}
.season-strategy {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 6px;
  padding: 4px 8px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 4px;
}
.season-position {
  font-size: 12px;
  font-weight: 600;
}

/* 当前季节详情 */
.season-detail {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px 20px;
  display: flex;
  gap: 16px;
  align-items: center;
}
.detail-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.detail-header h2 {
  font-size: 18px;
  margin: 0;
}
.detail-color {
  font-size: 20px;
}
.detail-content {
  flex: 1;
}
.detail-text {
  font-size: 13px;
  color: var(--text);
  margin-bottom: 8px;
}
.detail-action {
  font-size: 13px;
  color: var(--text-muted);
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 6px;
}

/* 主要内容区 */
.main-content {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 16px;
}
.chart-panel,
.metrics-panel {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.panel-header h3 {
  font-size: 14px;
  margin: 0;
  color: var(--text);
}
.chart-controls {
  display: flex;
  gap: 8px;
  align-items: center;
}
.code-input {
  width: 80px;
  padding: 6px 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-size: 13px;
}
.category-select {
  padding: 6px 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-size: 13px;
}
.chart-container {
  height: 300px;
}
.chart-placeholder {
  height: 300px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-dim);
  font-size: 13px;
}
.error-banner {
  background: rgba(239, 65, 70, 0.12);
  border: 1px solid var(--up);
  color: var(--up);
  padding: 10px 14px;
  border-radius: var(--radius);
  font-size: 13px;
  margin-bottom: 12px;
}

/* 市场指标 */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.metric-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.metric-label {
  font-size: 11px;
  color: var(--text-dim);
}
.metric-value {
  font-size: 16px;
  font-weight: 600;
}
.metric-bar {
  height: 4px;
  background: var(--bg);
  border-radius: 2px;
  overflow: hidden;
}
.metric-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.5s;
}

/* 股票区域 */
.stock-section {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
}
.section-title {
  margin-bottom: 20px;
}
.section-title h2 {
  font-size: 16px;
  margin: 0 0 6px 0;
  color: var(--text);
}
.section-desc {
  font-size: 12px;
  color: var(--text-dim);
  margin: 0;
}

/* 股票类型卡片 */
.stock-types {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 24px;
}
.stock-type-card {
  padding: 16px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-top: 3px solid;
  border-radius: var(--radius);
}
.type-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.type-icon {
  font-size: 20px;
}
.type-label {
  font-size: 14px;
  font-weight: 600;
}
.type-risk {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-dim);
}
.type-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 10px;
  line-height: 1.5;
}
.type-meta {
  font-size: 11px;
  color: var(--text-dim);
  margin-bottom: 10px;
}
.type-allocation {
  display: flex;
  gap: 12px;
}
.alloc-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.alloc-season {
  font-size: 10px;
  color: var(--text-dim);
}
.alloc-value {
  font-size: 12px;
  font-weight: 600;
}

/* 股票表格 */
.stock-table {
  margin-top: 20px;
}
.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.table-header h3 {
  font-size: 14px;
  margin: 0;
  color: var(--text);
}
.table-filter {
  display: flex;
  gap: 8px;
}
.filter-btn {
  padding: 4px 12px;
  background: transparent;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-dim);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.filter-btn:hover,
.filter-btn.active {
  background: rgba(255, 255, 255, 0.05);
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
th {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  color: var(--text-dim);
  font-weight: 500;
  font-size: 11px;
}
td {
  padding: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  color: var(--text);
}
tr:hover td {
  background: rgba(255, 255, 255, 0.02);
}
.code-cell {
  font-family: var(--font-mono);
  color: var(--text-muted);
}
.name-cell {
  font-weight: 500;
}
.moat-cell {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-dim);
}
.type-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border: 1px solid;
  border-radius: 12px;
  font-size: 11px;
}
.season-allocation {
  display: flex;
  gap: 4px;
}
.season-dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  color: #000;
  font-weight: 600;
}

/* 组合配置 */
.portfolio-section {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
}
.portfolio-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-bottom: 20px;
}
.pie-chart {
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-dim);
}
.portfolio-config {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.config-item {
  display: flex;
  align-items: center;
  gap: 12px;
}
.config-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  min-width: 140px;
}
.config-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.config-input {
  width: 60px;
  padding: 4px 8px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  font-size: 13px;
}
.config-percent {
  font-size: 13px;
  color: var(--text-muted);
  min-width: 30px;
}
.portfolio-summary {
  display: flex;
  gap: 24px;
  padding: 16px;
  background: var(--bg);
  border-radius: var(--radius);
}
.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.summary-label {
  font-size: 11px;
  color: var(--text-dim);
}
.summary-value {
  font-size: 14px;
  font-weight: 600;
}

/* 纪律卡片 */
.discipline-section {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
}
.discipline-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
.discipline-card {
  padding: 16px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.discipline-icon {
  font-size: 24px;
  margin-bottom: 10px;
}
.discipline-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--text);
}
.discipline-desc {
  font-size: 11px;
  color: var(--text-dim);
  line-height: 1.5;
}

/* 理念卡片 */
.philosophy-section {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
}
.philosophy-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}
.philosophy-card {
  padding: 20px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.philosophy-card h3 {
  font-size: 14px;
  margin: 0 0 10px 0;
  color: var(--text);
}
.philosophy-card p {
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.6;
  margin: 0;
}

/* 结论区 */
.conclusion-section {
  background: linear-gradient(135deg, rgba(34, 197, 94, 0.1) 0%, rgba(59, 130, 246, 0.1) 100%);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
}
.conclusion-box h2 {
  font-size: 18px;
  margin: 0 0 20px 0;
  text-align: center;
}
.conclusion-items {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}
.conclusion-item {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
  background: rgba(0, 0, 0, 0.2);
  border-radius: var(--radius);
}
.conclusion-num {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: linear-gradient(135deg, #22c55e, #3b82f6);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
}
.conclusion-quote {
  text-align: center;
  font-size: 14px;
  color: var(--text-muted);
  font-style: italic;
  padding: 16px;
  border-top: 1px solid var(--border);
  margin-top: 16px;
}
</style>
