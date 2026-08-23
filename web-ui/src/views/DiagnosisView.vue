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

function getPositionTagClass(positionPct: number): string {
  if (positionPct >= 60) return 'tag tag-green'
  if (positionPct >= 40) return 'tag tag-blue'
  if (positionPct >= 20) return 'tag tag-orange'
  return 'tag tag-red'
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
            <!-- V12: 多时间框架共振评分 -->
            <div v-if="diagnosis.chanlun.confluence_score != null" class="confluence-row">
              <span class="kv-key">🔗 共振评分</span>
              <span class="kv-val" :class="diagnosis.chanlun.confluence_score >= 0.7 ? 'buy' : diagnosis.chanlun.confluence_score >= 0.5 ? 'hold' : 'sell'">
                {{ (diagnosis.chanlun.confluence_score * 100).toFixed(0) }}分
              </span>
            </div>
            <!-- V13: 成交量剖面 -->
            <div v-if="diagnosis.chanlun.volume_profile" class="vol-profile-row">
              <span class="kv-key">📊 成交量支撑</span>
              <span class="kv-val">{{ diagnosis.chanlun.volume_profile.support ?? '无' }}</span>
              <span class="kv-key">📊 成交量阻力</span>
              <span class="kv-val">{{ diagnosis.chanlun.volume_profile.resistance ?? '无' }}</span>
              <span class="kv-key">位置分位</span>
              <span class="kv-val">{{ (diagnosis.chanlun.volume_profile.current_rank * 100).toFixed(0) }}%</span>
            </div>
            <!-- V7: 信号质量报告 -->
            <div v-if="diagnosis.chanlun.signal_report" class="signal-report">
              <div class="section-label">📋 信号质量报告</div>
              <div class="kv-row"><span class="kv-key">建议入场价</span><span class="kv-val buy">{{ diagnosis.chanlun.signal_report.entry_price }}</span></div>
              <div class="kv-row"><span class="kv-key">止损价</span><span class="kv-val sell">{{ diagnosis.chanlun.signal_report.stop_loss }}</span></div>
              <div v-if="diagnosis.chanlun.signal_report.dynamic_stop && diagnosis.chanlun.signal_report.dynamic_stop !== diagnosis.chanlun.signal_report.stop_loss" class="kv-row">
                <span class="kv-key">动态止损</span><span class="kv-val" style="color:#22c55e">{{ diagnosis.chanlun.signal_report.dynamic_stop }}</span>
                <small style="color:var(--text-dim);font-size:10px">（成交量支撑位）</small>
              </div>
              <div class="kv-row"><span class="kv-key">第一止盈</span><span class="kv-val buy">{{ diagnosis.chanlun.signal_report.take_profit_1 }}</span></div>
              <div class="kv-row"><span class="kv-key">风险收益比</span><span class="kv-val">1 : {{ diagnosis.chanlun.signal_report.risk_reward_ratio }}</span></div>
              <div class="kv-row"><span class="kv-key">信号强度</span><span class="kv-val">{{ ((diagnosis.chanlun.signal_report?.signal_strength ?? 0) * 100).toFixed(0) }}%</span></div>
              <div class="kv-note">{{ diagnosis.chanlun.signal_report.entry_reason }}</div>
              <div class="kv-note risk-note">{{ diagnosis.chanlun.signal_report.risk_notes }}</div>
              <!-- V14: 信号增强注释 -->
              <div v-if="diagnosis.chanlun.signal_report.enhancement_notes && diagnosis.chanlun.signal_report.enhancement_notes.length > 0" class="enhancement-notes">
                <div class="section-label" style="font-size:11px;color:var(--text-dim)">🔬 信号增强确认</div>
                <div v-for="note in diagnosis.chanlun.signal_report.enhancement_notes" :key="note" class="enhancement-tag">✅ {{ note }}</div>
              </div>
              <!-- V15: K线形态确认 -->
              <div v-if="diagnosis.chanlun.signal_report.kline_pattern" class="kline-pattern-row">
                <span class="kv-key">🕯️ K线形态</span>
                <span class="tag tag-green">{{ {hammer:'锤子线✅',bullish_engulfing:'阳吞没✅',doji:'十字星⚠️',bearish_engulfing:'阴吞没⚠️'}[diagnosis.chanlun.signal_report.kline_pattern] || diagnosis.chanlun.signal_report.kline_pattern }}</span>
              </div>
              <!-- V15: 信号衰减提示 -->
              <div v-if="diagnosis.chanlun.signal_report.signal_aging" class="aging-row">
                <span class="kv-key">⏱️ 信号时效</span>
                <span :class="diagnosis.chanlun.signal_report.signal_aging.aged ? 'tag tag-red' : 'tag tag-blue'">
                  {{ diagnosis.chanlun.signal_report.signal_aging.aged
                    ? `已衰减(${diagnosis.chanlun.signal_report.signal_aging.age_bars}根K线)`
                    : `新鲜(${diagnosis.chanlun.signal_report.signal_aging.age_bars}根)` }}
                </span>
                <small style="color:var(--text-dim);font-size:10px">衰减系数 {{ diagnosis.chanlun.signal_report.signal_aging.decay_factor }}</small>
              </div>
              <!-- V16: 仓位建议 -->
              <div v-if="diagnosis.chanlun.signal_report.position_sizing" class="position-sizing-row">
                <span class="kv-key">💼 仓位建议</span>
                <span :class="getPositionTagClass(diagnosis.chanlun.signal_report.position_sizing.position_pct)">
                  {{ diagnosis.chanlun.signal_report.position_sizing.suggestion }}
                  ({{ diagnosis.chanlun.signal_report.position_sizing.position_pct }}%)
                </span>
                <small style="color:var(--text-dim);font-size:10px">{{ diagnosis.chanlun.signal_report.position_sizing.risk_level }}</small>
              </div>
              <div v-if="diagnosis.chanlun.signal_report.position_sizing && diagnosis.chanlun.signal_report.position_sizing.notes.length > 0" class="position-notes">
                <div v-for="note in diagnosis.chanlun.signal_report.position_sizing.notes" :key="note" class="position-note-tag">📌 {{ note }}</div>
              </div>
            </div>
            <!-- V21: 决策辅助输出 -->
            <div v-if="diagnosis.chanlun.decision_recommendation" class="signal-report decision-rec">
              <div class="section-label">🎯 决策辅助（V21）</div>
              <div class="kv-row">
                <span class="kv-key">操作建议</span>
                <span :class="{'tag tag-green': diagnosis.chanlun.decision_recommendation.action==='buy', 'tag tag-red': diagnosis.chanlun.decision_recommendation.action==='sell', 'tag tag-yellow': diagnosis.chanlun.decision_recommendation.action==='hold'}">
                  {{ {buy:'买入',sell:'卖出',hold:'观望'}[diagnosis.chanlun.decision_recommendation.action] }}
                </span>
                <span class="kv-val" style="margin-left:auto">{{ diagnosis.chanlun.decision_recommendation.confidence_label }}置信度</span>
              </div>
              <div class="kv-row"><span class="kv-key">建议入场价</span><span class="kv-val buy">{{ diagnosis.chanlun.decision_recommendation.entry_price }}</span></div>
              <div class="kv-row"><span class="kv-key">止损价</span><span class="kv-val sell">{{ diagnosis.chanlun.decision_recommendation.stop_loss }}</span></div>
              <div class="kv-row"><span class="kv-key">止盈1 / 止盈2</span><span class="kv-val buy">{{ diagnosis.chanlun.decision_recommendation.take_profit_1 }} / {{ diagnosis.chanlun.decision_recommendation.take_profit_2 }}</span></div>
              <div class="kv-row"><span class="kv-key">关键支撑 / 阻力</span><span class="kv-val">{{ diagnosis.chanlun.decision_recommendation.key_support }} / {{ diagnosis.chanlun.decision_recommendation.key_resistance }}</span></div>
              <div class="kv-row"><span class="kv-key">风险收益比</span><span class="kv-val">1 : {{ diagnosis.chanlun.decision_recommendation.risk_reward_ratio }}</span></div>
              <div class="kv-row">
                <span class="kv-key">建议仓位</span>
                <span :class="getPositionTagClass((diagnosis.chanlun.decision_recommendation?.position_pct ?? 0)*100)">
                  {{ ((diagnosis.chanlun.decision_recommendation?.position_pct ?? 0) * 100).toFixed(0) }}%
                </span>
              </div>
              <div class="kv-note" style="font-weight:600;color:var(--text-primary)">{{ diagnosis.chanlun.decision_recommendation.recommendation_text }}</div>
              <div v-if="diagnosis.chanlun.decision_recommendation.warnings && diagnosis.chanlun.decision_recommendation.warnings.length > 0" class="enhancement-notes">
                <div class="section-label" style="font-size:11px;color:var(--text-dim)">⚠️ 风险提示</div>
                <div v-for="w in diagnosis.chanlun.decision_recommendation.warnings" :key="w" class="enhancement-tag tag tag-yellow">{{ w }}</div>
              </div>
            </div>
            <!-- V21: 组合信号 -->
            <div v-if="diagnosis.chanlun.combo_signal && diagnosis.chanlun.combo_signal.type && diagnosis.chanlun.combo_signal.type !== 'none'" class="signal-report combo-signal">
              <div class="section-label">🔗 组合信号（V21）</div>
              <div class="kv-row">
                <span class="kv-key">组合类型</span>
                <span class="tag tag-green">{{ diagnosis.chanlun.combo_signal.type }}</span>
                <span class="kv-val" style="margin-left:auto;color:#22c55e">+{{ (diagnosis.chanlun.combo_signal.bonus*100).toFixed(0) }}% 置信度加成</span>
              </div>
            </div>
            <!-- V22: 波动率双重确认 -->
            <div v-if="diagnosis.chanlun.vol_regime_dual && diagnosis.chanlun.vol_regime_dual.dual_confirmed" class="signal-report vol-dual">
              <div class="section-label">📊 波动率双重确认（V22）</div>
              <div class="kv-row">
                <span class="kv-key">波动率Regime</span>
                <span class="tag" :class="{'tag-red': diagnosis.chanlun.vol_regime_dual.regime==='high', 'tag-green': diagnosis.chanlun.vol_regime_dual.regime==='low', 'tag-yellow': diagnosis.chanlun.vol_regime_dual.regime==='medium'}">
                  {{ {high:'高波动',low:'低波动',medium:'正常'}[diagnosis.chanlun.vol_regime_dual.regime] }}
                </span>
                <span class="kv-key" style="margin-left:12px">价格行为</span>
                <span class="tag" :class="{'tag-red': diagnosis.chanlun.vol_regime_dual.price_action==='volatile', 'tag-green': diagnosis.chanlun.vol_regime_dual.price_action==='calm', 'tag-yellow': diagnosis.chanlun.vol_regime_dual.price_action==='normal'}">
                  {{ {volatile:'剧烈震荡',calm:'平稳',normal:'正常'}[diagnosis.chanlun.vol_regime_dual.price_action] }}
                </span>
              </div>
              <div class="kv-row">
                <span class="kv-key">双重确认</span>
                <span class="tag tag-green">✅ 已确认</span>
                <span class="kv-val" :style="{ marginLeft: 'auto', color: diagnosis.chanlun.vol_regime_dual.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                  {{ diagnosis.chanlun.vol_regime_dual.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.vol_regime_dual.confidence_adjust*100).toFixed(0) }}% 置信度调整
                </span>
              </div>
            </div>
            <!-- V22: 量价背离 -->
            <div v-if="diagnosis.chanlun.vol_price_divergence && diagnosis.chanlun.vol_price_divergence.type !== 'none'" class="signal-report vol-div">
              <div class="section-label">📈 量价背离检测（V22）</div>
              <div class="kv-row">
                <span class="kv-key">背离类型</span>
                <span :class="{'tag tag-red': diagnosis.chanlun.vol_price_divergence.type==='bearish_divergence', 'tag tag-green': diagnosis.chanlun.vol_price_divergence.type==='bullish_divergence', 'tag tag-blue': diagnosis.chanlun.vol_price_divergence.type==='confirmed_up', 'tag tag-yellow': diagnosis.chanlun.vol_price_divergence.type==='confirmed_down'}">
                  {{ diagnosis.chanlun.vol_price_divergence.signal }}
                </span>
                <span class="kv-val" style="margin-left:auto">强度 {{ (diagnosis.chanlun.vol_price_divergence.strength*100).toFixed(0) }}%</span>
              </div>
              <div class="kv-note">{{ diagnosis.chanlun.vol_price_divergence.description }}</div>
            </div>
            <!-- V23: Fibonacci回撤位确认 -->
            <div v-if="diagnosis.chanlun.fib_retracement && diagnosis.chanlun.fib_retracement.confirmation_bonus > 0" class="signal-report fib-retr">
              <div class="section-label">🔢 Fibonacci回撤位确认（V23）</div>
              <div class="kv-row">
                <span class="kv-key">最近回撤位</span>
                <span class="tag" :class="diagnosis.chanlun.fib_retracement.is_key_level ? 'tag-green' : 'tag-yellow'">
                  {{ diagnosis.chanlun.fib_retracement.near_fib_level || '未知' }}
                  {{ diagnosis.chanlun.fib_retracement.is_key_level ? '⭐ 关键位' : '' }}
                </span>
                <span class="kv-val" style="margin-left:auto">距离 {{ diagnosis.chanlun.fib_retracement.distance_to_level }}%</span>
              </div>
              <div class="kv-row">
                <span class="kv-key">回撤比例</span>
                <span class="kv-val">{{ diagnosis.chanlun.fib_retracement.fib_ratio }}</span>
                <span class="kv-val" :style="{ marginLeft: 'auto', color: '#22c55e' }">
                  +{{ (diagnosis.chanlun.fib_retracement.confirmation_bonus*100).toFixed(0) }}% 置信度加成
                </span>
              </div>
            </div>
            <!-- V23: RSI区域分类 -->
            <div v-if="diagnosis.chanlun.rsi_zone" class="signal-report rsi-zone">
              <div class="section-label">📊 RSI区域分类（V23）</div>
              <div class="kv-row">
                <span class="kv-key">RSI值</span>
                <span class="kv-val">{{ diagnosis.chanlun.rsi_zone.rsi }}</span>
                <span class="tag" :class="{
                  'tag-green': ['super_oversold','oversold','weak'].includes(diagnosis.chanlun.rsi_zone.zone),
                  'tag-yellow': diagnosis.chanlun.rsi_zone.zone === 'neutral',
                  'tag-red': ['slightly_overbought','overbought','super_overbought'].includes(diagnosis.chanlun.rsi_zone.zone),
                }">
                  {{ {super_oversold:'极强超卖',oversold:'超卖',weak:'弱势',neutral:'中性',slightly_overbought:'偏强',overbought:'超买',super_overbought:'极强超买'}[diagnosis.chanlun.rsi_zone.zone] || diagnosis.chanlun.rsi_zone.zone }}
                </span>
              </div>
            </div>
            <!-- V23: MACD零轴穿越确认 -->
            <div v-if="diagnosis.chanlun.macd_zero_cross && diagnosis.chanlun.macd_zero_cross.confidence_bonus > 0" class="signal-report macd-zero">
              <div class="section-label">📉 MACD零轴穿越确认（V23）</div>
              <div class="kv-row">
                <span class="kv-key">穿越类型</span>
                <span class="tag" :class="{'tag-green': diagnosis.chanlun.macd_zero_cross.cross_type==='cross_above' || diagnosis.chanlun.macd_zero_cross.cross_type==='above', 'tag-red': diagnosis.chanlun.macd_zero_cross.cross_type==='cross_below' || diagnosis.chanlun.macd_zero_cross.cross_type==='below'}">
                  {{ {cross_above:'上穿零轴↑',cross_below:'下穿零轴↓',above:'零轴上方',below:'零轴下方'}[diagnosis.chanlun.macd_zero_cross.cross_type] || diagnosis.chanlun.macd_zero_cross.cross_type }}
                </span>
                <span class="kv-val" style="margin-left:auto">强度 {{ {strong:'强',moderate:'中',weak:'弱'}[diagnosis.chanlun.macd_zero_cross.strength] || diagnosis.chanlun.macd_zero_cross.strength }}</span>
              </div>
              <div class="kv-row">
                <span class="kv-key">距零轴距离</span>
                <span class="kv-val">{{ diagnosis.chanlun.macd_zero_cross.distance_to_zero }}</span>
                <span class="kv-val" style="color:#22c55e;margin-left:auto">
                  +{{ (diagnosis.chanlun.macd_zero_cross.confidence_bonus*100).toFixed(0) }}% 置信度加成
                </span>
              </div>
            </div>
            <!-- V25: 信号后确认验证 -->
            <div v-if="diagnosis.chanlun.post_signal_confirm" class="signal-report post-signal">
              <div class="section-label">✅ 信号后确认验证（V25）</div>
              <div class="kv-row">
                <span class="kv-key">确认状态</span>
                <span class="tag" :class="diagnosis.chanlun.post_signal_confirm.confirmed ? 'tag-green' : 'tag-yellow'">
                  {{ diagnosis.chanlun.post_signal_confirm.confirmed ? '已确认 ✅' : '未确认 ⚠️' }}
                </span>
                <span class="kv-val">观察 {{ diagnosis.chanlun.post_signal_confirm.bars_ahead }} 根K线</span>
              </div>
              <div class="kv-row">
                <span class="kv-key">价格变化</span>
                <span class="kv-val" :style="{ color: diagnosis.chanlun.post_signal_confirm.price_change_pct > 0 ? '#22c55e' : '#ef4444' }">
                  {{ diagnosis.chanlun.post_signal_confirm.price_change_pct > 0 ? '+' : '' }}{{ diagnosis.chanlun.post_signal_confirm.price_change_pct }}%
                </span>
                <span class="kv-val" style="margin-left:auto;color:#22c55e">
                  {{ diagnosis.chanlun.post_signal_confirm.confirmed ? '+' : '' }}{{ (diagnosis.chanlun.post_signal_confirm.confidence_bonus*100).toFixed(0) }}% 置信度加成
                </span>
              </div>
            </div>
            <!-- V25: 动量衰减预警 -->
            <div v-if="diagnosis.chanlun.momentum_decay && diagnosis.chanlun.momentum_decay.decay_detected" class="signal-report momentum-decay">
              <div class="section-label">⚠️ 动量衰减预警（V25）</div>
              <div class="kv-row">
                <span class="kv-key">衰减类型</span>
                <span class="tag tag-orange">{{ {bullish_decay:'买入后动量衰减',bearish_decay:'卖出后动量衰减'}[diagnosis.chanlun.momentum_decay.decay_type] || diagnosis.chanlun.momentum_decay.decay_type }}</span>
                <span class="kv-val">动量评分 {{ diagnosis.chanlun.momentum_decay.momentum_score }}</span>
              </div>
              <div class="kv-row">
                <span class="kv-val" style="color:#ef4444;margin-left:auto">
                  {{ diagnosis.chanlun.momentum_decay.confidence_penalty > 0 ? '+' : '' }}{{ (diagnosis.chanlun.momentum_decay.confidence_penalty*100).toFixed(0) }}% 置信度调整
                </span>
              </div>
            </div>
            <!-- V25: 波动率自适应过滤 -->
            <div v-if="diagnosis.chanlun.vol_regime_filter" class="signal-report vol-regime">
              <div class="section-label">🌊 波动率自适应过滤（V25）</div>
              <div class="kv-row">
                <span class="kv-key">波动率状态</span>
                <span class="tag" :class="{'tag-red': diagnosis.chanlun.vol_regime_filter.regime==='high', 'tag-green': diagnosis.chanlun.vol_regime_filter.regime==='low'}">
                  {{ {high:'高波动 🔴',medium:'正常 🟡',low:'低波动 🟢'}[diagnosis.chanlun.vol_regime_filter.regime] || diagnosis.chanlun.vol_regime_filter.regime }}
                </span>
                <span class="kv-val">阈值调整 {{ diagnosis.chanlun.vol_regime_filter.threshold_adjustment }}x</span>
              </div>
              <div class="kv-row">
                <span class="kv-key">过滤应用</span>
                <span class="tag" :class="diagnosis.chanlun.vol_regime_filter.filter_applied ? 'tag-yellow' : 'tag-gray'">
                  {{ diagnosis.chanlun.vol_regime_filter.filter_applied ? '已应用' : '未应用' }}
                </span>
                <span class="kv-val" :style="{ color: diagnosis.chanlun.vol_regime_filter.confidence_bonus > 0 ? '#22c55e' : '#ef4444' }">
                  {{ diagnosis.chanlun.vol_regime_filter.confidence_bonus > 0 ? '+' : '' }}{{ (diagnosis.chanlun.vol_regime_filter.confidence_bonus*100).toFixed(0) }}% 置信度调整
                </span>
              </div>
            </div>
            <!-- V25: 综合信号质量评分 -->
            <div v-if="diagnosis.chanlun.composite_quality" class="signal-report composite-quality">
              <div class="section-label">⭐ 综合信号质量评分（V25）</div>
              <div class="kv-row">
                <span class="kv-key">综合得分</span>
                <span class="kv-val" :style="{ fontSize:'18px', fontWeight:'bold', color: diagnosis.chanlun.composite_quality.grade==='S'?'#22c55e':diagnosis.chanlun.composite_quality.grade==='A'?'#4ade80':diagnosis.chanlun.composite_quality.grade==='B'?'#f59e0b':'#ef4444' }">
                  {{ diagnosis.chanlun.composite_quality.overall_score }}分
                </span>
                <span class="tag grade-tag grade-{{ diagnosis.chanlun.composite_quality.grade }}" :style="{ fontSize:'14px', padding:'2px 8px' }">
                  评级 {{ diagnosis.chanlun.composite_quality.grade }}
                </span>
              </div>
              <div class="kv-row" v-for="(val, key) in diagnosis.chanlun.composite_quality.breakdown" :key="key">
                <span class="kv-key" style="font-size:11px">{{ key }}</span>
                <span class="kv-val" style="font-size:11px">{{ val }}</span>
              </div>
              <div class="kv-note" style="margin-top:4px;font-weight:bold">
                {{ diagnosis.chanlun.composite_quality.recommendation }}
              </div>
            </div>

            <!-- V26: 信号历史验证 -->
            <div v-if="diagnosis.chanlun.signal_history" class="signal-report signal-history">
              <div class="section-label">📊 信号历史验证（V26）</div>
              <div class="kv-row">
                <span class="kv-key">历史准确率</span>
                <span class="kv-val" :style="{ color: diagnosis.chanlun.signal_history.historical_accuracy >= 0.6 ? '#22c55e' : '#f59e0b' }">
                  {{ (diagnosis.chanlun.signal_history.historical_accuracy * 100).toFixed(1) }}%
                </span>
                <span class="tag" :class="diagnosis.chanlun.signal_history.validation_passed ? 'tag-green' : 'tag-yellow'">
                  {{ diagnosis.chanlun.signal_history.validation_passed ? '通过✅' : '待观察⚠️' }}
                </span>
              </div>
              <div class="kv-row">
                <span class="kv-key">样本数量</span>
                <span class="kv-val">{{ diagnosis.chanlun.signal_history.sample_size }} 根K线</span>
              </div>
              <div class="kv-row">
                <span class="kv-key">置信度调整</span>
                <span class="kv-val" :style="{ color: diagnosis.chanlun.signal_history.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                  {{ diagnosis.chanlun.signal_history.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.signal_history.confidence_adjust * 100).toFixed(2) }}%
                </span>
              </div>
              <div class="kv-row">
                <span class="kv-key">近期趋势</span>
                <span class="kv-val" :style="{ color: diagnosis.chanlun.signal_history.recent_trend > 0 ? '#22c55e' : '#ef4444' }">
                  {{ diagnosis.chanlun.signal_history.recent_trend > 0 ? '上涨↑' : '下跌↓' }} ({{ (diagnosis.chanlun.signal_history.recent_trend * 100).toFixed(2) }}%)
                </span>
              </div>
              <div class="kv-row">
                <span class="kv-key">20日波动率</span>
                <span class="kv-val">{{ (diagnosis.chanlun.signal_history.volatility_20d * 100).toFixed(2) }}%</span>
              </div>
            </div>

            <!-- V26: 动态风险收益优化 -->
            <div v-if="diagnosis.chanlun.dynamic_rr_optimization" class="signal-report dynamic-rr">
              <div class="section-label">⚖️ 动态风险收益优化（V26）</div>
              <div class="kv-row">
                <span class="kv-key">止损价</span>
                <span class="kv-val tag-red">{{ diagnosis.chanlun.dynamic_rr_optimization.optimal_stop_loss }}</span>
                <span class="kv-key">第一止盈</span>
                <span class="kv-val tag-green">{{ diagnosis.chanlun.dynamic_rr_optimization.optimal_take_profit_1 }}</span>
              </div>
              <div class="kv-row">
                <span class="kv-key">第二止盈</span>
                <span class="kv-val tag-green">{{ diagnosis.chanlun.dynamic_rr_optimization.optimal_take_profit_2 }}</span>
                <span class="kv-key" style="margin-left:12px">风险收益比</span>
                <span class="kv-val" :style="{ color: diagnosis.chanlun.dynamic_rr_optimization.risk_reward_ratio >= 2 ? '#22c55e' : '#f59e0b' }">
                  1 : {{ diagnosis.chanlun.dynamic_rr_optimization.risk_reward_ratio.toFixed(1) }}
                </span>
              </div>
              <div class="kv-row">
                <span class="kv-key">ATR止损距离</span>
                <span class="kv-val">{{ diagnosis.chanlun.dynamic_rr_optimization.atr_based_stop }}</span>
                <span class="kv-key">ATR值</span>
                <span class="kv-val">{{ diagnosis.chanlun.dynamic_rr_optimization.atr }}</span>
              </div>
              <div class="kv-row">
                <span class="kv-key">波动率调整</span>
                <span class="tag" :class="diagnosis.chanlun.dynamic_rr_optimization.volatility_adjusted ? 'tag-yellow' : 'tag-gray'">
                  {{ diagnosis.chanlun.dynamic_rr_optimization.volatility_adjusted ? '已调整' : '未调整' }}
                </span>
                <span class="kv-key">调整因子</span>
                <span class="kv-val">{{ diagnosis.chanlun.dynamic_rr_optimization.adjustment_factor }}x</span>
              </div>
              <div class="kv-note" style="margin-top:4px;font-size:11px;color:var(--text-dim)">
                当前波动率: {{ (diagnosis.chanlun.dynamic_rr_optimization.volatility * 100).toFixed(2) }}%
              </div>
            </div>

            <!-- V26: 多标的对比评分 -->
            <div v-if="diagnosis.chanlun.cross_stock_comparison && diagnosis.chanlun.cross_stock_comparison.ranked_signals.length > 0" class="signal-report cross-stock">
              <div class="section-label">📈 多标的对比评分（V26）</div>
              <div class="kv-row" v-for="(sig, idx) in diagnosis.chanlun.cross_stock_comparison.ranked_signals.slice(0, 3)" :key="idx">
                <span class="kv-key">#{{ idx + 1 }}</span>
                <span class="kv-val" :style="{ fontWeight: idx === 0 ? 'bold' : 'normal' }">
                  {{ sig.mmd_type }} (置信度{{ (sig.confidence * 100).toFixed(0) }}%)
                </span>
                <span class="tag grade-tag grade-{{ sig.grade }}" style="font-size:11px">{{ sig.grade }}级</span>
                <span class="kv-val" style="font-size:11px">{{ sig.recommendation }}</span>
              </div>
              <div class="kv-row" v-if="diagnosis.chanlun.cross_stock_comparison.comparison_summary">
                <span class="kv-key">平均得分</span>
                <span class="kv-val">{{ diagnosis.chanlun.cross_stock_comparison.comparison_summary.avg_composite_score }}</span>
                <span class="kv-key">分散化评分</span>
                <span class="kv-val">{{ diagnosis.chanlun.cross_stock_comparison.diversification_score }}</span>
              </div>
            </div>

            <!-- V27: 多级别区间套共振验证 -->
            <div v-if="diagnosis.chanlun.multi_tf_confluence" class="signal-report multi-tf">
              <div class="section-label">🔗 多级别区间套共振验证（V27）</div>
              <div class="kv-row">
                <span class="kv-key">共振评分</span>
                <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_tf_confluence.overall_confluence_score >= 0.7 ? '#22c55e' : diagnosis.chanlun.multi_tf_confluence.overall_confluence_score >= 0.5 ? '#f59e0b' : '#ef4444' }">
                  {{ (diagnosis.chanlun.multi_tf_confluence.overall_confluence_score * 100).toFixed(1) }}%
                </span>
                <span class="kv-key">趋势对齐</span>
                <span class="tag" :class="{
                  'tag-green': diagnosis.chanlun.multi_tf_confluence.trend_alignment.includes('bullish'),
                  'tag-red': diagnosis.chanlun.multi_tf_confluence.trend_alignment.includes('bearish'),
                  'tag-yellow': diagnosis.chanlun.multi_tf_confluence.trend_alignment === 'moderate_consistent',
                  'tag-gray': diagnosis.chanlun.multi_tf_confluence.trend_alignment === 'mixed'
                }">
                  {{ diagnosis.chanlun.multi_tf_confluence.trend_alignment === 'strong_bullish' ? '强势多头📈' :
                     diagnosis.chanlun.multi_tf_confluence.trend_alignment === 'strong_bearish' ? '强势空头📉' :
                     diagnosis.chanlun.multi_tf_confluence.trend_alignment === 'moderate_consistent' ? '中性一致⚖️' : '混合方向🌀' }}
                </span>
              </div>
              <div class="kv-row">
                <span class="kv-key">短期(20日)</span>
                <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_tf_confluence.short_trend === 'up' ? '#22c55e' : diagnosis.chanlun.multi_tf_confluence.short_trend === 'down' ? '#ef4444' : '#888' }">
                  {{ diagnosis.chanlun.multi_tf_confluence.short_trend === 'up' ? '上涨↑' : diagnosis.chanlun.multi_tf_confluence.short_trend === 'down' ? '下跌↓' : '横盘→' }}
                </span>
                <span class="kv-key">中期(20-40日)</span>
                <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_tf_confluence.mid_trend === 'up' ? '#22c55e' : diagnosis.chanlun.multi_tf_confluence.mid_trend === 'down' ? '#ef4444' : '#888' }">
                  {{ diagnosis.chanlun.multi_tf_confluence.mid_trend === 'up' ? '上涨↑' : diagnosis.chanlun.multi_tf_confluence.mid_trend === 'down' ? '下跌↓' : '横盘→' }}
                </span>
                <span class="kv-key">长期(40-60日)</span>
                <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_tf_confluence.long_trend === 'up' ? '#22c55e' : diagnosis.chanlun.multi_tf_confluence.long_trend === 'down' ? '#ef4444' : '#888' }">
                  {{ diagnosis.chanlun.multi_tf_confluence.long_trend === 'up' ? '上涨↑' : diagnosis.chanlun.multi_tf_confluence.long_trend === 'down' ? '下跌↓' : '横盘→' }}
                </span>
              </div>
              <div class="kv-row">
                <span class="kv-key">置信度调整</span>
                <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_tf_confluence.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                  {{ diagnosis.chanlun.multi_tf_confluence.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.multi_tf_confluence.confidence_adjust * 100).toFixed(2) }}%
                </span>
              </div>
            </div>

            <!-- V27: 买卖点结构位置评分 -->
            <div v-if="diagnosis.chanlun.structure_position" class="signal-report struct-pos">
              <div class="section-label">📍 买卖点结构位置评分（V27）</div>
              <div class="kv-row">
                <span class="kv-key">位置评分</span>
                <span class="kv-val" :style="{ color: diagnosis.chanlun.structure_position.position_score >= 0.7 ? '#22c55e' : diagnosis.chanlun.structure_position.position_score >= 0.5 ? '#f59e0b' : '#ef4444' }">
                  {{ (diagnosis.chanlun.structure_position.position_score * 100).toFixed(1) }}%
                </span>
                <span class="tag grade-tag grade-{{ diagnosis.chanlun.structure_position.structural_quality === 'excellent' ? 'S' : diagnosis.chanlun.structure_position.structural_quality === 'good' ? 'A' : diagnosis.chanlun.structure_position.structural_quality === 'fair' ? 'B' : 'C' }}" style="font-size:11px">
                  {{ diagnosis.chanlun.structure_position.structural_quality === 'excellent' ? '优秀' : diagnosis.chanlun.structure_position.structural_quality === 'good' ? '良好' : diagnosis.chanlun.structure_position.structural_quality === 'fair' ? '一般' : '较差' }}
                </span>
              </div>
              <div class="kv-row">
                <span class="kv-key">距支撑位</span>
                <span class="kv-val">{{ (diagnosis.chanlun.structure_position.distance_to_support * 100).toFixed(1) }}%</span>
                <span class="kv-key">距阻力位</span>
                <span class="kv-val">{{ (diagnosis.chanlun.structure_position.distance_to_resistance * 100).toFixed(1) }}%</span>
              </div>
              <div class="kv-row">
                <span class="kv-key">支撑位</span>
                <span class="kv-val tag-red">{{ diagnosis.chanlun.structure_position.support_level }}</span>
                <span class="kv-key">阻力位</span>
                <span class="kv-val tag-green">{{ diagnosis.chanlun.structure_position.resistance_level }}</span>
              </div>
              <div class="kv-note" style="margin-top:4px;font-size:11px;color:var(--text-dim)">
                {{ diagnosis.chanlun.structure_position.position_desc }}
              </div>
            </div>

            <!-- V27: 个股信号特征学习 -->
            <div v-if="diagnosis.chanlun.stock_profile" class="signal-report stock-profile">
              <div class="section-label">🧬 个股信号特征学习（V27）</div>
              <div class="kv-row">
                <span class="kv-key">信号成功率</span>
                <span class="kv-val" :style="{ color: diagnosis.chanlun.stock_profile.signal_type_success_rate >= 0.6 ? '#22c55e' : diagnosis.chanlun.stock_profile.signal_type_success_rate >= 0.5 ? '#f59e0b' : '#ef4444' }">
                  {{ (diagnosis.chanlun.stock_profile.signal_type_success_rate * 100).toFixed(1) }}%
                </span>
                <span class="tag" :class="{
                  'tag-green': diagnosis.chanlun.stock_profile.personalized_rating.includes('high'),
                  'tag-yellow': diagnosis.chanlun.stock_profile.personalized_rating.includes('good') || diagnosis.chanlun.stock_profile.personalized_rating.includes('moderate'),
                  'tag-red': diagnosis.chanlun.stock_profile.personalized_rating.includes('low')
                }">
                  {{ diagnosis.chanlun.stock_profile.personalized_rating === 'high_reliability' ? '高可靠⭐' :
                     diagnosis.chanlun.stock_profile.personalized_rating === 'good_reliability' ? '较可靠☆' :
                     diagnosis.chanlun.stock_profile.personalized_rating === 'moderate_reliability' ? '中等●' : '低可靠○' }}
                </span>
              </div>
              <div class="kv-row">
                <span class="kv-key">波动特征</span>
                <span class="tag" :class="{
                  'tag-green': diagnosis.chanlun.stock_profile.stock_volatility_regime === 'low',
                  'tag-yellow': diagnosis.chanlun.stock_profile.stock_volatility_regime === 'normal',
                  'tag-red': diagnosis.chanlun.stock_profile.stock_volatility_regime === 'high'
                }">
                  {{ diagnosis.chanlun.stock_profile.stock_volatility_regime === 'low' ? '低波动🌊' :
                     diagnosis.chanlun.stock_profile.stock_volatility_regime === 'high' ? '高波动⚡' : '正常波动~' }}
                </span>
                <span class="kv-key">信号频率</span>
                <span class="tag" :class="{
                  'tag-yellow': diagnosis.chanlun.stock_profile.signal_frequency === 'high',
                  'tag-green': diagnosis.chanlun.stock_profile.signal_frequency === 'normal',
                  'tag-gray': diagnosis.chanlun.stock_profile.signal_frequency === 'low'
                }">
                  {{ diagnosis.chanlun.stock_profile.signal_frequency === 'high' ? '频繁📊' :
                     diagnosis.chanlun.stock_profile.signal_frequency === 'low' ? '稀少📉' : '正常📈' }}
                </span>
              </div>
              <div class="kv-row">
                <span class="kv-key">20日波动率</span>
                <span class="kv-val">{{ (diagnosis.chanlun.stock_profile.vol_20d * 100).toFixed(2) }}%</span>
                <span class="kv-key">50日均值收益</span>
                <span class="kv-val" :style="{ color: diagnosis.chanlun.stock_profile.mean_return_50d > 0 ? '#22c55e' : '#ef4444' }">
                  {{ diagnosis.chanlun.stock_profile.mean_return_50d > 0 ? '+' : '' }}{{ (diagnosis.chanlun.stock_profile.mean_return_50d * 100).toFixed(2) }}%
                </span>
              </div>
              <div class="kv-row">
                <span class="kv-key">置信度调整</span>
                <span class="kv-val" :style="{ color: diagnosis.chanlun.stock_profile.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                  {{ diagnosis.chanlun.stock_profile.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.stock_profile.confidence_adjust * 100).toFixed(2) }}%
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- V28: BOLL带宽压缩确认 -->
        <div v-if="diagnosis.chanlun.boll_squeeze" class="metric-card">
          <div class="card-title">📊 BOLL带宽压缩确认（V28）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">压缩强度</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.boll_squeeze.squeeze_score >= 0.7 ? '#22c55e' : diagnosis.chanlun.boll_squeeze.squeeze_score >= 0.4 ? '#f59e0b' : '#ef4444' }">
                {{ (diagnosis.chanlun.boll_squeeze.squeeze_score * 100).toFixed(1) }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">状态</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.boll_squeeze.squeeze_active, 'tag-yellow': !diagnosis.chanlun.boll_squeeze.squeeze_active }">
                {{ diagnosis.chanlun.boll_squeeze.squeeze_active ? '压缩中🔥' : '正常' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">带宽</span>
              <span class="kv-val">{{ diagnosis.chanlun.boll_squeeze.band_width.toFixed(2) }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">带宽分位</span>
              <span class="kv-val">{{ (diagnosis.chanlun.boll_squeeze.band_width_rank * 100).toFixed(0) }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.boll_squeeze.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.boll_squeeze.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.boll_squeeze.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V28: 突破量价确认 -->
        <div v-if="diagnosis.chanlun.breakout_vol_price" class="metric-card">
          <div class="card-title">💹 突破量价确认（V28）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">突破强度</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.breakout_vol_price.breakout_strength === 'strong', 'tag-yellow': diagnosis.chanlun.breakout_vol_price.breakout_strength === 'moderate', 'tag-red': diagnosis.chanlun.breakout_vol_price.breakout_strength === 'weak' }">
                {{ diagnosis.chanlun.breakout_vol_price.breakout_strength === 'strong' ? '强突破💪' : diagnosis.chanlun.breakout_vol_price.breakout_strength === 'moderate' ? '中等⚡' : '弱突破⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">成交量比</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.breakout_vol_price.volume_ratio >= 1.2 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.breakout_vol_price.volume_ratio.toFixed(2) }}x
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">价格变动</span>
              <span class="kv-val">{{ diagnosis.chanlun.breakout_vol_price.price_force_ratio.toFixed(2) }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">确认状态</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.breakout_vol_price.confirmed, 'tag-red': !diagnosis.chanlun.breakout_vol_price.confirmed }">
                {{ diagnosis.chanlun.breakout_vol_price.confirmed ? '✅ 确认' : '❌ 未确认' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.breakout_vol_price.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.breakout_vol_price.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.breakout_vol_price.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V28: 动态ATR止损位 -->
        <div v-if="diagnosis.chanlun.dynamic_atr_stop" class="metric-card">
          <div class="card-title">🛡️ 动态ATR止损位（V28）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">止损价</span>
              <span class="kv-val" style="color:#ef4444">{{ diagnosis.chanlun.dynamic_atr_stop.stop_loss_price.toFixed(2) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">止损幅度</span>
              <span class="kv-val" style="color:#ef4444">-{{ diagnosis.chanlun.dynamic_atr_stop.stop_loss_pct.toFixed(2) }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">ATR值</span>
              <span class="kv-val">{{ diagnosis.chanlun.dynamic_atr_stop.atr_value.toFixed(4) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">止盈价</span>
              <span class="kv-val" style="color:#22c55e">{{ diagnosis.chanlun.dynamic_atr_stop.take_profit_price.toFixed(2) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">风险收益比</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.dynamic_atr_stop.risk_reward_ratio >= 2 ? '#22c55e' : diagnosis.chanlun.dynamic_atr_stop.risk_reward_ratio >= 1.5 ? '#f59e0b' : '#ef4444' }">
                1 : {{ diagnosis.chanlun.dynamic_atr_stop.risk_reward_ratio.toFixed(2) }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.dynamic_atr_stop.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.dynamic_atr_stop.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.dynamic_atr_stop.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V29: 趋势方向持续性确认 -->
        <div v-if="diagnosis.chanlun.trend_continuity" class="metric-card">
          <div class="card-title">📉 趋势持续性确认（V29）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">连续性评分</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.trend_continuity.continuity_score >= 0.7 ? '#22c55e' : diagnosis.chanlun.trend_continuity.continuity_score >= 0.5 ? '#f59e0b' : '#ef4444' }">
                {{ (diagnosis.chanlun.trend_continuity.continuity_score * 100).toFixed(1) }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">趋势状态</span>
              <span class="tag" :class="{
                'tag-green': diagnosis.chanlun.trend_continuity.future_trend === 'bullish' || diagnosis.chanlun.trend_continuity.future_trend === 'pullback_complete',
                'tag-red': diagnosis.chanlun.trend_continuity.future_trend === 'bearish' || diagnosis.chanlun.trend_continuity.future_trend === 'chasing',
                'tag-yellow': diagnosis.chanlun.trend_continuity.future_trend === 'neutral'
              }">
                {{ diagnosis.chanlun.trend_continuity.future_trend === 'bullish' ? '📈 上涨延续' :
                   diagnosis.chanlun.trend_continuity.future_trend === 'bearish' ? '📉 下跌延续' :
                   diagnosis.chanlun.trend_continuity.future_trend === 'pullback_complete' ? '✅ 回调到位' :
                   diagnosis.chanlun.trend_continuity.future_trend === 'rebound_complete' ? '✅ 反弹到位' :
                   diagnosis.chanlun.trend_continuity.future_trend === 'chasing' ? '⚠️ 追高中' :
                   diagnosis.chanlun.trend_continuity.future_trend === 'chasing_down' ? '⚠️ 追空中' : '➡️ 震荡' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">确认K线数</span>
              <span class="kv-val">{{ diagnosis.chanlun.trend_continuity.confirm_bars }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.trend_continuity.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.trend_continuity.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.trend_continuity.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V29: 盘整区背离预警 -->
        <div v-if="diagnosis.chanlun.consolidation_divergence && diagnosis.chanlun.consolidation_divergence.has_divergence" class="metric-card">
          <div class="card-title">⚠️ 盘整背离预警（V29）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">背离类型</span>
              <span class="tag" :class="{ 'tag-red': diagnosis.chanlun.consolidation_divergence.divergence_type === 'bearish', 'tag-green': diagnosis.chanlun.consolidation_divergence.divergence_type === 'bullish' }">
                {{ diagnosis.chanlun.consolidation_divergence.divergence_type === 'bearish' ? '🔴 顶背离' : '🟢 底背离' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">背离强度</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.consolidation_divergence.divergence_strength > 0.3 ? '#ef4444' : '#f59e0b' }">
                {{ (diagnosis.chanlun.consolidation_divergence.divergence_strength * 100).toFixed(1) }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">预警级别</span>
              <span class="tag" :class="{ 'tag-red': diagnosis.chanlun.consolidation_divergence.warning_level === 'high', 'tag-yellow': diagnosis.chanlun.consolidation_divergence.warning_level === 'medium' }">
                {{ diagnosis.chanlun.consolidation_divergence.warning_level === 'high' ? '🔴 高风险' : '🟡 中风险' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" style="color:#ef4444">{{ (diagnosis.chanlun.consolidation_divergence.confidence_adjust * 100).toFixed(2) }}%</span>
            </div>
          </div>
        </div>

        <!-- V30: K线形态反向确认 -->
        <div v-if="diagnosis.chanlun.kline_pattern_confirm" class="metric-card">
          <div class="card-title">🕯️ K线形态确认（V30）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">形态支持度</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.kline_pattern_confirm.pattern_score >= 0.7 ? '#22c55e' : diagnosis.chanlun.kline_pattern_confirm.pattern_score >= 0.4 ? '#f59e0b' : '#ef4444' }">
                {{ (diagnosis.chanlun.kline_pattern_confirm.pattern_score * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">K线方向</span>
              <span class="tag" :class="{
                'tag-green': diagnosis.chanlun.kline_pattern_confirm.bar_direction === 'bullish_continuation',
                'tag-red': diagnosis.chanlun.kline_pattern_confirm.bar_direction === 'bearish_continuation',
                'tag-yellow': diagnosis.chanlun.kline_pattern_confirm.bar_direction === 'mixed' || diagnosis.chanlun.kline_pattern_confirm.bar_direction === 'neutral',
                'tag-orange': diagnosis.chanlun.kline_pattern_confirm.bar_direction === 'bearish_pressure' || diagnosis.chanlun.kline_pattern_confirm.bar_direction === 'bullish_pressure'
              }">
                {{ {bullish_continuation:'📈 看涨延续',bearish_continuation:'📉 看跌延续',mixed:'➡️ 震荡',neutral:'⏸️ 中性',bearish_pressure:'🔴 空头压力',bullish_pressure:'🟢 多头压力'}[diagnosis.chanlun.kline_pattern_confirm.bar_direction] || diagnosis.chanlun.kline_pattern_confirm.bar_direction }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.kline_pattern_confirm.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.kline_pattern_confirm.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.kline_pattern_confirm.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V30: 中枢突破方向确认 -->
        <div v-if="diagnosis.chanlun.zs_breakout_confirm" class="metric-card">
          <div class="card-title">📊 中枢突破确认（V30）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">突破状态</span>
              <span class="tag" :class="{
                'tag-green': diagnosis.chanlun.zs_breakout_confirm.breakout_valid && diagnosis.chanlun.zs_breakout_confirm.breakout_direction === 'up',
                'tag-red': diagnosis.chanlun.zs_breakout_confirm.breakout_valid && diagnosis.chanlun.zs_breakout_confirm.breakout_direction === 'down',
                'tag-yellow': !diagnosis.chanlun.zs_breakout_confirm.breakout_valid && diagnosis.chanlun.zs_breakout_confirm.breakout_direction === 'inside'
              }">
                {{ diagnosis.chanlun.zs_breakout_confirm.breakout_valid
                  ? (diagnosis.chanlun.zs_breakout_confirm.breakout_direction === 'up' ? '✅ 有效突破↑' : '⚠️ 有效突破↓')
                  : (diagnosis.chanlun.zs_breakout_confirm.breakout_direction === 'inside' ? '🔄 中枢内震荡' : '⏸️ 未突破')
                }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">量能确认</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.zs_breakout_confirm.volume_confirmed, 'tag-gray': !diagnosis.chanlun.zs_breakout_confirm.volume_confirmed }">
                {{ diagnosis.chanlun.zs_breakout_confirm.volume_confirmed ? '✅ 放量确认' : '⚪ 未确认' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.zs_breakout_confirm.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.zs_breakout_confirm.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.zs_breakout_confirm.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V30: 近期波动区间止损 -->
        <div v-if="diagnosis.chanlun.recent_range_stop" class="metric-card">
          <div class="card-title">🛡️ 区间止损优化（V30）</div>
          <div class="card-body">
            <div class="kv-row"><span class="kv-key">止损价</span><span class="kv-val sell">{{ diagnosis.chanlun.recent_range_stop.stop_loss_price }}</span></div>
            <div class="kv-row"><span class="kv-key">止损幅度</span><span class="kv-val sell">{{ diagnosis.chanlun.recent_range_stop.stop_loss_pct }}%</span></div>
            <div class="kv-row"><span class="kv-key">近期低点 / 高点</span><span class="kv-val">{{ diagnosis.chanlun.recent_range_stop.recent_low }} / {{ diagnosis.chanlun.recent_range_stop.recent_high }}</span></div>
            <div class="kv-row"><span class="kv-key">止盈参考</span><span class="kv-val buy">{{ diagnosis.chanlun.recent_range_stop.take_profit_price }}</span></div>
            <div class="kv-row"><span class="kv-key">风险收益比</span><span class="kv-val" :style="{ color: diagnosis.chanlun.recent_range_stop.risk_reward_ratio >= 2 ? '#22c55e' : diagnosis.chanlun.recent_range_stop.risk_reward_ratio >= 1.5 ? '#f59e0b' : '#ef4444' }">1 : {{ diagnosis.chanlun.recent_range_stop.risk_reward_ratio.toFixed(2) }}</span></div>
          </div>
        </div>

        <!-- V31: 均线排列确认 -->
        <div v-if="diagnosis.chanlun.ma_alignment" class="metric-card">
          <div class="card-title">📐 均线排列确认（V31）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">排列状态</span>
              <span class="tag" :class="{
                'tag-green': diagnosis.chanlun.ma_alignment.alignment === 'bullish',
                'tag-red': diagnosis.chanlun.ma_alignment.alignment === 'bearish',
                'tag-yellow': diagnosis.chanlun.ma_alignment.alignment === 'mixed'
              }">
                {{ diagnosis.chanlun.ma_alignment.alignment === 'bullish' ? '📈 多头排列' : diagnosis.chanlun.ma_alignment.alignment === 'bearish' ? '📉 空头排列' : '➡️ 混乱排列' }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">MA5 / MA10 / MA20</span><span class="kv-val">{{ diagnosis.chanlun.ma_alignment.ma5 }} / {{ diagnosis.chanlun.ma_alignment.ma10 }} / {{ diagnosis.chanlun.ma_alignment.ma20 }}</span></div>
            <div class="kv-row">
              <span class="kv-key">多头排列</span>
              <span class="tag" :class="diagnosis.chanlun.ma_alignment.is_bullish_arrangement ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.ma_alignment.is_bullish_arrangement ? '✅ 是' : '❌ 否' }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">空头排列</span>
              <span class="tag" :class="diagnosis.chanlun.ma_alignment.is_bearish_arrangement ? 'tag-red' : 'tag-gray'">{{ diagnosis.chanlun.ma_alignment.is_bearish_arrangement ? '✅ 是' : '❌ 否' }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.ma_alignment.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.ma_alignment.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.ma_alignment.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V31: MACD柱状图加速度 -->
        <div v-if="diagnosis.chanlun.macd_histogram_acceleration" class="metric-card">
          <div class="card-title">📊 MACD动能加速度（V31）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">加速度方向</span>
              <span class="tag" :class="{
                'tag-green': diagnosis.chanlun.macd_histogram_acceleration.acceleration_direction === 'positive',
                'tag-red': diagnosis.chanlun.macd_histogram_acceleration.acceleration_direction === 'negative',
                'tag-yellow': diagnosis.chanlun.macd_histogram_acceleration.acceleration_direction === 'neutral'
              }">
                {{ diagnosis.chanlun.macd_histogram_acceleration.acceleration_direction === 'positive' ? '📈 加速上升' : diagnosis.chanlun.macd_histogram_acceleration.acceleration_direction === 'negative' ? '📉 加速下降' : '➡️ 平稳' }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">柱状斜率</span><span class="kv-val">{{ diagnosis.chanlun.macd_histogram_acceleration.hist_slope.toFixed(6) }}</span></div>
            <div class="kv-row"><span class="kv-key">加速度</span><span class="kv-val" :style="{ color: diagnosis.chanlun.macd_histogram_acceleration.hist_acceleration > 0 ? '#22c55e' : '#ef4444' }">{{ diagnosis.chanlun.macd_histogram_acceleration.hist_acceleration > 0 ? '+' : '' }}{{ diagnosis.chanlun.macd_histogram_acceleration.hist_acceleration.toFixed(6) }}</span></div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.macd_histogram_acceleration.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.macd_histogram_acceleration.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.macd_histogram_acceleration.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V31: 信号综合健康度报告 -->
        <div v-if="diagnosis.chanlun.signal_health_dashboard" class="metric-card" :class="'health-grade-' + diagnosis.chanlun.signal_health_dashboard.health_grade">
          <div class="card-title">💚 信号健康度报告（V31）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">健康评分</span>
              <span class="kv-val" :style="{
                color: diagnosis.chanlun.signal_health_dashboard.health_score >= 80 ? '#22c55e' :
                       diagnosis.chanlun.signal_health_dashboard.health_score >= 65 ? '#f59e0b' :
                       diagnosis.chanlun.signal_health_dashboard.health_score >= 50 ? '#f97316' : '#ef4444'
              }">
                {{ diagnosis.chanlun.signal_health_dashboard.health_score.toFixed(1) }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">健康等级</span>
              <span class="tag" :class="{
                'tag-green': diagnosis.chanlun.signal_health_dashboard.health_grade === 'A',
                'tag-blue': diagnosis.chanlun.signal_health_dashboard.health_grade === 'B',
                'tag-yellow': diagnosis.chanlun.signal_health_dashboard.health_grade === 'C',
                'tag-orange': diagnosis.chanlun.signal_health_dashboard.health_grade === 'D',
                'tag-red': diagnosis.chanlun.signal_health_dashboard.health_grade === 'F'
              }">
                {{ diagnosis.chanlun.signal_health_dashboard.health_grade }}级
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">建议</span>
              <span class="kv-val" style="font-size:12px">{{ diagnosis.chanlun.signal_health_dashboard.recommendation }}</span>
            </div>
            <div v-if="diagnosis.chanlun.signal_health_dashboard.strengths.length > 0" class="kv-note" style="color:#22c55e">
              ✅ {{ diagnosis.chanlun.signal_health_dashboard.strengths.join(' | ') }}
            </div>
            <div v-if="diagnosis.chanlun.signal_health_dashboard.weaknesses.length > 0" class="kv-note" style="color:#ef4444">
              ⚠️ {{ diagnosis.chanlun.signal_health_dashboard.weaknesses.join(' | ') }}
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.signal_health_dashboard.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.signal_health_dashboard.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.signal_health_dashboard.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V32: 量价背离检测增强 -->
        <div v-if="diagnosis.chanlun.vol_price_divergence_enhanced" class="metric-card vol-price-div">
          <div class="card-title">📉 量价背离检测（V32）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">背离状态</span>
              <span class="tag" :class="diagnosis.chanlun.vol_price_divergence_enhanced.divergence_detected ? 'tag-red' : 'tag-green'">
                {{ diagnosis.chanlun.vol_price_divergence_enhanced.divergence_detected ? '⚠️ 背离预警' : '✅ 量价配合' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">背离类型</span>
              <span class="kv-val">{{ diagnosis.chanlun.vol_price_divergence_enhanced.divergence_type === 'bearish' ? '顶背离（看跌）' : diagnosis.chanlun.vol_price_divergence_enhanced.divergence_type === 'bullish' ? '底背离（看涨）' : '无背离' }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">成交量趋势</span>
              <span class="kv-val">{{ diagnosis.chanlun.vol_price_divergence_enhanced.volume_trend === 'increasing' ? '📈 放量' : diagnosis.chanlun.vol_price_divergence_enhanced.volume_trend === 'decreasing' ? '📉 缩量' : '➡️ 平稳' }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">价格趋势</span>
              <span class="kv-val">{{ diagnosis.chanlun.vol_price_divergence_enhanced.price_trend === 'new_high' ? '🆙 创新高' : diagnosis.chanlun.vol_price_divergence_enhanced.price_trend === 'new_low' ? '🆕 创新低' : '➡️ 盘整' }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">背离强度</span>
              <span class="kv-val">{{ diagnosis.chanlun.vol_price_divergence_enhanced.strength.toFixed(2) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.vol_price_divergence_enhanced.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.vol_price_divergence_enhanced.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.vol_price_divergence_enhanced.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V32: 信号优先级动态排序 -->
        <div v-if="diagnosis.chanlun.signal_priority" class="metric-card signal-priority">
          <div class="card-title">🏆 信号优先级排序（V32）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">当前排名</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.signal_priority.priority_rank === 1 ? '#22c55e' : diagnosis.chanlun.signal_priority.priority_rank <= 2 ? '#3b82f6' : '#f59e0b' }">
                第 {{ diagnosis.chanlun.signal_priority.priority_rank }} / {{ diagnosis.chanlun.signal_priority.total_signals }} 个信号
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">优先级分数</span>
              <span class="kv-val">{{ diagnosis.chanlun.signal_priority.priority_score.toFixed(1) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">排序原因</span>
              <span class="kv-val" style="font-size:12px">{{ diagnosis.chanlun.signal_priority.rank_reason }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.signal_priority.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.signal_priority.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.signal_priority.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V32: 支撑阻力位突破确认 -->
        <div v-if="diagnosis.chanlun.sr_breakout_confirm" class="metric-card sr-breakout">
          <div class="card-title">📐 支撑阻力位确认（V32）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">S/R 类型</span>
              <span class="tag" :class="diagnosis.chanlun.sr_breakout_confirm.breakout_valid ? 'tag-green' : 'tag-yellow'">
                {{ diagnosis.chanlun.sr_breakout_confirm.sr_type === 'swing_low_broken' ? '✅ 支撑突破' : diagnosis.chanlun.sr_breakout_confirm.sr_type === 'swing_high_broken' ? '✅ 阻力跌破' : diagnosis.chanlun.sr_breakout_confirm.sr_type === 'approaching_sl' ? '⚠️ 接近支撑' : diagnosis.chanlun.sr_breakout_confirm.sr_type === 'approaching_sh' ? '⚠️ 接近阻力' : '➡️ 未突破' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">关键价位</span>
              <span class="kv-val">{{ diagnosis.chanlun.sr_breakout_confirm.sr_level > 0 ? diagnosis.chanlun.sr_breakout_confirm.sr_level : '-' }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">距离</span>
              <span class="kv-val">{{ diagnosis.chanlun.sr_breakout_confirm.distance_pct > 0 ? diagnosis.chanlun.sr_breakout_confirm.distance_pct.toFixed(2) + '%' : '-' }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.sr_breakout_confirm.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.sr_breakout_confirm.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.sr_breakout_confirm.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V33: OBV能量潮趋势确认 -->
        <div v-if="diagnosis.chanlun.obv_trend_confirm" class="metric-card obv-trend">
          <div class="card-title">💧 OBV能量潮确认（V33）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">OBV趋势</span>
              <span class="tag" :class="diagnosis.chanlun.obv_trend_confirm.obv_trend === 'rising' ? 'tag-green' : diagnosis.chanlun.obv_trend_confirm.obv_trend === 'falling' ? 'tag-red' : 'tag-yellow'">
                {{ diagnosis.chanlun.obv_trend_confirm.obv_trend === 'rising' ? '📈 上升' : diagnosis.chanlun.obv_trend_confirm.obv_trend === 'falling' ? '📉 下降' : '➡️ 平稳' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">价格趋势</span>
              <span class="tag" :class="diagnosis.chanlun.obv_trend_confirm.price_trend === 'up' ? 'tag-green' : diagnosis.chanlun.obv_trend_confirm.price_trend === 'down' ? 'tag-red' : 'tag-yellow'">
                {{ diagnosis.chanlun.obv_trend_confirm.price_trend === 'up' ? '📈 上涨' : diagnosis.chanlun.obv_trend_confirm.price_trend === 'down' ? '📉 下跌' : '➡️ 盘整' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">量价确认</span>
              <span class="tag" :class="diagnosis.chanlun.obv_trend_confirm.confirmation ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.obv_trend_confirm.confirmation ? '✅ 确认' : '⚠️ 背离/不确认' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">OBV/MA比值</span>
              <span class="kv-val">{{ diagnosis.chanlun.obv_trend_confirm.obv_ma_ratio.toFixed(4) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.obv_trend_confirm.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.obv_trend_confirm.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.obv_trend_confirm.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V33: MACD动能锥面积确认 -->
        <div v-if="diagnosis.chanlun.macd_hist_area" class="metric-card macd-hist-area">
          <div class="card-title">📊 MACD动能锥（V33）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">动能方向</span>
              <span class="tag" :class="diagnosis.chanlun.macd_hist_area.momentum_direction === 'bullish' ? 'tag-green' : diagnosis.chanlun.macd_hist_area.momentum_direction === 'bearish' ? 'tag-red' : 'tag-yellow'">
                {{ diagnosis.chanlun.macd_hist_area.momentum_direction === 'bullish' ? '🐂 看涨动能' : diagnosis.chanlun.macd_hist_area.momentum_direction === 'bearish' ? '🐻 看跌动能' : '➡️ 中性' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">加速度</span>
              <span class="tag" :class="diagnosis.chanlun.macd_hist_area.acceleration === 'accelerating' ? 'tag-green' : diagnosis.chanlun.macd_hist_area.acceleration === 'decaying' ? 'tag-red' : 'tag-blue'">
                {{ diagnosis.chanlun.macd_hist_area.acceleration === 'accelerating' ? '📈 加速' : diagnosis.chanlun.macd_hist_area.acceleration === 'decaying' ? '📉 衰减' : '➡️ 稳定' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">面积比（近/前）</span>
              <span class="kv-val">{{ diagnosis.chanlun.macd_hist_area.area_ratio.toFixed(4) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.macd_hist_area.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.macd_hist_area.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.macd_hist_area.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V33: RSI动量确认 -->
        <div v-if="diagnosis.chanlun.rsi_momentum_confirm" class="metric-card rsi-momentum">
          <div class="card-title">📉 RSI动量确认（V33）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">RSI值</span>
              <span class="tag" :class="diagnosis.chanlun.rsi_momentum_confirm.rsi_zone === 'overbought' ? 'tag-red' : diagnosis.chanlun.rsi_momentum_confirm.rsi_zone === 'oversold' ? 'tag-green' : 'tag-yellow'">
                {{ diagnosis.chanlun.rsi_momentum_confirm.rsi_value.toFixed(1) }}（{{ diagnosis.chanlun.rsi_momentum_confirm.rsi_zone === 'overbought' ? '超买' : diagnosis.chanlun.rsi_momentum_confirm.rsi_zone === 'oversold' ? '超卖' : diagnosis.chanlun.rsi_momentum_confirm.rsi_zone === 'strong' ? '偏强' : diagnosis.chanlun.rsi_momentum_confirm.rsi_zone === 'weak' ? '偏弱' : '中性' }}）
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">RSI动量</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.rsi_momentum_confirm.rsi_momentum > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.rsi_momentum_confirm.rsi_momentum > 0 ? '+' : '' }}{{ diagnosis.chanlun.rsi_momentum_confirm.rsi_momentum.toFixed(2) }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">动量支持</span>
              <span class="tag" :class="diagnosis.chanlun.rsi_momentum_confirm.momentum_support ? 'tag-green' : 'tag-yellow'">
                {{ diagnosis.chanlun.rsi_momentum_confirm.momentum_support ? '✅ 动量支持' : '⚠️ 无支持' }}
              </span>
            </div>
            <div v-if="diagnosis.chanlun.rsi_momentum_confirm.divergence_detected" class="kv-row">
              <span class="kv-key">背离</span>
              <span class="tag tag-red">⚠️ {{ diagnosis.chanlun.rsi_momentum_confirm.divergence_type === 'bearish' ? '顶背离' : '底背离' }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.rsi_momentum_confirm.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.rsi_momentum_confirm.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.rsi_momentum_confirm.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V34: 趋势动能延续确认 -->
        <div v-if="diagnosis.chanlun.trend_momentum_continuation" class="metric-card trend-momentum">
          <div class="card-title">🚀 趋势动能延续（V34）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">5日涨幅</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.trend_momentum_continuation.price_change_5d > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.trend_momentum_continuation.price_change_5d > 0 ? '+' : '' }}{{ diagnosis.chanlun.trend_momentum_continuation.price_change_5d.toFixed(2) }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">10日涨幅</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.trend_momentum_continuation.price_change_10d > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.trend_momentum_continuation.price_change_10d > 0 ? '+' : '' }}{{ diagnosis.chanlun.trend_momentum_continuation.price_change_10d.toFixed(2) }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">20日涨幅</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.trend_momentum_continuation.price_change_20d > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.trend_momentum_continuation.price_change_20d > 0 ? '+' : '' }}{{ diagnosis.chanlun.trend_momentum_continuation.price_change_20d.toFixed(2) }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">动能方向</span>
              <span class="tag" :class="diagnosis.chanlun.trend_momentum_continuation.momentum_direction === 'bullish' ? 'tag-green' : diagnosis.chanlun.trend_momentum_continuation.momentum_direction === 'bearish' ? 'tag-red' : 'tag-yellow'">
                {{ diagnosis.chanlun.trend_momentum_continuation.momentum_direction === 'bullish' ? '🐂 看涨' : diagnosis.chanlun.trend_momentum_continuation.momentum_direction === 'bearish' ? '🐻 看跌' : '➡️ 中性' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">加速度</span>
              <span class="tag" :class="diagnosis.chanlun.trend_momentum_continuation.acceleration === 'accelerating' ? 'tag-green' : diagnosis.chanlun.trend_momentum_continuation.acceleration === 'decelerating' ? 'tag-red' : 'tag-blue'">
                {{ diagnosis.chanlun.trend_momentum_continuation.acceleration === 'accelerating' ? '📈 加速' : diagnosis.chanlun.trend_momentum_continuation.acceleration === 'decelerating' ? '📉 衰减' : '➡️ 平稳' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">延续确认</span>
              <span class="tag" :class="diagnosis.chanlun.trend_momentum_continuation.continuation ? 'tag-green' : 'tag-yellow'">
                {{ diagnosis.chanlun.trend_momentum_continuation.continuation ? '✅ 动能延续' : '⚠️ 动能衰减' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.trend_momentum_continuation.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.trend_momentum_continuation.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.trend_momentum_continuation.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V34: 多指标共振强度评分 -->
        <div v-if="diagnosis.chanlun.multi_indicator_resonance" class="metric-card multi-resonance">
          <div class="card-title">🔗 多指标共振（V34）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">共振强度</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_indicator_resonance.resonance_score >= 80 ? '#22c55e' : diagnosis.chanlun.multi_indicator_resonance.resonance_score >= 60 ? '#3b82f6' : diagnosis.chanlun.multi_indicator_resonance.resonance_score >= 40 ? '#f59e0b' : '#ef4444' }">
                {{ diagnosis.chanlun.multi_indicator_resonance.resonance_score.toFixed(0) }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">共振等级</span>
              <span class="tag" :class="diagnosis.chanlun.multi_indicator_resonance.resonance_level === 'strong' ? 'tag-green' : diagnosis.chanlun.multi_indicator_resonance.resonance_level === 'moderate' ? 'tag-blue' : diagnosis.chanlun.multi_indicator_resonance.resonance_level === 'weak' ? 'tag-yellow' : 'tag-gray'">
                {{ diagnosis.chanlun.multi_indicator_resonance.resonance_level === 'strong' ? '💪 强共振' : diagnosis.chanlun.multi_indicator_resonance.resonance_level === 'moderate' ? '🔶 中共振' : diagnosis.chanlun.multi_indicator_resonance.resonance_level === 'weak' ? '🔸 弱共振' : '⚪ 无共振' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">看涨票</span>
              <span class="kv-val" style="color: #22c55e">{{ diagnosis.chanlun.multi_indicator_resonance.bullish_votes }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">看跌票</span>
              <span class="kv-val" style="color: #ef4444">{{ diagnosis.chanlun.multi_indicator_resonance.bearish_votes }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">指标数</span>
              <span class="kv-val">{{ diagnosis.chanlun.multi_indicator_resonance.total_indicators }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">投票详情</span>
              <span class="kv-val" style="font-size: 11px; word-break: break-all">
                {{ Object.entries(diagnosis.chanlun.multi_indicator_resonance.vote_details || {}).map(([k,v]) => `${k}=${v}`).join(' | ') }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_indicator_resonance.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.multi_indicator_resonance.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.multi_indicator_resonance.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V34: 波动率环境 -->
        <div v-if="diagnosis.chanlun.volatility_regime" class="metric-card volatility-regime">
          <div class="card-title">🌊 波动率环境（V34）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">ATR(14)</span>
              <span class="kv-val">{{ diagnosis.chanlun.volatility_regime.atr_value.toFixed(4) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">波动率</span>
              <span class="kv-val">{{ diagnosis.chanlun.volatility_regime.volatility_pct.toFixed(2) }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">波动 regime</span>
              <span class="tag" :class="diagnosis.chanlun.volatility_regime.volatility_regime === 'low' ? 'tag-blue' : diagnosis.chanlun.volatility_regime.volatility_regime === 'high' ? 'tag-red' : 'tag-yellow'">
                {{ diagnosis.chanlun.volatility_regime.volatility_regime === 'low' ? '🟢 低波' : diagnosis.chanlun.volatility_regime.volatility_regime === 'high' ? '🔴 高波' : '🟡 正常' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">门槛调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.volatility_regime.threshold_adjust > 0 ? '#22c55e' : diagnosis.chanlun.volatility_regime.threshold_adjust < 0 ? '#ef4444' : '#888' }">
                {{ diagnosis.chanlun.volatility_regime.threshold_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.volatility_regime.threshold_adjust * 100).toFixed(2) }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">止损调整</span>
              <span class="kv-val">{{ diagnosis.chanlun.volatility_regime.stop_loss_adjust_pct > 0 ? '+' : '' }}{{ diagnosis.chanlun.volatility_regime.stop_loss_adjust_pct.toFixed(1) }}%</span>
            </div>
          </div>
        </div>

        <!-- V35: 市场大环境过滤（条件77）-->
        <div v-if="diagnosis.chanlun.market_context" class="metric-card market-context">
          <div class="card-title">🌍 市场大环境（V35）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">市场趋势</span>
              <span class="tag" :class="diagnosis.chanlun.market_context.market_trend === 'bullish' ? 'tag-green' : diagnosis.chanlun.market_context.market_trend === 'bearish' ? 'tag-red' : 'tag-yellow'">
                {{ diagnosis.chanlun.market_context.market_trend === 'bullish' ? '🐂 牛市' : diagnosis.chanlun.market_context.market_trend === 'bearish' ? '🐻 熊市' : '➡️ 震荡' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">30日涨幅</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.market_context.price_change_30d > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.market_context.price_change_30d > 0 ? '+' : '' }}{{ diagnosis.chanlun.market_context.price_change_30d.toFixed(2) }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">60日涨幅</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.market_context.price_change_60d > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.market_context.price_change_60d > 0 ? '+' : '' }}{{ diagnosis.chanlun.market_context.price_change_60d.toFixed(2) }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.market_context.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.market_context.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.market_context.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V35: 信号衰减增强（条件78）-->
        <div v-if="diagnosis.chanlun.enhanced_signal_decay" class="metric-card signal-decay">
          <div class="card-title">⏰ 信号新鲜度（V35）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">信号距今年线</span>
              <span class="kv-val">{{ diagnosis.chanlun.enhanced_signal_decay.bars_since_signal }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">衰减系数</span>
              <span class="kv-val">{{ diagnosis.chanlun.enhanced_signal_decay.decay_factor.toFixed(3) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">波动率调整</span>
              <span class="kv-val">{{ diagnosis.chanlun.enhanced_signal_decay.volatility_adj.toFixed(3) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.enhanced_signal_decay.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.enhanced_signal_decay.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.enhanced_signal_decay.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V35: 假信号过滤（条件79）-->
        <div v-if="diagnosis.chanlun.false_signal_filter" class="metric-card fake-filter">
          <div class="card-title">🔍 假信号过滤（V35）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">假信号风险</span>
              <span class="tag" :class="diagnosis.chanlun.false_signal_filter.fake_signal_likelihood === 'low' ? 'tag-green' : diagnosis.chanlun.false_signal_filter.fake_signal_likelihood === 'medium' ? 'tag-yellow' : 'tag-red'">
                {{ diagnosis.chanlun.false_signal_filter.fake_signal_likelihood === 'low' ? '🟢 低风险' : diagnosis.chanlun.false_signal_filter.fake_signal_likelihood === 'medium' ? '🟡 中风险' : '🔴 高风险' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">量能确认</span>
              <span class="tag" :class="diagnosis.chanlun.false_signal_filter.volume_confirmed ? 'tag-green' : 'tag-gray'">
                {{ diagnosis.chanlun.false_signal_filter.volume_confirmed ? '✅ 已确认' : '❌ 未确认' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">MACD确认</span>
              <span class="tag" :class="diagnosis.chanlun.false_signal_filter.macd_confirmed ? 'tag-green' : 'tag-gray'">
                {{ diagnosis.chanlun.false_signal_filter.macd_confirmed ? '✅ 已确认' : '❌ 未确认' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.false_signal_filter.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.false_signal_filter.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.false_signal_filter.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V35: 动态止损止盈增强（条件80）-->
        <div v-if="diagnosis.chanlun.dynamic_sl_tp_enhanced" class="metric-card sl-tp">
          <div class="card-title">🛡️ 动态止损止盈（V35）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">建议止损价</span>
              <span class="kv-val" style="color: #ef4444">{{ diagnosis.chanlun.dynamic_sl_tp_enhanced.optimal_stop_loss }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">目标价TP1</span>
              <span class="kv-val" style="color: #22c55e">{{ diagnosis.chanlun.dynamic_sl_tp_enhanced.optimal_take_profit_1 }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">目标价TP2</span>
              <span class="kv-val" style="color: #22c55e">{{ diagnosis.chanlun.dynamic_sl_tp_enhanced.optimal_take_profit_2 }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">风险收益比</span>
              <span class="kv-val" style="color: #3b82f6">{{ diagnosis.chanlun.dynamic_sl_tp_enhanced.risk_reward_ratio }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">ATR距离</span>
              <span class="kv-val">{{ diagnosis.chanlun.dynamic_sl_tp_enhanced.atr_distance.toFixed(4) }}</span>
            </div>
          </div>
        </div>

        <!-- V35: 板块轮动上下文（条件81）-->
        <div v-if="diagnosis.chanlun.sector_rotation_context" class="metric-card sector-rotation">
          <div class="card-title">🔄 板块轮动（V35）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">趋势阶段</span>
              <span class="tag" :class="diagnosis.chanlun.sector_rotation_context.phase === 'early' ? 'tag-green' : diagnosis.chanlun.sector_rotation_context.phase === 'mid_to_late' ? 'tag-red' : diagnosis.chanlun.sector_rotation_context.phase === 'pullback' ? 'tag-yellow' : 'tag-blue'">
                {{ diagnosis.chanlun.sector_rotation_context.phase === 'early' ? '🌱 初期' : diagnosis.chanlun.sector_rotation_context.phase === 'mid_to_late' ? '🍂 末段' : diagnosis.chanlun.sector_rotation_context.phase === 'pullback' ? '↩️ 回踩' : '➡️ 中性' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">趋势强度</span>
              <span class="kv-val">{{ diagnosis.chanlun.sector_rotation_context.trend_strength.toFixed(4) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">MA10/MA30/MA60</span>
              <span class="kv-val">{{ diagnosis.chanlun.sector_rotation_context.ma10.toFixed(2) }}/{{ diagnosis.chanlun.sector_rotation_context.ma30.toFixed(2) }}/{{ diagnosis.chanlun.sector_rotation_context.ma60.toFixed(2) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.sector_rotation_context.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.sector_rotation_context.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.sector_rotation_context.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V35: 多维背离确认（条件82）-->
        <div v-if="diagnosis.chanlun.multi_dim_divergence" class="metric-card multi-div">
          <div class="card-title">📊 多维背离确认（V35）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">量价背离</span>
              <span class="tag" :class="diagnosis.chanlun.multi_dim_divergence.price_volume_div ? 'tag-yellow' : 'tag-gray'">
                {{ diagnosis.chanlun.multi_dim_divergence.price_volume_div ? '⚠️ 背离' : '✅ 正常' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">MACD背离</span>
              <span class="tag" :class="diagnosis.chanlun.multi_dim_divergence.price_macd_div ? 'tag-yellow' : 'tag-gray'">
                {{ diagnosis.chanlun.multi_dim_divergence.price_macd_div ? '⚠️ 背离' : '✅ 正常' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">背离维度数</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_dim_divergence.divergence_count >= 2 ? '#ef4444' : '#22c55e' }">
                {{ diagnosis.chanlun.multi_dim_divergence.divergence_count }}/2
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_dim_divergence.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.multi_dim_divergence.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.multi_dim_divergence.confidence_adjust * 100).toFixed(2) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V36: 信号执行窗口（条件83）-->
        <div v-if="diagnosis.chanlun.execution_window" class="metric-card execution-window">
          <div class="card-title">🕐 信号执行窗口（V36）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">窗口状态</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.execution_window.window_status === 'optimal', 'tag-yellow': diagnosis.chanlun.execution_window.window_status === 'forming' || diagnosis.chanlun.execution_window.window_status === 'confirming', 'tag-red': diagnosis.chanlun.execution_window.window_status === 'expired' }">
                {{ diagnosis.chanlun.execution_window.window_status }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">推荐操作</span>
              <span class="kv-val">{{ diagnosis.chanlun.execution_window.optimal_action }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">信号年龄</span>
              <span class="kv-val">{{ diagnosis.chanlun.execution_window.bars_since_signal }} 根K线</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">剩余窗口</span>
              <span class="kv-val">{{ diagnosis.chanlun.execution_window.window_remaining }} 根</span>
            </div>
          </div>
        </div>

        <!-- V36: 多时间框架一致性（条件84）-->
        <div v-if="diagnosis.chanlun.tf_consistency" class="metric-card tf-consistency">
          <div class="card-title">📐 多时间框架一致性（V36）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">短期趋势</span>
              <span class="tag" :class="diagnosis.chanlun.tf_consistency.short_term_trend === 'up' ? 'tag-green' : diagnosis.chanlun.tf_consistency.short_term_trend === 'down' ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.tf_consistency.short_term_trend }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">中期趋势</span>
              <span class="tag" :class="diagnosis.chanlun.tf_consistency.mid_term_trend === 'up' ? 'tag-green' : diagnosis.chanlun.tf_consistency.mid_term_trend === 'down' ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.tf_consistency.mid_term_trend }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">一致性</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.tf_consistency.consistency.includes('bullish') && diagnosis.chanlun.tf_consistency.consistency !== 'consistent_bearish', 'tag-red': diagnosis.chanlun.tf_consistency.consistency === 'consistent_bearish' || diagnosis.chanlun.tf_consistency.consistency === 'conflicted', 'tag-yellow': diagnosis.chanlun.tf_consistency.consistency.includes('partial') }">
                {{ diagnosis.chanlun.tf_consistency.consistency }}
              </span>
            </div>
          </div>
        </div>

        <!-- V36: 风险调整后收益（条件85）-->
        <div v-if="diagnosis.chanlun.risk_adjusted_return" class="metric-card rar">
          <div class="card-title">⚖️ 风险调整后收益（V36）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">预期收益</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.risk_adjusted_return.expected_return_pct >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.risk_adjusted_return.expected_return_pct >= 0 ? '+' : '' }}{{ diagnosis.chanlun.risk_adjusted_return.expected_return_pct }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">风险调整收益</span>
              <span class="kv-val">{{ diagnosis.chanlun.risk_adjusted_return.risk_adjusted_return }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">预估最大回撤</span>
              <span class="kv-val" style="color:#ef4444">{{ diagnosis.chanlun.risk_adjusted_return.max_drawdown_est }}%</span>
            </div>
          </div>
        </div>

        <!-- V36: 信号时效性紧急度（条件86）-->
        <div v-if="diagnosis.chanlun.urgency_score" class="metric-card urgency">
          <div class="card-title">🚨 信号紧急度（V36）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">紧急等级</span>
              <span class="tag" :class="{ 'tag-red': diagnosis.chanlun.urgency_score.urgency_level === 'critical', 'tag-orange': diagnosis.chanlun.urgency_score.urgency_level === 'high', 'tag-yellow': diagnosis.chanlun.urgency_score.urgency_level === 'normal', 'tag-gray': diagnosis.chanlun.urgency_score.urgency_level === 'low' || diagnosis.chanlun.urgency_score.urgency_level === 'expired' }">
                {{ diagnosis.chanlun.urgency_score.urgency_level }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">紧急度分数</span>
              <span class="kv-val">{{ diagnosis.chanlun.urgency_score.urgency_score }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">操作建议</span>
              <span class="kv-val" style="font-size:0.85em;color:#888">{{ diagnosis.chanlun.urgency_score.action_hint }}</span>
            </div>
          </div>
        </div>

        <!-- V36: 市场环境综合评分（条件87）-->
        <div v-if="diagnosis.chanlun.market_composite" class="metric-card market-composite">
          <div class="card-title">🌍 市场环境综合（V36）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">市场状态</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.market_composite.market_regime === 'bullish', 'tag-red': diagnosis.chanlun.market_composite.market_regime === 'bearish', 'tag-gray': diagnosis.chanlun.market_composite.market_regime === 'neutral' }">
                {{ diagnosis.chanlun.market_composite.market_regime }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">综合评分</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.market_composite.market_score >= 0.65 ? '#22c55e' : diagnosis.chanlun.market_composite.market_score <= 0.35 ? '#ef4444' : '#f59e0b' }">
                {{ (diagnosis.chanlun.market_composite.market_score * 100).toFixed(0) }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">趋势得分</span>
              <span class="kv-val">{{ (diagnosis.chanlun.market_composite.trend_score * 100).toFixed(0) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">波动率得分</span>
              <span class="kv-val">{{ (diagnosis.chanlun.market_composite.vol_score * 100).toFixed(0) }}</span>
            </div>
          </div>
        </div>

        <!-- V36: 买卖点策略推荐（条件88）-->
        <div v-if="diagnosis.chanlun.strategy_recommendation" class="metric-card strategy-rec">
          <div class="card-title">🎯 策略推荐（V36）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">推荐策略</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.strategy_recommendation.strategy.includes('buy'), 'tag-red': diagnosis.chanlun.strategy_recommendation.strategy.includes('sell'), 'tag-gray': diagnosis.chanlun.strategy_recommendation.strategy === 'hold' || diagnosis.chanlun.strategy_recommendation.strategy === 'watch' }">
                {{ diagnosis.chanlun.strategy_recommendation.strategy }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">建议仓位</span>
              <span class="kv-val">{{ (Math.abs(diagnosis.chanlun.strategy_recommendation.position_size_pct) * 100).toFixed(0) }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">持仓周期</span>
              <span class="kv-val">{{ diagnosis.chanlun.strategy_recommendation.hold_period }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">风险等级</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.strategy_recommendation.risk_level === 'low', 'tag-yellow': diagnosis.chanlun.strategy_recommendation.risk_level === 'medium', 'tag-red': diagnosis.chanlun.strategy_recommendation.risk_level === 'high' || diagnosis.chanlun.strategy_recommendation.risk_level === 'very_high' }">
                {{ diagnosis.chanlun.strategy_recommendation.risk_level }}
              </span>
            </div>
          </div>
        </div>

        <!-- V37: 连续确认过滤（条件89）-->
        <div v-if="diagnosis.chanlun.consecutive_confirmation" class="metric-card consecutive-conf">
          <div class="card-title">✅ 连续确认（V37）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">确认状态</span>
              <span class="tag" :class="diagnosis.chanlun.consecutive_confirmation.confirmed ? 'tag-green' : 'tag-gray'">
                {{ diagnosis.chanlun.consecutive_confirmation.confirmed ? '已确认 ✅' : '未确认 ⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">确认K线</span>
              <span class="kv-val">{{ diagnosis.chanlun.consecutive_confirmation.confirm_bars }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.consecutive_confirmation.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.consecutive_confirmation.confidence_adjust < 0 ? '#ef4444' : '#888' }">
                {{ diagnosis.chanlun.consecutive_confirmation.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.consecutive_confirmation.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V37: 价格动能加速度（条件90）-->
        <div v-if="diagnosis.chanlun.momentum_acceleration" class="metric-card momentum-acc">
          <div class="card-title">⚡ 动能加速度（V37）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">动量方向</span>
              <span class="tag" :class="diagnosis.chanlun.momentum_acceleration.momentum_direction === 'accelerating' ? 'tag-green' : diagnosis.chanlun.momentum_acceleration.momentum_direction === 'decelerating' ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.momentum_acceleration.momentum_direction }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">加速度</span>
              <span class="kv-val">{{ diagnosis.chanlun.momentum_acceleration.acceleration.toFixed(4) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.momentum_acceleration.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.momentum_acceleration.confidence_adjust < 0 ? '#ef4444' : '#888' }">
                {{ diagnosis.chanlun.momentum_acceleration.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.momentum_acceleration.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V37: 波动率状态转换（条件91）-->
        <div v-if="diagnosis.chanlun.volatility_regime_change" class="metric-card vol-regime">
          <div class="card-title">📊 波动率转换（V37）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">波动率状态</span>
              <span class="tag" :class="{ 'tag-red': diagnosis.chanlun.volatility_regime_change.regime_change === 'low_to_high', 'tag-green': diagnosis.chanlun.volatility_regime_change.regime_change === 'high_to_low', 'tag-gray': diagnosis.chanlun.volatility_regime_change.regime_change === 'stable' }">
                {{ diagnosis.chanlun.volatility_regime_change.regime_change === 'low_to_high' ? '低→高 📈' : diagnosis.chanlun.volatility_regime_change.regime_change === 'high_to_low' ? '高→低 📉' : '稳定 ➡️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">波动率比率</span>
              <span class="kv-val">{{ diagnosis.chanlun.volatility_regime_change.vol_ratio.toFixed(2) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.volatility_regime_change.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.volatility_regime_change.confidence_adjust < 0 ? '#ef4444' : '#888' }">
                {{ diagnosis.chanlun.volatility_regime_change.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.volatility_regime_change.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V37: 时间序列关联（条件92）-->
        <div v-if="diagnosis.chanlun.temporal_correlation" class="metric-card temporal-cor">
          <div class="card-title">⏱️ 时序关联（V37）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">间隔K线</span>
              <span class="kv-val">{{ diagnosis.chanlun.temporal_correlation.interval_bars }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">间隔状态</span>
              <span class="tag" :class="{ 'tag-red': diagnosis.chanlun.temporal_correlation.interval_status === 'too_close', 'tag-yellow': diagnosis.chanlun.temporal_correlation.interval_status === 'too_far', 'tag-green': diagnosis.chanlun.temporal_correlation.interval_status === 'normal', 'tag-gray': diagnosis.chanlun.temporal_correlation.interval_status === 'first_signal' }">
                {{ diagnosis.chanlun.temporal_correlation.interval_status === 'too_close' ? '过近 ⚠️' : diagnosis.chanlun.temporal_correlation.interval_status === 'too_far' ? '过远 📍' : diagnosis.chanlun.temporal_correlation.interval_status === 'first_signal' ? '首次信号' : '正常 ✓' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.temporal_correlation.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.temporal_correlation.confidence_adjust < 0 ? '#ef4444' : '#888' }">
                {{ diagnosis.chanlun.temporal_correlation.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.temporal_correlation.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V37: 多时间框架动量一致性（条件93）-->
        <div v-if="diagnosis.chanlun.multi_tf_momentum" class="metric-card multi-tf-mom">
          <div class="card-title">📐 多TF动量一致性（V37）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">短期趋势</span>
              <span class="tag" :class="diagnosis.chanlun.multi_tf_momentum.short_trend === 'up' ? 'tag-green' : diagnosis.chanlun.multi_tf_momentum.short_trend === 'down' ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.multi_tf_momentum.short_trend }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">中期趋势</span>
              <span class="tag" :class="diagnosis.chanlun.multi_tf_momentum.mid_trend === 'up' ? 'tag-green' : diagnosis.chanlun.multi_tf_momentum.mid_trend === 'down' ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.multi_tf_momentum.mid_trend }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">长期趋势</span>
              <span class="tag" :class="diagnosis.chanlun.multi_tf_momentum.long_trend === 'up' ? 'tag-green' : diagnosis.chanlun.multi_tf_momentum.long_trend === 'down' ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.multi_tf_momentum.long_trend }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">一致性</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.multi_tf_momentum.consistency.includes('bullish'), 'tag-red': diagnosis.chanlun.multi_tf_momentum.consistency.includes('bearish') || diagnosis.chanlun.multi_tf_momentum.consistency === 'conflicted', 'tag-gray': diagnosis.chanlun.multi_tf_momentum.consistency === 'neutral' }">
                {{ diagnosis.chanlun.multi_tf_momentum.consistency }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_tf_momentum.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.multi_tf_momentum.confidence_adjust < 0 ? '#ef4444' : '#888' }">
                {{ diagnosis.chanlun.multi_tf_momentum.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.multi_tf_momentum.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V37: 信号综合质量排名（条件94）-->
        <div v-if="diagnosis.chanlun.quality_ranking" class="metric-card quality-rank">
          <div class="card-title">🏆 信号质量排名（V37）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">质量等级</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.quality_ranking.grade === 'S' || diagnosis.chanlun.quality_ranking.grade === 'A', 'tag-yellow': diagnosis.chanlun.quality_ranking.grade === 'B', 'tag-gray': diagnosis.chanlun.quality_ranking.grade === 'C', 'tag-red': diagnosis.chanlun.quality_ranking.grade === 'D' }">
                {{ diagnosis.chanlun.quality_ranking.grade }} 级
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">排名</span>
              <span class="kv-val">#{{ diagnosis.chanlun.quality_ranking.rank }} / {{ diagnosis.chanlun.quality_ranking.total }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">综合得分</span>
              <span class="kv-val">{{ diagnosis.chanlun.quality_ranking.score.toFixed(1) }}</span>
            </div>
          </div>
        </div>

        <!-- V38: 中枢结构完整性（条件95）-->
        <div v-if="diagnosis.chanlun.zs_structure_integrity" class="metric-card zs-integrity">
          <div class="card-title">🏗️ 中枢结构完整性（V38）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">完整度评分</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.zs_structure_integrity.integrity_score >= 0.7 ? '#22c55e' : diagnosis.chanlun.zs_structure_integrity.integrity_score < 0.4 ? '#ef4444' : '#f59e0b' }">
                {{ (diagnosis.chanlun.zs_structure_integrity.integrity_score * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">中枢笔数</span>
              <span class="kv-val">{{ diagnosis.chanlun.zs_structure_integrity.bi_count }} 笔</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">中枢范围</span>
              <span class="kv-val">{{ diagnosis.chanlun.zs_structure_integrity.zs_range.toFixed(2) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">结构状态</span>
              <span class="tag" :class="diagnosis.chanlun.zs_structure_integrity.is_complete ? 'tag-green' : 'tag-yellow'">
                {{ diagnosis.chanlun.zs_structure_integrity.is_complete ? '已完善 ✅' : '待完善 ⚠️' }}
              </span>
            </div>
          </div>
        </div>

        <!-- V38: 买卖点位置评分（条件96）-->
        <div v-if="diagnosis.chanlun.mmd_position_score" class="metric-card mmd-position">
          <div class="card-title">📍 买卖点位置评分（V38）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">当前位置</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.mmd_position_score.position_label === 'near_bottom', 'tag-red': diagnosis.chanlun.mmd_position_score.position_label === 'near_top', 'tag-yellow': diagnosis.chanlun.mmd_position_score.position_label === 'near_mid' }">
                {{ diagnosis.chanlun.mmd_position_score.position_label === 'near_bottom' ? '区间底部 🟢' : diagnosis.chanlun.mmd_position_score.position_label === 'near_top' ? '区间顶部 🔴' : '区间中部 🟡' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">位置百分位</span>
              <span class="kv-val">{{ (diagnosis.chanlun.mmd_position_score.position_pct * 100).toFixed(0) }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.mmd_position_score.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.mmd_position_score.confidence_adjust < 0 ? '#ef4444' : '#888' }">
                {{ diagnosis.chanlun.mmd_position_score.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.mmd_position_score.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
          </div>
        </div>

        <!-- V38: 中枢突破力度（条件98）-->
        <div v-if="diagnosis.chanlun.breakout_strength" class="metric-card breakout-strength">
          <div class="card-title">💥 中枢突破力度（V38）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">突破强度</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.breakout_strength.breakout_strength > 0.6 ? '#22c55e' : diagnosis.chanlun.breakout_strength.breakout_strength < 0.3 ? '#ef4444' : '#f59e0b' }">
                {{ (diagnosis.chanlun.breakout_strength.breakout_strength * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">量能确认</span>
              <span class="tag" :class="diagnosis.chanlun.breakout_strength.volume_confirmation ? 'tag-green' : 'tag-gray'">
                {{ diagnosis.chanlun.breakout_strength.volume_confirmation ? '放量 ✅' : '缩量 ⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">OBV趋势</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.breakout_strength.obv_trend === 'up', 'tag-red': diagnosis.chanlun.breakout_strength.obv_trend === 'down', 'tag-gray': diagnosis.chanlun.breakout_strength.obv_trend === 'flat' }">
                {{ diagnosis.chanlun.breakout_strength.obv_trend === 'up' ? '上升 📈' : diagnosis.chanlun.breakout_strength.obv_trend === 'down' ? '下降 📉' : '平稳 ➡️' }}
              </span>
            </div>
          </div>
        </div>

        <!-- V38: 多指标偏离度（条件99）-->
        <div v-if="diagnosis.chanlun.composite_deviation" class="metric-card composite-dev">
          <div class="card-title">📊 多指标偏离度（V38）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">综合偏离</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.composite_deviation.extreme ? '#ef4444' : '#22c55e' }">
                {{ diagnosis.chanlun.composite_deviation.extreme ? '⚠️ 极端偏离' : '正常 ✅' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">RSI偏离</span>
              <span class="kv-val">{{ (diagnosis.chanlun.composite_deviation.rsi_dev * 100).toFixed(0) }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">KDJ偏离</span>
              <span class="kv-val">{{ (diagnosis.chanlun.composite_deviation.kdj_dev * 100).toFixed(0) }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">BIAS偏离</span>
              <span class="kv-val">{{ (diagnosis.chanlun.composite_deviation.bias_dev * 100).toFixed(0) }}%</span>
            </div>
          </div>
        </div>

        <!-- V38: 信号衰减预警（条件100）-->
        <div v-if="diagnosis.chanlun.signal_decay_warning" class="metric-card signal-decay">
          <div class="card-title">⏰ 信号衰减预警（V38）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">衰减阶段</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.signal_decay_warning.decay_stage === 'fresh', 'tag-yellow': diagnosis.chanlun.signal_decay_warning.decay_stage === 'warning', 'tag-red': diagnosis.chanlun.signal_decay_warning.decay_stage === 'expired' }">
                {{ diagnosis.chanlun.signal_decay_warning.decay_stage === 'fresh' ? '新鲜 ✅' : diagnosis.chanlun.signal_decay_warning.decay_stage === 'warning' ? '衰减中 ⚠️' : '已过期 ❌' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">已过K线</span>
              <span class="kv-val">{{ diagnosis.chanlun.signal_decay_warning.bars_since_signal }} 根</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">价格漂移</span>
              <span class="kv-val">{{ diagnosis.chanlun.signal_decay_warning.price_drift_pct.toFixed(2) }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">剩余窗口</span>
              <span class="kv-val">{{ (diagnosis.chanlun.signal_decay_warning.remaining_window_pct * 100).toFixed(0) }}%</span>
            </div>
          </div>
        </div>

        <!-- V44: 趋势方向对齐验证（条件121）-->
        <div v-if="diagnosis.chanlun.trend_direction_alignment" class="metric-card v44-trend">
          <div class="card-title">🧭 趋势方向对齐（V44·条件121）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">趋势方向</span>
              <span class="tag" :class="diagnosis.chanlun.trend_direction_alignment.aligned ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.trend_direction_alignment.trend_direction }}
                {{ diagnosis.chanlun.trend_direction_alignment.aligned ? '✅ 对齐' : '❌ 逆势' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.trend_direction_alignment.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.trend_direction_alignment.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.trend_direction_alignment.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.trend_direction_alignment.msg }}</div>
          </div>
        </div>

        <!-- V44: 突破笔力度对比（条件122）-->
        <div v-if="diagnosis.chanlun.breakout_bi_strength_compare" class="metric-card v44-breakout">
          <div class="card-title">💪 突破笔力度对比（V44·条件122）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">量比</span>
              <span class="kv-val">{{ diagnosis.chanlun.breakout_bi_strength_compare.vol_ratio.toFixed(2) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">价格幅度比</span>
              <span class="kv-val">{{ diagnosis.chanlun.breakout_bi_strength_compare.price_ratio.toFixed(2) }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">突破有效性</span>
              <span class="tag" :class="diagnosis.chanlun.breakout_bi_strength_compare.strength_ok ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.breakout_bi_strength_compare.strength_ok ? '有效突破 ✅' : '力度不足 ⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.breakout_bi_strength_compare.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.breakout_bi_strength_compare.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.breakout_bi_strength_compare.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.breakout_bi_strength_compare.msg }}</div>
          </div>
        </div>

        <!-- V44: 回踩时间窗口过滤（条件123）-->
        <div v-if="diagnosis.chanlun.pullback_time_window" class="metric-card v44-pullback">
          <div class="card-title">⏱️ 回踩时间窗口（V44·条件123）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">信号后K线</span>
              <span class="kv-val">{{ diagnosis.chanlun.pullback_time_window.bars_since_signal }} 根</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">时效窗口</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.pullback_time_window.window_status === 'optimal', 'tag-yellow': diagnosis.chanlun.pullback_time_window.window_status === 'acceptable', 'tag-orange': diagnosis.chanlun.pullback_time_window.window_status === 'expired', 'tag-red': diagnosis.chanlun.pullback_time_window.window_status === 'critical' }">
                {{ { optimal: '最佳窗口 ✅', acceptable: '可接受 ⚠️', expired: '已过期 🔶', critical: '严重过期 ❌' }[diagnosis.chanlun.pullback_time_window.window_status] || diagnosis.chanlun.pullback_time_window.window_status }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.pullback_time_window.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.pullback_time_window.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.pullback_time_window.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.pullback_time_window.msg }}</div>
          </div>
        </div>

        <!-- V44: 波动率自适应阈值（条件124）-->
        <div v-if="diagnosis.chanlun.volatility_adaptive_threshold" class="metric-card v44-vol">
          <div class="card-title">🌊 波动率自适应（V44·条件124）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">年化波动率</span>
              <span class="kv-val">{{ (diagnosis.chanlun.volatility_adaptive_threshold.volatility * 100).toFixed(2) }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">波动率状态</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.volatility_adaptive_threshold.vol_regime === 'low', 'tag-blue': diagnosis.chanlun.volatility_adaptive_threshold.vol_regime === 'normal', 'tag-orange': diagnosis.chanlun.volatility_adaptive_threshold.vol_regime === 'high', 'tag-red': diagnosis.chanlun.volatility_adaptive_threshold.vol_regime === 'extreme' }">
                {{ { low: '低波动 🟢', normal: '正常 🟡', high: '高波动 🟠', extreme: '极端 🔴' }[diagnosis.chanlun.volatility_adaptive_threshold.vol_regime] || diagnosis.chanlun.volatility_adaptive_threshold.vol_regime }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">阈值乘数</span>
              <span class="kv-val">{{ diagnosis.chanlun.volatility_adaptive_threshold.threshold_multiplier.toFixed(2) }}×</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.volatility_adaptive_threshold.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.volatility_adaptive_threshold.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.volatility_adaptive_threshold.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.volatility_adaptive_threshold.msg }}</div>
          </div>
        </div>

        <!-- V44: 多指标背离共振（条件125）-->
        <div v-if="diagnosis.chanlun.multi_indicator_divergence_resonance" class="metric-card v44-div">
          <div class="card-title">🔀 多指标背离共振（V44·条件125）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">MACD背离</span>
              <span class="tag" :class="diagnosis.chanlun.multi_indicator_divergence_resonance.macd_divergence ? 'tag-green' : 'tag-gray'">
                {{ diagnosis.chanlun.multi_indicator_divergence_resonance.macd_divergence ? '有背离 ✅' : '无背离' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">RSI背离</span>
              <span class="tag" :class="diagnosis.chanlun.multi_indicator_divergence_resonance.rsi_divergence ? 'tag-green' : 'tag-gray'">
                {{ diagnosis.chanlun.multi_indicator_divergence_resonance.rsi_divergence ? '有背离 ✅' : '无背离' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">KDJ背离</span>
              <span class="tag" :class="diagnosis.chanlun.multi_indicator_divergence_resonance.kdj_divergence ? 'tag-green' : 'tag-gray'">
                {{ diagnosis.chanlun.multi_indicator_divergence_resonance.kdj_divergence ? '有背离 ✅' : '无背离' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">共振数量</span>
              <span class="kv-val">{{ diagnosis.chanlun.multi_indicator_divergence_resonance.resonance_count }}/3</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_indicator_divergence_resonance.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.multi_indicator_divergence_resonance.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.multi_indicator_divergence_resonance.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.multi_indicator_divergence_resonance.msg }}</div>
          </div>
        </div>

        <!-- V46: 趋势动能强度过滤（条件126）-->
        <div v-if="diagnosis.chanlun.trend_momentum_strength" class="metric-card v46-momentum">
          <div class="card-title">🚀 趋势动能强度（V46·条件126）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">ADX值</span>
              <span class="kv-val">{{ diagnosis.chanlun.trend_momentum_strength.adx_value }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">趋势强度</span>
              <span class="tag" :class="diagnosis.chanlun.trend_momentum_strength.trend_strength === 'strong' ? 'tag-green' : diagnosis.chanlun.trend_momentum_strength.trend_strength === 'moderate' ? 'tag-blue' : 'tag-orange'">
                {{ diagnosis.chanlun.trend_momentum_strength.trend_strength }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.trend_momentum_strength.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.trend_momentum_strength.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.trend_momentum_strength.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.trend_momentum_strength.msg }}</div>
          </div>
        </div>

        <!-- V46: 量价背离二次确认（条件127）-->
        <div v-if="diagnosis.chanlun.volume_price_divergence_secondary" class="metric-card v46-volprice">
          <div class="card-title">📊 量价背离二次确认（V46·条件127）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">突破量价</span>
              <span class="tag" :class="diagnosis.chanlun.volume_price_divergence_secondary.breakout_vol_price ? 'tag-green' : 'tag-gray'">
                {{ diagnosis.chanlun.volume_price_divergence_secondary.breakout_vol_price ? '有背离 ✅' : '无背离' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">回踩量价</span>
              <span class="tag" :class="diagnosis.chanlun.volume_price_divergence_secondary.pullback_vol_price ? 'tag-green' : 'tag-gray'">
                {{ diagnosis.chanlun.volume_price_divergence_secondary.pullback_vol_price ? '有背离 ✅' : '无背离' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">矛盾状态</span>
              <span class="tag" :class="diagnosis.chanlun.volume_price_divergence_secondary.conflict ? 'tag-red' : 'tag-green'">
                {{ diagnosis.chanlun.volume_price_divergence_secondary.conflict ? '⚠️ 矛盾' : '✅ 一致' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.volume_price_divergence_secondary.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.volume_price_divergence_secondary.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.volume_price_divergence_secondary.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.volume_price_divergence_secondary.msg }}</div>
          </div>
        </div>

        <!-- V46: 中枢突破真实性验证（条件128）-->
        <div v-if="diagnosis.chanlun.zs_breakout_authenticity" class="metric-card v46-zs">
          <div class="card-title">🎯 中枢突破真实性（V46·条件128）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">站稳K线</span>
              <span class="kv-val">{{ diagnosis.chanlun.zs_breakout_authenticity.bars_standing }} 根</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">突破有效性</span>
              <span class="tag" :class="diagnosis.chanlun.zs_breakout_authenticity.authentic ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.zs_breakout_authenticity.authentic ? '有效突破 ✅' : '疑似假突破 ⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.zs_breakout_authenticity.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.zs_breakout_authenticity.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.zs_breakout_authenticity.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.zs_breakout_authenticity.msg }}</div>
          </div>
        </div>

        <!-- V46: 多时间框架信号一致性（条件129）-->
        <div v-if="diagnosis.chanlun.multi_tf_signal_consistency" class="metric-card v46-tf">
          <div class="card-title">🔀 多TF信号一致性（V46·条件129）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">MA5斜率</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_tf_signal_consistency.ma5_slope > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.multi_tf_signal_consistency.ma5_slope > 0 ? '+' : '' }}{{ diagnosis.chanlun.multi_tf_signal_consistency.ma5_slope }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">MA10斜率</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_tf_signal_consistency.ma10_slope > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.multi_tf_signal_consistency.ma10_slope > 0 ? '+' : '' }}{{ diagnosis.chanlun.multi_tf_signal_consistency.ma10_slope }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">MA20斜率</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_tf_signal_consistency.ma20_slope > 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.multi_tf_signal_consistency.ma20_slope > 0 ? '+' : '' }}{{ diagnosis.chanlun.multi_tf_signal_consistency.ma20_slope }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">一致性</span>
              <span class="tag" :class="diagnosis.chanlun.multi_tf_signal_consistency.consistency === 'bullish' ? 'tag-green' : diagnosis.chanlun.multi_tf_signal_consistency.consistency === 'bearish' ? 'tag-red' : 'tag-orange'">
                {{ diagnosis.chanlun.multi_tf_signal_consistency.consistency }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_tf_signal_consistency.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.multi_tf_signal_consistency.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.multi_tf_signal_consistency.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.multi_tf_signal_consistency.msg }}</div>
          </div>
        </div>

        <!-- V46: 动态市场环境适配（条件130）-->
        <div v-if="diagnosis.chanlun.dynamic_market_regime" class="metric-card v46-regime">
          <div class="card-title">🌍 动态市场环境适配（V46·条件130）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">市场状态</span>
              <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.dynamic_market_regime.regime === 'trending', 'tag-red': diagnosis.chanlun.dynamic_market_regime.regime === 'high_volatility', 'tag-blue': diagnosis.chanlun.dynamic_market_regime.regime === 'low_volatility', 'tag-orange': diagnosis.chanlun.dynamic_market_regime.regime === 'ranging' }">
                {{ diagnosis.chanlun.dynamic_market_regime.regime }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">年波动率</span>
              <span class="kv-val">{{ diagnosis.chanlun.dynamic_market_regime.volatility }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">量能趋势</span>
              <span class="tag" :class="diagnosis.chanlun.dynamic_market_regime.volume_trend === 'increasing' ? 'tag-green' : diagnosis.chanlun.dynamic_market_regime.volume_trend === 'decreasing' ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.dynamic_market_regime.volume_trend }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.dynamic_market_regime.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.dynamic_market_regime.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.dynamic_market_regime.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.dynamic_market_regime.msg }}</div>
          </div>
        </div>

        <!-- V47: 后确认价格跟随过滤（条件131）-->
        <div v-if="diagnosis.chanlun.post_signal_price_follow_through" class="metric-card v47-follow">
          <div class="card-title">✅ 后确认价格跟随（V47·条件131）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">跟随状态</span>
              <span class="tag" :class="diagnosis.chanlun.post_signal_price_follow_through.followed ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.post_signal_price_follow_through.followed ? '通过 ✅' : '未通过 ⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">价格变化</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.post_signal_price_follow_through.follow_pct >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.post_signal_price_follow_through.follow_pct > 0 ? '+' : '' }}{{ diagnosis.chanlun.post_signal_price_follow_through.follow_pct }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">观察K线</span>
              <span class="kv-val">{{ diagnosis.chanlun.post_signal_price_follow_through.looked_bars }} 根</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.post_signal_price_follow_through.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.post_signal_price_follow_through.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.post_signal_price_follow_through.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.post_signal_price_follow_through.msg }}</div>
          </div>
        </div>

        <!-- V47: 信号有效性窗口（条件132）-->
        <div v-if="diagnosis.chanlun.signal_validity_window" class="metric-card v47-window">
          <div class="card-title">⏱️ 信号有效性窗口（V47·条件132）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">窗口大小</span>
              <span class="kv-val">{{ diagnosis.chanlun.signal_validity_window.window_bars }} 根K线</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">止损阈值</span>
              <span class="kv-val">{{ diagnosis.chanlun.signal_validity_window.window_pct }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">有效性</span>
              <span class="tag" :class="diagnosis.chanlun.signal_validity_window.valid ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.signal_validity_window.valid ? '有效 ✅' : '失效 ⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.signal_validity_window.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.signal_validity_window.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.signal_validity_window.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.signal_validity_window.msg }}</div>
          </div>
        </div>

        <!-- V48: 量价背离二次确认（条件134）-->
        <div v-if="diagnosis.chanlun.volume_price_divergence_secondary_v48" class="metric-card v48-volprice">
          <div class="card-title">📊 量价背离二次确认（V48·条件134）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">确认状态</span>
              <span class="tag" :class="diagnosis.chanlun.volume_price_divergence_secondary_v48.confirmed ? 'tag-green' : 'tag-yellow'">
                {{ diagnosis.chanlun.volume_price_divergence_secondary_v48.confirmed ? '已确认 ✅' : '未确认 ⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">VWAP偏离</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.volume_price_divergence_secondary_v48.divergence_pct >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.volume_price_divergence_secondary_v48.divergence_pct > 0 ? '+' : '' }}{{ diagnosis.chanlun.volume_price_divergence_secondary_v48.divergence_pct }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.volume_price_divergence_secondary_v48.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.volume_price_divergence_secondary_v48.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.volume_price_divergence_secondary_v48.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.volume_price_divergence_secondary_v48.msg }}</div>
          </div>
        </div>

        <!-- V48: 趋势强度加权（条件135）-->
        <div v-if="diagnosis.chanlun.trend_strength_weighting" class="metric-card v48-trend">
          <div class="card-title">📈 趋势强度加权（V48·条件135）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">ADX值</span>
              <span class="kv-val">{{ diagnosis.chanlun.trend_strength_weighting.adx_value }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">趋势强度</span>
              <span class="tag" :class="diagnosis.chanlun.trend_strength_weighting.adx_level === 'strong' ? 'tag-green' : diagnosis.chanlun.trend_strength_weighting.adx_level === 'medium' ? 'tag-blue' : 'tag-yellow'">
                {{ diagnosis.chanlun.trend_strength_weighting.adx_level === 'strong' ? '强趋势 ✅' : diagnosis.chanlun.trend_strength_weighting.adx_level === 'medium' ? '中趋势' : '弱趋势 ⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">MA对齐</span>
              <span class="tag" :class="diagnosis.chanlun.trend_strength_weighting.ma_alignment === 'up' ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.trend_strength_weighting.ma_alignment === 'up' ? '向上 ↑' : '向下 ↓' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.trend_strength_weighting.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.trend_strength_weighting.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.trend_strength_weighting.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.trend_strength_weighting.msg }}</div>
          </div>
        </div>

        <!-- V48: 动态风险收益比（条件136）-->
        <div v-if="diagnosis.chanlun.dynamic_risk_reward_ratio" class="metric-card v48-rrr">
          <div class="card-title">💰 动态风险收益比（V48·条件136）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">建议入场价</span>
              <span class="kv-val">{{ diagnosis.chanlun.dynamic_risk_reward_ratio.entry_price }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">止损位</span>
              <span class="kv-val" style="color:#ef4444">{{ diagnosis.chanlun.dynamic_risk_reward_ratio.stop_loss }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">第一止盈</span>
              <span class="kv-val" style="color:#22c55e">{{ diagnosis.chanlun.dynamic_risk_reward_ratio.take_profit_1 }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">风险收益比</span>
              <span class="tag" :class="diagnosis.chanlun.dynamic_risk_reward_ratio.risk_reward_ratio >= 2 ? 'tag-green' : diagnosis.chanlun.dynamic_risk_reward_ratio.risk_reward_ratio >= 1.5 ? 'tag-blue' : 'tag-red'">
                {{ diagnosis.chanlun.dynamic_risk_reward_ratio.quality_tier }}级 ({{ diagnosis.chanlun.dynamic_risk_reward_ratio.risk_reward_ratio }}:1)
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">ATR波动</span>
              <span class="kv-val">{{ diagnosis.chanlun.dynamic_risk_reward_ratio.atr }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.dynamic_risk_reward_ratio.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.dynamic_risk_reward_ratio.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.dynamic_risk_reward_ratio.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.dynamic_risk_reward_ratio.msg }}</div>
          </div>
        </div>

        <!-- V49: 突破力度二次验证（条件137）-->
        <div v-if="diagnosis.chanlun.breakout_strength_revalidation_v49" class="metric-card v49-breakout">
          <div class="card-title">⚡ 突破力度二次验证（V49·条件137）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">验证状态</span>
              <span class="tag" :class="diagnosis.chanlun.breakout_strength_revalidation_v49.confirmed ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.breakout_strength_revalidation_v49.confirmed ? '动能稳定 ✅' : '动能衰减 ⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">动能面积比</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.breakout_strength_revalidation_v49.hist_area_ratio >= 0.8 ? '#22c55e' : diagnosis.chanlun.breakout_strength_revalidation_v49.hist_area_ratio >= 0.6 ? '#f59e0b' : '#ef4444' }">
                {{ diagnosis.chanlun.breakout_strength_revalidation_v49.hist_area_ratio }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">突破前动能</span>
              <span class="kv-val">{{ diagnosis.chanlun.breakout_strength_revalidation_v49.break_force_before }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">突破后动能</span>
              <span class="kv-val">{{ diagnosis.chanlun.breakout_strength_revalidation_v49.break_force_after }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.breakout_strength_revalidation_v49.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.breakout_strength_revalidation_v49.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.breakout_strength_revalidation_v49.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.breakout_strength_revalidation_v49.msg }}</div>
          </div>
        </div>

        <!-- V49: 回踩结构完整性（条件138）-->
        <div v-if="diagnosis.chanlun.pullback_structure_integrity_v49" class="metric-card v49-pullback">
          <div class="card-title">🔍 回踩结构完整性（V49·条件138）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">验证状态</span>
              <span class="tag" :class="diagnosis.chanlun.pullback_structure_integrity_v49.confirmed ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.pullback_structure_integrity_v49.confirmed ? '结构完整 ✅' : '结构无效 ⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">结构质量</span>
              <span class="tag" :class="diagnosis.chanlun.pullback_structure_integrity_v49.structure_quality === 'strong' ? 'tag-green' : diagnosis.chanlun.pullback_structure_integrity_v49.structure_quality === 'weak' ? 'tag-yellow' : 'tag-red'">
                {{ diagnosis.chanlun.pullback_structure_integrity_v49.structure_quality === 'strong' ? '清晰 ✅' : diagnosis.chanlun.pullback_structure_integrity_v49.structure_quality === 'weak' ? '偏弱' : '无效 ⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.pullback_structure_integrity_v49.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.pullback_structure_integrity_v49.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.pullback_structure_integrity_v49.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.pullback_structure_integrity_v49.msg }}</div>
          </div>
        </div>

        <!-- V49: 中枢级别权重（条件139）-->
        <div v-if="diagnosis.chanlun.zhongshu_level_weight_v49" class="metric-card v49-zslevel">
          <div class="card-title">🏗️ 中枢级别权重（V49·条件139）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">中枢级别</span>
              <span class="tag" :class="diagnosis.chanlun.zhongshu_level_weight_v49.level === 'high' ? 'tag-green' : diagnosis.chanlun.zhongshu_level_weight_v49.level === 'medium' ? 'tag-blue' : 'tag-yellow'">
                {{ diagnosis.chanlun.zhongshu_level_weight_v49.level === 'high' ? '稳固（≥5笔）✅' : diagnosis.chanlun.zhongshu_level_weight_v49.level === 'medium' ? '正常（3-4笔）' : '较弱（1-2笔）⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">中枢线条数</span>
              <span class="kv-val">{{ diagnosis.chanlun.zhongshu_level_weight_v49.line_count }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.zhongshu_level_weight_v49.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.zhongshu_level_weight_v49.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.zhongshu_level_weight_v49.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.zhongshu_level_weight_v49.msg }}</div>
          </div>
        </div>

        <!-- V50: 板块联动分析（条件140）-->
        <div v-if="diagnosis.chanlun.sector_correlation_v50" class="metric-card v50-sector">
          <div class="card-title">🔗 板块联动分析（V50·条件140）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">联动状态</span>
              <span class="tag" :class="diagnosis.chanlun.sector_correlation_v50.correlated ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.sector_correlation_v50.correlated ? '板块联动确认 ✅' : '无联动/背离 ⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">联动幅度</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.sector_correlation_v50.correlation_pct >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.sector_correlation_v50.correlation_pct > 0 ? '+' : '' }}{{ diagnosis.chanlun.sector_correlation_v50.correlation_pct }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.sector_correlation_v50.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.sector_correlation_v50.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.sector_correlation_v50.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.sector_correlation_v50.msg }}</div>
          </div>
        </div>

        <!-- V50: 多时间框架共振验证（条件141）-->
        <div v-if="diagnosis.chanlun.multi_tf_resonance_v50" class="metric-card v50-mtf">
          <div class="card-title">⏱️ 多时间框架共振（V50·条件141）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">共振状态</span>
              <span class="tag" :class="diagnosis.chanlun.multi_tf_resonance_v50.resonant ? 'tag-green' : 'tag-yellow'">
                {{ diagnosis.chanlun.multi_tf_resonance_v50.resonant ? '多周期共振 ✅' : '部分一致/背离' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">对齐分数</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_tf_resonance_v50.alignment_score >= 0.67 ? '#22c55e' : diagnosis.chanlun.multi_tf_resonance_v50.alignment_score >= 0.33 ? '#f59e0b' : '#ef4444' }">
                {{ diagnosis.chanlun.multi_tf_resonance_v50.alignment_score }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_tf_resonance_v50.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.multi_tf_resonance_v50.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.multi_tf_resonance_v50.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.multi_tf_resonance_v50.msg }}</div>
          </div>
        </div>

        <!-- V50: 缠论级别递归验证（条件142）-->
        <div v-if="diagnosis.chanlun.level_recursive_validation_v50" class="metric-card v50-level">
          <div class="card-title">📐 级别递归验证（V50·条件142）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">验证状态</span>
              <span class="tag" :class="diagnosis.chanlun.level_recursive_validation_v50.validated ? 'tag-green' : 'tag-yellow'">
                {{ diagnosis.chanlun.level_recursive_validation_v50.validated ? '递归验证通过 ✅' : '未通过' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">级别质量</span>
              <span class="tag" :class="diagnosis.chanlun.level_recursive_validation_v50.level_quality === 'strong' ? 'tag-green' : diagnosis.chanlun.level_recursive_validation_v50.level_quality === 'normal' ? 'tag-blue' : 'tag-yellow'">
                {{ diagnosis.chanlun.level_recursive_validation_v50.level_quality === 'strong' ? '强（支撑/阻力位）✅' : diagnosis.chanlun.level_recursive_validation_v50.level_quality === 'normal' ? '中（结构稳固）' : '弱' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.level_recursive_validation_v50.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.level_recursive_validation_v50.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.level_recursive_validation_v50.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.level_recursive_validation_v50.msg }}</div>
          </div>
        </div>

        <!-- V50: 市场情绪指标融合（条件143）-->
        <div v-if="diagnosis.chanlun.market_sentiment_fusion_v50" class="metric-card v50-sentiment">
          <div class="card-title">🎭 市场情绪融合（V50·条件143）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">情绪状态</span>
              <span class="tag" :class="diagnosis.chanlun.market_sentiment_fusion_v50.sentiment === 'oversold' ? 'tag-green' : diagnosis.chanlun.market_sentiment_fusion_v50.sentiment === 'overbought' ? 'tag-red' : diagnosis.chanlun.market_sentiment_fusion_v50.sentiment === 'bullish' ? 'tag-blue' : 'tag-yellow'">
                {{ diagnosis.chanlun.market_sentiment_fusion_v50.sentiment === 'oversold' ? '超卖（逆向买入机会）✅' : diagnosis.chanlun.market_sentiment_fusion_v50.sentiment === 'overbought' ? '超买（逆向卖出机会）✅' : diagnosis.chanlun.market_sentiment_fusion_v50.sentiment === 'bullish' ? '偏多' : diagnosis.chanlun.market_sentiment_fusion_v50.sentiment === 'bearish' ? '偏空' : '中性' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">情绪评分</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.market_sentiment_fusion_v50.sentiment_score > 0 ? '#22c55e' : diagnosis.chanlun.market_sentiment_fusion_v50.sentiment_score < 0 ? '#ef4444' : '#6b7280' }">
                {{ diagnosis.chanlun.market_sentiment_fusion_v50.sentiment_score > 0 ? '+' : '' }}{{ diagnosis.chanlun.market_sentiment_fusion_v50.sentiment_score }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.market_sentiment_fusion_v50.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.market_sentiment_fusion_v50.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.market_sentiment_fusion_v50.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.market_sentiment_fusion_v50.msg }}</div>
          </div>
        </div>

        <!-- V51: 突破笔力度二次确认增强（条件144）-->
        <div v-if="diagnosis.chanlun.breakout_bi_strength_enhanced_v51" class="metric-card v51-breakout">
          <div class="card-title">⚡ 突破笔力度增强（V51·条件144）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">维度评分</span>
              <span class="tag" :class="diagnosis.chanlun.breakout_bi_strength_enhanced_v51.score >= 2 ? 'tag-green' : diagnosis.chanlun.breakout_bi_strength_enhanced_v51.score >= 1 ? 'tag-yellow' : 'tag-red'">
                {{ diagnosis.chanlun.breakout_bi_strength_enhanced_v51.score }}/3 维度
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">成交量比</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.breakout_bi_strength_enhanced_v51.vol_ok ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.breakout_bi_strength_enhanced_v51.vol_ratio }} {{ diagnosis.chanlun.breakout_bi_strength_enhanced_v51.vol_ok ? '✅' : '⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">价格比</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.breakout_bi_strength_enhanced_v51.price_ok ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.breakout_bi_strength_enhanced_v51.price_ratio }} {{ diagnosis.chanlun.breakout_bi_strength_enhanced_v51.price_ok ? '✅' : '⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">MACD面积比</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.breakout_bi_strength_enhanced_v51.macd_ok ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.breakout_bi_strength_enhanced_v51.macd_area_ratio }} {{ diagnosis.chanlun.breakout_bi_strength_enhanced_v51.macd_ok ? '✅' : '⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.breakout_bi_strength_enhanced_v51.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.breakout_bi_strength_enhanced_v51.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.breakout_bi_strength_enhanced_v51.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.breakout_bi_strength_enhanced_v51.msg }}</div>
          </div>
        </div>

        <!-- V51: 回踩笔深度+时间综合验证（条件145）-->
        <div v-if="diagnosis.chanlun.pullback_depth_time_v51" class="metric-card v51-pullback">
          <div class="card-title">📏 回踩深度+时间（V51·条件145）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">回踩深度</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.pullback_depth_time_v51.depth_ok ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.pullback_depth_time_v51.pullback_depth_pct }}% {{ diagnosis.chanlun.pullback_depth_time_v51.depth_ok ? '✅' : '⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">回踩时间</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.pullback_depth_time_v51.time_ok ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.pullback_depth_time_v51.pullback_bars }} 根K线 {{ diagnosis.chanlun.pullback_depth_time_v51.time_ok ? '✅' : '⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">综合状态</span>
              <span class="tag" :class="diagnosis.chanlun.pullback_depth_time_v51.combined_status === 'strong' ? 'tag-green' : diagnosis.chanlun.pullback_depth_time_v51.combined_status === 'normal' ? 'tag-blue' : 'tag-red'">
                {{ diagnosis.chanlun.pullback_depth_time_v51.combined_status === 'strong' ? '强确认 ✅' : diagnosis.chanlun.pullback_depth_time_v51.combined_status === 'normal' ? '中等' : '弱 ⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.pullback_depth_time_v51.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.pullback_depth_time_v51.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.pullback_depth_time_v51.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.pullback_depth_time_v51.msg }}</div>
          </div>
        </div>

        <!-- V51: 趋势强度综合评分（条件146）-->
        <div v-if="diagnosis.chanlun.trend_strength_composite_v51" class="metric-card v51-trend">
          <div class="card-title">📊 趋势强度综合评分（V51·条件146）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">综合评分</span>
              <span class="tag" :class="diagnosis.chanlun.trend_strength_composite_v51.total_score >= 3 ? 'tag-green' : diagnosis.chanlun.trend_strength_composite_v51.total_score >= 0 ? 'tag-yellow' : 'tag-red'">
                {{ diagnosis.chanlun.trend_strength_composite_v51.total_score }} 分
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">ADX值</span>
              <span class="kv-val">{{ diagnosis.chanlun.trend_strength_composite_v51.adx_value }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">MA斜率</span>
              <span class="tag" :class="diagnosis.chanlun.trend_strength_composite_v51.ma_slope === 'up' ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.trend_strength_composite_v51.ma_slope === 'up' ? '向上 ↑' : '向下 ↓' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">5日动量</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.trend_strength_composite_v51.momentum_5d >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.trend_strength_composite_v51.momentum_5d >= 0 ? '+' : '' }}{{ diagnosis.chanlun.trend_strength_composite_v51.momentum_5d }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">趋势强度</span>
              <span class="tag" :class="diagnosis.chanlun.trend_strength_composite_v51.trend_strength === 'strong' ? 'tag-green' : diagnosis.chanlun.trend_strength_composite_v51.trend_strength === 'medium' ? 'tag-blue' : diagnosis.chanlun.trend_strength_composite_v51.trend_strength === 'weak' ? 'tag-yellow' : 'tag-red'">
                {{ diagnosis.chanlun.trend_strength_composite_v51.trend_strength === 'strong' ? '强趋势 ✅' : diagnosis.chanlun.trend_strength_composite_v51.trend_strength === 'medium' ? '中趋势' : diagnosis.chanlun.trend_strength_composite_v51.trend_strength === 'weak' ? '弱趋势' : '逆势 ⚠️' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.trend_strength_composite_v51.confidence_adjust >= 0 ? '#22c55e' : '#ef4444' }">
                {{ diagnosis.chanlun.trend_strength_composite_v51.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.trend_strength_composite_v51.confidence_adjust * 100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.trend_strength_composite_v51.msg }}</div>
          </div>
        </div>

        <!-- V51: 交易决策建议（条件147）-->
        <div v-if="diagnosis.chanlun.trading_decision_v51" class="metric-card v51-decision">
          <div class="card-title">💰 交易决策建议（V51·条件147）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">决策建议</span>
              <span class="tag" :class="diagnosis.chanlun.trading_decision_v51.decision.includes('buy') ? 'tag-green' : diagnosis.chanlun.trading_decision_v51.decision.includes('sell') ? 'tag-red' : 'tag-yellow'">
                {{ diagnosis.chanlun.trading_decision_v51.decision.includes('aggressive') ? '🟢 积极' : diagnosis.chanlun.trading_decision_v51.decision.includes('cautious') ? '🟡 谨慎' : '⚪ 观望' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">质量评级</span>
              <span class="tag" :class="diagnosis.chanlun.trading_decision_v51.quality_tier === 'S' ? 'tag-green' : diagnosis.chanlun.trading_decision_v51.quality_tier === 'A' ? 'tag-blue' : diagnosis.chanlun.trading_decision_v51.quality_tier === 'B' ? 'tag-yellow' : 'tag-red'">
                {{ diagnosis.chanlun.trading_decision_v51.quality_tier }}级
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">建议入场价</span>
              <span class="kv-val">{{ diagnosis.chanlun.trading_decision_v51.entry_price }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">止损位</span>
              <span class="kv-val" style="color:#ef4444">{{ diagnosis.chanlun.trading_decision_v51.stop_loss }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">止盈1 / 止盈2</span>
              <span class="kv-val" style="color:#22c55e">{{ diagnosis.chanlun.trading_decision_v51.take_profit_1 }} / {{ diagnosis.chanlun.trading_decision_v51.take_profit_2 }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">风险收益比</span>
              <span class="tag" :class="diagnosis.chanlun.trading_decision_v51.risk_reward_ratio >= 2 ? 'tag-green' : diagnosis.chanlun.trading_decision_v51.risk_reward_ratio >= 1.5 ? 'tag-blue' : 'tag-red'">
                {{ diagnosis.chanlun.trading_decision_v51.risk_reward_ratio }}:1
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">ATR波动</span>
              <span class="kv-val">{{ diagnosis.chanlun.trading_decision_v51.atr }}</span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.trading_decision_v51.msg }}</div>
          </div>
        </div>

        <!-- V52: 量价持续确认（条件148）-->
        <div v-if="diagnosis.chanlun.volume_sustain_after_signal_v52" class="metric-card v52-volume">
          <div class="card-title">📊 量价持续确认（V52·条件148）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">成交量趋势</span>
              <span class="tag" :class="diagnosis.chanlun.volume_sustain_after_signal_v52.confirmed ? 'tag-green' : 'tag-yellow'">
                {{ diagnosis.chanlun.volume_sustain_after_signal_v52.vol_trend === 'sustaining' ? '✅ 维持' : diagnosis.chanlun.volume_sustain_after_signal_v52.vol_trend === 'shrinking' ? '⚠️ 萎缩' : '🟡 正常' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">量比（信号后/信号前）</span>
              <span class="kv-val">{{ diagnosis.chanlun.volume_sustain_after_signal_v52.vol_ratio_avg }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="tag" :class="diagnosis.chanlun.volume_sustain_after_signal_v52.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.volume_sustain_after_signal_v52.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.volume_sustain_after_signal_v52.confidence_adjust > 0 ? '+' : '' }}{{ diagnosis.chanlun.volume_sustain_after_signal_v52.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.volume_sustain_after_signal_v52.msg }}</div>
          </div>
        </div>

        <!-- V52: 多指标背离共振（条件149）-->
        <div v-if="diagnosis.chanlun.multi_indicator_divergence_fusion_v52" class="metric-card v52-divergence">
          <div class="card-title">🔀 多指标背离共振（V52·条件149）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">MACD背离</span>
              <span class="tag" :class="diagnosis.chanlun.multi_indicator_divergence_fusion_v52.macd_div ? 'tag-green' : 'tag-gray'">
                {{ diagnosis.chanlun.multi_indicator_divergence_fusion_v52.macd_div ? '✅' : '❌' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">RSI背离</span>
              <span class="tag" :class="diagnosis.chanlun.multi_indicator_divergence_fusion_v52.rsi_div ? 'tag-green' : 'tag-gray'">
                {{ diagnosis.chanlun.multi_indicator_divergence_fusion_v52.rsi_div ? '✅' : '❌' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">KDJ背离</span>
              <span class="tag" :class="diagnosis.chanlun.multi_indicator_divergence_fusion_v52.kdj_div ? 'tag-green' : 'tag-gray'">
                {{ diagnosis.chanlun.multi_indicator_divergence_fusion_v52.kdj_div ? '✅' : '❌' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">共振得分</span>
              <span class="tag" :class="diagnosis.chanlun.multi_indicator_divergence_fusion_v52.fusion_score >= 2 ? 'tag-green' : diagnosis.chanlun.multi_indicator_divergence_fusion_v52.fusion_score === 1 ? 'tag-yellow' : 'tag-red'">
                {{ diagnosis.chanlun.multi_indicator_divergence_fusion_v52.fusion_score }}/3
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.multi_indicator_divergence_fusion_v52.msg }}</div>
          </div>
        </div>

        <!-- V52: 近期极端价位检测（条件150）-->
        <div v-if="diagnosis.chanlun.recent_extreme_price_v52" class="metric-card v52-extreme">
          <div class="card-title">📍 近期极端价位检测（V52·条件150）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">60日区间位置</span>
              <span class="tag" :class="diagnosis.chanlun.recent_extreme_price_v52.is_extreme ? (diagnosis.chanlun.recent_extreme_price_v52.confidence_adjust > 0 ? 'tag-green' : 'tag-red') : 'tag-gray'">
                {{ diagnosis.chanlun.recent_extreme_price_v52.price_position }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">极端信号</span>
              <span class="tag" :class="diagnosis.chanlun.recent_extreme_price_v52.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.recent_extreme_price_v52.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.recent_extreme_price_v52.confidence_adjust > 0 ? '✅ 支撑/阻力有效' : diagnosis.chanlun.recent_extreme_price_v52.confidence_adjust < 0 ? '⚠️ 过度延伸' : '🟡 正常' }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.recent_extreme_price_v52.msg }}</div>
          </div>
        </div>

        <!-- V52: 市场环境健康评分（条件151）-->
        <div v-if="diagnosis.chanlun.market_regime_score_v52" class="metric-card v52-regime">
          <div class="card-title">🌍 市场环境健康评分（V52·条件151）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">波动率状态</span>
              <span class="tag" :class="diagnosis.chanlun.market_regime_score_v52.volatility_regime === 'low' ? 'tag-green' : diagnosis.chanlun.market_regime_score_v52.volatility_regime === 'high' ? 'tag-red' : 'tag-yellow'">
                {{ diagnosis.chanlun.market_regime_score_v52.volatility_regime === 'low' ? '✅ 低波动' : diagnosis.chanlun.market_regime_score_v52.volatility_regime === 'high' ? '⚠️ 高波动' : '🟡 正常波动' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">趋势健康度</span>
              <span class="tag" :class="diagnosis.chanlun.market_regime_score_v52.trend_health === 'sideways' ? 'tag-red' : 'tag-green'">
                {{ diagnosis.chanlun.market_regime_score_v52.trend_health === 'strong_uptrend' ? '📈 强趋势向上' : diagnosis.chanlun.market_regime_score_v52.trend_health === 'strong_downtrend' ? '📉 强趋势向下' : diagnosis.chanlun.market_regime_score_v52.trend_health === 'sideways' ? '➡️ 横盘' : '🔄 弱趋势' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">动量得分</span>
              <span class="tag" :class="diagnosis.chanlun.market_regime_score_v52.momentum_score > 0 ? 'tag-green' : diagnosis.chanlun.market_regime_score_v52.momentum_score < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.market_regime_score_v52.momentum_score > 0 ? '+' : '' }}{{ diagnosis.chanlun.market_regime_score_v52.momentum_score }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">环境评分</span>
              <span class="tag" :class="diagnosis.chanlun.market_regime_score_v52.regime_score >= 2 ? 'tag-green' : diagnosis.chanlun.market_regime_score_v52.regime_score <= -1 ? 'tag-red' : 'tag-yellow'">
                {{ diagnosis.chanlun.market_regime_score_v52.regime_score >= 2 ? '✅ 良好' : diagnosis.chanlun.market_regime_score_v52.regime_score <= -1 ? '⚠️ 较差' : '🟡 中性' }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.market_regime_score_v52.msg }}</div>
          </div>
        </div>

        <!-- V53: 趋势阶段识别与顺势确认（条件152）-->
        <div v-if="diagnosis.chanlun.trend_stage_follow_confirmation_v53" class="metric-card v53-trend">
          <div class="card-title">📈 趋势阶段识别（V53·条件152）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">趋势方向</span>
              <span class="tag" :class="diagnosis.chanlun.trend_stage_follow_confirmation_v53.trend_direction === 'strong_uptrend' ? 'tag-green' : diagnosis.chanlun.trend_stage_follow_confirmation_v53.trend_direction === 'strong_downtrend' ? 'tag-red' : 'tag-yellow'">
                {{ diagnosis.chanlun.trend_stage_follow_confirmation_v53.trend_direction === 'strong_uptrend' ? '📈 强上升趋势' : diagnosis.chanlun.trend_stage_follow_confirmation_v53.trend_direction === 'strong_downtrend' ? '📉 强下降趋势' : diagnosis.chanlun.trend_stage_follow_confirmation_v53.trend_direction === 'sideways' ? '➡️ 震荡' : '🔄 弱趋势' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">趋势阶段</span>
              <span class="tag" :class="diagnosis.chanlun.trend_stage_follow_confirmation_v53.trend_stage === 'early' ? 'tag-green' : diagnosis.chanlun.trend_stage_follow_confirmation_v53.trend_stage === 'late' ? 'tag-yellow' : 'tag-gray'">
                {{ diagnosis.chanlun.trend_stage_follow_confirmation_v53.trend_stage === 'early' ? '🟢 初期' : diagnosis.chanlun.trend_stage_follow_confirmation_v53.trend_stage === 'mid' ? '🟡 中期' : diagnosis.chanlun.trend_stage_follow_confirmation_v53.trend_stage === 'late' ? '🟠 晚期' : '🔵 震荡' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">顺势确认</span>
              <span class="tag" :class="diagnosis.chanlun.trend_stage_follow_confirmation_v53.is_following_trend ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.trend_stage_follow_confirmation_v53.is_following_trend ? '✅ 顺势' : '⚠️ 逆势' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="tag" :class="diagnosis.chanlun.trend_stage_follow_confirmation_v53.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.trend_stage_follow_confirmation_v53.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.trend_stage_follow_confirmation_v53.confidence_adjust > 0 ? '+' : '' }}{{ diagnosis.chanlun.trend_stage_follow_confirmation_v53.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.trend_stage_follow_confirmation_v53.msg }}</div>
          </div>
        </div>

        <!-- V53: ATR自适应止损距离（条件153）-->
        <div v-if="diagnosis.chanlun.atr_adaptive_stop_v53" class="metric-card v53-atr">
          <div class="card-title">📏 ATR自适应止损（V53·条件153）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">ATR(14)</span>
              <span class="kv-val">{{ diagnosis.chanlun.atr_adaptive_stop_v53.atr_value }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">ATR占比</span>
              <span class="kv-val">{{ diagnosis.chanlun.atr_adaptive_stop_v53.stop_distance_pct }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">建议仓位</span>
              <span class="tag" :class="diagnosis.chanlun.atr_adaptive_stop_v53.position_suggestion === 'high' ? 'tag-green' : diagnosis.chanlun.atr_adaptive_stop_v53.position_suggestion === 'cautious' ? 'tag-yellow' : 'tag-red'">
                {{ diagnosis.chanlun.atr_adaptive_stop_v53.position_suggestion === 'high' ? '🟢 重仓(70-100%)' : diagnosis.chanlun.atr_adaptive_stop_v53.position_suggestion === 'medium' ? '🟡 中等(40-70%)' : diagnosis.chanlun.atr_adaptive_stop_v53.position_suggestion === 'cautious' ? '🟠 轻仓(20-40%)' : '🔴 观望(0-20%)' }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.atr_adaptive_stop_v53.msg }}</div>
          </div>
        </div>

        <!-- V53: 中枢突破力度验证（条件154）-->
        <div v-if="diagnosis.chanlun.zs_breakout_strength_v53" class="metric-card v53-breakout">
          <div class="card-title">💪 中枢突破力度验证（V53·条件154）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">突破笔强度</span>
              <span class="kv-val">{{ diagnosis.chanlun.zs_breakout_strength_v53.breakout_strength }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">进入笔强度</span>
              <span class="kv-val">{{ diagnosis.chanlun.zs_breakout_strength_v53.entry_bi_strength }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">强度比值</span>
              <span class="tag" :class="diagnosis.chanlun.zs_breakout_strength_v53.confirmed ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.zs_breakout_strength_v53.strength_ratio }}x {{ diagnosis.chanlun.zs_breakout_strength_v53.confirmed ? '✅' : '⚠️' }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.zs_breakout_strength_v53.msg }}</div>
          </div>
        </div>

        <!-- V53: 信号质量综合分层（条件155）-->
        <div v-if="diagnosis.chanlun.signal_quality_tier_v53" class="metric-card v53-quality">
          <div class="card-title">🏆 信号质量分层（V53·条件155）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">质量等级</span>
              <span class="tag" :class="{
                'tag-green': diagnosis.chanlun.signal_quality_tier_v53.quality_tier === 'S',
                'tag-blue': diagnosis.chanlun.signal_quality_tier_v53.quality_tier === 'A',
                'tag-yellow': diagnosis.chanlun.signal_quality_tier_v53.quality_tier === 'B',
                'tag-orange': diagnosis.chanlun.signal_quality_tier_v53.quality_tier === 'C',
                'tag-red': diagnosis.chanlun.signal_quality_tier_v53.quality_tier === 'D',
              }">
                {{ diagnosis.chanlun.signal_quality_tier_v53.quality_tier === 'S' ? '⭐ S级' : diagnosis.chanlun.signal_quality_tier_v53.quality_tier === 'A' ? '🥇 A级' : diagnosis.chanlun.signal_quality_tier_v53.quality_tier === 'B' ? '🥈 B级' : diagnosis.chanlun.signal_quality_tier_v53.quality_tier === 'C' ? '🥉 C级' : '❌ D级' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">综合评分</span>
              <span class="kv-val">{{ diagnosis.chanlun.signal_quality_tier_v53.tier_score }}/100</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">评级标签</span>
              <span class="tag" :class="diagnosis.chanlun.signal_quality_tier_v53.position_recommendation === 'aggressive' ? 'tag-green' : diagnosis.chanlun.signal_quality_tier_v53.position_recommendation === 'cautious' ? 'tag-yellow' : 'tag-red'">
                {{ diagnosis.chanlun.signal_quality_tier_v53.tier_label }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">建议操作</span>
              <span class="tag" :class="{
                'tag-green': diagnosis.chanlun.signal_quality_tier_v53.position_recommendation === 'aggressive',
                'tag-blue': diagnosis.chanlun.signal_quality_tier_v53.position_recommendation === 'moderate',
                'tag-yellow': diagnosis.chanlun.signal_quality_tier_v53.position_recommendation === 'cautious',
                'tag-gray': diagnosis.chanlun.signal_quality_tier_v53.position_recommendation === 'wait',
                'tag-red': diagnosis.chanlun.signal_quality_tier_v53.position_recommendation === 'avoid',
              }">
                {{ diagnosis.chanlun.signal_quality_tier_v53.position_recommendation === 'aggressive' ? '积极买入' : diagnosis.chanlun.signal_quality_tier_v53.position_recommendation === 'moderate' ? '适度买入' : diagnosis.chanlun.signal_quality_tier_v53.position_recommendation === 'cautious' ? '谨慎买入' : diagnosis.chanlun.signal_quality_tier_v53.position_recommendation === 'wait' ? '观望' : '回避' }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.signal_quality_tier_v53.msg }}</div>
          </div>
        </div>

        <!-- V54: 多K线确认后确认（条件156）-->
        <div v-if="diagnosis.chanlun.multi_bar_confirmation_v54" class="metric-card v54-multibar">
          <div class="card-title">📊 多K线确认后确认（V54·条件156）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">确认状态</span>
              <span class="tag" :class="diagnosis.chanlun.multi_bar_confirmation_v54.confirmed ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.multi_bar_confirmation_v54.confirmed ? '✅ 确认通过' : '⚠️ 确认不足' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">连续确认K线</span>
              <span class="kv-val">{{ diagnosis.chanlun.multi_bar_confirmation_v54.confirm_bars }} / {{ diagnosis.chanlun.multi_bar_confirmation_v54.total_bars }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="tag" :class="diagnosis.chanlun.multi_bar_confirmation_v54.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.multi_bar_confirmation_v54.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.multi_bar_confirmation_v54.confidence_adjust > 0 ? '+' : '' }}{{ diagnosis.chanlun.multi_bar_confirmation_v54.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.multi_bar_confirmation_v54.msg }}</div>
          </div>
        </div>

        <!-- V54: 缺口风险评估（条件157）-->
        <div v-if="diagnosis.chanlun.gap_risk_assessment_v54" class="metric-card v54-gap">
          <div class="card-title">🕳️ 缺口风险评估（V54·条件157）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">缺口检测</span>
              <span class="tag" :class="diagnosis.chanlun.gap_risk_assessment_v54.has_gap ? (diagnosis.chanlun.gap_risk_assessment_v54.gap_direction === 'down' && diagnosis.chanlun.gap_risk_assessment_v54.confidence_adjust < 0 ? 'tag-red' : 'tag-green') : 'tag-gray'">
                {{ diagnosis.chanlun.gap_risk_assessment_v54.has_gap ? (diagnosis.chanlun.gap_risk_assessment_v54.gap_direction === 'up' ? '⬆️ 向上缺口' : '⬇️ 向下缺口') : '✅ 无缺口' }}
              </span>
            </div>
            <div class="kv-row" v-if="diagnosis.chanlun.gap_risk_assessment_v54.has_gap">
              <span class="kv-key">缺口幅度</span>
              <span class="kv-val">{{ diagnosis.chanlun.gap_risk_assessment_v54.gap_size_pct }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="tag" :class="diagnosis.chanlun.gap_risk_assessment_v54.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.gap_risk_assessment_v54.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.gap_risk_assessment_v54.confidence_adjust > 0 ? '+' : '' }}{{ diagnosis.chanlun.gap_risk_assessment_v54.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.gap_risk_assessment_v54.msg }}</div>
          </div>
        </div>

        <!-- V54: 波动率 regime 切换检测（条件158）-->
        <div v-if="diagnosis.chanlun.volatility_regime_change_v54" class="metric-card v54-vol">
          <div class="card-title">📈 波动率切换检测（V54·条件158）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">波动率状态</span>
              <span class="tag" :class="diagnosis.chanlun.volatility_regime_change_v54.regime === 'expanding' ? 'tag-green' : diagnosis.chanlun.volatility_regime_change_v54.regime === 'contracting' ? 'tag-yellow' : 'tag-gray'">
                {{ diagnosis.chanlun.volatility_regime_change_v54.regime === 'expanding' ? '📈 波动率扩张' : diagnosis.chanlun.volatility_regime_change_v54.regime === 'contracting' ? '📉 波动率收缩' : '➡️ 稳定' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">ATR变化</span>
              <span class="tag" :class="diagnosis.chanlun.volatility_regime_change_v54.atr_expansion_pct > 0 ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.volatility_regime_change_v54.atr_expansion_pct > 0 ? '+' : '' }}{{ diagnosis.chanlun.volatility_regime_change_v54.atr_expansion_pct }}%
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="tag" :class="diagnosis.chanlun.volatility_regime_change_v54.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.volatility_regime_change_v54.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.volatility_regime_change_v54.confidence_adjust > 0 ? '+' : '' }}{{ diagnosis.chanlun.volatility_regime_change_v54.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.volatility_regime_change_v54.msg }}</div>
          </div>
        </div>

        <!-- V54: 量价配合度评分（条件159）-->
        <div v-if="diagnosis.chanlun.volume_price_coordination_v54" class="metric-card v54-volprice">
          <div class="card-title">📊 量价配合度评分（V54·条件159）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">价格趋势</span>
              <span class="tag" :class="diagnosis.chanlun.volume_price_coordination_v54.price_trend === 'up' ? 'tag-green' : diagnosis.chanlun.volume_price_coordination_v54.price_trend === 'down' ? 'tag-red' : 'tag-yellow'">
                {{ diagnosis.chanlun.volume_price_coordination_v54.price_trend === 'up' ? '📈 上涨' : diagnosis.chanlun.volume_price_coordination_v54.price_trend === 'down' ? '📉 下跌' : '➡️ 震荡' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">量能趋势</span>
              <span class="tag" :class="diagnosis.chanlun.volume_price_coordination_v54.volume_trend === 'expanding' ? 'tag-green' : diagnosis.chanlun.volume_price_coordination_v54.volume_trend === 'shrinking' ? 'tag-yellow' : 'tag-gray'">
                {{ diagnosis.chanlun.volume_price_coordination_v54.volume_trend === 'expanding' ? '📈 放量' : diagnosis.chanlun.volume_price_coordination_v54.volume_trend === 'shrinking' ? '📉 缩量' : '➡️ 稳定' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">配合评分</span>
              <span class="tag" :class="diagnosis.chanlun.volume_price_coordination_v54.score >= 2 ? 'tag-green' : diagnosis.chanlun.volume_price_coordination_v54.score <= -2 ? 'tag-red' : 'tag-yellow'">
                {{ diagnosis.chanlun.volume_price_coordination_v54.score >= 2 ? '✅ 优秀' : diagnosis.chanlun.volume_price_coordination_v54.score <= -2 ? '🚨 恶化' : '🟡 一般' }} ({{ diagnosis.chanlun.volume_price_coordination_v54.score > 0 ? '+' : '' }}{{ diagnosis.chanlun.volume_price_coordination_v54.score }})
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="tag" :class="diagnosis.chanlun.volume_price_coordination_v54.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.volume_price_coordination_v54.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.volume_price_coordination_v54.confidence_adjust > 0 ? '+' : '' }}{{ diagnosis.chanlun.volume_price_coordination_v54.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.volume_price_coordination_v54.msg }}</div>
          </div>
        </div>

        <!-- V55: 分钟级多时间框架共振过滤（条件160）-->
        <div v-if="diagnosis.chanlun.multi_tf_resonance_filter_v55" class="metric-card v55-mtfr">
          <div class="card-title">🔗 多时间框架共振过滤（V55·条件160）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">共振状态</span>
              <span class="tag" :class="diagnosis.chanlun.multi_tf_resonance_filter_v55.resonated ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.multi_tf_resonance_filter_v55.resonated ? '✅ 共振确认' : '⚠️ 无共振/冲突' }}
              </span>
            </div>
            <div class="kv-row" v-for="(tf, idx) in diagnosis.chanlun.multi_tf_resonance_filter_v55.timeframes" :key="idx">
              <span class="kv-key">时间框架{{ idx + 1 }}</span>
              <span class="kv-val">{{ tf }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="tag" :class="diagnosis.chanlun.multi_tf_resonance_filter_v55.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.multi_tf_resonance_filter_v55.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.multi_tf_resonance_filter_v55.confidence_adjust > 0 ? '+' : '' }}{{ diagnosis.chanlun.multi_tf_resonance_filter_v55.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.multi_tf_resonance_filter_v55.msg }}</div>
          </div>
        </div>

        <!-- V55: 中枢级别权重自适应（条件161）-->
        <div v-if="diagnosis.chanlun.zhongshu_level_weight_v55" class="metric-card v55-zsw">
          <div class="card-title">💎 中枢级别权重（V55·条件161）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">中枢级别</span>
              <span class="tag" :class="diagnosis.chanlun.zhongshu_level_weight_v55.level === '月线' ? 'tag-gold' : diagnosis.chanlun.zhongshu_level_weight_v55.level === '周线' ? 'tag-green' : diagnosis.chanlun.zhongshu_level_weight_v55.level === '日线' ? 'tag-blue' : 'tag-gray'">
                {{ diagnosis.chanlun.zhongshu_level_weight_v55.level }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">权重加分</span>
              <span class="kv-val">+{{ diagnosis.chanlun.zhongshu_level_weight_v55.weight_bonus }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">综合评分</span>
              <span class="kv-val">{{ diagnosis.chanlun.zhongshu_level_weight_v55.level_score }}/10</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="tag" :class="diagnosis.chanlun.zhongshu_level_weight_v55.confidence_adjust > 0 ? 'tag-green' : 'tag-gray'">
                +{{ diagnosis.chanlun.zhongshu_level_weight_v55.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.zhongshu_level_weight_v55.msg }}</div>
          </div>
        </div>

        <!-- V55: 弱势股专项风险检测（条件162）-->
        <div v-if="diagnosis.chanlun.weak_stock_risk_v55" class="metric-card v55-wsr" :class="{ 'is-weak': diagnosis.chanlun.weak_stock_risk_v55.is_weak }">
          <div class="card-title">⚡ 弱势股风险检测（V55·条件162）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">风险等级</span>
              <span class="tag" :class="diagnosis.chanlun.weak_stock_risk_v55.is_weak ? 'tag-red' : 'tag-green'">
                {{ diagnosis.chanlun.weak_stock_risk_v55.is_weak ? '🚨 高风险' : '✅ 低风险' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">ATR/价格比</span>
              <span class="kv-val">{{ diagnosis.chanlun.weak_stock_risk_v55.volatility_ratio }}%</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">量比</span>
              <span class="kv-val">{{ diagnosis.chanlun.weak_stock_risk_v55.volume_ratio }}</span>
            </div>
            <div class="kv-row" v-if="diagnosis.chanlun.weak_stock_risk_v55.risk_factors.length > 0">
              <span class="kv-key">风险因素</span>
              <span class="kv-val tag-red" style="font-size:11px">{{ diagnosis.chanlun.weak_stock_risk_v55.risk_factors.join(' | ') }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="tag" :class="diagnosis.chanlun.weak_stock_risk_v55.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.weak_stock_risk_v55.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.weak_stock_risk_v55.confidence_adjust > 0 ? '+' : '' }}{{ diagnosis.chanlun.weak_stock_risk_v55.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.weak_stock_risk_v55.msg }}</div>
          </div>
        </div>

        <!-- V55: 信号与趋势方向对齐验证（条件163）-->
        <div v-if="diagnosis.chanlun.signal_trend_alignment_v55" class="metric-card v55-sta">
          <div class="card-title">🧭 信号趋势对齐验证（V55·条件163）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">对齐状态</span>
              <span class="tag" :class="diagnosis.chanlun.signal_trend_alignment_v55.aligned ? 'tag-green' : (diagnosis.chanlun.signal_trend_alignment_v55.confidence_adjust < 0 ? 'tag-red' : 'tag-yellow')">
                {{ diagnosis.chanlun.signal_trend_alignment_v55.aligned ? '✅ 顺势信号' : (diagnosis.chanlun.signal_trend_alignment_v55.confidence_adjust < 0 ? '⚠️ 逆势信号' : '➡️ 震荡市') }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">趋势方向</span>
              <span class="tag" :class="diagnosis.chanlun.signal_trend_alignment_v55.trend_direction === 'up' ? 'tag-green' : diagnosis.chanlun.signal_trend_alignment_v55.trend_direction === 'down' ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.signal_trend_alignment_v55.trend_direction === 'up' ? '📈 上升' : diagnosis.chanlun.signal_trend_alignment_v55.trend_direction === 'down' ? '📉 下降' : '➡️ 震荡' }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="tag" :class="diagnosis.chanlun.signal_trend_alignment_v55.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.signal_trend_alignment_v55.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.signal_trend_alignment_v55.confidence_adjust > 0 ? '+' : '' }}{{ diagnosis.chanlun.signal_trend_alignment_v55.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.signal_trend_alignment_v55.msg }}</div>
          </div>
        </div>

        <!-- V56: 假突破识别 -->
        <div v-if="diagnosis.chanlun.false_breakout_detection_v56" class="metric-card v56-fake">
          <div class="card-title">🔍 假突破识别 (164)</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">状态</span>
              <span class="tag" :class="diagnosis.chanlun.false_breakout_detection_v56.is_fake ? 'tag-red' : (diagnosis.chanlun.false_breakout_detection_v56.breakout_valid ? 'tag-green' : 'tag-yellow')">
                {{ diagnosis.chanlun.false_breakout_detection_v56.is_fake ? '🚨 假突破' : (diagnosis.chanlun.false_breakout_detection_v56.breakout_valid ? '✅ 真突破' : '➡️ 待确认') }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">回撤幅度</span><span class="kv-val">{{ diagnosis.chanlun.false_breakout_detection_v56.retracement_pct }}%</span></div>
            <div class="kv-row"><span class="kv-key">量比</span><span class="kv-val">{{ diagnosis.chanlun.false_breakout_detection_v56.volume_ratio }}</span></div>
            <div class="kv-row">
              <span class="kv-key">置信度</span>
              <span class="tag" :class="diagnosis.chanlun.false_breakout_detection_v56.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.false_breakout_detection_v56.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.false_breakout_detection_v56.confidence_adjust > 0 ? '+' : '' }}{{ diagnosis.chanlun.false_breakout_detection_v56.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.false_breakout_detection_v56.msg }}</div>
          </div>
        </div>

        <!-- V56: 中枢结构复杂度 -->
        <div v-if="diagnosis.chanlun.zhongshu_structure_complexity_v56" class="metric-card v56-zs">
          <div class="card-title">🏗️ 中枢结构复杂度 (165)</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">复杂度</span>
              <span class="tag" :class="diagnosis.chanlun.zhongshu_structure_complexity_v56.complexity === 'simple' ? 'tag-green' : (diagnosis.chanlun.zhongshu_structure_complexity_v56.complexity === 'moderate' ? 'tag-yellow' : (diagnosis.chanlun.zhongshu_structure_complexity_v56.complexity === 'complex' ? 'tag-orange' : 'tag-red'))">
                {{ diagnosis.chanlun.zhongshu_structure_complexity_v56.complexity === 'simple' ? '简单' : (diagnosis.chanlun.zhongshu_structure_complexity_v56.complexity === 'moderate' ? '中等' : (diagnosis.chanlun.zhongshu_structure_complexity_v56.complexity === 'complex' ? '复杂' : '高度复杂')) }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">重叠数</span><span class="kv-val">{{ diagnosis.chanlun.zhongshu_structure_complexity_v56.overlap_count }}</span></div>
            <div class="kv-row">
              <span class="kv-key">置信度</span>
              <span class="tag" :class="diagnosis.chanlun.zhongshu_structure_complexity_v56.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.zhongshu_structure_complexity_v56.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.zhongshu_structure_complexity_v56.confidence_adjust > 0 ? '+' : '' }}{{ diagnosis.chanlun.zhongshu_structure_complexity_v56.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.zhongshu_structure_complexity_v56.msg }}</div>
          </div>
        </div>

        <!-- V56: 波动率仓位建议 -->
        <div v-if="diagnosis.chanlun.volatility_adaptive_position_v56" class="metric-card v56-vol">
          <div class="card-title">📊 波动率仓位建议 (166)</div>
          <div class="card-body">
            <div class="kv-row"><span class="kv-key">ATR</span><span class="kv-val">{{ diagnosis.chanlun.volatility_adaptive_position_v56.atr_value }}%</span></div>
            <div class="kv-row">
              <span class="kv-key">波动等级</span>
              <span class="tag" :class="diagnosis.chanlun.volatility_adaptive_position_v56.volatility_level === 'low' ? 'tag-green' : (diagnosis.chanlun.volatility_adaptive_position_v56.volatility_level === 'normal' ? 'tag-blue' : (diagnosis.chanlun.volatility_adaptive_position_v56.volatility_level === 'high' ? 'tag-orange' : 'tag-red'))">
                {{ diagnosis.chanlun.volatility_adaptive_position_v56.volatility_level === 'low' ? '低波动' : (diagnosis.chanlun.volatility_adaptive_position_v56.volatility_level === 'normal' ? '正常' : (diagnosis.chanlun.volatility_adaptive_position_v56.volatility_level === 'high' ? '高波动' : '极高波动')) }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">仓位建议</span>
              <span class="tag" :class="diagnosis.chanlun.volatility_adaptive_position_v56.position_suggestion === 'high' ? 'tag-green' : (diagnosis.chanlun.volatility_adaptive_position_v56.position_suggestion === 'medium' ? 'tag-blue' : (diagnosis.chanlun.volatility_adaptive_position_v56.position_suggestion === 'cautious' ? 'tag-orange' : 'tag-red'))">
                {{ diagnosis.chanlun.volatility_adaptive_position_v56.position_suggestion === 'high' ? '重仓(70-100%)' : (diagnosis.chanlun.volatility_adaptive_position_v56.position_suggestion === 'medium' ? '中等(40-70%)' : (diagnosis.chanlun.volatility_adaptive_position_v56.position_suggestion === 'cautious' ? '轻仓(20-40%)' : '观望(0-20%)')) }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度</span>
              <span class="tag" :class="diagnosis.chanlun.volatility_adaptive_position_v56.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.volatility_adaptive_position_v56.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.volatility_adaptive_position_v56.confidence_adjust > 0 ? '+' : '' }}{{ diagnosis.chanlun.volatility_adaptive_position_v56.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.volatility_adaptive_position_v56.msg }}</div>
          </div>
        </div>

        <!-- V56: 多信号共振 -->
        <div v-if="diagnosis.chanlun.multi_signal_resonance_v56" class="metric-card v56-res">
          <div class="card-title">🎯 多信号共振评分 (167)</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">共振数</span>
              <span class="tag" :class="diagnosis.chanlun.multi_signal_resonance_v56.resonance_count >= 3 ? 'tag-green' : (diagnosis.chanlun.multi_signal_resonance_v56.resonance_count >= 2 ? 'tag-blue' : (diagnosis.chanlun.multi_signal_resonance_v56.resonance_count >= 1 ? 'tag-yellow' : 'tag-red'))">
                {{ diagnosis.chanlun.multi_signal_resonance_v56.resonance_count >= 3 ? '强共振' : (diagnosis.chanlun.multi_signal_resonance_v56.resonance_count >= 2 ? '弱共振' : (diagnosis.chanlun.multi_signal_resonance_v56.resonance_count >= 1 ? '单指标' : '无共振')) }}
              </span>
            </div>
            <div class="kv-row">
              <span class="kv-key">确认指标</span>
              <span class="kv-val" style="font-size:12px">{{ diagnosis.chanlun.multi_signal_resonance_v56.confirming_indicators.join(', ') || '无' }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度</span>
              <span class="tag" :class="diagnosis.chanlun.multi_signal_resonance_v56.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.multi_signal_resonance_v56.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.multi_signal_resonance_v56.confidence_adjust > 0 ? '+' : '' }}{{ diagnosis.chanlun.multi_signal_resonance_v56.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.multi_signal_resonance_v56.msg }}</div>
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

/* V12: 共振评分 */
.confluence-row { margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--border); }

/* V13: 成交量剖面 */
.vol-profile-row { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 12px; padding-top: 8px; border-top: 1px dashed var(--border); font-size: 12px; }
.vol-profile-row .kv-key { color: var(--text-dim); margin-right: 4px; }
.vol-profile-row .kv-val { color: var(--text-primary); font-weight: 500; }

/* V7: 信号质量报告 */
.signal-report { margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border); }
.kv-note { font-size: 11px; color: var(--text-dim); line-height: 1.6; margin-top: 4px; }
.risk-note { color: #f97316; }
/* V14: 信号增强注释 */
.enhancement-notes { margin-top: 6px; padding-top: 6px; border-top: 1px dashed var(--border); }
.enhancement-tag { font-size: 11px; color: #22c55e; margin-top: 2px; }

/* V15: K线形态 & 信号衰减 */
.kline-pattern-row { margin-top: 6px; display: flex; align-items: center; gap: 6px; }
.aging-row { margin-top: 6px; display: flex; align-items: center; gap: 6px; }
/* V16: 仓位建议 */
.position-sizing-row { margin-top: 6px; display: flex; align-items: center; gap: 6px; }
.position-notes { margin-top: 4px; display: flex; flex-direction: column; gap: 2px; }
.position-note-tag { font-size: 10px; color: var(--text-dim); padding-left: 4px; }

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

/* V21: 决策辅助 & 组合信号 */
.decision-rec .kv-note { font-weight: 600; color: var(--text-primary); }
.combo-signal .kv-val { color: #22c55e; font-weight: 600; }

/* V22: 波动率双重确认 & 量价背离 */
.vol-dual .kv-val { font-weight: 500; }
.vol-div .kv-note { color: var(--text-dim); line-height: 1.5; }

/* V26: 信号历史验证 */
.signal-history .kv-val { font-weight: 600; }
.signal-history .tag { font-size: 11px; }

/* V26: 动态风险收益优化 */
.dynamic-rr .kv-val { font-weight: 600; }
.dynamic-rr .kv-note { font-size: 11px; color: var(--text-dim); }

/* V26: 多标的对比评分 */
.cross-stock .kv-val { font-weight: 500; }
.cross-stock .tag { font-size: 10px; padding: 1px 6px; }

/* V27: 多级别区间套+结构位置+个股学习 */
.multi-tf .kv-val { font-weight: 600; }
.struct-pos .kv-val { font-weight: 500; }
.stock-profile .kv-val { font-weight: 500; }

/* V28: BOLL压缩+突破量价+ATR止损 */
.boll-squeeze .kv-val { font-weight: 600; }

/* V29: 趋势持续性 + 背离预警 */
.trend-cont .kv-val { font-weight: 600; }
.divergence-warn .kv-val { font-weight: 600; }
.breakout-vol .kv-val { font-weight: 600; }
.atr-stop .kv-val { font-weight: 600; }

/* V30: K线形态 + 中枢突破 + 区间止损 */
.kline-pattern .kv-val { font-weight: 600; }
.zs-breakout .kv-val { font-weight: 600; }
.range-stop .kv-val { font-weight: 600; }

/* V31: 均线排列 + MACD加速度 + 健康度报告 */
.ma-align .kv-val { font-weight: 600; }
.macd-accel .kv-val { font-weight: 600; }
.health-grade-A .card-title { color: #22c55e; }
.health-grade-B .card-title { color: #3b82f6; }
.health-grade-C .card-title { color: #f59e0b; }
.health-grade-D .card-title { color: #f97316; }
.health-grade-F .card-title { color: #ef4444; }

/* V32: 量价背离 + 信号优先级 + 支撑阻力位 */
.vol-price-div .kv-val { font-weight: 600; }
.signal-priority .kv-val { font-weight: 600; }
.sr-breakout .kv-val { font-weight: 600; }

/* V33: OBV能量潮 + MACD动能锥 + RSI动量确认 */
.obv-trend .kv-val { font-weight: 600; }
.macd-hist-area .kv-val { font-weight: 600; }
.rsi-momentum .kv-val { font-weight: 600; }

/* V34: 趋势动能 + 多指标共振 + 波动率环境 */
.trend-momentum .kv-val { font-weight: 600; }
.multi-resonance .kv-val { font-weight: 600; }
.volatility-regime .kv-val { font-weight: 600; }

/* V35: 市场环境 + 信号衰减 + 假信号过滤 + 动态SL/TP + 板块轮动 + 多维背离 */
.market-context .kv-val { font-weight: 600; }
.signal-decay .kv-val { font-weight: 600; }
.fake-filter .kv-val { font-weight: 600; }
.sl-tp .kv-val { font-weight: 600; }
.sector-rotation .kv-val { font-weight: 600; }
.multi-div .kv-val { font-weight: 600; }

/* V36: 执行窗口 + 多TF一致性 + 风险收益 + 紧急度 + 市场综合 + 策略推荐 */
.execution-window .kv-val { font-weight: 600; }
.tf-consistency .kv-val { font-weight: 600; }
.rar .kv-val { font-weight: 600; }
.urgency .kv-val { font-weight: 600; }
.market-composite .kv-val { font-weight: 600; }
.strategy-rec .kv-val { font-weight: 600; }

/* V37: 连续确认 + 动能加速度 + 波动率转换 + 时序关联 + 多TF动量 + 质量排名 */
.consecutive-conf .kv-val { font-weight: 600; }
.momentum-acc .kv-val { font-weight: 600; }
.vol-regime .kv-val { font-weight: 600; }
.temporal-cor .kv-val { font-weight: 600; }
.multi-tf-mom .kv-val { font-weight: 600; }
.quality-rank .kv-val { font-weight: 600; }
.zs-integrity .kv-val { font-weight: 600; }
.mmd-position .kv-val { font-weight: 600; }
.breakout-strength .kv-val { font-weight: 600; }
.composite-dev .kv-val { font-weight: 600; }
.signal-decay .kv-val { font-weight: 600; }

/* V44: 趋势对齐 + 突破力度 + 回踩窗口 + 波动自适应 + 背离共振 */
.v44-trend .kv-val { font-weight: 600; }
.v44-breakout .kv-val { font-weight: 600; }
.v44-pullback .kv-val { font-weight: 600; }
.v44-vol .kv-val { font-weight: 600; }
.v44-div .kv-val { font-weight: 600; }

/* V46: 趋势动能 + 量价背离 + 突破验证 + 多TF + 动态regime */
.v46-momentum .kv-val { font-weight: 600; }
.v46-volprice .kv-val { font-weight: 600; }
.v46-zs .kv-val { font-weight: 600; }
.v46-tf .kv-val { font-weight: 600; }
.v46-regime .kv-val { font-weight: 600; }

/* V50: 板块联动 + 多TF共振 + 级别递归 + 情绪融合 */
.v50-sector .kv-val { font-weight: 600; }
.v50-mtf .kv-val { font-weight: 600; }
.v50-level .kv-val { font-weight: 600; }
.v50-sentiment .kv-val { font-weight: 600; }

/* V52: 量价持续 + 多指标背离 + 极端价位 + 市场评分 */
.v52-volsustain .kv-val { font-weight: 600; }
.v52-divergence .kv-val { font-weight: 600; }
.v52-extreme .kv-val { font-weight: 600; }
.v52-regime .kv-val { font-weight: 600; }

/* V53: 趋势阶段 + ATR止损 + 突破力度 + 质量分层 */
.v53-trendstage .kv-val { font-weight: 600; }
.v53-atrstop .kv-val { font-weight: 600; }
.v53-breakout .kv-val { font-weight: 600; }
.v53-quality .kv-val { font-weight: 600; }

/* V54: 多K线确认 + 缺口风险 + 波动率切换 + 量价配合 */
.v54-multibar .kv-val { font-weight: 600; }
.v54-gap .kv-val { font-weight: 600; }
.v54-vol .kv-val { font-weight: 600; }
.v54-volprice .kv-val { font-weight: 600; }

/* V55: 多TF共振 + 中枢级别权重 + 弱势股风险 + 趋势对齐 */
.v55-mtfr .kv-val { font-weight: 600; }
.v55-zsw .kv-val { font-weight: 600; }
.v55-wsr.is-weak { border-color: #ef4444; }
.v55-sta .kv-val { font-weight: 600; }

/* V55 custom tag colors */
.tag-gold { background: #f59e0b; color: #fff; }
</style>
