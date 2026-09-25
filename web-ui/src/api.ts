// 后端 API 封装。统一 fetch + 错误处理，返回类型化结果。
// 开发期通过 vite proxy 走 /api（同源），生产期由 FastAPI 同源托管。

import type {
  ApiError,
  BacktestRequest,
  BacktestResult,
  Bar,
  Category,
  DiagnosisResult,
  MultiStrategyBacktestRequest,
  OptimizeAllBacktestRequest,
  OptimizeBacktestRequest,
  PortfolioBacktestRequest,
  SavedStrategy,
  SavedStrategyCreate,
  SavedStrategyListResponse,
  ServerHostInfo,
  ServerHostListResponse,
  ServerSwitchResult,
  StrategiesResponse,
  TaskListResponse,
  TaskState,
  TaskSubmitResponse,
  MultiStockComparisonResponse,
  AdviceSimulateResult,
} from './types'
import {
  barsCacheKey,
  loadBarsSeries,
  saveBarsSeries,
} from './utils/barsCache'

const BASE = '/api/v1'

/** 把未知错误格式化为用户可读的消息（网络错误给友好提示）。 */
export function formatError(e: unknown): string {
  if (e instanceof TypeError && e.message.includes('fetch')) {
    return '网络错误：无法连接后端服务，请确认 easy-tdx serve 已启动'
  }
  return e instanceof Error ? e.message : String(e)
}

/** 重启窗口内网关/SPA 兜底可能返回 HTML（D16），给出可读提示而非 JSON.parse 报错。 */
const SERVICE_RESTARTING_MSG = '服务正在重启，请稍候重试'

/** V721: D16 非 JSON 响应防御——content-type 非 application/json 时抛友好错误。 */
async function parseJson(resp: Response): Promise<unknown> {
  if (!(resp.headers.get('content-type') ?? '').includes('application/json')) {
    throw new Error(SERVICE_RESTARTING_MSG)
  }
  return resp.json()
}

/** 把 Response 解析为 ApiError 抛出（后端统一错误格式 {error, detail}）。 */
async function throwError(resp: Response): Promise<never> {
  // V721: D16 错误体也先验 content-type，SPA index.html 兜底不再炸出难懂报错
  if (!(resp.headers.get('content-type') ?? '').includes('application/json')) {
    throw new Error(`${resp.status} ${resp.statusText}（${SERVICE_RESTARTING_MSG}）`)
  }
  let detail = `${resp.status} ${resp.statusText}`
  try {
    const body = (await resp.json()) as ApiError
    if (body?.detail) detail = body.detail
  } catch {
    // 非 JSON 错误体，用 statusText
  }
  throw new Error(detail)
}

/** 枚举预置策略 + 参数 schema。 */
export async function fetchStrategies(): Promise<StrategiesResponse> {
  const resp = await fetch(`${BASE}/backtest/strategies`)
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as StrategiesResponse
}

/**
 * 按标的取 K 线行情（OHLCV）。
 *
 * 后端 /bars 单次最多 800 根。当 startDate 到 endDate 跨度超过 800 根时，
 * 自动分页拉取（start=0, 800, 1600...）拼接，直到覆盖 startDate 或达上限。
 * 可选 startDate/endDate 对结果做闭区间过滤（ISO 日期字符串，如 "2024-01-01"）。
 */
const MAX_PAGES = 10 // 翻页上限：10 × 800 = 8000 根（约 32 年日线）

// ── V724: K 线历史本地缓存（IndexedDB）─────────────────────────────────────
// 已收盘历史序列存浏览器本地；重复查看同一标的时不再向服务器翻页重拉。
// 策略：缓存命中且请求窗口可满足 → 只取「缓存末日之后」的增量（1 次小请求）
// 校准尾部；除权导致前复权历史重算（价格整体变化）→ 自动检测并整体重取。
const BARS_SAMPLE_STRIDE = 37 // 除权检测采样步长
const BARS_TAIL_SAMPLE = 5 // 除权检测尾部采样根数

function cacheDay(b: Bar): string {
  return b.datetime.slice(0, 10)
}

/** 采样比对缓存与最新数据的 close：抽样一致才算缓存可信（前复权重算检测）。 */
function cacheLooksValid(cached: Bar[], fresh: Bar[]): boolean {
  if (!cached.length || !fresh.length) return true
  const freshIdx = new Map<string, Bar>()
  for (const b of fresh) freshIdx.set(cacheDay(b), b)
  const stride = Math.max(1, BARS_SAMPLE_STRIDE)
  const samples: Bar[] = []
  for (let i = 0; i < cached.length; i += stride) samples.push(cached[i])
  for (let i = Math.max(0, cached.length - BARS_TAIL_SAMPLE); i < cached.length; i++) {
    samples.push(cached[i])
  }
  for (const s of samples) {
    const f = freshIdx.get(cacheDay(s))
    if (!f) continue // 增量覆盖不到的采样点跳过（无法证伪即信任）
    if (Math.abs(f.close - s.close) > 1e-6) return false
  }
  return true
}

/**
 * 请求「缓存末日之后」的增量（含末日当天，便于对齐校准）。
 * endDate 缺省 = 最新。start_date 早于缓存末日一格以上时绕过缓存，
 * 走服务端区间直达取数（fetch_bars_range 一次往返）。
 */
async function fetchBarsIncrement(
  market: string,
  code: string,
  category: Category,
  lastDay: string,
  endDate?: string,
): Promise<Bar[]> {
  const params = new URLSearchParams({
    market,
    code,
    category,
    start_date: lastDay,
  })
  if (endDate) params.set('end_date', endDate)
  const resp = await fetch(`${BASE}/bars?${params}`)
  if (!resp.ok) await throwError(resp)
  const body = (await parseJson(resp)) as { data: Record<string, unknown>[] }
  return body.data.map((row) => normalizeBar(row))
}

export async function fetchBars(
  market: string,
  code: string,
  category: Category,
  startDate?: string,
  endDate?: string,
  maxCount?: number,
): Promise<Bar[]> {
  // ── 缓存快速路径 ────────────────────────────────────────────────
  // 无 startDate（=最新窗口）或 startDate 在缓存范围内，且 endDate 未早于
  // 缓存末日时，可用缓存 + 尾部增量合成结果，避免整段翻页重拉。
  const key = barsCacheKey(market, code, category)
  const cached = await loadBarsSeries(key)
  // 窗口起点落在缓存范围内即可走缓存：endDate 早于缓存末日 = 窗口完全在
  // 缓存内（直接用）；endDate 晚于缓存末日 = 增量校准到 endDate 为止。
  const cacheUsable =
    cached !== null && (!startDate || startDate >= cacheDay(cached[0]))

  if (cached && cacheUsable) {
    // 无显式窗口 = 看最新：增量取缓存末日之后（endDate 缺省到最新）
    // 有窗口但末端早于缓存末日：缓存自身即可满足，无需联网
    const needFresh = !endDate || endDate >= cacheDay(cached[cached.length - 1])
    if (needFresh) {
      try {
        const increment = await fetchBarsIncrement(
          market,
          code,
          category,
          cacheDay(cached[cached.length - 1]),
          endDate,
        )
        const incByDay = new Map<string, Bar>()
        for (const b of increment) incByDay.set(cacheDay(b), b)
        // 除权检测：采样比对缓存段 close，价格被前复权重算 → 整体重取
        if (!cacheLooksValid(cached, increment)) {
          const fresh = await fetchBarsDirect(market, code, category, startDate, endDate, maxCount)
          if (!startDate && !endDate && !maxCount) {
            void saveBarsSeries(key, fresh)
          }
          return fresh
        }
        // 合并：缓存段 + 增量段（增量含末日当天重叠一根，按日期覆盖）
        let merged = cached.slice()
        for (const b of increment) {
          const day = cacheDay(b)
          const i = merged.findIndex((c) => cacheDay(c) === day)
          if (i >= 0) merged[i] = b
          else if (day > cacheDay(merged[merged.length - 1])) merged.push(b)
          // 增量里的更早日期（缓存缺口）：忽略——序列仍连续，缺口不影响缠论分析
        }
        merged.sort((a, b) => a.datetime.localeCompare(b.datetime))
        let bars = applyBarsWindow(merged, startDate, endDate, maxCount)
        // 无窗口全量结果回填缓存（下次查看免增量请求）
        if (!startDate && !endDate && !maxCount) {
          void saveBarsSeries(key, bars)
        }
        return bars
      } catch {
        // 增量请求失败（断网/服务器忙）→ 直接用缓存渲染，静默降级
        return applyBarsWindow(cached, startDate, endDate, maxCount)
      }
    }
    return applyBarsWindow(cached, startDate, endDate, maxCount)
  }

  // ── 常规路径：翻页直取（无缓存 / 窗口早于缓存起点 / 请求被缓存否定）──
  const bars = await fetchBarsDirect(market, code, category, startDate, endDate, maxCount)
  // 无窗口全量结果回填缓存
  if (!startDate && !endDate && !maxCount) {
    void saveBarsSeries(key, bars)
  }
  return bars
}

/** 按窗口闭区间过滤 + maxCount 尾截（fetchBars 两路径共用的收尾）。 */
function applyBarsWindow(cached: Bar[], startDate?: string, endDate?: string, maxCount?: number): Bar[] {
  let bars = cached
  if (startDate) bars = bars.filter((b) => b.datetime.slice(0, 10) >= startDate)
  if (endDate) bars = bars.filter((b) => b.datetime.slice(0, 10) <= endDate)
  if (maxCount && bars.length > maxCount) {
    bars = bars.slice(bars.length - maxCount)
  }
  return bars
}

/** 常规翻页直取（原 fetchBars 主体，未走缓存的路径）。 */
async function fetchBarsDirect(
  market: string,
  code: string,
  category: Category,
  startDate?: string,
  endDate?: string,
  maxCount?: number,
): Promise<Bar[]> {
  let allBars: Bar[] = []
  for (let page = 0; page < MAX_PAGES; page++) {
    const params = new URLSearchParams({
      market,
      code,
      category,
      count: '800',
      start: String(page * 800),
    })
    const resp = await fetch(`${BASE}/bars?${params}`)
    if (!resp.ok) await throwError(resp)
    const body = (await parseJson(resp)) as { data: Record<string, unknown>[] }
    const pageBars = body.data.map((row) => normalizeBar(row))
    if (pageBars.length === 0) break // 无更多数据

    allBars = allBars.concat(pageBars)

    // 若已覆盖到 startDate（本页最早一根 ≤ startDate），停止翻页
    if (startDate && pageBars.length > 0) {
      const oldest = pageBars[pageBars.length - 1].datetime.slice(0, 10)
      if (oldest <= startDate) break
    }
    // 不足 800 根说明已到数据起点
    if (pageBars.length < 800) break
  }

  // 翻页拼接后按时间正序排序：每页内部是正序，但页间是逆序
  // （page1=最新段，page2=更旧段），concat 后需排序保证整体正序，
  // 否则引擎/图表只正确处理第一页的数据。
  allBars.sort((a, b) => a.datetime.localeCompare(b.datetime))
  return applyBarsWindow(allBars, startDate, endDate, maxCount)
}

/**
 * V722: 增量加载更早的历史 K 线（图表「往前看」）。
 *
 * 走服务端 /bars?lookback=N 循环翻页取前 earliest 之前的 moreCount 根，
 * 返回按时间升序的 Bar 数组（不含当前已加载窗口——调用方自行拼接）。
 * 服务端翻页会自动去重，此处按 earliest 严格过滤旧段。
 */
export async function loadEarlierBars(
  market: string,
  code: string,
  category: Category,
  earliest: string,
  moreCount: number = 800,
): Promise<Bar[]> {
  // 估算需要的总根数：先取 earliest 到最新一页（800），再按起始位置翻页。
  // 简化策略：直接请求 lookback = 已知最早往前推 moreCount 根，由服务端翻页。
  // 由于前端不知道 earliest 距今多少根，用迭代翻页（每次 800）直到越过 earliest。
  const target = earliest.slice(0, 10)
  const collected: Bar[] = []
  let page = 0
  while (page < MAX_PAGES) {
    const params = new URLSearchParams({
      market,
      code,
      category,
      count: '800',
      start: String(page * 800),
    })
    const resp = await fetch(`${BASE}/bars?${params}`)
    if (!resp.ok) await throwError(resp)
    const body = (await parseJson(resp)) as { data: Record<string, unknown>[] }
    const pageBars = body.data.map((row) => normalizeBar(row))
    if (pageBars.length === 0) break
    collected.push(...pageBars)
    const oldest = pageBars[pageBars.length - 1].datetime.slice(0, 10)
    // 已越过目标日期（页面里最早一根 ≤ earliest）→ 收齐
    if (oldest <= target) break
    if (pageBars.length < 800) break // 到数据起点
    page += 1
  }
  collected.sort((a, b) => a.datetime.localeCompare(b.datetime))
  // 只保留 earliest 之前的 moreCount 根（不含 earliest 本身）
  const earlier = collected.filter((b) => b.datetime.slice(0, 10) < target)
  return earlier.slice(Math.max(0, earlier.length - moreCount))
}

/** 把后端 bars 的单条记录归一化为统一 Bar（datetime 字段）。 */
function normalizeBar(row: Record<string, unknown>): Bar {
  const raw = (row.datetime ?? row.date) as string | undefined
  if (!raw) throw new Error('行情数据缺少 datetime/date 字段')
  return {
    datetime: raw.slice(0, 19).replace(' ', 'T'),
    open: Number(row.open),
    high: Number(row.high),
    low: Number(row.low),
    close: Number(row.close),
    vol: Number(row.vol),
    amount: Number(row.amount),
  }
}

/**
 * V723: 按日期区间取 K 线（服务端一次往返直达，闭区间）。
 *
 * 后端 /bars?start_date= 由 fetch_bars_range 从最新 bar 向过去循环翻页，
 * 直达 [start_date, end_date] 区间——与前端自行翻页（fetchBars）相比，
 * 无 8000 根客户端上限，也不受响应体大小拖累。
 * endDate 缺省 = 到最新一根。
 */
export async function fetchBarsRange(
  market: string,
  code: string,
  category: Category,
  startDate: string,
  endDate?: string,
): Promise<Bar[]> {
  const params = new URLSearchParams({
    market,
    code,
    category,
    start_date: startDate,
  })
  if (endDate) params.set('end_date', endDate)
  const resp = await fetch(`${BASE}/bars?${params}`)
  if (!resp.ok) await throwError(resp)
  const body = (await parseJson(resp)) as { data: Record<string, unknown>[] }
  return body.data.map((row) => normalizeBar(row))
}

/** 同步回测（内联 OHLCV，快速）。 */
export async function runBacktest(req: BacktestRequest): Promise<BacktestResult> {
  const resp = await fetch(`${BASE}/backtest/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as BacktestResult
}

/** 提交后台回测任务，返回 task_id。 */
export async function submitBacktestTask(req: BacktestRequest): Promise<TaskSubmitResponse> {
  const resp = await fetch(`${BASE}/backtest/run/async`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as TaskSubmitResponse
}

/** 提交组合回测后台任务，返回 task_id。 */
export async function submitPortfolioTask(
  req: PortfolioBacktestRequest,
): Promise<TaskSubmitResponse> {
  const resp = await fetch(`${BASE}/backtest/portfolio/run/async`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as TaskSubmitResponse
}

/** 提交多策略组合回测后台任务（资金分仓），返回 task_id。 */
export async function submitMultiStrategyTask(
  req: MultiStrategyBacktestRequest,
): Promise<TaskSubmitResponse> {
  const resp = await fetch(`${BASE}/backtest/multi-strategy/run/async`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as TaskSubmitResponse
}

/** 提交参数网格寻优后台任务，返回 task_id。 */
export async function submitOptimizeTask(
  req: OptimizeBacktestRequest,
): Promise<TaskSubmitResponse> {
  const resp = await fetch(`${BASE}/backtest/optimize/run/async`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as TaskSubmitResponse
}

/** 提交「一键寻优所有策略」后台任务，返回 task_id。 */
export async function submitOptimizeAllTask(
  req: OptimizeAllBacktestRequest,
): Promise<TaskSubmitResponse> {
  const resp = await fetch(`${BASE}/backtest/optimize-all/run/async`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as TaskSubmitResponse
}

/** 查询后台任务状态（轮询用）。 */
export async function fetchTask(taskId: string): Promise<TaskState> {
  const resp = await fetch(`${BASE}/backtest/tasks/${taskId}`)
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as TaskState
}

/** 列出最近任务摘要（供对比页选择）。 */
export async function fetchTaskList(limit = 20): Promise<TaskListResponse> {
  const resp = await fetch(`${BASE}/backtest/tasks?limit=${limit}`)
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as TaskListResponse
}

/**
 * 提交后台任务并轮询直到 done/failed。
 * @param req 回测请求
 * @param onPoll 每次轮询回调（可选，用于更新 UI 进度）
 * @param intervalMs 轮询间隔（默认 300ms）
 * @param timeoutMs 总超时（默认 120s）
 */
export async function runBacktestWithPolling(
  req: BacktestRequest,
  onPoll?: (state: TaskState) => void,
  intervalMs = 300,
  timeoutMs = 120_000,
): Promise<TaskState> {
  const { task_id } = await submitBacktestTask(req)
  const start = Date.now()
  while (true) {
    const state = await fetchTask(task_id)
    onPoll?.(state)
    if (state.status === 'done' || state.status === 'failed') return state
    if (Date.now() - start > timeoutMs) {
      throw new Error(`回测任务超时（${timeoutMs / 1000}s）`)
    }
    await new Promise((r) => setTimeout(r, intervalMs))
  }
}

// ── 策略库（已保存策略）──────────────────────────────────────────────────────

/** 列出全部已保存策略（按创建时间倒序）。 */
export async function fetchSavedStrategies(): Promise<SavedStrategyListResponse> {
  const resp = await fetch(`${BASE}/strategies`)
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as SavedStrategyListResponse
}

/** 查看单条已保存策略。 */
export async function fetchSavedStrategy(id: string): Promise<SavedStrategy> {
  const resp = await fetch(`${BASE}/strategies/${id}`)
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as SavedStrategy
}

/** 保存一条策略（含当时的标的上下文与成绩快照）。 */
export async function saveStrategy(req: SavedStrategyCreate): Promise<SavedStrategy> {
  const resp = await fetch(`${BASE}/strategies`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as SavedStrategy
}

/** 删除一条已保存策略。 */
export async function deleteSavedStrategy(id: string): Promise<void> {
  const resp = await fetch(`${BASE}/strategies/${id}`, { method: 'DELETE' })
  if (!resp.ok) await throwError(resp)
}

/** V209: 更新一条已保存策略的快照（策略库「一键重验」后刷新验证结论）。 */
export async function updateStrategySnapshot(
  id: string,
  snapshot: Record<string, unknown>,
): Promise<SavedStrategy> {
  const resp = await fetch(`${BASE}/strategies/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ snapshot }),
  })
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as SavedStrategy
}

// ── 服务器设置 ──────────────────────────────────────────────────────────────

/** 列出所有候选通达信服务器 + 当前使用的 host（不含延迟，需点测速）。 */
export async function fetchServerHosts(): Promise<ServerHostListResponse> {
  const resp = await fetch(`${BASE}/server/hosts`)
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as ServerHostListResponse
}

/** 并发测速全部（或指定）host，返回延迟和可达性。 */
export async function testServerHosts(hosts?: string[]): Promise<ServerHostInfo[]> {
  const resp = await fetch(`${BASE}/server/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hosts: hosts ?? null }),
  })
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as ServerHostInfo[]
}

/** 切换到指定 host（热重连，无需重启服务）。 */
export async function switchServerHost(host: string): Promise<ServerSwitchResult> {
  const resp = await fetch(`${BASE}/server/switch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ host }),
  })
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as ServerSwitchResult
}

// ── 股票诊断 ──────────────────────────────────────────────────────────────

/** 快速诊断单只股票技术面（GET，方便浏览器直接访问）。 */
export async function fetchDiagnosis(market: string, code: string): Promise<DiagnosisResult> {
  const resp = await fetch(`${BASE}/diagnosis/quick?market=${market}&code=${code}`)
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as DiagnosisResult
}

/** V102 建议回放实证：对 3买/3卖 信号生成建议并在历史行情回放。 */
export async function fetchAdviceSimulate(
  market: string,
  code: string,
  category = 'DAY',
  count = 500,
  maxHold = 10,
): Promise<AdviceSimulateResult> {
  const resp = await fetch(`${BASE}/diagnosis/advice-simulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ market, code, category, count, max_hold: maxHold }),
  })
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as AdviceSimulateResult
}

// ── V64: 多股票对比分析 ──────────────────────────────────────────────────────

/** 多股票信号质量对比（V64 新增）。 */
export async function fetchMultiStockComparison(
  stocks: Array<{ market: string; code: string }>,
): Promise<MultiStockComparisonResponse> {
  const resp = await fetch(`${BASE}/diagnosis/multi-stock`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(stocks),
  })
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as MultiStockComparisonResponse
}

// ── v590 选股两步流 ────────────────────────────────────────────────────
export interface StockPickPoolItem {
  symbol: string
  market: string
  code: string
  category: string
  quality_score: number
  detail?: Record<string, unknown>
  post_performance?: unknown
}

export interface StockPickScreenResult {
  date: string
  total: number
  results: StockPickPoolItem[]
  source?: 'local' | 'online'
  updated_at?: string
}

export interface StockPickTimingResult {
  symbol: string
  market?: string
  code?: string
  date?: string
  error?: string
  bars?: Bar[]
  bis?: unknown[]
  xds?: unknown[]
  zss?: unknown[]
  mmds?: unknown[]
  bcs?: unknown[]
  fractals?: unknown[]
  macd?: { dif: number[]; dea: number[]; hist: number[] }
  verdict?: { action: string; signal?: string; confidence?: number; reason?: string; direction?: string }
  novice_advice?: {
    explanation: string
    entry: number | null
    stop: number | null
    target: number | null
    position_note: string
    signal?: string
    direction?: string
  }
  // V709: 多级别递归结构确认（更高一级买卖点对笔级别结论的佐证）
  recursion?: {
    depth_produced: number
    latest: { level: number; signal: string; direction: string; confidence: number; date?: string } | null
    alignment?: 'confirm' | 'conflict' | 'none'
    note?: string
  }
  levels?: Record<string, unknown>
  signal_quality?: {
    summary?: string
    ranking?: {
      type: string
      direction: string
      signals: number
      excess_hit_rate: number
      avg_return: number
      hit_rate: number
      profit_factor: number
      verdict: string
    }[]
    best_buy?: {
      type: string
      hit_rate: number
      excess_hit_rate: number
      avg_return?: number
      signals?: number
      verdict?: string
    } | null
    best_sell?: {
      type: string
      hit_rate: number
      excess_hit_rate: number
      avg_return?: number
      signals?: number
      verdict?: string
    } | null
  }
  structure?: { bi_count: number; zs_count: number; mmd_count: number; bc_count: number }
}

/** 四季判断（市场所处季节与仓位建议，四季判断联动择时排行）。 */
export interface SeasonInfo {
  season: string
  label: string
  color?: string
  description?: string
  strategy?: string
  position_range?: [number, number]
  action?: string
}

/** 第一步：长盈基本面选股池（point-in-time）。 */
export async function stockPickScreen(req: {
  date: string
  markets?: string[]
  pool?: { market: string; code: string }[]
  stock_type?: string
  top_n?: number
}): Promise<StockPickScreenResult> {
  const resp = await fetch(BASE + '/stock-pick/screen', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as StockPickScreenResult
}

/** 全局提醒流（V718）：信号监控 + 今日看板统一写入的自动提醒。 */
export interface MonitorAlert {
  ts?: number
  source?: 'monitor' | 'dashboard'
  stock?: string
  type?: string
  action?: string
  confidence?: number
  date?: string
  msg?: string
  entry?: number | null
  stop?: number | null
  target?: number | null
  position_note?: string
  top_hit_label?: string
  align_label?: string
  season_note?: string
  key?: string
}

export async function monitorAlerts(
  limit = 50,
  source = '',
): Promise<{ alerts: MonitorAlert[]; count: number }> {
  const q = new URLSearchParams({ limit: String(limit) })
  if (source) q.set('source', source)
  const resp = await fetch(BASE + `/monitor/alerts?` + q.toString())
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as { alerts: MonitorAlert[]; count: number }
}

export async function monitorAlertsClear(): Promise<{ ok: boolean; cleared: number }> {
  const resp = await fetch(BASE + '/monitor/alerts/clear', { method: 'POST' })
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as { ok: boolean; cleared: number }
}

/** 「今日可操作」一屏决策看板：提交后台聚合任务（选股+批量择时+四季）。 */
export interface DashboardAction {
  symbol: string
  market?: string
  code?: string
  category?: string
  quality_score?: number | null
  action: string
  confidence: number
  alignLabel: string
  top_hit_label?: string
  top_hit_good?: boolean
  verdict?: { action: string; signal?: string; confidence?: number; reason?: string; direction?: string }
  novice_advice?: {
    explanation: string
    entry: number | null
    stop: number | null
    target: number | null
    position_note: string
    signal?: string
    direction?: string
  }
  recursion?: {
    depth_produced: number
    latest: { level: number; signal: string; direction: string; confidence: number; date?: string } | null
    alignment?: 'confirm' | 'conflict' | 'none'
    note?: string
  }
  signal_quality?: {
    summary?: string
    ranking?: {
      type: string
      direction: string
      signals: number
      excess_hit_rate: number
      avg_return: number
      hit_rate: number
      profit_factor: number
      verdict: string
    }[]
    best_buy?: {
      type: string
      hit_rate: number
      excess_hit_rate: number
      avg_return?: number
      signals?: number
      verdict?: string
    } | null
    best_sell?: {
      type: string
      hit_rate: number
      excess_hit_rate: number
      avg_return?: number
      signals?: number
      verdict?: string
    } | null
  }
  bars?: Bar[]
  bis?: unknown[]
  xds?: unknown[]
  zss?: unknown[]
  mmds?: unknown[]
  bcs?: unknown[]
  fractals?: unknown[]
  macd?: { dif: number[]; dea: number[]; hist: number[] }
}

export interface DashboardResult {
  date: string
  season?: SeasonInfo | null
  summary?: { buy: number; sell: number; wait: number; timed: number; pool: number }
  actions?: DashboardAction[]
}

export async function stockPickDashboardAsync(req: {
  date: string
  markets?: string[]
  pool?: { market: string; code: string }[]
  stock_type?: string
  pool_scope?: string
  top_n?: number
  time_n?: number
  recursion_depth?: number
}): Promise<{ task_id: string; description: string }> {
  const resp = await fetch(BASE + '/stock-pick/dashboard/async', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as { task_id: string; description: string }
}

export async function stockPickDashboardTask(taskId: string): Promise<ScreenTaskState> {
  const resp = await fetch(BASE + `/stock-pick/dashboard/task/${taskId}`)
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as ScreenTaskState
}

/** 第一步异步版：提交长盈选股后台任务（全市场约 13s，进度轮询）。 */
export async function stockPickScreenAsync(req: {
  date: string
  markets?: string[]
  pool?: { market: string; code: string }[]
  stock_type?: string
  pool_scope?: string
  top_n?: number
}): Promise<{ task_id: string; description: string }> {
  const resp = await fetch(BASE + '/stock-pick/screen/async', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as { task_id: string; description: string }
}

/** 轮询选股任务状态（progress 0~100 + 说明 + 结果）。 */
export interface ScreenTaskState {
  task_id: string
  status: 'pending' | 'running' | 'done' | 'failed'
  // 选股任务：{date,total,results}；今日看板任务：{date,season,summary,actions}
  result: Record<string, any> | null
  error?: string
  description?: string
  elapsed?: number
  progress?: number | null
  progress_note?: string
}

export async function stockPickScreenTask(taskId: string): Promise<ScreenTaskState> {
  const resp = await fetch(BASE + `/stock-pick/screen/task/${taskId}`)
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as ScreenTaskState
}

/** 第二步：缠论择时（截至目标日的前复权 K 线 + 缠论结构 + 结论）。 */
export async function stockPickTiming(req: {
  date: string
  symbols: { market: string; code: string }[]
  count?: number
  recursion_depth?: number
}): Promise<{ date: string; results: StockPickTimingResult[]; season?: SeasonInfo | null }> {
  const resp = await fetch(BASE + '/stock-pick/timing', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) await throwError(resp)
  return (await parseJson(resp)) as { date: string; results: StockPickTimingResult[] }
}
