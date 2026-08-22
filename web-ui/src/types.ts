// 后端 API 的 TypeScript 类型镜像。
// 与 src/easy_tdx/web/backtest_schemas.py 及 backtest router 的响应保持一致。
// 后端是唯一事实源；这里只做类型契约。

// ── 策略 schema（GET /api/v1/backtest/strategies） ───────────────────────────

export type ParamType = 'int' | 'float' | 'bool' | 'str'

export interface ParamSchema {
  name: string
  type: ParamType
  default: number | string | boolean
  label: string
  min_value?: number
  max_value?: number
  choices?: string[]
  description?: string
}

export interface StrategySchema {
  name: string
  label: string
  description: string
  params: ParamSchema[]
  preset_grid?: Record<string, Array<number | string>>
}

export interface StrategiesResponse {
  strategies: StrategySchema[]
  count: number
}

// ── OHLCV 行情（GET /api/v1/bars） ────────────────────────────────────────────

export interface Bar {
  datetime: string
  open: number
  high: number
  low: number
  close: number
  vol: number
  amount: number
}

export interface DataFrameResponse {
  data: Record<string, unknown>[]
  count: number
}

// ── 回测请求（POST /api/v1/backtest/run） ─────────────────────────────────────

export type ExecutionMode = 'next_open' | 'next_close'
export type Category = 'DAY' | 'WEEK' | 'MONTH' | 'MIN_5' | 'MIN_15' | 'MIN_30' | 'MIN_60'

export interface BacktestRequest {
  strategy: string
  params?: Record<string, number | string | boolean>
  cash?: number
  commission?: number
  min_commission?: number
  stamp_tax?: number
  slippage?: number
  execution?: ExecutionMode
  ohlcv?: Bar[]
  symbol?: string
  category?: Category
  count?: number
}

// ── 回测结果 ──────────────────────────────────────────────────────────────────

export interface Performance {
  total_return: number
  annual_return: number
  max_drawdown: number
  max_dd_duration: number
  sharpe: number
  sortino: number
  calmar: number
  total_trades: number
  win_trades: number
  lose_trades: number
  rejected_trades: number
  win_rate: number
  profit_factor: number
  avg_win: number
  avg_loss: number
  max_win: number
  max_loss: number
  avg_holding_days: number
  volatility: number
  // 新增指标（V2.1）
  max_consec_win: number
  max_consec_loss: number
  sharpe_ratio: number
  start_cash: number
  end_value: number
}

export interface EquityPoint {
  datetime: string
  cash: number
  position_value: number
  total: number
  drawdown: number
  drawdown_pct: number
}

export interface Trade {
  datetime: string
  direction: 'BUY' | 'SELL'
  size: number
  price: number
  commission: number
  slippage: number
  pnl: number
  rejected: boolean
}

export interface BacktestResult {
  performance: Performance
  equity_curve: EquityPoint[]
  trades: Trade[]
  positions: Record<string, unknown>[]
  config: Record<string, unknown>
}

// ── 后台任务（POST /api/v1/backtest/run/async + GET /tasks/{id}） ─────────────

export interface TaskSubmitResponse {
  task_id: string
  status: 'pending' | 'running'
}

export type TaskStatus = 'pending' | 'running' | 'done' | 'failed'

export interface TaskState {
  task_id: string
  status: TaskStatus
  result: BacktestResult | PortfolioResult | OptimizeResult | OptimizeAllResult | null
  error: string | null
  description: string
  elapsed: number
}

// ── 任务摘要（Phase 5 对比页） ────────────────────────────────────────────────

export interface TaskSummary {
  task_id: string
  status: TaskStatus
  description: string
  created_at: number
  elapsed: number
}

export interface TaskListResponse {
  tasks: TaskSummary[]
  count: number
}

// ── 组合回测（Phase 3） ───────────────────────────────────────────────────────

export interface PortfolioBacktestRequest {
  strategy: string
  params?: Record<string, number | string | boolean>
  cash?: number
  commission?: number
  slippage?: number
  execution?: ExecutionMode
  stocks: string[]
  category?: Category
  start_date?: string
  end_date?: string
}

export interface PortfolioResult {
  total_performance: {
    total_return: number
    annual_return: number
    total_stocks: number
    total_cash: number
  }
  individual_results: Record<string, BacktestResult>
  equity_allocation: Record<string, number>
  combined_equity: EquityPoint[]
}

// ── 参数网格寻优（Phase 4） ──────────────────────────────────────────────────

export interface OptimizeBacktestRequest {
  strategy: string
  cash?: number
  commission?: number
  slippage?: number
  execution?: ExecutionMode
  param_grid: Record<string, Array<number | string>>
  ohlcv?: Bar[]
  symbol?: string
  category?: Category
  count?: number
  start_date?: string
  end_date?: string
  // Walk-Forward 验证参数
  use_walk_forward?: boolean
  train_ratio?: number
  step_ratio?: number
}

export interface GridPointResult {
  params: Record<string, number | string>
  total_return: number | null
  sharpe: number | null
  max_drawdown: number | null
  total_trades: number
  win_rate: number | null
  profit_factor: number | null
}

export interface OptimizeHeatmap {
  x_name: string
  y_name: string
  x: Array<number | string>
  y: Array<number | string>
  data: Array<[number, number, number | null]>
}

export interface OptimizeResult {
  strategy: string
  param_names: string[]
  results: GridPointResult[]
  best: GridPointResult | null
  heatmap: OptimizeHeatmap | null
}

// ── 一键寻优所有策略（Phase 6） ──────────────────────────────────────────────

export interface OptimizeAllBacktestRequest {
  cash?: number
  commission?: number
  slippage?: number
  execution?: ExecutionMode
  workers?: number
  ohlcv?: Bar[]
  symbol?: string
  category?: Category
  count?: number
  start_date?: string
  end_date?: string
}

export interface OptimizeAllRankEntry {
  strategy: string
  strategy_label: string
  params: Record<string, number | string>
  total_return: number | null
  sharpe: number | null
  max_drawdown: number | null
  total_trades: number
  win_rate: number | null
  profit_factor: number | null
  grid_points: number
}

export interface OptimizeAllResult {
  ranking: OptimizeAllRankEntry[]
  best: OptimizeAllRankEntry | null
  per_strategy: Record<string, OptimizeAllRankEntry>
  total_grid_points: number
}

// ── 错误响应（后端 ApiErrorResponse） ─────────────────────────────────────────

export interface ApiError {
  error: string
  detail: string
}

// ── 策略库（已保存策略，GET/POST/DELETE /api/v1/strategies） ─────────────────

/** 新建一条已保存策略的请求体（前端在回测结果区点「保存」时提交）。 */
export interface SavedStrategyCreate {
  name: string
  kind: 'single' | 'portfolio' | 'multi'
  strategy: string
  strategy_label?: string
  params?: Record<string, number | string | boolean>
  /** 标的上下文：single 存 symbol/category/start_date/end_date；portfolio 存 stocks；multi 存 items + cash/execution */
  context?: Record<string, unknown>
  /** 资金与成本配置（cash/commission/...） */
  trade_config?: Record<string, unknown>
  /** 保存时的成绩快照（total_return/sharpe/...） */
  snapshot?: Record<string, unknown>
  tags?: string[]
  notes?: string
}

/** 一条已保存策略（响应模型，含 id 与时间戳）。 */
export interface SavedStrategy {
  id: string
  name: string
  kind: 'single' | 'portfolio' | 'multi'
  strategy: string
  strategy_label: string
  params: Record<string, number | string | boolean>
  context: Record<string, unknown>
  trade_config: Record<string, unknown>
  snapshot: Record<string, unknown>
  tags: string[]
  notes: string
  created_at: string
  updated_at: string
  app_version: string
}

export interface SavedStrategyListResponse {
  strategies: SavedStrategy[]
  count: number
}

// ── 多策略组合回测（资金分仓，POST /api/v1/backtest/multi-strategy/run/async） ──

/** 多策略组合的单个策略槽位（一个策略 + 参数 + 它要跑的原标的 + 日期）。 */
export interface MultiStrategyItem {
  strategy: string
  strategy_label?: string
  params?: Record<string, number | string | boolean>
  symbol: string
  category?: Category
  start_date?: string
  end_date?: string
}

/** 多策略组合回测请求（各策略各拿 1/N 资金，结果结构同 PortfolioResult）。 */
export interface MultiStrategyBacktestRequest {
  items: MultiStrategyItem[]
  cash?: number
  commission?: number
  min_commission?: number
  stamp_tax?: number
  slippage?: number
  execution?: ExecutionMode
}

// ── 服务器设置（GET /api/v1/server/hosts 等） ────────────────────────────────

/** 单个通达信服务器的状态信息。 */
export interface ServerHostInfo {
  host: string
  /** 延迟（毫秒）。null = 未测速或不可达。 */
  latency_ms: number | null
  reachable: boolean
  is_current: boolean
}

/** GET /server/hosts 的响应。 */
export interface ServerHostListResponse {
  hosts: ServerHostInfo[]
  current_host: string
  total: number
}

/** POST /server/switch 的响应。 */
export interface ServerSwitchResult {
  ok: boolean
  host: string
  message: string
}

// ── 股票诊断 ─────────────────────────────────────────────────────────────

export interface DiagnosisChanlunMmdQuality {
  grade: 'S' | 'A' | 'B' | 'C' | 'D' | null
  score: number | null
  reasons: string[] | null
}

export interface DiagnosisChanlunMmd {
  type: string | null
  confidence: number | null
  msg: string | null
  quality: DiagnosisChanlunMmdQuality | null
  // V15: K线形态确认
  kline_pattern?: string | null
  // V16: 仓位建议
  position_sizing?: { position_pct: number; suggestion: string; risk_level: string; notes: string[] } | null
}

export interface DiagnosisChanlunRecentSignal {
  type: string
  confidence: number
  quality: { grade: 'S'|'A'|'B'|'C'|'D'|null; score: number|null } | null
}

export interface DiagnosisSignalReport {
  entry_price: number | null
  stop_loss: number | null
  dynamic_stop: number | null
  take_profit_1: number | null
  take_profit_2: number | null
  risk_reward_ratio: number | null
  signal_strength: number | null
  entry_reason: string | null
  risk_notes: string | null
  atr: number | null
  enhancement_notes: string[] | null
  trailing_stop: number | null
  // V15: 信号衰减信息
  signal_aging?: { aged: boolean; age_bars: number; decay_factor: number } | null
  // V15: K线形态确认
  kline_pattern?: string | null
  // V16: 仓位建议
  position_sizing?: { position_pct: number; suggestion: string; risk_level: string; notes: string[] } | null
}

export interface DiagnosisChanlun {
  bi_count: number
  zs_count: number
  mmd_count: number
  buy_1_count: number
  sell_1_count: number
  buy_2_count: number
  sell_2_count: number
  latest_mmd: DiagnosisChanlunMmd | null
  recent_signals: DiagnosisChanlunRecentSignal[]
  confluence_score: number | null
  volume_profile: {
    support: number | null
    resistance: number | null
    current_rank: number
    cluster_up: boolean
    cluster_down: boolean
  } | null
  signal_report: DiagnosisSignalReport | null
  // V21: 决策辅助输出
  decision_recommendation?: {
    action: 'buy' | 'sell' | 'hold'
    entry_price: number | null
    stop_loss: number | null
    take_profit_1: number | null
    take_profit_2: number | null
    position_pct: number | null
    risk_reward_ratio: number | null
    key_support: number | null
    key_resistance: number | null
    confidence_label: '高' | '中' | '低' | null
    warnings: string[] | null
    recommendation_text: string | null
  } | null
  // V21: 组合信号信息
  combo_signal?: {
    type: string | null
    bonus: number
  } | null
  // V22: 波动率双重确认
  vol_regime_dual?: {
    regime: string
    price_action: string
    dual_confirmed: boolean
    confidence_adjust: number
  } | null
  // V22: 量价背离检测
  vol_price_divergence?: {
    type: string
    strength: number
    signal: string
    description: string
  } | null
}

export interface DiagnosisMACD {
  dif: number
  dea: number
  hist: number
  golden_cross: boolean
  dead_cross: boolean
  above_zero: boolean
  trending: 'up' | 'down' | 'flat'
}

export interface DiagnosisBOLL {
  upper: number
  mid: number
  lower: number
  width: number
  percent_b: number
  position: 'upper' | 'mid' | 'lower'
}

export interface DiagnosisMovingAverages {
  ma5: number
  ma10: number
  ma20: number
  ma60: number
  bullish_arrangement: boolean
  bearish_arrangement: boolean
}

export interface DiagnosisVolume {
  ratio: number
  expanding: boolean
  contracting: boolean
}

export interface DiagnosisKDJ {
  k: number
  d: number
  j: number
  golden_cross: boolean
  dead_cross: boolean
  overbought: boolean
  oversold: boolean
  position: '超买' | '超卖' | '中性'
}

export interface DiagnosisRSI {
  value: number
  overbought: boolean
  oversold: boolean
  position: '极强超买' | '超买' | '中性' | '超卖' | '极强超卖'
}

export interface DiagnosisADX {
  pdi: number
  mdi: number
  adx: number
  adxr: number
  trend_direction: 'up' | 'down'
  strength: string
  level: 'very_strong' | 'strong' | 'medium' | 'weak' | 'none'
}

export interface DiagnosisOBV {
  value: number
  ma20: number
  trending_up: boolean
  trending_down: boolean
  divergence_with_price: 'bullish' | 'bearish' | 'none'
}

export interface DiagnosisDivergence {
  macd: { type: string; strength: number; detected: boolean }
  kdj: { type: string; strength: number; detected: boolean }
  rsi: { type: string; strength: number; detected: boolean }
  dominant: 'bullish' | 'bearish' | 'none'
  strength: number
  has_divergence: boolean
}

export interface DiagnosisCandlestick {
  signal: 'bullish' | 'bearish' | 'neutral' | 'none'
  strength: number
  recent_patterns: Array<{ bar_index: number; type: string; bullish: boolean }>
}

export interface DiagnosisPositionSuggestion {
  position_pct: number
  suggestion: string
  risk_level: string
  notes: string
}

export interface DiagnosisFibonacci {
  levels: Record<string, number>
  position: number
  period_high: number | null
  period_low: number | null
}

export interface DiagnosisRisk {
  stop_loss_price: number
  take_profit_price: number
  stop_loss_pct: number
  take_profit_pct: number
  risk_reward_ratio: number
  atr: number
  atr_pct: number
  volatility_label: string
  volatility_level: 'low' | 'medium' | 'high'
  support_1: number
  resistance_1: number
  support_2: number
  resistance_2: number
}

export interface DiagnosisResult {
  symbol: string
  date: string
  close: number
  score: number
  action: 'strong_buy' | 'buy' | 'hold' | 'sell' | 'strong_sell'
  action_label: string
  action_color: string
  reason: string
  chanlun: DiagnosisChanlun
  macd: DiagnosisMACD
  boll: DiagnosisBOLL
  moving_averages: DiagnosisMovingAverages
  volume: DiagnosisVolume
  kdj: DiagnosisKDJ
  rsi: DiagnosisRSI
  adx: DiagnosisADX
  obv: DiagnosisOBV
  divergence: DiagnosisDivergence
  candlestick: DiagnosisCandlestick
  risk: DiagnosisRisk
  position_suggestion: DiagnosisPositionSuggestion
  fibonacci: DiagnosisFibonacci
}
