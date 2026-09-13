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

const BASE = '/api/v1'

/** 把未知错误格式化为用户可读的消息（网络错误给友好提示）。 */
export function formatError(e: unknown): string {
  if (e instanceof TypeError && e.message.includes('fetch')) {
    return '网络错误：无法连接后端服务，请确认 easy-tdx serve 已启动'
  }
  return e instanceof Error ? e.message : String(e)
}

/** 把 Response 解析为 ApiError 抛出（后端统一错误格式 {error, detail}）。 */
async function throwError(resp: Response): Promise<never> {
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
  return (await resp.json()) as StrategiesResponse
}

/**
 * 按标的取 K 线行情（OHLCV）。
 *
 * 后端 /bars 单次最多 800 根。当 startDate 到 endDate 跨度超过 800 根时，
 * 自动分页拉取（start=0, 800, 1600...）拼接，直到覆盖 startDate 或达上限。
 * 可选 startDate/endDate 对结果做闭区间过滤（ISO 日期字符串，如 "2024-01-01"）。
 */
const MAX_PAGES = 10 // 翻页上限：10 × 800 = 8000 根（约 32 年日线）

export async function fetchBars(
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
    const body = (await resp.json()) as { data: Record<string, unknown>[] }
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

  // 按日期范围过滤（闭区间）
  let bars = allBars
  if (startDate) bars = bars.filter((b) => b.datetime.slice(0, 10) >= startDate)
  if (endDate) bars = bars.filter((b) => b.datetime.slice(0, 10) <= endDate)
  // 翻页拼接后按时间正序排序：每页内部是正序，但页间是逆序
  // （page1=最新段，page2=更旧段），concat 后需排序保证整体正序，
  // 否则引擎/图表只正确处理第一页的数据。
  bars.sort((a, b) => a.datetime.localeCompare(b.datetime))
  // 可选 maxCount：只保留最新 maxCount 根（与缠论分析窗口对齐，
  // 避免图表显示 8000 根历史但叠加层只覆盖最近 800 根）。
  if (maxCount && bars.length > maxCount) {
    bars = bars.slice(bars.length - maxCount)
  }
  return bars
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

/** 同步回测（内联 OHLCV，快速）。 */
export async function runBacktest(req: BacktestRequest): Promise<BacktestResult> {
  const resp = await fetch(`${BASE}/backtest/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) await throwError(resp)
  return (await resp.json()) as BacktestResult
}

/** 提交后台回测任务，返回 task_id。 */
export async function submitBacktestTask(req: BacktestRequest): Promise<TaskSubmitResponse> {
  const resp = await fetch(`${BASE}/backtest/run/async`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) await throwError(resp)
  return (await resp.json()) as TaskSubmitResponse
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
  return (await resp.json()) as TaskSubmitResponse
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
  return (await resp.json()) as TaskSubmitResponse
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
  return (await resp.json()) as TaskSubmitResponse
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
  return (await resp.json()) as TaskSubmitResponse
}

/** 查询后台任务状态（轮询用）。 */
export async function fetchTask(taskId: string): Promise<TaskState> {
  const resp = await fetch(`${BASE}/backtest/tasks/${taskId}`)
  if (!resp.ok) await throwError(resp)
  return (await resp.json()) as TaskState
}

/** 列出最近任务摘要（供对比页选择）。 */
export async function fetchTaskList(limit = 20): Promise<TaskListResponse> {
  const resp = await fetch(`${BASE}/backtest/tasks?limit=${limit}`)
  if (!resp.ok) await throwError(resp)
  return (await resp.json()) as TaskListResponse
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
  // eslint-disable-next-line no-constant-condition
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
  return (await resp.json()) as SavedStrategyListResponse
}

/** 查看单条已保存策略。 */
export async function fetchSavedStrategy(id: string): Promise<SavedStrategy> {
  const resp = await fetch(`${BASE}/strategies/${id}`)
  if (!resp.ok) await throwError(resp)
  return (await resp.json()) as SavedStrategy
}

/** 保存一条策略（含当时的标的上下文与成绩快照）。 */
export async function saveStrategy(req: SavedStrategyCreate): Promise<SavedStrategy> {
  const resp = await fetch(`${BASE}/strategies`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) await throwError(resp)
  return (await resp.json()) as SavedStrategy
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
  return (await resp.json()) as SavedStrategy
}

// ── 服务器设置 ──────────────────────────────────────────────────────────────

/** 列出所有候选通达信服务器 + 当前使用的 host（不含延迟，需点测速）。 */
export async function fetchServerHosts(): Promise<ServerHostListResponse> {
  const resp = await fetch(`${BASE}/server/hosts`)
  if (!resp.ok) await throwError(resp)
  return (await resp.json()) as ServerHostListResponse
}

/** 并发测速全部（或指定）host，返回延迟和可达性。 */
export async function testServerHosts(hosts?: string[]): Promise<ServerHostInfo[]> {
  const resp = await fetch(`${BASE}/server/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hosts: hosts ?? null }),
  })
  if (!resp.ok) await throwError(resp)
  return (await resp.json()) as ServerHostInfo[]
}

/** 切换到指定 host（热重连，无需重启服务）。 */
export async function switchServerHost(host: string): Promise<ServerSwitchResult> {
  const resp = await fetch(`${BASE}/server/switch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ host }),
  })
  if (!resp.ok) await throwError(resp)
  return (await resp.json()) as ServerSwitchResult
}

// ── 股票诊断 ──────────────────────────────────────────────────────────────

/** 快速诊断单只股票技术面（GET，方便浏览器直接访问）。 */
export async function fetchDiagnosis(market: string, code: string): Promise<DiagnosisResult> {
  const resp = await fetch(`${BASE}/diagnosis/quick?market=${market}&code=${code}`)
  if (!resp.ok) await throwError(resp)
  return (await resp.json()) as DiagnosisResult
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
  return (await resp.json()) as AdviceSimulateResult
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
  return (await resp.json()) as MultiStockComparisonResponse
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
  verdict?: { action: string; signal?: string; confidence?: number; reason?: string }
  structure?: { bi_count: number; zs_count: number; mmd_count: number; bc_count: number }
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
  return (await resp.json()) as StockPickScreenResult
}

/** 第二步：缠论择时（截至目标日的前复权 K 线 + 缠论结构 + 结论）。 */
export async function stockPickTiming(req: {
  date: string
  symbols: { market: string; code: string }[]
  count?: number
}): Promise<{ date: string; results: StockPickTimingResult[] }> {
  const resp = await fetch(BASE + '/stock-pick/timing', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!resp.ok) await throwError(resp)
  return (await resp.json()) as { date: string; results: StockPickTimingResult[] }
}
