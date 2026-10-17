<script setup lang="ts">
/**
 * 买卖点核对页（V-CHECK）
 *
 * 目标：回答两个问题，且**只用一屏**：
 *   1. 历史上某个时期，缠论标出的买卖点**准不准**（事后收益 + 命中率 + 随机基准对照）
 *   2. **最新的买卖点提示**是什么
 *
 * 与 ChanlunView 的区别：那个页面是「缠论工作台」（多级别/递归/训练/熟练度…），
 * 控件非常多。本页只保留三个输入：股票、周期、时间段。其余自动。
 *
 * 「准不准」怎么算（写在这里便于复核）：
 *   每个买点取信号当日收盘价，算之后 N 根的最高/最低/收盘涨跌；
 *   同时在同一段数据上做**随机入场**基准（同数量、固定种子）。
 *   命中率（买后上涨的比例）高于随机 ⇒ 该信号有信息量，否则没有。
 */
import { computed, onMounted, ref, watch } from 'vue'
import ChanlunChart from '../components/ChanlunChart.vue'
import { fetchBars } from '../api'
import { formatError } from '../api'
import type { Bar } from '../types'

type Category = 'DAY' | 'MIN_30' | 'MIN_60' | 'WEEK'

interface Mmd {
  type: string
  date: string | null
  bar_index: number | undefined
  anchor_val: number | undefined
  msg: string
  confidence: number
}
interface StatRow {
  /** 信号类型（1buy / 3sell / …） */
  type: string
  horizon: number
  /** 样本数 —— n 小的时候百分比毫无意义，必须暴露给用户 */
  count: number
  /** 小数（0.0388 == +3.88%） */
  avg: number
  rnd: number
  excess: number
  t: number
  significant: boolean
  verdict: string
}

const HORIZON = 5 // 前瞻根数：买点看 5 根后是否上涨

const code = ref('600519')
const category = ref<Category>('DAY')
const preset = ref<'1y' | '3y' | '5y' | 'custom'>('1y')
/** 自定义起止日期（preset==='custom' 时生效） */
const customStart = ref('')
const customEnd = ref('')
/** 次级别周期：用于区间套（'' = 不做区间套） */
const subCategory = ref<Category | ''>('')
const coverage = ref<{ bar_count: number; first: string | null; last: string | null } | null>(null)
/** 区间套请求失败原因（后端要跨周期取数，可能超时/失败） */
const qtErr = ref('')
const noSubData = computed(
  () => !!subCategory.value && coverage.value !== null && coverage.value.bar_count === 0,
)

/** 区间套结果：mmd 索引 → 嵌套信息 */
const qujiantao = ref<Record<number, any>>({})
/** 次级别 K 线/笔/中枢/买卖点（multi-level 的 low_level.result）——
 * 点买卖点时画次级别图，让用户「跳转其他周期看区间套」精确定位 */
const lowBars = ref<Bar[]>([])
const lowBis = ref<any[]>([])
const lowZss = ref<any[]>([])
const lowMmds = ref<Mmd[]>([])

const bars = ref<Bar[]>([])
const mmds = ref<Mmd[]>([])
/** 后端 /chanlun/signal-stats 的统计（**唯一口径**，与审计脚本共用
 *  src/easy_tdx/backtest/signal_stats.py）。前端**不自己算**，避免两份
 *  实现漂移出两个不同的数。 */
const statsRows = ref<StatRow[]>([])
const critT = ref<number | null>(null)
const bis = ref<any[]>([])
const zss = ref<any[]>([])
const xds = ref<any[]>([])
const loading = ref(false)
const err = ref('')
const picked = ref<Mmd | null>(null)

const PRESETS: Record<string, number> = { '1y': 250, '3y': 750, '5y': 1250 }

const CATS: { value: Category; label: string }[] = [
  { value: 'DAY', label: '日线' },
  { value: 'MIN_30', label: '30分钟' },
  { value: 'MIN_60', label: '60分钟' },
  { value: 'WEEK', label: '周线' },
]

/** 市场代码：/chanlun/analyze 要求大写（^(SZ|SH|BJ)$，小写会 422）。
 *  注意与 fetchBars 不同 —— 那个接受小写，别混用。 */
function detectMarket(c: string): string {
  if (c.startsWith('6')) return 'SH'
  if (c.startsWith('0') || c.startsWith('3')) return 'SZ'
  if (c.startsWith('8') || c.startsWith('4')) return 'BJ'
  return 'SH'
}

const barCount = computed(() => {
  if (preset.value === 'custom') return 3000 // 自定义区间：尽量覆盖，再由日期截断
  return PRESETS[preset.value] ?? 750
})

/** 自定义模式下是否填了日期 */
const customReady = computed(
  () => preset.value !== 'custom' || (!!customStart.value && !!customEnd.value),
)

async function load() {
  loading.value = true
  err.value = ''
  picked.value = null
  try {
    const market = detectMarket(code.value)
    const sd = preset.value === 'custom' ? customStart.value : undefined
    const ed = preset.value === 'custom' ? customEnd.value : undefined
    const b = await fetchBars(
      market.toLowerCase(), code.value, category.value, sd, ed, barCount.value,
    )
    if (!b.length) {
      err.value = '未取到数据，检查股票代码'
      return
    }
    bars.value = b

    // 缠论分析：窗口内取数 + 分析同一区间，保证叠加层与 K 线对齐
    const resp = await fetch('/api/v1/chanlun/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        market,
        code: code.value,
        category: category.value,
        count: b.length,
        start: 0,
        start_date: b[0].datetime.slice(0, 10),
        end_date: b[b.length - 1].datetime.slice(0, 10),
      }),
    })
    if (!resp.ok) throw new Error(await formatError(resp))
    const d = await resp.json()
    mmds.value = d.mmds ?? []
    bis.value = d.bis ?? []
    zss.value = d.zss ?? []
    xds.value = d.xds ?? []

    // 统计：走后端**唯一口径**（market 大写，否则 422）
    // ⚠️ 必须带上与 analyze **完全相同的** start_date/end_date ——
    //    只传 count 会让统计窗口和图上的 K 线窗口对不上，统计的就不是
    //    用户眼前这段行情里的买卖点（实测：601398 传 count=800 有 2buy_s，
    //    页面按 750 根窗口则没有 ⇒ 两套数）。
    const s2 = await fetch('/api/v1/chanlun/signal-stats', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        market,
        code: code.value,
        category: category.value,
        count: b.length,
        start: 0,
        start_date: b[0].datetime.slice(0, 10),
        end_date: b[b.length - 1].datetime.slice(0, 10),
      }),
    })
    if (s2.ok) {
      const sd = await s2.json()
      statsRows.value = sd.stats ?? []
      critT.value = sd.critical_t ?? null
    } else {
      statsRows.value = []
      critT.value = null
    }

    // 区间套：需要次级别周期才拉；结果按 mmd 顺序索引
    qujiantao.value = {}
    coverage.value = null
    qtErr.value = ''
    lowBars.value = []
    lowBis.value = []
    lowZss.value = []
    lowMmds.value = []
    if (subCategory.value) {
      try {
      const q = await fetch('/api/v1/chanlun/multi-level', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          market,
          code: code.value,
          category: category.value,
          low_level: subCategory.value,
          count: b.length,
          start: 0,
          start_date: b[0].datetime.slice(0, 10),
          end_date: b[b.length - 1].datetime.slice(0, 10),
        }),
      })
      if (q.ok) {
        const qd = await q.json()
        coverage.value = qd.low_level_coverage ?? null
        // 次级别结构数据（画次级别 K 线图，精确定位区间套）
        const lr = qd.low_level?.result ?? {}
        lowBars.value = lr.bars ?? []
        lowBis.value = lr.bis ?? []
        lowZss.value = lr.zss ?? []
        lowMmds.value = lr.mmds ?? []
        const arr = qd.qujiantao ?? []
        const map: Record<number, any> = {}
        arr.forEach((v: any, i: number) => {
          if (v) map[i] = v
        })
        qujiantao.value = map
        // 次级别 K 线（to_dict 不含 bars，单独取，画次级别图）
        try {
          const lb = await fetchBars(
            market.toLowerCase(), code.value, subCategory.value,
            b[0].datetime.slice(0, 10), b[b.length - 1].datetime.slice(0, 10), 3000,
          )
          lowBars.value = lb
        } catch { lowBars.value = [] }
      } else {
        qtErr.value = `区间套请求失败（HTTP ${q.status}）`
      }
      } catch (e: any) {
        // 跨周期取数较重（实测：1年≈19s / 3年≈38s，浏览器 30s 超时），
        // 失败不能拖垮主流程；提示用户缩短区间或换更短次级别
        qtErr.value = `区间套取数超时/失败：${e?.message ?? String(e)}。区间套需拉低级别全段，3年+30min约38s会超浏览器30s上限，建议选「近1年」或次级别用60分钟（根数少更快）。`
      }
    }
  } catch (e: any) {
    err.value = e?.message ?? String(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
// ⚠️ 自定义模式下必须等**两个日期都填了**才发起请求：
//    只切到 custom 而日期仍为空时若照常 load()，会拉回「最新 3000 根」
//    （2014→2026），而这次请求**最后完成**、覆盖掉后面正确的窗口请求
//    ⇒ 用户选了 2024 年却看到 2026 年数据（实测 3000 根 / 统计 0 行）。
watch([code, category, preset, customStart, customEnd, subCategory], () => {
  if (!customReady.value) return
  load()
})

// ── 统计：全部来自后端 /chanlun/signal-stats（唯一口径）───────────────────

const stats = computed<StatRow[]>(() =>
  [...statsRows.value].sort((a, b) => {
    if (a.significant !== b.significant) return a.significant ? -1 : 1
    return b.excess - a.excess
  }),
)

const totalSignals = computed(() => stats.value.reduce((a, b) => a + b.count, 0))
/** 通过显著性检验（Bonferroni 校正后）的类型数 —— 这才是"可信"的那部分 */
const effective = computed(() => stats.value.filter((s) => s.significant))
/** 样本量不足的行：必须让用户看见，否则「100% 命中率」是误导 */
const thinRows = computed(() => stats.value.filter((s) => s.count < 5))


/** 最新买卖点：窗口末尾最近的那条 */
const latest = computed<Mmd | null>(() => {
  const withIdx = mmds.value.filter((m) => m.bar_index != null)
  if (!withIdx.length) return null
  return withIdx.reduce((a, b) => (b.bar_index! > a.bar_index! ? b : a))
})

/** 最新信号距今天数（K线根数） */
const latestAge = computed(() => {
  if (!latest.value?.bar_index || !bars.value.length) return null
  return bars.value.length - 1 - latest.value.bar_index
})

const LABEL: Record<string, string> = {
  '1buy': '一买', '2buy': '二买', '2buy_s': '类二买', '3buy': '三买',
  '1sell': '一卖', '2sell': '二卖', '2sell_s': '类二卖', '3sell': '三卖',
}

/** ⚠️ 已证伪（2026-10-10）：曾把 `2buy_s`（类二买）标成"方向是反的"，
 *  那是**我自己的 bug** —— 用 `t.endswith("buy")` 判买卖方向，而
 *  `2buy_s` 以 `_s` 结尾 ⇒ 被当成卖点取反，产出稳定的假反向信号。
 *  改用 `is_buy_type()`（权威口径 `"buy" in type`）后，2buy_s 三档
 *  全部 ✅ 显著（t = 7.10 / 3.99 / 5.80）。
 *  **类二买是有效信号，不要隐藏也不要打反向标记。**
 *  详见 docs/CHANLUN_CORRECTNESS_50STOCKS.md「已证伪」一节。
 */
const label = (t: string) => LABEL[t] ?? t
/** 小数 → 百分比字符串（后端统一返回小数，0.0388 == +3.88%） */
const pct = (v: number) => `${v >= 0 ? '+' : ''}${(v * 100).toFixed(2)}%`
// ⚠️ 不能用 `t.endsWith('buy')`：`2buy_s`（类二买）以 `_s` 结尾会漏判，
//    前端会把「类二买」显示成**卖出**（后端已修同类 bug，前端必须同步）。
//    权威口径与后端 signal_stats.is_buy_type 一致：`'buy' in t`。
const isBuyType = (t: string) => t.includes('buy')

/**
 * 某类型信号在当前次级别下**有多少个被区间套确认 / 共多少个**。
 * 返回 null = 没开区间套；否则返回 {nested, total}。
 *
 * 后端 qujiantao 按 high_result.mmds 顺序**逐信号**返回（实测：7 个买卖点
 * → 7 条区间套，其中 6 条 nested=True）。所以不能按「类型取第一个下标」
 * 去查（同一类型有多个信号，取第一个会漏掉其余），必须**遍历该类型的
 * 全部信号**再聚合。
 */
function nestedOf(type: string): { nested: number; total: number } | null {
  if (!subCategory.value) return null
  const idxs: number[] = []
  mmds.value.forEach((m, i) => {
    if (m.type === type) idxs.push(i)
  })
  if (!idxs.length) return null
  let n = 0
  for (const i of idxs) {
    const q = qujiantao.value[i]
    if (q && q.nested) n += 1
  }
  return { nested: n, total: idxs.length }
}

/** 次级别数据覆盖提示：窗口早于边界 ⇒ 区间套必然全 false */

const rangeText = computed(() => {
  if (!bars.value.length) return ''
  return `${bars.value[0].datetime.slice(0, 10)} ~ ${bars.value[bars.value.length - 1].datetime.slice(0, 10)}`
})

/** 当前选中的买卖点索引（点击明细列表行设置；-1 = 未选）。
 *  切换股票/周期/时间段/次级别时清空，避免错位。 */
const selectedIdx = ref(-1)
watch([code, category, preset, customStart, customEnd, subCategory], () => {
  selectedIdx.value = -1
})

/** 选中买卖点的区间套详情（来自后端 qujiantao[idx]）。
 *  没开区间套 / 没选中 / 该信号无区间套数据时为 null。 */
const selectedQt = computed<any | null>(() => {
  if (selectedIdx.value < 0 || !subCategory.value) return null
  return qujiantao.value[selectedIdx.value] ?? null
})

/** 区间套徽章文案：nested + method 区分（真跨周期 vs 合成近似 vs 无数据）。
 *  method='cross_period' = 真区间套（原文语义）；其余只作参考。 */
function qtBadge(q: any | null): { text: string; cls: string } {
  if (!q) return { text: '—', cls: 'qt-na' }
  if (q.nested) {
    const real = q.method === 'cross_period'
    return { text: real ? '✅ 真区间套确认' : '☑ 确认(近似)', cls: real ? 'qt-yes' : 'qt-maybe' }
  }
  return { text: '✗ 未确认', cls: 'qt-no' }
}
</script>

<template>
  <div class="check-page">
    <header class="bar-top">
      <h1>买卖点核对</h1>
      <div class="ctrl">
        <input v-model="code" class="inp code" placeholder="代码 如 600519" />
        <select v-model="category" class="inp">
          <option v-for="c in CATS" :key="c.value" :value="c.value">{{ c.label }}</option>
        </select>
        <select v-model="preset" class="inp">
          <option value="1y">近 1 年</option>
          <option value="3y">近 3 年</option>
          <option value="5y">近 5 年</option>
          <option value="custom">自定义区间…</option>
        </select>
        <template v-if="preset === 'custom'">
          <input v-model="customStart" class="inp" type="date" />
          <span class="tilde">~</span>
          <input v-model="customEnd" class="inp" type="date" />
        </template>
        <select v-model="subCategory" class="inp" title="次级别周期（区间套：大级别背驰在小级别确认）">
          <option value="">不套区间套</option>
          <option value="MIN_5">次级别 5分钟</option>
          <option value="MIN_15">次级别 15分钟</option>
          <option value="MIN_30">次级别 30分钟</option>
          <option value="MIN_60">次级别 60分钟</option>
        </select>
        <button class="btn" :disabled="loading || !customReady" @click="load">
          {{ loading ? '加载中…' : '查看' }}
        </button>
      </div>
    </header>

    <p v-if="err" class="err">{{ err }}</p>

    <template v-if="bars.length">
      <p class="range">{{ code }} · {{ CATS.find(c => c.value === category)?.label }} · {{ rangeText }} · 共 {{ bars.length }} 根</p>

      <!-- 1. 最新买卖点提示 -->
      <section class="card latest">
        <h2>最新买卖点提示</h2>
        <div v-if="latest" class="latest-body" :class="isBuyType(latest.type) ? 'buy' : 'sell'">
          <div class="big">
            <span class="tag">{{ label(latest.type) }}</span>
            <span class="dir">{{ isBuyType(latest.type) ? '买入' : '卖出' }}</span>
          </div>
          <div class="meta">
            <span>{{ latest.date }}</span>
            <span v-if="latestAge !== null">（{{ latestAge }} 根之前）</span>
            <span>价格 {{ latest.anchor_val }}</span>
            <span>置信度 {{ (latest.confidence * 100).toFixed(0) }}%</span>
          </div>
          <p class="msg">{{ latest.msg }}</p>
        </div>
        <p v-else class="muted">当前窗口内没有买卖点信号。</p>
      </section>

      <!-- 2. 准不准 -->
      <section class="card">
        <h2>这段时间的买卖点准不准</h2>
        <p class="hint">
          每个信号看之后 {{ HORIZON }} 根的涨跌，与<b>同数量随机入场</b>对照。
          只有<b>胜过随机</b>才算有效 —— 否则那只是这段时间本身在涨。
        </p>
        <table v-if="stats.length" class="tbl">
          <thead>
            <tr>
              <th>信号</th>
              <th>前瞻</th>
              <th>样本数</th>
              <th>信号涨跌</th>
              <th>随机基准</th>
              <th>超额</th>
              <th>结论（胜过随机才算准）</th>
              <th v-if="subCategory">区间套</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in stats" :key="s.type + '-' + s.horizon">
              <td class="nm">{{ label(s.type) }}</td>
              <td>{{ s.horizon }} 根</td>
              <td :class="s.count < 5 ? 'thin' : ''">{{ s.count }}</td>
              <td :class="s.avg >= 0 ? 'up' : 'dn'">{{ pct(s.avg) }}</td>
              <td class="muted">{{ pct(s.rnd) }}</td>
              <td :class="s.excess > 0 ? 'up' : 'dn'">{{ pct(s.excess) }}</td>
              <td>{{ s.verdict }}</td>
              <td v-if="subCategory">
                <span v-if="nestedOf(s.type) === null" class="muted">—</span>
                <span v-else-if="nestedOf(s.type)!.nested > 0" class="qt-yes">
                  ✅ {{ nestedOf(s.type)!.nested }}/{{ nestedOf(s.type)!.total }}
                </span>
                <span v-else class="muted">0/{{ nestedOf(s.type)!.total }} 未确认</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted">这段时间内没有可用于统计的买卖点。</p>
        <p v-if="stats.length" class="sum">
          共 {{ totalSignals }} 个信号，其中
          <b>{{ effective.length }}</b> 个组合通过显著性检验（|t| &gt; {{ critT?.toFixed(2) }}，已按 {{ stats.length }} 次比较做 Bonferroni 校正）。
          <span v-if="!effective.length" class="warn">
            ⇒ 这只票在这段时间里，没有可验证的买卖点信息量。
          </span>
        </p>
        <p v-if="qtErr" class="sum warn">
          ⚠️ {{ qtErr }} —— 已跳过区间套，其余统计不受影响。
          次级别取数较重（需拉取低周期全段），可稍后重试或选更短区间。
        </p>
        <p v-if="noSubData" class="sum warn">
          ⚠️ 所选区间早于次级别数据起点（{{ coverage?.first ?? '未知' }}），
          **没有低周期数据可做区间套** —— 下面的「未确认」是数据覆盖不到，
          不是模型判断失败。请改选更近的区间。
        </p>
        <p v-if="thinRows.length" class="sum warn">
          ⚠️ 有 {{ thinRows.length }} 行样本数 &lt; 5，这类行的百分比**不足为凭**
          （n=1 时的「100%」是运气，不是能力）。
        </p>
      </section>

      <!-- 3. 买卖点明细（逐个，可点击看区间套） -->
      <section class="card">
        <h2>买卖点明细（点击看区间套）</h2>
        <p class="hint">
          逐个列出本时段所有买卖点。开启次级别后，每行显示该买卖点的<b>区间套确认状态</b>；
          点击任一行查看该买卖点在低级别的确认详情。
          <span v-if="!subCategory" class="warn">（未选次级别 → 无区间套，请上方选 5/15/30/60 分钟）</span>
        </p>
        <table v-if="mmds.length" class="tbl detail">
          <thead>
            <tr>
              <th>日期</th>
              <th>类型</th>
              <th>方向</th>
              <th>价格</th>
              <th>置信度</th>
              <th v-if="subCategory">区间套</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(m, i) in mmds"
              :key="i"
              :class="['row', selectedIdx === i ? 'sel' : '', isBuyType(m.type) ? 'buy' : 'sell']"
              @click="selectedIdx = selectedIdx === i ? -1 : i"
            >
              <td>{{ m.date ?? '—' }}</td>
              <td class="nm">{{ label(m.type) }}</td>
              <td>{{ isBuyType(m.type) ? '买入' : '卖出' }}</td>
              <td>{{ m.anchor_val ?? '—' }}</td>
              <td>{{ (m.confidence * 100).toFixed(0) }}%</td>
              <td v-if="subCategory">
                <span :class="qtBadge(qujiantao[i] ?? null).cls">
                  {{ qtBadge(qujiantao[i] ?? null).text }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
        <p v-else class="muted">本时段没有买卖点信号。</p>

        <!-- 选中买卖点的区间套详情 -->
        <div v-if="selectedQt" class="qt-detail">
          <h3>区间套确认详情</h3>
          <p class="qt-msg">{{ selectedQt.msg }}</p>
          <ul class="qt-meta">
            <li>确认状态：<b :class="selectedQt.nested ? 'up' : 'dn'">{{ selectedQt.nested ? '已确认' : '未确认' }}</b></li>
            <li>区间套强度评分：{{ (selectedQt.score * 100).toFixed(0) }}%</li>
            <li>数据来源：<span :class="selectedQt.method === 'cross_period' ? 'up' : 'muted'">{{ selectedQt.method === 'cross_period' ? '真实跨周期（原文意义）' : selectedQt.method }}</span></li>
            <li>状态：{{ selectedQt.state ?? '—' }}</li>
          </ul>
          <p v-if="selectedQt.detail" class="qt-detail-sub">
            低级别结构：笔 {{ selectedQt.detail.low_bi_count ?? 0 }} / 中枢 {{ selectedQt.detail.low_zs_count ?? 0 }}
            / 同向背驰 {{ selectedQt.detail.low_bc_same_dir ? '有' : '无' }}
            / 同向买卖点 {{ selectedQt.detail.low_mmd_same_dir ? '有' : '无' }}
          </p>
        </div>
        <p v-else-if="selectedIdx >= 0 && subCategory" class="muted">
          该买卖点在所选次级别无区间套数据（可能窗口外无低级别结构）。
        </p>

        <!-- 次级别 K 线图：选了次级别且点了买卖点 → 跳转看该周期的结构 -->
        <div v-if="subCategory && lowBars.length && selectedIdx >= 0" class="qt-sub-chart">
          <h3>次级别（{{ subCategory }}）K 线结构</h3>
          <p class="hint">下图是该买卖点在次级别周期的走势，可看区间套收缩过程（笔/中枢/买卖点）。</p>
          <ChanlunChart
            :bars="lowBars"
            :bis="lowBis"
            :xds="[]"
            :zss="lowZss"
            :mmds="lowMmds"
            :frequency="subCategory"
          />
        </div>
      </section>

      <!-- 4. 图 -->
      <section class="card">
        <h2>买卖点位置</h2>
        <p class="hint">点上方「买卖点明细」里的任一行，会在下方图上高亮该信号位置（选中行变粗）。</p>
        <ChanlunChart
          :bars="bars"
          :bis="bis"
          :xds="xds"
          :zss="zss"
          :mmds="mmds"
          :frequency="category"
        />
      </section>
    </template>

    <p v-else-if="!loading && !err" class="muted">输入股票代码后点「查看」。</p>
  </div>
</template>

<style scoped>
.check-page { max-width: 1100px; margin: 0 auto; padding: 16px; }
.bar-top { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; }
h1 { font-size: 20px; margin: 0; }
.ctrl { display: flex; gap: 8px; flex-wrap: wrap; }
.inp { padding: 6px 8px; border: 1px solid #d0d7de; border-radius: 6px; font-size: 14px; }
.code { width: 120px; }
.btn { padding: 6px 14px; background: #1f6feb; color: #fff; border: 0; border-radius: 6px; cursor: pointer; font-size: 14px; }
.btn:disabled { background: #9aa4b2; cursor: not-allowed; }
.err { color: #cf222e; }
.range { color: #57606a; font-size: 13px; margin: 4px 0 12px; }
.card { border: 1px solid #d8dee4; border-radius: 8px; padding: 14px; margin-bottom: 14px; }
.card h2 { font-size: 15px; margin: 0 0 8px; }
.hint { font-size: 12px; color: #57606a; margin: 0 0 10px; line-height: 1.6; }
.latest-body { border-left: 4px solid #1a7f37; padding-left: 12px; }
.latest-body.sell { border-left-color: #cf222e; }
.big { display: flex; align-items: baseline; gap: 10px; }
.tag { font-size: 22px; font-weight: 700; }
.dir { font-size: 13px; color: #57606a; }
.meta { display: flex; gap: 12px; flex-wrap: wrap; font-size: 12px; color: #57606a; margin-top: 4px; }
.msg { font-size: 13px; margin: 6px 0 0; }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th, .tbl td { padding: 6px 8px; border-bottom: 1px solid #eaeef2; text-align: right; }
.tbl th:first-child, .tbl td:first-child { text-align: left; }
.tbl th:last-child, .tbl td:last-child { text-align: left; }
.nm { font-weight: 600; }
.up { color: #1a7f37; }
.dn { color: #cf222e; }
.muted { color: #57606a; font-size: 13px; }
.sum { font-size: 13px; margin: 10px 0 0; }
.warn { color: #cf222e; }

/* 买卖点明细列表 */
.tbl.detail tbody tr.row { cursor: pointer; transition: background 0.1s; }
.tbl.detail tbody tr.row:hover { background: #f6f8fa; }
.tbl.detail tbody tr.row.sel { background: #fff8c5; font-weight: 700; }
.tbl.detail tbody tr.row.buy td:nth-child(3) { color: #1a7f37; }
.tbl.detail tbody tr.row.sell td:nth-child(3) { color: #cf222e; }

/* 区间套徽章 */
.qt-yes { color: #1a7f37; font-weight: 600; }
.qt-maybe { color: #bf8700; }
.qt-no { color: #cf222e; }
.qt-na { color: #57606a; }

/* 区间套详情面板 */
.qt-detail { margin-top: 14px; padding: 12px; background: #f6f8fa; border-radius: 6px; border-left: 4px solid #1f6feb; }
.qt-detail h3 { font-size: 14px; margin: 0 0 8px; }
.qt-sub-chart { margin-top: 14px; padding: 12px; background: #fff; border: 1px dashed #1f6feb; border-radius: 6px; }
.qt-sub-chart h3 { font-size: 14px; margin: 0 0 4px; color: #1f6feb; }
.qt-msg { font-size: 13px; margin: 0 0 8px; line-height: 1.6; }
.qt-meta { list-style: none; padding: 0; margin: 0; font-size: 13px; }
.qt-meta li { padding: 2px 0; }
.qt-detail-sub { font-size: 12px; color: #57606a; margin: 8px 0 0; }
</style>
