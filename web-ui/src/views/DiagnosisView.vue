<script setup lang="ts">
// 股票技术诊断页面：综合缠论/MACD/BOLL/均线/成交量给出买卖决策建议。
// 对应后端 API：GET /api/v1/diagnosis/quick?market=SZ&code=000001

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchDiagnosis, fetchMultiStockComparison, formatError } from '../api'
import type { DiagnosisResult, MultiStockResult } from '../types'
import KlineChart from '../components/KlineChart.vue'
import type { Bar } from '../types'
import { fetchBars } from '../api'

const router = useRouter()

const market = ref<'SZ' | 'SH'>('SZ')
const code = ref('000001')
const loading = ref(false)
const error = ref('')
const diagnosis = ref<DiagnosisResult | null>(null)

// V64: 多股票对比模式
type MultiStockEntry = { market: 'SZ' | 'SH'; code: string }
const multiMode = ref(false)
const multiInputs = ref<MultiStockEntry[]>([
  { market: 'SZ', code: '000001' },
  { market: 'SZ', code: '000002' },
  { market: 'SH', code: '600000' },
])
const multiLoading = ref(false)
const multiError = ref('')
const multiResults = ref<MultiStockResult[]>([])

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
const v76IntegrityLabel = (level: string | null | undefined): string => {
  const map: Record<string, string> = { strong: '强信号', moderate: '中性', weak: '弱信号', invalid: '不建议' }
  return map[level ?? ''] ?? '—'
}
const v77QualityLabel = (level: string | null | undefined): string => {
  const map: Record<string, string> = { strong: '高置信度', moderate: '中等', weak: '低置信', mixed: '混合' }
  return map[level ?? ''] ?? '—'
}
const v78QualityLabel = (level: string | null | undefined): string => {
  const map: Record<string, string> = { strong: '高置信度', moderate: '中等', weak: '低置信', mixed: '混合' }
  return map[level ?? ''] ?? '—'
}
const v79QualityLabel = (level: string | null | undefined): string => {
  const map: Record<string, string> = { strong: '高置信度', moderate: '中等', weak: '低置信', mixed: '混合' }
  return map[level ?? ''] ?? '—'
}
const v80QualityLabel = (level: string | null | undefined): string => {
  const map: Record<string, string> = { strong: '高置信度', moderate: '中等', weak: '低置信', mixed: '混合' }
  return map[level ?? ''] ?? '—'
}
const multiResultsHaveConditionData = computed(() =>
  multiResults.value.some((r: MultiStockResult) => Object.keys(r.condition_breakdown || {}).length > 0)
)
const getConditionBreakdown = (r: MultiStockResult): Record<string, number> => r.condition_breakdown || {}

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

// V64: 多股票对比分析
function addStockEntry() {
  multiInputs.value.push({ market: 'SZ', code: '' })
}

function removeStockEntry(index: number) {
  if (multiInputs.value.length > 1) {
    multiInputs.value.splice(index, 1)
  }
}

async function runMultiStockComparison() {
  const valid = multiInputs.value.filter(e => e.code.trim().match(/^\d{6}$/))
  if (valid.length === 0) {
    multiError.value = '请至少输入一个有效的 6 位股票代码'
    return
  }
  multiLoading.value = true
  multiError.value = ''
  multiResults.value = []
  try {
    multiResults.value = (await fetchMultiStockComparison(valid.map(e => ({ market: e.market, code: e.code })))).stocks
  } catch (e) {
    multiError.value = formatError(e)
  } finally {
    multiLoading.value = false
  }
}

const confLevelColor = (conf: number): string => {
  if (conf >= 0.7) return '#22c55e'
  if (conf >= 0.5) return '#f59e0b'
  return '#ef4444'
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
      <div class="mode-toggle">
        <button :class="{ active: !multiMode }" @click="multiMode = false">单股诊断</button>
        <button :class="{ active: multiMode }" @click="multiMode = !multiMode">V64 多股对比</button>
      </div>
      <template v-if="!multiMode">
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
      </template>
      <template v-else>
      <div class="multi-input-area">
        <div v-for="(entry, idx) in multiInputs" :key="idx" class="multi-entry">
          <select v-model="entry.market" class="market-select">
            <option value="SZ">深市</option>
            <option value="SH">沪市</option>
          </select>
          <input
            v-model="entry.code"
            placeholder="6 位代码"
            maxlength="6"
            class="code-input"
          />
          <button class="ghost btn-remove" :disabled="multiInputs.length <= 1" @click="removeStockEntry(idx)">✕</button>
        </div>
        <button class="ghost" @click="addStockEntry">+ 添加股票</button>
        <button class="primary" :disabled="multiLoading" @click="runMultiStockComparison">
          {{ multiLoading ? '对比中…' : '📊 多股对比' }}
        </button>
      </div>
      <span v-if="multiError" class="error-msg">{{ multiError }}</span>
      </template>
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
          <!-- V76: 四维验证摘要 -->
          <div v-if="diagnosis.v76_summary" class="v76-summary-row">
            <span class="v76-tag" :class="{
              'v76-strong': diagnosis.v76_summary.structure_integrity === 'strong',
              'v76-moderate': diagnosis.v76_summary.structure_integrity === 'moderate',
              'v76-weak': diagnosis.v76_summary.structure_integrity === 'weak',
              'v76-invalid': diagnosis.v76_summary.structure_integrity === 'invalid',
            }">
              🎯 V76有效性{{ v76IntegrityLabel(diagnosis.v76_summary.structure_integrity) }}
              · {{ diagnosis.v76_summary.validity_score != null ? (diagnosis.v76_summary.validity_score * 100).toFixed(0) + '%' : '—' }}
            </span>
          </div>
          <!-- V77: 四维度量摘要 -->
          <div v-if="diagnosis.v77_summary" class="v77-summary-row">
            <span class="v77-tag" :class="{
              'v77-strong': diagnosis.v77_summary.quality_level === 'strong',
              'v77-moderate': diagnosis.v77_summary.quality_level === 'moderate',
              'v77-weak': diagnosis.v77_summary.quality_level === 'weak',
              'v77-mixed': diagnosis.v77_summary.quality_level === 'mixed',
            }">
              📊 V77四维度量{{ v77QualityLabel(diagnosis.v77_summary.quality_level) }}
              · 正{{ diagnosis.v77_summary.positive_count ?? '—' }}/负{{ diagnosis.v77_summary.negative_count ?? '—' }}
              · 调整{{ diagnosis.v77_summary.total_adjust != null ? (diagnosis.v77_summary.total_adjust * 100 > 0 ? '+' : '') + diagnosis.v77_summary.total_adjust.toFixed(0) + '%' : '—' }}
            </span>
          </div>
          <div v-if="diagnosis.v78_summary" class="v78-summary-row">
            <span class="v78-tag" :class="{
              'v78-strong': diagnosis.v78_summary.quality_level === 'strong',
              'v78-moderate': diagnosis.v78_summary.quality_level === 'moderate',
              'v78-weak': diagnosis.v78_summary.quality_level === 'weak',
              'v78-mixed': diagnosis.v78_summary.quality_level === 'mixed',
            }">
              🔭 V78四维度量{{ v78QualityLabel(diagnosis.v78_summary.quality_level) }}
              · 正{{ diagnosis.v78_summary.positive_count ?? '—' }}/负{{ diagnosis.v78_summary.negative_count ?? '—' }}
              · 调整{{ diagnosis.v78_summary.total_adjust != null ? (diagnosis.v78_summary.total_adjust * 100 > 0 ? '+' : '') + diagnosis.v78_summary.total_adjust.toFixed(0) + '%' : '—' }}
            </span>
          </div>
          <div v-if="diagnosis.v79_summary" class="v79-summary-row">
            <span class="v79-tag" :class="{
              'v79-strong': diagnosis.v79_summary.quality_level === 'strong',
              'v79-moderate': diagnosis.v79_summary.quality_level === 'moderate',
              'v79-weak': diagnosis.v79_summary.quality_level === 'weak',
              'v79-mixed': diagnosis.v79_summary.quality_level === 'mixed',
            }">
              🎯 V79四维度量{{ v79QualityLabel(diagnosis.v79_summary.quality_level) }}
              · 正{{ diagnosis.v79_summary.positive_count ?? '—' }}/负{{ diagnosis.v79_summary.negative_count ?? '—' }}
              · 调整{{ diagnosis.v79_summary.total_adjust != null ? (diagnosis.v79_summary.total_adjust * 100 > 0 ? '+' : '') + diagnosis.v79_summary.total_adjust.toFixed(0) + '%' : '—' }}
            </span>
          </div>
          <div v-if="diagnosis.v80_summary" class="v80-summary-row">
            <span class="v80-tag" :class="{
              'v80-strong': diagnosis.v80_summary.quality_level === 'strong',
              'v80-moderate': diagnosis.v80_summary.quality_level === 'moderate',
              'v80-weak': diagnosis.v80_summary.quality_level === 'weak',
              'v80-mixed': diagnosis.v80_summary.quality_level === 'mixed',
            }">
              🔬 V80四维度量{{ v80QualityLabel(diagnosis.v80_summary.quality_level) }}
              · 正{{ diagnosis.v80_summary.positive_count ?? '—' }}/负{{ diagnosis.v80_summary.negative_count ?? '—' }}
              · 调整{{ diagnosis.v80_summary.total_adjust != null ? (diagnosis.v80_summary.total_adjust * 100 > 0 ? '+' : '') + diagnosis.v80_summary.total_adjust.toFixed(0) + '%' : '—' }}
            </span>
          </div>
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

        <!-- V57: 回踩幅度与时间双重过滤 -->
        <div v-if="diagnosis.chanlun.pullback_filter_v57" class="metric-card v57-pullback">
          <div class="card-title">📐 回踩过滤检测 (168)</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">过滤结果</span>
              <span class="tag" :class="diagnosis.chanlun.pullback_filter_v57.pass_filter ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.pullback_filter_v57.pass_filter ? '✅ 通过' : '🚨 未通过' }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">回踩深度</span><span class="kv-val">{{ diagnosis.chanlun.pullback_filter_v57.pullback_depth_pct }}%</span></div>
            <div class="kv-row"><span class="kv-key">检查K线</span><span class="kv-val">{{ diagnosis.chanlun.pullback_filter_v57.pullback_bars }}根</span></div>
            <div class="kv-row">
              <span class="kv-key">置信度</span>
              <span class="tag" :class="diagnosis.chanlun.pullback_filter_v57.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.pullback_filter_v57.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.pullback_filter_v57.confidence_adjust > 0 ? '+' : '' }}{{ diagnosis.chanlun.pullback_filter_v57.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.pullback_filter_v57.msg }}</div>
          </div>
        </div>

        <!-- V57: 突破力度验证 -->
        <div v-if="diagnosis.chanlun.breakout_strength_validation_v57" class="metric-card v57-breakout">
          <div class="card-title">💪 突破力度验证 (169)</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">力度达标</span>
              <span class="tag" :class="diagnosis.chanlun.breakout_strength_validation_v57.strength_adequate ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.breakout_strength_validation_v57.strength_adequate ? '✅ 充足' : '⚠️ 不足' }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">力度比</span><span class="kv-val">{{ diagnosis.chanlun.breakout_strength_validation_v57.force_ratio }}</span></div>
            <div class="kv-row"><span class="kv-key">量比</span><span class="kv-val">{{ diagnosis.chanlun.breakout_strength_validation_v57.volume_ratio }}</span></div>
            <div class="kv-row">
              <span class="kv-key">置信度</span>
              <span class="tag" :class="diagnosis.chanlun.breakout_strength_validation_v57.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.breakout_strength_validation_v57.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.breakout_strength_validation_v57.confidence_adjust > 0 ? '+' : '' }}{{ diagnosis.chanlun.breakout_strength_validation_v57.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.breakout_strength_validation_v57.msg }}</div>
          </div>
        </div>

        <!-- V57: 中枢背驰检测 -->
        <div v-if="diagnosis.chanlun.zs_divergence_check_v57" class="metric-card v57-div">
          <div class="card-title">🔍 中枢背驰检测 (170)</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">背驰状态</span>
              <span class="tag" :class="!diagnosis.chanlun.zs_divergence_check_v57.has_divergence ? 'tag-green' : 'tag-orange'">
                {{ diagnosis.chanlun.zs_divergence_check_v57.has_divergence ? '⚠️ 有背驰' : '✅ 无背驰' }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">背驰类型</span><span class="kv-val">{{ diagnosis.chanlun.zs_divergence_check_v57.divergence_type }}</span></div>
            <div class="kv-row">
              <span class="kv-key">置信度</span>
              <span class="tag" :class="diagnosis.chanlun.zs_divergence_check_v57.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.zs_divergence_check_v57.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.zs_divergence_check_v57.confidence_adjust > 0 ? '+' : '' }}{{ diagnosis.chanlun.zs_divergence_check_v57.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.zs_divergence_check_v57.msg }}</div>
          </div>
        </div>

        <!-- V57: 信号衰减检测 -->
        <div v-if="diagnosis.chanlun.signal_decay_detection_v57" class="metric-card v57-decay">
          <div class="card-title">📉 信号衰减检测 (171)</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">衰减状态</span>
              <span class="tag" :class="!diagnosis.chanlun.signal_decay_detection_v57.is_decaying ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.signal_decay_detection_v57.is_decaying ? '🚨 衰减中' : '✅ 有效' }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">价格趋势</span><span class="kv-val">{{ diagnosis.chanlun.signal_decay_detection_v57.price_trend }}</span></div>
            <div class="kv-row"><span class="kv-key">动量</span><span class="kv-val">{{ diagnosis.chanlun.signal_decay_detection_v57.trend_momentum }}%</span></div>
            <div class="kv-row">
              <span class="kv-key">置信度</span>
              <span class="tag" :class="diagnosis.chanlun.signal_decay_detection_v57.confidence_adjust > 0 ? 'tag-green' : diagnosis.chanlun.signal_decay_detection_v57.confidence_adjust < 0 ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.signal_decay_detection_v57.confidence_adjust > 0 ? '+' : '' }}{{ diagnosis.chanlun.signal_decay_detection_v57.confidence_adjust }}
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.signal_decay_detection_v57.msg }}</div>
          </div>
        </div>

        <!-- V58: 多时间框架趋势一致性 -->
        <div v-if="diagnosis.chanlun.multi_tf_trend_consistency_v58" class="metric-card v58-tf">
          <div class="card-title">📊 V58 多时间框架趋势一致性（条件172）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">排列状态</span>
              <span class="tag" :class="diagnosis.chanlun.multi_tf_trend_consistency_v58.bullish_alignment ? 'tag-green' : diagnosis.chanlun.multi_tf_trend_consistency_v58.bearish_alignment ? 'tag-red' : 'tag-gray'">
                {{ diagnosis.chanlun.multi_tf_trend_consistency_v58.bullish_alignment ? '✅ 多头排列' : diagnosis.chanlun.multi_tf_trend_consistency_v58.bearish_alignment ? '🔴 空头排列' : '⚪ 交错' }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">MA5</span><span class="kv-val">{{ diagnosis.chanlun.multi_tf_trend_consistency_v58.short_ma }}</span></div>
            <div class="kv-row"><span class="kv-key">MA20</span><span class="kv-val">{{ diagnosis.chanlun.multi_tf_trend_consistency_v58.mid_ma }}</span></div>
            <div class="kv-row"><span class="kv-key">MA60</span><span class="kv-val">{{ diagnosis.chanlun.multi_tf_trend_consistency_v58.long_ma }}</span></div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_tf_trend_consistency_v58.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.multi_tf_trend_consistency_v58.confidence_adjust < 0 ? '#ef4444' : '#9ca3af' }">
                {{ diagnosis.chanlun.multi_tf_trend_consistency_v58.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.multi_tf_trend_consistency_v58.confidence_adjust*100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.multi_tf_trend_consistency_v58.msg }}</div>
          </div>
        </div>

        <!-- V58: 成交量堆积验证 -->
        <div v-if="diagnosis.chanlun.volume_accumulation_validation_v58" class="metric-card v58-vol">
          <div class="card-title">📈 V58 成交量堆积验证（条件173）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">量能状态</span>
              <span class="tag" :class="diagnosis.chanlun.volume_accumulation_validation_v58.volume_adequate ? 'tag-green' : 'tag-red'">
                {{ diagnosis.chanlun.volume_accumulation_validation_v58.volume_adequate ? '✅ 量能充足' : '🚨 无量突破' }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">量比</span><span class="kv-val">{{ diagnosis.chanlun.volume_accumulation_validation_v58.volume_ratio }}</span></div>
            <div class="kv-row"><span class="kv-key">近5日均量</span><span class="kv-val">{{ diagnosis.chanlun.volume_accumulation_validation_v58.recent_vol }}</span></div>
            <div class="kv-row"><span class="kv-key">近20日均量</span><span class="kv-val">{{ diagnosis.chanlun.volume_accumulation_validation_v58.avg_vol_20 }}</span></div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.volume_accumulation_validation_v58.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.volume_accumulation_validation_v58.confidence_adjust < 0 ? '#ef4444' : '#9ca3af' }">
                {{ diagnosis.chanlun.volume_accumulation_validation_v58.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.volume_accumulation_validation_v58.confidence_adjust*100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.volume_accumulation_validation_v58.msg }}</div>
          </div>
        </div>

        <!-- V58: ATR自适应止损 -->
        <div v-if="diagnosis.chanlun.atr_adaptive_stop_v58" class="metric-card v58-atr">
          <div class="card-title">🛡️ V58 ATR自适应止损距离（条件174）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">波动率等级</span>
              <span class="tag" :class="diagnosis.chanlun.atr_adaptive_stop_v58.volatility_level === 'low' ? 'tag-green' : diagnosis.chanlun.atr_adaptive_stop_v58.volatility_level === 'medium' ? 'tag-blue' : diagnosis.chanlun.atr_adaptive_stop_v58.volatility_level === 'high' ? 'tag-orange' : 'tag-red'">
                {{ { low: '低波动', medium: '正常', high: '高波动', extreme: '极高波动', unknown: '未知' }[diagnosis.chanlun.atr_adaptive_stop_v58.volatility_level] || '未知' }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">ATR(14)</span><span class="kv-val">{{ diagnosis.chanlun.atr_adaptive_stop_v58.atr_14 }}</span></div>
            <div class="kv-row"><span class="kv-key">建议止损位</span><span class="kv-val">{{ diagnosis.chanlun.atr_adaptive_stop_v58.stop_loss_price }}</span></div>
            <div class="kv-row"><span class="kv-key">止损距离</span><span class="kv-val">{{ diagnosis.chanlun.atr_adaptive_stop_v58.stop_distance_pct }}%</span></div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span class="kv-val" :style="{ color: diagnosis.chanlun.atr_adaptive_stop_v58.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.atr_adaptive_stop_v58.confidence_adjust < 0 ? '#ef4444' : '#9ca3af' }">
                {{ diagnosis.chanlun.atr_adaptive_stop_v58.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.atr_adaptive_stop_v58.confidence_adjust*100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.atr_adaptive_stop_v58.msg }}</div>
          </div>
        </div>

        <!-- V58: 信号质量综合评分 -->
        <div v-if="diagnosis.chanlun.composite_quality_score_v58" class="metric-card v58-quality">
          <div class="card-title">⭐ V58 信号质量综合评分（条件175）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">质量等级</span>
              <span class="tag" :class="{
                'tag-green': diagnosis.chanlun.composite_quality_score_v58.grade === 'S',
                'tag-blue': diagnosis.chanlun.composite_quality_score_v58.grade === 'A',
                'tag-gray': diagnosis.chanlun.composite_quality_score_v58.grade === 'B',
                'tag-orange': diagnosis.chanlun.composite_quality_score_v58.grade === 'C',
                'tag-red': diagnosis.chanlun.composite_quality_score_v58.grade === 'D'
              }">
                {{ diagnosis.chanlun.composite_quality_score_v58.grade }}档 — {{ diagnosis.chanlun.composite_quality_score_v58.grade_desc }}
              </span>
            </div>
            <div class="kv-row"><span class="kv-key">综合调整</span><span class="kv-val" :style="{ color: diagnosis.chanlun.composite_quality_score_v58.total_adjust >= 0 ? '#22c55e' : '#ef4444' }">{{ diagnosis.chanlun.composite_quality_score_v58.total_adjust >= 0 ? '+' : '' }}{{ (diagnosis.chanlun.composite_quality_score_v58.total_adjust*100).toFixed(0) }}%</span></div>
            <div class="kv-row"><span class="kv-key">明细</span><span class="kv-val" style="font-size:12px;word-break:break-all">{{ Object.entries(diagnosis.chanlun.composite_quality_score_v58.detail_scores).map(([k,v])=>`${k}=${v>=0?'+':''}${(v*100).toFixed(0)}%`).join(' | ') || '无有效条件' }}</span></div>
            <div class="kv-note">{{ diagnosis.chanlun.composite_quality_score_v58.msg }}</div>
          </div>
        </div>

        <!-- V59: 波动率自适应MA周期 -->
        <div v-if="diagnosis.chanlun.volatility_adaptive_ma_v59" class="metric-card v59-vol-ma">
          <div class="card-title">📐 V59 波动率自适应MA周期（条件176）</div>
          <div class="card-body">
            <div class="kv-row">
              <span class="kv-key">波动率</span>
              <span class="tag" :class="{
                'tag-red': diagnosis.chanlun.volatility_adaptive_ma_v59.volatility_regime === 'high',
                'tag-green': diagnosis.chanlun.volatility_adaptive_ma_v59.volatility_regime === 'low',
                'tag-blue': diagnosis.chanlun.volatility_adaptive_ma_v59.volatility_regime === 'normal'
              }">{{ diagnosis.chanlun.volatility_adaptive_ma_v59.volatility_regime }}</span>
            </div>
            <div class="kv-row"><span class="kv-key">自适应MA</span><span class="kv-val">MA{{ diagnosis.chanlun.volatility_adaptive_ma_v59.adaptive_ma_short }} / MA{{ diagnosis.chanlun.volatility_adaptive_ma_v59.adaptive_ma_mid }} / MA{{ diagnosis.chanlun.volatility_adaptive_ma_v59.adaptive_ma_long }}</span></div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span :style="{ color: diagnosis.chanlun.volatility_adaptive_ma_v59.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.volatility_adaptive_ma_v59.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                {{ diagnosis.chanlun.volatility_adaptive_ma_v59.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.volatility_adaptive_ma_v59.confidence_adjust*100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.volatility_adaptive_ma_v59.msg }}</div>
          </div>
        </div>

        <!-- V59: ATR倍数自适应 -->
        <div v-if="diagnosis.chanlun.atr_multiplier_adapt_v59" class="metric-card v59-atr-mult">
          <div class="card-title">🎯 V59 ATR倍数自适应（条件177）</div>
          <div class="card-body">
            <div class="kv-row"><span class="kv-key">ATR(14)</span><span class="kv-val">{{ diagnosis.chanlun.atr_multiplier_adapt_v59.atr_14 }}</span></div>
            <div class="kv-row"><span class="kv-key">最优倍数</span><span class="kv-val">{{ diagnosis.chanlun.atr_multiplier_adapt_v59.optimal_multiplier }}x</span></div>
            <div class="kv-row"><span class="kv-key">止损距离</span><span class="kv-val">{{ diagnosis.chanlun.atr_multiplier_adapt_v59.stop_distance_pct }}%</span></div>
            <div class="kv-row">
              <span class="kv-key">波动率</span>
              <span class="tag" :class="{
                'tag-red': diagnosis.chanlun.atr_multiplier_adapt_v59.volatility_regime === 'extreme',
                'tag-orange': diagnosis.chanlun.atr_multiplier_adapt_v59.volatility_regime === 'high',
                'tag-green': diagnosis.chanlun.atr_multiplier_adapt_v59.volatility_regime === 'low',
                'tag-blue': diagnosis.chanlun.atr_multiplier_adapt_v59.volatility_regime === 'normal'
              }">{{ diagnosis.chanlun.atr_multiplier_adapt_v59.volatility_regime }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span :style="{ color: diagnosis.chanlun.atr_multiplier_adapt_v59.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.atr_multiplier_adapt_v59.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                {{ diagnosis.chanlun.atr_multiplier_adapt_v59.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.atr_multiplier_adapt_v59.confidence_adjust*100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.atr_multiplier_adapt_v59.msg }}</div>
          </div>
        </div>

        <!-- V59: 多时间框架共振信号 -->
        <div v-if="diagnosis.chanlun.multi_tf_resonance_signal_v59" class="metric-card v59-resonance">
          <div class="card-title">🔀 V59 多TF共振信号（条件178）</div>
          <div class="card-body">
            <div class="kv-row"><span class="kv-key">短周期趋势</span><span class="kv-val">{{ diagnosis.chanlun.multi_tf_resonance_signal_v59.short_tf_trend }}</span></div>
            <div class="kv-row"><span class="kv-key">短周期动量</span><span class="kv-val">{{ diagnosis.chanlun.multi_tf_resonance_signal_v59.short_tf_momentum }}</span></div>
            <div class="kv-row">
              <span class="kv-key">共振强度</span>
              <span class="tag" :class="{
                'tag-green': diagnosis.chanlun.multi_tf_resonance_signal_v59.resonance_strength === 'strong',
                'tag-blue': diagnosis.chanlun.multi_tf_resonance_signal_v59.resonance_strength === 'moderate',
                'tag-orange': diagnosis.chanlun.multi_tf_resonance_signal_v59.resonance_strength === 'weak_opposite',
                'tag-red': diagnosis.chanlun.multi_tf_resonance_signal_v59.resonance_strength === 'strong_opposite'
              }">{{ diagnosis.chanlun.multi_tf_resonance_signal_v59.resonance_strength }}</span>
            </div>
            <div class="kv-row"><span class="kv-key">共振评分</span><span class="kv-val">{{ diagnosis.chanlun.multi_tf_resonance_signal_v59.resonance_score }}</span></div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span :style="{ color: diagnosis.chanlun.multi_tf_resonance_signal_v59.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.multi_tf_resonance_signal_v59.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                {{ diagnosis.chanlun.multi_tf_resonance_signal_v59.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.multi_tf_resonance_signal_v59.confidence_adjust*100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.multi_tf_resonance_signal_v59.msg }}</div>
          </div>
        </div>

        <!-- V59: 信号衰减速度评估 -->
        <div v-if="diagnosis.chanlun.signal_decay_speed_v59" class="metric-card v59-decay-speed">
          <div class="card-title">⏱️ V59 信号衰减速度（条件179）</div>
          <div class="card-body">
            <div class="kv-row"><span class="kv-key">价格变化</span><span class="kv-val">{{ diagnosis.chanlun.signal_decay_speed_v59.price_speed_after_signal }}%</span></div>
            <div class="kv-row">
              <span class="kv-key">衰减状态</span>
              <span class="tag" :class="{
                'tag-green': diagnosis.chanlun.signal_decay_speed_v59.decay_rate === 'fast_rise' || diagnosis.chanlun.signal_decay_speed_v59.decay_rate === 'fast_fall',
                'tag-blue': diagnosis.chanlun.signal_decay_speed_v59.decay_rate === 'moderate_rise' || diagnosis.chanlun.signal_decay_speed_v59.decay_rate === 'moderate_fall',
                'tag-orange': diagnosis.chanlun.signal_decay_speed_v59.decay_rate === 'slow_rise' || diagnosis.chanlun.signal_decay_speed_v59.decay_rate === 'slow_fall',
                'tag-red': diagnosis.chanlun.signal_decay_speed_v59.decay_rate === 'reversal' || diagnosis.chanlun.signal_decay_speed_v59.decay_rate === 'rebound'
              }">{{ diagnosis.chanlun.signal_decay_speed_v59.decay_rate }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">信号强度</span>
              <span class="tag" :class="{
                'tag-green': diagnosis.chanlun.signal_decay_speed_v59.signal_strength === 'strong',
                'tag-blue': diagnosis.chanlun.signal_decay_speed_v59.signal_strength === 'moderate',
                'tag-orange': diagnosis.chanlun.signal_decay_speed_v59.signal_strength === 'weak',
                'tag-red': diagnosis.chanlun.signal_decay_speed_v59.signal_strength === 'fake'
              }">{{ diagnosis.chanlun.signal_decay_speed_v59.signal_strength }}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span :style="{ color: diagnosis.chanlun.signal_decay_speed_v59.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.signal_decay_speed_v59.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                {{ diagnosis.chanlun.signal_decay_speed_v59.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.signal_decay_speed_v59.confidence_adjust*100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.signal_decay_speed_v59.msg }}</div>
          </div>
        </div>

        <!-- V60: RSI深度背离过滤 -->
        <div v-if="diagnosis.chanlun.rsi_deep_divergence_v60" class="metric-card v60-rsi-div">
          <div class="card-title">📉 V60 RSI深度背离（条件180）</div>
          <div class="card-body">
            <div class="kv-row"><span class="kv-key">当前RSI</span><span class="kv-val">{{ diagnosis.chanlun.rsi_deep_divergence_v60.rsi_current }}</span></div>
            <div class="kv-row"><span class="kv-key">背离类型</span><span class="tag" :class="diagnosis.chanlun.rsi_deep_divergence_v60.divergence_type === 'bullish_deep' ? 'tag-green' : diagnosis.chanlun.rsi_deep_divergence_v60.divergence_type === 'bearish_deep' ? 'tag-red' : 'tag-gray'">{{ diagnosis.chanlun.rsi_deep_divergence_v60.divergence_type }}</span></div>
            <div class="kv-row"><span class="kv-key">背离深度</span><span class="tag" :class="diagnosis.chanlun.rsi_deep_divergence_v60.divergence_depth === 'deep' ? 'tag-green' : diagnosis.chanlun.rsi_deep_divergence_v60.divergence_depth === 'moderate' ? 'tag-blue' : 'tag-gray'">{{ diagnosis.chanlun.rsi_deep_divergence_v60.divergence_depth }}</span></div>
            <div class="kv-row"><span class="kv-key">价格低点</span><span class="kv-val">{{ diagnosis.chanlun.rsi_deep_divergence_v60.price_prev_low }} → {{ diagnosis.chanlun.rsi_deep_divergence_v60.price_curr_low }}</span></div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span :style="{ color: diagnosis.chanlun.rsi_deep_divergence_v60.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.rsi_deep_divergence_v60.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                {{ diagnosis.chanlun.rsi_deep_divergence_v60.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.rsi_deep_divergence_v60.confidence_adjust*100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.rsi_deep_divergence_v60.msg }}</div>
          </div>
        </div>

        <!-- V60: MA排列间距强度评分 -->
        <div v-if="diagnosis.chanlun.ma_spacing_strength_v60" class="metric-card v60-ma-spacing">
          <div class="card-title">📐 V60 MA排列间距（条件181）</div>
          <div class="card-body">
            <div class="kv-row"><span class="kv-key">MA5/MA20/MA60</span><span class="kv-val">{{ diagnosis.chanlun.ma_spacing_strength_v60.ma5 }} / {{ diagnosis.chanlun.ma_spacing_strength_v60.ma20 }} / {{ diagnosis.chanlun.ma_spacing_strength_v60.ma60 }}</span></div>
            <div class="kv-row"><span class="kv-key">排列方向</span><span class="tag" :class="diagnosis.chanlun.ma_spacing_strength_v60.alignment === 'bullish' ? 'tag-green' : diagnosis.chanlun.ma_spacing_strength_v60.alignment === 'bearish' ? 'tag-red' : 'tag-orange'">{{ diagnosis.chanlun.ma_spacing_strength_v60.alignment }}</span></div>
            <div class="kv-row"><span class="kv-key">间距比例</span><span class="kv-val">{{ diagnosis.chanlun.ma_spacing_strength_v60.spacing_ratio }}%</span></div>
            <div class="kv-row"><span class="kv-key">间距强度</span><span class="tag" :class="diagnosis.chanlun.ma_spacing_strength_v60.spacing_strength === 'strong' ? 'tag-green' : diagnosis.chanlun.ma_spacing_strength_v60.spacing_strength === 'moderate' ? 'tag-blue' : 'tag-orange'">{{ diagnosis.chanlun.ma_spacing_strength_v60.spacing_strength }}</span></div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span :style="{ color: diagnosis.chanlun.ma_spacing_strength_v60.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.ma_spacing_strength_v60.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                {{ diagnosis.chanlun.ma_spacing_strength_v60.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.ma_spacing_strength_v60.confidence_adjust*100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.ma_spacing_strength_v60.msg }}</div>
          </div>
        </div>

        <!-- V60: 中枢支撑/阻力距离评分增强 -->
        <div v-if="diagnosis.chanlun.zs_distance_enhanced_v60" class="metric-card v60-zs-dist">
          <div class="card-title">🏛️ V60 中枢距离增强（条件182）</div>
          <div class="card-body">
            <div class="kv-row"><span class="kv-key">当前价格</span><span class="kv-val">{{ diagnosis.chanlun.zs_distance_enhanced_v60.price }}</span></div>
            <div class="kv-row"><span class="kv-key">中枢区间</span><span class="kv-val">[{{ diagnosis.chanlun.zs_distance_enhanced_v60.zs_zd }}, {{ diagnosis.chanlun.zs_distance_enhanced_v60.zs_zg }}]</span></div>
            <div class="kv-row"><span class="kv-key">价格位置</span><span class="tag" :class="diagnosis.chanlun.zs_distance_enhanced_v60.position === 'above_zs' ? 'tag-green' : diagnosis.chanlun.zs_distance_enhanced_v60.position === 'below_zs' ? 'tag-red' : 'tag-orange'">{{ diagnosis.chanlun.zs_distance_enhanced_v60.position }}</span></div>
            <div class="kv-row"><span class="kv-key">距上沿</span><span class="kv-val">{{ diagnosis.chanlun.zs_distance_enhanced_v60.distance_to_zg_pct }}%</span></div>
            <div class="kv-row"><span class="kv-key">距下沿</span><span class="kv-val">{{ diagnosis.chanlun.zs_distance_enhanced_v60.distance_to_zd_pct }}%</span></div>
            <div class="kv-row"><span class="kv-key">回踩确认</span><span class="tag" :class="diagnosis.chanlun.zs_distance_enhanced_v60.pullback_confirmed ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.zs_distance_enhanced_v60.pullback_confirmed ? '✅ 已确认' : '⚪ 未确认' }}</span></div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span :style="{ color: diagnosis.chanlun.zs_distance_enhanced_v60.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.zs_distance_enhanced_v60.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                {{ diagnosis.chanlun.zs_distance_enhanced_v60.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.zs_distance_enhanced_v60.confidence_adjust*100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.zs_distance_enhanced_v60.msg }}</div>
          </div>
        </div>

        <!-- V60: KDJ超买超卖确认 -->
        <div v-if="diagnosis.chanlun.kdj_ob_os_confirm_v60" class="metric-card v60-kdj">
          <div class="card-title">💹 V60 KDJ超买超卖（条件183）</div>
          <div class="card-body">
            <div class="kv-row"><span class="kv-key">K/D/J</span><span class="kv-val">{{ diagnosis.chanlun.kdj_ob_os_confirm_v60.kdj_k }} / {{ diagnosis.chanlun.kdj_ob_os_confirm_v60.kdj_d }} / {{ diagnosis.chanlun.kdj_ob_os_confirm_v60.kdj_j }}</span></div>
            <div class="kv-row"><span class="kv-key">J值趋势</span><span class="tag" :class="diagnosis.chanlun.kdj_ob_os_confirm_v60.j_trend === 'rising' ? 'tag-green' : diagnosis.chanlun.kdj_ob_os_confirm_v60.j_trend === 'falling' ? 'tag-red' : 'tag-gray'">{{ diagnosis.chanlun.kdj_ob_os_confirm_v60.j_trend }}</span></div>
            <div class="kv-row"><span class="kv-key">超买超卖区</span><span class="tag" :class="diagnosis.chanlun.kdj_ob_os_confirm_v60.ob_os_zone === 'oversold' || diagnosis.chanlun.kdj_ob_os_confirm_v60.ob_os_zone === 'extreme_oversold' ? 'tag-green' : diagnosis.chanlun.kdj_ob_os_confirm_v60.ob_os_zone === 'overbought' || diagnosis.chanlun.kdj_ob_os_confirm_v60.ob_os_zone === 'extreme_overbought' ? 'tag-red' : 'tag-gray'">{{ diagnosis.chanlun.kdj_ob_os_confirm_v60.ob_os_zone }}</span></div>
            <div class="kv-row"><span class="kv-key">信号对齐</span><span class="tag" :class="diagnosis.chanlun.kdj_ob_os_confirm_v60.signal_aligned ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.kdj_ob_os_confirm_v60.signal_aligned ? '✅ 对齐' : '⚪ 未对齐' }}</span></div>
            <div class="kv-row">
              <span class="kv-key">置信度调整</span>
              <span :style="{ color: diagnosis.chanlun.kdj_ob_os_confirm_v60.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.kdj_ob_os_confirm_v60.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                {{ diagnosis.chanlun.kdj_ob_os_confirm_v60.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.kdj_ob_os_confirm_v60.confidence_adjust*100).toFixed(0) }}%
              </span>
            </div>
            <div class="kv-note">{{ diagnosis.chanlun.kdj_ob_os_confirm_v60.msg }}</div>
          </div>
        </div>

        <!-- V61: MACD柱状图背离融合 -->
        <div v-if="diagnosis.chanlun.macd_hist_divergence_v61" class="metric-card v61-macd-div">
           <div class="card-title">🔍 V61 MACD柱状图背离融合（条件184）</div>
           <div class="card-body">
             <div class="kv-row"><span class="kv-key">MACD柱当前/前期</span><span class="kv-val">{{ diagnosis.chanlun.macd_hist_divergence_v61.macd_hist_curr }} / {{ diagnosis.chanlun.macd_hist_divergence_v61.macd_hist_prev }}</span></div>
             <div class="kv-row"><span class="kv-key">背离类型</span><span class="tag" :class="diagnosis.chanlun.macd_hist_divergence_v61.divergence_type === 'bullish_macd' ? 'tag-green' : diagnosis.chanlun.macd_hist_divergence_v61.divergence_type === 'bearish_macd' ? 'tag-red' : 'tag-gray'">{{ diagnosis.chanlun.macd_hist_divergence_v61.divergence_type }}</span></div>
             <div class="kv-row"><span class="kv-key">背离深度</span><span class="tag" :class="diagnosis.chanlun.macd_hist_divergence_v61.divergence_depth === 'deep' ? 'tag-green' : diagnosis.chanlun.macd_hist_divergence_v61.divergence_depth === 'moderate' ? 'tag-blue' : 'tag-gray'">{{ diagnosis.chanlun.macd_hist_divergence_v61.divergence_depth }}</span></div>
             <div class="kv-row"><span class="kv-key">RSI融合</span><span class="tag" :class="diagnosis.chanlun.macd_hist_divergence_v61.rsi_fusion === 'fused_bullish' || diagnosis.chanlun.macd_hist_divergence_v61.rsi_fusion === 'fused_bearish' ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.macd_hist_divergence_v61.rsi_fusion }}</span></div>
             <div class="kv-row"><span class="kv-key">置信度调整</span>
               <span :style="{ color: diagnosis.chanlun.macd_hist_divergence_v61.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.macd_hist_divergence_v61.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                 {{ diagnosis.chanlun.macd_hist_divergence_v61.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.macd_hist_divergence_v61.confidence_adjust*100).toFixed(0) }}%
               </span>
             </div>
             <div class="kv-note">{{ diagnosis.chanlun.macd_hist_divergence_v61.msg }}</div>
           </div>
         </div>

        <!-- V61: 综合多信号评分 -->
        <div v-if="diagnosis.chanlun.composite_signal_score_v61" class="metric-card v61-composite" :style="{ borderColor: diagnosis.chanlun.composite_signal_score_v61.tier_color + '40', borderWidth: '2px', borderStyle: 'solid' }">
           <div class="card-title">⭐ V61 综合多信号评分（条件185）</div>
           <div class="card-body">
             <div class="kv-row">
               <span class="kv-key">质量等级</span>
               <span class="tag" :style="{ backgroundColor: diagnosis.chanlun.composite_signal_score_v61.tier_color, color: '#fff', fontWeight: 700, fontSize: '14px', padding: '2px 10px' }">
                 {{ diagnosis.chanlun.composite_signal_score_v61.quality_tier }}级
               </span>
               <span class="kv-key">综合评分</span>
               <span class="kv-val" :style="{ color: diagnosis.chanlun.composite_signal_score_v61.tier_color, fontWeight: 700 }">{{ (diagnosis.chanlun.composite_signal_score_v61.composite_score*100).toFixed(0) }}%</span>
             </div>
             <div class="kv-row"><span class="kv-key">有效条件数</span><span class="kv-val">{{ diagnosis.chanlun.composite_signal_score_v61.condition_count }} 个</span></div>
             <div class="kv-row"><span class="kv-key">总调整量</span><span :style="{ color: diagnosis.chanlun.composite_signal_score_v61.total_adjustment > 0 ? '#22c55e' : diagnosis.chanlun.composite_signal_score_v61.total_adjustment < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">{{ diagnosis.chanlun.composite_signal_score_v61.total_adjustment > 0 ? '+' : '' }}{{ (diagnosis.chanlun.composite_signal_score_v61.total_adjustment*100).toFixed(0) }}%</span></div>
             <div class="kv-row"><span class="kv-key">推荐操作</span><span class="tag" :class="diagnosis.chanlun.composite_signal_score_v61.quality_tier === 'S' || diagnosis.chanlun.composite_signal_score_v61.quality_tier === 'A' ? 'tag-green' : diagnosis.chanlun.composite_signal_score_v61.quality_tier === 'D' ? 'tag-red' : 'tag-orange'">{{ diagnosis.chanlun.composite_signal_score_v61.recommendation }}</span></div>
             <div class="kv-row"><span class="kv-key">决策帮助</span><span class="kv-val" style="font-size:12px">{{ diagnosis.chanlun.composite_signal_score_v61.decision_help }}</span></div>
             <div v-if="Object.keys(diagnosis.chanlun.composite_signal_score_v61.breakdown).length > 0" class="kv-note" style="font-size:11px; color:#9ca3af">
               贡献明细: {{ Object.entries(diagnosis.chanlun.composite_signal_score_v61.breakdown).map(([k,v]) => `${k}=${v>0?'+':''}${(v*100).toFixed(0)}%`).join(' | ') }}
             </div>
           </div>
         </div>

          <!-- V62: BOLL带宽突破确认 -->
          <div v-if="diagnosis.chanlun.boll_bandwidth_breakout_v62" class="metric-card v62-boll-bw">
             <div class="card-title">📊 V62 BOLL带宽突破确认（条件186）</div>
             <div class="card-body">
               <div class="kv-row"><span class="kv-key">BOLL上轨/下轨</span><span class="kv-val">{{ diagnosis.chanlun.boll_bandwidth_breakout_v62.boll_upper }} / {{ diagnosis.chanlun.boll_bandwidth_breakout_v62.boll_lower }}</span></div>
               <div class="kv-row"><span class="kv-key">带宽</span><span class="kv-val">{{ diagnosis.chanlun.boll_bandwidth_breakout_v62.band_width.toFixed(2) }}%</span></div>
               <div class="kv-row"><span class="kv-key">价格位置</span><span class="tag" :class="diagnosis.chanlun.boll_bandwidth_breakout_v62.price_position === 'upper' ? 'tag-green' : diagnosis.chanlun.boll_bandwidth_breakout_v62.price_position === 'lower' ? 'tag-red' : 'tag-gray'">{{ diagnosis.chanlun.boll_bandwidth_breakout_v62.price_position }}</span></div>
               <div class="kv-row"><span class="kv-key">带宽趋势</span><span class="tag" :class="diagnosis.chanlun.boll_bandwidth_breakout_v62.band_trend === 'expanding' ? 'tag-green' : diagnosis.chanlun.boll_bandwidth_breakout_v62.band_trend === 'contracting' ? 'tag-red' : 'tag-gray'">{{ diagnosis.chanlun.boll_bandwidth_breakout_v62.band_trend }}</span></div>
               <div class="kv-row"><span class="kv-key">突破确认</span><span class="tag" :class="diagnosis.chanlun.boll_bandwidth_breakout_v62.breakout_confirmed ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.boll_bandwidth_breakout_v62.breakout_confirmed ? '是' : '否' }}</span></div>
               <div class="kv-row"><span class="kv-key">置信度调整</span>
                 <span :style="{ color: diagnosis.chanlun.boll_bandwidth_breakout_v62.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.boll_bandwidth_breakout_v62.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                   {{ diagnosis.chanlun.boll_bandwidth_breakout_v62.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.boll_bandwidth_breakout_v62.confidence_adjust*100).toFixed(0) }}%
                 </span>
               </div>
               <div class="kv-note">{{ diagnosis.chanlun.boll_bandwidth_breakout_v62.msg }}</div>
             </div>
           </div>

           <!-- V62: BOLL带宽压缩反弹确认 -->
           <div v-if="diagnosis.chanlun.boll_bandwidth_reversal_v62" class="metric-card v62-boll-rev">
              <div class="card-title">🔄 V62 BOLL带宽压缩反弹确认（条件187）</div>
              <div class="card-body">
                <div class="kv-row"><span class="kv-key">带宽分位</span><span class="kv-val">{{ (diagnosis.chanlun.boll_bandwidth_reversal_v62.band_width_rank*100).toFixed(0) }}%</span></div>
                <div class="kv-row"><span class="kv-key">压缩状态</span><span class="tag" :class="diagnosis.chanlun.boll_bandwidth_reversal_v62.squeeze_active ? 'tag-orange' : 'tag-gray'">{{ diagnosis.chanlun.boll_bandwidth_reversal_v62.squeeze_active ? '压缩中' : '正常' }}</span></div>
                <div class="kv-row"><span class="kv-key">反弹确认</span><span class="tag" :class="diagnosis.chanlun.boll_bandwidth_reversal_v62.reversal_confirmed ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.boll_bandwidth_reversal_v62.reversal_confirmed ? '是' : '否' }}</span></div>
                <div class="kv-row"><span class="kv-key">反弹类型</span><span class="tag" :class="diagnosis.chanlun.boll_bandwidth_reversal_v62.reversal_type === 'bullish_reversal' ? 'tag-green' : diagnosis.chanlun.boll_bandwidth_reversal_v62.reversal_type === 'bearish_reversal' ? 'tag-red' : 'tag-gray'">{{ diagnosis.chanlun.boll_bandwidth_reversal_v62.reversal_type }}</span></div>
                <div class="kv-row"><span class="kv-key">置信度调整</span>
                  <span :style="{ color: diagnosis.chanlun.boll_bandwidth_reversal_v62.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.boll_bandwidth_reversal_v62.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                    {{ diagnosis.chanlun.boll_bandwidth_reversal_v62.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.boll_bandwidth_reversal_v62.confidence_adjust*100).toFixed(0) }}%
                  </span>
                </div>
                <div class="kv-note">{{ diagnosis.chanlun.boll_bandwidth_reversal_v62.msg }}</div>
              </div>
           </div>

           <!-- V62: 动态阈值-波动率状态切换 -->
           <div v-if="diagnosis.chanlun.dynamic_threshold_volatility_regime_v62" class="metric-card v62-dyn-threshold">
              <div class="card-title">⚡ V62 动态阈值-波动率状态切换（条件188）</div>
              <div class="card-body">
                <div class="kv-row"><span class="kv-key">ATR(14)%</span><span class="kv-val">{{ diagnosis.chanlun.dynamic_threshold_volatility_regime_v62.atr_pct.toFixed(2) }}%</span></div>
                <div class="kv-row"><span class="kv-key">波动率状态</span><span class="tag" :class="diagnosis.chanlun.dynamic_threshold_volatility_regime_v62.volatility_regime === 'high' ? 'tag-red' : diagnosis.chanlun.dynamic_threshold_volatility_regime_v62.volatility_regime === 'low' ? 'tag-green' : 'tag-blue'">{{ diagnosis.chanlun.dynamic_threshold_volatility_regime_v62.volatility_regime }}</span></div>
                <div class="kv-row"><span class="kv-key">置信度调整</span>
                  <span :style="{ color: diagnosis.chanlun.dynamic_threshold_volatility_regime_v62.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.dynamic_threshold_volatility_regime_v62.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                    {{ diagnosis.chanlun.dynamic_threshold_volatility_regime_v62.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.dynamic_threshold_volatility_regime_v62.confidence_adjust*100).toFixed(0) }}%
                  </span>
                </div>
                <div class="kv-note">{{ diagnosis.chanlun.dynamic_threshold_volatility_regime_v62.msg }}</div>
              </div>
           </div>

           <!-- V62: 动态阈值-ATR倍数自适应 -->
           <div v-if="diagnosis.chanlun.dynamic_threshold_atr_multiplier_v62" class="metric-card v62-atr-mult">
              <div class="card-title">🎯 V62 动态阈值-ATR倍数自适应（条件189）</div>
              <div class="card-body">
                <div class="kv-row"><span class="kv-key">ATR(14)</span><span class="kv-val">{{ diagnosis.chanlun.dynamic_threshold_atr_multiplier_v62.atr_14.toFixed(4) }}</span></div>
                <div class="kv-row"><span class="kv-key">最优倍数</span><span class="kv-val">{{ diagnosis.chanlun.dynamic_threshold_atr_multiplier_v62.optimal_multiplier }}x</span></div>
                <div class="kv-row"><span class="kv-key">止损距离</span><span class="kv-val">{{ diagnosis.chanlun.dynamic_threshold_atr_multiplier_v62.stop_distance_pct.toFixed(1) }}%</span></div>
                <div class="kv-row"><span class="kv-key">波动率状态</span><span class="tag" :class="diagnosis.chanlun.dynamic_threshold_atr_multiplier_v62.volatility_regime === 'extreme' ? 'tag-red' : diagnosis.chanlun.dynamic_threshold_atr_multiplier_v62.volatility_regime === 'high' ? 'tag-orange' : diagnosis.chanlun.dynamic_threshold_atr_multiplier_v62.volatility_regime === 'low' ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.dynamic_threshold_atr_multiplier_v62.volatility_regime }}</span></div>
                <div class="kv-row"><span class="kv-key">置信度调整</span>
                  <span :style="{ color: diagnosis.chanlun.dynamic_threshold_atr_multiplier_v62.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.dynamic_threshold_atr_multiplier_v62.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                    {{ diagnosis.chanlun.dynamic_threshold_atr_multiplier_v62.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.dynamic_threshold_atr_multiplier_v62.confidence_adjust*100).toFixed(0) }}%
                  </span>
                </div>
                <div class="kv-note">{{ diagnosis.chanlun.dynamic_threshold_atr_multiplier_v62.msg }}</div>
              </div>
           </div>
          <!-- V63: 中枢级别权重优化增强 -->
          <div v-if="diagnosis.chanlun.zhongshu_level_weight_enhanced_v63" class="metric-card v63-zs-weight">
             <div class="card-title">💎 V63 中枢级别权重优化（条件190）</div>
             <div class="card-body">
               <div class="kv-row"><span class="kv-key">中枢级别</span><span class="tag" :class="diagnosis.chanlun.zhongshu_level_weight_enhanced_v63.level === '月线' ? 'tag-gold' : diagnosis.chanlun.zhongshu_level_weight_enhanced_v63.level === '周线' ? 'tag-green' : diagnosis.chanlun.zhongshu_level_weight_enhanced_v63.level === '日线' ? 'tag-blue' : 'tag-gray'">{{ diagnosis.chanlun.zhongshu_level_weight_enhanced_v63.level }}</span></div>
               <div class="kv-row"><span class="kv-key">距离评分</span><span class="kv-val">{{ diagnosis.chanlun.zhongshu_level_weight_enhanced_v63.distance_score }}/4</span></div>
               <div class="kv-row"><span class="kv-key">质量评分</span><span class="kv-val">{{ diagnosis.chanlun.zhongshu_level_weight_enhanced_v63.quality_score }}/3</span></div>
               <div class="kv-row"><span class="kv-key">近期测试</span><span class="kv-val">{{ diagnosis.chanlun.zhongshu_level_weight_enhanced_v63.recent_test_score }}/2</span></div>
               <div class="kv-row"><span class="kv-key">总权重分</span><span class="kv-val" style="font-weight:700">{{ diagnosis.chanlun.zhongshu_level_weight_enhanced_v63.total_weight_bonus }}</span></div>
               <div class="kv-row" style="margin-top:6px">
                 <span class="kv-key">置信度调整</span>
                 <span :style="{ color: diagnosis.chanlun.zhongshu_level_weight_enhanced_v63.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.zhongshu_level_weight_enhanced_v63.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                   {{ diagnosis.chanlun.zhongshu_level_weight_enhanced_v63.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.zhongshu_level_weight_enhanced_v63.confidence_adjust*100).toFixed(0) }}%
                 </span>
               </div>
               <div class="kv-note">{{ diagnosis.chanlun.zhongshu_level_weight_enhanced_v63.msg }}</div>
             </div>
          </div>

          <!-- V63: 多周期信号衰减追踪 -->
          <div v-if="diagnosis.chanlun.multi_period_signal_decay_v63" class="metric-card v63-signal-decay">
             <div class="card-title">📉 V63 多周期信号衰减追踪（条件191）</div>
             <div class="card-body">
               <div class="kv-row"><span class="kv-key">短期(5根)</span><span class="kv-val" :style="{ color: diagnosis.chanlun.multi_period_signal_decay_v63.short_term_momentum >= 0 ? '#22c55e' : '#ef4444' }">{{ diagnosis.chanlun.multi_period_signal_decay_v63.short_term_momentum >= 0 ? '+' : '' }}{{ diagnosis.chanlun.multi_period_signal_decay_v63.short_term_momentum.toFixed(1) }}%</span></div>
               <div class="kv-row"><span class="kv-key">中期(10根)</span><span class="kv-val" :style="{ color: diagnosis.chanlun.multi_period_signal_decay_v63.mid_term_momentum >= 0 ? '#22c55e' : '#ef4444' }">{{ diagnosis.chanlun.multi_period_signal_decay_v63.mid_term_momentum >= 0 ? '+' : '' }}{{ diagnosis.chanlun.multi_period_signal_decay_v63.mid_term_momentum.toFixed(1) }}%</span></div>
               <div class="kv-row"><span class="kv-key">长期(20根)</span><span class="kv-val" :style="{ color: diagnosis.chanlun.multi_period_signal_decay_v63.long_term_momentum >= 0 ? '#22c55e' : '#ef4444' }">{{ diagnosis.chanlun.multi_period_signal_decay_v63.long_term_momentum >= 0 ? '+' : '' }}{{ diagnosis.chanlun.multi_period_signal_decay_v63.long_term_momentum.toFixed(1) }}%</span></div>
               <div class="kv-row"><span class="kv-key">健康度</span><span class="tag" :class="diagnosis.chanlun.multi_period_signal_decay_v63.overall_health === 'strong' ? 'tag-green' : diagnosis.chanlun.multi_period_signal_decay_v63.overall_health === 'healthy' ? 'tag-blue' : diagnosis.chanlun.multi_period_signal_decay_v63.overall_health === 'stable' ? 'tag-gray' : 'tag-red'">{{ diagnosis.chanlun.multi_period_signal_decay_v63.overall_health }}</span></div>
               <div class="kv-row"><span class="kv-key">衰减检测</span><span class="tag" :class="diagnosis.chanlun.multi_period_signal_decay_v63.decay_detected ? 'tag-red' : 'tag-green'">{{ diagnosis.chanlun.multi_period_signal_decay_v63.decay_detected ? '⚠️ 是' : '✅ 否' }}</span></div>
               <div class="kv-row" style="margin-top:6px">
                 <span class="kv-key">置信度调整</span>
                 <span :style="{ color: diagnosis.chanlun.multi_period_signal_decay_v63.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.multi_period_signal_decay_v63.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                   {{ diagnosis.chanlun.multi_period_signal_decay_v63.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.multi_period_signal_decay_v63.confidence_adjust*100).toFixed(0) }}%
                 </span>
               </div>
               <div class="kv-note">{{ diagnosis.chanlun.multi_period_signal_decay_v63.msg }}</div>
             </div>
          </div>

           <!-- V65: 量价背离二次确认增强 -->
           <div v-if="diagnosis.chanlun.volume_price_divergence_secondary_v65" class="metric-card v65-vp-div">
              <div class="card-title">📊 V65 量价背离二次确认（条件192）</div>
              <div class="card-body">
                <div class="kv-row"><span class="kv-key">背离确认</span><span class="tag" :class="diagnosis.chanlun.volume_price_divergence_secondary_v65.diverge_confirmed ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.volume_price_divergence_secondary_v65.diverge_confirmed ? '✅ 已确认' : '⚠️ 未确认' }}</span></div>
                <div class="kv-row"><span class="kv-key">背离强度</span><span class="kv-val">{{ diagnosis.chanlun.volume_price_divergence_secondary_v65.divergence_strength.toFixed(2) }}</span></div>
                <div class="kv-row"><span class="kv-key">持续K线</span><span class="kv-val">{{ diagnosis.chanlun.volume_price_divergence_secondary_v65.duration_bars }} 根</span></div>
                <div class="kv-row" style="margin-top:6px">
                  <span class="kv-key">置信度调整</span>
                  <span :style="{ color: diagnosis.chanlun.volume_price_divergence_secondary_v65.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.volume_price_divergence_secondary_v65.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                    {{ diagnosis.chanlun.volume_price_divergence_secondary_v65.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.volume_price_divergence_secondary_v65.confidence_adjust*100).toFixed(0) }}%
                  </span>
                </div>
                <div class="kv-note">{{ diagnosis.chanlun.volume_price_divergence_secondary_v65.msg }}</div>
              </div>
           </div>

           <!-- V65: 中枢突破回踩确认 -->
           <div v-if="diagnosis.chanlun.breakout_retest_confirmation_v65" class="metric-card v65-breakout">
              <div class="card-title">🎯 V65 中枢突破回踩确认（条件193）</div>
              <div class="card-body">
                <div class="kv-row"><span class="kv-key">回踩确认</span><span class="tag" :class="diagnosis.chanlun.breakout_retest_confirmation_v65.retest_confirmed ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.breakout_retest_confirmation_v65.retest_confirmed ? '✅ 已确认' : '⚠️ 未确认' }}</span></div>
                <div class="kv-row"><span class="kv-key">突破有效</span><span class="tag" :class="diagnosis.chanlun.breakout_retest_confirmation_v65.breakout_valid ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.breakout_retest_confirmation_v65.breakout_valid ? '✅ 有效' : '❌ 假突破' }}</span></div>
                <div class="kv-row"><span class="kv-key">回撤幅度</span><span class="kv-val">{{ (diagnosis.chanlun.breakout_retest_confirmation_v65.retest_depth * 100).toFixed(1) }}%</span></div>
                <div class="kv-row" style="margin-top:6px">
                  <span class="kv-key">置信度调整</span>
                  <span :style="{ color: diagnosis.chanlun.breakout_retest_confirmation_v65.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.breakout_retest_confirmation_v65.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                    {{ diagnosis.chanlun.breakout_retest_confirmation_v65.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.breakout_retest_confirmation_v65.confidence_adjust*100).toFixed(0) }}%
                  </span>
                </div>
                <div class="kv-note">{{ diagnosis.chanlun.breakout_retest_confirmation_v65.msg }}</div>
              </div>
           </div>

           <!-- V65: 波动率压缩突破 -->
           <div v-if="diagnosis.chanlun.volatility_compression_breakout_v65" class="metric-card v65-squeeze">
              <div class="card-title">🔥 V65 波动率压缩突破（条件194）</div>
              <div class="card-body">
                <div class="kv-row"><span class="kv-key">压缩状态</span><span class="tag" :class="diagnosis.chanlun.volatility_compression_breakout_v65.compression_detected ? 'tag-blue' : 'tag-gray'">{{ diagnosis.chanlun.volatility_compression_breakout_v65.compression_detected ? '🔴 压缩中' : '⚪ 无压缩' }}</span></div>
                <div class="kv-row"><span class="kv-key">压缩评分</span><span class="kv-val">{{ diagnosis.chanlun.volatility_compression_breakout_v65.squeeze_score.toFixed(2) }}</span></div>
                <div class="kv-row"><span class="kv-key">突破力度</span><span class="kv-val">{{ diagnosis.chanlun.volatility_compression_breakout_v65.breakout_strength.toFixed(2) }}</span></div>
                <div class="kv-row" style="margin-top:6px">
                  <span class="kv-key">置信度调整</span>
                  <span :style="{ color: diagnosis.chanlun.volatility_compression_breakout_v65.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.volatility_compression_breakout_v65.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                    {{ diagnosis.chanlun.volatility_compression_breakout_v65.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.volatility_compression_breakout_v65.confidence_adjust*100).toFixed(0) }}%
                  </span>
                </div>
                <div class="kv-note">{{ diagnosis.chanlun.volatility_compression_breakout_v65.msg }}</div>
              </div>
           </div>

           <!-- V65: 信号新鲜度 -->
           <div v-if="diagnosis.chanlun.signal_time_window_freshness_v65" class="metric-card v65-freshness">
              <div class="card-title">⏰ V65 信号时间窗口新鲜度（条件195）</div>
              <div class="card-body">
                <div class="kv-row"><span class="kv-key">信号年龄</span><span class="kv-val">{{ diagnosis.chanlun.signal_time_window_freshness_v65.bars_since_signal }} 根K线前</span></div>
                <div class="kv-row"><span class="kv-key">趋势健康</span><span class="tag" :class="diagnosis.chanlun.signal_time_window_freshness_v65.trend_health === 'strong_uptrend' || diagnosis.chanlun.signal_time_window_freshness_v65.trend_health === 'strong_downtrend' ? 'tag-green' : diagnosis.chanlun.signal_time_window_freshness_v65.trend_health === 'expired' ? 'tag-red' : 'tag-gray'">{{ diagnosis.chanlun.signal_time_window_freshness_v65.trend_health }}</span></div>
                <div class="kv-row"><span class="kv-key">新鲜度评分</span><span class="kv-val">{{ diagnosis.chanlun.signal_time_window_freshness_v65.freshness_score.toFixed(2) }}</span></div>
                <div class="kv-row" style="margin-top:6px">
                  <span class="kv-key">置信度调整</span>
                  <span :style="{ color: diagnosis.chanlun.signal_time_window_freshness_v65.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.signal_time_window_freshness_v65.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                    {{ diagnosis.chanlun.signal_time_window_freshness_v65.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.signal_time_window_freshness_v65.confidence_adjust*100).toFixed(0) }}%
                  </span>
                </div>
                <div class="kv-note">{{ diagnosis.chanlun.signal_time_window_freshness_v65.msg }}</div>
              </div>
           </div>

           <!-- V66: MACD动能锥加速确认 -->
           <div v-if="diagnosis.chanlun.macd_momentum_acceleration_v66" class="metric-card v66-macd-acc">
              <div class="card-title">⚡ V66 MACD动能锥加速（条件196）</div>
              <div class="card-body">
                <div class="kv-row"><span class="kv-key">加速确认</span><span class="tag" :class="diagnosis.chanlun.macd_momentum_acceleration_v66.acceleration_detected ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.macd_momentum_acceleration_v66.acceleration_detected ? '✅ 已加速' : '⚠️ 未加速' }}</span></div>
                <div class="kv-row"><span class="kv-key">加速方向</span><span class="tag" :class="diagnosis.chanlun.macd_momentum_acceleration_v66.acceleration_direction === 'up' ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.macd_momentum_acceleration_v66.acceleration_direction === 'up' ? '↑ 向上' : '↓ 向下' }}</span></div>
                <div class="kv-row"><span class="kv-key">动能锥</span><span class="kv-val">{{ diagnosis.chanlun.macd_momentum_acceleration_v66.cone_bars }} 根K线</span></div>
                <div class="kv-row" style="margin-top:6px">
                  <span class="kv-key">置信度调整</span>
                  <span :style="{ color: diagnosis.chanlun.macd_momentum_acceleration_v66.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.macd_momentum_acceleration_v66.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                    {{ diagnosis.chanlun.macd_momentum_acceleration_v66.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.macd_momentum_acceleration_v66.confidence_adjust*100).toFixed(0) }}%
                  </span>
                </div>
                <div class="kv-note">{{ diagnosis.chanlun.macd_momentum_acceleration_v66.msg }}</div>
              </div>
           </div>

           <!-- V66: 量价配合深度评分 -->
           <div v-if="diagnosis.chanlun.volume_price_coordination_deep_v66" class="metric-card v66-vp-coord">
              <div class="card-title">📈 V66 量价配合深度评分（条件197）</div>
              <div class="card-body">
                <div class="kv-row"><span class="kv-key">短期配合</span><span class="kv-val">{{ diagnosis.chanlun.volume_price_coordination_deep_v66.short_score.toFixed(2) }}</span></div>
                <div class="kv-row"><span class="kv-key">中期配合</span><span class="kv-val">{{ diagnosis.chanlun.volume_price_coordination_deep_v66.mid_score.toFixed(2) }}</span></div>
                <div class="kv-row"><span class="kv-key">极端量能</span><span class="tag" :class="diagnosis.chanlun.volume_price_coordination_deep_v66.extreme_flag === 'normal' ? 'tag-gray' : diagnosis.chanlun.volume_price_coordination_deep_v66.extreme_flag === 'extreme_high' ? 'tag-orange' : 'tag-blue'">{{ diagnosis.chanlun.volume_price_coordination_deep_v66.extreme_flag }}</span></div>
                <div class="kv-row"><span class="kv-key">综合评分</span><span class="kv-val" style="font-weight:700">{{ diagnosis.chanlun.volume_price_coordination_deep_v66.overall_score.toFixed(2) }}</span></div>
                <div class="kv-row" style="margin-top:6px">
                  <span class="kv-key">置信度调整</span>
                  <span :style="{ color: diagnosis.chanlun.volume_price_coordination_deep_v66.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.volume_price_coordination_deep_v66.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                    {{ diagnosis.chanlun.volume_price_coordination_deep_v66.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.volume_price_coordination_deep_v66.confidence_adjust*100).toFixed(0) }}%
                  </span>
                </div>
                <div class="kv-note">{{ diagnosis.chanlun.volume_price_coordination_deep_v66.msg }}</div>
              </div>
           </div>

           <!-- V66: 多时间框架共振强度 -->
           <div v-if="diagnosis.chanlun.multi_tf_convergence_intensity_v66" class="metric-card v66-tf-conv">
              <div class="card-title">🔄 V66 多时间框架共振强度（条件198）</div>
              <div class="card-body">
                <div class="kv-row"><span class="kv-key">短期趋势</span><span class="tag" :class="diagnosis.chanlun.multi_tf_convergence_intensity_v66.short_trend === 'up' ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.multi_tf_convergence_intensity_v66.short_trend === 'up' ? '↑ 上升' : '↓ 下降' }}</span></div>
                <div class="kv-row"><span class="kv-key">中期趋势</span><span class="tag" :class="diagnosis.chanlun.multi_tf_convergence_intensity_v66.mid_trend === 'up' ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.multi_tf_convergence_intensity_v66.mid_trend === 'up' ? '↑ 上升' : '↓ 下降' }}</span></div>
                <div class="kv-row"><span class="kv-key">长期趋势</span><span class="tag" :class="diagnosis.chanlun.multi_tf_convergence_intensity_v66.long_trend === 'up' ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.multi_tf_convergence_intensity_v66.long_trend === 'up' ? '↑ 上升' : '↓ 下降' }}</span></div>
                <div class="kv-row"><span class="kv-key">共振评分</span><span class="kv-val" style="font-weight:700">{{ diagnosis.chanlun.multi_tf_convergence_intensity_v66.convergence_score.toFixed(2) }}</span></div>
                <div class="kv-row" style="margin-top:6px">
                  <span class="kv-key">置信度调整</span>
                  <span :style="{ color: diagnosis.chanlun.multi_tf_convergence_intensity_v66.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.multi_tf_convergence_intensity_v66.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                    {{ diagnosis.chanlun.multi_tf_convergence_intensity_v66.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.multi_tf_convergence_intensity_v66.confidence_adjust*100).toFixed(0) }}%
                  </span>
                </div>
                <div class="kv-note">{{ diagnosis.chanlun.multi_tf_convergence_intensity_v66.msg }}</div>
              </div>
           </div>

           <!-- V66: 信号执行优先级 -->
           <div v-if="diagnosis.chanlun.signal_execution_priority_v66" class="metric-card v66-priority">
              <div class="card-title">🚦 V66 信号执行优先级（条件199）</div>
              <div class="card-body">
                <div class="kv-row"><span class="kv-key">执行优先级</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.signal_execution_priority_v66.priority === 0, 'tag-blue': diagnosis.chanlun.signal_execution_priority_v66.priority === 1, 'tag-orange': diagnosis.chanlun.signal_execution_priority_v66.priority === 2, 'tag-red': diagnosis.chanlun.signal_execution_priority_v66.priority === 3 }">{{ diagnosis.chanlun.signal_execution_priority_v66.priority_label }}</span></div>
                <div class="kv-row"><span class="kv-key">风险等级</span><span class="tag" :class="diagnosis.chanlun.signal_execution_priority_v66.risk_level === 'low' ? 'tag-green' : diagnosis.chanlun.signal_execution_priority_v66.risk_level === 'medium' ? 'tag-blue' : 'tag-orange'">{{ diagnosis.chanlun.signal_execution_priority_v66.risk_level }}</span></div>
                <div class="kv-row"><span class="kv-key">建议操作</span><span class="kv-val" style="font-weight:700">{{ diagnosis.chanlun.signal_execution_priority_v66.suggested_action }}</span></div>
                <div class="kv-note">{{ diagnosis.chanlun.signal_execution_priority_v66.msg }}</div>
              </div>
           </div>

            <!-- V67: 中枢背驰力度量化 -->
            <div v-if="diagnosis.chanlun.zhongshu_divergence_strength_v67" class="metric-card v67-zs-div">
               <div class="card-title">🎯 V67 中枢背驰力度量化（条件200）</div>
               <div class="card-body">
                 <div class="kv-row"><span class="kv-key">背驰类型</span><span class="tag" :class="diagnosis.chanlun.zhongshu_divergence_strength_v67.divergence_type === 'none' ? 'tag-gray' : diagnosis.chanlun.zhongshu_divergence_strength_v67.divergence_type.includes('strong') ? 'tag-green' : 'tag-blue'">{{ {strong_down:'↓ 强背驰',moderate_down:'↘ 中背驰',strong_up:'↑ 强背驰(卖)',moderate_up:'↗ 中背驰(卖)',none:'无背驰'}[diagnosis.chanlun.zhongshu_divergence_strength_v67.divergence_type] ?? '—' }}</span></div>
                 <div class="kv-row"><span class="kv-key">中枢强度</span><span class="tag" :class="diagnosis.chanlun.zhongshu_divergence_strength_v67.zhongshu_strength === 'weak' ? 'tag-orange' : diagnosis.chanlun.zhongshu_divergence_strength_v67.zhongshu_strength === 'strong' ? 'tag-green' : 'tag-gray'">{{ {weak:'弱',normal:'中',strong:'强'}[diagnosis.chanlun.zhongshu_divergence_strength_v67.zhongshu_strength] ?? '—' }}</span></div>
                 <div class="kv-row"><span class="kv-key">背驰面积比</span><span class="kv-val">{{ diagnosis.chanlun.zhongshu_divergence_strength_v67.backchi_ratio.toFixed(3) }}</span></div>
                 <div class="kv-row" style="margin-top:6px">
                   <span class="kv-key">置信度调整</span>
                   <span :style="{ color: diagnosis.chanlun.zhongshu_divergence_strength_v67.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.zhongshu_divergence_strength_v67.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                     {{ diagnosis.chanlun.zhongshu_divergence_strength_v67.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.zhongshu_divergence_strength_v67.confidence_adjust*100).toFixed(0) }}%
                   </span>
                 </div>
                 <div class="kv-note">{{ diagnosis.chanlun.zhongshu_divergence_strength_v67.msg }}</div>
               </div>
            </div>

            <!-- V67: 多级别买卖点一致性 -->
            <div v-if="diagnosis.chanlun.multi_level_mmd_consistency_v67" class="metric-card v67-ml-cons">
               <div class="card-title">🔗 V67 多级别买卖点一致性（条件201）</div>
               <div class="card-body">
                 <div class="kv-row"><span class="kv-key">短期趋势</span><span class="tag" :class="diagnosis.chanlun.multi_level_mmd_consistency_v67.short_dir === 'up' ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.multi_level_mmd_consistency_v67.short_dir === 'up' ? '↑ 上升' : '↓ 下降' }}</span></div>
                 <div class="kv-row"><span class="kv-key">中期趋势</span><span class="tag" :class="diagnosis.chanlun.multi_level_mmd_consistency_v67.mid_dir === 'up' ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.multi_level_mmd_consistency_v67.mid_dir === 'up' ? '↑ 上升' : '↓ 下降' }}</span></div>
                 <div class="kv-row"><span class="kv-key">长期趋势</span><span class="tag" :class="diagnosis.chanlun.multi_level_mmd_consistency_v67.long_dir === 'up' ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.multi_level_mmd_consistency_v67.long_dir === 'up' ? '↑ 上升' : '↓ 下降' }}</span></div>
                 <div class="kv-row"><span class="kv-key">一致评分</span><span class="kv-val" style="font-weight:700">{{ diagnosis.chanlun.multi_level_mmd_consistency_v67.consistency_score.toFixed(2) }}</span></div>
                 <div class="kv-row" style="margin-top:6px">
                   <span class="kv-key">置信度调整</span>
                   <span :style="{ color: diagnosis.chanlun.multi_level_mmd_consistency_v67.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.multi_level_mmd_consistency_v67.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                     {{ diagnosis.chanlun.multi_level_mmd_consistency_v67.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.multi_level_mmd_consistency_v67.confidence_adjust*100).toFixed(0) }}%
                   </span>
                 </div>
                 <div class="kv-note">{{ diagnosis.chanlun.multi_level_mmd_consistency_v67.msg }}</div>
               </div>
            </div>

            <!-- V67: 信号后价格轨迹健康度 -->
            <div v-if="diagnosis.chanlun.post_signal_trajectory_health_v67" class="metric-card v67-traj">
               <div class="card-title">📊 V67 信号后价格轨迹健康度（条件202）</div>
               <div class="card-body">
                 <div class="kv-row"><span class="kv-key">趋势质量</span><span class="tag" :class="diagnosis.chanlun.post_signal_trajectory_health_v67.trend_quality === 'excellent' ? 'tag-green' : diagnosis.chanlun.post_signal_trajectory_health_v67.trend_quality === 'good' ? 'tag-blue' : diagnosis.chanlun.post_signal_trajectory_health_v67.trend_quality === 'fair' ? 'tag-orange' : 'tag-red'">{{ {excellent:'⭐ 优秀',good:'✅ 良好',fair:'⚠️ 一般',poor:'❌ 较差'}[diagnosis.chanlun.post_signal_trajectory_health_v67.trend_quality] ?? '—' }}</span></div>
                 <div class="kv-row"><span class="kv-key">上涨K线</span><span class="kv-val" style="color:#22c55e">{{ diagnosis.chanlun.post_signal_trajectory_health_v67.up_bars }} 根</span></div>
                 <div class="kv-row"><span class="kv-key">下跌K线</span><span class="kv-val" style="color:#ef4444">{{ diagnosis.chanlun.post_signal_trajectory_health_v67.down_bars }} 根</span></div>
                 <div class="kv-row"><span class="kv-key">最大回撤</span><span class="kv-val">{{ diagnosis.chanlun.post_signal_trajectory_health_v67.max_drawdown_pct.toFixed(2) }}%</span></div>
                 <div class="kv-row" style="margin-top:6px">
                   <span class="kv-key">置信度调整</span>
                   <span :style="{ color: diagnosis.chanlun.post_signal_trajectory_health_v67.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.post_signal_trajectory_health_v67.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                     {{ diagnosis.chanlun.post_signal_trajectory_health_v67.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.post_signal_trajectory_health_v67.confidence_adjust*100).toFixed(0) }}%
                   </span>
                 </div>
                 <div class="kv-note">{{ diagnosis.chanlun.post_signal_trajectory_health_v67.msg }}</div>
               </div>
            </div>

            <!-- V67: 动态止损止盈推荐 -->
            <div v-if="diagnosis.chanlun.dynamic_sl_tp_recommendation_v67" class="metric-card v67-sltp">
               <div class="card-title">🛡️ V67 动态止损止盈推荐（条件203）</div>
               <div class="card-body">
                 <div class="kv-row"><span class="kv-key">止损位</span><span class="kv-val" style="color: #ef4444">{{ diagnosis.chanlun.dynamic_sl_tp_recommendation_v67.stop_loss }}</span></div>
                 <div class="kv-row"><span class="kv-key">止盈位</span><span class="kv-val" style="color: #22c55e">{{ diagnosis.chanlun.dynamic_sl_tp_recommendation_v67.take_profit }}</span></div>
                 <div class="kv-row"><span class="kv-key">风险收益比</span><span class="kv-val" style="color:#3b82f6;font-weight:700">{{ diagnosis.chanlun.dynamic_sl_tp_recommendation_v67.risk_reward_ratio.toFixed(2) }}:1</span></div>
                 <div class="kv-row"><span class="kv-key">建议仓位</span><span class="kv-val">{{ (diagnosis.chanlun.dynamic_sl_tp_recommendation_v67.position_size_pct * 100).toFixed(0) }}%</span></div>
                 <div class="kv-row" style="margin-top:6px">
                   <span class="kv-key">置信度调整</span>
                   <span :style="{ color: diagnosis.chanlun.dynamic_sl_tp_recommendation_v67.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.dynamic_sl_tp_recommendation_v67.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 700 }">
                     {{ diagnosis.chanlun.dynamic_sl_tp_recommendation_v67.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.dynamic_sl_tp_recommendation_v67.confidence_adjust*100).toFixed(0) }}%
                   </span>
                 </div>
                 <div class="kv-note">{{ diagnosis.chanlun.dynamic_sl_tp_recommendation_v67.msg }}</div>
               </div>
            </div>

            <!-- V68: 缺口方向与趋势一致性验证 -->
            <div v-if="diagnosis.chanlun.gap_trend_consistency_v68" class="metric-card v68-gap">
               <div class="card-title">🕳️ V68 缺口趋势一致性（条件204）</div>
               <div class="card-body">
                 <div class="kv-row"><span class="kv-key">缺口检测</span><span class="tag" :class="diagnosis.chanlun.gap_trend_consistency_v68.gap_detected ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.gap_trend_consistency_v68.gap_detected ? '✅ 发现' : '❌ 无' }}</span></div>
                 <div class="kv-row"><span class="kv-key">缺口方向</span><span class="tag" :class="diagnosis.chanlun.gap_trend_consistency_v68.gap_direction === 'up' ? 'tag-green' : diagnosis.chanlun.gap_trend_consistency_v68.gap_direction === 'down' ? 'tag-red' : 'tag-gray'">{{ {up:'↑ 向上',down:'↓ 向下',none:'—'}[diagnosis.chanlun.gap_trend_consistency_v68.gap_direction] ?? '—' }}</span></div>
                 <div class="kv-row"><span class="kv-key">趋势方向</span><span class="tag" :class="diagnosis.chanlun.gap_trend_consistency_v68.trend_alignment === 'up' ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.gap_trend_consistency_v68.trend_alignment === 'up' ? '↑ 上升' : '↓ 下降' }}</span></div>
                 <div class="kv-row"><span class="kv-key">质量评级</span><span class="tag" :class="diagnosis.chanlun.gap_trend_consistency_v68.gap_quality === 'strong' ? 'tag-green' : diagnosis.chanlun.gap_trend_consistency_v68.gap_quality === 'weak' ? 'tag-red' : 'tag-orange'">{{ {strong:'⭐ 强',moderate:'⚡ 中',weak:'⚠️ 弱',no_gap_trend_ok:'→ 无缺趋势正',no_gap_trend_bad:'↓ 无缺趋势负'}[diagnosis.chanlun.gap_trend_consistency_v68.gap_quality] ?? '—' }}</span></div>
                 <div class="kv-row" style="margin-top:6px">
                   <span class="kv-key">置信度调整</span>
                   <span :style="{ color: diagnosis.chanlun.gap_trend_consistency_v68.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.gap_trend_consistency_v68.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                     {{ diagnosis.chanlun.gap_trend_consistency_v68.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.gap_trend_consistency_v68.confidence_adjust*100).toFixed(0) }}%
                   </span>
                 </div>
                 <div class="kv-note">{{ diagnosis.chanlun.gap_trend_consistency_v68.msg }}</div>
               </div>
            </div>

            <!-- V68: 多级别区间套一致性 -->
            <div v-if="diagnosis.chanlun.range_set_multi_level_v68" class="metric-card v68-range">
               <div class="card-title">🔲 V68 区间套一致性（条件205）</div>
               <div class="card-body">
                 <div class="kv-row"><span class="kv-key">中枢数量</span><span class="kv-val">{{ diagnosis.chanlun.range_set_multi_level_v68.zhongshu_count }}</span></div>
                 <div class="kv-row"><span class="kv-key">价格上方中枢</span><span class="tag tag-red">{{ diagnosis.chanlun.range_set_multi_level_v68.zs_above_price }} 个</span></div>
                 <div class="kv-row"><span class="kv-key">价格下方中枢</span><span class="tag tag-green">{{ diagnosis.chanlun.range_set_multi_level_v68.zs_below_price }} 个</span></div>
                 <div class="kv-row"><span class="kv-key">区间套评分</span><span class="kv-val" style="font-weight:700">{{ diagnosis.chanlun.range_set_multi_level_v68.multi_level_score.toFixed(3) }}</span></div>
                 <div class="kv-row" style="margin-top:6px">
                   <span class="kv-key">置信度调整</span>
                   <span :style="{ color: diagnosis.chanlun.range_set_multi_level_v68.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.range_set_multi_level_v68.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                     {{ diagnosis.chanlun.range_set_multi_level_v68.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.range_set_multi_level_v68.confidence_adjust*100).toFixed(0) }}%
                   </span>
                 </div>
                 <div class="kv-note">{{ diagnosis.chanlun.range_set_multi_level_v68.msg }}</div>
               </div>
            </div>

            <!-- V68: 信号后资金流向确认 -->
            <div v-if="diagnosis.chanlun.post_signal_fund_flow_v68" class="metric-card v68-fund">
               <div class="card-title">💰 V68 资金流向确认（条件206）</div>
               <div class="card-body">
                 <div class="kv-row"><span class="kv-key">资金流向</span><span class="tag" :class="diagnosis.chanlun.post_signal_fund_flow_v68.fund_flow_direction.includes('inflow') && !diagnosis.chanlun.post_signal_fund_flow_v68.fund_flow_direction.includes('outflow') ? 'tag-green' : diagnosis.chanlun.post_signal_fund_flow_v68.fund_flow_direction.includes('outflow') ? 'tag-red' : 'tag-gray'">{{ {inflow_strong:'↑↑ 大幅流入',inflow_moderate:'↑ 中等流入',inflow_weak:'↑ 微弱流入',outflow_strong:'↓↓ 大幅流出',outflow_moderate:'↓ 中等流出',outflow_weak:'↓ 微弱流出',neutral:'→ 中性'}[diagnosis.chanlun.post_signal_fund_flow_v68.fund_flow_direction] ?? diagnosis.chanlun.post_signal_fund_flow_v68.fund_flow_direction }}</span></div>
                 <div class="kv-row"><span class="kv-key">平均量比</span><span class="kv-val">{{ diagnosis.chanlun.post_signal_fund_flow_v68.avg_volume_ratio.toFixed(2) }}</span></div>
                 <div class="kv-row"><span class="kv-key">流向置信</span><span class="tag" :class="diagnosis.chanlun.post_signal_fund_flow_v68.flow_confidence === 'strong' ? 'tag-green' : diagnosis.chanlun.post_signal_fund_flow_v68.flow_confidence === 'moderate' ? 'tag-blue' : diagnosis.chanlun.post_signal_fund_flow_v68.flow_confidence === 'warning' ? 'tag-orange' : 'tag-gray'">{{ {strong:'⭐ 强',moderate:'✅ 中',weak:'⚡ 弱',warning:'⚠️ 警示',neutral:'→ 中性'}[diagnosis.chanlun.post_signal_fund_flow_v68.flow_confidence] ?? '—' }}</span></div>
                 <div class="kv-row" style="margin-top:6px">
                   <span class="kv-key">置信度调整</span>
                   <span :style="{ color: diagnosis.chanlun.post_signal_fund_flow_v68.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.post_signal_fund_flow_v68.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                     {{ diagnosis.chanlun.post_signal_fund_flow_v68.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.post_signal_fund_flow_v68.confidence_adjust*100).toFixed(0) }}%
                   </span>
                 </div>
                 <div class="kv-note">{{ diagnosis.chanlun.post_signal_fund_flow_v68.msg }}</div>
               </div>
            </div>

            <!-- V68: 市场风格适配评分 -->
            <div v-if="diagnosis.chanlun.market_regime_adaptation_v68" class="metric-card v68-regime">
               <div class="card-title">🌊 V68 市场风格适配（条件207）</div>
               <div class="card-body">
                 <div class="kv-row"><span class="kv-key">ATR占比</span><span class="kv-val">{{ diagnosis.chanlun.market_regime_adaptation_v68.atr_pct.toFixed(2) }}%</span></div>
                 <div class="kv-row"><span class="kv-key">波动率状态</span><span class="tag" :class="diagnosis.chanlun.market_regime_adaptation_v68.volatility_regime === 'low' ? 'tag-blue' : diagnosis.chanlun.market_regime_adaptation_v68.volatility_regime === 'normal' ? 'tag-gray' : 'tag-orange'">{{ {low:'🟢 低波',normal:'🟡 正常',high:'🟠 高波'}[diagnosis.chanlun.market_regime_adaptation_v68.volatility_regime] ?? '—' }}</span></div>
                 <div class="kv-row"><span class="kv-key">趋势强度</span><span class="tag" :class="diagnosis.chanlun.market_regime_adaptation_v68.trend_strength === 'strong' ? 'tag-green' : diagnosis.chanlun.market_regime_adaptation_v68.trend_strength === 'moderate' ? 'tag-blue' : 'tag-gray'">{{ {strong:'⭐ 强趋势',moderate:'⚡ 中趋势',weak:'→ 弱趋势'}[diagnosis.chanlun.market_regime_adaptation_v68.trend_strength] ?? '—' }}</span></div>
                 <div class="kv-row"><span class="kv-key">适配评分</span><span class="kv-val" style="font-weight:700">{{ diagnosis.chanlun.market_regime_adaptation_v68.adaptation_score.toFixed(2) }}</span></div>
                 <div class="kv-row" style="margin-top:6px">
                   <span class="kv-key">置信度调整</span>
                   <span :style="{ color: diagnosis.chanlun.market_regime_adaptation_v68.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.market_regime_adaptation_v68.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 700 }">
                     {{ diagnosis.chanlun.market_regime_adaptation_v68.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.market_regime_adaptation_v68.confidence_adjust*100).toFixed(0) }}%
                   </span>
                 </div>
                 <div class="kv-note">{{ diagnosis.chanlun.market_regime_adaptation_v68.msg }}</div>
                </div>
            </div>

            
             <!-- V69: 量价背离二次确认 -->
             <div v-if="diagnosis.chanlun.price_volume_divergence_v69" class="metric-card v69-pv">
                <div class="card-title">📊 V69 量价背离确认（条件208）</div>
                <div class="card-body">
                  <div class="kv-row"><span class="kv-key">价格趋势</span><span class="tag" :class="diagnosis.chanlun.price_volume_divergence_v69.price_trend === 'up' ? 'tag-green' : diagnosis.chanlun.price_volume_divergence_v69.price_trend === 'down' ? 'tag-red' : 'tag-gray'">{{ {up:'↑ 上涨',down:'↓ 下跌',flat:'→ 盘整'}[diagnosis.chanlun.price_volume_divergence_v69.price_trend] ?? '—' }}</span></div>
                  <div class="kv-row"><span class="kv-key">量能趋势</span><span class="tag" :class="diagnosis.chanlun.price_volume_divergence_v69.volume_trend === 'expanding' ? 'tag-green' : diagnosis.chanlun.price_volume_divergence_v69.volume_trend === 'shrinking' ? 'tag-blue' : 'tag-gray'">{{ {expanding:'📈 放量',shrinking:'📉 缩量',stable:'➡️ 平稳'}[diagnosis.chanlun.price_volume_divergence_v69.volume_trend] ?? '—' }}</span></div>
                  <div class="kv-row"><span class="kv-key">背离类型</span><span class="tag" :class="diagnosis.chanlun.price_volume_divergence_v69.divergence_type.includes('bullish') ? 'tag-green' : diagnosis.chanlun.price_volume_divergence_v69.divergence_type.includes('bearish') ? 'tag-red' : 'tag-gray'">{{ {bullish:'🟢 看涨背离',weak_bullish:'🔵 弱看涨',bearish:'🔴 看跌背离',weak_bearish:'🟠 弱看跌',none:'⚪ 无背离'}[diagnosis.chanlun.price_volume_divergence_v69.divergence_type] ?? '—' }}</span></div>
                  <div class="kv-row"><span class="kv-key">背离强度</span><span class="kv-val" style="font-weight:700">{{ diagnosis.chanlun.price_volume_divergence_v69.divergence_strength.toFixed(3) }}</span></div>
                  <div class="kv-row" style="margin-top:6px">
                    <span class="kv-key">置信度调整</span>
                    <span :style="{ color: diagnosis.chanlun.price_volume_divergence_v69.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.price_volume_divergence_v69.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                      {{ diagnosis.chanlun.price_volume_divergence_v69.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.price_volume_divergence_v69.confidence_adjust*100).toFixed(0) }}%
                    </span>
                  </div>
                  <div class="kv-note">{{ diagnosis.chanlun.price_volume_divergence_v69.msg }}</div>
                </div>
             </div>

             <!-- V69: 结构完整性评分 -->
             <div v-if="diagnosis.chanlun.structural_integrity_v69" class="metric-card v69-struct">
                <div class="card-title">🏗️ V69 结构完整性（条件209）</div>
                <div class="card-body">
                  <div class="kv-row"><span class="kv-key">笔完成</span><span class="tag" :class="diagnosis.chanlun.structural_integrity_v69.bi_complete ? 'tag-green' : 'tag-orange'">{{ diagnosis.chanlun.structural_integrity_v69.bi_complete ? '✅ 已完成' : '⏳ 未完成' }}</span></div>
                  <div class="kv-row"><span class="kv-key">笔序列</span><span class="tag" :class="diagnosis.chanlun.structural_integrity_v69.bi_sequence_valid ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.structural_integrity_v69.bi_sequence_valid ? '✅ 连续' : '❌ 断裂' }}</span></div>
                  <div class="kv-row"><span class="kv-key">中枢有效</span><span class="tag" :class="diagnosis.chanlun.structural_integrity_v69.zhongshu_valid ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.structural_integrity_v69.zhongshu_valid ? '✅ 有效' : '⚪ 无效' }}</span></div>
                  <div class="kv-row"><span class="kv-key">结构评分</span><span class="kv-val" style="font-weight:700">{{ diagnosis.chanlun.structural_integrity_v69.structural_score.toFixed(3) }}</span></div>
                  <div class="kv-row" style="margin-top:6px">
                    <span class="kv-key">置信度调整</span>
                    <span :style="{ color: diagnosis.chanlun.structural_integrity_v69.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.structural_integrity_v69.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                      {{ diagnosis.chanlun.structural_integrity_v69.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.structural_integrity_v69.confidence_adjust*100).toFixed(0) }}%
                    </span>
                  </div>
                  <div class="kv-note">{{ diagnosis.chanlun.structural_integrity_v69.msg }}</div>
                </div>
             </div>

             <!-- V69: 多指标背离融合 -->
             <div v-if="diagnosis.chanlun.multi_indicator_divergence_v69" class="metric-card v69-multi">
                <div class="card-title">🔀 V69 多指标背离融合（条件210）</div>
                <div class="card-body">
                  <div class="kv-row"><span class="kv-key">MACD背离</span><span class="tag" :class="diagnosis.chanlun.multi_indicator_divergence_v69.macd_divergence === 'bullish' ? 'tag-green' : diagnosis.chanlun.multi_indicator_divergence_v69.macd_divergence === 'bearish' ? 'tag-red' : 'tag-gray'">{{ {bullish:'🟢 看涨',bearish:'🔴 看跌',none:'⚪ 无'}[diagnosis.chanlun.multi_indicator_divergence_v69.macd_divergence] ?? '—' }}</span></div>
                  <div class="kv-row"><span class="kv-key">RSI背离</span><span class="tag" :class="diagnosis.chanlun.multi_indicator_divergence_v69.rsi_divergence === 'bullish' ? 'tag-green' : diagnosis.chanlun.multi_indicator_divergence_v69.rsi_divergence === 'bearish' ? 'tag-red' : 'tag-gray'">{{ {bullish:'🟢 看涨',bearish:'🔴 看跌',none:'⚪ 无'}[diagnosis.chanlun.multi_indicator_divergence_v69.rsi_divergence] ?? '—' }}</span></div>
                  <div class="kv-row"><span class="kv-key">KDJ背离</span><span class="tag" :class="diagnosis.chanlun.multi_indicator_divergence_v69.kdj_divergence === 'bullish' ? 'tag-green' : diagnosis.chanlun.multi_indicator_divergence_v69.kdj_divergence === 'bearish' ? 'tag-red' : 'tag-gray'">{{ {bullish:'🟢 看涨',bearish:'🔴 看跌',none:'⚪ 无'}[diagnosis.chanlun.multi_indicator_divergence_v69.kdj_divergence] ?? '—' }}</span></div>
                  <div class="kv-row"><span class="kv-key">共振数</span><span class="kv-val" style="font-weight:700">{{ diagnosis.chanlun.multi_indicator_divergence_v69.resonance_count }} / 3</span></div>
                  <div class="kv-row" style="margin-top:6px">
                    <span class="kv-key">置信度调整</span>
                    <span :style="{ color: diagnosis.chanlun.multi_indicator_divergence_v69.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.multi_indicator_divergence_v69.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                      {{ diagnosis.chanlun.multi_indicator_divergence_v69.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.multi_indicator_divergence_v69.confidence_adjust*100).toFixed(0) }}%
                    </span>
                  </div>
                  <div class="kv-note">{{ diagnosis.chanlun.multi_indicator_divergence_v69.msg }}</div>
                </div>
             </div>

             <!-- V69: 回踩深度量化 -->
             <div v-if="diagnosis.chanlun.retracement_depth_v69" class="metric-card v69-ret">
                <div class="card-title">📐 V69 回踩深度量化（条件211）</div>
                <div class="card-body">
                  <div class="kv-row"><span class="kv-key">回踩深度</span><span class="kv-val">{{ diagnosis.chanlun.retracement_depth_v69.retracement_depth_pct.toFixed(1) }}%</span></div>
                  <div class="kv-row"><span class="kv-key">回踩类型</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.retracement_depth_v69.retracement_type === 'optimal', 'tag-blue': diagnosis.chanlun.retracement_depth_v69.retracement_type === 'shallow', 'tag-orange': diagnosis.chanlun.retracement_depth_v69.retracement_type === 'deep', 'tag-red': diagnosis.chanlun.retracement_depth_v69.retracement_type === 'breakdown' }">{{ {optimal:'✅ 理想',shallow:'🔵 偏浅',deep:'🟠 偏深',breakdown:'🔴 过度'}[diagnosis.chanlun.retracement_depth_v69.retracement_type] ?? '—' }}</span></div>
                  <div class="kv-row"><span class="kv-key">最优区间</span><span class="tag" :class="diagnosis.chanlun.retracement_depth_v69.optimal_range === 'yes' ? 'tag-green' : diagnosis.chanlun.retracement_depth_v69.optimal_range === 'partial' ? 'tag-blue' : 'tag-red'">{{ {yes:'✅ 是',partial:'△ 部分',no:'❌ 否'}[diagnosis.chanlun.retracement_depth_v69.optimal_range] ?? '—' }}</span></div>
                  <div class="kv-row" style="margin-top:6px">
                    <span class="kv-key">置信度调整</span>
                    <span :style="{ color: diagnosis.chanlun.retracement_depth_v69.confidence_adjust > 0 ? '#22c55e' : diagnosis.chanlun.retracement_depth_v69.confidence_adjust < 0 ? '#ef4444' : '#9ca3af', fontWeight: 600 }">
                      {{ diagnosis.chanlun.retracement_depth_v69.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.retracement_depth_v69.confidence_adjust*100).toFixed(0) }}%
                    </span>
                  </div>
                  <div class="kv-note">{{ diagnosis.chanlun.retracement_depth_v69.msg }}</div>
                </div>
             </div>

              <!-- V70: 分时量峰检测 -->
              <div v-if="diagnosis.chanlun.volume_peak_detection_v70" class="metric-card v70-vp">
                 <div class="card-title">📊 V70 量峰检测（条件212）</div>
                 <div class="card-body">
                   <div class="kv-row"><span class="kv-key">量峰比</span><span class="kv-val">{{ diagnosis.chanlun.volume_peak_detection_v70.peak_ratio.toFixed(2) }}x</span></div>
                   <div class="kv-row"><span class="kv-key">量峰确认</span><span class="tag" :class="diagnosis.chanlun.volume_peak_detection_v70.peak_detected ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.volume_peak_detection_v70.peak_detected ? '✅ 确认' : '❌ 未确认' }}</span></div>
                   <div class="kv-row"><span class="kv-key">量能强度</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.volume_peak_detection_v70.volume_strength === 'strong', 'tag-blue': diagnosis.chanlun.volume_peak_detection_v70.volume_strength === 'moderate', 'tag-gray': diagnosis.chanlun.volume_peak_detection_v70.volume_strength === 'weak' }">{{ {strong:'📈 强',moderate:'📉 中',weak:'⚪ 弱'}[diagnosis.chanlun.volume_peak_detection_v70.volume_strength] ?? '—' }}</span></div>
                   <div class="kv-row" style="margin-top:6px">
                     <span class="kv-key">置信度调整</span>
                     <span :style="{ color: diagnosis.chanlun.volume_peak_detection_v70.confidence_adjust > 0 ? '#22c55e' : '#ef4444', fontWeight: 600 }">
                       {{ diagnosis.chanlun.volume_peak_detection_v70.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.volume_peak_detection_v70.confidence_adjust*100).toFixed(0) }}%
                     </span>
                   </div>
                   <div class="kv-note">{{ diagnosis.chanlun.volume_peak_detection_v70.msg }}</div>
                 </div>
              </div>

              <!-- V70: 信号时间衰减 -->
              <div v-if="diagnosis.chanlun.signal_time_decay_v70" class="metric-card v70-decay">
                 <div class="card-title">⏱️ V70 信号衰减（条件213）</div>
                 <div class="card-body">
                   <div class="kv-row"><span class="kv-key">信号后K线</span><span class="kv-val">{{ diagnosis.chanlun.signal_time_decay_v70.bar_count }} 根</span></div>
                   <div class="kv-row"><span class="kv-key">衰减因子</span><span class="kv-val">{{ diagnosis.chanlun.signal_time_decay_v70.decay_factor.toFixed(3) }}</span></div>
                   <div class="kv-row"><span class="kv-key">时效等级</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.signal_time_decay_v70.signal_age === 'fresh', 'tag-blue': diagnosis.chanlun.signal_time_decay_v70.signal_age === 'moderate', 'tag-orange': diagnosis.chanlun.signal_time_decay_v70.signal_age === 'aging', 'tag-red': diagnosis.chanlun.signal_time_decay_v70.signal_age === 'old' }">{{ {fresh:'🟢 新鲜',moderate:'🔵 中期',aging:'🟠 衰退',old:'🔴 过期'}[diagnosis.chanlun.signal_time_decay_v70.signal_age] ?? '—' }}</span></div>
                   <div class="kv-row" style="margin-top:6px">
                     <span class="kv-key">置信度调整</span>
                     <span :style="{ color: diagnosis.chanlun.signal_time_decay_v70.confidence_adjust >= 0 ? '#22c55e' : '#ef4444', fontWeight: 600 }">
                       {{ diagnosis.chanlun.signal_time_decay_v70.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.signal_time_decay_v70.confidence_adjust*100).toFixed(0) }}%
                     </span>
                   </div>
                   <div class="kv-note">{{ diagnosis.chanlun.signal_time_decay_v70.msg }}</div>
                 </div>
              </div>

              <!-- V70: 假突破过滤 -->
              <div v-if="diagnosis.chanlun.false_breakout_filter_v70" class="metric-card v70-fb">
                 <div class="card-title">🛡️ V70 假突破过滤（条件214）</div>
                 <div class="card-body">
                   <div class="kv-row"><span class="kv-key">持续根数</span><span class="kv-val">{{ diagnosis.chanlun.false_breakout_filter_v70.sustained_bars }} 根</span></div>
                   <div class="kv-row"><span class="kv-key">突破确认</span><span class="tag" :class="diagnosis.chanlun.false_breakout_filter_v70.is_sustained ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.false_breakout_filter_v70.is_sustained ? '✅ 真突破' : '❌ 疑似假突破' }}</span></div>
                   <div class="kv-row"><span class="kv-key">突破质量</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.false_breakout_filter_v70.breakout_quality === 'strong', 'tag-blue': diagnosis.chanlun.false_breakout_filter_v70.breakout_quality === 'good', 'tag-orange': diagnosis.chanlun.false_breakout_filter_v70.breakout_quality === 'moderate', 'tag-gray': diagnosis.chanlun.false_breakout_filter_v70.breakout_quality === 'weak', 'tag-red': diagnosis.chanlun.false_breakout_filter_v70.breakout_quality === 'fake' }">{{ {strong:'🟢 强',good:'🔵 良',moderate:'🟠 中',weak:'⚪ 弱',fake:'🔴 假'}[diagnosis.chanlun.false_breakout_filter_v70.breakout_quality] ?? '—' }}</span></div>
                   <div class="kv-row" style="margin-top:6px">
                     <span class="kv-key">置信度调整</span>
                     <span :style="{ color: diagnosis.chanlun.false_breakout_filter_v70.confidence_adjust > 0 ? '#22c55e' : '#ef4444', fontWeight: 600 }">
                       {{ diagnosis.chanlun.false_breakout_filter_v70.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.false_breakout_filter_v70.confidence_adjust*100).toFixed(0) }}%
                     </span>
                   </div>
                   <div class="kv-note">{{ diagnosis.chanlun.false_breakout_filter_v70.msg }}</div>
                 </div>
              </div>

              <!-- V70: 置信度最终校准 -->
              <div v-if="diagnosis.chanlun.final_confidence_calibration_v70" class="metric-card v70-cali">
                 <div class="card-title">🎯 V70 置信度校准（条件215）</div>
                 <div class="card-body">
                   <div class="kv-row"><span class="kv-key">总调整</span><span class="kv-val" :style="{ color: diagnosis.chanlun.final_confidence_calibration_v70.total_adjust > 0 ? '#22c55e' : '#ef4444' }">{{ diagnosis.chanlun.final_confidence_calibration_v70.total_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.final_confidence_calibration_v70.total_adjust*100).toFixed(0) }}%</span></div>
                   <div class="kv-row"><span class="kv-key">校准后置信</span><span class="kv-val" style="font-weight:700">{{ diagnosis.chanlun.final_confidence_calibration_v70.calibrated_confidence.toFixed(3) }}</span></div>
                   <div class="kv-row"><span class="kv-key">校准等级</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.final_confidence_calibration_v70.calibration_level === 'high', 'tag-blue': diagnosis.chanlun.final_confidence_calibration_v70.calibration_level === 'medium', 'tag-orange': diagnosis.chanlun.final_confidence_calibration_v70.calibration_level === 'low', 'tag-red': diagnosis.chanlun.final_confidence_calibration_v70.calibration_level === 'critical' }">{{ {high:'🟢 高',medium:'🔵 中',low:'🟠 低',critical:'🔴 危'}[diagnosis.chanlun.final_confidence_calibration_v70.calibration_level] ?? '—' }}</span></div>
                   <div class="kv-row"><span class="kv-key">调整统计</span><span class="kv-val">共{{ diagnosis.chanlun.final_confidence_calibration_v70.adjust_count }}项 (+{{ diagnosis.chanlun.final_confidence_calibration_v70.positive_adjusts }}/-{{ diagnosis.chanlun.final_confidence_calibration_v70.negative_adjusts }})</span></div>
                   <div class="kv-note">{{ diagnosis.chanlun.final_confidence_calibration_v70.msg }}</div>
                 </div>
              </div>

             
              <!-- V71: 均线排列强度评估 -->
              <div v-if="diagnosis.chanlun.ma_alignment_strength_v71" class="metric-card v71-ma">
                 <div class="card-title">📊 V71 均线排列强度（条件216）</div>
                 <div class="card-body">
                   <div class="kv-row"><span class="kv-key">排列状态</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.ma_alignment_strength_v71.alignment === 'bullish', 'tag-red': diagnosis.chanlun.ma_alignment_strength_v71.alignment === 'bearish', 'tag-orange': diagnosis.chanlun.ma_alignment_strength_v71.alignment === 'mixed' }">{{ {bullish:'🟢 多头排列',bearish:'🔴 空头排列',mixed:'🟠 混合排列'}[diagnosis.chanlun.ma_alignment_strength_v71.alignment] ?? '—' }}</span></div>
                   <div class="kv-row"><span class="kv-key">趋势强度</span><span class="kv-val">{{ diagnosis.chanlun.ma_alignment_strength_v71.strength.toFixed(3) }}</span></div>
                   <div class="kv-row" style="margin-top:6px">
                     <span class="kv-key">置信度调整</span>
                     <span :style="{ color: diagnosis.chanlun.ma_alignment_strength_v71.confidence_adjust > 0 ? '#22c55e' : '#ef4444', fontWeight: 600 }">
                       {{ diagnosis.chanlun.ma_alignment_strength_v71.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.ma_alignment_strength_v71.confidence_adjust*100).toFixed(0) }}%
                     </span>
                   </div>
                   <div class="kv-note">{{ diagnosis.chanlun.ma_alignment_strength_v71.msg }}</div>
                 </div>
              </div>

              <!-- V71: 多周期均线共振 -->
              <div v-if="diagnosis.chanlun.multi_tf_ma_resonance_v71" class="metric-card v71-res">
                 <div class="card-title">🔗 V71 多周期均线共振（条件217）</div>
                 <div class="card-body">
                   <div class="kv-row"><span class="kv-key">短期共振</span><span class="tag" :class="diagnosis.chanlun.multi_tf_ma_resonance_v71.short_aligned ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.multi_tf_ma_resonance_v71.short_aligned ? '✅ 同向' : '❌ 反向' }}</span></div>
                   <div class="kv-row"><span class="kv-key">中期共振</span><span class="tag" :class="diagnosis.chanlun.multi_tf_ma_resonance_v71.mid_aligned ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.multi_tf_ma_resonance_v71.mid_aligned ? '✅ 同向' : '❌ 反向' }}</span></div>
                   <div class="kv-row"><span class="kv-key">长期共振</span><span class="tag" :class="diagnosis.chanlun.multi_tf_ma_resonance_v71.long_aligned ? 'tag-green' : 'tag-red'">{{ diagnosis.chanlun.multi_tf_ma_resonance_v71.long_aligned ? '✅ 同向' : '❌ 反向' }}</span></div>
                   <div class="kv-row"><span class="kv-key">共振数</span><span class="kv-val">{{ diagnosis.chanlun.multi_tf_ma_resonance_v71.resonance_count }} / 3</span></div>
                   <div class="kv-row" style="margin-top:6px">
                     <span class="kv-key">置信度调整</span>
                     <span :style="{ color: diagnosis.chanlun.multi_tf_ma_resonance_v71.confidence_adjust > 0 ? '#22c55e' : '#ef4444', fontWeight: 600 }">
                       {{ diagnosis.chanlun.multi_tf_ma_resonance_v71.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.multi_tf_ma_resonance_v71.confidence_adjust*100).toFixed(0) }}%
                     </span>
                   </div>
                   <div class="kv-note">{{ diagnosis.chanlun.multi_tf_ma_resonance_v71.msg }}</div>
                 </div>
              </div>

              <!-- V71: 历史胜率回溯 -->
              <div v-if="diagnosis.chanlun.mmd_history_winrate_v71" class="metric-card v71-win">
                 <div class="card-title">📈 V71 历史胜率回溯（条件218）</div>
                 <div class="card-body">
                   <div class="kv-row"><span class="kv-key">回溯胜率</span><span class="kv-val" :style="{ color: diagnosis.chanlun.mmd_history_winrate_v71.lookback_winrate >= 0.5 ? '#22c55e' : '#ef4444', fontWeight: 700 }">{{ (diagnosis.chanlun.mmd_history_winrate_v71.lookback_winrate * 100).toFixed(1) }}%</span></div>
                   <div class="kv-row"><span class="kv-key">样本数量</span><span class="kv-val">{{ diagnosis.chanlun.mmd_history_winrate_v71.sample_count }} 个形态</span></div>
                   <div class="kv-row" style="margin-top:6px">
                     <span class="kv-key">置信度调整</span>
                     <span :style="{ color: diagnosis.chanlun.mmd_history_winrate_v71.confidence_adjust > 0 ? '#22c55e' : '#ef4444', fontWeight: 600 }">
                       {{ diagnosis.chanlun.mmd_history_winrate_v71.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.mmd_history_winrate_v71.confidence_adjust*100).toFixed(0) }}%
                     </span>
                   </div>
                   <div class="kv-note">{{ diagnosis.chanlun.mmd_history_winrate_v71.msg }}</div>
                 </div>
              </div>

              <!-- V71: 动态风险收益比 -->
              <div v-if="diagnosis.chanlun.dynamic_rr_optimization_v71" class="metric-card v71-rr">
                 <div class="card-title">⚖️ V71 动态风险收益（条件219）</div>
                 <div class="card-body">
                   <div class="kv-row"><span class="kv-key">止损幅度</span><span class="kv-val" style="color:#ef4444">-{{ diagnosis.chanlun.dynamic_rr_optimization_v71.stop_loss_pct.toFixed(2) }}%</span></div>
                   <div class="kv-row"><span class="kv-key">止盈幅度</span><span class="kv-val" style="color:#22c55e">+{{ diagnosis.chanlun.dynamic_rr_optimization_v71.take_profit_pct.toFixed(2) }}%</span></div>
                   <div class="kv-row"><span class="kv-key">风险收益比</span><span class="kv-val" style="font-weight:700">{{ diagnosis.chanlun.dynamic_rr_optimization_v71.rr_ratio.toFixed(1) }}x</span></div>
                   <div class="kv-row"><span class="kv-key">ATR基准</span><span class="kv-val">SL={{ diagnosis.chanlun.dynamic_rr_optimization_v71.atr_based_sl.toFixed(2) }}% TP={{ diagnosis.chanlun.dynamic_rr_optimization_v71.atr_based_tp.toFixed(2) }}%</span></div>
                   <div class="kv-note">{{ diagnosis.chanlun.dynamic_rr_optimization_v71.msg }}</div>
                 </div>
              </div>
              <!-- V72: 均线收敛发散状态评估 -->
              <div v-if="diagnosis.chanlun.ma_convergence_divergence_v72" class="metric-card v72-ma">
                 <div class="card-title">📊 V72 均线收敛发散（条件220）</div>
                 <div class="card-body">
                   <div class="kv-row"><span class="kv-key">状态</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.ma_convergence_divergence_v72.state === 'converging', 'tag-red': diagnosis.chanlun.ma_convergence_divergence_v72.state === 'diverging', 'tag-orange': diagnosis.chanlun.ma_convergence_divergence_v72.state === 'entangled' }">{{ {converging:'🟢 收敛',diverging:'🔴 发散',entangled:'🟠 纠缠'}[diagnosis.chanlun.ma_convergence_divergence_v72.state] ?? '—' }}</span></div>
                   <div class="kv-row"><span class="kv-key">MA间距</span><span class="kv-val">{{ diagnosis.chanlun.ma_convergence_divergence_v72.spread_pct.toFixed(3) }}%</span></div>
                   <div class="kv-row"><span class="kv-key">间距变化</span><span class="kv-val" :style="{ color: diagnosis.chanlun.ma_convergence_divergence_v72.spread_change_pct < 0 ? '#22c55e' : '#ef4444' }">{{ diagnosis.chanlun.ma_convergence_divergence_v72.spread_change_pct >= 0 ? '+' : '' }}{{ diagnosis.chanlun.ma_convergence_divergence_v72.spread_change_pct.toFixed(3) }}%</span></div>
                   <div class="kv-row"><span class="kv-key">收敛分</span><span class="kv-val">{{ diagnosis.chanlun.ma_convergence_divergence_v72.convergence_score.toFixed(3) }}</span></div>
                   <div class="kv-note">{{ diagnosis.chanlun.ma_convergence_divergence_v72.msg }}</div>
                 </div>
              </div>
              <!-- V72: 支撑/阻力位距离评估 -->
              <div v-if="diagnosis.chanlun.support_resistance_proximity_v72" class="metric-card v72-sr">
                 <div class="card-title">📐 V72 支撑阻力距离（条件221）</div>
                 <div class="card-body">
                   <div class="kv-row"><span class="kv-key">当前价</span><span class="kv-val">{{ diagnosis.chanlun.support_resistance_proximity_v72.current_price }}</span></div>
                   <div class="kv-row"><span class="kv-key">最近支撑</span><span class="kv-val" style="color:#22c55e">{{ diagnosis.chanlun.support_resistance_proximity_v72.nearest_support }} ({{ diagnosis.chanlun.support_resistance_proximity_v72.support_dist_pct >= 0 ? '+' : '' }}{{ diagnosis.chanlun.support_resistance_proximity_v72.support_dist_pct }}%)</span></div>
                   <div class="kv-row"><span class="kv-key">最近阻力</span><span class="kv-val" style="color:#ef4444">{{ diagnosis.chanlun.support_resistance_proximity_v72.nearest_resistance }} ({{ diagnosis.chanlun.support_resistance_proximity_v72.resistance_dist_pct >= 0 ? '+' : '' }}{{ diagnosis.chanlun.support_resistance_proximity_v72.resistance_dist_pct }}%)</span></div>
                   <div class="kv-row"><span class="kv-key">距离 bonus</span><span class="kv-val">{{ diagnosis.chanlun.support_resistance_proximity_v72.proximity_bonus.toFixed(3) }}</span></div>
                   <div class="kv-note">{{ diagnosis.chanlun.support_resistance_proximity_v72.msg }}</div>
                 </div>
              </div>
              <!-- V72: 量价结构质量评分 -->
              <div v-if="diagnosis.chanlun.volume_structure_quality_v72" class="metric-card v72-vsq">
                 <div class="card-title">📈 V72 量价结构质量（条件222）</div>
                 <div class="card-body">
                   <div class="kv-row"><span class="kv-key">上涨量能比</span><span class="kv-val" :style="{ color: diagnosis.chanlun.volume_structure_quality_v72.up_vol_ratio > 1 ? '#22c55e' : '#ef4444' }">{{ diagnosis.chanlun.volume_structure_quality_v72.up_vol_ratio.toFixed(3) }}</span></div>
                   <div class="kv-row"><span class="kv-key">下跌量能比</span><span class="kv-val" :style="{ color: diagnosis.chanlun.volume_structure_quality_v72.down_vol_ratio < 1 ? '#22c55e' : '#ef4444' }">{{ diagnosis.chanlun.volume_structure_quality_v72.down_vol_ratio.toFixed(3) }}</span></div>
                   <div class="kv-row"><span class="kv-key">健康分</span><span class="kv-val" :style="{ color: diagnosis.chanlun.volume_structure_quality_v72.volume_health > 0 ? '#22c55e' : '#ef4444' }">{{ diagnosis.chanlun.volume_structure_quality_v72.volume_health >= 0 ? '+' : '' }}{{ diagnosis.chanlun.volume_structure_quality_v72.volume_health.toFixed(3) }}</span></div>
                   <div class="kv-row"><span class="kv-key">稳定分</span><span class="kv-val">{{ diagnosis.chanlun.volume_structure_quality_v72.stability_score.toFixed(3) }}</span></div>
                   <div class="kv-note">{{ diagnosis.chanlun.volume_structure_quality_v72.msg }}</div>
                 </div>
              </div>
              <!-- V72: 信号衰减速度评估 -->
              <div v-if="diagnosis.chanlun.signal_decay_velocity_v72" class="metric-card v72-sdv">
                 <div class="card-title">⏱️ V72 信号衰减速度（条件223）</div>
                 <div class="card-body">
                   <div class="kv-row"><span class="kv-key">趋势</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.signal_decay_velocity_v72.trend_direction === 'strengthening', 'tag-red': diagnosis.chanlun.signal_decay_velocity_v72.trend_direction === 'weakening', 'tag-blue': diagnosis.chanlun.signal_decay_velocity_v72.trend_direction === 'stable' }">{{ {strengthening:'🟢 强化',weakening:'🔴 衰退',stable:'🔵 稳定'}[diagnosis.chanlun.signal_decay_velocity_v72.trend_direction] ?? '—' }}</span></div>
                   <div class="kv-row"><span class="kv-key">速度</span><span class="kv-val" :style="{ color: diagnosis.chanlun.signal_decay_velocity_v72.velocity > 0 ? '#22c55e' : '#ef4444' }">{{ diagnosis.chanlun.signal_decay_velocity_v72.velocity >= 0 ? '+' : '' }}{{ diagnosis.chanlun.signal_decay_velocity_v72.velocity.toFixed(4) }}</span></div>
                   <div class="kv-row"><span class="kv-key">波动</span><span class="kv-val">{{ diagnosis.chanlun.signal_decay_velocity_v72.volatility.toFixed(4) }}</span></div>
                   <div class="kv-row"><span class="kv-key">样本</span><span class="kv-val">{{ diagnosis.chanlun.signal_decay_velocity_v72.recent_confidences.join(', ') }}</span></div>
                   <div class="kv-note">{{ diagnosis.chanlun.signal_decay_velocity_v72.msg }}</div>
                 </div>
              </div>
               <!-- V73: 买卖点位置风险评估 -->
               <div v-if="diagnosis.chanlun.mmd_position_risk_v73" class="metric-card v73-pr">
                  <div class="card-title">🎯 V73 买卖点位置风险（条件224）</div>
                  <div class="card-body">
                    <div class="kv-row"><span class="kv-key">风险等级</span><span class="tag" :class="{ 'tag-red': diagnosis.chanlun.mmd_position_risk_v73.risk_level === 'high', 'tag-green': diagnosis.chanlun.mmd_position_risk_v73.risk_level === 'low', 'tag-orange': diagnosis.chanlun.mmd_position_risk_v73.risk_level === 'medium' }">{{ {high:'🔴 高风险',low:'🟢 低风险',medium:'🟠 中风险'}[diagnosis.chanlun.mmd_position_risk_v73.risk_level] ?? '—' }}</span></div>
                    <div class="kv-row"><span class="kv-key">价格位置</span><span class="kv-val">{{ (diagnosis.chanlun.mmd_position_risk_v73.position_pct * 100).toFixed(1) }}%</span></div>
                    <div class="kv-row"><span class="kv-key">风险分</span><span class="kv-val">{{ diagnosis.chanlun.mmd_position_risk_v73.risk_score.toFixed(3) }}</span></div>
                    <div class="kv-note">{{ diagnosis.chanlun.mmd_position_risk_v73.msg }}</div>
                  </div>
               </div>
               <!-- V73: 中枢突破有效性验证 -->
               <div v-if="diagnosis.chanlun.zhongshu_breakout_validity_v73" class="metric-card v73-zb">
                  <div class="card-title">🔍 V73 中枢突破验证（条件225）</div>
                  <div class="card-body">
                    <div class="kv-row"><span class="kv-key">有效性</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.zhongshu_breakout_validity_v73.breakout_valid, 'tag-red': !diagnosis.chanlun.zhongshu_breakout_validity_v73.breakout_valid }">{{ diagnosis.chanlun.zhongshu_breakout_validity_v73.breakout_valid ? '✅ 有效' : '⚠️ 可疑' }}</span></div>
                    <div class="kv-row"><span class="kv-key">维持率</span><span class="kv-val" :style="{ color: diagnosis.chanlun.zhongshu_breakout_validity_v73.sustain_ratio >= 0.7 ? '#22c55e' : '#ef4444' }">{{ (diagnosis.chanlun.zhongshu_breakout_validity_v73.sustain_ratio * 100).toFixed(0) }}%</span></div>
                    <div class="kv-row"><span class="kv-key">量能比</span><span class="kv-val">{{ diagnosis.chanlun.zhongshu_breakout_validity_v73.volume_ratio.toFixed(2) }}</span></div>
                    <div class="kv-note">{{ diagnosis.chanlun.zhongshu_breakout_validity_v73.msg }}</div>
                  </div>
               </div>
               <!-- V73: 多指标确认一致性 -->
               <div v-if="diagnosis.chanlun.multi_indicator_consistency_v73" class="metric-card v73-mic">
                  <div class="card-title">🔗 V73 多指标一致性（条件226）</div>
                  <div class="card-body">
                    <div class="kv-row"><span class="kv-key">一致率</span><span class="kv-val" :style="{ color: diagnosis.chanlun.multi_indicator_consistency_v73.agreement_ratio >= 0.6 ? '#22c55e' : diagnosis.chanlun.multi_indicator_consistency_v73.agreement_ratio <= 0.4 ? '#ef4444' : '#f59e0b' }">{{ (diagnosis.chanlun.multi_indicator_consistency_v73.agreement_ratio * 100).toFixed(0) }}%</span></div>
                    <div class="kv-row"><span class="kv-key">一致分</span><span class="kv-val">{{ diagnosis.chanlun.multi_indicator_consistency_v73.consistency_score.toFixed(3) }}</span></div>
                    <div class="kv-note">{{ diagnosis.chanlun.multi_indicator_consistency_v73.msg }}</div>
                  </div>
               </div>
               <!-- V73: 波动率环境适配 -->
               <div v-if="diagnosis.chanlun.volatility_regime_adaptation_v73" class="metric-card v73-vra">
                  <div class="card-title">🌊 V73 波动率环境（条件227）</div>
                  <div class="card-body">
                    <div class="kv-row"><span class="kv-key">波动环境</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.volatility_regime_adaptation_v73.vol_regime === 'low', 'tag-blue': diagnosis.chanlun.volatility_regime_adaptation_v73.vol_regime === 'normal', 'tag-orange': diagnosis.chanlun.volatility_regime_adaptation_v73.vol_regime === 'high', 'tag-red': diagnosis.chanlun.volatility_regime_adaptation_v73.vol_regime === 'extreme' }">{{ {low:'🟢 低波动',normal:'🔵 正常',high:'🟠 高波动',extreme:'🔴 极端'}[diagnosis.chanlun.volatility_regime_adaptation_v73.vol_regime] ?? '—' }}</span></div>
                    <div class="kv-row"><span class="kv-key">ATR占比</span><span class="kv-val">{{ diagnosis.chanlun.volatility_regime_adaptation_v73.atr_pct.toFixed(2) }}%</span></div>
                    <div class="kv-row"><span class="kv-key">历史分位</span><span class="kv-val">{{ (diagnosis.chanlun.volatility_regime_adaptation_v73.atr_rank * 100).toFixed(0) }}%</span></div>
                    <div class="kv-note">{{ diagnosis.chanlun.volatility_regime_adaptation_v73.msg }}</div>
                  </div>
               </div>
               <!-- V74: 量价背离二次确认 -->
               <div v-if="diagnosis.chanlun.volume_price_divergence_secondary_v74" class="metric-card v74-vpd">
                  <div class="card-title">📊 V74 量价背离（条件228）</div>
                  <div class="card-body">
                    <div class="kv-row"><span class="kv-key">背离类型</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.volume_price_divergence_secondary_v74.divergence_type === 'bullish_divergence' || diagnosis.chanlun.volume_price_divergence_secondary_v74.divergence_type === 'healthy_rally', 'tag-red': diagnosis.chanlun.volume_price_divergence_secondary_v74.divergence_type === 'bearish_warning' || diagnosis.chanlun.volume_price_divergence_secondary_v74.divergence_type === 'heavy_selling', 'tag-blue': diagnosis.chanlun.volume_price_divergence_secondary_v74.divergence_type === 'none' }">{{ {bullish_divergence:'🟢 bullish背离',healthy_rally:'🟢 健康上涨',bearish_warning:'🔴 警示',heavy_selling:'🔴 放量下跌',none:'⚪ 无背离'}[diagnosis.chanlun.volume_price_divergence_secondary_v74.divergence_type] ?? '—' }}</span></div>
                    <div class="kv-row"><span class="kv-key">背离强度</span><span class="kv-val">{{ diagnosis.chanlun.volume_price_divergence_secondary_v74.divergence_strength.toFixed(2) }}</span></div>
                    <div class="kv-row"><span class="kv-key">二次确认</span><span class="tag" :class="diagnosis.chanlun.volume_price_divergence_secondary_v74.confirm_signal ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.volume_price_divergence_secondary_v74.confirm_signal ? '✅ 已确认' : '❌ 未确认' }}</span></div>
                    <div class="kv-note">{{ diagnosis.chanlun.volume_price_divergence_secondary_v74.msg }}</div>
                  </div>
               </div>
               <!-- V74: 趋势动能持续 -->
               <div v-if="diagnosis.chanlun.trend_momentum_continuity_v74" class="metric-card v74-tmc">
                  <div class="card-title">🚀 V74 动能持续（条件229）</div>
                  <div class="card-body">
                    <div class="kv-row"><span class="kv-key">短/中/长期动量</span><span class="kv-val">{{ diagnosis.chanlun.trend_momentum_continuity_v74.short_term >= 0 ? '+' : '' }}{{ diagnosis.chanlun.trend_momentum_continuity_v74.short_term.toFixed(2) }} / {{ diagnosis.chanlun.trend_momentum_continuity_v74.mid_term >= 0 ? '+' : '' }}{{ diagnosis.chanlun.trend_momentum_continuity_v74.mid_term.toFixed(2) }} / {{ diagnosis.chanlun.trend_momentum_continuity_v74.long_term >= 0 ? '+' : '' }}{{ diagnosis.chanlun.trend_momentum_continuity_v74.long_term.toFixed(2) }}</span></div>
                    <div class="kv-row"><span class="kv-key">动能评分</span><span class="kv-val">{{ diagnosis.chanlun.trend_momentum_continuity_v74.momentum_score.toFixed(3) }}</span></div>
                    <div class="kv-row"><span class="kv-key">持续状态</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.trend_momentum_continuity_v74.continuity === 'strong', 'tag-blue': diagnosis.chanlun.trend_momentum_continuity_v74.continuity === 'moderate', 'tag-orange': diagnosis.chanlun.trend_momentum_continuity_v74.continuity === 'weakening', 'tag-red': diagnosis.chanlun.trend_momentum_continuity_v74.continuity === 'neutral' }">{{ {strong:'🟢 强势',moderate:'🔵 温和',weakening:'🟠 衰减',neutral:'🔴 中性'}[diagnosis.chanlun.trend_momentum_continuity_v74.continuity] ?? '—' }}</span></div>
                    <div class="kv-note">{{ diagnosis.chanlun.trend_momentum_continuity_v74.msg }}</div>
                  </div>
               </div>
               <!-- V74: 中枢重叠度 -->
               <div v-if="diagnosis.chanlun.zhongshu_overlap_density_v74" class="metric-card v74-zod">
                  <div class="card-title">🔄 V74 中枢重叠（条件230）</div>
                  <div class="card-body">
                    <div class="kv-row"><span class="kv-key">重叠度</span><span class="kv-val">{{ (diagnosis.chanlun.zhongshu_overlap_density_v74.overlap_density * 100).toFixed(0) }}%</span></div>
                    <div class="kv-row"><span class="kv-key">附近中枢数</span><span class="kv-val">{{ diagnosis.chanlun.zhongshu_overlap_density_v74.nearby_zs_count }} 个</span></div>
                    <div class="kv-row"><span class="kv-key">信号强度</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.zhongshu_overlap_density_v74.signal_strength === 'strong_support' || diagnosis.chanlun.zhongshu_overlap_density_v74.signal_strength === 'strong_resistance', 'tag-blue': diagnosis.chanlun.zhongshu_overlap_density_v74.signal_strength === 'moderate', 'tag-orange': diagnosis.chanlun.zhongshu_overlap_density_v74.signal_strength === 'near_zone', 'tag-gray': diagnosis.chanlun.zhongshu_overlap_density_v74.signal_strength === 'weak' }">{{ {strong_support:'🟢 强支撑',strong_resistance:'🔴 强阻力',moderate:'🔵 中等',near_zone:'🟠 近区',weak:'⚪ 弱'}[diagnosis.chanlun.zhongshu_overlap_density_v74.signal_strength] ?? '—' }}</span></div>
                    <div class="kv-note">{{ diagnosis.chanlun.zhongshu_overlap_density_v74.msg }}</div>
                  </div>
               </div>
               <!-- V74: 信号共振深度 -->
               <div v-if="diagnosis.chanlun.signal_resonance_depth_v74" class="metric-card v74-srd">
                  <div class="card-title">🔗 V74 共振深度（条件231）</div>
                  <div class="card-body">
                    <div class="kv-row"><span class="kv-key">共振维度</span><span class="kv-val">{{ diagnosis.chanlun.signal_resonance_depth_v74.confirming_dimensions }} / {{ diagnosis.chanlun.signal_resonance_depth_v74.total_dimensions }}</span></div>
                    <div class="kv-row"><span class="kv-key">深度得分</span><span class="kv-val">{{ diagnosis.chanlun.signal_resonance_depth_v74.depth_score.toFixed(3) }}</span></div>
                    <div class="kv-row"><span class="kv-key">共振等级</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.signal_resonance_depth_v74.resonance_level === 'deep', 'tag-blue': diagnosis.chanlun.signal_resonance_depth_v74.resonance_level === 'moderate', 'tag-orange': diagnosis.chanlun.signal_resonance_depth_v74.resonance_level === 'weak', 'tag-red': diagnosis.chanlun.signal_resonance_depth_v74.resonance_level === 'shallow' }">{{ {deep:'🟢 深共振',moderate:'🔵 中共振',weak:'🟠 弱共振',shallow:'🔴 浅共振'}[diagnosis.chanlun.signal_resonance_depth_v74.resonance_level] ?? '—' }}</span></div>
                    <div class="kv-note">{{ diagnosis.chanlun.signal_resonance_depth_v74.msg }}</div>
                  </div>
               </div>
               <!-- V75: 回调深度验证 -->
               <div v-if="diagnosis.chanlun.pullback_depth_validation_v75" class="metric-card v75-pdv">
                  <div class="card-title">📉 V75 回调深度（条件232）</div>
                  <div class="card-body">
                    <div class="kv-row"><span class="kv-key">回调深度</span><span class="kv-val">{{ (diagnosis.chanlun.pullback_depth_validation_v75.pullback_depth * 100).toFixed(1) }}%</span></div>
                    <div class="kv-row"><span class="kv-key">斐波那契位</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.pullback_depth_validation_v75.fibonacci_level === 'shallow_15' || diagnosis.chanlun.pullback_depth_validation_v75.fibonacci_level === 'fib_236', 'tag-blue': diagnosis.chanlun.pullback_depth_validation_v75.fibonacci_level === 'fib_382', 'tag-orange': diagnosis.chanlun.pullback_depth_validation_v75.fibonacci_level === 'fib_50', 'tag-red': diagnosis.chanlun.pullback_depth_validation_v75.fibonacci_level === 'deep_over_50' }">{{ {shallow_15:'🟢 浅回(≤15%)',fib_236:'🟢 斐波23.6%',fib_382:'🔵 斐波38.2%',fib_50:'🟠 过度回调',deep_over_50:'🔴 深度回调>50%'}[diagnosis.chanlun.pullback_depth_validation_v75.fibonacci_level] ?? '—' }}</span></div>
                    <div class="kv-row"><span class="kv-key">回调确认</span><span class="tag" :class="diagnosis.chanlun.pullback_depth_validation_v75.confirm_signal ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.pullback_depth_validation_v75.confirm_signal ? '✅ 回调健康' : '⚠️ 回调过深' }}</span></div>
                    <div class="kv-note">{{ diagnosis.chanlun.pullback_depth_validation_v75.msg }}</div>
                  </div>
               </div>
               <!-- V75: 中枢回踩确认 -->
               <div v-if="diagnosis.chanlun.zhongshu_retracement_confirm_v75" class="metric-card v75-zrc">
                  <div class="card-title">🔄 V75 中枢回踩（条件233）</div>
                  <div class="card-body">
                    <div class="kv-row"><span class="kv-key">回踩类型</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.zhongshu_retracement_confirm_v75.retracement_type === 'zs_support_bounce' || diagnosis.chanlun.zhongshu_retracement_confirm_v75.retracement_type === 'above_zs_confirmed', 'tag-blue': diagnosis.chanlun.zhongshu_retracement_confirm_v75.retracement_type === 'inside_zs', 'tag-orange': diagnosis.chanlun.zhongshu_retracement_confirm_v75.retracement_type === 'below_zs', 'tag-red': diagnosis.chanlun.zhongshu_retracement_confirm_v75.retracement_type === 'none' }">{{ {zs_support_bounce:'🟢 支撑反弹',above_zs_confirmed:'🟢 中枢上方确认',inside_zs:'🔵 中枢内部',below_zs:'🟠 跌破中枢',none:'⚪ 无回踩'}[diagnosis.chanlun.zhongshu_retracement_confirm_v75.retracement_type] ?? '—' }}</span></div>
                    <div class="kv-row"><span class="kv-key">反弹强度</span><span class="kv-val">{{ diagnosis.chanlun.zhongshu_retracement_confirm_v75.bounce_strength.toFixed(3) }}</span></div>
                    <div class="kv-row"><span class="kv-key">距最近中枢</span><span class="kv-val">{{ diagnosis.chanlun.zhongshu_retracement_confirm_v75.nearest_zs_dist.toFixed(2) }}x 区间</span></div>
                    <div class="kv-row"><span class="kv-key">回踩确认</span><span class="tag" :class="diagnosis.chanlun.zhongshu_retracement_confirm_v75.confirm_signal ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.zhongshu_retracement_confirm_v75.confirm_signal ? '✅ 回踩确认' : '❌ 未确认' }}</span></div>
                    <div class="kv-note">{{ diagnosis.chanlun.zhongshu_retracement_confirm_v75.msg }}</div>
                  </div>
               </div>
               <!-- V75: 量峰持续评分 -->
               <div v-if="diagnosis.chanlun.volume_peak_duration_v75" class="metric-card v75-vpd2">
                  <div class="card-title">📊 V75 量峰持续（条件234）</div>
                  <div class="card-body">
                    <div class="kv-row"><span class="kv-key">放量天数</span><span class="kv-val">{{ diagnosis.chanlun.volume_peak_duration_v75.peak_days }} 天</span></div>
                    <div class="kv-row"><span class="kv-key">连续峰值</span><span class="kv-val">{{ diagnosis.chanlun.volume_peak_duration_v75.peak_duration }} 天</span></div>
                    <div class="kv-row"><span class="kv-key">均量比</span><span class="kv-val">{{ diagnosis.chanlun.volume_peak_duration_v75.avg_vol_ratio.toFixed(2) }}x</span></div>
                    <div class="kv-row"><span class="kv-key">量能确认</span><span class="tag" :class="diagnosis.chanlun.volume_peak_duration_v75.confirm_signal ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.volume_peak_duration_v75.confirm_signal ? '✅ 量能配合' : '⚠️ 量能不足' }}</span></div>
                    <div class="kv-note">{{ diagnosis.chanlun.volume_peak_duration_v75.msg }}</div>
                  </div>
               </div>
               <!-- V75: 多信号时间一致性 -->
               <div v-if="diagnosis.chanlun.multi_signal_time_consistency_v75" class="metric-card v75-mstc">
                  <div class="card-title">⏰ V75 时间一致（条件235）</div>
                  <div class="card-body">
                    <div class="kv-row"><span class="kv-key">信号数量</span><span class="kv-val">{{ diagnosis.chanlun.multi_signal_time_consistency_v75.signal_dates?.length ?? 0 }} 个</span></div>
                    <div class="kv-row"><span class="kv-key">一致率</span><span class="kv-val">{{ (diagnosis.chanlun.multi_signal_time_consistency_v75.consistency_score * 100).toFixed(0) }}%</span></div>
                    <div class="kv-row"><span class="kv-key">对齐比</span><span class="kv-val">{{ diagnosis.chanlun.multi_signal_time_consistency_v75.alignment_ratio.toFixed(3) }}</span></div>
                    <div class="kv-row"><span class="kv-key">时间确认</span><span class="tag" :class="diagnosis.chanlun.multi_signal_time_consistency_v75.confirm_signal ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.multi_signal_time_consistency_v75.confirm_signal ? '✅ 信号同步' : '⚠️ 信号分散' }}</span></div>
                    <div class="kv-note">{{ diagnosis.chanlun.multi_signal_time_consistency_v75.msg }}</div>
                  </div>
               </div>
                <!-- V76: 价格结构完整性验证 -->
                <div v-if="diagnosis.chanlun.price_structure_integrity_v76" class="metric-card v76-psI">
                   <div class="card-title">🏗️ V76 结构完整（条件236）</div>
                   <div class="card-body">
                     <div class="kv-row"><span class="kv-key">结构评分</span><span class="kv-val">{{ (diagnosis.chanlun.price_structure_integrity_v76.structure_score * 100).toFixed(0) }}%</span></div>
                     <div class="kv-row"><span class="kv-key">趋势结构</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.price_structure_integrity_v76.trend_structure === 'bottom_accumulation' || diagnosis.chanlun.price_structure_integrity_v76.trend_structure === 'mid_recovery', 'tag-blue': diagnosis.chanlun.price_structure_integrity_v76.trend_structure === 'breakout_attempt', 'tag-orange': diagnosis.chanlun.price_structure_integrity_v76.trend_structure === 'overextended' || diagnosis.chanlun.price_structure_integrity_v76.trend_structure === 'top_distribution' }">{{ {bottom_accumulation:'🟢 底部积累',mid_recovery:'🟢 中期反弹',breakout_attempt:'🔵 突破尝试',overextended:'🟠 过度延伸',top_distribution:'🟠 顶部派发',mid_pullback:'🔵 中期回踩',breakdown_attempt:'🟠 破位尝试',oversold:'🔴 超卖'}[diagnosis.chanlun.price_structure_integrity_v76.trend_structure] ?? '—' }}</span></div>
                     <div class="kv-row"><span class="kv-key">关键价位</span><span class="tag" :class="diagnosis.chanlun.price_structure_integrity_v76.key_levels_valid ? 'tag-green' : 'tag-orange'">{{ diagnosis.chanlun.price_structure_integrity_v76.key_levels_valid ? '✅ 有效' : '⚠️ 偏离' }}</span></div>
                     <div class="kv-row"><span class="kv-key">结构确认</span><span class="tag" :class="diagnosis.chanlun.price_structure_integrity_v76.confirm_signal ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.price_structure_integrity_v76.confirm_signal ? '✅ 结构完整' : '⚠️ 结构不足' }}</span></div>
                     <div class="kv-note">{{ diagnosis.chanlun.price_structure_integrity_v76.msg }}</div>
                   </div>
                </div>
                <!-- V76: 趋势方向对齐验证 -->
                <div v-if="diagnosis.chanlun.trend_alignment_validation_v76" class="metric-card v76-tav">
                   <div class="card-title">🧭 V76 趋势对齐（条件237）</div>
                   <div class="card-body">
                     <div class="kv-row"><span class="kv-key">趋势方向</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.trend_alignment_validation_v76.trend_direction === 'bullish' || diagnosis.chanlun.trend_alignment_validation_v76.trend_direction === 'weak_bullish', 'tag-red': diagnosis.chanlun.trend_alignment_validation_v76.trend_direction === 'bearish' || diagnosis.chanlun.trend_alignment_validation_v76.trend_direction === 'weak_bearish', 'tag-blue': diagnosis.chanlun.trend_alignment_validation_v76.trend_direction === 'neutral' }">{{ {bullish:'🟢 强多头',weak_bullish:'🟢 弱多头',bearish:'🔴 强空头',weak_bearish:'🔴 弱空头',neutral:'🔵 中性'}[diagnosis.chanlun.trend_alignment_validation_v76.trend_direction] ?? '—' }}</span></div>
                     <div class="kv-row"><span class="kv-key">对齐状态</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.trend_alignment_validation_v76.alignment_status === 'strong_aligned', 'tag-blue': diagnosis.chanlun.trend_alignment_validation_v76.alignment_status === 'moderately_aligned', 'tag-red': diagnosis.chanlun.trend_alignment_validation_v76.alignment_status === 'diverged' }">{{ {strong_aligned:'🟢 强对齐',moderately_aligned:'🔵 中对齐',diverged:'🔴 背离'}[diagnosis.chanlun.trend_alignment_validation_v76.alignment_status] ?? '—' }}</span></div>
                     <div class="kv-row" v-for="ma in diagnosis.chanlun.trend_alignment_validation_v76.ma_alignment" :key="ma.period">
                       <span class="kv-key">MA{{ ma.period }}</span>
                       <span class="tag" :class="ma.trend === 'up' ? 'tag-green' : ma.trend === 'down' ? 'tag-red' : 'tag-gray'">{{ ma.trend === 'up' ? '🟢 向上' : ma.trend === 'down' ? '🔴 向下' : '⚪ 走平' }}</span>
                     </div>
                     <div class="kv-row"><span class="kv-key">趋势确认</span><span class="tag" :class="diagnosis.chanlun.trend_alignment_validation_v76.confirm_signal ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.trend_alignment_validation_v76.confirm_signal ? '✅ 趋势一致' : '⚠️ 趋势分歧' }}</span></div>
                     <div class="kv-note">{{ diagnosis.chanlun.trend_alignment_validation_v76.msg }}</div>
                   </div>
                </div>
                <!-- V76: 波动率自适应置信度 -->
                <div v-if="diagnosis.chanlun.volatility_adaptive_confidence_v76" class="metric-card v76-vac">
                   <div class="card-title">📊 V76 波动率自适应（条件238）</div>
                   <div class="card-body">
                     <div class="kv-row"><span class="kv-key">波动率等级</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.volatility_adaptive_confidence_v76.vol_level === 'low', 'tag-blue': diagnosis.chanlun.volatility_adaptive_confidence_v76.vol_level === 'normal', 'tag-orange': diagnosis.chanlun.volatility_adaptive_confidence_v76.vol_level === 'high', 'tag-red': diagnosis.chanlun.volatility_adaptive_confidence_v76.vol_level === 'extreme' }">{{ {low:'🟢 低波动',normal:'🔵 正常波动',high:'🟠 高波动',extreme:'🔴 极端波动'}[diagnosis.chanlun.volatility_adaptive_confidence_v76.vol_level] ?? '—' }}</span></div>
                     <div class="kv-row"><span class="kv-key">ATR比率</span><span class="kv-val">{{ diagnosis.chanlun.volatility_adaptive_confidence_v76.atr_ratio.toFixed(3) }}</span></div>
                     <div class="kv-row"><span class="kv-key">自适应置信度</span><span class="kv-val">{{ (diagnosis.chanlun.volatility_adaptive_confidence_v76.adaptive_confidence * 100).toFixed(0) }}%</span></div>
                     <div class="kv-row"><span class="kv-key">波动确认</span><span class="tag" :class="diagnosis.chanlun.volatility_adaptive_confidence_v76.confirm_signal ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.volatility_adaptive_confidence_v76.confirm_signal ? '✅ 置信度达标' : '⚠️ 需更强确认' }}</span></div>
                     <div class="kv-note">{{ diagnosis.chanlun.volatility_adaptive_confidence_v76.msg }}</div>
                   </div>
                </div>
                <!-- V76: 买卖点最终有效性评分 -->
                <div v-if="diagnosis.chanlun.signal_final_validity_v76" class="metric-card v76-sfv">
                   <div class="card-title">🎯 V76 最终有效性（条件239）</div>
                   <div class="card-body">
                     <div class="kv-row"><span class="kv-key">有效性等级</span><span class="tag" :class="{ 'tag-green': diagnosis.chanlun.signal_final_validity_v76.final_validity === 'strong', 'tag-blue': diagnosis.chanlun.signal_final_validity_v76.final_validity === 'moderate', 'tag-orange': diagnosis.chanlun.signal_final_validity_v76.final_validity === 'weak', 'tag-red': diagnosis.chanlun.signal_final_validity_v76.final_validity === 'invalid' }">{{ {strong:'🟢 强信号',moderate:'🔵 中性信号',weak:'🟠 弱信号',invalid:'🔴 不建议操作'}[diagnosis.chanlun.signal_final_validity_v76.final_validity] ?? '—' }}</span></div>
                     <div class="kv-row"><span class="kv-key">有效性得分</span><span class="kv-val">{{ (diagnosis.chanlun.signal_final_validity_v76.validity_score * 100).toFixed(0) }}%</span></div>
                     <div class="kv-row"><span class="kv-key">操作建议</span><span class="tag" :class="diagnosis.chanlun.signal_final_validity_v76.confirm_signal ? 'tag-green' : 'tag-gray'">{{ diagnosis.chanlun.signal_final_validity_v76.recommendation }}</span></div>
                     <div class="kv-note">{{ diagnosis.chanlun.signal_final_validity_v76.msg }}</div>
                   </div>
                </div>
                <!-- V77: 量能分布深度分析（条件240） -->
                <div v-if="diagnosis.chanlun.volume_distribution_depth_v77" class="metric-card v77-vdd">
                   <div class="card-title">📊 V77 量能分布深度（条件240）</div>
                   <div class="card-body">
                     <div class="kv-row">
                       <span class="kv-key">能量区域</span>
                       <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.volume_distribution_depth_v77.energy_zone === 'accumulation', 'tag-red': diagnosis.chanlun.volume_distribution_depth_v77.energy_zone === 'distribution', 'tag-blue': diagnosis.chanlun.volume_distribution_depth_v77.energy_zone === 'low_zone', 'tag-orange': diagnosis.chanlun.volume_distribution_depth_v77.energy_zone === 'high_zone', 'tag-gray': diagnosis.chanlun.volume_distribution_depth_v77.energy_zone === 'neutral' }">
                         {{ {accumulation:'🟢 筹码收集',distribution:'🔴 筹码派发',low_zone:'🔵 低位区',high_zone:'🟠 高位区',neutral:'⚪ 中性'}[diagnosis.chanlun.volume_distribution_depth_v77.energy_zone] ?? '—' }}
                       </span>
                       <span class="kv-key">量分位</span>
                       <span class="kv-val">{{ (diagnosis.chanlun.volume_distribution_depth_v77.volume_rank * 100).toFixed(0) }}%</span>
                     </div>
                     <div class="kv-row">
                       <span class="kv-key">距支撑</span>
                       <span class="kv-val">{{ (diagnosis.chanlun.volume_distribution_depth_v77.support_distance * 100).toFixed(1) }}%</span>
                       <span class="kv-key">距阻力</span>
                       <span class="kv-val">{{ (diagnosis.chanlun.volume_distribution_depth_v77.resistance_distance * 100).toFixed(1) }}%</span>
                     </div>
                     <div class="kv-row">
                       <span class="kv-key">置信度调整</span>
                       <span class="kv-val" :style="{ color: diagnosis.chanlun.volume_distribution_depth_v77.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                         {{ diagnosis.chanlun.volume_distribution_depth_v77.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.volume_distribution_depth_v77.confidence_adjust * 100).toFixed(0) }}%
                       </span>
                     </div>
                     <div class="kv-note">{{ diagnosis.chanlun.volume_distribution_depth_v77.msg }}</div>
                   </div>
                </div>
                <!-- V77: 中枢结构权重评估（条件241） -->
                <div v-if="diagnosis.chanlun.zhongshu_structure_weight_v77" class="metric-card v77-zsw">
                   <div class="card-title">🏗️ V77 中枢结构权重（条件241）</div>
                   <div class="card-body">
                     <div class="kv-row">
                       <span class="kv-key">结构权重</span>
                       <span class="kv-val" :style="{ color: diagnosis.chanlun.zhongshu_structure_weight_v77.weight_score >= 0.7 ? '#22c55e' : diagnosis.chanlun.zhongshu_structure_weight_v77.weight_score >= 0.5 ? '#f59e0b' : '#ef4444' }">
                         {{ (diagnosis.chanlun.zhongshu_structure_weight_v77.weight_score * 100).toFixed(0) }}%
                       </span>
                       <span class="kv-key">最近中枢</span>
                       <span class="tag tag-blue">{{ diagnosis.chanlun.zhongshu_structure_weight_v77.zs_level }}</span>
                     </div>
                     <div class="kv-row">
                       <span class="kv-key">距中枢距离</span>
                       <span class="kv-val">{{ (diagnosis.chanlun.zhongshu_structure_weight_v77.nearest_zs_dist * 100).toFixed(1) }}%</span>
                     </div>
                     <div class="kv-row">
                       <span class="kv-key">置信度调整</span>
                       <span class="kv-val" :style="{ color: diagnosis.chanlun.zhongshu_structure_weight_v77.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                         {{ diagnosis.chanlun.zhongshu_structure_weight_v77.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.zhongshu_structure_weight_v77.confidence_adjust * 100).toFixed(0) }}%
                       </span>
                     </div>
                     <div class="kv-note">{{ diagnosis.chanlun.zhongshu_structure_weight_v77.msg }}</div>
                   </div>
                </div>
                <!-- V77: 信号新鲜度验证（条件242） -->
                <div v-if="diagnosis.chanlun.signal_freshness_validation_v77" class="metric-card v77-sfsh">
                   <div class="card-title">⏱️ V77 信号新鲜度（条件242）</div>
                   <div class="card-body">
                     <div class="kv-row">
                       <span class="kv-key">新鲜度评分</span>
                       <span class="kv-val" :style="{ color: diagnosis.chanlun.signal_freshness_validation_v77.freshness_score >= 0.7 ? '#22c55e' : diagnosis.chanlun.signal_freshness_validation_v77.freshness_score >= 0.4 ? '#f59e0b' : '#ef4444' }">
                         {{ (diagnosis.chanlun.signal_freshness_validation_v77.freshness_score * 100).toFixed(0) }}%
                       </span>
                       <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.signal_freshness_validation_v77.age_label === 'very_fresh', 'tag-blue': diagnosis.chanlun.signal_freshness_validation_v77.age_label === 'fresh', 'tag-yellow': diagnosis.chanlun.signal_freshness_validation_v77.age_label === 'aging', 'tag-red': diagnosis.chanlun.signal_freshness_validation_v77.age_label === 'stale' }">
                         {{ {very_fresh:'🟢 极新鲜',fresh:'🔵 新鲜',aging:'🟡 衰减中',stale:'🔴 陈旧'}[diagnosis.chanlun.signal_freshness_validation_v77.age_label] ?? '—' }}
                       </span>
                     </div>
                     <div class="kv-row">
                       <span class="kv-key">信号后K线数</span>
                       <span class="kv-val">{{ diagnosis.chanlun.signal_freshness_validation_v77.bars_since_signal }} 根</span>
                     </div>
                     <div class="kv-row">
                       <span class="kv-key">置信度调整</span>
                       <span class="kv-val" :style="{ color: diagnosis.chanlun.signal_freshness_validation_v77.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                         {{ diagnosis.chanlun.signal_freshness_validation_v77.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.signal_freshness_validation_v77.confidence_adjust * 100).toFixed(0) }}%
                       </span>
                     </div>
                     <div class="kv-note">{{ diagnosis.chanlun.signal_freshness_validation_v77.msg }}</div>
                   </div>
                </div>
                <!-- V77: 价格动能加速度（条件243） -->
                <div v-if="diagnosis.chanlun.price_momentum_acceleration_v77" class="metric-card v77-pma">
                   <div class="card-title">🚀 V77 动能加速度（条件243）</div>
                   <div class="card-body">
                     <div class="kv-row">
                       <span class="kv-key">加速度</span>
                       <span class="kv-val" :style="{ color: (diagnosis.chanlun.price_momentum_acceleration_v77.acceleration > 0) ? '#22c55e' : '#ef4444' }">
                         {{ diagnosis.chanlun.price_momentum_acceleration_v77.acceleration > 0 ? '+' : '' }}{{ diagnosis.chanlun.price_momentum_acceleration_v77.acceleration.toFixed(4) }}
                       </span>
                       <span class="tag" :class="{ 'tag-green': ['accelerating_up','growing_up'].includes(diagnosis.chanlun.price_momentum_acceleration_v77.momentum_direction), 'tag-red': ['sharp_reversal','decelerating'].includes(diagnosis.chanlun.price_momentum_acceleration_v77.momentum_direction), 'tag-gray': diagnosis.chanlun.price_momentum_acceleration_v77.momentum_direction === 'flat' }">
                         {{ {accelerating_up:'📈 加速上涨',growing_up:'📈 稳步上涨',flat:'➡️ 横盘',decelerating:'📉 动能减弱',sharp_reversal:'🔴 急剧反转'}[diagnosis.chanlun.price_momentum_acceleration_v77.momentum_direction] ?? '—' }}
                       </span>
                     </div>
                     <div class="kv-row">
                       <span class="kv-key">加速度强度</span>
                       <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.price_momentum_acceleration_v77.acceleration_strength === 'strong', 'tag-yellow': diagnosis.chanlun.price_momentum_acceleration_v77.acceleration_strength === 'moderate', 'tag-gray': diagnosis.chanlun.price_momentum_acceleration_v77.acceleration_strength === 'weak' }">
                         {{ {strong:'🟢 强',moderate:'🟡 中',weak:'⚪ 弱'}[diagnosis.chanlun.price_momentum_acceleration_v77.acceleration_strength] ?? '—' }}
                       </span>
                       <span class="kv-key">置信度调整</span>
                       <span class="kv-val" :style="{ color: diagnosis.chanlun.price_momentum_acceleration_v77.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                         {{ diagnosis.chanlun.price_momentum_acceleration_v77.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.price_momentum_acceleration_v77.confidence_adjust * 100).toFixed(0) }}%
                       </span>
                     </div>
                     <div class="kv-note">{{ diagnosis.chanlun.price_momentum_acceleration_v77.msg }}</div>
                   </div>
                </div>
                 <!-- V78: 买卖点周期位置评分（条件244） -->
                 <div v-if="diagnosis.chanlun.mmd_cycle_position_v78" class="metric-card v78-mcp">
                    <div class="card-title">📍 V78 周期位置（条件244）</div>
                    <div class="card-body">
                      <div class="kv-row">
                        <span class="kv-key">周期位置</span>
                        <span class="tag" :class="{ 'tag-green': ['bottom','lower'].includes(diagnosis.chanlun.mmd_cycle_position_v78.cycle_position), 'tag-red': ['top','upper'].includes(diagnosis.chanlun.mmd_cycle_position_v78.cycle_position), 'tag-gray': diagnosis.chanlun.mmd_cycle_position_v78.cycle_position === 'mid' }">
                          {{ {bottom:'🟢 波段底部',lower:'🟢 中下部',mid:'⚪ 中部',upper:'🟠 中上部',top:'🔴 波段顶部'}[diagnosis.chanlun.mmd_cycle_position_v78.cycle_position] ?? '—' }}
                        </span>
                      </div>
                      <div class="kv-row">
                        <span class="kv-key">位置评分</span>
                        <span class="kv-val" :style="{ color: diagnosis.chanlun.mmd_cycle_position_v78.position_score >= 0.7 ? '#22c55e' : diagnosis.chanlun.mmd_cycle_position_v78.position_score >= 0.4 ? '#f59e0b' : '#ef4444' }">
                          {{ (diagnosis.chanlun.mmd_cycle_position_v78.position_score * 100).toFixed(0) }}%
                        </span>
                        <span class="kv-key">距低位</span><span class="kv-val">{{ (diagnosis.chanlun.mmd_cycle_position_v78.distance_to_low * 100).toFixed(0) }}%</span>
                        <span class="kv-key">距高位</span><span class="kv-val">{{ (diagnosis.chanlun.mmd_cycle_position_v78.distance_to_high * 100).toFixed(0) }}%</span>
                      </div>
                      <div class="kv-note">{{ diagnosis.chanlun.mmd_cycle_position_v78.msg }}</div>
                    </div>
                 </div>
                 <!-- V78: 多信号时间窗口一致性（条件245） -->
                 <div v-if="diagnosis.chanlun.multi_signal_consensus_v78" class="metric-card v78-msc">
                    <div class="card-title">🤝 V78 信号共识（条件245）</div>
                    <div class="card-body">
                      <div class="kv-row">
                        <span class="kv-key">共识度</span>
                        <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.multi_signal_consensus_v78.consensus_level === 'strong_consensus', 'tag-blue': diagnosis.chanlun.multi_signal_consensus_v78.consensus_level === 'moderate_consensus', 'tag-red': diagnosis.chanlun.multi_signal_consensus_v78.consensus_level === 'contradicted', 'tag-gray': diagnosis.chanlun.multi_signal_consensus_v78.consensus_level === 'isolated' }">
                          {{ {strong_consensus:'🟢 强共识',moderate_consensus:'🔵 中共识',contradicted:'🔴 分歧',isolated:'⚪ 孤立',mixed:'🟡 混合'}[diagnosis.chanlun.multi_signal_consensus_v78.consensus_level] ?? '—' }}
                        </span>
                      </div>
                      <div class="kv-row">
                        <span class="kv-key">评分</span>
                        <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_signal_consensus_v78.consensus_score >= 0.7 ? '#22c55e' : diagnosis.chanlun.multi_signal_consensus_v78.consensus_score >= 0.4 ? '#f59e0b' : '#ef4444' }">
                          {{ (diagnosis.chanlun.multi_signal_consensus_v78.consensus_score * 100).toFixed(0) }}%
                        </span>
                        <span class="kv-key">近买</span><span class="kv-val">{{ diagnosis.chanlun.multi_signal_consensus_v78.nearby_buy_count }}</span>
                        <span class="kv-key">近卖</span><span class="kv-val">{{ diagnosis.chanlun.multi_signal_consensus_v78.nearby_sell_count }}</span>
                      </div>
                      <div class="kv-note">{{ diagnosis.chanlun.multi_signal_consensus_v78.msg }}</div>
                    </div>
                 </div>
                 <!-- V78: 波动率压缩突破预测（条件246） -->
                 <div v-if="diagnosis.chanlun.volatility_compression_breakout_v78" class="metric-card v78-vcb">
                    <div class="card-title">📊 V78 波动率压缩（条件246）</div>
                    <div class="card-body">
                      <div class="kv-row">
                        <span class="kv-key">压缩评分</span>
                        <span class="kv-val" :style="{ color: diagnosis.chanlun.volatility_compression_breakout_v78.compression_score >= 0.7 ? '#22c55e' : '#f59e0b' }">
                          {{ (diagnosis.chanlun.volatility_compression_breakout_v78.compression_score * 100).toFixed(0) }}%
                        </span>
                        <span class="kv-key">突破方向</span>
                        <span class="tag" :class="{ 'tag-green': ['up','up_continuing'].includes(diagnosis.chanlun.volatility_compression_breakout_v78.breakout_direction), 'tag-red': ['down','down_continuing'].includes(diagnosis.chanlun.volatility_compression_breakout_v78.breakout_direction), 'tag-gray': diagnosis.chanlun.volatility_compression_breakout_v78.breakout_direction === 'neutral' || diagnosis.chanlun.volatility_compression_breakout_v78.breakout_direction === 'normal' }">
                          {{ {up:'📈 向上突破',up_continuing:'📈 延续上涨',down:'📉 向下突破',down_continuing:'📉 延续下跌',neutral:'➡️ 中性',normal:'➡️ 正常'}[diagnosis.chanlun.volatility_compression_breakout_v78.breakout_direction] ?? '—' }}
                        </span>
                      </div>
                      <div class="kv-row">
                        <span class="kv-key">带宽百分位</span><span class="kv-val">{{ (diagnosis.chanlun.volatility_compression_breakout_v78.boll_width_percentile * 100).toFixed(0) }}%</span>
                        <span class="kv-key">置信度调整</span>
                        <span class="kv-val" :style="{ color: diagnosis.chanlun.volatility_compression_breakout_v78.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">
                          {{ diagnosis.chanlun.volatility_compression_breakout_v78.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.volatility_compression_breakout_v78.confidence_adjust * 100).toFixed(0) }}%
                        </span>
                      </div>
                      <div class="kv-note">{{ diagnosis.chanlun.volatility_compression_breakout_v78.msg }}</div>
                    </div>
                 </div>
                 <!-- V78: 资金流向与价格背离检测（条件247） -->
                 <div v-if="diagnosis.chanlun.fund_flow_divergence_v78" class="metric-card v78-ffd">
                    <div class="card-title">💰 V78 资金背离（条件247）</div>
                    <div class="card-body">
                      <div class="kv-row">
                        <span class="kv-key">背离类型</span>
                        <span class="tag" :class="{ 'tag-red': diagnosis.chanlun.fund_flow_divergence_v78.divergence_type === 'bearish_divergence', 'tag-green': diagnosis.chanlun.fund_flow_divergence_v78.divergence_type === 'bullish_divergence', 'tag-blue': diagnosis.chanlun.fund_flow_divergence_v78.divergence_type === 'confirmed_up', 'tag-orange': diagnosis.chanlun.fund_flow_divergence_v78.divergence_type === 'confirmed_down', 'tag-gray': diagnosis.chanlun.fund_flow_divergence_v78.divergence_type === 'neutral' }">
                          {{ {bearish_divergence:'🔴 看跌背离',bullish_divergence:'🟢 看涨背离',confirmed_up:'🔵 量价齐升',confirmed_down:'🟠 量价齐跌',neutral:'⚪ 中性'}[diagnosis.chanlun.fund_flow_divergence_v78.divergence_type] ?? '—' }}
                        </span>
                      </div>
                      <div class="kv-row">
                        <span class="kv-key">资金评分</span>
                        <span class="kv-val" :style="{ color: diagnosis.chanlun.fund_flow_divergence_v78.money_flow_score >= 0.6 ? '#22c55e' : diagnosis.chanlun.fund_flow_divergence_v78.money_flow_score >= 0.4 ? '#f59e0b' : '#ef4444' }">
                          {{ (diagnosis.chanlun.fund_flow_divergence_v78.money_flow_score * 100).toFixed(0) }}%
                        </span>
                        <span class="kv-key">量价相关</span><span class="kv-val">{{ diagnosis.chanlun.fund_flow_divergence_v78.volume_price_correlation.toFixed(2) }}</span>
                      </div>
                      <div class="kv-note">{{ diagnosis.chanlun.fund_flow_divergence_v78.msg }}</div>
                    </div>
                 </div>
                 <!-- V79: 分型稳定性验证（条件248） -->
                 <div v-if="diagnosis.chanlun.fractal_stability_validation_v79" class="metric-card v79-fsv">
                    <div class="card-title">🔍 V79 分型稳定性（条件248）</div>
                    <div class="card-body">
                      <div class="kv-row">
                        <span class="kv-key">分型状态</span>
                        <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.fractal_stability_validation_v79.fractal_status === 'stable', 'tag-orange': diagnosis.chanlun.fractal_stability_validation_v79.fractal_status === 'weak', 'tag-red': diagnosis.chanlun.fractal_stability_validation_v79.fractal_status === 'broken', 'tag-gray': diagnosis.chanlun.fractal_stability_validation_v79.fractal_status === 'unknown' }">
                          {{ {stable:'🟢 稳定',weak:'🟠 弱稳定',broken:'🔴 已破坏',unknown:'⚪ 未知'}[diagnosis.chanlun.fractal_stability_validation_v79.fractal_status] ?? '—' }}
                        </span>
                      </div>
                      <div class="kv-row">
                        <span class="kv-key">稳定评分</span>
                        <span class="kv-val" :style="{ color: diagnosis.chanlun.fractal_stability_validation_v79.stability_score >= 0.7 ? '#22c55e' : diagnosis.chanlun.fractal_stability_validation_v79.stability_score >= 0.4 ? '#f59e0b' : '#ef4444' }">
                          {{ (diagnosis.chanlun.fractal_stability_validation_v79.stability_score * 100).toFixed(0) }}%
                        </span>
                        <span class="kv-key">置信度调整</span><span class="kv-val" :style="{ color: diagnosis.chanlun.fractal_stability_validation_v79.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">{{ diagnosis.chanlun.fractal_stability_validation_v79.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.fractal_stability_validation_v79.confidence_adjust * 100).toFixed(0) }}%</span>
                      </div>
                      <div class="kv-note">{{ diagnosis.chanlun.fractal_stability_validation_v79.msg }}</div>
                    </div>
                 </div>
                 <!-- V79: 买卖点距离安全阈值（条件249） -->
                 <div v-if="diagnosis.chanlun.mmd_distance_safety_v79" class="metric-card v79-mds">
                    <div class="card-title">📏 V79 距离安全（条件249）</div>
                    <div class="card-body">
                      <div class="kv-row">
                        <span class="kv-key">安全等级</span>
                        <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.mmd_distance_safety_v79.safety_level === 'safe', 'tag-blue': diagnosis.chanlun.mmd_distance_safety_v79.safety_level === 'moderate', 'tag-orange': diagnosis.chanlun.mmd_distance_safety_v79.safety_level === 'close', 'tag-red': diagnosis.chanlun.mmd_distance_safety_v79.safety_level === 'too_close', 'tag-gray': diagnosis.chanlun.mmd_distance_safety_v79.safety_level === 'isolated' }">
                          {{ {safe:'🟢 安全',moderate:'🔵 适中',close:'🟠 过近',too_close:'🔴 太近',isolated:'⚪ 孤立'}[diagnosis.chanlun.mmd_distance_safety_v79.safety_level] ?? '—' }}
                        </span>
                      </div>
                      <div class="kv-row">
                        <span class="kv-key">安全评分</span>
                        <span class="kv-val" :style="{ color: diagnosis.chanlun.mmd_distance_safety_v79.distance_score >= 0.7 ? '#22c55e' : diagnosis.chanlun.mmd_distance_safety_v79.distance_score >= 0.4 ? '#f59e0b' : '#ef4444' }">
                          {{ (diagnosis.chanlun.mmd_distance_safety_v79.distance_score * 100).toFixed(0) }}%
                        </span>
                        <span class="kv-key">距最近同向</span><span class="kv-val">{{ diagnosis.chanlun.mmd_distance_safety_v79.bars_to_nearest }}根K线</span>
                      </div>
                      <div class="kv-note">{{ diagnosis.chanlun.mmd_distance_safety_v79.msg }}</div>
                    </div>
                 </div>
                 <!-- V79: 多级别结构一致性评分（条件250） -->
                 <div v-if="diagnosis.chanlun.multi_level_structure_consistency_v79" class="metric-card v79-mls">
                    <div class="card-title">🔄 V79 多级别一致（条件250）</div>
                    <div class="card-body">
                      <div class="kv-row">
                        <span class="kv-key">短周期(5日)</span>
                        <span class="tag" :class="diagnosis.chanlun.multi_level_structure_consistency_v79.short_align ? 'tag-green' : 'tag-red'">
                          {{ diagnosis.chanlun.multi_level_structure_consistency_v79.short_align ? '✓ 同向' : '✗ 反向' }}
                        </span>
                        <span class="kv-key">中周期(20日)</span>
                        <span class="tag" :class="diagnosis.chanlun.multi_level_structure_consistency_v79.mid_align ? 'tag-green' : 'tag-red'">
                          {{ diagnosis.chanlun.multi_level_structure_consistency_v79.mid_align ? '✓ 同向' : '✗ 反向' }}
                        </span>
                      </div>
                      <div class="kv-row">
                        <span class="kv-key">长周期(60日)</span>
                        <span class="tag" :class="diagnosis.chanlun.multi_level_structure_consistency_v79.long_align ? 'tag-green' : 'tag-red'">
                          {{ diagnosis.chanlun.multi_level_structure_consistency_v79.long_align ? '✓ 同向' : '✗ 反向' }}
                        </span>
                        <span class="kv-key">一致评分</span>
                        <span class="kv-val" :style="{ color: diagnosis.chanlun.multi_level_structure_consistency_v79.consistency_score >= 0.7 ? '#22c55e' : diagnosis.chanlun.multi_level_structure_consistency_v79.consistency_score >= 0.4 ? '#f59e0b' : '#ef4444' }">
                          {{ (diagnosis.chanlun.multi_level_structure_consistency_v79.consistency_score * 100).toFixed(0) }}%
                        </span>
                      </div>
                      <div class="kv-note">{{ diagnosis.chanlun.multi_level_structure_consistency_v79.msg }}</div>
                    </div>
                 </div>
                 <!-- V79: 价格动能持续性评分（条件251） -->
                 <div v-if="diagnosis.chanlun.price_momentum_continuity_v79" class="metric-card v79-pmc">
                    <div class="card-title">⚡ V79 动能持续（条件251）</div>
                    <div class="card-body">
                      <div class="kv-row">
                        <span class="kv-key">动能级别</span>
                        <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.price_momentum_continuity_v79.momentum_level === 'strong', 'tag-blue': diagnosis.chanlun.price_momentum_continuity_v79.momentum_level === 'moderate', 'tag-orange': diagnosis.chanlun.price_momentum_continuity_v79.momentum_level === 'weak', 'tag-red': diagnosis.chanlun.price_momentum_continuity_v79.momentum_level === 'declining', 'tag-gray': diagnosis.chanlun.price_momentum_continuity_v79.momentum_level === 'neutral' }">
                          {{ {strong:'🟢 强劲',moderate:'🔵 中等',weak:'🟠 偏弱',declining:'🔴 衰竭',neutral:'⚪ 中性'}[diagnosis.chanlun.price_momentum_continuity_v79.momentum_level] ?? '—' }}
                        </span>
                      </div>
                      <div class="kv-row">
                        <span class="kv-key">动能评分</span>
                        <span class="kv-val" :style="{ color: diagnosis.chanlun.price_momentum_continuity_v79.momentum_score >= 0.7 ? '#22c55e' : diagnosis.chanlun.price_momentum_continuity_v79.momentum_score >= 0.4 ? '#f59e0b' : '#ef4444' }">
                          {{ (diagnosis.chanlun.price_momentum_continuity_v79.momentum_score * 100).toFixed(0) }}%
                        </span>
                        <span class="kv-key">加速度</span><span class="kv-val">{{ diagnosis.chanlun.price_momentum_continuity_v79.acceleration.toFixed(4) }}</span>
                      </div>
                      <div class="kv-row">
                        <span class="kv-key">量能趋势</span>
                        <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.price_momentum_continuity_v79.vol_trend === 'up', 'tag-red': diagnosis.chanlun.price_momentum_continuity_v79.vol_trend === 'down', 'tag-gray': diagnosis.chanlun.price_momentum_continuity_v79.vol_trend === 'neutral' }">
                          {{ {up:'📈 放大',down:'📉 萎缩',neutral:'➡️ 平稳'}[diagnosis.chanlun.price_momentum_continuity_v79.vol_trend] ?? '—' }}
                        </span>
                        <span class="kv-key">调整</span><span class="kv-val" :style="{ color: diagnosis.chanlun.price_momentum_continuity_v79.confidence_adjust > 0 ? '#22c55e' : '#ef4444' }">{{ diagnosis.chanlun.price_momentum_continuity_v79.confidence_adjust > 0 ? '+' : '' }}{{ (diagnosis.chanlun.price_momentum_continuity_v79.confidence_adjust * 100).toFixed(0) }}%</span>
                      </div>
                      <div class="kv-note">{{ diagnosis.chanlun.price_momentum_continuity_v79.msg }}</div>
                    </div>
                 </div>
                  <!-- V80: 买卖点与中枢距离验证（条件252） -->
                  <div v-if="diagnosis.chanlun.mmd_zhongshu_distance_v80" class="metric-card v80-msd">
                     <div class="card-title">🏛️ V80 中枢距离（条件252）</div>
                     <div class="card-body">
                       <div class="kv-row">
                         <span class="kv-key">中枢位置</span>
                         <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.mmd_zhongshu_distance_v80.zs_position === 'just_above', 'tag-blue': diagnosis.chanlun.mmd_zhongshu_distance_v80.zs_position === 'above', 'tag-orange': diagnosis.chanlun.mmd_zhongshu_distance_v80.zs_position === 'far_above', 'tag-yellow': diagnosis.chanlun.mmd_zhongshu_distance_v80.zs_position === 'inside', 'tag-red': diagnosis.chanlun.mmd_zhongshu_distance_v80.zs_position === 'below', 'tag-gray': diagnosis.chanlun.mmd_zhongshu_distance_v80.zs_position === 'unknown' }">
                           {{ {just_above:'🟢 刚突破',above:'🔵 上方',far_above:'🟠 过远',inside:'🟡 中枢内',below:'🔴 下方',unknown:'⚪ 未知'}[diagnosis.chanlun.mmd_zhongshu_distance_v80.zs_position] ?? '—' }}
                         </span>
                       </div>
                       <div class="kv-row">
                         <span class="kv-key">距离评分</span>
                         <span class="kv-val" :style="{ color: diagnosis.chanlun.mmd_zhongshu_distance_v80.distance_score >= 0.7 ? '#22c55e' : diagnosis.chanlun.mmd_zhongshu_distance_v80.distance_score >= 0.4 ? '#f59e0b' : '#ef4444' }">
                           {{ (diagnosis.chanlun.mmd_zhongshu_distance_v80.distance_score * 100).toFixed(0) }}%
                         </span>
                         <span class="kv-key">距中枢</span><span class="kv-val">{{ diagnosis.chanlun.mmd_zhongshu_distance_v80.nearest_zs_dist_pct > 0 ? '+' : '' }}{{ diagnosis.chanlun.mmd_zhongshu_distance_v80.nearest_zs_dist_pct }}%</span>
                       </div>
                       <div class="kv-note">{{ diagnosis.chanlun.mmd_zhongshu_distance_v80.msg }}</div>
                     </div>
                  </div>
                  <!-- V80: 量能配合度评分（条件253） -->
                  <div v-if="diagnosis.chanlun.volume_confirmation_v80" class="metric-card v80-vcf">
                     <div class="card-title">📊 V80 量能配合（条件253）</div>
                     <div class="card-body">
                       <div class="kv-row">
                         <span class="kv-key">价格趋势</span>
                         <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.volume_confirmation_v80.price_trend === 'up', 'tag-red': diagnosis.chanlun.volume_confirmation_v80.price_trend === 'down', 'tag-gray': diagnosis.chanlun.volume_confirmation_v80.price_trend === 'flat' }">
                           {{ {up:'📈 上涨',down:'📉 下跌',flat:'➡️ 横盘'}[diagnosis.chanlun.volume_confirmation_v80.price_trend] ?? '—' }}
                         </span>
                         <span class="kv-key">量能趋势</span>
                         <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.volume_confirmation_v80.volume_trend === 'up', 'tag-red': diagnosis.chanlun.volume_confirmation_v80.volume_trend === 'down', 'tag-gray': diagnosis.chanlun.volume_confirmation_v80.volume_trend === 'flat' }">
                           {{ {up:'📈 放量',down:'📉 缩量',flat:'➡️ 平稳'}[diagnosis.chanlun.volume_confirmation_v80.volume_trend] ?? '—' }}
                         </span>
                       </div>
                       <div class="kv-row">
                         <span class="kv-key">量比</span>
                         <span class="kv-val">{{ diagnosis.chanlun.volume_confirmation_v80.vol_ratio.toFixed(2) }}</span>
                         <span class="kv-key">配合评分</span>
                         <span class="kv-val" :style="{ color: diagnosis.chanlun.volume_confirmation_v80.confirmation_score >= 0.7 ? '#22c55e' : diagnosis.chanlun.volume_confirmation_v80.confirmation_score >= 0.4 ? '#f59e0b' : '#ef4444' }">
                           {{ (diagnosis.chanlun.volume_confirmation_v80.confirmation_score * 100).toFixed(0) }}%
                         </span>
                       </div>
                       <div class="kv-note">{{ diagnosis.chanlun.volume_confirmation_v80.msg }}</div>
                     </div>
                  </div>
                  <!-- V80: 均线排列强度确认（条件254） -->
                  <div v-if="diagnosis.chanlun.ma_alignment_strength_v80" class="metric-card v80-mas">
                     <div class="card-title">📐 V80 均线排列（条件254）</div>
                     <div class="card-body">
                       <div class="kv-row">
                         <span class="kv-key">均线排列</span>
                         <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.ma_alignment_strength_v80.ma_alignment === 'bullish', 'tag-red': diagnosis.chanlun.ma_alignment_strength_v80.ma_alignment === 'bearish', 'tag-orange': diagnosis.chanlun.ma_alignment_strength_v80.ma_alignment === 'mixed', 'tag-gray': diagnosis.chanlun.ma_alignment_strength_v80.ma_alignment === 'unknown' }">
                           {{ {bullish:'🟢 多头排列',bearish:'🔴 空头排列',mixed:'🟠 混乱',unknown:'⚪ 未知'}[diagnosis.chanlun.ma_alignment_strength_v80.ma_alignment] ?? '—' }}
                         </span>
                       </div>
                       <div class="kv-row">
                         <span class="kv-key">价格位置</span>
                         <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.ma_alignment_strength_v80.price_position === 'above_all', 'tag-blue': diagnosis.chanlun.ma_alignment_strength_v80.price_position === 'above_mid', 'tag-yellow': diagnosis.chanlun.ma_alignment_strength_v80.price_position === 'near_ma20', 'tag-orange': diagnosis.chanlun.ma_alignment_strength_v80.price_position === 'below_mid', 'tag-red': diagnosis.chanlun.ma_alignment_strength_v80.price_position === 'below_all', 'tag-gray': diagnosis.chanlun.ma_alignment_strength_v80.price_position === 'unknown' }">
                           {{ {above_all:'🟢 全上方',above_mid:'🔵 中上方',near_ma20:'🟡 贴近MA20',below_mid:'🟠 中下方',below_all:'🔴 全下方',unknown:'⚪ 未知'}[diagnosis.chanlun.ma_alignment_strength_v80.price_position] ?? '—' }}
                         </span>
                         <span class="kv-key">排列评分</span>
                         <span class="kv-val" :style="{ color: diagnosis.chanlun.ma_alignment_strength_v80.alignment_score >= 0.7 ? '#22c55e' : diagnosis.chanlun.ma_alignment_strength_v80.alignment_score >= 0.4 ? '#f59e0b' : '#ef4444' }">
                           {{ (diagnosis.chanlun.ma_alignment_strength_v80.alignment_score * 100).toFixed(0) }}%
                         </span>
                       </div>
                       <div class="kv-note">{{ diagnosis.chanlun.ma_alignment_strength_v80.msg }}</div>
                     </div>
                  </div>
                  <!-- V80: 盈亏比动态评估（条件255） -->
                  <div v-if="diagnosis.chanlun.dynamic_risk_reward_v80" class="metric-card v80-drr">
                     <div class="card-title">⚖️ V80 盈亏比（条件255）</div>
                     <div class="card-body">
                       <div class="kv-row">
                         <span class="kv-key">风险级别</span>
                         <span class="tag" :class="{ 'tag-green': diagnosis.chanlun.dynamic_risk_reward_v80.risk_level === 'excellent', 'tag-blue': diagnosis.chanlun.dynamic_risk_reward_v80.risk_level === 'good', 'tag-yellow': diagnosis.chanlun.dynamic_risk_reward_v80.risk_level === 'moderate', 'tag-orange': diagnosis.chanlun.dynamic_risk_reward_v80.risk_level === 'poor', 'tag-red': diagnosis.chanlun.dynamic_risk_reward_v80.risk_level === 'dangerous', 'tag-gray': diagnosis.chanlun.dynamic_risk_reward_v80.risk_level === 'unknown' }">
                           {{ {excellent:'🟢 极佳',good:'🔵 良好',moderate:'🟡 中等',poor:'🟠 较差',dangerous:'🔴 危险',unknown:'⚪ 未知'}[diagnosis.chanlun.dynamic_risk_reward_v80.risk_level] ?? '—' }}
                         </span>
                       </div>
                       <div class="kv-row">
                         <span class="kv-key">盈亏比</span>
                         <span class="kv-val" :style="{ color: diagnosis.chanlun.dynamic_risk_reward_v80.rr_ratio >= 2 ? '#22c55e' : diagnosis.chanlun.dynamic_risk_reward_v80.rr_ratio >= 1.5 ? '#f59e0b' : '#ef4444' }">
                           {{ diagnosis.chanlun.dynamic_risk_reward_v80.rr_ratio.toFixed(1) }}:1
                         </span>
                         <span class="kv-key">止损/止盈</span><span class="kv-val" style="color:#ef4444">-{{ diagnosis.chanlun.dynamic_risk_reward_v80.stop_loss_pct }}%</span><span class="kv-val" style="color:#22c55e">+{{ diagnosis.chanlun.dynamic_risk_reward_v80.take_profit_pct }}%</span>
                       </div>
                       <div class="kv-note">{{ diagnosis.chanlun.dynamic_risk_reward_v80.msg }}</div>
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

    <!-- V64: 多股票对比结果 -->
    <template v-if="multiMode && multiResults.length > 0">
      <div class="multi-compare-section">
        <div class="section-title">📊 V64 多股票信号质量对比</div>
        <div class="multi-table-wrap">
          <table class="multi-table">
            <thead>
              <tr>
                <th>股票代码</th>
                <th>K线数</th>
                <th>总信号</th>
                <th>买入</th>
                <th>卖出</th>
                <th>平均置信度</th>
                <th>V63-190命中</th>
                <th>V63-191命中</th>
                <th>V65-192命中</th>
                <th>V65-193命中</th>
                <th>V65-194命中</th>
                <th>V65-195命中</th>
                <th>V66-196命中</th>
                <th>V66-197命中</th>
                <th>V66-198命中</th>
                <th>V66-199命中</th>
                <th>V67-200命中</th>
                <th>V67-201命中</th>
                <th>V67-202命中</th>
                <th>V67-203命中</th>
                <th>V68-204命中</th>
                <th>V68-205命中</th>
                <th>V68-206命中</th>
                <th>V68-207命中</th>
                <th>V69-208命中</th>
                <th>V69-209命中</th>
                <th>V69-210命中</th>
                <th>V69-211命中</th>
                <th>V70-212命中</th>
                <th>V70-213命中</th>
                <th>V70-214命中</th>
                <th>V70-215命中</th>
                <th>V71-216命中</th>
                <th>V71-217命中</th>
                <th>V71-218命中</th>
                <th>V71-219命中</th>
                <th>V72-220命中</th>
                <th>V72-221命中</th>
                <th>V72-222命中</th>
                <th>V72-223命中</th>
                <th>V73-224命中</th>
                <th>V73-225命中</th>
                <th>V73-226命中</th>
                <th>V73-227命中</th>
                <th>V74-228命中</th>
                <th>V74-229命中</th>
                <th>V74-230命中</th>
                <th>V74-231命中</th>
                <th>V75-232命中</th>
                <th>V75-233命中</th>
                <th>V75-234命中</th>
                <th>V75-235命中</th>
                <th>V76-236命中</th>
                <th>V76-237命中</th>
                <th>V76-238命中</th>
                <th>V76-239命中</th>
                <th>V77-240命中</th>
                <th>V77-241命中</th>
                <th>V77-242命中</th>
                <th>V77-243命中</th>
                <th>V78-244命中</th>
                <th>V78-245命中</th>
                <th>V78-246命中</th>
                <th>V78-247命中</th>
                <th>V79-248命中</th>
                <th>V79-249命中</th>
                <th>V79-250命中</th>
                <th>V79-251命中</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in multiResults" :key="r.stock_code">
                <td class="code-cell">{{ r.stock_code }}</td>
                <td>{{ r.total_bars ?? '—' }}</td>
                <td>{{ r.signal_count }}</td>
                <td class="buy-cell">{{ r.buy_count }}</td>
                <td class="sell-cell">{{ r.sell_count }}</td>
                <td>
                  <span class="conf-badge" :style="{ background: confLevelColor(r.avg_confidence) + '22', color: confLevelColor(r.avg_confidence) }">
                    {{ r.avg_confidence.toFixed(2) }}
                  </span>
                </td>
                <td>{{ r.condition_breakdown?.v63_cond190 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v63_cond191 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v65_cond192 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v65_cond193 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v65_cond194 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v65_cond195 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v66_cond196 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v66_cond197 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v66_cond198 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v66_cond199 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v67_cond200 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v67_cond201 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v67_cond202 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v67_cond203 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v68_cond204 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v68_cond205 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v68_cond206 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v68_cond207 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v69_cond208 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v69_cond209 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v69_cond210 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v69_cond211 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v70_cond212 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v70_cond213 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v70_cond214 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v70_cond215 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v71_cond216 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v71_cond217 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v71_cond218 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v71_cond219 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v72_cond220 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v72_cond221 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v72_cond222 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v72_cond223 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v73_cond224 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v73_cond225 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v73_cond226 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v73_cond227 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v74_cond228 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v74_cond229 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v74_cond230 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v74_cond231 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v75_cond232 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v75_cond233 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v75_cond234 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v75_cond235 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v76_cond236 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v76_cond237 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v76_cond238 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v76_cond239 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v77_cond240 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v77_cond241 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v77_cond242 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v77_cond243 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v78_cond244 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v78_cond245 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v78_cond246 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v78_cond247 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v79_cond248 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v79_cond249 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v79_cond250 ?? 0 }}</td>
                <td>{{ r.condition_breakdown?.v79_cond251 ?? 0 }}</td>
                <td>
                  <span v-if="r.error" class="status-err">❌ {{ r.error }}</span>
                  <span v-else class="status-ok">✅ 正常</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- 条件命中详情 -->
        <div v-if="multiResultsHaveConditionData" class="condition-detail">
          <div class="section-title">条件命中详情（V58-V79）</div>
          <div class="cond-grid">
            <template v-for="r in multiResults" :key="r.stock_code">
              <div v-if="getConditionBreakdown(r).length > 0" class="cond-card">
                <div class="cond-card-title">{{ r.stock_code }}</div>
                <div v-for="(count, key) in getConditionBreakdown(r)" :key="key" class="cond-row">
                  <span class="cond-key">{{ key }}</span>
                  <span class="cond-val">{{ count }}</span>
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </template>

    <!-- 多股对比加载态 -->
    <div v-else-if="multiMode && multiLoading" class="state-center">
      <div class="spinner"></div>
      <p>正在对比分析多只股票…</p>
    </div>

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
.v76-summary-row { margin-bottom: 6px; }
.v76-tag {
  display: inline-block; padding: 3px 10px; border-radius: 12px;
  font-size: 12px; font-weight: 600;
  background: rgba(107,114,128,0.15); color: var(--text-dim);
}
.v76-tag.v76-strong  { background: rgba(34,197,94,0.15); color: #22c55e; }
.v76-tag.v76-moderate { background: rgba(59,130,246,0.15); color: #3b82f6; }
.v76-tag.v76-weak    { background: rgba(245,158,11,0.15); color: #f59e0b; }
.v76-tag.v76-invalid  { background: rgba(239,68,68,0.15); color: #ef4444; }
.v77-summary-row { margin-bottom: 6px; }
.v77-tag {
  display: inline-block; padding: 3px 10px; border-radius: 12px;
  font-size: 12px; font-weight: 600;
  background: rgba(139,92,246,0.15); color: #a78bfa;
}
.v77-tag.v77-strong  { background: rgba(34,197,94,0.15); color: #22c55e; }
.v77-tag.v77-moderate { background: rgba(59,130,246,0.15); color: #3b82f6; }
.v77-tag.v77-weak    { background: rgba(245,158,11,0.15); color: #f59e0b; }
.v77-tag.v77-mixed  { background: rgba(107,114,128,0.15); color: #9ca3af; }
.v78-summary-row { margin-bottom: 6px; }
.v78-tag {
  display: inline-block; padding: 3px 10px; border-radius: 12px;
  font-size: 12px; font-weight: 600; line-height: 1.4;
}
.v78-tag.v78-strong  { background: rgba(168,85,247,0.15); color: #a855f7; }
.v78-tag.v78-moderate { background: rgba(59,130,246,0.15); color: #3b82f6; }
.v78-tag.v78-weak    { background: rgba(245,158,11,0.15); color: #f59e0b; }
.v78-tag.v78-mixed  { background: rgba(107,114,128,0.15); color: #9ca3af; }
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

/* V58: 多时间框架 + 成交量堆积 + ATR止损 + 质量评分 */
.v58-tf .kv-val { font-weight: 600; }
.v58-vol .kv-val { font-weight: 600; }
.v58-atr .kv-val { font-weight: 600; }
.v58-quality .kv-val { font-weight: 600; }

/* V59: 波动率自适应MA + ATR倍数 + 多TF共振 + 信号衰减速度 */
.v59-vol-ma .kv-val { font-weight: 600; }
.v59-atr-mult .kv-val { font-weight: 600; }
.v59-resonance .kv-val { font-weight: 600; }
.v59-decay-speed .kv-val { font-weight: 600; }

/* V60: RSI深度背离 + MA间距 + 中枢距离 + KDJ超买超卖 */
.v60-rsi-div .kv-val { font-weight: 600; }
.v60-ma-spacing .kv-val { font-weight: 600; }
.v60-zs-dist .kv-val { font-weight: 600; }
.v60-kdj .kv-val { font-weight: 600; }

/* V61: MACD柱状图背离融合 + 综合多信号评分 */
.v61-macd-div .kv-val { font-weight: 600; }
.v61-composite .card-title { font-weight: 700; }
.v61-composite .kv-val { font-weight: 600; }
/* V62: BOLL带宽确认 + 动态阈值 */
.v62-boll-bw .kv-val { font-weight: 600; }
.v62-boll-rev .kv-val { font-weight: 600; }
.v62-dyn-threshold .kv-val { font-weight: 600; }
.v62-atr-mult .kv-val { font-weight: 600; }

/* V63: 中枢级别权重优化 + 多周期信号衰减追踪 */
.v63-zs-weight .kv-val { font-weight: 600; }
.v63-signal-decay .kv-val { font-weight: 600; }

/* V64: 多股票对比分析 */
.mode-toggle { display: flex; gap: 8px; margin-bottom: 12px; }
.mode-toggle button {
  padding: 6px 16px; border-radius: 6px; border: 1px solid #d1d5db;
  background: #f9fafb; cursor: pointer; font-size: 13px; color: #374151;
  transition: all 0.15s;
}
.mode-toggle button.active {
  background: #3b82f6; color: #fff; border-color: #3b82f6;
}
.multi-input-area {
  display: flex; flex-direction: column; gap: 8px; width: 100%; max-width: 500px;
}
.multi-entry {
  display: flex; gap: 8px; align-items: center;
}
.btn-remove {
  width: 32px; height: 32px; padding: 0; font-size: 14px; flex-shrink: 0;
}
.multi-compare-section { width: 100%; margin-top: 24px; }
.multi-table-wrap { overflow-x: auto; }
.multi-table {
  width: 100%; border-collapse: collapse; font-size: 13px;
  background: #fff; border-radius: 8px; overflow: hidden;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.multi-table th {
  background: #f3f4f6; padding: 10px 12px; text-align: left;
  font-weight: 600; color: #374151; border-bottom: 1px solid #e5e7eb;
  white-space: nowrap;
}
.multi-table td {
  padding: 9px 12px; border-bottom: 1px solid #f3f4f6; vertical-align: middle;
}
.multi-table tr:last-child td { border-bottom: none; }
.code-cell { font-family: monospace; font-weight: 600; color: #1f2937; }
.buy-cell { color: #16a34a; }
.sell-cell { color: #dc2626; }
.conf-badge {
  display: inline-block; padding: 2px 8px; border-radius: 10px;
  font-size: 12px; font-weight: 600;
}
.status-ok { color: #16a34a; font-size: 12px; }
.status-err { color: #dc2626; font-size: 12px; }
.cond-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px; margin-top: 12px;
}
.cond-card {
  background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
  padding: 12px; font-size: 12px;
}
.cond-card-title {
  font-weight: 700; font-size: 13px; color: #1f2937;
  margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid #f3f4f6;
}
.cond-row {
  display: flex; justify-content: space-between; padding: 3px 0;
}
.cond-key { color: #6b7280; }
.cond-val { font-weight: 600; color: #374151; }

/* V65: 量价背离二次确认 + 突破回踩 + 波动率压缩 + 信号新鲜度 */
.v65-vp-div .kv-val { font-weight: 600; }
.v65-breakout .kv-val { font-weight: 600; }
.v65-squeeze .kv-val { font-weight: 600; }
.v65-freshness .kv-val { font-weight: 600; }
.v66-macd-acc .kv-val { font-weight: 600; }
.v66-vp-coord .kv-val { font-weight: 600; }
.v66-tf-conv .kv-val { font-weight: 600; }
.v66-priority .kv-val { font-weight: 700; }
.v67-zs-div .kv-val { font-weight: 600; }
.v67-ml-cons .kv-val { font-weight: 600; }
.v67-traj .kv-val { font-weight: 600; }
.v67-sltp .kv-val { font-weight: 700; }
.v68-gap .kv-val { font-weight: 600; }
.v68-range .kv-val { font-weight: 700; }
.v68-fund .kv-val { font-weight: 600; }
.v68-regime .kv-val { font-weight: 700; }
.v69-pv .kv-val { font-weight: 600; }
.v69-struct .kv-val { font-weight: 700; }
.v69-multi .kv-val { font-weight: 600; }
.v69-ret .kv-val { font-weight: 700; }

/* V70: 量峰检测+时间衰减+假突破过滤+置信度校准 */
.v70-vp .kv-val { font-weight: 600; }
.v70-decay .kv-val { font-weight: 700; }
.v70-fb .kv-val { font-weight: 600; }
.v70-cali .kv-val { font-weight: 700; }

/* V72: 均线收敛发散+支撑阻力距离+量价结构质量+信号衰减速度 */
.v72-ma .kv-val { font-weight: 600; }
.v72-sr .kv-val { font-weight: 600; }
.v72-vsq .kv-val { font-weight: 600; }
.v72-sdv .kv-val { font-weight: 600; }
.v73-pr .kv-val { font-weight: 600; }
.v73-zb .kv-val { font-weight: 600; }
.v73-mic .kv-val { font-weight: 600; }
.v73-vra .kv-val { font-weight: 600; }
/* V74: 量价背离+动能持续+中枢重叠+共振深度 */
.v74-vpd .kv-val { font-weight: 600; }
.v74-tmc .kv-val { font-weight: 600; }
.v74-zod .kv-val { font-weight: 600; }
.v74-srd .kv-val { font-weight: 600; }
/* V75: 回调深度+中枢回踩+量峰持续+时间一致性 */
.v75-pdv .kv-val { font-weight: 600; }
.v75-zrc .kv-val { font-weight: 600; }
.v75-vpd .kv-val { font-weight: 600; }
.v75-mstc .kv-val { font-weight: 600; }
/* V76: 结构完整+趋势对齐+波动率自适应+最终有效性 */
.v76-psI .kv-val { font-weight: 600; }
.v76-tav .kv-val { font-weight: 600; }
.v76-vac .kv-val { font-weight: 600; }
.v76-sfv .kv-val { font-weight: 700; }
/* V77: 量能分布+中枢权重+新鲜度+动能加速度 */
.v77-vdd .kv-val { font-weight: 600; }
.v77-zsw .kv-val { font-weight: 600; }
.v77-sfsh .kv-val { font-weight: 600; }
.v77-pma .kv-val { font-weight: 600; }
.v78-mcp .kv-val { font-weight: 600; }
.v78-msc .kv-val { font-weight: 600; }
.v78-vcb .kv-val { font-weight: 600; }
.v78-ffd .kv-val { font-weight: 600; }
.v79-fsv .kv-val { font-weight: 600; }
.v79-mds .kv-val { font-weight: 600; }
.v79-mls .kv-val { font-weight: 600; }
.v79-pmc .kv-val { font-weight: 600; }
.v79-summary-row { margin-bottom: 6px; }
.v79-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 600;
  margin-right: 6px;
}
.v79-tag.v79-strong   { background: rgba(34,197,94,0.15); color: #22c55e; }
.v79-tag.v79-moderate { background: rgba(59,130,246,0.15); color: #3b82f6; }
.v79-tag.v79-weak     { background: rgba(245,158,11,0.15); color: #f59e0b; }
.v79-tag.v79-mixed    { background: rgba(107,114,128,0.15); color: #9ca3af; }
.v80-msd .kv-val { font-weight: 600; }
.v80-vcf .kv-val { font-weight: 600; }
.v80-mas .kv-val { font-weight: 600; }
.v80-drr .kv-val { font-weight: 600; }
.v80-summary-row { margin-bottom: 6px; }
.v80-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 600;
  margin-right: 6px;
}
.v80-tag.v80-strong   { background: rgba(34,197,94,0.15); color: #22c55e; }
.v80-tag.v80-moderate { background: rgba(59,130,246,0.15); color: #3b82f6; }
.v80-tag.v80-weak     { background: rgba(245,158,11,0.15); color: #f59e0b; }
.v80-tag.v80-mixed    { background: rgba(107,114,128,0.15); color: #9ca3af; }
</style>
