<script setup lang="ts">
// 实战交易信号页（V-TRADE）
// 30min 买点入场 → 5min 卖点出场 → 止损/止盈（可调）。
// 诚实原则：买入价用「确认日收盘」(分型右根走完，缠论62/65课原文查证)，信号老化与价偏离显式标注。
import { ref, computed, onMounted } from 'vue'
import { chanlunTradeSignals, chanlunTradeReplay, stockPickScreen, type TradeResult, type ReplayResult } from '../api'

// ── 模式切换：当日信号 / 历史回放 ──
const mode = ref<'signals' | 'replay'>('signals')

// ── 参数 ──
const stopLossPct = ref(5)
const takeProfitPct = ref(20)
const countBars = ref(400)

// ── 标的池 ──
const poolInput = ref('SH:600000,SH:600519,SH:601318')
const symbols = ref<{ market: string; code: string }[]>([])
const screening = ref(false)
const screenMsg = ref('')
const selectDate = ref(new Date().toISOString().slice(0, 10))

// ── 结果 ──
const loading = ref(false)
const errorMsg = ref('')
const results = ref<TradeResult[]>([])

// ── 持仓跟踪（localStorage）──
interface Holding {
  symbol: string
  buyPrice: number
  buyDate: string
  stopLoss: number
  takeProfit: number
}
const STORAGE_KEY = 'dsh.trade.holdings.v1'
const holdings = ref<Holding[]>([])

function loadHoldings() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) holdings.value = JSON.parse(raw)
  } catch { /* ignore */ }
}
function saveHoldings() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(holdings.value))
}
function addHolding(r: TradeResult) {
  const price = r.latest_buy?.confirm_price ?? r.current_price ?? 0
  if (!price) return
  // 同标的去重（覆盖）
  holdings.value = holdings.value.filter((h) => h.symbol !== r.symbol)
  holdings.value.push({
    symbol: r.symbol,
    buyPrice: price,
    buyDate: r.latest_buy?.confirm_date ?? r.last_date ?? '',
    stopLoss: r.stop_loss_price ?? price * (1 - stopLossPct.value / 100),
    takeProfit: r.take_profit_price ?? price * (1 + takeProfitPct.value / 100),
  })
  saveHoldings()
}
function removeHolding(sym: string) {
  holdings.value = holdings.value.filter((h) => h.symbol !== sym)
  saveHoldings()
}

// ── 标的池解析 ──
function parsePool(): { market: string; code: string }[] {
  return poolInput.value
    .split(/[,，\s]+/)
    .map((s) => s.trim().toUpperCase().replace(/[:：]/g, ''))
    .filter(Boolean)
    .map((s) => {
      const m = s.match(/^(SH|SZ|BJ)(\d{6})$/)
      if (m) return { market: m[1], code: m[2] }
      const m2 = s.match(/^(\d{6})$/)
      if (m2) return { market: 'SH', code: m2[1] }
      return null
    })
    .filter(Boolean) as { market: string; code: string }[]
}

// ── 树粮菜选股定池 ──
async function runScreen() {
  screening.value = true
  screenMsg.value = '正在树粮菜选股…'
  errorMsg.value = ''
  try {
    const res = await stockPickScreen({
      date: selectDate.value,
      markets: ['SH', 'SZ'],
      stock_type: 'all',
      top_n: 8,
    })
    const pool = res.results ?? []
    if (!pool.length) {
      screenMsg.value = '该时间暂无符合树粮菜的标的'
      return
    }
    symbols.value = pool.map((p) => ({
      market: p.market || (p.symbol.startsWith('SZ') ? 'SZ' : 'SH'),
      code: p.code || p.symbol.replace(/^(SH|SZ|BJ)/, ''),
    })).slice(0, 8)
    poolInput.value = symbols.value.map((s) => `${s.market}:${s.code}`).join(',')
    screenMsg.value = `树粮菜选出 ${pool.length} 只，已锁定前 ${symbols.value.length} 只`
  } catch (e: any) {
    screenMsg.value = '选股失败：' + (e?.message || String(e)).slice(0, 60)
  } finally {
    screening.value = false
  }
}

// ── 拉取交易信号 ──
async function fetchSignals() {
  const syms = parsePool()
  if (!syms.length) {
    errorMsg.value = '请先输入或选股得到标的（如 SH:600000）'
    return
  }
  symbols.value = syms
  loading.value = true
  errorMsg.value = ''
  results.value = []
  try {
    const res = await chanlunTradeSignals({
      symbols: syms,
      stop_loss_pct: stopLossPct.value,
      take_profit_pct: takeProfitPct.value,
      count: countBars.value,
    })
    results.value = res.results
  } catch (e: any) {
    errorMsg.value = '信号拉取失败：' + (e?.message || String(e)).slice(0, 80)
  } finally {
    loading.value = false
  }
}

// ── 渲染辅助 ──
function buyTypeLabel(t: string | null) {
  if (!t) return ''
  const map: Record<string, string> = { '1buy': '一买', '2buy': '二买', '3buy': '三买', '2buy_s': '类二买' }
  return map[t] || t
}
function sellTypeLabel(t: string | null) {
  if (!t) return ''
  const map: Record<string, string> = { '1sell': '一卖', '2sell': '二卖', '3sell': '三卖', '2sell_s': '类二卖' }
  return map[t] || t
}
function qtLabel(s: string | null) {
  if (s === 'CONFIRMED') return '已确认'
  if (s === 'REJECTED') return '已否决'
  if (s === 'ASSUMED') return '待确认'
  return '—'
}
function qtCls(s: string | null) {
  if (s === 'CONFIRMED') return 'qt-conf'
  if (s === 'REJECTED') return 'qt-rej'
  if (s === 'ASSUMED') return 'qt-assume'
  return 'qt-none'
}
function actionColor(a: string) {
  if (a === '可买') return '#d32f2f'
  if (a === '卖出') return '#1565c0'
  return '#757575'
}
function actionCls(a: string) {
  if (a === '可买') return 'act-buy'
  if (a === '卖出') return 'act-sell'
  return 'act-wait'
}
function holdingFor(sym: string) {
  return holdings.value.find((h) => h.symbol === sym)
}
function pnlPct(sym: string, cur: number | null) {
  const h = holdingFor(sym)
  if (!h || !cur) return null
  return Math.round((cur / h.buyPrice - 1) * 1000) / 10
}
// 持仓的卖出触发判断（预计算，避免模板内嵌套引号/正则）
function holdingInfo(sym: string, r: TradeResult): { action: string; reason: string; color: string; cls: string } {
  const h = holdingFor(sym)
  if (!h) return { action: '', reason: '', color: '#757575', cls: '' }
  const cur = r.current_price ?? 0
  const sell = r.latest_sell_5min
  let action = '持有'
  let reason = `买入价 ${h.buyPrice}，止损 ${h.stopLoss} / 止盈 ${h.takeProfit}`
  if (cur <= h.stopLoss) { action = '止损卖出'; reason = `当前价 ${cur} 触及止损线 ${h.stopLoss}` }
  else if (cur >= h.takeProfit) { action = '止盈卖出'; reason = `当前价 ${cur} 触及止盈线 ${h.takeProfit}` }
  else if (sell && (sell.age_bars ?? 999) <= 8) { action = '信号卖出'; reason = `5min ${sellTypeLabel(sell.type)} 出现（${sell.age_bars} 根前）` }
  return { action, reason, color: actionColor(action), cls: action.replace(/\s/g, '') }
}

function resultFor(sym: string): TradeResult | undefined {
  return results.value.find((x) => x.symbol === sym)
}

// 持仓卡片预计算（避免模板内用 ! 非空断言）
interface HoldingCard {
  symbol: string
  buyPrice: number
  buyDate: string
  stopLoss: number
  takeProfit: number
  cur: number | null
  pnl: number | null
  action: string
  reason: string
  color: string
  cls: string
  hasResult: boolean
}
const holdingCards = computed<HoldingCard[]>(() =>
  holdings.value.map((h) => {
    const r = resultFor(h.symbol)
    if (!r) {
      return { symbol: h.symbol, buyPrice: h.buyPrice, buyDate: h.buyDate, stopLoss: h.stopLoss, takeProfit: h.takeProfit, cur: null, pnl: null, action: '', reason: '待刷新信号', color: '#757575', cls: '', hasResult: false }
    }
    const info = holdingInfo(h.symbol, r)
    return {
      symbol: h.symbol, buyPrice: h.buyPrice, buyDate: h.buyDate,
      stopLoss: h.stopLoss, takeProfit: h.takeProfit,
      cur: r.current_price, pnl: pnlPct(h.symbol, r.current_price),
      action: info.action, reason: info.reason, color: info.color, cls: info.cls,
      hasResult: true,
    }
  })
)

onMounted(() => {
  loadHoldings()
  // 不自动 fetchSignals：3标的~55s 会占满 uvicorn，切到回放模式时回放请求会排队挂起。
  // 让用户手动点「拉取交易信号」/「回放」，避免请求竞争。
})

// ── 历史回放 ──
const replaySymbol = ref('SH:600000')
const replayLoading = ref(false)
const replayError = ref('')
const replayData = ref<ReplayResult | null>(null)

async function runReplay() {
  const s = replaySymbol.value.replace(/[:：]/g, '').trim()
  const m = s.match(/^(SH|SZ|BJ)(\d{6})$/)
  if (!m) { replayError.value = '标的格式错，如 SH:600000'; return }
  replayLoading.value = true
  replayError.value = ''
  replayData.value = null
  try {
    replayData.value = await chanlunTradeReplay({
      market: m[1], code: m[2],
      stop_loss_pct: stopLossPct.value,
      take_profit_pct: takeProfitPct.value,
      count: Math.max(countBars.value, 600),
    })
  } catch (e: any) {
    replayError.value = e?.message || String(e)
  } finally {
    replayLoading.value = false
  }
}

function reasonCls(r: string): string {
  if (r === '止盈') return 'rs-tp'
  if (r === '止损') return 'rs-sl'
  if (r.startsWith('5min')) return 'rs-sell'
  return 'rs-hold'
}
</script>

<template>
  <div class="trade-view">
    <h2>⚡ 实战交易信号</h2>
    <p class="subtitle">30min 买点入场 → 5min 卖点出场 → 止损/止盈。信号来自真实缠论分析，买入价用确认日收盘（分型右根走完，缠论62/65课原文查证），非事后笔终点价。</p>

    <!-- 模式切换 -->
    <div class="mode-tabs">
      <button :class="['tab', { active: mode === 'signals' }]" @click="mode = 'signals'">⚡ 当日信号</button>
      <button :class="['tab', { active: mode === 'replay' }]" @click="mode = 'replay'">📊 历史回放</button>
    </div>

    <!-- ===== 当日信号模式 ===== -->
    <template v-if="mode === 'signals'">
    <!-- 参数 + 选股 -->
    <div class="control-bar">
      <div class="param-group">
        <label>止损 <input type="number" v-model.number="stopLossPct" min="1" max="20" step="0.5"> %</label>
        <label>止盈 <input type="number" v-model.number="takeProfitPct" min="1" max="50" step="1"> %</label>
        <label>30min根数 <input type="number" v-model.number="countBars" min="100" max="800" step="50"></label>
      </div>
      <div class="date-group">
        <label>选股日 <input type="date" v-model="selectDate"></label>
        <button class="btn-screen" :disabled="screening" @click="runScreen">
          {{ screening ? '选股中…' : '🌳 树粮菜选股定池' }}
        </button>
        <span class="screen-msg">{{ screenMsg }}</span>
      </div>
      <div class="pool-group">
        <label>标的池（SH:600000,SZ:002594…）</label>
        <input class="pool-input" v-model="poolInput" placeholder="SH:600000,SH:600519,…" @keyup.enter="fetchSignals">
        <button class="btn-fetch" :disabled="loading" @click="fetchSignals">
          {{ loading ? '分析中…' : '🔍 拉取交易信号' }}
        </button>
      </div>
    </div>

    <div v-if="errorMsg" class="error-banner">{{ errorMsg }}</div>

    <!-- 持仓卡（已持仓标的的卖出监控）-->
    <div v-if="holdings.length" class="holdings-section">
      <h3>持仓监控（{{ holdings.length }}）</h3>
      <div class="holding-cards">
        <div v-for="hc in holdingCards" :key="hc.symbol" class="holding-card">
          <div class="holding-head">
            <span class="sym">{{ hc.symbol }}</span>
            <span class="buy-info">买@{{ hc.buyPrice }} ({{ hc.buyDate?.slice(0, 10) }})</span>
            <button class="btn-remove" @click="removeHolding(hc.symbol)">✕ 清仓</button>
          </div>
          <div v-if="hc.hasResult" class="holding-body">
            <span>现价 <b>{{ hc.cur }}</b></span>
            <span :class="['pnl', (hc.pnl ?? 0) >= 0 ? 'pos' : 'neg']">
              {{ hc.pnl ?? '—' }}%
            </span>
            <span class="lines">止损 {{ hc.stopLoss }} / 止盈 {{ hc.takeProfit }}</span>
            <span :class="['ha', hc.cls]">{{ hc.action }}</span>
            <span class="ha-reason">{{ hc.reason }}</span>
          </div>
          <div v-else class="holding-body">
            <span class="ha-reason">{{ hc.reason }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 信号卡片 -->
    <div class="results-section">
      <h3>交易信号（{{ results.length }} 只）</h3>
      <div v-if="loading" class="loading">正在对每只标的跑 30min/5min 联立分析…</div>
      <div class="signal-grid">
        <div v-for="r in results" :key="r.symbol" :class="['signal-card', { error: r.error }]">
          <div v-if="r.error" class="card-error">{{ r.symbol }}: {{ r.error }}</div>
          <template v-else>
            <div class="card-head">
              <span class="sym">{{ r.symbol }}</span>
              <span class="price">现价 {{ r.current_price }}</span>
              <span class="last-date">{{ r.last_date?.slice(5, 16) }}</span>
            </div>
            <!-- 操作建议 -->
            <div :class="['action-bar', actionCls(r.action)]">
              <span :class="['action', actionCls(r.action)]">{{ r.action }}</span>
              <span class="action-reason">{{ r.action_reason }}</span>
            </div>
            <!-- 30min 买点 -->
            <div v-if="r.latest_buy" class="signal-block buy">
              <div class="block-title">📈 30min 买点：{{ buyTypeLabel(r.latest_buy.type) }}</div>
              <div class="block-detail">
                <span>笔终日 {{ r.latest_buy.date?.slice(5, 16) }}</span>
                <span>确认日 <b>{{ r.latest_buy.confirm_date?.slice(5, 16) || '未确认' }}</b></span>
                <span>确认价 <b>{{ r.latest_buy.confirm_price ?? '—' }}</b></span>
                <span :class="['age', (r.latest_buy.age_bars ?? 0) > 8 ? 'stale' : 'fresh']">
                  老化 {{ r.latest_buy.age_bars }} 根
                </span>
                <span :class="['qt', qtCls(r.latest_buy.qt_state)]">
                  区间套 {{ qtLabel(r.latest_buy.qt_state) }}
                </span>
                <span :class="['dev', (r.latest_buy.price_deviation_pct ?? 0) >= 0 ? 'pos' : 'neg']">
                  偏离 {{ r.latest_buy.price_deviation_pct }}%
                </span>
              </div>
            </div>
            <div v-else class="signal-block none">无 30min 买点</div>
            <!-- 5min 卖点 -->
            <div v-if="r.latest_sell_5min" class="signal-block sell">
              <div class="block-title">📉 5min 卖点：{{ sellTypeLabel(r.latest_sell_5min.type) }}</div>
              <div class="block-detail">
                <span>{{ r.latest_sell_5min.date?.slice(5, 16) }}</span>
                <span :class="['age', (r.latest_sell_5min.age_bars ?? 0) > 8 ? 'stale' : 'fresh']">
                  老化 {{ r.latest_sell_5min.age_bars }} 根
                </span>
              </div>
            </div>
            <!-- 止损止盈线 -->
            <div v-if="r.stop_loss_price" class="lines-block">
              <span class="line sl">止损 {{ r.stop_loss_price }} ({{ stopLossPct }}%)</span>
              <span class="line tp">止盈 {{ r.take_profit_price }} ({{ takeProfitPct }}%)</span>
            </div>
            <!-- 持仓操作 -->
            <div class="holding-ops">
              <button v-if="r.action === '可买' && !holdingFor(r.symbol)"
                      class="btn-buy" @click="addHolding(r)">
                📝 已买入@{{ r.latest_buy?.confirm_price }}
              </button>
              <span v-if="holdingFor(r.symbol)" class="holding-tag">已持仓</span>
            </div>
          </template>
        </div>
      </div>
    </div>
    </template><!-- 当日信号模式结束 -->

    <!-- ===== 历史回放模式 ===== -->
    <template v-if="mode === 'replay'">
      <div class="replay-bar">
        <label>标的 <input class="replay-sym" v-model="replaySymbol" placeholder="SH:600000" @keyup.enter="runReplay"></label>
        <span class="replay-params">止损 {{ stopLossPct }}% / 止盈 {{ takeProfitPct }}% / {{ Math.max(countBars, 600) }}根</span>
        <button class="btn-replay" :disabled="replayLoading" @click="runReplay">📊 回放</button>
      </div>
      <div v-if="replayError" class="error-banner">{{ replayError }}</div>
      <div v-if="replayLoading" class="loading">正在回放所有30min买点→逐根跟踪止损/止盈/5min卖点…</div>
      <div v-if="replayData && !replayData.error" class="replay-result">
        <div class="replay-summary">
          <div class="sum-card"><span class="sum-label">标的</span><span class="sum-val">{{ replayData.symbol }}</span></div>
          <div class="sum-card"><span class="sum-label">总交易</span><span class="sum-val">{{ replayData.summary.total }}</span></div>
          <div class="sum-card"><span class="sum-label">胜率</span><span :class="['sum-val', replayData.summary.win_rate >= 50 ? 'pos' : 'neg']">{{ replayData.summary.win_rate }}%</span></div>
          <div class="sum-card"><span class="sum-label">均收</span><span :class="['sum-val', replayData.summary.avg_return >= 0 ? 'pos' : 'neg']">{{ replayData.summary.avg_return }}%</span></div>
          <div class="sum-card"><span class="sum-label">总收</span><span :class="['sum-val', replayData.summary.total_return >= 0 ? 'pos' : 'neg']">{{ replayData.summary.total_return }}%</span></div>
          <div class="sum-card"><span class="sum-label">最大盈/亏</span><span class="sum-val">{{ replayData.summary.max_win }}% / {{ replayData.summary.max_loss }}%</span></div>
        </div>
        <div class="reason-dist">
          <span class="rd-title">出场原因分布：</span>
          <span v-for="(v, k) in replayData.summary.by_reason" :key="k" :class="['rd-chip', reasonCls(String(k))]">
            {{ k }} ×{{ v.count }} (均{{ v.avg }}%)
          </span>
        </div>
        <table class="replay-table">
          <thead><tr><th>买点</th><th>买入日</th><th>买价</th><th>出场原因</th><th>出场日</th><th>卖价</th><th>收益</th><th>持仓</th></tr></thead>
          <tbody>
            <tr v-for="(t, i) in replayData.trades" :key="i">
              <td>{{ t.buy_type }}</td>
              <td>{{ t.buy_date }}</td>
              <td>{{ t.buy_price }}</td>
              <td :class="reasonCls(t.exit_reason)">{{ t.exit_reason }}</td>
              <td>{{ t.exit_date }}</td>
              <td>{{ t.exit_price }}</td>
              <td :class="t.return_pct >= 0 ? 'pos' : 'neg'">{{ t.return_pct }}%</td>
              <td>{{ t.hold_bars }}根</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template><!-- 历史回放模式结束 -->
  </div>
</template>

<style scoped>
.trade-view { padding: 16px 20px; max-width: 1400px; margin: 0 auto; }
.subtitle { color: #888; font-size: 13px; margin: -4px 0 12px; }
.control-bar { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; padding: 12px; background: #f7f8fa; border-radius: 8px; margin-bottom: 12px; }
.param-group, .date-group, .pool-group { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.param-group label, .date-group label { font-size: 13px; color: #555; display: flex; align-items: center; gap: 4px; }
input[type=number] { width: 56px; padding: 3px 6px; border: 1px solid #ccc; border-radius: 4px; }
input[type=date] { padding: 3px 6px; border: 1px solid #ccc; border-radius: 4px; }
.pool-input { width: 340px; padding: 4px 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px; }
.btn-screen, .btn-fetch { padding: 5px 12px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; }
.btn-screen { background: #66bb6a; color: #fff; }
.btn-fetch { background: #1976d2; color: #fff; }
.btn-screen:disabled, .btn-fetch:disabled { opacity: .5; }
.screen-msg { font-size: 12px; color: #888; }
.error-banner { background: #ffebee; color: #c62828; padding: 8px 12px; border-radius: 4px; margin-bottom: 10px; font-size: 13px; }
.loading { color: #888; padding: 20px; text-align: center; }
h3 { font-size: 15px; margin: 16px 0 8px; color: #333; }
.holdings-section { background: #fff3e0; padding: 12px; border-radius: 8px; margin-bottom: 12px; }
.holding-cards { display: flex; flex-direction: column; gap: 8px; }
.holding-card { background: #fff; border: 1px solid #ffcc80; border-radius: 6px; padding: 8px 12px; }
.holding-head { display: flex; align-items: center; gap: 12px; }
.holding-head .sym { font-weight: bold; font-size: 14px; }
.buy-info { color: #555; font-size: 13px; }
.holding-body { display: flex; gap: 16px; align-items: center; margin-top: 6px; font-size: 13px; flex-wrap: wrap; }
.pnl.pos { color: #d32f2f; font-weight: bold; }
.pnl.neg { color: #1565c0; font-weight: bold; }
.lines { color: #888; }
.btn-remove { margin-left: auto; background: none; border: 1px solid #ccc; border-radius: 4px; cursor: pointer; font-size: 12px; padding: 2px 8px; }
.signal-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 12px; }
.signal-card { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px; }
.signal-card.error { border-color: #ef9a9a; background: #ffebee; }
.card-error { color: #c62828; font-size: 13px; }
.card-head { display: flex; align-items: baseline; gap: 10px; margin-bottom: 8px; }
.card-head .sym { font-weight: bold; font-size: 16px; }
.card-head .price { color: #d32f2f; font-size: 14px; }
.card-head .last-date { color: #aaa; font-size: 12px; margin-left: auto; }
.action-bar { border-left: 4px solid #757575; padding: 6px 10px; background: #f5f5f5; border-radius: 0 4px 4px 0; margin-bottom: 8px; }
.action { font-weight: bold; font-size: 14px; margin-right: 8px; }
.action-reason { font-size: 12px; color: #555; }
.signal-block { padding: 8px; border-radius: 4px; margin-bottom: 6px; font-size: 13px; }
.signal-block.buy { background: #fff8e1; }
.signal-block.sell { background: #e3f2fd; }
.signal-block.none { color: #aaa; text-align: center; }
.block-title { font-weight: bold; margin-bottom: 4px; }
.block-detail { display: flex; flex-wrap: wrap; gap: 10px; font-size: 12px; color: #555; }
.age.fresh { color: #2e7d32; }
.age.stale { color: #c62828; }
.dev.pos { color: #d32f2f; }
.dev.neg { color: #1565c0; }
.lines-block { display: flex; gap: 12px; margin-top: 6px; font-size: 13px; }
.line.sl { color: #1565c0; }
.line.tp { color: #d32f2f; }
.holding-ops { margin-top: 8px; }
.btn-buy { background: #d32f2f; color: #fff; border: none; border-radius: 4px; padding: 4px 10px; cursor: pointer; font-size: 12px; }
.holding-tag { color: #888; font-size: 12px; }
/* action/qt class colors */
.act-buy, .action-bar.act-buy { border-left-color: #d32f2f; }
.act-buy .action, .action.act-buy { color: #d32f2f; }
.act-sell, .action-bar.act-sell { border-left-color: #1565c0; }
.act-sell .action, .action.act-sell { color: #1565c0; }
.act-wait, .action-bar.act-wait { border-left-color: #757575; }
.act-wait .action, .action.act-wait { color: #757575; }
.qt-conf { color: #e53935; }
.qt-rej { color: #9e9e9e; }
.qt-assume { color: #fb8c00; }
.qt-none { color: #999; }
.ha.act-buy { color: #d32f2f; }
.ha.act-sell { color: #1565c0; }
.ha.act-wait { color: #757575; }

/* ── 历史回放 ── */
.mode-tabs { display: flex; gap: 4px; margin-bottom: 12px; }
.mode-tabs .tab { padding: 6px 16px; border: 1px solid #ddd; background: #f5f5f5; cursor: pointer; border-radius: 6px 6px 0 0; font-size: 14px; }
.mode-tabs .tab.active { background: #1976d2; color: #fff; border-color: #1976d2; }
.replay-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.replay-sym { width: 140px; padding: 4px 8px; border: 1px solid #ccc; border-radius: 4px; }
.replay-params { color: #666; font-size: 13px; }
.btn-replay { padding: 6px 16px; background: #7b1fa2; color: #fff; border: none; border-radius: 4px; cursor: pointer; }
.btn-replay:disabled { opacity: 0.5; }
.replay-summary { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.sum-card { background: #f5f5f5; padding: 8px 14px; border-radius: 6px; display: flex; flex-direction: column; align-items: center; min-width: 80px; }
.sum-label { font-size: 11px; color: #888; }
.sum-val { font-size: 18px; font-weight: bold; }
.sum-val.pos { color: #d32f2f; }
.sum-val.neg { color: #2e7d32; }
.reason-dist { margin-bottom: 12px; font-size: 13px; }
.rd-title { color: #666; margin-right: 8px; }
.rd-chip { display: inline-block; padding: 2px 8px; margin: 2px; border-radius: 10px; font-size: 12px; }
.rd-chip.rs-tp { background: #ffe0e0; color: #d32f2f; }
.rd-chip.rs-sl { background: #e0e0ff; color: #1565c0; }
.rd-chip.rs-sell { background: #fff3e0; color: #e65100; }
.rd-chip.rs-hold { background: #f0f0f0; color: #666; }
.replay-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.replay-table th { background: #f5f5f5; padding: 6px 8px; text-align: left; border-bottom: 2px solid #ddd; }
.replay-table td { padding: 5px 8px; border-bottom: 1px solid #eee; }
.replay-table td.pos { color: #d32f2f; }
.replay-table td.neg { color: #2e7d32; }
.replay-table td.rs-tp { color: #d32f2f; font-weight: bold; }
.replay-table td.rs-sl { color: #1565c0; }
.replay-table td.rs-sell { color: #e65100; }
</style>
