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
  robustness_segments?: number | null
  out_of_sample?: boolean
  oos_train_ratio?: number
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

export interface SignalHorizonStat {
  count: number
  hit_rate: number
  avg_return: number
  median_return: number
  baseline_hit_rate: number
  baseline_avg_return: number
  excess_hit_rate: number
  excess_avg_return: number
}

export interface SignalAccuracyReport {
  buy: { signals: number; horizons: Record<string, SignalHorizonStat> } | null
  sell: { signals: number; horizons: Record<string, SignalHorizonStat> } | null
  benchmark: { buy_hold_return?: number; strategy_return?: number; alpha?: number }
  verdict: string
  note?: string
  // 缠论专属：按买卖点类型分组的准确度
  chanlun_by_type?: Record<string, any> | null
  chanlun_ranking?: Array<{
    type: string
    direction: string
    signals: number
    excess_hit_rate: number
    hit_rate: number
    avg_return: number
    verdict: string
  }> | null
  chanlun_summary?: string | null
}

export interface SegmentRobustnessReport {
  segments: Array<{
    label: string
    bars: number
    skipped?: boolean
    note?: string
    start?: string
    end?: string
    total_return?: number
    win_rate?: number
    sharpe?: number
    max_drawdown?: number
    trades?: number
    hit_rate?: number | null
    buy_hold_return?: number
    alpha?: number
  }>
  consistency: {
    segments_analyzed: number
    positive_segment_ratio?: number
    beats_buy_hold_ratio?: number
    win_rate_mean?: number
    win_rate_std?: number
    win_rate_cv?: number
    hit_rate_mean?: number | null
    hit_rate_std?: number | null
    return_mean?: number
    return_std?: number
    best_segment?: string
    worst_segment?: string
  }
  overfit_likely: boolean
  verdict: string
  note?: string | null
}

export interface ModelTrustReport {
  score: number
  grade: '高' | '中' | '低'
  components: {
    accuracy: Record<string, number | string | null>
    robustness: Record<string, number | string | boolean | null>
    performance: Record<string, number | null>
  }
  verdict: string
}

export interface OutOfSampleSection {
  bars: number
  total_return?: number
  win_rate?: number
  sharpe?: number
  max_drawdown?: number
  trades?: number
  buy_hold_return?: number
  alpha?: number
  hit_rate?: number | null
  baseline_hit_rate?: number | null
  excess_hit_rate?: number | null
}

export interface OutOfSampleReport {
  train_ratio: number
  train_bars: number
  test_bars: number
  train: OutOfSampleSection
  test: OutOfSampleSection
  degraded: boolean
  verdict: string
  note?: string | null
}

export interface BacktestResult {
  performance: Performance
  equity_curve: EquityPoint[]
  trades: Trade[]
  positions: Record<string, unknown>[]
  config: Record<string, unknown>
  signal_accuracy?: SignalAccuracyReport | null
  segment_robustness?: SegmentRobustnessReport | null
  model_trust?: ModelTrustReport | null
  diagnostic?: string | null
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

export interface PortfolioSymbolAccuracy {
  symbol: string
  allocation: number
  total_return: number
  win_rate: number
  sharpe: number
  max_drawdown: number
  trades: number
  hit_rate: number | null
  baseline_hit_rate: number | null
  excess_hit_rate: number | null
}

export interface PortfolioAccuracyReport {
  symbols: PortfolioSymbolAccuracy[]
  portfolio: {
    symbols: number
    symbols_with_accuracy: number
    avg_hit_rate: number
    avg_baseline_hit_rate: number
    avg_excess_hit_rate: number
    avg_win_rate: number
    avg_total_return: number
    avg_sharpe: number
    positive_symbols: number
    hit_above_baseline: number
  }
  verdict: string
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
  accuracy_summary?: PortfolioAccuracyReport | null
  portfolio_trust?: ModelTrustReport | null
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
/** V100: 保存策略时持久化的准确度验证快照（signal_accuracy 关键结论）。 */
export interface StrategyAccuracySnapshot {
  hit_rate: number | null
  excess_hit_rate: number | null
  verdict: string
}

/** V100: 保存策略时持久化的稳健性验证快照（segment_robustness 关键结论）。 */
export interface StrategyRobustnessSnapshot {
  overfit_likely: boolean
  verdict: string
}

/** 策略成绩快照：绩效指标 + V100 新增的准确度/稳健性验证结论。 */
export interface SavedStrategySnapshot extends Record<string, unknown> {
  total_return?: number
  annual_return?: number
  max_drawdown?: number
  sharpe?: number
  win_rate?: number
  trades_count?: number
  accuracy?: StrategyAccuracySnapshot
  robustness?: StrategyRobustnessSnapshot
}

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
  snapshot?: SavedStrategySnapshot
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
  snapshot: SavedStrategySnapshot
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
  // V79 缠论增强条件
  v79_fractal_stability?: { stability_score: number; fractal_status: string; confidence_adjust: number; msg: string } | null
  v79_distance_safety?: { distance_score: number; bars_to_nearest: number; safety_level: string; confidence_adjust: number; msg: string } | null
  v79_multi_level_consistency?: { consistency_score: number; short_align: boolean; mid_align: boolean; long_align: boolean; confidence_adjust: number; msg: string } | null
  v79_momentum_continuity?: { momentum_score: number; acceleration: number; momentum_level: string; confidence_adjust: number; msg: string } | null
  // V80 缠论增强条件
  v80_zhongshu_distance?: { distance_score: number; nearest_zs_dist_pct: number; zs_position: string; confidence_adjust: number; msg: string } | null
  v80_volume_confirmation?: { confirmation_score: number; vol_ratio: number; volume_trend: string; price_trend: string; confidence_adjust: number; msg: string } | null
  v80_ma_alignment?: { alignment_score: number; ma_alignment: string; price_position: string; confidence_adjust: number; msg: string } | null
  v80_risk_reward?: { rr_ratio: number; stop_loss_pct: number; take_profit_pct: number; risk_level: string; confidence_adjust: number; msg: string } | null
  // V81 缠论增强条件（条件256-259）
  v81_volatility_regime?: { regime: string; transition_type: string; atr_ratio: number; atr_change_pct: number; confidence_adjust: number; msg: string } | null
  v81_support_resistance?: { strength_level: string; nearest_sr_dist_pct: number; sr_count: number; confidence_adjust: number; msg: string } | null
  v81_energy_distribution?: { energy_zone: string; energy_score: number; volume_concentration: number; confidence_adjust: number; msg: string } | null
  v81_execution_window?: { window_quality: string; volatility_score: number; liquidity_score: number; confidence_adjust: number; msg: string } | null
  // V82 缠论增强条件（条件260-263）
  v82_age_decay?: { age_bars: number; age_label: string; confidence_adjust: number; msg: string } | null
  v82_breakout_retest?: { retest_detected: boolean; retest_quality: string; confidence_adjust: number; msg: string } | null
  v82_macd_resonance?: { short_acceleration: number; mid_trend: string; resonance: string; confidence_adjust: number; msg: string } | null
  v82_volatility_compression?: { compression_level: number; breakout_strength: number; volume_confirm: boolean; confidence_adjust: number; msg: string } | null
}

export interface DiagnosisChanlunRecentSignal {
  type: string
  confidence: number
  quality: { grade: 'S'|'A'|'B'|'C'|'D'|null; score: number|null } | null
  // V79 缠论增强条件
  v79_fractal_stability?: { stability_score: number; fractal_status: string; confidence_adjust: number; msg: string } | null
  v79_distance_safety?: { distance_score: number; bars_to_nearest: number; safety_level: string; confidence_adjust: number; msg: string } | null
  v79_multi_level_consistency?: { consistency_score: number; short_align: boolean; mid_align: boolean; long_align: boolean; confidence_adjust: number; msg: string } | null
  v79_momentum_continuity?: { momentum_score: number; acceleration: number; momentum_level: string; confidence_adjust: number; msg: string } | null
  // V80 缠论增强条件
  v80_zhongshu_distance?: { distance_score: number; nearest_zs_dist_pct: number; zs_position: string; confidence_adjust: number; msg: string } | null
  v80_volume_confirmation?: { confirmation_score: number; vol_ratio: number; volume_trend: string; price_trend: string; confidence_adjust: number; msg: string } | null
  v80_ma_alignment?: { alignment_score: number; ma_alignment: string; price_position: string; confidence_adjust: number; msg: string } | null
  v80_risk_reward?: { rr_ratio: number; stop_loss_pct: number; take_profit_pct: number; risk_level: string; confidence_adjust: number; msg: string } | null
  // V81 缠论增强条件（条件256-259）
  v81_volatility_regime?: { regime: string; transition_type: string; atr_ratio: number; atr_change_pct: number; confidence_adjust: number; msg: string } | null
  v81_support_resistance?: { strength_level: string; nearest_sr_dist_pct: number; sr_count: number; confidence_adjust: number; msg: string } | null
  v81_energy_distribution?: { energy_zone: string; energy_score: number; volume_concentration: number; confidence_adjust: number; msg: string } | null
  v81_execution_window?: { window_quality: string; volatility_score: number; liquidity_score: number; confidence_adjust: number; msg: string } | null
  // V82 缠论增强条件（条件260-263）
  v82_age_decay?: { age_bars: number; age_label: string; confidence_adjust: number; msg: string } | null
  v82_breakout_retest?: { retest_detected: boolean; retest_quality: string; confidence_adjust: number; msg: string } | null
  v82_macd_resonance?: { short_acceleration: number; mid_trend: string; resonance: string; confidence_adjust: number; msg: string } | null
  v82_volatility_compression?: { compression_level: number; breakout_strength: number; volume_confirm: boolean; confidence_adjust: number; msg: string } | null
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
  // V23: Fibonacci回撤位确认（条件40）
  fib_retracement?: {
    near_fib_level: string | null
    fib_ratio: number
    distance_to_level: number
    is_key_level: boolean
    confirmation_bonus: number
  } | null
  // V23: RSI区域分类（条件41）
  rsi_zone?: {
    zone: string
    rsi: number
  } | null
  // V23: MACD零轴穿越确认（条件42）
  macd_zero_cross?: {
    cross_type: string
    distance_to_zero: number
    strength: string
    confidence_bonus: number
  } | null
  // V24: 笔质量评分（条件43）
  bi_quality?: {
    quality_score: number
    confidence_bonus: number
    factors: Record<string, number>
  } | null
  // V24: 中枢强度分析（条件44）
  zs_strength?: {
    strength_level: string
    strength_score: number
    confidence_bonus: number
  } | null
  // V24: 增强背离检测（条件45）
  enhanced_divergence?: {
    divergence_type: string
    strength: string
    confidence_bonus: number
  } | null
  // V24: 信号交叉验证评分（条件46）
  cross_validation?: {
    consensus_score: number
    confirmations: string[]
    consensus_bonus: number
  } | null
  // V25: 信号后确认验证（条件47）
  post_signal_confirm?: {
    confirmed: boolean
    bars_ahead: number
    price_change_pct: number
    confidence_bonus: number
  } | null
  // V25: 动量衰减预警（条件48）
  momentum_decay?: {
    decay_detected: boolean
    decay_type: string
    momentum_score: number
    confidence_penalty: number
  } | null
  // V25: 波动率自适应过滤（条件49）
  vol_regime_filter?: {
    regime: string
    filter_applied: boolean
    threshold_adjustment: number
    confidence_bonus: number
  } | null
  // V25: 综合信号质量评分（条件50）
  composite_quality?: {
    overall_score: number
    grade: string
    breakdown: Record<string, number>
    recommendation: string
  } | null
  // V26: 信号历史验证（条件51）
  signal_history?: {
    historical_accuracy: number
    sample_size: number
    confidence_adjust: number
    validation_passed: boolean
    recent_trend: number
    volatility_20d: number
  } | null
  // V26: 动态风险收益优化（条件52）
  dynamic_rr_optimization?: {
    optimal_stop_loss: number
    optimal_take_profit_1: number
    optimal_take_profit_2: number
    risk_reward_ratio: number
    atr_based_stop: number
    volatility_adjusted: boolean
    adjustment_factor: number
    atr: number
    volatility: number
  } | null
  // V26: 多标的对比评分（条件53）
  cross_stock_comparison?: {
    ranked_signals: Array<{
      index: number
      mmd_type: string
      confidence: number
      composite_score: number
      grade: string
      recommendation: string
      sort_score: number
    }>
    best_signal: any | null
    comparison_summary: {
      total_signals: number
      avg_composite_score: number
      avg_confidence: number
      buy_signals: number
      sell_signals: number
      best_grade: string
      recommendation: string
    }
    diversification_score: number
  } | null
  // V27: 多级别区间套共振验证（条件54）
  multi_tf_confluence?: {
    overall_confluence_score: number
    confidence_adjust: number
    trend_alignment: string
    short_trend: string
    mid_trend: string
    long_trend: string
    per_signal: Record<string, {
      resonance_score: number
      trend_alignment: string
      short_trend: string
      mid_trend: string
      long_trend: string
    }>
  } | null
  // V27: 买卖点结构位置评分（条件55）
  structure_position?: {
    position_score: number
    distance_to_support: number
    distance_to_resistance: number
    structural_quality: string
    position_desc: string
    latest_price: number
    support_level: number
    resistance_level: number
  } | null
  // V27: 个股信号特征学习（条件56）
  stock_profile?: {
    signal_type_success_rate: number
    stock_volatility_regime: string
    signal_frequency: string
    confidence_adjust: number
    personalized_rating: string
    vol_20d: number
    mean_return_50d: number
  } | null
  // V28: BOLL带宽压缩确认（条件57）
  boll_squeeze?: {
    squeeze_score: number
    band_width: number
    band_width_rank: number
    squeeze_active: boolean
    confidence_adjust: number
  } | null
  // V28: 突破量价确认（条件58）
  breakout_vol_price?: {
    breakout_strength: string
    volume_ratio: number
    price_force_ratio: number
    confirmed: boolean
    confidence_adjust: number
  } | null
  // V28: 动态ATR止损位（条件59）
  dynamic_atr_stop?: {
    stop_loss_price: number
    stop_loss_pct: number
    atr_value: number
    risk_reward_ratio: number
    take_profit_price: number
    confidence_adjust: number
  } | null
  // V29: 趋势方向持续性确认（条件60）
  trend_continuity?: {
    continuity_score: number
    future_trend: string
    confirm_bars: number
    confidence_adjust: number
  } | null
  // V29: 盘整区背离预警（条件61）
  consolidation_divergence?: {
    has_divergence: boolean
    divergence_type: string
    divergence_strength: number
    warning_level: string
    confidence_adjust: number
  } | null
  // V30: K线形态反向确认（条件62）
  kline_pattern_confirm?: {
    pattern_score: number
    bar_direction: string
    confidence_adjust: number
  } | null
  // V30: 中枢突破方向确认（条件63）
  zs_breakout_confirm?: {
    breakout_valid: boolean
    breakout_direction: string
    volume_confirmed: boolean
    confidence_adjust: number
  } | null
  // V30: 近期波动区间止损优化（条件64）
  recent_range_stop?: {
    stop_loss_price: number
    stop_loss_pct: number
    atr_value: number
    recent_low: number
    recent_high: number
    risk_reward_ratio: number
    take_profit_price: number
    confidence_adjust: number
  } | null
  // V31: 均线排列确认（条件65）
  ma_alignment?: {
    alignment: string
    ma5: number
    ma10: number
    ma20: number
    is_bullish_arrangement: boolean
    is_bearish_arrangement: boolean
    confidence_adjust: number
  } | null
  // V31: MACD柱状图加速度（条件66）
  macd_histogram_acceleration?: {
    hist_slope: number
    hist_acceleration: number
    acceleration_direction: string
    confidence_adjust: number
  } | null
  // V31: 信号综合健康度报告（条件67）
  signal_health_dashboard?: {
    health_score: number
    health_grade: string
    dimensions: Record<string, any>
    strengths: string[]
    weaknesses: string[]
    recommendation: string
    confidence_adjust: number
  } | null
  // V32: 量价背离检测增强（条件68）
  vol_price_divergence_enhanced?: {
    divergence_detected: boolean
    divergence_type: string
    strength: number
    volume_trend: string
    price_trend: string
    confidence_adjust: number
  } | null
  // V32: 信号优先级动态排序（条件69）
  signal_priority?: {
    priority_rank: number
    total_signals: number
    priority_score: number
    rank_reason: string
    confidence_adjust: number
  } | null
  // V32: 支撑阻力位突破确认（条件70）
  sr_breakout_confirm?: {
    sr_level: number
    sr_type: string
    breakout_valid: boolean
    distance_pct: number
    confidence_adjust: number
  } | null
  // V33: OBV能量潮趋势确认（条件71）
  obv_trend_confirm?: {
    obv_trend: string
    price_trend: string
    confirmation: boolean
    obv_ma_ratio: number
    confidence_adjust: number
  } | null
  // V33: MACD动能锥面积确认（条件72）
  macd_hist_area?: {
    hist_area_recent: number
    hist_area_prev: number
    area_ratio: number
    momentum_direction: string
    acceleration: string
    confidence_adjust: number
  } | null
  // V33: RSI动量确认（条件73）
  rsi_momentum_confirm?: {
    rsi_value: number
    rsi_prev: number
    rsi_momentum: number
    rsi_zone: string
    momentum_support: boolean
    divergence_detected: boolean
    divergence_type: string
    confidence_adjust: number
  } | null
  // V34: 趋势动能延续确认（条件74）
  trend_momentum_continuation?: {
    price_change_5d: number
    price_change_10d: number
    price_change_20d: number
    momentum_direction: string
    continuation: boolean
    acceleration: string
    confidence_adjust: number
  } | null
  // V34: 多指标共振强度评分（条件75）
  multi_indicator_resonance?: {
    resonance_score: number
    resonance_level: string
    bullish_votes: number
    bearish_votes: number
    neutral_votes: number
    total_indicators: number
    vote_details: Record<string, string>
    confidence_adjust: number
  } | null
  // V34: 波动率环境自适应阈值（条件76）
  volatility_regime?: {
    atr_value: number
    volatility_pct: number
    volatility_regime: string
    threshold_adjust: number
    stop_loss_adjust_pct: number
  } | null
  // V35: 市场大环境过滤（条件77）
  market_context?: {
    market_trend: string
    price_change_30d: number
    price_change_60d: number
    confidence_adjust: number
  } | null
  // V35: 信号衰减增强（条件78）
  enhanced_signal_decay?: {
    bars_since_signal: number
    decay_factor: number
    volatility_adj: number
    confidence_adjust: number
  } | null
  // V35: 假信号过滤（条件79）
  false_signal_filter?: {
    fake_signal_likelihood: string
    volume_confirmed: boolean
    macd_confirmed: boolean
    confidence_adjust: number
  } | null
  // V35: 动态止损止盈增强（条件80）
  dynamic_sl_tp_enhanced?: {
    optimal_stop_loss: number
    optimal_take_profit_1: number
    optimal_take_profit_2: number
    risk_reward_ratio: number
    atr_distance: number
    recent_range_high: number
    recent_range_low: number
  } | null
  // V35: 板块轮动上下文（条件81）
  sector_rotation_context?: {
    phase: string
    trend_strength: number
    confidence_adjust: number
    ma10: number
    ma30: number
    ma60: number
  } | null
  // V35: 多维背离确认（条件82）
  multi_dim_divergence?: {
    price_volume_div: boolean
    price_macd_div: boolean
    divergence_count: number
    confidence_adjust: number
  } | null
  // V36: 信号执行窗口优化（条件83）
  execution_window?: {
    window_status: string
    optimal_action: string
    confidence_adjust: number
    bars_since_signal: number
    window_remaining: number
  } | null
  // V36: 多时间框架一致性验证（条件84）
  tf_consistency?: {
    short_term_trend: string
    mid_term_trend: string
    consistency: string
    confidence_adjust: number
  } | null
  // V36: 风险调整后收益预期（条件85）
  risk_adjusted_return?: {
    expected_return_pct: number
    risk_adjusted_return: number
    max_drawdown_est: number
    volatility_adj: number
  } | null
  // V36: 信号时效性紧急度评分（条件86）
  urgency_score?: {
    urgency_level: string
    urgency_score: number
    confidence_adjust: number
    action_hint: string
  } | null
  // V36: 市场环境综合评分（条件87）
  market_composite?: {
    market_score: number
    trend_score: number
    vol_score: number
    volume_score: number
    macd_score: number
    confidence_adjust: number
    market_regime: string
  } | null
  // V36: 买卖点策略推荐（条件88）
  strategy_recommendation?: {
    strategy: string
    position_size_pct: number
    hold_period: string
    risk_level: string
    action_priority: number
  } | null
  // V37: 连续确认过滤（条件89）
  consecutive_confirmation?: {
    confirmed: boolean
    confirm_bars: number
    confidence_adjust: number
  } | null
  // V37: 价格动能加速度（条件90）
  momentum_acceleration?: {
    acceleration: number
    momentum_direction: string
    confidence_adjust: number
  } | null
  // V37: 波动率状态转换检测（条件91）
  volatility_regime_change?: {
    regime_change: string
    vol_ratio: number
    confidence_adjust: number
  } | null
  // V37: 买卖点时间序列关联分析（条件92）
  temporal_correlation?: {
    interval_bars: number
    interval_status: string
    confidence_adjust: number
  } | null
  // V37: 多时间框架动量一致性（条件93）
  multi_tf_momentum?: {
    short_trend: string
    mid_trend: string
    long_trend: string
    consistency: string
    confidence_adjust: number
  } | null
  // V37: 信号综合质量排名（条件94）
  quality_ranking?: {
    grade: string
    rank: number
    total: number
    score: number
  } | null
  // V38: 中枢结构完整性评分（条件95）
  zs_structure_integrity?: {
    integrity_score: number
    bi_count: number
    zs_range: number
    is_complete: boolean
  } | null
  // V38: 买卖点位置评分（条件96）
  mmd_position_score?: {
    position_pct: number
    position_label: string
    confidence_adjust: number
  } | null
  // V38: 信号后收益跟踪（条件97）
  post_signal_return?: {
    signal_return_pct: number
    lookback_bars: number
    return_quality: string
    sample_signals: number
  } | null
  // V38: 中枢突破力度评估（条件98）
  breakout_strength?: {
    breakout_strength: number
    volume_confirmation: boolean
    obv_trend: string
  } | null
  // V38: 多指标偏离度综合评分（条件99）
  composite_deviation?: {
    composite_deviation: number
    rsi_dev: number
    kdj_dev: number
    bias_dev: number
    extreme: boolean
  } | null
  // V38: 信号衰减预警（条件100）
  signal_decay_warning?: {
    decay_stage: string
    bars_since_signal: number
    price_drift_pct: number
    remaining_window_pct: number
  } | null
  // V39: 买卖点信号一致性验证（条件101）
  signal_consistency?: {
    consistency_ratio: number
    historical_win_rate: number
    sample_size: number
    confidence_adjust: number
  } | null
  // V39: 中枢级别匹配验证（条件102）
  zs_level_match?: {
    level_match: boolean
    zs_level: number
    mmd_type_level: number
    match_score: number
    confidence_adjust: number
  } | null
  // V39: 多时间框架背离确认（条件103）
  multi_tf_divergence?: {
    multi_tf_bullish: number
    multi_tf_bearish: number
    confirmation_strength: number
    confidence_adjust: number
  } | null
  // V39: 独立交叉验证（条件104）
  independent_cross_validation?: {
    method1_support: boolean
    method2_support: boolean
    cross_validated: boolean
    confidence_adjust: number
  } | null
  // V39: 决策质量综合评分（条件105）
  decision_quality_score?: {
    decision_score: number
    risk_level: string
    hold_period: string
    action: string
    action_label: string
    factors: Record<string, number>
  } | null
  // V40: 时间衰减自适应过滤（条件106）
  time_decay_adaptive?: {
    bars_since_signal: number
    decay_factor: number
    effective_age: number
    valid_window: number
    confidence_adjust: number
    is_fresh: boolean
  } | null
  // V40: 中枢突破回踩验证（条件107）
  breakout_retest_validation?: {
    retest_detected: boolean
    retest_depth: number
    volume_confirm: boolean
    breakout_valid: boolean
    confidence_adjust: number
  } | null
  // V40: 多周期MACD共振确认（条件108）
  multi_cycle_macd_resonance?: {
    fast_macd_bullish: boolean
    mid_macd_bullish: boolean
    slow_macd_bullish: boolean
    fast_macd_bearish: boolean
    mid_macd_bearish: boolean
    slow_macd_bearish: boolean
    resonance_count: number
    resonance_strength: number
    confidence_adjust: number
  } | null
  // V40: K线形态综合评分（条件109）
  kline_pattern_composite?: {
    pattern_score: number
    patterns_found: string[]
    pattern_confidence: number
    confidence_adjust: number
  } | null
  // V40: 置信度动态校准（条件110）
  confidence_calibration?: {
    raw_confidence: number
    calibrated_confidence: number
    calibration_method: string
    confidence_adjust: number
    distribution_stats: Record<string, number>
    z_score?: number
  } | null
  // V41: 量价能量分布分析（条件111）
  volume_price_energy_dist?: {
    energy_zone: string
    volume_rank: number
    support_distance: number
    resistance_distance: number
    confidence_adjust: number
  } | null
  // V41: 量能周期检测（条件112）
  volume_cycle_detection?: {
    cycle_state: string
    volume_trend: string
    volume_price_alignment: boolean
    confidence_adjust: number
  } | null
  // V41: 走势预测（条件113）
  post_signal_trajectory?: {
    predicted_direction: string
    prediction_confidence: number
    expected_return_range: number[]
    momentum_score: number
    confidence_adjust: number
  } | null
  // V41: 动态质量分层（条件114）
  quality_tier_classification?: {
    tier: string
    rank: number
  } | null
  // V41: 反转风险评估（条件115）
  reversal_risk_assessment?: {
    risk_level: string
    divergence_strength: number
    rsi_overbought: boolean
    volume_divergence: boolean
    momentum_decay: boolean
    risk_score: number
    confidence_adjust: number
  } | null
  // V42: 后确认验证（条件116）
  post_signal_confirmation?: {
    confirmed: boolean
    bars_confirmed: number
    direction_match: string
    confidence_adjust: number
    msg: string
  } | null
  // V42: 突破-回调量比验证（条件117）
  break_pullback_volume_ratio?: {
    break_vol_ratio: number
    pullback_vol_ratio: number
    volume_ratio_ok: boolean
    confidence_adjust: number
  } | null
  // V42: 中枢距离验证（条件118）
  zhongshu_distance_validation?: {
    distance_pct: number
    distance_valid: boolean
    confidence_adjust: number
  } | null
  // V42: ADX趋势强度确认（条件119）
  adx_trend_strength?: {
    adx_value: number
    adx_level: string
    trend_valid: boolean
    confidence_adjust: number
  } | null
  // V42: 信号时效性衰减增强（条件120）
  signal_freshness?: {
    bars_since_signal: number
    decay_factor: number
    effective_age: number
    is_expired: boolean
    confidence_adjust: number
  } | null
  // V44: 趋势方向对齐验证（条件121）
  trend_direction_alignment?: {
    trend_direction: string
    aligned: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V44: 突破笔力度对比（条件122）
  breakout_bi_strength_compare?: {
    breakout_bi_idx: number
    entry_bi_idx: number
    vol_ratio: number
    price_ratio: number
    strength_ok: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V44: 回踩时间窗口过滤（条件123）
  pullback_time_window?: {
    bars_since_signal: number
    window_status: string
    confidence_adjust: number
    msg: string
  } | null
  // V44: 波动率自适应阈值（条件124）
  volatility_adaptive_threshold?: {
    volatility: number
    vol_regime: string
    threshold_multiplier: number
    confidence_adjust: number
    msg: string
  } | null
  // V44: 多指标背离共振（条件125）
  multi_indicator_divergence_resonance?: {
    macd_divergence: boolean
    rsi_divergence: boolean
    kdj_divergence: boolean
    resonance_count: number
    confidence_adjust: number
    msg: string
  } | null
  // V46: 趋势动能强度过滤（条件126）
  trend_momentum_strength?: {
    adx_value: number
    trend_strength: string
    confidence_adjust: number
    msg: string
  } | null
  // V46: 量价背离二次确认（条件127）
  volume_price_divergence_secondary?: {
    breakout_vol_price: boolean
    pullback_vol_price: boolean
    conflict: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V46: 中枢突破真实性验证（条件128）
  zs_breakout_authenticity?: {
    bars_standing: number
    authentic: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V46: 多时间框架信号一致性（条件129）
  multi_tf_signal_consistency?: {
    ma5_slope: number
    ma10_slope: number
    ma20_slope: number
    consistency: string
    confidence_adjust: number
    msg: string
  } | null
  // V46: 动态市场环境适配（条件130）
  dynamic_market_regime?: {
    regime: string
    volatility: number
    volume_trend: string
    confidence_adjust: number
    msg: string
  } | null
  // V47: 后确认价格跟随过滤（条件131）
  post_signal_price_follow_through?: {
    followed: boolean
    follow_pct: number
    signal_bar_idx: number
    looked_bars: number
    confidence_adjust: number
    msg: string
  } | null
  // V47: 信号有效性窗口（条件132）
  signal_validity_window?: {
    window_bars: number
    window_pct: number
    valid: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V47: 置信度动态校准（条件133）
  confidence_v47_calibrated?: number | null
  // V48: 量价背离二次确认（条件134）
  volume_price_divergence_secondary_v48?: {
    confirmed: boolean
    divergence_pct: number
    confidence_adjust: number
    msg: string
  } | null
  // V48: 趋势强度加权（条件135）
  trend_strength_weighting?: {
    adx_value: number
    adx_level: string
    ma_alignment: string
    confidence_adjust: number
    msg: string
  } | null
  // V48: 动态风险收益比（条件136）
  dynamic_risk_reward_ratio?: {
    entry_price: number
    stop_loss: number
    take_profit_1: number
    risk_reward_ratio: number
    quality_tier: string
    atr: number
    confidence_adjust: number
    msg: string
  } | null
  // V49: 突破力度二次验证（条件137）
  breakout_strength_revalidation_v49?: {
    confirmed: boolean
    hist_area_ratio: number
    break_force_before: number
    break_force_after: number
    confidence_adjust: number
    msg: string
  } | null
  // V49: 回踩结构完整性（条件138）
  pullback_structure_integrity_v49?: {
    confirmed: boolean
    structure_quality: string
    confidence_adjust: number
    msg: string
  } | null
  // V49: 中枢级别权重（条件139）
  zhongshu_level_weight_v49?: {
    level: string
    line_count: number
    confidence_adjust: number
    msg: string
  } | null
  // V50: 板块联动分析（条件140）
  sector_correlation_v50?: {
    correlated: boolean
    correlation_pct: number
    confidence_adjust: number
    msg: string
  } | null
  // V50: 多时间框架共振验证（条件141）
  multi_tf_resonance_v50?: {
    resonant: boolean
    alignment_score: number
    confidence_adjust: number
    msg: string
  } | null
  // V50: 缠论级别递归验证（条件142）
  level_recursive_validation_v50?: {
    validated: boolean
    level_quality: string
    confidence_adjust: number
    msg: string
  } | null
  // V50: 市场情绪指标融合（条件143）
  market_sentiment_fusion_v50?: {
    sentiment: string
    sentiment_score: number
    confidence_adjust: number
    msg: string
  } | null
  // V51: 突破笔力度二次确认增强（条件144）
  breakout_bi_strength_enhanced_v51?: {
    vol_ratio: number
    price_ratio: number
    macd_area_ratio: number
    vol_ok: boolean
    price_ok: boolean
    macd_ok: boolean
    score: number
    confidence_adjust: number
    msg: string
  } | null
  // V51: 回踩笔深度+时间综合验证（条件145）
  pullback_depth_time_v51?: {
    pullback_depth_pct: number
    pullback_bars: number
    depth_ok: boolean
    time_ok: boolean
    combined_status: string
    confidence_adjust: number
    msg: string
  } | null
  // V51: 趋势强度综合评分（条件146）
  trend_strength_composite_v51?: {
    adx_value: number
    adx_level: string
    ma_slope: string
    momentum_5d: number
    total_score: number
    trend_strength: string
    confidence_adjust: number
    msg: string
  } | null
  // V51: 交易决策建议（条件147）
  trading_decision_v51?: {
    entry_price: number
    stop_loss: number
    take_profit_1: number
    take_profit_2: number
    risk_reward_ratio: number
    quality_tier: string
    decision: string
    atr: number
    msg: string
  } | null
  // V52: 量价持续确认（条件148）
  volume_sustain_after_signal_v52?: {
    vol_ratio_avg: number
    vol_trend: string
    confirmed: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V52: 多指标背离共振（条件149）
  multi_indicator_divergence_fusion_v52?: {
    macd_div: boolean
    rsi_div: boolean
    kdj_div: boolean
    fusion_score: number
    confidence_adjust: number
    msg: string
  } | null
  // V52: 近期极端价位检测（条件150）
  recent_extreme_price_v52?: {
    price_position: string
    is_extreme: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V52: 市场环境健康评分（条件151）
  market_regime_score_v52?: {
    volatility_regime: string
    trend_health: string
    momentum_score: number
    regime_score: number
    confidence_adjust: number
    msg: string
  } | null
  // V53: 趋势阶段识别与顺势确认（条件152）
  trend_stage_follow_confirmation_v53?: {
    trend_stage: string
    trend_direction: string
    is_following_trend: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V53: ATR自适应止损距离（条件153）
  atr_adaptive_stop_v53?: {
    atr_value: number
    stop_distance_pct: number
    stop_level: number
    position_suggestion: string
    confidence_adjust: number
    msg: string
  } | null
  // V53: 中枢突破力度验证（条件154）
  zs_breakout_strength_v53?: {
    breakout_strength: number
    entry_bi_strength: number
    strength_ratio: number
    confirmed: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V53: 信号质量综合分层（条件155）
  signal_quality_tier_v53?: {
    quality_tier: string
    tier_score: number
    tier_label: string
    position_recommendation: string
    confidence_adjust: number
    msg: string
  } | null
  // V54: 多K线确认后确认（条件156）
  multi_bar_confirmation_v54?: {
    confirmed: boolean
    confirm_bars: number
    total_bars: number
    confidence_adjust: number
    msg: string
  } | null
  // V54: 缺口风险评估（条件157）
  gap_risk_assessment_v54?: {
    has_gap: boolean
    gap_direction: string
    gap_size_pct: number
    confidence_adjust: number
    msg: string
  } | null
  // V54: 波动率 regime 切换检测（条件158）
  volatility_regime_change_v54?: {
    atr_expansion_pct: number
    regime: string
    confidence_adjust: number
    msg: string
  } | null
  // V54: 量价配合度评分（条件159）
  volume_price_coordination_v54?: {
    score: number
    volume_trend: string
    price_trend: string
    confidence_adjust: number
    msg: string
  } | null
  // V55: 分钟级多时间框架共振过滤（条件160）
  multi_tf_resonance_filter_v55?: {
    resonated: boolean
    timeframes: string[]
    confidence_adjust: number
    msg: string
  } | null
  // V55: 中枢级别权重自适应（条件161）
  zhongshu_level_weight_v55?: {
    level: string
    weight_bonus: number
    level_score: number
    confidence_adjust: number
    msg: string
  } | null
  // V55: 弱势股专项风险检测（条件162）
  weak_stock_risk_v55?: {
    is_weak: boolean
    risk_factors: string[]
    volatility_ratio: number
    volume_ratio: number
    confidence_adjust: number
    msg: string
  } | null
  // V55: 信号与趋势方向对齐验证（条件163）
  signal_trend_alignment_v55?: {
    aligned: boolean
    trend_direction: string
    confidence_adjust: number
    msg: string
  } | null
  // V56: 假突破识别（条件164）
  false_breakout_detection_v56?: {
    is_fake: boolean
    breakout_valid: boolean
    confidence_adjust: number
    msg: string
    retracement_pct: number
    volume_ratio: number
  } | null
  // V56: 中枢结构复杂度分析（条件165）
  zhongshu_structure_complexity_v56?: {
    complexity: string
    overlap_count: number
    confidence_adjust: number
    msg: string
  } | null
  // V56: 波动率自适应仓位建议（条件166）
  volatility_adaptive_position_v56?: {
    atr_value: number
    volatility_level: string
    position_suggestion: string
    confidence_adjust: number
    msg: string
  } | null
  // V56: 多信号共振评分（条件167）
  multi_signal_resonance_v56?: {
    resonance_count: number
    confirming_indicators: string[]
    confidence_adjust: number
    msg: string
  } | null
  // V57: 回踩幅度与时间双重过滤（条件168）
  pullback_filter_v57?: {
    pass_filter: boolean
    pullback_depth_pct: number
    pullback_bars: number
    confidence_adjust: number
    msg: string
  } | null
  // V57: 突破力度验证（条件169）
  breakout_strength_validation_v57?: {
    strength_adequate: boolean
    force_ratio: number
    volume_ratio: number
    confidence_adjust: number
    msg: string
  } | null
  // V57: 中枢背驰检测（条件170）
  zs_divergence_check_v57?: {
    has_divergence: boolean
    divergence_type: string
    confidence_adjust: number
    msg: string
  } | null
  // V57: 信号衰减检测（条件171）
  signal_decay_detection_v57?: {
    is_decaying: boolean
    price_trend: string
    trend_momentum: number
    confidence_adjust: number
    msg: string
  } | null
  // V58: 多时间框架趋势一致性验证（条件172）
  multi_tf_trend_consistency_v58?: {
    short_ma: number
    mid_ma: number
    long_ma: number
    bullish_alignment: boolean
    bearish_alignment: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V58: 成交量堆积验证（条件173）
  volume_accumulation_validation_v58?: {
    volume_ratio: number
    recent_vol: number
    avg_vol_20: number
    volume_adequate: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V58: ATR自适应止损距离（条件174）
  atr_adaptive_stop_v58?: {
    atr_14: number
    stop_loss_price: number
    stop_distance_pct: number
    volatility_level: string
    confidence_adjust: number
    msg: string
  } | null
  // V58: 信号质量综合评分（条件175）
  composite_quality_score_v58?: {
    total_adjust: number
    grade: string
    grade_desc: string
    detail_scores: Record<string, number>
    msg: string
  } | null
  // V59: 波动率自适应MA周期（条件176）
  volatility_adaptive_ma_v59?: {
    adaptive_ma_short: number
    adaptive_ma_mid: number
    adaptive_ma_long: number
    volatility_regime: string
    recommended_period: string
    confidence_adjust: number
    msg: string
  } | null
  // V59: ATR倍数自适应（条件177）
  atr_multiplier_adapt_v59?: {
    atr_14: number
    optimal_multiplier: number
    stop_distance_pct: number
    volatility_regime: string
    confidence_adjust: number
    msg: string
  } | null
  // V59: 多时间框架共振信号（条件178）
  multi_tf_resonance_signal_v59?: {
    short_tf_trend: string
    short_tf_momentum: string
    resonance_score: number
    resonance_strength: string
    confidence_adjust: number
    msg: string
  } | null
  // V59: 信号衰减速度评估（条件179）
  signal_decay_speed_v59?: {
    price_speed_after_signal: number
    decay_rate: string
    signal_strength: string
    confidence_adjust: number
    msg: string
  } | null
  // V60: RSI深度背离过滤（条件180）
  rsi_deep_divergence_v60?: {
    rsi_current: number
    rsi_prev_low: number
    price_curr_low: number
    price_prev_low: number
    divergence_type: string
    divergence_depth: string
    confidence_adjust: number
    msg: string
  } | null
  // V60: MA排列间距强度评分（条件181）
  ma_spacing_strength_v60?: {
    ma5: number
    ma20: number
    ma60: number
    spacing_ratio: number
    alignment: string
    spacing_strength: string
    confidence_adjust: number
    msg: string
  } | null
  // V60: 中枢支撑/阻力距离评分增强（条件182）
  zs_distance_enhanced_v60?: {
    zs_zg: number
    zs_zd: number
    price: number
    distance_to_zg_pct: number
    distance_to_zd_pct: number
    zs_width_pct: number
    position: string
    pullback_confirmed: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V60: KDJ超买超卖确认（条件183）
  kdj_ob_os_confirm_v60?: {
    kdj_k: number
    kdj_d: number
    kdj_j: number
    j_prev: number
    j_trend: string
    ob_os_zone: string
    signal_aligned: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V61: MACD柱状图背离融合（条件184）
  macd_hist_divergence_v61?: {
    divergence_type: string
    macd_hist_curr: number
    macd_hist_prev: number
    price_curr_low: number
    price_prev_low: number
    price_curr_high: number
    price_prev_high: number
    divergence_depth: string
    rsi_fusion: string
    confidence_adjust: number
    msg: string
  } | null
  // V61: 综合多信号评分（条件185）
  composite_signal_score_v61?: {
    composite_score: number
    quality_tier: string
    tier_color: string
    condition_count: number
    total_adjustment: number
    breakdown: Record<string, number>
    decision_help: string
    recommendation: string
  } | null
  // V62: BOLL带宽突破确认（条件186）
  boll_bandwidth_breakout_v62?: {
    boll_upper: number
    boll_lower: number
    band_width: number
    price_position: string
    breakout_confirmed: boolean
    band_trend: string
    confidence_adjust: number
    msg: string
  } | null
  // V62: BOLL带宽压缩反弹确认（条件187）
  boll_bandwidth_reversal_v62?: {
    band_width_rank: number
    squeeze_active: boolean
    reversal_confirmed: boolean
    reversal_type: string
    confidence_adjust: number
    msg: string
  } | null
  // V62: 动态阈值-波动率状态切换（条件188）
  dynamic_threshold_volatility_regime_v62?: {
    atr_pct: number
    volatility_regime: string
    threshold_adjustment: number
    confidence_adjust: number
    msg: string
  } | null
  // V62: 动态阈值-ATR倍数自适应（条件189）
  dynamic_threshold_atr_multiplier_v62?: {
    atr_14: number
    optimal_multiplier: number
    stop_distance_pct: number
    volatility_regime: string
    confidence_adjust: number
    msg: string
  } | null
  // V63: 中枢级别权重优化增强（条件190）
  zhongshu_level_weight_enhanced_v63?: {
    level: string
    distance_score: number
    quality_score: number
    recent_test_score: number
    total_weight_bonus: number
    confidence_adjust: number
    msg: string
  } | null
  // V63: 多周期信号衰减追踪（条件191）
  multi_period_signal_decay_v63?: {
    short_term_momentum: number
    mid_term_momentum: number
    long_term_momentum: number
    overall_health: string
    decay_detected: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V65: 量价背离二次确认增强（条件192）
  volume_price_divergence_secondary_v65?: {
    diverge_confirmed: boolean
    divergence_strength: number
    duration_bars: number
    confidence_adjust: number
    msg: string
  } | null
  // V65: 中枢突破回踩确认（条件193）
  breakout_retest_confirmation_v65?: {
    retest_confirmed: boolean
    retest_depth: number
    breakout_valid: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V65: 波动率压缩突破信号（条件194）
  volatility_compression_breakout_v65?: {
    compression_detected: boolean
    squeeze_score: number
    breakout_strength: number
    confidence_adjust: number
    msg: string
  } | null
  // V65: 买卖点时间窗口新鲜度（条件195）
  signal_time_window_freshness_v65?: {
    bars_since_signal: number
    trend_health: string
    freshness_score: number
    confidence_adjust: number
    msg: string
  } | null
  // V66: MACD动能锥加速确认（条件196）
  macd_momentum_acceleration_v66?: {
    acceleration_detected: boolean
    acceleration_direction: string
    cone_bars: number
    confidence_adjust: number
    msg: string
  } | null
  // V66: 量价配合深度评分（条件197）
  volume_price_coordination_deep_v66?: {
    short_score: number
    mid_score: number
    extreme_flag: string
    overall_score: number
    confidence_adjust: number
    msg: string
  } | null
  // V66: 多时间框架共振强度（条件198）
  multi_tf_convergence_intensity_v66?: {
    short_trend: string
    mid_trend: string
    long_trend: string
    convergence_score: number
    confidence_adjust: number
    msg: string
  } | null
  // V66: 信号执行优先级建议（条件199）
  signal_execution_priority_v66?: {
    priority: number
    priority_label: string
    risk_level: string
    suggested_action: string
    confidence_adjust: number
    msg: string
  } | null
  // V67: 中枢背驰力度量化（条件200）
  zhongshu_divergence_strength_v67?: {
    backchi_ratio: number
    zhongshu_strength: string
    divergence_type: string
    confidence_adjust: number
    msg: string
  } | null
  // V67: 多级别买卖点一致性验证（条件201）
  multi_level_mmd_consistency_v67?: {
    short_dir: string
    mid_dir: string
    long_dir: string
    consistency_score: number
    confidence_adjust: number
    msg: string
  } | null
  // V67: 信号后价格轨迹健康度（条件202）
  post_signal_trajectory_health_v67?: {
    max_drawdown_pct: number
    up_bars: number
    down_bars: number
    trend_quality: string
    confidence_adjust: number
    msg: string
  } | null
  // V67: 动态止损止盈推荐（条件203）
  dynamic_sl_tp_recommendation_v67?: {
    stop_loss: number
    take_profit: number
    risk_reward_ratio: number
    position_size_pct: number
    confidence_adjust: number
    msg: string
  } | null
  // V68: 缺口方向与趋势一致性验证（条件204）
  gap_trend_consistency_v68?: {
    gap_detected: boolean
    gap_direction: string
    trend_alignment: string
    gap_quality: string
    confidence_adjust: number
    msg: string
  } | null
  // V68: 多级别区间套一致性验证（条件205）
  range_set_multi_level_v68?: {
    zhongshu_count: number
    zs_above_price: number
    zs_below_price: number
    multi_level_score: number
    confidence_adjust: number
    msg: string
  } | null
  // V68: 信号后资金流向确认（条件206）
  post_signal_fund_flow_v68?: {
    fund_flow_direction: string
    avg_volume_ratio: number
    flow_confidence: string
    confidence_adjust: number
    msg: string
  } | null
  // V68: 市场风格适配评分（条件207）
  market_regime_adaptation_v68?: {
    atr_pct: number
    volatility_regime: string
    trend_strength: string
    adaptation_score: number
    confidence_adjust: number
    msg: string
  } | null
  // V69: 量价背离二次确认（条件208）
  price_volume_divergence_v69?: {
    divergence_type: string
    price_trend: string
    volume_trend: string
    divergence_strength: number
    confidence_adjust: number
    msg: string
  } | null
  // V69: 结构完整性评分（条件209）
  structural_integrity_v69?: {
    bi_complete: boolean
    bi_sequence_valid: boolean
    zhongshu_valid: boolean
    structural_score: number
    confidence_adjust: number
    msg: string
  } | null
  // V69: 多指标背离融合（条件210）
  multi_indicator_divergence_v69?: {
    macd_divergence: string
    rsi_divergence: string
    kdj_divergence: string
    resonance_count: number
    confidence_adjust: number
    msg: string
  } | null
  // V69: 回踩深度量化（条件211）
  retracement_depth_v69?: {
    retracement_depth_pct: number
    retracement_type: string
    optimal_range: string
    confidence_adjust: number
    msg: string
  } | null
  // V70: 分时量峰检测（条件212）
  volume_peak_detection_v70?: {
    peak_ratio: number
    peak_detected: boolean
    volume_strength: string
    confidence_adjust: number
    msg: string
  } | null
  // V70: 买卖点时间窗口衰减（条件213）
  signal_time_decay_v70?: {
    bar_count: number
    decay_factor: number
    signal_age: string
    confidence_adjust: number
    msg: string
  } | null
  // V70: 假突破二次过滤（条件214）
  false_breakout_filter_v70?: {
    sustained_bars: number
    is_sustained: boolean
    breakout_quality: string
    confidence_adjust: number
    msg: string
  } | null
  // V70: 信号置信度最终校准（条件215）
  final_confidence_calibration_v70?: {
    total_adjust: number
    calibrated_confidence: number
    calibration_level: string
    adjust_count: number
    positive_adjusts: number
    negative_adjusts: number
    msg: string
  } | null
  // V71: 均线排列强度评估（条件216）
  ma_alignment_strength_v71?: {
    alignment: string
    strength: number
    confidence_adjust: number
    msg: string
  } | null
  // V71: 多周期均线共振（条件217）
  multi_tf_ma_resonance_v71?: {
    short_aligned: boolean
    mid_aligned: boolean
    long_aligned: boolean
    resonance_count: number
    confidence_adjust: number
    msg: string
  } | null
  // V71: 买卖点历史胜率回溯（条件218）
  mmd_history_winrate_v71?: {
    lookback_winrate: number
    sample_count: number
    confidence_adjust: number
    msg: string
  } | null
  // V71: 动态风险收益比优化（条件219）
  dynamic_rr_optimization_v71?: {
    stop_loss_pct: number
    take_profit_pct: number
    rr_ratio: number
    atr_based_sl: number
    atr_based_tp: number
    msg: string
  } | null
  // V72: 均线收敛发散状态评估（条件220）
  ma_convergence_divergence_v72?: {
    state: string
    spread_pct: number
    spread_change_pct: number
    convergence_score: number
    confidence_adjust: number
    msg: string
  } | null
  // V72: 支撑/阻力位距离评估（条件221）
  support_resistance_proximity_v72?: {
    current_price: number
    nearest_support: number
    nearest_resistance: number
    support_dist_pct: number
    resistance_dist_pct: number
    proximity_bonus: number
    confidence_adjust: number
    msg: string
  } | null
  // V72: 量价结构质量评分（条件222）
  volume_structure_quality_v72?: {
    up_vol_ratio: number
    down_vol_ratio: number
    volume_health: number
    stability_score: number
    confidence_adjust: number
    msg: string
  } | null
  // V72: 信号衰减速度评估（条件223）
  signal_decay_velocity_v72?: {
    recent_confidences: number[]
    trend_direction: string
    velocity: number
    volatility: number
    confidence_adjust: number
    msg: string
  } | null
  // V73: 买卖点位置风险评估（条件224）
  mmd_position_risk_v73?: {
    position_pct: number
    risk_level: string
    risk_score: number
    confidence_adjust: number
    msg: string
  } | null
  // V73: 中枢突破有效性验证（条件225）
  zhongshu_breakout_validity_v73?: {
    breakout_valid: boolean
    confirm_bars: number
    sustain_ratio: number
    volume_ratio: number
    confidence_adjust: number
    msg: string
  } | null
  // V73: 多指标确认一致性（条件226）
  multi_indicator_consistency_v73?: {
    agreement_count: number
    agreement_ratio: number
    consistency_score: number
    confidence_adjust: number
    msg: string
  } | null
  // V73: 波动率环境适配（条件227）
  volatility_regime_adaptation_v73?: {
    atr_pct: number
    atr_rank: number
    vol_regime: string
    regime_score: number
    confidence_adjust: number
    msg: string
  } | null
  // V74: 量价背离二次确认（条件228）
  volume_price_divergence_secondary_v74?: {
    divergence_type: string
    divergence_strength: number
    confirm_signal: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V74: 趋势动能持续验证（条件229）
  trend_momentum_continuity_v74?: {
    momentum_score: number
    short_term: number
    mid_term: number
    long_term: number
    continuity: string
    confidence_adjust: number
    msg: string
  } | null
  // V74: 中枢重叠度评估（条件230）
  zhongshu_overlap_density_v74?: {
    overlap_density: number
    nearby_zs_count: number
    distance_to_zs: number
    signal_strength: string
    confidence_adjust: number
    msg: string
  } | null
  // V74: 信号共振深度评分（条件231）
  signal_resonance_depth_v74?: {
    depth_score: number
    confirming_dimensions: number
    total_dimensions: number
    resonance_level: string
    confidence_adjust: number
    msg: string
  } | null
  // V75: 回调深度验证（条件232）
  pullback_depth_validation_v75?: {
    pullback_depth: number
    max_retracement: number
    fibonacci_level: string
    confirm_signal: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V75: 中枢区间回踩确认（条件233）
  zhongshu_retracement_confirm_v75?: {
    retracement_type: string
    nearest_zs_dist: number
    bounce_strength: number
    confirm_signal: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V75: 量峰持续时间评分（条件234）
  volume_peak_duration_v75?: {
    peak_duration: number
    avg_vol_ratio: number
    peak_days: number
    confirm_signal: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V75: 多信号时间一致性（条件235）
  multi_signal_time_consistency_v75?: {
    consistency_score: number
    signal_dates: Array<{ name: string; days_ago: number }>
    alignment_ratio: number
    confirm_signal: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V76: 价格结构完整性验证（条件236）
  price_structure_integrity_v76?: {
    structure_score: number
    trend_structure: string
    key_levels_valid: boolean
    confirm_signal: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V76: 趋势方向对齐验证（条件237）
  trend_alignment_validation_v76?: {
    alignment_status: string
    ma_alignment: Array<{ period: number; trend: string }>
    trend_direction: string
    confirm_signal: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V76: 波动率自适应置信度（条件238）
  volatility_adaptive_confidence_v76?: {
    vol_level: string
    atr_ratio: number
    adaptive_confidence: number
    confirm_signal: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V76: 买卖点最终有效性评分（条件239）
  signal_final_validity_v76?: {
    final_validity: string
    validity_score: number
    recommendation: string
    confirm_signal: boolean
    confidence_adjust: number
    msg: string
  } | null
  // V77: 量能分布深度分析（条件240）
  volume_distribution_depth_v77?: {
    energy_zone: string
    volume_rank: number
    support_distance: number
    resistance_distance: number
    confidence_adjust: number
    msg: string
  } | null
  // V77: 中枢结构权重评估（条件241）
  zhongshu_structure_weight_v77?: {
    weight_score: number
    nearest_zs_dist: number
    zs_level: string
    confidence_adjust: number
    msg: string
  } | null
  // V77: 信号新鲜度验证（条件242）
  signal_freshness_validation_v77?: {
    freshness_score: number
    bars_since_signal: number
    age_label: string
    confidence_adjust: number
    msg: string
  } | null
  // V77: 价格动能加速度（条件243）
  price_momentum_acceleration_v77?: {
    acceleration: number
    momentum_direction: string
    acceleration_strength: string
    confidence_adjust: number
    msg: string
  } | null
   // V78: 买卖点周期位置评分（条件244）
   mmd_cycle_position_v78?: {
     position_score: number
     cycle_position: string
     distance_to_low: number
     distance_to_high: number
     confidence_adjust: number
     msg: string
   } | null
   // V78: 多信号时间窗口一致性（条件245）
   multi_signal_consensus_v78?: {
     consensus_score: number
     nearby_buy_count: number
     nearby_sell_count: number
     consensus_level: string
     confidence_adjust: number
     msg: string
   } | null
   // V78: 波动率压缩突破预测（条件246）
   volatility_compression_breakout_v78?: {
     compression_score: number
     boll_width_percentile: number
     breakout_direction: string
     confidence_adjust: number
     msg: string
   } | null
   // V78: 资金流向与价格背离检测（条件247）
   fund_flow_divergence_v78?: {
     divergence_type: string
     money_flow_score: number
     volume_price_correlation: number
     confidence_adjust: number
     msg: string
   } | null
    // V79: 分型稳定性验证（条件248）
    fractal_stability_validation_v79?: {
      stability_score: number
      fractal_status: string
      confidence_adjust: number
      msg: string
    } | null
    // V79: 买卖点距离安全阈值（条件249）
    mmd_distance_safety_v79?: {
      distance_score: number
      bars_to_nearest: number
      safety_level: string
      confidence_adjust: number
      msg: string
    } | null
    // V79: 多级别结构一致性评分（条件250）
    multi_level_structure_consistency_v79?: {
      consistency_score: number
      short_align: boolean
      mid_align: boolean
      long_align: boolean
      confidence_adjust: number
      msg: string
    } | null
    // V79: 价格动能持续性评分（条件251）
    price_momentum_continuity_v79?: {
      momentum_score: number
      acceleration: number
      vol_trend: string
      momentum_level: string
      confidence_adjust: number
      msg: string
    } | null
    // V80: 买卖点与中枢距离验证（条件252）
    mmd_zhongshu_distance_v80?: {
      distance_score: number
      nearest_zs_dist_pct: number
      zs_position: string
      confidence_adjust: number
      msg: string
    } | null
    // V80: 量能配合度评分（条件253）
    volume_confirmation_v80?: {
      confirmation_score: number
      vol_ratio: number
      volume_trend: string
      price_trend: string
      confidence_adjust: number
      msg: string
    } | null
    // V80: 均线排列强度确认（条件254）
    ma_alignment_strength_v80?: {
      alignment_score: number
      ma_alignment: string
      price_position: string
      confidence_adjust: number
      msg: string
    } | null
    // V80: 盈亏比动态评估（条件255）
    dynamic_risk_reward_v80?: {
      rr_ratio: number
      stop_loss_pct: number
      take_profit_pct: number
      risk_level: string
      confidence_adjust: number
      msg: string
    } | null
    // V81: 波动率状态转换检测（条件256）
    volatility_regime_transition_v81?: {
      regime: string
      transition_type: string
      atr_ratio: number
      atr_change_pct: number
      confidence_adjust: number
      msg: string
    } | null
    // V81: 关键支撑阻力强度验证（条件257）
    support_resistance_strength_v81?: {
      strength_level: string
      nearest_sr_dist_pct: number
      sr_count: number
      confidence_adjust: number
      msg: string
    } | null
    // V81: 量价能量分布验证（条件258）
    volume_price_energy_distribution_v81?: {
      energy_zone: string
      energy_score: number
      volume_concentration: number
      confidence_adjust: number
      msg: string
    } | null
    // V81: 信号执行窗口评估（条件259）
    signal_execution_window_v81?: {
      window_quality: string
      volatility_score: number
      liquidity_score: number
      confidence_adjust: number
      msg: string
    } | null
    // V82: 买卖点时间衰减验证（条件260）
    mmd_age_decay_v82?: {
      age_bars: number
      age_label: string
      confidence_adjust: number
      msg: string
    } | null
    // V82: 中枢突破回踩确认（条件261）
    breakout_retest_confirm_v82?: {
      retest_detected: boolean
      retest_quality: string
      confidence_adjust: number
      msg: string
    } | null
    // V82: 多级别MACD共振（条件262）
    macd_multi_tf_resonance_v82?: {
      short_acceleration: number
      mid_trend: string
      resonance: string
      confidence_adjust: number
      msg: string
    } | null
    // V82: 波动率压缩突破确认（条件263）
    volatility_compression_breakout_v82?: {
      compression_level: number
      breakout_strength: number
      volume_confirm: boolean
      confidence_adjust: number
      msg: string
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
  // V76: 四维验证摘要（条件236-239）
  v76_summary?: {
    structure_integrity: 'strong' | 'moderate' | 'weak' | 'invalid' | null
    validity_score: number | null
    recommendation: string
  }
   // V77: 四维度量摘要（条件240-243）
   v77_summary?: {
     quality_level: 'strong' | 'moderate' | 'weak' | 'mixed' | null
     total_adjust: number | null
     positive_count: number | null
     negative_count: number | null
     recommendation: string
     vdd_energy_zone: string | null
     zs_weight_score: number | null
     signal_freshness: string | null
     momentum_direction: string | null
   }
   // V78: 四维度量摘要（条件244-247）
   v78_summary?: {
     quality_level: 'strong' | 'moderate' | 'weak' | 'mixed' | null
     total_adjust: number | null
     positive_count: number | null
     negative_count: number | null
     recommendation: string
     cycle_position: string | null
     consensus_level: string | null
     breakout_direction: string | null
     divergence_type: string | null
    }
    // V79: 四维度量摘要（条件248-251）
    v79_summary?: {
      quality_level: 'strong' | 'moderate' | 'weak' | 'mixed' | null
      total_adjust: number | null
      positive_count: number | null
      negative_count: number | null
      recommendation: string
      fractal_status: string | null
      safety_level: string | null
      consistency_level: string | null
      momentum_level: string | null
    }
    // V80: 四维度量摘要（条件252-255）
    v80_summary?: {
      quality_level: 'strong' | 'moderate' | 'weak' | 'mixed' | null
      total_adjust: number | null
      positive_count: number | null
      negative_count: number | null
      recommendation: string
      zs_position: string | null
      volume_confirmed: string | null
      ma_alignment: string | null
      risk_level: string | null
    }
    // V81: 四维度量摘要（条件256-259）
    v81_summary?: {
      quality_level: 'strong' | 'moderate' | 'weak' | 'mixed' | null
      total_adjust: number | null
      positive_count: number | null
      negative_count: number | null
      recommendation: string
      regime: string | null
      strength_level: string | null
      energy_zone: string | null
      window_quality: string | null
    }
    // V82: 四维度量摘要（条件260-263）
    v82_summary?: {
      quality_level: 'strong' | 'moderate' | 'weak' | 'mixed' | null
      total_adjust: number | null
      positive_count: number | null
      negative_count: number | null
      recommendation: string
      age_label: string | null
      retest_quality: string | null
      resonance: string | null
      compression_level: string | null
    }
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

// ── V64: 多股票对比分析 ────────────────────────────────────────────────────────

export interface MultiStockResult {
  stock_code: string
  stock_name: string
  total_bars?: number
  signal_count: number
  buy_count: number
  sell_count: number
  avg_confidence: number
  condition_breakdown: Record<string, number>
  error?: string
}

export interface MultiStockComparisonResponse {
  stocks: MultiStockResult[]
  count: number
}
