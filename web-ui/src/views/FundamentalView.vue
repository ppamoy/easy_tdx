<!-- P1 长赢基本面选股：历史时点 + 树粮菜量化打分 + 后续表现 + 四季判断 -->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { formatError } from '../api'

const selectDate = ref('')
const poolText = ref('')
const stockType = ref<'all' | 'tree' | 'grain' | 'vegetable'>('all')
const loading = ref(false)
const error = ref('')
const result = ref<any>(null)

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

onMounted(() => {
  const now = new Date()
  const d = new Date(now.getFullYear(), now.getMonth() - 2, 15)
  selectDate.value = d.toISOString().slice(0, 10)
  poolText.value = DEFAULT_POOL.map((p) => p.code).join('\n')
})
</script>

<template>
  <div class="fundamental-view">
    <div class="config-bar">
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
      <div class="field-group pool-group">
        <label>自选池（每行一个 6 位代码，留空用默认池）</label>
        <textarea v-model="poolText" class="pool-input" rows="3" placeholder="600519&#10;000858&#10;..." />
      </div>
      <button class="primary scan-btn" :disabled="loading" @click="runScreen">
        {{ loading ? '选股中（加载 gpcw 财报 + 计算指标）…' : '🚀 开始历史时点选股' }}
      </button>
    </div>

    <div v-if="error" class="error-banner">⚠ {{ error }}</div>

    <template v-if="result">
      <div v-if="result.season" class="season-card" :style="{ borderColor: result.season.color }">
        <div class="season-left">
          <div class="season-title" :style="{ color: result.season.color }">📅 当时四季：{{ result.season.label }}</div>
          <div class="season-desc">{{ result.season.description }}</div>
        </div>
        <div class="season-right">
          <div class="season-row"><span>策略</span>{{ result.season.strategy }}</div>
          <div class="season-row"><span>操作</span>{{ result.season.action }}</div>
          <div class="season-row"><span>仓位</span>{{ result.season.position_range[0] }}% ~ {{ result.season.position_range[1] }}%</div>
          <div class="season-row" v-if="result.season.signals"><span>信号分</span>{{ result.season.signals.total_score }}（{{ result.season.signals.trend_60d_pct ?? 0 }}% / 60日）</div>
        </div>
      </div>

      <div class="stats-bar">
        <div class="stat-item"><span class="stat-label">入选</span><span class="stat-value">{{ stats.total }}</span></div>
        <div class="stat-item"><span class="stat-label">🌳 树</span><span class="stat-value" style="color:#22c55e">{{ stats.tree }}</span></div>
        <div class="stat-item"><span class="stat-label">🌾 粮</span><span class="stat-value" style="color:#f59e0b">{{ stats.grain }}</span></div>
        <div class="stat-item"><span class="stat-label">🥬 菜</span><span class="stat-value" style="color:#ef4444">{{ stats.vegetable }}</span></div>
        <div class="stat-item"><span class="stat-label">数据口径</span><span class="stat-value" style="font-size:13px">披露日 ≤ {{ result.date }}</span></div>
      </div>

      <div class="result-table-wrap">
        <table class="result-table">
          <thead>
            <tr>
              <th>代码</th>
              <th>分类</th>
              <th>报告期</th>
              <th>EPS</th>
              <th>ROE%</th>
              <th>毛利率%</th>
              <th>净利率%</th>
              <th>负债率%</th>
              <th>营收同比%</th>
              <th>净利同比%</th>
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
                <span class="cat-badge" :style="{ color: CATEGORY_COLORS[r.category], background: CATEGORY_COLORS[r.category] + '22' }">
                  {{ r.label }}
                </span>
              </td>
              <td>{{ r.report_date }}</td>
              <td>{{ fmt(r.indicators.eps) }}</td>
              <td>{{ fmt(r.indicators.roe) }}</td>
              <td>{{ fmt(r.indicators.gross_margin) }}</td>
              <td>{{ fmt(r.indicators.net_margin) }}</td>
              <td>{{ fmt(r.indicators.debt_ratio) }}</td>
              <td :style="{ color: (r.indicators.rev_yoy ?? 0) >= 0 ? '#22c55e' : '#ef4444' }">{{ fmt(r.indicators.rev_yoy) }}</td>
              <td :style="{ color: (r.indicators.np_yoy ?? 0) >= 0 ? '#22c55e' : '#ef4444' }">{{ fmt(r.indicators.np_yoy) }}</td>
              <td :style="{ color: (r.performance.ret_20d ?? 0) >= 0 ? '#22c55e' : '#ef4444' }">{{ fmt(r.performance.ret_20d) }}</td>
              <td :style="{ color: (r.performance.ret_60d ?? 0) >= 0 ? '#22c55e' : '#ef4444' }">{{ fmt(r.performance.ret_60d) }}</td>
              <td :style="{ color: (r.performance.ret_250d ?? 0) >= 0 ? '#22c55e' : '#ef4444' }">{{ fmt(r.performance.ret_250d) }}</td>
              <td>
                <details class="score-details">
                  <summary>🌳{{ Math.round(r.scores.tree) }} / 🌾{{ Math.round(r.scores.grain) }} / 🥬{{ Math.round(r.scores.vegetable) }}</summary>
                  <div v-for="(ds, cat) in r.details" :key="cat" class="score-block">
                    <div class="score-cat" :style="{ color: CATEGORY_COLORS[cat] }">{{ CATEGORY_LABELS[cat] }} {{ Math.round(r.scores[cat]) }}分</div>
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

    <div v-else-if="!loading" class="intro">
      <h3>📊 长赢基本面选股（P1）</h3>
      <p>选一个历史日期，用<b>截至当天已披露</b>的 gpcw 财报，对自选池做树粮菜量化打分，并回看标的自该日起的实际走势。</p>
      <p class="hint">数据口径：只使用披露日 ≤ 目标日期的财报（point-in-time，杜绝未来函数）。</p>
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
.field-group { display: flex; flex-direction: column; gap: 4px; }
.field-group label { font-size: 11px; color: var(--text-muted); }
.date-input, .market-select {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 10px;
  font-size: 13px;
  color: var(--text);
}
.date-input { width: 140px; }
.market-select { width: 130px; }
.pool-group { flex: 1; min-width: 200px; }
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
.scan-btn { padding: 7px 18px; font-size: 13px; height: auto; }
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
.season-left { display: flex; flex-direction: column; gap: 4px; }
.season-title { font-size: 16px; font-weight: 600; }
.season-desc { font-size: 12px; color: var(--text-muted); max-width: 420px; }
.season-right { display: flex; flex-direction: column; gap: 2px; font-size: 12px; }
.season-row span { color: var(--text-dim); margin-right: 8px; }
.stats-bar {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 16px;
}
.stat-item { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.stat-label { font-size: 11px; color: var(--text-dim); }
.stat-value { font-size: 18px; font-weight: 600; color: var(--text); }
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
.result-table th, .result-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  text-align: right;
  white-space: nowrap;
}
.result-table th { color: var(--text-dim); font-weight: 500; text-align: right; }
.result-table th:first-child, .result-table td:first-child { text-align: left; }
.result-table tbody tr:hover { background: rgba(255,255,255,0.03); }
.code-cell { font-family: monospace; font-weight: 600; }
.cat-badge {
  padding: 2px 8px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}
.score-details summary { cursor: pointer; font-size: 12px; }
.score-block { margin: 6px 0 2px 4px; text-align: left; }
.score-cat { font-weight: 600; font-size: 12px; margin-bottom: 2px; }
.score-block ul { margin: 0; padding-left: 16px; color: var(--text-muted); font-size: 11px; }
.empty-state { text-align: center; color: var(--text-muted); padding: 30px; }
.intro { text-align: center; color: var(--text-muted); padding: 40px 20px; line-height: 1.8; }
.intro h3 { color: var(--text); }
.hint { font-size: 12px; color: var(--text-dim); }
</style>
