<script setup lang="ts">
// V722: 模型准确性审计页 —— 只读展示服务端落盘的真实审计报告。
// 数据全部来自 easy_tdx.audit.accuracy 真实计算（不伪造），含长盈三维
// 分层前瞻收益、缠论买卖点台账命中率、图表一致性对账。

import { onMounted, ref, computed } from 'vue'
import { formatError } from '../api'

interface StatSlot {
  n: number
  p50: number | null
  win_rate: number | null
}
interface IndexSlot {
  as_of_close?: number
  ret_20d?: number | null
  ret_60d?: number | null
  ret_250d?: number | null
}
interface AuditReport {
  generated_at?: string
  bases?: string[]
  marks?: { count: number; trade_date: string; by_category?: Record<string, number>; age_days?: number; stale?: boolean }
  changying?: {
    per_class?: Record<string, Record<string, StatSlot>>
    per_symbol?: Array<{ symbol: string; category: string; data_missing?: boolean; pit_ok?: boolean; performance?: Record<string, IndexSlot & Record<string, unknown>> }>
    index?: Record<string, IndexSlot>
    caveat?: string
  }
  chanlun?: {
    note?: string
    sample_size?: number
    signal_count?: number
    by_type?: Record<string, { signals: number; hit_rate: number; avg_return: number }>
  }
  chart_consistency?: { checked: number; mismatches: unknown[] }
}

const report = ref<AuditReport | null>(null)
const loading = ref(false)
const error = ref('')


const CAT_META: Record<string, { label: string; cls: string }> = {
  tree: { label: '🌳 树', cls: 'cat-tree' },
  grain: { label: '🌾 粮', cls: 'cat-grain' },
  vegetable: { label: '🥬 菜', cls: 'cat-veg' },
}
const HORIZONS = ['ret_20d', 'ret_60d', 'ret_250d'] as const
const HORIZON_LABEL: Record<string, string> = {
  ret_20d: '20 日',
  ret_60d: '60 日',
  ret_250d: '250 日',
}

async function load(date?: string) {
  loading.value = true
  error.value = ''
  try {
    const url = date ? `/api/v1/audit/accuracy?date=${date}` : '/api/v1/audit/accuracy'
    const resp = await fetch(url)
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}))
      throw new Error((body as { detail?: string }).detail ?? `HTTP ${resp.status}`)
    }
    report.value = (await resp.json()) as AuditReport
  } catch (e) {
    error.value = formatError(e)
    report.value = null
  } finally {
    loading.value = false
  }
}

const classRows = computed(() => {
  const perClass = report.value?.changying?.per_class ?? {}
  const rows: Array<{
    category: string
    label: string
    cls: string
    samples: number
    cells: Array<{ horizon: string; n: number; p50: number | null; win: number | null }>
  }> = []
  for (const [cat, basesMap] of Object.entries(perClass)) {
    const meta = CAT_META[cat] ?? { label: cat, cls: 'cat-veg' }
    const samples = (basesMap as Record<string, unknown>).samples as number ?? 0
    const bases = report.value?.bases ?? []
    // 逐基期取 ret_* 主口径（超额口径用 title 提示）
    const cells = HORIZONS.map((h) => {
      let n = 0
      let p50: number | null = null
      let win: number | null = null
      // 取最新一个有数据的基期
      for (const b of bases) {
        const slot = (
          basesMap as Record<string, Partial<Record<(typeof HORIZONS)[number], StatSlot>>>
        )[b]?.[h]
        if (slot && slot.n > 0 && slot.p50 !== null) {
          n = slot.n
          p50 = slot.p50
          win = slot.win_rate
          break
        }
      }
      return { horizon: h, n, p50, win }
    })
    rows.push({ category: cat, label: meta.label, cls: meta.cls, samples, cells })
  }
  return rows
})

const chanlunRows = computed(() => {
  const byType = report.value?.chanlun?.by_type ?? {}
  return Object.entries(byType)
    .map(([t, s]) => ({ type: t, ...s }))
    .sort((a, b) => b.signals - a.signals)
})

const pitViolations = computed(() => {
  const per = report.value?.changying?.per_symbol ?? []
  return per.filter((p) => p.pit_ok === false).length
})

const missingCount = computed(() => {
  const per = report.value?.changying?.per_symbol ?? []
  return per.filter((p) => p.data_missing).length
})

onMounted(() => load())
</script>

<template>
  <div class="audit-view">
    <header class="audit-header">
      <h2>模型准确性审计</h2>
      <p class="audit-sub">
        长盈选股（树/粮/菜）前瞻收益 + 缠论买卖点台账命中率 + 图表一致性对账 —— 全部真实历史数据计算，缺失即诚实标注。
        <button class="btn btn-secondary" style="margin-left: 12px" :disabled="loading" @click="load()">刷新</button>
      </p>
    </header>

    <div v-if="loading" class="audit-loading">加载审计报告…</div>
    <div v-else-if="error" class="audit-error">{{ error }}</div>

    <template v-else-if="report">
      <!-- 总览卡片 -->
      <section class="audit-cards">
        <div class="audit-card">
          <div class="card-num">{{ report.marks?.count ?? '—' }}</div>
          <div class="card-label">标记标的数（{{ report.marks?.trade_date ?? '' }}<span v-if="report.marks?.stale" class="stale-badge">已过期 {{ report.marks?.age_days }} 天</span>）</div>
        </div>
        <div class="audit-card">
          <div class="card-num">{{ report.chanlun?.signal_count ?? '—' }}</div>
          <div class="card-label">缠论信号（{{ report.chanlun?.sample_size ?? '—' }} 只样本）</div>
        </div>
        <div class="audit-card">
          <div class="card-num">{{ report.chart_consistency?.checked ?? '—' }}</div>
          <div class="card-label">图表对账 checked / {{ report.chart_consistency?.mismatches?.length ?? 0 }} 不一致</div>
        </div>
        <div class="audit-card">
          <div class="card-num" :class="{ 'num-bad': pitViolations > 0 }">{{ pitViolations }}</div>
          <div class="card-label">PIT 违规（未来函数）</div>
        </div>
        <div class="audit-card">
          <div class="card-num" :class="{ 'num-warn': missingCount > 0 }">{{ missingCount }}</div>
          <div class="card-label">数据缺失标的（诚实缺失，不伪造）</div>
        </div>
      </section>

      <!-- 长盈三维分层 -->
      <section class="audit-section">
        <h3>长盈选股 · 前瞻收益（按分类 × 基期）</h3>
        <table class="audit-table">
          <thead>
            <tr>
              <th>分类</th>
              <th>样本</th>
              <th v-for="h in HORIZONS" :key="h">{{ HORIZON_LABEL[h] }} p50（胜率）</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in classRows" :key="row.category">
              <td><span class="cat-badge" :class="row.cls">{{ row.label }}</span></td>
              <td>{{ row.samples }}</td>
              <td v-for="cell in row.cells" :key="cell.horizon">
                <template v-if="cell.p50 === null"><span class="muted">基期前瞻不足</span></template>
                <template v-else>
                  <span :class="cell.p50 >= 0 ? 'pos' : 'neg'">{{ cell.p50.toFixed(2) }}%</span>
                  <span class="muted">（{{ ((cell.win ?? 0) * 100).toFixed(0) }}%）</span>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
        <p class="audit-note">取最新有数据的基期；250 日窗口仅在最早基期可算属正常诚实缺失。对比基准与分基期全表见落盘报告。</p>
      </section>

      <!-- 缠论台账 -->
      <section class="audit-section">
        <h3>缠论买卖点 · 信号台账命中率</h3>
        <p class="audit-note">{{ report.chanlun?.note }}</p>
        <table class="audit-table">
          <thead>
            <tr><th>信号类型</th><th>信号数</th><th>命中率</th><th>平均收益（方向对齐）</th></tr>
          </thead>
          <tbody>
            <tr v-for="r in chanlunRows" :key="r.type">
              <td>{{ r.type }}</td>
              <td>{{ r.signals }}</td>
              <td :class="(r.hit_rate ?? 0) >= 0.6 ? 'pos' : 'neg'">{{ ((r.hit_rate ?? 0) * 100).toFixed(1) }}%</td>
              <td :class="(r.avg_return ?? 0) >= 0 ? 'pos' : 'neg'">{{ (r.avg_return ?? 0).toFixed(2) }}%</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- 诚实性脚注 -->
      <section class="audit-section">
        <h3>口径与诚实性说明</h3>
        <ul class="audit-caveats">
          <li v-if="report.changying?.caveat">{{ report.changying.caveat }}</li>
          <li>前瞻收益 = 基期收盘 → N 日后收盘（真实历史行情，零基价记 -100%）；前瞻窗口不足时标注「基期前瞻不足」，不做外推。</li>
          <li>缠论信号口径与信号精度面板共用 signal_ledger 统一台账（方向对齐），数字必须对得上。</li>
          <li v-if="report.generated_at">报告生成时间：{{ report.generated_at }}（服务端 easy_tdx audit-accuracy 真实运行产物）。</li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.audit-view { padding: 16px 20px; max-width: 1080px; margin: 0 auto; }
.audit-header h2 { margin: 8px 0 4px; }
.audit-sub { color: #8a93a6; font-size: 13px; margin: 0 0 16px; }
.audit-loading, .audit-error { padding: 40px; text-align: center; color: #8a93a6; }
.audit-error { color: #e05555; }
.audit-cards { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
.audit-card { flex: 1; min-width: 150px; background: var(--bg-elev, #1a1f2b); border: 1px solid var(--border, #2a3040); border-radius: 8px; padding: 14px 16px; }
.card-num { font-size: 26px; font-weight: 700; }
.card-num.num-bad { color: #e05555; }
.card-num.num-warn { color: #e0a832; }
.card-label { font-size: 12px; color: #8a93a6; margin-top: 4px; }
.stale-badge { color: #e0a832; margin-left: 6px; font-size: 11px; }
.audit-section { margin-bottom: 24px; }
.audit-section h3 { font-size: 15px; margin: 0 0 8px; }
.audit-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.audit-table th, .audit-table td { border: 1px solid var(--border, #2a3040); padding: 6px 10px; text-align: left; }
.audit-table th { background: var(--bg-elev, #1a1f2b); color: #aeb7c9; font-weight: 600; }
.cat-badge { font-weight: 600; }
.cat-tree { color: #4caf7d; }
.cat-grain { color: #d4a94e; }
.cat-veg { color: #7da7d4; }
.pos { color: #4caf7d; }
.neg { color: #e05555; }
.muted { color: #6b7385; font-size: 12px; }
.audit-note { color: #6b7385; font-size: 12px; margin: 6px 0 10px; }
.audit-caveats { color: #8a93a6; font-size: 12.5px; line-height: 1.7; padding-left: 18px; }
</style>
