<script setup lang="ts">
// 选股两步流（v590）：Step1 长盈基本面选股池 → Step2 缠论择时。
import { ref } from 'vue'
import BeginnerGuide from '../components/BeginnerGuide.vue'
import ChanlunChart from '../components/ChanlunChart.vue'
import {
  formatError,
  stockPickScreen,
  stockPickTiming,
  type StockPickPoolItem,
  type StockPickTimingResult,
} from '../api'

const selectDate = ref('2025-01-02')
const markets = ref<string[]>(['SZ', 'SH'])
const poolScope = ref<'pool' | 'full'>('pool')
const poolText = ref('') // 自定义池（每行 600519 / 000001；空则用热门池）
const screening = ref(false)
const timing = ref(false)
const pool = ref<StockPickPoolItem[]>([])
const screenSource = ref<string>('')
const screenUpdatedAt = ref<string>('')
const selected = ref<StockPickPoolItem | null>(null)
const timingResult = ref<StockPickTimingResult | null>(null)
const error = ref('')

const categoryLabel: Record<string, string> = {
  tree: '🌳 树型',
  grain: '🌾 粮型',
  vegetable: '🥬 菜型',
}

function parseCustomPool(): { market: string; code: string }[] {
  return poolText.value
    .split(/[\s,，;；]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((raw) => {
      const code = raw.replace(/^(SH|SZ)/i, '').padStart(6, '0')
      const market = /^SH/i.test(raw) ? 'SH' : /^SZ/i.test(raw) ? 'SZ' : ''
      return { market, code }
    })
    .filter((x) => x.code.length === 6)
}

async function runScreen() {
  error.value = ''
  screening.value = true
  selected.value = null
  timingResult.value = null
  try {
    const custom = parseCustomPool()
    const req: any = {
      date: selectDate.value,
      markets: markets.value,
      stock_type: 'all',
      pool_scope: poolScope.value,
      top_n: 50,
    }
    if (poolScope.value === 'pool' && custom.length) {
      req.pool = custom.map((c) => ({ market: c.market || 'SH', code: c.code }))
    }
    const res = await stockPickScreen(req)
    pool.value = res.results
    screenSource.value = (res as any).source ?? 'online'
    screenUpdatedAt.value = (res as any).updated_at ?? ''
    if (!res.results.length) error.value = '该时间/池内暂无符合长盈模型的标的'
  } catch (e) {
    error.value = formatError(e)
  } finally {
    screening.value = false
  }
}

async function runTiming(item: StockPickPoolItem) {
  error.value = ''
  selected.value = item
  timingResult.value = null
  timing.value = true
  try {
    const res = await stockPickTiming({
      date: selectDate.value,
      symbols: [{ market: item.market || 'SH', code: item.code }],
      count: 500,
    })
    timingResult.value = res.results[0] ?? null
    if (timingResult.value?.error) error.value = timingResult.value.error
  } catch (e) {
    error.value = formatError(e)
  } finally {
    timing.value = false
  }
}
</script>

<template>
  <section class="stock-pick-view">
    <h2>选股（长盈基本面 → 缠论择时）</h2>
    <BeginnerGuide />

    <div class="controls">
      <label>
        目标日期
        <input v-model="selectDate" type="date" />
      </label>
      <fieldset>
        <legend>市场</legend>
        <label><input v-model="markets" type="checkbox" value="SZ" /> 深圳</label>
        <label><input v-model="markets" type="checkbox" value="SH" /> 上海</label>
      </fieldset>
      <label>
        池范围
        <select v-model="poolScope">
          <option value="pool">热门池/自定义池</option>
          <option value="full">全市场扫描</option>
        </select>
      </label>
      <label v-if="poolScope === 'pool'" class="pool-text">
        自定义池（每行一个代码，留空用热门池）
        <textarea v-model="poolText" rows="2" placeholder="600519&#10;000333" />
      </label>
      <button :disabled="screening" @click="runScreen">
        {{ screening ? '选股中…' : '① 长盈选股' }}
      </button>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="layout">
      <div class="pool-panel">
        <h3>基本面标的池（{{ pool.length }}）</h3>
        <p v-if="screenSource" class="source-note">
          数据来源：{{ screenSource === 'local' ? '本地沉淀池' : '在线扫描' }}<template v-if="screenUpdatedAt"> · 更新于 {{ screenUpdatedAt.slice(0, 10) }}</template>
        </p>
        <table v-if="pool.length">
          <thead>
            <tr>
              <th>标的</th>
              <th>分类</th>
              <th>质量分</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in pool"
              :key="item.symbol"
              :class="{ active: selected?.symbol === item.symbol }"
            >
              <td>{{ item.symbol }}</td>
              <td>{{ categoryLabel[item.category] ?? item.category }}</td>
              <td>{{ item.quality_score?.toFixed?.(1) ?? item.quality_score }}</td>
              <td>
                <button :disabled="timing" @click="runTiming(item)">② 缠论择时</button>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="hint">选择时间后点击「① 长盈选股」生成基本面标的池。</p>
      </div>

      <div class="timing-panel">
        <h3>缠论择时详情</h3>
        <template v-if="timingResult">
          <div v-if="timingResult.verdict" class="verdict">
            <strong>{{ timingResult.verdict.action }}</strong>
            <span>{{ timingResult.verdict.signal }} · {{ (timingResult.verdict.confidence ?? 0) * 100 }}%</span>
            <p>{{ timingResult.verdict.reason }}</p>
            <div v-if="timingResult.novice_advice" class="novice-advice">
              <p>{{ timingResult.novice_advice.explanation }}</p>
              <div class="levels">
                <span>参考入场：{{ timingResult.novice_advice.entry ?? '—' }}</span>
                <span>止损：{{ timingResult.novice_advice.stop ?? '—' }}</span>
                <span>目标：{{ timingResult.novice_advice.target ?? '—' }}</span>
              </div>
              <p class="position-note">{{ timingResult.novice_advice.position_note }}</p>
            </div>
            <div v-if="timingResult.signal_quality?.summary" class="signal-quality">
              <p>📊 信号可信度：{{ timingResult.signal_quality.summary }}</p>
            </div>
          </div>
          <ChanlunChart
            v-if="timingResult.bars?.length"
            :bars="(timingResult.bars as any)"
            :bis="(timingResult.bis as any) ?? []"
            :xds="(timingResult.xds as any) ?? []"
            :zss="(timingResult.zss as any) ?? []"
            :mmds="(timingResult.mmds as any) ?? []"
            :fxs="(timingResult.fractals as any) ?? []"
            :bcs="(timingResult.bcs as any) ?? []"
            :macd="(timingResult.macd as any) ?? undefined"
            frequency="daily"
            compact
          />
          <p v-else class="hint">该标的截至目标日无足够 K 线，无法绘制缠论图。</p>
        </template>
        <p v-else class="hint">在左侧点击「② 缠论择时」查看单只标的的买卖点/背驰/中枢。</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.stock-pick-view {
  padding: 20px;
}
.controls {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  align-items: flex-end;
  margin-bottom: 12px;
}
.controls label,
.controls fieldset {
  font-size: 13px;
  color: var(--text-dim);
}
.controls input,
.controls textarea,
.controls select {
  background: var(--bg-input, #1a1d26);
  color: var(--text, #e6e6e6);
  border: 1px solid var(--border, #2a2e3a);
  border-radius: 4px;
  padding: 6px 8px;
  margin-top: 4px;
}
.pool-text {
  display: flex;
  flex-direction: column;
}
button {
  background: var(--accent, #3b82f6);
  color: #fff;
  border: none;
  border-radius: 4px;
  padding: 8px 12px;
  cursor: pointer;
}
button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.error {
  color: #f87171;
}
.layout {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 16px;
  margin-top: 12px;
}
.pool-panel,
.timing-panel {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px;
}
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
th,
td {
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}
tr.active td {
  background: rgba(59, 130, 246, 0.12);
}
.verdict {
  padding: 10px;
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.3);
  border-radius: 6px;
  margin-bottom: 12px;
}
.verdict strong {
  font-size: 18px;
  margin-right: 10px;
}
.novice-advice {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed rgba(255, 255, 255, 0.15);
}
.novice-advice p {
  margin: 4px 0;
  color: var(--text);
}
.levels {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  font-size: 13px;
  color: #e5e7eb;
}
.position-note {
  color: #fbbf24;
}
.signal-quality {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed rgba(255, 255, 255, 0.15);
  font-size: 12px;
  color: #94a3b8;
}
.verdict p {
  margin: 6px 0 0;
  color: var(--text-dim);
}
.hint {
  color: var(--text-dim);
}
.source-note {
  font-size: 12px;
  color: #94a3b8;
  margin: 4px 0;
}
</style>