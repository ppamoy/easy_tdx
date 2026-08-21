<script setup lang="ts">
// 股票技术诊断页面：综合缠论/MACD/BOLL/均线/成交量给出买卖决策建议。
// 对应后端 API：GET /api/v1/diagnosis/quick?market=SZ&code=000001

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchDiagnosis, formatError } from '../api'
import type { DiagnosisResult } from '../types'
import KlineChart from '../components/KlineChart.vue'
import type { Bar } from '../types'
import { fetchBars } from '../api'

const router = useRouter()

const market = ref<'SZ' | 'SH'>('SZ')
const code = ref('000001')
const loading = ref(false)
const error = ref('')
const diagnosis = ref<DiagnosisResult | null>(null)

// 评分颜色
const SCORE_COLORS: Record<string, string> = {
  strong_buy: '#22c55e',
  buy: '#4ade80',
  hold: '#f59e0b',
  sell: '#f97316',
  strong_sell: '#ef4444',
}

const scoreColor = computed(() => diagnosis.value ? SCORE_COLORS[diagnosis.value.action] || '#6b7280' : '#6b7280')
const scoreValue = computed(() => diagnosis.value ? diagnosis.value.score : 0)

// 最新 K 线
const bars = ref<Bar[]>([])
const barsLoading = ref(false)

async function runDiagnosis() {
  const c = code.value.trim()
  if (!c.match(/^\d{6}$/)) {
    error.value = '请输入 6 位股票代码'
    return
  }
  loading.value = true
  error.value = ''
  diagnosis.value = null
  try {
    diagnosis.value = await fetchDiagnosis(market.value, c)
  } catch (e) {
    error.value = formatError(e)
  } finally {
    loading.value = false
  }
}

async function loadBars() {
  const c = code.value.trim()
  if (!c.match(/^\d{6}$/)) return
  barsLoading.value = true
  try {
    bars.value = await fetchBars(market.value, c, 'DAY', undefined, undefined)
  } catch {
    bars.value = []
  } finally {
    barsLoading.value = false
  }
}

const PATTERN_LABELS: Record<string, string> = {
  doji: '十字星',
  hammer: '锤子线',
  hanging_leg: '吊颈线',
  bullish_engulfing: '阳吞没',
  bearish_engulfing: '阴吞没',
}

function patternLabel(type: string): string {
  return PATTERN_LABELS[type] || type
}

onMounted(() => {
  const q = router.currentRoute.value.query
  if (q.code) code.value = String(q.code)
  if (q.market) market.value = q.market as 'SZ' | 'SH'
  runDiagnosis()
  loadBars()
})
</script>

<template>
  <div class="diagnosis-page">
    <!-- 输入区 -->
    <div class="input-bar">
      <div class="input-group">
        <select v-model="market" class="market-select">
          <option value="SZ">深市</option>
          <option value="SH">沪市</option>
        </select>
        <input
          v-model="code"
          placeholder="6 位代码"
          maxlength="6"
          class="code-input"
          @keyup.enter="runDiagnosis"
        />
        <button class="primary" :disabled="loading" @click="runDiagnosis">
          {{ loading ? '分析中…' : '🔍 技术诊断' }}
        </button>
      </div>
      <span v-if="error" class="error-msg">{{ error }}</span>
    </div>

    <!-- 加载态 -->
    <div v-if="loading" class="state-center">
      <div class="spinner"></div>
      <p>正在综合分析技术指标…</p>
    </div>

    <!-- 无结果 -->
    <div v-else-if="!diagnosis && !error" class="state-center">
      <p>输入股票代码，开始技术诊断</p>
    </div>

    <!-- 诊断结果 -->
    <template v-else-if="diagnosis">
      <!-- 总分 + 操作建议（大卡片） -->
      <div class="hero-card" :style="{ borderTopColor: scoreColor }">
        <div class="hero-left">
          <div class="score-ring" :style="{ borderColor: scoreColor }">
            <span class="score-num" :style="{ color: scoreColor }">{{ scoreValue }}</span>
            <span class="score-unit">分</span>
          </div>
        </div>
        <div class="hero-right">
          <div class="action-badge" :style="{ background: scoreColor }">{{ diagnosis.action_label }}</div>
          <div class="action-reason">{{ diagnosis.reason }}</div>
          <div class="meta-info">
            <span>{{ diagnosis.symbol }}</span>
            <span class="sep">·</span>
            <span>最新价 <b>{{ diagnosis.close }}</b></span>
            <span class="sep">·</span>
            <span>{{ diagnosis.date }}</span>
          </div>
        </div>
      </div>

      <!-- 六维指标网格 -->
      <div class="metrics-grid">
        <!-- 缠论 -->
        <div class="metric-card">
          <div class="card-title">🧧 缠论结构</div>
          <div class="card-body">
            <div class="kv-row"><span class="kv-key">笔数</span><span class="kv-val">{{ diagnosis.chanlun.bi_count }}</span></div>
            <div class="kv-row"><span class="kv-key">中枢数</span><span class="kv-val">{{ diagnosis.chanlun.zs_count }}</span></div>
            <div class="kv-row"><span class="kv-key">买卖点</span><span class="kv-val">{{ diagnosis.chanlun.mmd_count }}</span></div>
            <div class="kv-row highlight"><span class="kv-key">一类买点</span><span class="kv-val buy">{{ diagnosis.chanlun.buy_1_count }}</span></div>
            <div class="kv-row"><span class="kv-key">一类卖点</span><span class="kv-val sell">{{ diagnosis.chanlun.sell_1_count }}</span></div>
            <div v-if="diagnosis.chanlun.latest_mmd" class="latest-mmd">
              <span class="mmd-tag" :class="diagnosis.chanlun.latest_mmd.type">{{ diagnosis.chanlun.latest_mmd.type }}</span>
              <span class="mmd-conf">置信度 {{ diagnosis.chanlun.latest_mmd.confidence ?? '-' }}</span>
              <span v-if="diagnosis.chanlun.latest_mmd.quality" class="mmd-quality" :class="'grade-' + diagnosis.chanlun.latest_mmd.quality.grade">
                质量: {{ diagnosis.chanlun.latest_mmd.quality.grade }} ({{ diagnosis.chanlun.latest_mmd.quality.score }}分)
              </span>
            </div>
            <div v-if="diagnosis.chanlun.recent_signals.length > 0" class="recent-signals">
              <div class="section-label">近3个高质量信号:</div>
              <div class="signal-list">
                <span v-for="(sig, i) in diagnosis.chanlun.recent_signals" :key="i" class="signal-item" :class="sig.type">
                  {{ sig.type }}
                  <span class="sig-conf">{{ (sig.confidence * 100).toFixed(0) }}%</span>
                  <span v-if="sig.quality" class="sig-grade grade-{{ sig.quality.grade }}">{{ sig.quality.grade }}</span>
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- MACD -->
        <div class="metric-card">
          <div class="card-title">📈 MACD</div>
          <div class="card-body">
            <div class="kv-row"><span class="kv-key">DIF</span><span class="kv-val">{{ diagnosis.macd.dif }}</span></div>
            <div class="kv-row"><span class="kv-key">DEA</span><span class="kv-val">{{ diagnosis.macd.dea }}</span></div>
            <div class="kv-row"><span class="kv-key">柱状</span><span class="kv-val" :class="diagnosis.macd.hist >= 0 ? 'up' : 'down'">{{ diagnosis.macd.hist >= 0 ? '+' : '' }}{{ diagnosis.macd.hist }}</span></div>
            <div class="kv-row">
              <span class="kv-key">状态</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.macd.golden_cross, 'tag-red': diagnosis.macd.dead_cross, 'tag-blue': diagnosis.macd.above_zero }">
                {{ diagnosis.macd.golden_cross ? '金叉' : diagnosis.macd.dead_cross ? '死叉' : diagnosis.macd.trending }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">零轴</span><span class="kv-val">{{ diagnosis.macd.above_zero ? '上方 ✅' : '下方 ⚠️' }}</span></div>
          </div>
        </div>

        <!-- BOLL -->
        <div class="metric-card">
          <div class="card-title">📊 BOLL 通道</div>
          <div class="card-body">
            <div class="kv-row"><span class="kv-key">上轨</span><span class="kv-val">{{ diagnosis.boll.upper }}</span></div>
            <div class="kv-row"><span class="kv-key">中轨</span><span class="kv-val">{{ diagnosis.boll.mid }}</span></div>
            <div class="kv-row"><span class="kv-key">下轨</span><span class="kv-val">{{ diagnosis.boll.lower }}</span></div>
            <div class="kv-row">
              <span class="kv-key">位置</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.boll.position === 'lower', 'tag-red': diagnosis.boll.position === 'upper' }">
                {{ diagnosis.boll.position === 'upper' ? '🔴 上沿（超买）' : diagnosis.boll.position === 'lower' ? '🟢 下沿（超卖）' : '🟡 中部' }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">%B</span><span class="kv-val">{{ diagnosis.boll.percent_b }}</span></div>
            <div class="kv-row"><span class="kv-key">带宽</span><span class="kv-val">{{ diagnosis.boll.width }}</span></div>
          </div>
        </div>

        <!-- 均线 -->
        <div class="metric-card">
          <div class="card-title">📉 均线系统</div>
          <div class="card-body">
            <div class="kv-row"><span class="kv-key">MA5</span><span class="kv-val">{{ diagnosis.moving_averages.ma5 }}</span></div>
            <div class="kv-row"><span class="kv-key">MA10</span><span class="kv-val">{{ diagnosis.moving_averages.ma10 }}</span></div>
            <div class="kv-row"><span class="kv-key">MA20</span><span class="kv-val">{{ diagnosis.moving_averages.ma20 }}</span></div>
            <div class="kv-row"><span class="kv-key">MA60</span><span class="kv-val">{{ diagnosis.moving_averages.ma60 }}</span></div>
            <div class="kv-row">
              <span class="kv-key">排列</span>
              <span class="tag" :class="diagnosis.moving_averages.bullish_arrangement ? 'tag-green' : diagnosis.moving_averages.bearish_arrangement ? 'tag-red' : ''">
                {{ diagnosis.moving_averages.bullish_arrangement ? '多头排列 ✅' : diagnosis.moving_averages.bearish_arrangement ? '空头排列 ⚠️' : '纠缠' }}
              </span>
            </div>
          </div>
        </div>

        <!-- 成交量 -->
        <div class="metric-card">
          <div class="card-title">📊 成交量</div>
          <div class="card-body">
            <div class="kv-row"><span class="kv-key">量比</span><span class="kv-val">{{ diagnosis.volume.ratio }}</span></div>
            <div class="kv-row">
              <span class="kv-key">状态</span>
              <span class="tag" :class="diagnosis.volume.expanding ? 'tag-orange' : diagnosis.volume.contracting ? 'tag-blue' : ''">
                {{ diagnosis.volume.expanding ? '🔥 放量' : diagnosis.volume.contracting ? '😶 缩量' : '→ 平稳' }}
              </span>
            </div>
            <div class="vol-tip">
              <template v-if="diagnosis.volume.expanding">放量可能意味趋势加速，需结合价格方向判断</template>
              <template v-else-if="diagnosis.volume.contracting">缩量通常表示观望情绪，等待方向选择</template>
              <template v-else>量能平稳，市场处于常态</template>
            </div>
          </div>
        </div>

        <!-- KDJ -->
        <div class="metric-card">
          <div class="card-title">📈 KDJ 指标</div>
          <div class="card-body">
            <div class="kv-row"><span class="kv-key">K值</span><span class="kv-val">{{ diagnosis.kdj.k }}</span></div>
            <div class="kv-row"><span class="kv-key">D值</span><span class="kv-val">{{ diagnosis.kdj.d }}</span></div>
            <div class="kv-row"><span class="kv-key">J值</span><span class="kv-val" :class="diagnosis.kdj.j > 100 ? 'sell' : diagnosis.kdj.j < 0 ? 'buy' : ''">{{ diagnosis.kdj.j }}</span></div>
            <div class="kv-row">
              <span class="kv-key">状态</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.kdj.golden_cross, 'tag-red': diagnosis.kdj.dead_cross }">
                {{ diagnosis.kdj.golden_cross ? '金叉 ✅' : diagnosis.kdj.dead_cross ? '死叉 ⚠️' : diagnosis.kdj.position }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">区域</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.kdj.oversold, 'tag-red': diagnosis.kdj.overbought }">
                {{ diagnosis.kdj.oversold ? '🟢 超卖区' : diagnosis.kdj.overbought ? '🔴 超买区' : '🟡 中性区' }}
              </span>
            </div>
          </div>
        </div>

        <!-- RSI -->
        <div class="metric-card">
          <div class="card-title">📊 RSI 指标</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">RSI(14)</span>
              <span class="kv-val" :class="diagnosis.rsi.overbought ? 'sell' : diagnosis.rsi.oversold ? 'buy' : ''">{{ diagnosis.rsi.value }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">状态</span>
              <span class="tag" :class="{ 'tag-red': diagnosis.rsi.overbought, 'tag-green': diagnosis.rsi.oversold }">
                {{ diagnosis.rsi.position }}
              </span>
            </div>
            <div class="vol-tip">
              <template v-if="diagnosis.rsi.overbought">RSI > 70，市场过热，注意回调风险</template>
              <template v-else-if="diagnosis.rsi.oversold">RSI < 30，市场超卖，可能有反弹机会</template>
              <template v-else>RSI 处于中性区间，趋势不明朗</template>
            </div>
          </div>
        </div>

        <!-- ADX 趋势强度 -->
        <div class="metric-card">
          <div class="card-title">📐 ADX 趋势强度</div>
          <div class="card-body">
            <div class="kv-row"><span class="kv-key">ADX</span><span class="kv-val">{{ diagnosis.adx.adx }}</span></div>
            <div class="kv-row"><span class="kv-key">方向</span>
              <span class="tag" :class="diagnosis.adx.trend_direction === 'up' ? 'tag-green' : 'tag-red'">
                {{ diagnosis.adx.trend_direction === 'up' ? '📈 上升' : '📉 下降' }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">强度</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.adx.level === 'very_strong', 'tag-orange': diagnosis.adx.level === 'medium', 'tag-blue': diagnosis.adx.level === 'none' }">
                {{ diagnosis.adx.strength }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">+DI/-DI</span><span class="kv-val">{{ diagnosis.adx.pdi }} / {{ diagnosis.adx.mdi }}</span></div>
            <div class="vol-tip">
              <template v-if="diagnosis.adx.level === 'none' || diagnosis.adx.level === 'weak'">ADX 无趋势信号，市场震荡，不宜追涨杀跌</template>
              <template v-else-if="diagnosis.adx.level === 'strong' || diagnosis.adx.level === 'very_strong'">趋势明确（{{ diagnosis.adx.strength }}），可顺势操作</template>
              <template v-else>趋势中等，需谨慎判断方向</template>
            </div>
          </div>
        </div>

        <!-- OBV 能量潮 -->
        <div class="metric-card">
          <div class="card-title">💧 OBV 能量潮</div>
          <div class="card-body">
            <div class="kv-row"><span class="kv-key">OBV</span><span class="kv-val">{{ diagnosis.obv.value }}</span></div>
            <div class="kv-row"><span class="kv-key">20日均线</span><span class="kv-val">{{ diagnosis.obv.ma20 }}</span></div>
            <div class="kv-row">
              <span class="kv-key">趋势</span>
              <span class="tag" :class="diagnosis.obv.trending_up ? 'tag-green' : diagnosis.obv.trending_down ? 'tag-red' : 'tag-blue'">
                {{ diagnosis.obv.trending_up ? '📈 资金流入' : diagnosis.obv.trending_down ? '📉 资金流出' : '→ 横盘' }}
              </span>
            </div>
            <div v-if="diagnosis.obv.divergence_with_price !== 'none'" class="kv-row">
              <span class="kv-key">量价背离</span>
              <span class="tag" :class="diagnosis.obv.divergence_with_price === 'bullish' ? 'tag-green' : 'tag-red'">
                {{ diagnosis.obv.divergence_with_price === 'bullish' ? '🟢 底背离（看涨）' : '🔴 顶背离（看跌）' }}
              </span>
            </div>
            <div class="vol-tip">
              <template v-if="diagnosis.obv.divergence_with_price === 'bullish'">OBV与价格底背离，资金暗中流入，潜在买点</template>
              <template v-else-if="diagnosis.obv.divergence_with_price === 'bearish'">OBV与价格顶背离，资金暗中流出，注意风险</template>
              <template v-else>量能跟随价格，趋势健康</template>
            </div>
          </div>
        </div>

        <!-- Fibonacci 回撤位 -->
        <div class="metric-card">
          <div class="card-title">🌀 Fibonacci 回撤位 (120日)</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">当前位置</span>
              <span class="kv-val" :class="diagnosis.fibonacci.position < 0.2 ? 'buy' : diagnosis.fibonacci.position > 0.8 ? 'sell' : ''">
                {{ (diagnosis.fibonacci.position * 100).toFixed(1) }}%
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">周期高点</span><span class="kv-val">{{ diagnosis.fibonacci.period_high }}</span></div>
            <div class="kv-row"><span class="kv-key">周期低点</span><span class="kv-val">{{ diagnosis.fibonacci.period_low }}</span></div>
            <div v-for="(val, key) in diagnosis.fibonacci.levels" :key="key" class="kv-row">
              <span class="kv-key">{{ key }}</span>
              <span class="kv-val">{{ val }}</span>
            </div>
            <div class="vol-tip">
              <template v-if="diagnosis.fibonacci.position < 0.2">价格接近周期低点，斐波那契支撑强劲</template>
              <template v-else-if="diagnosis.fibonacci.position > 0.8">价格接近周期高点，注意回调风险</template>
              <template v-else>价格在回撤位中间区域，等待方向选择</template>
            </div>
          </div>
        </div>

        <!-- 背离检测 -->
        <div class="metric-card" v-if="diagnosis.divergence.has_divergence">
          <div class="card-title">⚠️ 指标背离</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">主导方向</span>
              <span class="tag" :class="diagnosis.divergence.dominant === 'bullish' ? 'tag-green' : 'tag-red'">
                {{ diagnosis.divergence.dominant === 'bullish' ? '🟢 底背离（看涨）' : '🔴 顶背离（看跌）' }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">强度</span><span class="kv-val">{{ diagnosis.divergence.strength }}</span></div>
            <div class="kv-row" v-if="diagnosis.divergence.macd.type !== 'none'">
              <span class="kv-key">MACD</span>
              <span class="tag" :class="diagnosis.divergence.macd.type === 'bullish' ? 'tag-green' : 'tag-red'">
                {{ diagnosis.divergence.macd.type === 'bullish' ? '底背离' : '顶背离' }}
              </span>
            </div>
            <div class="kv-row" v-if="diagnosis.divergence.kdj.type !== 'none'">
              <span class="kv-key">KDJ</span>
              <span class="tag" :class="diagnosis.divergence.kdj.type === 'bullish' ? 'tag-green' : 'tag-red'">
                {{ diagnosis.divergence.kdj.type === 'bullish' ? '底背离' : '顶背离' }}
              </span>
            </div>
            <div class="kv-row" v-if="diagnosis.divergence.rsi.type !== 'none'">
              <span class="kv-key">RSI</span>
              <span class="tag" :class="diagnosis.divergence.rsi.type === 'bullish' ? 'tag-green' : 'tag-red'">
                {{ diagnosis.divergence.rsi.type === 'bullish' ? '底背离' : '顶背离' }}
              </span>
            </div>
            <div class="vol-tip">
              多指标同时背离时信号更强，建议结合缠论买卖点综合判断
            </div>
          </div>
        </div>

        <!-- K线形态 -->
        <div class="metric-card" v-if="diagnosis.candlestick.signal !== 'none' && diagnosis.candlestick.signal !== 'neutral'">
          <div class="card-title">🕯️ K线形态</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">综合信号</span>
              <span class="tag" :class="diagnosis.candlestick.signal === 'bullish' ? 'tag-green' : 'tag-red'">
                {{ diagnosis.candlestick.signal === 'bullish' ? '🟢 看涨形态' : '🔴 看跌形态' }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">强度</span><span class="kv-val">{{ diagnosis.candlestick.strength }}</span></div>
            <div v-for="p in diagnosis.candlestick.recent_patterns" :key="p.bar_index" class="kv-row">
              <span class="kv-key">{{ patternLabel(p.type) }}</span>
              <span class="tag" :class="p.bullish ? 'tag-green' : 'tag-red'">
                {{ p.bullish ? '看涨' : '看跌' }}
              </span>
            </div>
          </div>
        </div>

        <!-- 仓位建议 -->
        <div class="metric-card position-card">
          <div class="card-title">💼 仓位建议</div>
          <div class="card-body">
            <div class="position-main">
              <div class="position-pct" :style="{ color: diagnosis.position_suggestion.position_pct >= 60 ? '#22c55e' : diagnosis.position_suggestion.position_pct >= 40 ? '#f59e0b' : '#ef4444' }">
                {{ diagnosis.position_suggestion.position_pct }}%
              </div>
              <div class="position-label">{{ diagnosis.position_suggestion.suggestion }}</div>
            </div>
            <div class="kv-row">
              <span class="kv-key">风险等级</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.position_suggestion.risk_level === '低风险', 'tag-orange': diagnosis.position_suggestion.risk_level === '中等风险', 'tag-red': diagnosis.position_suggestion.risk_level === '高风险' }">
                {{ diagnosis.position_suggestion.risk_level }}
              </span>
            </div>
            <div class="position-notes">{{ diagnosis.position_suggestion.notes }}</div>
          </div>
        </div>

        <!-- 止损止盈 & 风险 -->
        <div class="metric-card risk-card">
          <div class="card-title">🛡️ 风控建议</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">波动率</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.risk.volatility_level === 'low', 'tag-orange': diagnosis.risk.volatility_level === 'medium', 'tag-red': diagnosis.risk.volatility_level === 'high' }">
                {{ diagnosis.risk.volatility_label }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">ATR(14)</span><span class="kv-val">{{ diagnosis.risk.atr }}</span></div>
            <div class="divider"></div>
            <div class="kv-row highlight-row">
              <span class="kv-key">🛑 止损价</span>
              <span class="kv-val sell">{{ diagnosis.risk.stop_loss_price }} <small>(-{{ diagnosis.risk.stop_loss_pct }}%)</small></span>
            </div>
            <div class="kv-row highlight-row">
              <span class="kv-key">🎯 止盈价</span>
              <span class="kv-val buy">{{ diagnosis.risk.take_profit_price }} <small>(+{{ diagnosis.risk.take_profit_pct }}%)</small></span>
            </div>
            <div class="kv-row"><span class="kv-key">风险收益比</span><span class="kv-val">1 : {{ diagnosis.risk.risk_reward_ratio }}</span></div>
            <div class="divider"></div>
            <div class="kv-row"><span class="kv-key">支撑位 S1</span><span class="kv-val">{{ diagnosis.risk.support_1 }}</span></div>
            <div class="kv-row"><span class="kv-key">阻力位 R1</span><span class="kv-val">{{ diagnosis.risk.resistance_1 }}</span></div>
          </div>
        </div>

        <!-- 操作建议汇总 -->
        <div class="metric-card tip-card">
          <div class="card-title">💡 决策建议</div>
          <div class="card-body">
            <div class="tip-summary">{{ diagnosis.reason }}</div>
            <div class="tip-actions">
              <button class="primary small" @click="router.push({ path: '/chanlun', query: { symbol: code, market } })">
                🧧 深入缠论分析
              </button>
              <button class="ghost small" @click="router.push({ path: '/', query: { symbol: code, category: 'DAY' } })">
                📈 回测验证
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- K 线图 -->
      <div class="chart-section" v-if="bars.length > 0">
        <div class="section-title">最近 K 线走势</div>
        <div class="chart-wrap">
          <KlineChart :bars="bars.slice(-120)" :trades="[]" />
        </div>
      </div>
    </template>

    <!-- 错误 -->
    <div v-else class="state-center error-state">
      <p>⚠️ {{ error }}</p>
      <button class="ghost" @click="runDiagnosis">重试</button>
    </div>
  </div>
</template>

<style scoped>
.diagnosis-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 20px 16px;
}

/* 输入栏 */
.input-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.input-group {
  display: flex;
  gap: 8px;
  align-items: center;
}
.market-select {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
}
.code-input {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 12px;
  font-size: 14px;
  color: var(--text);
  width: 120px;
  font-family: var(--font-mono);
}
.code-input:focus { outline: none; border-color: var(--accent); }
.error-msg { color: #ef4444; font-size: 13px; }

/* 加载/空状态 */
.state-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  color: var(--text-dim);
  gap: 16px;
}
.error-state p { color: #ef4444; }
.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* 大卡：分数 + 操作建议 */
.hero-card {
  display: flex;
  align-items: center;
  gap: 24px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  border-top: 4px solid var(--accent);
  padding: 24px;
  margin-bottom: 20px;
}
.hero-left { flex-shrink: 0; }
.score-ring {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  border: 4px solid var(--accent);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,0.2);
}
.score-num {
  font-size: 32px;
  font-weight: 800;
  line-height: 1;
}
.score-unit {
  font-size: 12px;
  color: var(--text-dim);
}
.hero-right { flex: 1; }
.action-badge {
  display: inline-block;
  padding: 4px 16px;
  border-radius: 20px;
  color: #fff;
  font-size: 15px;
  font-weight: 700;
  margin-bottom: 8px;
}
.action-reason {
  font-size: 14px;
  color: var(--text);
  line-height: 1.6;
  margin-bottom: 8px;
}
.meta-info {
  font-size: 12px;
  color: var(--text-dim);
  display: flex;
  gap: 6px;
  align-items: center;
}
.meta-info .sep { opacity: 0.5; }

/* 六维网格 */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}
.metric-card {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}
.card-title {
  font-size: 13px;
  font-weight: 600;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: rgba(255,255,255,0.03);
}
.card-body {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.kv-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}
.kv-key { color: var(--text-dim); }
.kv-val { font-family: var(--font-mono); font-weight: 600; color: var(--text); }
.kv-row.highlight .kv-val.buy { color: #22c55e; }
.kv-row.highlight .kv-val.sell { color: #ef4444; }
.kv-val.up { color: #22c55e; }
.kv-val.down { color: #ef4444; }

/* 标签 */
.tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 600;
}
.tag-green { background: rgba(34,197,94,0.15); color: #22c55e; }
.tag-red { background: rgba(239,68,68,0.15); color: #ef4444; }
.tag-blue { background: rgba(59,130,246,0.15); color: #60a5fa; }
.tag-orange { background: rgba(249,115,22,0.15); color: #f97316; }

/* 最新买卖点 */
.latest-mmd {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 6px;
  border-top: 1px dashed var(--border);
  margin-top: 2px;
}
.mmd-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 700;
  font-family: var(--font-mono);
}
.mmd-tag.buy { background: rgba(34,197,94,0.2); color: #22c55e; }
.mmd-tag.sell { background: rgba(239,68,68,0.2); color: #ef4444; }
.mmd-conf { font-size: 11px; color: var(--text-dim); }
.mmd-quality { font-size: 11px; margin-left: 8px; padding: 1px 6px; border-radius: 4px; font-weight: 600; }
.mmd-quality.grade-S { background: rgba(234,179,8,0.2); color: #eab308; }
.mmd-quality.grade-A { background: rgba(34,197,94,0.2); color: #22c55e; }
.mmd-quality.grade-B { background: rgba(59,130,246,0.2); color: #3b82f6; }
.mmd-quality.grade-C { background: rgba(249,115,22,0.2); color: #f97316; }
.mmd-quality.grade-D { background: rgba(239,68,68,0.2); color: #ef4444; }
.recent-signals { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); }
.section-label { font-size: 11px; color: var(--text-dim); margin-bottom: 6px; }
.signal-list { display: flex; flex-wrap: wrap; gap: 6px; }
.signal-item { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 4px; font-size: 12px; background: var(--bg-elevated); }
.signal-item.buy { border-left: 2px solid #22c55e; }
.signal-item.sell { border-left: 2px solid #ef4444; }
.sig-conf { font-size: 10px; color: var(--text-dim); }
.sig-grade { font-size: 10px; font-weight: 700; padding: 0 4px; border-radius: 3px; }
.sig-grade.grade-S { background: rgba(234,179,8,0.2); color: #eab308; }
.sig-grade.grade-A { background: rgba(34,197,94,0.2); color: #22c55e; }
.sig-grade.grade-B { background: rgba(59,130,246,0.2); color: #3b82f6; }
.sig-grade.grade-C { background: rgba(249,115,22,0.2); color: #f97316; }
.sig-grade.grade-D { background: rgba(239,68,68,0.2); color: #ef4444; }

/* 成交量提示 */
.vol-tip {
  font-size: 11px;
  color: var(--text-dim);
  line-height: 1.5;
  padding-top: 4px;
  border-top: 1px dashed var(--border);
  margin-top: 2px;
}

/* 风控卡片 */
.risk-card .divider {
  height: 1px;
  background: var(--border);
  margin: 4px 0;
}
.risk-card .highlight-row {
  font-size: 14px;
}
.risk-card .kv-val small {
  font-size: 11px;
  opacity: 0.7;
  margin-left: 4px;
}

/* 仓位建议卡 */
.position-card .position-main {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.position-card .position-pct {
  font-size: 32px;
  font-weight: 800;
  line-height: 1;
}
.position-card .position-label {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
}
.position-card .position-notes {
  font-size: 11px;
  color: var(--text-dim);
  line-height: 1.5;
  padding-top: 6px;
  border-top: 1px dashed var(--border);
  margin-top: 4px;
}
.tip-card .tip-summary {
  font-size: 13px;
  color: var(--text);
  line-height: 1.6;
  margin-bottom: 10px;
}
.tip-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.small {
  font-size: 12px;
  padding: 5px 12px;
}

/* K线图 */
.chart-section {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px;
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text);
}
.chart-wrap {
  height: 360px;
}
</style>
