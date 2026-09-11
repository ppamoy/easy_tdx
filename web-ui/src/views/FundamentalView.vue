<!-- P1/P2 长赢基本面选股：单日选股 + 批量时点验证 + 全市场扫描 -->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { formatError } from '../api'

// ── 模式：单日选股 / 批量验证 / 全市场扫描 ────────────────────────────
const mode = ref<'screen' | 'verify' | 'scan'>('screen')

// 单日选股
const selectDate = ref('')
const poolText = ref('')
const stockType = ref<'all' | 'tree' | 'grain' | 'vegetable'>('all')
const loading = ref(false)
const error = ref('')
const result = ref<any>(null)

// 批量验证
const verifyDatesText = ref('')
const verifyLoading = ref(false)
const verifyError = ref('')
const verifyResult = ref<any>(null)

// 全市场扫描
const scanDate = ref('')
const scanMarkets = ref<Record<string, boolean>>({ SH: true, SZ: true })
const scanStockType = ref<'all' | 'tree' | 'grain' | 'vegetable'>('all')
const scanTopN = ref(50)
const scanMinScore = ref(15)
const scanWithPerf = ref(true)
const scanSinaPool = ref('')
const scanLoading = ref(false)
const scanError = ref('')
const scanResult = ref<any>(null)

const CATEGORY_COLORS: Record<string, string> = {
  tree: '#22c55e',
  grain: '#f59e0b',
  vegetable: '#ef4444',
}
const CATEGORY_LABELS: Record<string, string> = {
  tree: '🌳 树型',
  grain: '🌾 粮型',
  vegetable: '🥬 菜型',
}

const DEFAULT_POOL = [
  { market: 'SH', code: '600519' },
  { market: 'SZ', code: '000858' },
  { market: 'SZ', code: '000333' },
  { market: 'SH', code: '601318' },
  { market: 'SH', code: '600036' },
  { market: 'SH', code: '600900' },
  { market: 'SZ', code: '300750' },
  { market: 'SZ', code: '002594' },
  { market: 'SH', code: '601012' },
]

const DEFAULT_VERIFY_DATES = ['2024-04-15', '2025-04-15', '2025-10-15']

function parsePoolText(text: string) {
  const lines = text
    .split(/[\s,，;；]+/)
    .map((s) => s.trim())
    .filter((s) => s.length >= 6)
  const seen = new Set<string>()
  const pool: { market: string; code: string }[] = []
  for (const ln of lines) {
    const digits = ln.replace(/\D/g, '').slice(0, 6)
    if (digits.length !== 6) continue
    const market = digits.startsWith('6') ? 'SH' : 'SZ'
    const key = market + digits
    if (seen.has(key)) continue
    seen.add(key)
    pool.push({ market, code: digits })
  }
  return pool
}

const pool = computed(() => {
  const txt = poolText.value.trim()
  if (txt) return parsePoolText(txt)
  return DEFAULT_POOL
})

function parseDates(text: string): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const ln of text.split(/[\s,，;；]+/)) {
    const s = ln.trim()
    if (/^\d{4}-\d{2}-\d{2}$/.test(s) && !seen.has(s)) {
      seen.add(s)
      out.push(s)
    }
  }
  return out
}

async function runScreen() {
  if (!selectDate.value) {
    error.value = '请选择历史日期'
    return
  }
  if (pool.value.length === 0) {
    error.value = '自选池为空，请输入至少一个股票代码'
    return
  }
  loading.value = true
  error.value = ''
  result.value = null
  try {
    const resp = await fetch('/api/v1/fundamental/screen', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date: selectDate.value,
        stock_type: stockType.value,
        pool: pool.value,
      }),
    })
    if (!resp.ok) throw new Error(await resp.text())
    result.value = await resp.json()
  } catch (e) {
    error.value = formatError(e)
  } finally {
    loading.value = false
  }
}

async function runVerify() {
  const dates = parseDates(verifyDatesText.value)
  if (dates.length < 1) {
    verifyError.value = '请输入至少一个历史日期（YYYY-MM-DD）'
    return
  }
  if (pool.value.length === 0) {
    verifyError.value = '自选池为空，请输入至少一个股票代码'
    return
  }
  verifyLoading.value = true
  verifyError.value = ''
  verifyResult.value = null
  try {
    const resp = await fetch('/api/v1/fundamental/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dates, pool: pool.value }),
    })
    if (!resp.ok) throw new Error(await resp.text())
    verifyResult.value = await resp.json()
  } catch (e) {
    verifyError.value = formatError(e)
  } finally {
    verifyLoading.value = false
  }
}

async function runScan() {
  if (!scanDate.value) {
    scanError.value = '请选择历史日期'
    return
  }
  const markets = Object.entries(scanMarkets.value)
    .filter(([, on]) => on)
    .map(([m]) => m)
  if (markets.length === 0) {
    scanError.value = '至少选择一个市场（SH/SZ）'
    return
  }
  // V91：新浪补充自选池（gpcw 未覆盖历史时点时用新浪财报）
  const sinaPool = parsePoolText(scanSinaPool.value)
  scanLoading.value = true
  scanError.value = ''
  scanResult.value = null
  try {
    const resp = await fetch('/api/v1/fundamental/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date: scanDate.value,
        markets,
        stock_type: scanStockType.value,
        top_n: Number(scanTopN.value) || 50,
        min_score: Number(scanMinScore.value) || 0,
        with_performance: scanWithPerf.value,
        ...(sinaPool.length ? { sina_pool: sinaPool } : {}),
      }),
    })
    if (!resp.ok) throw new Error(await resp.text())
    scanResult.value = await resp.json()
  } catch (e) {
    scanError.value = formatError(e)
  } finally {
    scanLoading.value = false
  }
}

const scanStats = computed(() => {
  const rs = scanResult.value?.results ?? []
  return {
    total: scanResult.value?.total_scanned ?? 0,
    returned: rs.length,
    tree: scanResult.value?.by_category?.tree ?? 0,
    grain: scanResult.value?.by_category?.grain ?? 0,
    vegetable: scanResult.value?.by_category?.vegetable ?? 0,
    truncated: scanResult.value?.truncated ?? 0,
  }
})

const stats = computed(() => {
  const rs = result.value?.results ?? []
  return {
    total: rs.length,
    tree: rs.filter((r: any) => r.category === 'tree').length,
    grain: rs.filter((r: any) => r.category === 'grain').length,
    vegetable: rs.filter((r: any) => r.category === 'vegetable').length,
  }
})

function fmt(v: any, suffix = '') {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  if (typeof v === 'number') return v.toFixed(1) + suffix
  return String(v) + suffix
}

/** 估值（PE/PB）两位小数。 */
function fmtVal(v: any) {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  return Number(v).toFixed(2)
}

/** 金额以「亿」显示（年化营收等）。 */
function fmtYi(v: any) {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  return (Number(v) / 1e8).toFixed(1) + '亿'
}

function pct(v: any) {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  return (v * 100).toFixed(0) + '%'
}

function colorBy(v: any) {
  if (v === null || v === undefined || Number.isNaN(v)) return ''
  return v > 0 ? '#22c55e' : v < 0 ? '#ef4444' : ''
}

const verifySummary = computed(() => verifyResult.value?.summary ?? null)
const verifyPeriods = computed(() => verifyResult.value?.periods ?? [])

onMounted(() => {
  const now = new Date()
  const d = new Date(now.getFullYear(), now.getMonth() - 2, 15)
  selectDate.value = d.toISOString().slice(0, 10)
  scanDate.value = d.toISOString().slice(0, 10)
  poolText.value = DEFAULT_POOL.map((p) => p.code).join('\n')
  verifyDatesText.value = DEFAULT_VERIFY_DATES.join('\n')
})
</script>

<template>
  <div class="fundamental-view">
    <!-- 模式切换 + 配置栏 -->
    <div class="config-bar">
      <div class="mode-tabs">
        <button class="mode-tab" :class="{ active: mode === 'screen' }" @click="mode = 'screen'">
          📌 单日选股
        </button>
        <button class="mode-tab" :class="{ active: mode === 'verify' }" @click="mode = 'verify'">
          📈 批量时点验证
        </button>
        <button class="mode-tab" :class="{ active: mode === 'scan' }" @click="mode = 'scan'">
          🔭 全市场扫描
        </button>
      </div>

      <template v-if="mode === 'screen'">
        <div class="field-group">
          <label>历史日期（只使用该日之前已披露的财报）</label>
          <input v-model="selectDate" type="date" class="date-input" />
        </div>
        <div class="field-group">
          <label>股票类型</label>
          <select v-model="stockType" class="market-select">
            <option value="all">全部</option>
            <option value="tree">🌳 树型</option>
            <option value="grain">🌾 粮型</option>
            <option value="vegetable">🥬 菜型</option>
          </select>
        </div>
        <button class="primary scan-btn" :disabled="loading" @click="runScreen">
          {{ loading ? '选股中（加载 gpcw 财报 + 计算指标）…' : '🚀 开始历史时点选股' }}
        </button>
      </template>

      <template v-else-if="mode === 'verify'">
        <div class="field-group dates-group">
          <label>历史日期（每行一个 YYYY-MM-DD，多个时点汇总验证）</label>
          <textarea
            v-model="verifyDatesText"
            class="pool-input"
            rows="3"
            placeholder="2024-04-15&#10;2025-04-15&#10;..."
          />
        </div>
        <button class="primary scan-btn" :disabled="verifyLoading" @click="runVerify">
          {{ verifyLoading ? '批量验证中（逐时点选股 + 回看后续）…' : '📈 运行批量时点验证' }}
        </button>
      </template>

      <template v-else-if="mode === 'scan'">
        <div class="field-group">
          <label>历史日期（全市场 point-in-time）</label>
          <input v-model="scanDate" type="date" class="date-input" />
        </div>
        <div class="field-group">
          <label>市场</label>
          <div class="market-checks">
            <label class="check-item"
              ><input type="checkbox" v-model="scanMarkets.SH" /> 沪 SH</label
            >
            <label class="check-item"
              ><input type="checkbox" v-model="scanMarkets.SZ" /> 深 SZ</label
            >
          </div>
        </div>
        <div class="field-group">
          <label>股票类型</label>
          <select v-model="scanStockType" class="market-select">
            <option value="all">全部</option>
            <option value="tree">🌳 树型</option>
            <option value="grain">🌾 粮型</option>
            <option value="vegetable">🥬 菜型</option>
          </select>
        </div>
        <div class="field-group num-group">
          <label>返回 Top N</label>
          <input v-model.number="scanTopN" type="number" min="1" max="200" class="num-input" />
        </div>
        <div class="field-group num-group">
          <label>最低分类分</label>
          <input v-model.number="scanMinScore" type="number" min="0" max="100" class="num-input" />
        </div>
        <div class="field-group sina-pool-group">
          <label>新浪补充自选池（可选，gpcw 未覆盖的更早历史时点用）</label>
          <textarea
            v-model="scanSinaPool"
            class="pool-input"
            rows="2"
            placeholder="600519&#10;000858&#10;..."
          />
        </div>
        <label class="check-item perf-check"
          ><input type="checkbox" v-model="scanWithPerf" /> 附带后续表现</label
        >
        <button class="primary scan-btn" :disabled="scanLoading" @click="runScan">
          {{ scanLoading ? '扫描中（全市场财报 + 树粮菜打分）…' : '🔭 运行全市场扫描' }}
        </button>
      </template>

      <div class="field-group pool-group" v-if="mode !== 'scan'">
        <label>自选池（每行一个 6 位代码，留空用默认池）</label>
        <textarea
          v-model="poolText"
          class="pool-input"
          rows="3"
          placeholder="600519&#10;000858&#10;..."
        />
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="error-banner">⚠ {{ error }}</div>
    <div v-if="verifyError" class="error-banner">⚠ {{ verifyError }}</div>
    <div v-if="scanError" class="error-banner">⚠ {{ scanError }}</div>

    <!-- ── 单日选股结果 ─────────────────────────────────────────────── -->
    <template v-if="mode === 'screen' && result">
      <div v-if="result.season" class="season-card" :style="{ borderColor: result.season.color }">
        <div class="season-left">
          <div class="season-title" :style="{ color: result.season.color }">
            📅 当时四季：{{ result.season.label }}
          </div>
          <div class="season-desc">{{ result.season.description }}</div>
        </div>
        <div class="season-right">
          <div class="season-row"><span>策略</span>{{ result.season.strategy }}</div>
          <div class="season-row"><span>操作</span>{{ result.season.action }}</div>
          <div class="season-row">
            <span>仓位</span>{{ result.season.position_range[0] }}% ~
            {{ result.season.position_range[1] }}%
          </div>
          <div class="season-row" v-if="result.season.signals">
            <span>信号分</span>{{ result.season.signals.total_score }}（{{
              result.season.signals.trend_60d_pct ?? 0
            }}% / 60日）
          </div>
        </div>
      </div>

      <div class="stats-bar">
        <div class="stat-item">
          <span class="stat-label">入选</span><span class="stat-value">{{ stats.total }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">🌳 树</span
          ><span class="stat-value" style="color: #22c55e">{{ stats.tree }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">🌾 粮</span
          ><span class="stat-value" style="color: #f59e0b">{{ stats.grain }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">🥬 菜</span
          ><span class="stat-value" style="color: #ef4444">{{ stats.vegetable }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">数据口径</span
          ><span class="stat-value" style="font-size: 13px">披露日 ≤ {{ result.date }}</span>
        </div>
      </div>

      <div class="result-table-wrap">
        <table class="result-table">
          <thead>
            <tr>
              <th>代码</th>
              <th>分类</th>
              <th>报告期</th>
              <th>年化营收</th>
              <th>年化EPS</th>
              <th>每股净资产</th>
              <th>ROE%</th>
              <th>毛利率%</th>
              <th>净利率%</th>
              <th>负债率%</th>
              <th>营收同比%</th>
              <th>净利同比%</th>
              <th>每股现金流</th>
              <th>PE</th>
              <th>PB</th>
              <th>+20日%</th>
              <th>+60日%</th>
              <th>+250日%</th>
              <th>明细</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in result.results" :key="r.market + r.code">
              <td class="code-cell">{{ r.market }}.{{ r.code }}</td>
              <td>
                <span
                  class="cat-badge"
                  :style="{
                    color: CATEGORY_COLORS[r.category],
                    background: CATEGORY_COLORS[r.category] + '22',
                  }"
                >
                  {{ r.label }}
                </span>
              </td>
              <td>{{ r.report_date }}</td>
              <td>{{ fmtYi(r.indicators.revenue_annualized) }}</td>
              <td>{{ fmt(r.indicators.eps_annualized) }}</td>
              <td>{{ fmt(r.indicators.bps) }}</td>
              <td>{{ fmt(r.indicators.roe_annualized) }}</td>
              <td>{{ fmt(r.indicators.gross_margin) }}</td>
              <td>{{ fmt(r.indicators.net_margin) }}</td>
              <td>{{ fmt(r.indicators.debt_ratio) }}</td>
              <td :style="{ color: colorBy(r.indicators.rev_yoy) }">
                {{ fmt(r.indicators.rev_yoy) }}
              </td>
              <td :style="{ color: colorBy(r.indicators.np_yoy) }">
                {{ fmt(r.indicators.np_yoy) }}
              </td>
              <td>{{ fmt(r.indicators.ocf_ps) }}</td>
              <td>{{ fmtVal(r.valuation?.pe) }}</td>
              <td>{{ fmtVal(r.valuation?.pb) }}</td>
              <td :style="{ color: colorBy(r.performance.ret_20d) }">
                {{ fmt(r.performance.ret_20d) }}
              </td>
              <td :style="{ color: colorBy(r.performance.ret_60d) }">
                {{ fmt(r.performance.ret_60d) }}
              </td>
              <td :style="{ color: colorBy(r.performance.ret_250d) }">
                {{ fmt(r.performance.ret_250d) }}
              </td>
              <td>
                <details class="score-details">
                  <summary>
                    🌳{{ Math.round(r.scores.tree) }} / 🌾{{ Math.round(r.scores.grain) }} / 🥬{{
                      Math.round(r.scores.vegetable)
                    }}
                  </summary>
                  <div v-for="(ds, cat) in r.details" :key="cat" class="score-block">
                    <div class="score-cat" :style="{ color: CATEGORY_COLORS[cat] }">
                      {{ CATEGORY_LABELS[cat] }} {{ Math.round(r.scores[cat]) }}分
                    </div>
                    <ul>
                      <li v-for="d in ds" :key="d.name">{{ d.reason }}</li>
                    </ul>
                  </div>
                </details>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="result.results.length === 0" class="empty-state">
        <p>该股票类型在目标日期无入选标的</p>
        <p class="hint">尝试切换日期、股票类型或扩大自选池</p>
      </div>
    </template>

    <!-- ── 批量时点验证结果 ─────────────────────────────────────────── -->
    <template v-if="mode === 'verify' && verifyResult">
      <div class="verify-head">
        <h3>
          📈 长赢理论批量时点验证（{{ verifyPeriods.length }} 个历史时点 × 自选池
          {{ pool.length }} 只）
        </h3>
        <p class="hint">
          口径：每个时点用「披露日 ≤ 该日」的财报选股，回看标的自该日起 20/60/250
          个交易日的实际涨跌，并与同期上证指数对比。
        </p>
      </div>

      <!-- 是否跑赢基准 -->
      <div class="beats-card" v-if="verifySummary?.beats_index">
        <div class="beats-title">🎯 长赢选股 vs 上证指数（同期）</div>
        <div class="beats-grid">
          <div class="beats-item" v-for="h in ['ret_20d', 'ret_60d', 'ret_250d']" :key="h">
            <span class="beats-label">{{ h.replace('ret_', '+').replace('d', '日') }}</span>
            <span
              class="beats-alpha"
              :style="{
                color: (verifySummary.beats_index[h].alpha ?? 0) >= 0 ? '#22c55e' : '#ef4444',
              }"
            >
              α {{ fmt(verifySummary.beats_index[h].alpha) }}%
            </span>
            <span class="beats-badge" :class="verifySummary.beats_index[h].beats ? 'win' : 'lose'">
              {{ verifySummary.beats_index[h].beats ? '跑赢' : '跑输' }}
            </span>
          </div>
        </div>
      </div>

      <!-- 汇总表：按分类 -->
      <div class="result-table-wrap">
        <table class="result-table verify-table">
          <thead>
            <tr>
              <th>口径</th>
              <th>样本数</th>
              <th>+20日 平均%</th>
              <th>+20日 命中率</th>
              <th>+60日 平均%</th>
              <th>+60日 命中率</th>
              <th>+250日 平均%</th>
              <th>+250日 命中率</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="cat in ['tree', 'grain', 'vegetable']" :key="cat">
              <td>
                <span
                  class="cat-badge"
                  :style="{ color: CATEGORY_COLORS[cat], background: CATEGORY_COLORS[cat] + '22' }"
                >
                  {{ CATEGORY_LABELS[cat] }}
                </span>
              </td>
              <td>{{ verifySummary.by_category[cat].count }}</td>
              <td :style="{ color: colorBy(verifySummary.by_category[cat].ret_20d.avg) }">
                {{ fmt(verifySummary.by_category[cat].ret_20d.avg) }}
              </td>
              <td>{{ pct(verifySummary.by_category[cat].ret_20d.hit_rate) }}</td>
              <td :style="{ color: colorBy(verifySummary.by_category[cat].ret_60d.avg) }">
                {{ fmt(verifySummary.by_category[cat].ret_60d.avg) }}
              </td>
              <td>{{ pct(verifySummary.by_category[cat].ret_60d.hit_rate) }}</td>
              <td :style="{ color: colorBy(verifySummary.by_category[cat].ret_250d.avg) }">
                {{ fmt(verifySummary.by_category[cat].ret_250d.avg) }}
              </td>
              <td>{{ pct(verifySummary.by_category[cat].ret_250d.hit_rate) }}</td>
            </tr>
            <tr class="overall-row">
              <td>📊 总体（长赢选股）</td>
              <td>{{ verifySummary.overall.count }}</td>
              <td :style="{ color: colorBy(verifySummary.overall.ret_20d.avg) }">
                {{ fmt(verifySummary.overall.ret_20d.avg) }}
              </td>
              <td>{{ pct(verifySummary.overall.ret_20d.hit_rate) }}</td>
              <td :style="{ color: colorBy(verifySummary.overall.ret_60d.avg) }">
                {{ fmt(verifySummary.overall.ret_60d.avg) }}
              </td>
              <td>{{ pct(verifySummary.overall.ret_60d.hit_rate) }}</td>
              <td :style="{ color: colorBy(verifySummary.overall.ret_250d.avg) }">
                {{ fmt(verifySummary.overall.ret_250d.avg) }}
              </td>
              <td>{{ pct(verifySummary.overall.ret_250d.hit_rate) }}</td>
            </tr>
            <tr class="index-row">
              <td>📉 上证指数（同期基准）</td>
              <td>{{ verifySummary.index.ret_20d.count }}</td>
              <td>{{ fmt(verifySummary.index.ret_20d.avg) }}</td>
              <td>-</td>
              <td>{{ fmt(verifySummary.index.ret_60d.avg) }}</td>
              <td>-</td>
              <td>{{ fmt(verifySummary.index.ret_250d.avg) }}</td>
              <td>-</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 各时点明细 -->
      <div class="verify-periods">
        <div v-for="p in verifyPeriods" :key="p.date" class="period-card">
          <div class="period-head">
            <span class="period-date">📅 {{ p.date }}</span>
            <span v-if="p.season" class="period-season" :style="{ color: p.season.color }">{{
              p.season.label
            }}</span>
            <span class="period-idx" v-if="p.index">
              上证指数 +20日 {{ fmt(p.index.ret_20d) }}% / +60日 {{ fmt(p.index.ret_60d) }}% /
              +250日 {{ fmt(p.index.ret_250d) }}%
            </span>
          </div>
          <table class="result-table period-table">
            <thead>
              <tr>
                <th>代码</th>
                <th>分类</th>
                <th>报告期</th>
                <th>+20日%</th>
                <th>+60日%</th>
                <th>+250日%</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="r in p.results" :key="p.date + r.market + r.code">
                <td class="code-cell">{{ r.market }}.{{ r.code }}</td>
                <td>
                  <span
                    class="cat-badge"
                    :style="{
                      color: CATEGORY_COLORS[r.category],
                      background: CATEGORY_COLORS[r.category] + '22',
                    }"
                  >
                    {{ r.label }}
                  </span>
                </td>
                <td>{{ r.report_date }}</td>
                <td>{{ fmtYi(r.indicators.revenue_annualized) }}</td>
                <td :style="{ color: colorBy(r.performance.ret_20d) }">
                  {{ fmt(r.performance.ret_20d) }}
                </td>
                <td :style="{ color: colorBy(r.performance.ret_60d) }">
                  {{ fmt(r.performance.ret_60d) }}
                </td>
                <td :style="{ color: colorBy(r.performance.ret_250d) }">
                  {{ fmt(r.performance.ret_250d) }}
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="p.results.length === 0" class="empty-state">
            <p>该时点无入选标的（财报披露覆盖不足）</p>
          </div>
        </div>
      </div>
    </template>

    <!-- ── 全市场扫描结果 ─────────────────────────────────────────── -->
    <template v-if="mode === 'scan' && scanResult">
      <div v-if="scanResult.warning" class="warning-banner">⚠ {{ scanResult.warning }}</div>
      <div
        v-if="scanResult.season"
        class="season-card"
        :style="{ borderColor: scanResult.season.color }"
      >
        <div class="season-left">
          <div class="season-title" :style="{ color: scanResult.season.color }">
            📅 当时四季：{{ scanResult.season.label }}
          </div>
          <div class="season-desc">{{ scanResult.season.description }}</div>
        </div>
        <div class="season-right">
          <div class="season-row"><span>策略</span>{{ scanResult.season.strategy }}</div>
          <div class="season-row"><span>操作</span>{{ scanResult.season.action }}</div>
          <div class="season-row">
            <span>仓位</span>{{ scanResult.season.position_range[0] }}% ~
            {{ scanResult.season.position_range[1] }}%
          </div>
          <div class="season-row" v-if="scanResult.season.signals">
            <span>信号分</span>{{ scanResult.season.signals.total_score }}（{{
              scanResult.season.signals.trend_60d_pct ?? 0
            }}% / 60日）
          </div>
        </div>
      </div>

      <div class="stats-bar">
        <div class="stat-item">
          <span class="stat-label">全市场扫描</span
          ><span class="stat-value">{{ scanStats.total }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">🌳 树</span
          ><span class="stat-value" style="color: #22c55e">{{ scanStats.tree }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">🌾 粮</span
          ><span class="stat-value" style="color: #f59e0b">{{ scanStats.grain }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">🥬 菜</span
          ><span class="stat-value" style="color: #ef4444">{{ scanStats.vegetable }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">返回 Top</span
          ><span class="stat-value">{{ scanStats.returned }}</span>
        </div>
        <div class="stat-item" v-if="scanStats.truncated">
          <span class="stat-label">截断</span
          ><span class="stat-value" style="color: #f59e0b">+{{ scanStats.truncated }}</span>
        </div>
        <div class="stat-item">
          <span class="stat-label">数据口径</span
          ><span class="stat-value" style="font-size: 13px">披露日 ≤ {{ scanResult.date }}</span>
        </div>
        <div class="stat-item" v-if="scanResult.cache">
          <span class="stat-label">财报缓存</span
          ><span class="stat-value" style="font-size: 13px; color: #22c55e"
            >💾 {{ scanResult.cache.zips_count }} 期 /
            {{ (scanResult.cache.db_bytes / 1048576).toFixed(1) }}MB</span
          >
        </div>
      </div>

      <div class="result-table-wrap">
        <table class="result-table scan-table">
          <thead>
            <tr>
              <th>代码</th>
              <th>分类</th>
              <th>得分</th>
              <th>数据源</th>
              <th>报告期</th>
              <th>年化营收</th>
              <th>年化EPS</th>
              <th>每股净资产</th>
              <th>ROE%</th>
              <th>毛利率%</th>
              <th>净利率%</th>
              <th>负债率%</th>
              <th>营收同比%</th>
              <th>净利同比%</th>
              <th>每股现金流</th>
              <th v-if="scanWithPerf">PE</th>
              <th v-if="scanWithPerf">PB</th>
              <th v-if="scanWithPerf">+20日%</th>
              <th v-if="scanWithPerf">+60日%</th>
              <th v-if="scanWithPerf">+250日%</th>
              <th>明细</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in scanResult.results" :key="r.market + r.code">
              <td class="code-cell">{{ r.market }}.{{ r.code }}</td>
              <td>
                <span
                  class="cat-badge"
                  :style="{
                    color: CATEGORY_COLORS[r.category],
                    background: CATEGORY_COLORS[r.category] + '22',
                  }"
                >
                  {{ r.label }}
                </span>
              </td>
              <td class="score-cell">{{ fmt(r.score) }}</td>
              <td>
                <span class="ds-badge" :class="r.data_source === 'sina' ? 'sina' : 'gpcw'">{{
                  r.data_source === 'sina' ? '新浪' : 'gpcw'
                }}</span>
              </td>
              <td>{{ r.report_date }}</td>
              <td>{{ fmtYi(r.indicators.revenue_annualized) }}</td>
              <td>{{ fmt(r.indicators.eps_annualized) }}</td>
              <td>{{ fmt(r.indicators.bps) }}</td>
              <td>{{ fmt(r.indicators.roe_annualized) }}</td>
              <td>{{ fmt(r.indicators.gross_margin) }}</td>
              <td>{{ fmt(r.indicators.net_margin) }}</td>
              <td>{{ fmt(r.indicators.debt_ratio) }}</td>
              <td :style="{ color: colorBy(r.indicators.rev_yoy) }">
                {{ fmt(r.indicators.rev_yoy) }}
              </td>
              <td :style="{ color: colorBy(r.indicators.np_yoy) }">
                {{ fmt(r.indicators.np_yoy) }}
              </td>
              <td>{{ fmt(r.indicators.ocf_ps) }}</td>
              <td v-if="scanWithPerf">{{ fmtVal(r.valuation?.pe) }}</td>
              <td v-if="scanWithPerf">{{ fmtVal(r.valuation?.pb) }}</td>
              <td v-if="scanWithPerf" :style="{ color: colorBy(r.performance?.ret_20d) }">
                {{ fmt(r.performance?.ret_20d) }}
              </td>
              <td v-if="scanWithPerf" :style="{ color: colorBy(r.performance?.ret_60d) }">
                {{ fmt(r.performance?.ret_60d) }}
              </td>
              <td v-if="scanWithPerf" :style="{ color: colorBy(r.performance?.ret_250d) }">
                {{ fmt(r.performance?.ret_250d) }}
              </td>
              <td>
                <details class="score-details">
                  <summary>
                    🌳{{ Math.round(r.scores.tree) }} / 🌾{{ Math.round(r.scores.grain) }} / 🥬{{
                      Math.round(r.scores.vegetable)
                    }}
                  </summary>
                  <div v-for="(ds, cat) in r.details" :key="cat" class="score-block">
                    <div class="score-cat" :style="{ color: CATEGORY_COLORS[cat] }">
                      {{ CATEGORY_LABELS[cat] }} {{ Math.round(r.scores[cat]) }}分
                    </div>
                    <ul>
                      <li v-for="d in ds" :key="d.name">{{ d.reason }}</li>
                    </ul>
                  </div>
                </details>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="scanResult.results.length === 0" class="empty-state">
        <p>该日期/条件下无入选标的</p>
        <p class="hint">尝试切换日期、降低最低分类分或扩大市场范围</p>
      </div>
    </template>

    <div v-else-if="!loading && !verifyLoading && !scanLoading" class="intro">
      <h3>📊 长赢基本面选股（P1/P2）</h3>
      <p>
        选一个历史日期，用<b>截至当天已披露</b>的 gpcw
        财报，对自选池（或全市场）做树粮菜量化打分，并回看标的自该日起的实际走势。
      </p>
      <p class="hint">
        「批量时点验证」跨多个历史日期汇总命中率并与上证指数对比；「全市场扫描」对全市场逐只打分返回
        Top N。
      </p>
    </div>
  </div>
</template>

<style scoped>
.fundamental-view {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px 20px;
  height: 100%;
  overflow-y: auto;
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
.mode-tabs {
  display: flex;
  gap: 6px;
}
.mode-tab {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 12px;
  font-size: 13px;
  color: var(--text-muted);
  cursor: pointer;
}
.mode-tab.active {
  background: var(--primary, #2563eb);
  color: #fff;
  border-color: transparent;
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
.date-input,
.market-select {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 10px;
  font-size: 13px;
  color: var(--text);
}
.date-input {
  width: 140px;
}
.market-select {
  width: 130px;
}
.pool-group {
  flex: 1;
  min-width: 200px;
}
.dates-group {
  min-width: 220px;
}
.pool-input {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 10px;
  font-size: 12px;
  color: var(--text);
  width: 100%;
  resize: vertical;
  font-family: monospace;
}
.scan-btn {
  padding: 7px 18px;
  font-size: 13px;
  height: auto;
}
.error-banner {
  background: rgba(239, 65, 70, 0.12);
  border: 1px solid var(--up);
  color: var(--up);
  padding: 10px 14px;
  border-radius: var(--radius);
  font-size: 13px;
}
.season-card {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-left-width: 4px;
  border-radius: var(--radius);
  padding: 12px 16px;
}
.season-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.season-title {
  font-size: 16px;
  font-weight: 600;
}
.season-desc {
  font-size: 12px;
  color: var(--text-muted);
  max-width: 420px;
}
.season-right {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12px;
}
.season-row span {
  color: var(--text-dim);
  margin-right: 8px;
}
.stats-bar {
  display: flex;
  gap: 24px;
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
.verify-head {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.verify-head h3 {
  margin: 0;
  font-size: 16px;
  color: var(--text);
}
.beats-card {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-left-width: 4px;
  border-left-color: #f59e0b;
  border-radius: var(--radius);
  padding: 12px 16px;
}
.beats-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 8px;
}
.beats-grid {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
}
.beats-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.beats-label {
  font-size: 11px;
  color: var(--text-dim);
}
.beats-alpha {
  font-size: 16px;
  font-weight: 700;
}
.beats-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  width: fit-content;
}
.beats-badge.win {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}
.beats-badge.lose {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}
.result-table-wrap {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: auto;
}
.result-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  min-width: 1100px;
}
.result-table th,
.result-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  text-align: right;
  white-space: nowrap;
}
.result-table th {
  color: var(--text-dim);
  font-weight: 500;
  text-align: right;
}
.result-table th:first-child,
.result-table td:first-child {
  text-align: left;
}
.result-table tbody tr:hover {
  background: rgba(255, 255, 255, 0.03);
}
.overall-row td {
  font-weight: 700;
  background: rgba(37, 99, 235, 0.06);
}
.index-row td {
  color: var(--text-muted);
}
.code-cell {
  font-family: monospace;
  font-weight: 600;
}
.cat-badge {
  padding: 2px 8px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}
.score-details summary {
  cursor: pointer;
  font-size: 12px;
}
.score-block {
  margin: 6px 0 2px 4px;
  text-align: left;
}
.score-cat {
  font-weight: 600;
  font-size: 12px;
  margin-bottom: 2px;
}
.score-block ul {
  margin: 0;
  padding-left: 16px;
  color: var(--text-muted);
  font-size: 11px;
}
.verify-periods {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.period-card {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.period-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.period-date {
  font-weight: 700;
  color: var(--text);
}
.period-season {
  font-weight: 600;
}
.period-idx {
  margin-left: auto;
  color: var(--text-muted);
  font-size: 12px;
}
.period-table {
  min-width: 0;
}
.period-table th:first-child,
.period-table td:first-child {
  text-align: left;
}
.empty-state {
  text-align: center;
  color: var(--text-muted);
  padding: 30px;
}
.intro {
  text-align: center;
  color: var(--text-muted);
  padding: 40px 20px;
  line-height: 1.8;
}
.intro h3 {
  color: var(--text);
}
.hint {
  font-size: 12px;
  color: var(--text-dim);
}
.market-checks {
  display: flex;
  gap: 10px;
}
.check-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text);
  cursor: pointer;
}
.perf-check {
  align-self: center;
  margin-bottom: 8px;
  white-space: nowrap;
}
.num-group {
  width: 110px;
}
.num-input {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 10px;
  font-size: 13px;
  color: var(--text);
  width: 100%;
}
.warning-banner {
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid #f59e0b;
  color: #f59e0b;
  padding: 10px 14px;
  border-radius: var(--radius);
  font-size: 13px;
}
.score-cell {
  font-weight: 700;
  color: var(--text);
}
.scan-table {
  min-width: 1100px;
}
.sina-pool-group {
  min-width: 180px;
}
.ds-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
}
.ds-badge.gpcw {
  background: rgba(37, 99, 235, 0.15);
  color: #60a5fa;
}
.ds-badge.sina {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}
</style>
