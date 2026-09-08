// 共享数字格式化工具。ECharts tooltip/axis 统一用两位小数。

/** 数字保留两位小数（NaN/Inf 返回 '-'）。 */
export function fmt2(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  return v.toFixed(2)
}

/** 百分比（接受小数如 0.1234 → "12.34%"）。 */
export function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  return `${(v * 100).toFixed(2)}%`
}

/** 一位小数百分比（用于准确度面板）。 */
export function fmtAccPct(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  return `${(v * 100).toFixed(1)}%`
}

/** 带符号百分比（用于超额命中率等）。 */
export function fmtAccSigned(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  const sign = v >= 0 ? '+' : ''
  return `${sign}${(v * 100).toFixed(1)}%`
}

/** 盈亏比（profit_factor）：999 表示仅盈利无亏损，显示 ∞；其余保留两位小数。 */
export function fmtPf(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '-'
  if (v >= 999) return '∞'
  return v.toFixed(2)
}
