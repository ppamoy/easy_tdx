<script setup lang="ts">
// 选股两步流（v590）：Step1 长盈基本面选股池 → Step2 缠论择时。
// V2：新增「缠论选股」标签页（结构驱动选股），与长盈选股并列。
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import BeginnerGuide from '../components/BeginnerGuide.vue'
import ChanlunChart from '../components/ChanlunChart.vue'
import {
  formatError,
  stockPickScreen,
  stockPickScreenAsync,
  stockPickScreenTask,
  stockPickTiming,
  chanlunScreen,
  type SeasonInfo,
  type StockPickPoolItem,
  type StockPickTimingResult,
  type ChanlunScreenResult,
} from '../api'
import { useEarlierBars } from '../composables/useEarlierBars'
import { useTimeJump } from '../composables/useTimeJump'
import type { Bar, Category } from '../types'
import { padMacdHead, shiftStructure } from '../utils/shiftStructure'

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

// V722: timing chart full-history backfill (load earlier; server count driven)
const {
  loading: earlierLoading,
  canLoad: earlierCanLoad,
  error: earlierError,
  fetchEarlier,
} = useEarlierBars({
  code: () => timingResult.value?.code ?? '',
  category: () => 'DAY' as Category,
  earliest: () => {
    const b = timingResult.value?.bars as Bar[] | undefined
    return b && b.length ? b[0].datetime.slice(0, 10) : ''
  },
  detectMarket: () => timingResult.value?.market ?? 'SZ',
})

async function loadEarlierTiming() {
  const earlier = await fetchEarlier()
  if (earlier.length && timingResult.value) {
    const shift = earlier.length
    const merged = [...earlier, ...((timingResult.value.bars as Bar[]) ?? [])]
    // V723: 本地扩窗不重跑分析，结构索引整体 +shift（含递归 levels）
    const levels: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(timingResult.value.levels ?? {})) {
      const lv = v as Record<string, unknown>
      levels[k] = {
        ...lv,
        bis: shiftStructure(lv.bis as any[], shift),
        xds: shiftStructure(lv.xds as any[], shift),
        zss: shiftStructure(lv.zss as any[], shift),
        mmds: shiftStructure(lv.mmds as any[], shift),
        bcs: shiftStructure(lv.bcs as any[], shift),
        zsds: shiftStructure(lv.zsds as any[], shift),
        qsds: shiftStructure(lv.qsds as any[], shift),
      }
    }
    timingResult.value = {
      ...timingResult.value,
      bars: merged,
      bis: shiftStructure(timingResult.value.bis as any[], shift),
      xds: shiftStructure(timingResult.value.xds as any[], shift),
      zss: shiftStructure(timingResult.value.zss as any[], shift),
      mmds: shiftStructure(timingResult.value.mmds as any[], shift),
      fractals: shiftStructure(timingResult.value.fractals as any[], shift),
      valid_fractals: shiftStructure(timingResult.value.valid_fractals as any[], shift),
      bcs: shiftStructure(timingResult.value.bcs as any[], shift),
      zsds: shiftStructure(timingResult.value.zsds as any[], shift),
      qsds: shiftStructure(timingResult.value.qsds as any[], shift),
      macd: padMacdHead(timingResult.value.macd as any, shift),
      levels,
    } as StockPickTimingResult
  }
}

const season = ref<SeasonInfo | null>(null)
const error = ref('')

// ── 缠论选股标签页 ────────────────────────────────────────────────────────
const router = useRouter()
const activeTab = ref<'changying' | 'chanlun'>('changying')

// 缠论选股条件
const clMarket = ref('SZ')
const clCodes = ref('') // 自定义代码（每行一个），空则自动取前 30 只
const clSignalType = ref('any_buy')
const clTrend = ref('any')
const clZsPosition = ref('any')
const clHasBeichi = ref(false)
const clCombineChangying = ref(false)
const clTopN = ref(10)

const clScanning = ref(false)
const clError = ref('')
const clResults = ref<ChanlunScreenResult[]>([])

const signalTypeLabels: Record<string, string> = {
  any: '任意信号',
  any_buy: '任意买点',
  '1buy': '1买（背驰买）',
  '2buy': '2买',
  '3buy': '3买',
  '1sell': '1卖（背驰卖）',
}
const trendLabels: Record<string, string> = {
  any: '不限',
  up: '向上',
  down: '向下',
}
const zsPosLabels: Record<string, string> = {
  any: '不限',
  above: '中枢上方',
  below: '中枢下方',
  inside: '中枢内',
}

async function runChanlunScreen() {
  clScanning.value = true
  clError.value = ''
  clResults.value = []
  try {
    const codes = clCodes.value
      .split(/[\s,]+/)
      .map((c) => c.trim())
      .filter(Boolean)
    const resp = await chanlunScreen({
      market: clMarket.value,
      codes: codes.length ? codes : undefined,
      criteria: {
        signal_type: clSignalType.value,
        trend: clTrend.value,
        zs_position: clZsPosition.value,
        has_beichi: clHasBeichi.value,
      },
      combine_changying: clCombineChangying.value,
      top_n: clTopN.value,
    })
    clResults.value = resp.qualified
    if (!resp.qualified.length) {
      clError.value = `扫描 ${resp.total_scanned} 只，无符合条件的标的`
    }
  } catch (e) {
    clError.value = formatError(e)
  } finally {
    clScanning.value = false
  }
}

/** 选股→择时→回测闭环：跳转回测页，预填代码 + chanlun_pair 策略。 */
function gotoBacktest(item: ChanlunScreenResult) {
  router.push({
    path: '/',
    query: { symbol: item.code, strategy: 'chanlun_pair' },
  })
}
// 择时数据来自 /stock-pick/timing（date 语义 = 分析截至日），这里跳转时：
// date 用区间终点（结构与图表对齐到该日），count 按 8000 上限覆盖起点。
const {
  jumpStart,
  jumpEnd,
  jumping,
  jumpError,
} = useTimeJump({
  code: () => timingResult.value?.code ?? '',
  category: () => 'DAY' as Category,
  detectMarket: () => timingResult.value?.market ?? 'SZ',
})

async function jumpTimingRange() {
  const item = selected.value
  if (!item || jumping.value) return
  const start = jumpStart.value.trim()
  if (!start) {
    jumpError.value = '请选择开始日期'
    return
  }
  const end = jumpEnd.value.trim() || selectDate.value
  error.value = ''
  jumping.value = true
  jumpError.value = ''
  try {
    // 服务端每页 800 根逐页回溯，count 越大越慢；按日期跨度估算根数
    //（自然日 × 5/7 ≈ 交易日）+ 余量，封顶 3000，控制跳转等待时间。
    const spanDays = Math.max(0, Math.round((Date.parse(end) - Date.parse(start)) / 86400000))
    const estCount = Math.min(3000, Math.max(400, Math.ceil((spanDays * 5) / 7) + 60))
    const res = await stockPickTiming({
      date: end,
      symbols: [{ market: item.market || 'SH', code: item.code }],
      count: estCount,
      recursion_depth: 2,
    })
    const r = res.results[0]
    if (!r || r.error) {
      jumpError.value = r?.error ?? '该区间无可用分析结果'
      return
    }
    // 客户端按 start 精确左截断（服务端 date 只截右端）
    const allBars = (r.bars as Bar[]) ?? []
    const barsWin = allBars.filter((b) => b.datetime.slice(0, 10) >= start)
    if (!barsWin.length) {
      jumpError.value = allBars.length
        ? `区间起点早于已取数据（只取到 ${allBars[0].datetime.slice(0, 10)}），请缩短区间或重试`
        : '该区间没有行情数据'
      return
    }
    const shift = allBars.length - barsWin.length
    const shiftList = (list: any[] | undefined) => (list ?? []).slice(shift)
    const levels: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(r.levels ?? {})) {
      const lv = v as Record<string, unknown>
      levels[k] = {
        ...lv,
        bis: shiftList(lv.bis as any[]),
        xds: shiftList(lv.xds as any[]),
        zss: shiftList(lv.zss as any[]),
        mmds: shiftList(lv.mmds as any[]),
        bcs: shiftList(lv.bcs as any[]),
        zsds: shiftList(lv.zsds as any[]),
        qsds: shiftList(lv.qsds as any[]),
      }
    }
    timingResult.value = {
      ...r,
      bars: barsWin,
      bis: shiftList(r.bis as any[]),
      xds: shiftList(r.xds as any[]),
      zss: shiftList(r.zss as any[]),
      mmds: shiftList(r.mmds as any[]),
      fractals: shiftList(r.fractals as any[]),
      valid_fractals: shiftList(r.valid_fractals as any[]),
      bcs: shiftList(r.bcs as any[]),
      macd: (r.macd as any)
        ? {
            ...(r.macd as any),
            dif: (r.macd as any).dif?.slice(shift),
            dea: (r.macd as any).dea?.slice(shift),
            hist: (r.macd as any).hist?.slice(shift),
          }
        : r.macd,
      levels,
    } as StockPickTimingResult
  } catch (e) {
    jumpError.value = formatError(e)
  } finally {
    jumping.value = false
  }
}
// V716: 全市场扫描异步任务进度（0~100，null=未在跑）
const screenProgress = ref<number | null>(null)
const screenProgressNote = ref('')

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
    // V716: 全市场扫描走异步任务 + 进度轮询（约 13s，进度条可见）。
    if (poolScope.value === 'full') {
      const { task_id } = await stockPickScreenAsync(req)
      for (;;) {
        const st = await stockPickScreenTask(task_id)
        screenProgress.value = st.progress ?? null
        screenProgressNote.value = st.progress_note ?? ''
        if (st.status === 'done') {
          pool.value = st.result?.results ?? []
          screenSource.value = 'online'
          screenUpdatedAt.value = ''
          if (!pool.value.length) error.value = '该时间/市场暂无符合长盈模型的标的'
          break
        }
        if (st.status === 'failed') throw new Error(st.error ?? '选股任务失败')
        await new Promise((r) => setTimeout(r, 800))
      }
      return
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
      count: 1200,
      recursion_depth: 2,
    })
    timingResult.value = res.results[0] ?? null
    season.value = res.season ?? null
    if (timingResult.value?.error) error.value = timingResult.value.error
  } catch (e) {
    error.value = formatError(e)
  } finally {
    timing.value = false
  }
}

// ── 一键批量择时：对选股池全部标的统一择时并按可操作性排序 ──
type TimingRankRow = StockPickTimingResult & {
  confidence: number
  action: string
  alignLabel: string
  // 该票历史上最强买点信号的命中率与结论（signal_quality 后验）
  topHitLabel: string
  topHitGood: boolean
}
const timingSummary = ref<TimingRankRow[]>([])
const timingAll = ref(false)

const actionRank: Record<string, number> = { 买入: 0, 卖出: 1, 观望: 2 }

async function runAllTiming() {
  error.value = ''
  timingSummary.value = []
  const batch = (pool.value || []).slice(0, 20)
  if (!batch.length) return
  timingAll.value = true
  try {
    const res = await stockPickTiming({
      date: selectDate.value,
      symbols: batch.map((x) => ({ market: x.market || 'SH', code: x.code.slice(-6) })),
      count: 1200,
      recursion_depth: 2,
    })
    const rows: TimingRankRow[] = (res.results || [])
      .filter((r) => r.symbol && !r.error)
      .map((r) => {
        const topBuy = r.signal_quality?.best_buy ?? null
        return {
          ...r,
          confidence: r.verdict?.confidence ?? 0,
          action: r.verdict?.action ?? '观望',
          alignLabel:
            r.recursion?.alignment === 'confirm'
              ? '同向'
              : r.recursion?.alignment === 'conflict'
                ? '背离'
                : '—',
          topHitLabel: topBuy
            ? `${topBuy.type} ${Math.round(topBuy.hit_rate * 100)}%`
            : '—',
          topHitGood: Boolean(topBuy && topBuy.hit_rate >= 0.6 && topBuy.excess_hit_rate > 0),
        }
      })
    rows.sort((a, b) => actionRank[a.action] - actionRank[b.action] || b.confidence - a.confidence)
    timingSummary.value = rows
    season.value = res.season ?? null
  } catch (e) {
    error.value = formatError(e)
  } finally {
    timingAll.value = false
  }
}

function pickTiming(row: StockPickTimingResult) {
  selected.value =
    pool.value.find((p) => p.code?.slice(-6) === (row.code ?? '').slice(-6)) ?? null
  timingResult.value = row
}
</script>

<template>
  <section class="stock-pick-view">
    <h2>选股</h2>
    <BeginnerGuide />

    <!-- 标签切换：长盈选股 / 缠论选股 -->
    <div class="tab-bar">
      <button
        :class="['tab-btn', { active: activeTab === 'changying' }]"
        @click="activeTab = 'changying'"
      >
        长盈选股
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'chanlun' }]"
        @click="activeTab = 'chanlun'"
      >
        缠论选股
      </button>
    </div>

    <!-- ════════ 缠论选股面板 ════════ -->
    <div v-if="activeTab === 'chanlun'" class="chanlun-screen-panel">
      <h3>缠论原著选股（结构驱动：买卖点 / 走势 / 中枢 / 背驰）</h3>
      <div class="cl-controls">
        <label>
          市场
          <select v-model="clMarket">
            <option value="SZ">深圳</option>
            <option value="SH">上海</option>
          </select>
        </label>
        <label>
          信号类型
          <select v-model="clSignalType">
            <option v-for="(lbl, val) in signalTypeLabels" :key="val" :value="val">{{ lbl }}</option>
          </select>
        </label>
        <label>
          走势方向
          <select v-model="clTrend">
            <option v-for="(lbl, val) in trendLabels" :key="val" :value="val">{{ lbl }}</option>
          </select>
        </label>
        <label>
          中枢位置
          <select v-model="clZsPosition">
            <option v-for="(lbl, val) in zsPosLabels" :key="val" :value="val">{{ lbl }}</option>
          </select>
        </label>
        <label class="checkbox-label">
          <input v-model="clHasBeichi" type="checkbox" /> 必须有背驰
        </label>
        <label class="checkbox-label">
          <input v-model="clCombineChangying" type="checkbox" /> 叠加长赢过滤
        </label>
        <label>
          返回前
          <input v-model.number="clTopN" type="number" min="1" max="50" style="width: 60px" />
          只
        </label>
        <button class="primary" :disabled="clScanning" @click="runChanlunScreen">
          {{ clScanning ? '扫描中…' : '🔍 缠论选股' }}
        </button>
      </div>
      <label class="cl-codes-label">
        自定义代码（每行一个，留空则自动取前 30 只）
        <textarea
          v-model="clCodes"
          rows="2"
          placeholder="000001&#10;600519"
          :disabled="clScanning"
        />
      </label>

      <p v-if="clError" class="error">{{ clError }}</p>

      <table v-if="clResults.length" class="cl-results">
        <thead>
          <tr>
            <th>代码</th>
            <th>现价</th>
            <th>最新信号</th>
            <th>走势</th>
            <th>中枢位置</th>
            <th>背驰</th>
            <th>质量分</th>
            <th>笔/中枢</th>
            <th>分类</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in clResults" :key="item.code">
            <td>{{ item.symbol }}</td>
            <td>{{ item.close }}</td>
            <td>
              <span :class="item.latest_signal?.is_buy ? 'cl-buy' : 'cl-sell'">
                {{ item.latest_signal?.type ?? '—' }}
              </span>
              <span v-if="item.latest_signal?.date" class="cl-date">{{ item.latest_signal.date }}</span>
            </td>
            <td>{{ trendLabels[item.trend ?? 'any'] ?? item.trend ?? '—' }}</td>
            <td>{{ zsPosLabels[item.zs_position ?? 'any'] ?? item.zs_position ?? '—' }}</td>
            <td>{{ item.has_beichi ? '✓' : '—' }}</td>
            <td>{{ item.quality_score }}</td>
            <td>{{ item.bi_count }}/{{ item.zs_count }}</td>
            <td>{{ item.classification }}</td>
            <td>
              <button class="ghost small" @click="gotoBacktest(item)">📊 回测</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ════════ 长盈选股面板（原有） ════════ -->
    <div v-if="activeTab === 'changying'">
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
      <p v-if="poolScope === 'pool'" class="pool-bias-hint">
        ⚠️ 热门池为当前龙头股（幸存者样本），回测胜率会系统性偏高；衡量策略真实
        水平请用「全市场扫描」。
      </p>
      <label v-if="poolScope === 'pool'" class="pool-text">
        自定义池（每行一个代码，留空用热门池）
        <textarea v-model="poolText" rows="2" placeholder="600519&#10;000333" />
      </label>
      <button :disabled="screening" @click="runScreen">
        {{ screening ? '选股中…' : '① 长盈选股' }}
      </button>
      <div v-if="screening && screenProgress !== null" class="scan-progress">
        <div class="scan-progress-bar" :style="{ width: `${screenProgress}%` }"></div>
        <span class="scan-progress-text"
          >{{ Math.round(screenProgress) }}% {{ screenProgressNote }}</span
        >
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="layout">
      <div class="pool-panel">
        <h3>基本面标的池（{{ pool.length }}）</h3>
        <p v-if="screenSource" class="source-note">
          数据来源：{{ screenSource === 'local' ? '本地沉淀池' : '在线扫描'
          }}<template v-if="screenUpdatedAt"> · 更新于 {{ screenUpdatedAt.slice(0, 10) }}</template>
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
        <div class="pool-actions">
          <button :disabled="timingAll || !pool.length" @click="runAllTiming">
            {{ timingAll ? '批量择时中…' : `② 一键择时 TOP ${Math.min(pool.length, 20)}` }}
          </button>
        </div>
        <div v-if="season" class="season-banner" :style="{ borderColor: season.color ?? '#4ade80' }">
          <div class="season-head">
            <strong :style="{ color: season.color ?? '#4ade80' }">{{ season.label }}</strong>
            <span v-if="season.position_range" class="season-pos"
              >建议仓位 {{ season.position_range[0] }}%~{{ season.position_range[1] }}%</span
            >
          </div>
          <p v-if="season.description">{{ season.description }}</p>
          <p v-if="season.strategy" class="season-strategy">策略：{{ season.strategy }}</p>
        </div>
        <div v-if="timingSummary.length" class="timing-summary">
          <h4>📊 择时排行（按可操作性排序）</h4>
          <table>
            <thead>
              <tr>
                <th>标的</th>
                <th>建议</th>
                <th>信号</th>
                <th>置信</th>
                <th>历史胜率</th>
                <th>递归</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in timingSummary"
                :key="row.symbol"
                :class="{ 'row-buy': row.action === '买入', 'row-sell': row.action === '卖出' }"
              >
                <td>{{ row.symbol }}</td>
                <td>{{ row.action }}</td>
                <td>{{ row.verdict?.signal ?? '—' }}</td>
                <td>{{ Math.round(row.confidence * 100) }}%</td>
                <td :class="{ ok: row.topHitGood }">{{ row.topHitLabel }}</td>
                <td :class="{ ok: row.alignLabel === '同向', warn: row.alignLabel === '背离' }">
                  {{ row.alignLabel }}
                </td>
                <td><button class="ghost" @click="pickTiming(row)">详情</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="timing-panel">
        <h3>缠论择时详情</h3>
        <div v-if="season" class="season-banner" :style="{ borderColor: season.color ?? '#4ade80' }">
          <div class="season-head">
            <strong :style="{ color: season.color ?? '#4ade80' }">{{ season.label }}</strong>
            <span v-if="season.position_range" class="season-pos"
              >建议仓位 {{ season.position_range[0] }}%~{{ season.position_range[1] }}%</span
            >
          </div>
          <p v-if="season.action">操作：{{ season.action }}</p>
        </div>
        <template v-if="timingResult">
          <div v-if="timingResult.verdict" class="verdict">
            <strong>{{ timingResult.verdict.action }}</strong>
            <span
              >{{ timingResult.verdict.signal }} ·
              {{ (timingResult.verdict.confidence ?? 0) * 100 }}%</span
            >
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
            <div v-if="timingResult.recursion" class="signal-quality">
              <p>
                🪜 更高级别确认：
                <template v-if="timingResult.recursion.latest">
                  {{ timingResult.recursion.latest.signal }}（{{ timingResult.recursion.latest.date ?? '—' }} ·
                  {{ Math.round((timingResult.recursion.latest.confidence ?? 0) * 100) }}%），共
                  {{ timingResult.recursion.depth_produced }} 级递归
                  <span v-if="timingResult.recursion.alignment === 'confirm'" class="ok"
                    >↑ 与笔级别同向</span
                  >
                  <span v-else-if="timingResult.recursion.alignment === 'conflict'" class="warn"
                    >↓ 与笔级别背离</span
                  >
                </template>
                <template v-else>{{ timingResult.recursion.note ?? '更高级别结构暂不足' }}</template>
              </p>
            </div>
          </div>
          <div class="timing-toolbar">
            <span v-if="earlierError" class="hint">{{ earlierError }}</span>
            <button class="hint-btn" :disabled="!earlierCanLoad" @click="loadEarlierTiming">
              {{ earlierLoading ? '加载中…' : '加载更早 ⏪' }}
            </button>
            <!-- V723: 任意日期区间跳转（重新按区间取数 + 择时分析） -->
            <input v-model="jumpStart" type="date" title="开始日期" />
            <input v-model="jumpEnd" type="date" title="结束日期" />
            <button class="hint-btn" :disabled="jumping" @click="jumpTimingRange">
              {{ jumping ? '跳转中…' : '跳转 📅' }}
            </button>
            <span v-if="jumpError" class="hint">{{ jumpError }}</span>
          </div>
          <ChanlunChart
            v-if="timingResult.bars?.length"
            :bars="timingResult.bars as any"
            :bis="(timingResult.bis as any) ?? []"
            :xds="(timingResult.xds as any) ?? []"
            :zss="(timingResult.zss as any) ?? []"
            :mmds="(timingResult.mmds as any) ?? []"
            :fxs="(timingResult.fractals as any) ?? []"
            :validFxs="(timingResult.valid_fractals as any) ?? []"
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
    </div><!-- /长盈选股面板 -->
  </section>
</template>

<style scoped>
.timing-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
}
.timing-toolbar .hint-btn {
  font-size: 12px;
  color: #8a93a6;
  background: transparent;
  border: 1px solid var(--border, #2a3040);
  border-radius: 4px;
  padding: 2px 10px;
  cursor: pointer;
}
.timing-toolbar .hint-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

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
.pool-bias-hint {
  color: #fcd34d;
  font-size: 12px;
  line-height: 1.5;
  margin: 4px 0 0;
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
.signal-quality .ok {
  color: #22c55e;
  font-weight: 600;
}
.signal-quality .warn {
  color: #f59e0b;
  font-weight: 600;
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
.pool-actions {
  margin-top: 10px;
}
.pool-actions button {
  width: 100%;
}
.timing-summary {
  margin-top: 12px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 10px;
  padding: 10px;
  background: rgba(255, 255, 255, 0.03);
}
.timing-summary h4 {
  margin: 0 0 8px;
  font-size: 13px;
  color: #e2e8f0;
}
.timing-summary table {
  width: 100%;
  font-size: 12px;
}
.timing-summary th {
  color: #94a3b8;
  font-weight: 500;
  text-align: left;
  padding: 4px 6px;
}
.timing-summary td {
  padding: 5px 6px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.timing-summary .row-buy td:first-child {
  color: #22c55e;
  font-weight: 600;
}
.timing-summary .row-sell td:first-child {
  color: #f87171;
  font-weight: 600;
}
.ok {
  color: #22c55e;
  font-weight: 600;
}
.warn {
  color: #f59e0b;
  font-weight: 600;
}
.season-banner {
  margin-top: 12px;
  border: 1px solid #4ade80;
  border-radius: 10px;
  padding: 10px 12px;
  background: rgba(74, 222, 128, 0.06);
}
.season-banner p {
  margin: 6px 0 0;
  font-size: 12px;
  color: #94a3b8;
}
.season-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.season-head strong {
  font-size: 14px;
}
.season-pos {
  font-size: 12px;
  color: #e2e8f0;
}
.season-strategy {
  color: #cbd5e1;
}
.scan-progress {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.scan-progress-bar {
  height: 6px;
  min-width: 4px;
  border-radius: 3px;
  background: linear-gradient(90deg, #60b4ff, #22c55e);
  transition: width 0.4s ease;
}
.scan-progress-text {
  font-size: 12px;
  color: #94a3b8;
  white-space: nowrap;
}

/* ── 缠论选股标签页 ── */
.tab-bar {
  display: flex;
  gap: 0;
  margin-bottom: 16px;
  border-bottom: 2px solid rgba(255, 255, 255, 0.1);
}
.tab-btn {
  padding: 8px 20px;
  border: none;
  background: transparent;
  color: #94a3b8;
  font-size: 14px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: all 0.2s;
}
.tab-btn:hover {
  color: #e2e8f0;
}
.tab-btn.active {
  color: #60b4ff;
  border-bottom-color: #60b4ff;
  font-weight: 600;
}
.chanlun-screen-panel {
  margin-bottom: 20px;
}
.chanlun-screen-panel h3 {
  font-size: 15px;
  margin-bottom: 12px;
  color: #e2e8f0;
}
.cl-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.cl-controls label {
  font-size: 12px;
  color: #94a3b8;
  display: flex;
  align-items: center;
  gap: 4px;
}
.cl-controls select,
.cl-controls input[type='number'] {
  padding: 4px 8px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 6px;
  color: #e2e8f0;
  font-size: 13px;
}
.checkbox-label {
  flex-direction: row !important;
  cursor: pointer;
}
.cl-codes-label {
  display: block;
  font-size: 12px;
  color: #94a3b8;
  margin-bottom: 12px;
}
.cl-codes-label textarea {
  display: block;
  width: 300px;
  margin-top: 4px;
  padding: 6px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 6px;
  color: #e2e8f0;
  font-size: 13px;
  font-family: monospace;
}
.cl-results {
  width: 100%;
  font-size: 13px;
}
.cl-results th {
  color: #94a3b8;
  font-weight: 500;
  text-align: left;
  padding: 6px 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12);
}
.cl-results td {
  padding: 6px 8px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}
.cl-buy {
  color: #22c55e;
  font-weight: 600;
}
.cl-sell {
  color: #f87171;
  font-weight: 600;
}
.cl-date {
  display: block;
  font-size: 11px;
  color: #64748b;
}
</style>
