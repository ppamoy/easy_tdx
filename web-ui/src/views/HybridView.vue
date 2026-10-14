<template>
  <div class="hybrid-view">
    <h2>吴伟志+缠论融合交易系统</h2>
    <p class="subtitle">基本面定方向 · 技术面定时机 · 制度面定约束</p>

    <!-- 控制面板 -->
    <div class="control-panel">
      <div class="input-group">
        <label>市场</label>
        <select v-model="market">
          <option value="SH">沪市</option>
          <option value="SZ">深市</option>
        </select>
      </div>
      <div class="input-group">
        <label>股票代码</label>
        <input v-model="code" placeholder="600000" @keyup.enter="onAnalyze" />
      </div>
      <div class="input-group">
        <label>操作级别</label>
        <select v-model="period">
          <option value="MIN_30">30分钟</option>
          <option value="MIN_60">60分钟</option>
        </select>
      </div>
      <div class="input-group">
        <label>K线条数</label>
        <input v-model.number="count" type="number" min="100" max="4000" step="100" />
      </div>
      <button class="btn-run" @click="onAnalyze" :disabled="loading">
        {{ loading ? '分析中...' : '融合分析' }}
      </button>
    </div>

    <!-- 市场季节卡片 -->
    <div class="season-card" v-if="season?.season">
      <div class="season-badge" :style="{ background: season.color || '#888' }">
        {{ season.label || season.season }}
      </div>
      <div class="season-info">
        <span class="info-item">仓位上限: {{ season.position_range?.[1] || 0 }}%</span>
        <span class="info-item">策略: {{ season.strategy || '' }}</span>
      </div>
      <!-- P0-2: 估值分位 + 涨跌家数信号 -->
      <div class="season-signals" v-if="season.signals">
        <div class="signal-row" v-if="season.signals.val_percentile != null">
          <span class="signal-label">估值分位</span>
          <span class="signal-value" :class="season.signals.val_score > 0 ? 'pos' : season.signals.val_score < 0 ? 'neg' : ''">
            {{ season.signals.val_percentile }}%
          </span>
          <span class="signal-bar">
            <span class="bar-fill" :style="{ width: season.signals.val_percentile + '%', background: season.signals.val_score > 0 ? '#4ade80' : season.signals.val_score < 0 ? '#f87171' : '#94a3b8' }"></span>
          </span>
        </div>
        <div class="signal-row" v-if="season.signals.breadth_ratio != null">
          <span class="signal-label">涨跌家数</span>
          <span class="signal-value" :class="season.signals.breadth_score > 0 ? 'pos' : season.signals.breadth_score < 0 ? 'neg' : ''">
            {{ (season.signals.breadth_ratio * 100).toFixed(1) }}% 上涨
          </span>
          <span class="signal-bar">
            <span class="bar-fill" :style="{ width: (season.signals.breadth_ratio * 100) + '%', background: season.signals.breadth_score > 0 ? '#4ade80' : season.signals.breadth_score < 0 ? '#f87171' : '#94a3b8' }"></span>
          </span>
        </div>
        <div class="signal-row">
          <span class="signal-label">趋势总分</span>
          <span class="signal-value" :class="season.signals.total_score > 0 ? 'pos' : season.signals.total_score < 0 ? 'neg' : ''">
            {{ season.signals.total_score }}
          </span>
        </div>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="loading">正在执行融合分析...</div>

    <!-- 错误 -->
    <div v-if="error" class="error">{{ error }}</div>

    <!-- 分析结果 -->
    <div v-if="result && !loading" class="result-container">
      <!-- 三层架构概览 -->
      <div class="arch-overview">
        <div class="arch-layer" :class="{ pass: result.filter?.passed }">
          <div class="layer-title">第一层：方向过滤</div>
          <div class="layer-content">
            <span class="tag" :class="`tag-${result.category}`">{{ result.category_label || result.category || '未分类' }}</span>
            <span class="tag" :class="`tag-${result.season}`">{{ result.season_label || result.season || '未知' }}</span>
            <span class="filter-result" :class="result.filter?.passed ? 'pass' : 'fail'">
              {{ result.filter?.passed ? '✅ 通过' : '❌ 否决' }}
            </span>
          </div>
          <div class="layer-reason" v-if="result.filter?.reason">{{ result.filter.reason }}</div>
        </div>

        <div class="arch-layer" :class="{ pass: result.latest_signal }">
          <div class="layer-title">第二层：时机执行（缠论）</div>
          <div class="layer-content">
            <template v-if="result.latest_signal">
              <span class="signal-tag" :class="result.latest_signal.is_buy ? 'signal-buy' : 'signal-sell'">
                {{ signalLabel(result.latest_signal.signal_type) }}
              </span>
              <span class="info-item">价格: {{ result.latest_signal.price.toFixed(2) }}</span>
              <span class="info-item">置信度: {{ Math.round(result.latest_signal.confidence * 100) }}%</span>
              <span class="info-item">背驰力度: {{ Math.round(result.latest_signal.beichi_force * 100) }}%</span>
              <span class="info-item">级别: {{ result.latest_signal.level }}</span>
            </template>
            <span v-else class="no-signal">无缠论买卖点信号</span>
          </div>
        </div>

        <div class="arch-layer" :class="{ pass: result.score?.recommendation === 'execute' }">
          <div class="layer-title">第三层：技术评分 + 制度约束</div>
          <div class="layer-content">
            <span class="score-value">评分: {{ result.score?.total || 0 }}/100</span>
            <span class="info-item">日线趋势: {{ trendLabel(result.daily_trend) }}</span>
            <span class="info-item" v-if="result.score?.suggested_position">
              建议仓位: {{ (result.score.suggested_position * 100).toFixed(1) }}%
            </span>
          </div>
          <div class="score-items" v-if="result.score?.items">
            <span v-for="(val, key) in result.score.items" :key="key" class="score-item">
              {{ key }}: +{{ val }}
            </span>
          </div>
        </div>
      </div>

      <!-- 树类提醒卡片 -->
      <div class="tree-reminder" v-if="result.reminder">
        <div class="reminder-icon">🌳</div>
        <div class="reminder-content">
          <div class="reminder-title">树类·长期持有提醒</div>
          <div class="reminder-text">{{ result.reminder }}</div>
          <div class="reminder-hint">大周期买点 = 日线/周线级别买卖点</div>
        </div>
      </div>

      <!-- 最终信号 -->
      <div class="final-signal" :class="`signal-${result.final_signal}`">
        <div class="final-label">最终决策</div>
        <div class="final-action">{{ finalActionLabel(result.final_signal) }}</div>
        <div class="final-reason">{{ result.final_reason }}</div>
      </div>

      <!-- 买卖点列表 -->
      <div class="signals-list" v-if="result.signals?.length">
        <h3>缠论买卖点（{{ result.signals.length }}个）</h3>
        <table class="signals-table">
          <thead>
            <tr>
              <th>类型</th>
              <th>方向</th>
              <th>价格</th>
              <th>置信度</th>
              <th>背驰力度</th>
              <th>级别</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(sig, i) in result.signals" :key="i"
                :class="sig.is_buy ? 'row-buy' : 'row-sell'">
              <td>{{ signalLabel(sig.signal_type) }}</td>
              <td>{{ sig.is_buy ? '买入' : '卖出' }}</td>
              <td>{{ sig.price.toFixed(2) }}</td>
              <td>{{ Math.round(sig.confidence * 100) }}%</td>
              <td>{{ Math.round(sig.beichi_force * 100) }}%</td>
              <td>{{ sig.level }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 财务指标 -->
      <div class="indicators" v-if="result.indicators && Object.keys(result.indicators).length">
        <h3>财务指标（树粮草分类依据）</h3>
        <div class="indicators-grid">
          <div class="ind-item" v-for="(val, key) in displayIndicators" :key="key">
            <span class="ind-label">{{ key }}</span>
            <span class="ind-value">{{ formatInd(val) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const market = ref('SH')
const code = ref('600000')
const period = ref('MIN_30')
const count = ref(500)
const loading = ref(false)
const error = ref('')
const result = ref<any>(null)
const season = ref<any>(null)

// 加载当前季节
async function loadSeason() {
  try {
    const resp = await fetch('/api/v1/hybrid/season')
    season.value = await resp.json()
  } catch (e) {
    // 季节加载失败不影响主功能
  }
}
loadSeason()

// 从看板跳转来自动填充
onMounted(() => {
  if (route.query.code) {
    code.value = route.query.code as string
    if (route.query.market) {
      market.value = route.query.market as string
    }
    onAnalyze()
  }
})

async function onAnalyze() {
  loading.value = true
  error.value = ''
  result.value = null
  try {
    const resp = await fetch('/api/v1/hybrid/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        market: market.value,
        code: code.value,
        period: period.value,
        count: count.value,
      }),
    })
    const data = await resp.json()
    if (data.error) {
      error.value = data.error
    } else {
      result.value = data
    }
  } catch (e: any) {
    error.value = `请求失败: ${e.message}`
  } finally {
    loading.value = false
  }
}

const SIGNAL_LABELS: Record<string, string> = {
  buy_1: '1买', buy_2: '2买', buy_3: '3买',
  sell_1: '1卖', sell_2: '2卖', sell_3: '3卖',
}
function signalLabel(t: string) {
  return SIGNAL_LABELS[t] || t
}
function trendLabel(t: string) {
  return { up: '↑ 向上', down: '↓ 向下', sideways: '→ 震荡', unknown: '未知' }[t] || t
}
function finalActionLabel(s: string) {
  return { execute: '✅ 执行', observe: '👀 观察', reject: '❌ 否决' }[s] || s
}

const IND_KEYS = ['roe', 'eps', 'bps', 'revenue', 'net_profit', 'gross_margin', 'net_margin', 'debt_ratio', 'ocf', 'rev_yoy', 'np_yoy', 'circ_a']
const displayIndicators = computed(() => {
  const ind = result.value?.indicators || {}
  const out: Record<string, any> = {}
  for (const k of IND_KEYS) {
    if (ind[k] != null && ind[k] !== '') out[k] = ind[k]
  }
  return out
})
function formatInd(v: any) {
  if (typeof v === 'number') {
    if (Math.abs(v) > 1e8) return (v / 1e8).toFixed(2) + '亿'
    if (Math.abs(v) > 1e4) return (v / 1e4).toFixed(2) + '万'
    return v.toFixed(2)
  }
  return String(v ?? '')
}
</script>

<style scoped>
.hybrid-view {
  max-width: 1200px;
  margin: 0 auto;
  padding: 16px;
}
.subtitle {
  color: #888;
  font-size: 14px;
  margin: -8px 0 16px;
}
.control-panel {
  display: flex;
  gap: 12px;
  align-items: end;
  flex-wrap: wrap;
  margin-bottom: 20px;
  padding: 16px;
  background: #1a1a2e;
  border-radius: 8px;
}
.input-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.input-group label {
  font-size: 12px;
  color: #888;
}
.input-group input, .input-group select {
  padding: 6px 10px;
  border: 1px solid #444;
  border-radius: 4px;
  background: #16213e;
  color: #e0e0e0;
  width: 120px;
}
.btn-run {
  padding: 8px 24px;
  background: #3964fe;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}
.btn-run:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.season-card {
  display: flex;
  gap: 16px;
  align-items: center;
  padding: 12px 16px;
  background: #1a1a2e;
  border-radius: 8px;
  margin-bottom: 16px;
}
.season-badge {
  padding: 6px 16px;
  border-radius: 20px;
  font-weight: bold;
  color: #fff;
  font-size: 14px;
}
.season-info {
  display: flex;
  gap: 16px;
}
.info-item {
  color: #aaa;
  font-size: 13px;
}
.loading, .error {
  padding: 40px;
  text-align: center;
  color: #888;
}
.error {
  color: #e74c3c;
}
.result-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.arch-overview {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.arch-layer {
  padding: 12px 16px;
  background: #1a1a2e;
  border-radius: 8px;
  border-left: 4px solid #444;
}
.arch-layer.pass {
  border-left-color: #4ade80;
}
.layer-title {
  font-weight: bold;
  color: #ccc;
  margin-bottom: 8px;
  font-size: 13px;
}
.layer-content {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}
.layer-reason {
  color: #888;
  font-size: 12px;
  margin-top: 4px;
}
.tag {
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: bold;
}
.tag-tree { background: #166534; color: #4ade80; }
.tag-grain { background: #854d0e; color: #fbbf24; }
.tag-vegetable { background: #3b0764; color: #c084fc; }
.tag-spring { background: #14532d; color: #4ade80; }
.tag-summer { background: #713f12; color: #fbbf24; }
.tag-autumn { background: #7c2d12; color: #fb923c; }
.tag-winter { background: #1e3a5f; color: #60a5fa; }
.filter-result.pass { color: #4ade80; font-weight: bold; }
.filter-result.fail { color: #f87171; font-weight: bold; }
.signal-tag {
  padding: 2px 10px;
  border-radius: 4px;
  font-weight: bold;
  font-size: 13px;
}
.signal-buy { background: #166534; color: #4ade80; }
.signal-sell { background: #7f1d1d; color: #f87171; }
.no-signal { color: #666; }
.score-value {
  font-size: 18px;
  font-weight: bold;
  color: #fbbf24;
}
.score-items {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 4px;
}
.score-item {
  padding: 2px 8px;
  background: #16213e;
  border-radius: 4px;
  font-size: 11px;
  color: #4ade80;
}
.final-signal {
  padding: 16px 20px;
  border-radius: 8px;
  text-align: center;
}
.signal-execute { background: #14532d; border: 2px solid #4ade80; }
.signal-observe { background: #1e3a5f; border: 2px solid #60a5fa; }
.signal-reject { background: #7f1d1d; border: 2px solid #f87171; }
.final-label {
  font-size: 12px;
  color: #aaa;
}
.final-action {
  font-size: 24px;
  font-weight: bold;
  margin: 4px 0;
}
.signal-execute .final-action { color: #4ade80; }
.signal-observe .final-action { color: #60a5fa; }
.signal-reject .final-action { color: #f87171; }
.final-reason {
  color: #ccc;
  font-size: 13px;
}
.tree-reminder {
  display: flex;
  gap: 12px;
  align-items: start;
  padding: 14px 18px;
  background: linear-gradient(135deg, #1a3a1a, #16213e);
  border: 2px solid #4ade80;
  border-radius: 8px;
}
.reminder-icon {
  font-size: 28px;
  line-height: 1;
}
.reminder-title {
  font-weight: bold;
  color: #4ade80;
  font-size: 14px;
  margin-bottom: 4px;
}
.reminder-text {
  color: #ddd;
  font-size: 13px;
  line-height: 1.5;
}
.reminder-hint {
  color: #888;
  font-size: 11px;
  margin-top: 4px;
}
.signals-list h3, .indicators h3 {
  color: #ccc;
  font-size: 15px;
  margin-bottom: 8px;
}
.signals-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.signals-table th {
  background: #16213e;
  color: #888;
  padding: 6px 10px;
  text-align: left;
  font-weight: normal;
}
.signals-table td {
  padding: 6px 10px;
  border-bottom: 1px solid #222;
  color: #ddd;
}
.row-buy td:first-child { color: #4ade80; }
.row-sell td:first-child { color: #f87171; }
.indicators-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 8px;
}
.ind-item {
  display: flex;
  justify-content: space-between;
  padding: 6px 10px;
  background: #1a1a2e;
  border-radius: 4px;
}
.ind-label {
  color: #888;
  font-size: 12px;
}
.ind-value {
  color: #ddd;
  font-weight: bold;
  font-size: 13px;
}
.season-signals {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.signal-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.signal-label {
  color: #888;
  min-width: 70px;
}
.signal-value {
  font-weight: bold;
  min-width: 80px;
}
.signal-value.pos { color: #4ade80; }
.signal-value.neg { color: #f87171; }
.signal-bar {
  flex: 1;
  height: 6px;
  background: #1a1a2e;
  border-radius: 3px;
  overflow: hidden;
}
.bar-fill {
  display: block;
  height: 100%;
  border-radius: 3px;
  transition: width 0.3s;
}
</style>
