/**
 * 区间套徽章三态逻辑（V853，第61课状态机：ASSUMED/CONFIRMED/REJECTED）。
 *
 * 后端 compute_qujiantao / compute_qujiantao_cross_period 现输出 `state` 字段。
 * 三态区分（原文第61课）：
 *   - CONFIRMED：本重背驰确认（力度衰减），可交易转折点 → 🔗 套（qt-ok 绿）。
 *   - REJECTED ：背驰段不成立（力度未衰减），别当背驰段交易 → 🔗✗（qt-reject 红）。
 *   - ASSUMED  ：待观察（暂无证据，可能继续确认）→ 🔗?（qt-assumed 灰）。
 *
 * 口径区分（V731）：method='cross_period' 才是真实双周期（缠论原文语义）；
 * 其他（recursive/single）实测确认率 ~3%，标 qt-recursive 与真跨周期区分。
 *
 * 兼容：旧响应无 `state` 时按 `nested` 回退（nested→CONFIRMED，否则 ASSUMED）；
 * REJECTED 不回退出（旧响应没有「背驰段不成立」概念）。
 */
export interface QujiantaoDto {
  nested?: boolean | null
  state?: string | null
  score?: number | null
  method?: string | null
  msg?: string | null
  [k: string]: unknown
}

export const QT_RECURSIVE_WARN =
  '⚠ 非真跨周期：本标记来自同序列递归级别（或单级别近似），实测确认率约 3%，' +
  '不能等同于缠论原文的区间套。'

/** 权威 state：优先用后端 state 字段，缺失时按 nested 回退。 */
export function qtResolvedState(qt: QujiantaoDto | null | undefined): string {
  if (!qt) return ''
  if (qt.state) return String(qt.state)
  return qt.nested ? 'CONFIRMED' : 'ASSUMED'
}

/** 徽章 CSS 类。 */
export function qtBadgeClass(qt: QujiantaoDto | null | undefined): string {
  if (!qt) return ''
  const st = qtResolvedState(qt)
  const isReal = qt.method === 'cross_period'
  // 递归口径（method≠cross_period）即便确认也标 qt-recursive，与真跨周期区分
  if (!isReal) return st === 'CONFIRMED' ? 'qt-recursive' : 'qt-no'
  // 真跨周期：三态分色
  if (st === 'CONFIRMED') return 'qt-ok'
  if (st === 'REJECTED') return 'qt-reject'
  return 'qt-assumed'
}

/** 徽章文字（不含 score 百分比，调用方自行拼接）。 */
export function qtBadgeLabel(qt: QujiantaoDto | null | undefined): string {
  if (!qt) return ''
  const st = qtResolvedState(qt)
  if (qt.method !== 'cross_period') {
    // 递归口径：确认=🔗级?（存疑），未确认/不成立=🔗✗
    return st === 'CONFIRMED' ? '🔗 级?' : '🔗✗'
  }
  // 真跨周期三态
  if (st === 'CONFIRMED') return '🔗 套'
  if (st === 'REJECTED') return '🔗✗'
  return '🔗?'
}

/** 徽章 title（hover 文案）。递归口径前置来源警告。 */
export function qtBadgeTitle(qt: QujiantaoDto | null | undefined): string {
  if (!qt) return ''
  const base = qt.msg ?? ''
  if (qt.method === 'cross_period') return base
  return QT_RECURSIVE_WARN + base
}

/**
 * 图表 markPoint 用：区间套三态颜色（ECharts itemStyle.borderColor）。
 * 与 qtBadgeClass 同口径（真跨周期三态分色 / 递归口径降级）。
 * 返回空串表示无 qujiantao 数据（单级别视图，不加 ring）。
 */
export function qtStateColor(qt: QujiantaoDto | null | undefined): string {
  if (!qt) return ''
  const st = qtResolvedState(qt)
  const isReal = qt.method === 'cross_period'
  // 与 qtBadgeClass 同口径：递归口径 CONFIRMED=amber(qt-recursive)，其余=muted 灰(qt-no)
  if (!isReal) return st === 'CONFIRMED' ? '#f39c12' : '#95a5a6'
  if (st === 'CONFIRMED') return '#2ecc71' // 真背驰，力度衰减确认 → 绿
  if (st === 'REJECTED') return '#e74c3c' // 背驰段不成立，力度未衰减 → 红
  return '#95a5a6' // ASSUMED 待观察 → 灰
}

/**
 * 图表 markPoint 用：区间套三态标记字（label.formatter）。
 * ✓=确认 / ✕=不成立 / ?=待观察；递归口径确认带 ?（存疑）。
 * 返回空串表示无 qujiantao 数据（回落到 rebound_verified ⚠ 或隐藏）。
 */
export function qtStateMark(qt: QujiantaoDto | null | undefined): string {
  if (!qt) return ''
  const st = qtResolvedState(qt)
  if (st === 'CONFIRMED') return qt.method === 'cross_period' ? '✓' : '✓?'
  if (st === 'REJECTED') return '✕'
  return '?'
}
