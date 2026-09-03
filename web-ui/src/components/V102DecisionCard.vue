<template>
  <div v-if="hasV102" class="v102-card">
    <div class="v102-header">🎯 V102 决策支持 <small>(条件264-267)</small></div>

    <!-- 条件266：操作建议（入场/止损/止盈/仓位） -->
    <div v-if="mmd && mmd.v102_decision_support" class="v102-sec">
      <div class="v102-action" :class="recClass">{{ recText }}</div>
      <div class="v102-grid">
        <div class="v102-item">
          <span class="v102-k">入场价</span>
          <b class="buy">{{ fmt(mmd.v102_decision_support.entry_price) }}</b>
        </div>
        <div class="v102-item">
          <span class="v102-k">止损价</span>
          <b class="sell">{{ fmt(mmd.v102_decision_support.stop_loss) }}</b>
        </div>
        <div class="v102-item">
          <span class="v102-k">止盈1</span>
          <b class="buy">{{ fmt(mmd.v102_decision_support.take_profit_1) }}</b>
        </div>
        <div class="v102-item">
          <span class="v102-k">止盈2</span>
          <b class="buy">{{ fmt(mmd.v102_decision_support.take_profit_2) }}</b>
        </div>
        <div class="v102-item">
          <span class="v102-k">风险收益比</span>
          <b>{{
            mmd.v102_decision_support.risk_reward_ratio
              ? '1 : ' + mmd.v102_decision_support.risk_reward_ratio
              : '—'
          }}</b>
        </div>
        <div class="v102-item">
          <span class="v102-k">建议仓位</span>
          <b :class="positionClass">{{ mmd.v102_decision_support.position_size_pct }}%</b>
        </div>
      </div>
      <div v-if="mmd.v102_decision_support.risk_notes" class="v102-note">
        ⚙️ {{ mmd.v102_decision_support.risk_notes }}
      </div>
    </div>

    <!-- 条件265：信号质量评分卡 -->
    <div v-if="mmd && mmd.v102_signal_quality" class="v102-sec">
      <div class="v102-sub">📊 信号质量评分卡</div>
      <div class="v102-grade-row">
        <span class="v102-grade" :class="'g' + (mmd.v102_signal_quality.overall_grade || 'C')">{{
          mmd.v102_signal_quality.overall_grade || 'C'
        }}</span>
        <span class="v102-grade-text"
          >{{ mmd.v102_signal_quality.overall_score }} 分 · {{ strengthText }}</span
        >
        <span
          v-if="mmd.v102_signal_quality.confidence_adjust"
          class="v102-adjust"
          :class="mmd.v102_signal_quality.confidence_adjust > 0 ? 'up' : 'down'"
        >
          {{ fmtAdj(mmd.v102_signal_quality.confidence_adjust) }}
        </span>
      </div>
      <div class="v102-bars">
        <div v-for="bar in qualityBars" :key="bar.label" class="v102-bar-row">
          <span class="v102-bar-label">{{ bar.label }}</span>
          <div class="v102-bar"><i :style="{ width: bar.pct }" /></div>
        </div>
      </div>
    </div>

    <!-- 条件267：历史模式匹配 -->
    <div v-if="mmd && mmd.v102_pattern_match" class="v102-sec">
      <div class="v102-sub">📈 历史模式匹配</div>
      <div class="v102-grid">
        <div class="v102-item">
          <span class="v102-k">相似形态</span>
          <b>{{ mmd.v102_pattern_match.similar_patterns_found }} 个</b>
        </div>
        <div class="v102-item">
          <span class="v102-k">胜率</span>
          <b class="buy">{{ mmd.v102_pattern_match.win_rate }}%</b>
        </div>
        <div class="v102-item">
          <span class="v102-k">平均收益</span>
          <b>{{ mmd.v102_pattern_match.avg_return }}%</b>
        </div>
        <div class="v102-item">
          <span class="v102-k">最大回撤</span>
          <b class="sell">{{ mmd.v102_pattern_match.max_drawdown }}%</b>
        </div>
      </div>
      <div v-if="mmd.v102_pattern_match.msg" class="v102-note">
        {{ mmd.v102_pattern_match.msg }}
      </div>
    </div>

    <!-- 条件264：多信号相关性 -->
    <div
      v-if="mmd && mmd.v102_multi_signal_correlation && mmd.v102_multi_signal_correlation.msg"
      class="v102-sec"
    >
      <div class="v102-note" style="color: var(--text-dim)">
        {{ mmd.v102_multi_signal_correlation.msg }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DiagnosisChanlunMmd } from '../types'

const props = defineProps<{ mmd: DiagnosisChanlunMmd | null }>()

const hasV102 = computed(
  () =>
    !!props.mmd &&
    !!(
      props.mmd.v102_decision_support ||
      props.mmd.v102_signal_quality ||
      props.mmd.v102_pattern_match ||
      props.mmd.v102_multi_signal_correlation
    ),
)

const recText = computed(() => {
  const rec: string | undefined = props.mmd?.v102_decision_support?.action_recommendation
  return rec || '暂不提供操作建议'
})

const recClass = computed(() => {
  const rec = recText.value
  if (rec.includes('买入')) return 'action-buy'
  if (rec.includes('卖出')) return 'action-sell'
  return 'action-hold'
})

const positionClass = computed(() => {
  const pct = props.mmd?.v102_decision_support?.position_size_pct ?? 0
  if (pct >= 20) return 'pos-mid'
  return 'pos-low'
})

const STRENGTH_TEXT: Record<string, string> = {
  strong: '强信号',
  medium: '中等',
  weak: '偏弱',
  very_weak: '极弱',
}

const strengthText = computed(
  () => STRENGTH_TEXT[props.mmd?.v102_signal_quality?.strength ?? ''] ?? '',
)

const qualityBars = computed(() => {
  const q = props.mmd?.v102_signal_quality
  if (!q) return []
  const pct = (v: number, max: number): string => {
    const p = Math.min(100, Math.max(0, (v / max) * 100)).toFixed(0)
    return p + '%'
  }
  return [
    { label: '技术指标', pct: pct(q.tech_score, 4) },
    { label: '量价配合', pct: pct(q.volume_score, 2) },
    { label: '趋势对齐', pct: pct(q.trend_score, 2) },
    { label: '波动率环境', pct: pct(q.volatility_score, 1) },
  ]
})

const fmt = (v: number | null | undefined): string => (v == null ? '—' : Number(v).toFixed(2))

const fmtAdj = (v: number | null | undefined): string => {
  if (v == null || v === 0) return ''
  const pct = (v * 100).toFixed(0)
  return (Number(v) > 0 ? '+' : '') + pct + '% 置信度'
}
</script>

<style scoped>
.v102-card {
  margin-top: 6px;
  padding: 8px 10px;
  border: 1px dashed var(--accent, #4a9eff);
  border-radius: 8px;
  background: rgba(74, 158, 255, 0.04);
  font-size: 12px;
}
.v102-header {
  font-weight: 600;
  margin-bottom: 6px;
}
.v102-header small {
  font-weight: 400;
  color: var(--text-dim, #5c6370);
}
.v102-sec {
  padding: 6px 0;
  border-top: 1px solid rgba(128, 128, 128, 0.15);
}
.v102-sec:first-of-type {
  border-top: none;
}
.v102-action {
  font-weight: 700;
  padding: 4px 8px;
  border-radius: 6px;
  margin-bottom: 6px;
}
.action-buy {
  color: #22c55e;
  background: rgba(34, 197, 94, 0.1);
}
.action-sell {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}
.action-hold {
  color: #f59e0b;
  background: rgba(245, 158, 11, 0.1);
}
.v102-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px 10px;
}
.v102-item {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.v102-k {
  font-size: 10px;
  color: var(--text-dim, #5c6370);
}
.v102-item b {
  font-weight: 600;
  font-size: 12px;
}
.buy {
  color: #22c55e;
}
.sell {
  color: #ef4444;
}
.pos-mid {
  color: #f59e0b;
}
.pos-low {
  color: #94a3b8;
}
.v102-note {
  margin-top: 5px;
  color: var(--text-secondary, #8b93a3);
  font-size: 11px;
}
.v102-sub {
  font-size: 11px;
  color: var(--text-dim, #5c6370);
  margin-bottom: 4px;
}
.v102-grade-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.v102-grade {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 12px;
  color: #fff;
}
.gA {
  background: #22c55e;
}
.gB {
  background: #4a9eff;
}
.gC {
  background: #f59e0b;
}
.gD {
  background: #ef4444;
}
.v102-grade-text {
  font-size: 11px;
}
.v102-adjust {
  margin-left: auto;
  font-size: 11px;
}
.v102-adjust.up {
  color: #22c55e;
}
.v102-adjust.down {
  color: #ef4444;
}
.v102-bars {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.v102-bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.v102-bar-label {
  width: 58px;
  font-size: 10px;
  color: var(--text-dim, #5c6370);
  text-align: right;
}
.v102-bar {
  flex: 1;
  height: 5px;
  background: rgba(128, 128, 128, 0.15);
  border-radius: 3px;
  overflow: hidden;
}
.v102-bar i {
  display: block;
  height: 100%;
  background: var(--accent, #4a9eff);
  border-radius: 3px;
}
</style>
