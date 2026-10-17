/**
 * 同级别分解视图（V853，第38课分解 + 第105课机械操作）。
 *
 * 后端 to_dict 的 same_level_segments：每段走势类型含
 *   kind(up/down/none) / n_segments / is_panzheng / is_trend / has_zs /
 *   start_val / end_val / start_date / end_date / lines / zss。
 *
 * 第38课：按同级别走势类型依次切（三段成中枢/不延伸/盘整+盘整）。
 * 第105课：机械操作——只做上涨+盘整段，避开下跌；段结束（背驰/盘整背驰）→机械卖出。
 */
export interface SameLevelSegDto {
  index?: number
  kind?: string // up/down/none
  n_segments?: number
  is_panzheng?: boolean
  is_trend?: boolean
  has_zs?: boolean
  start_val?: number | null
  end_val?: number | null
  start_date?: string | null
  end_date?: string | null
  [k: string]: unknown
}

/** 段方向标签。 */
export function slKindLabel(kind?: string | null): string {
  if (kind === 'up') return '↑上涨'
  if (kind === 'down') return '↓下跌'
  return '—未完成'
}

/** 段方向 CSS 类（着色）。 */
export function slKindClass(kind?: string | null): string {
  if (kind === 'up') return 'sl-up'
  if (kind === 'down') return 'sl-down'
  return 'sl-none'
}

/** 走势类型（第38课：≥2同向中枢=趋势；1中枢=盘整；未完成段=进行中）。 */
export function slTrendLabel(seg: SameLevelSegDto | null | undefined): string {
  if (!seg) return ''
  if (seg.is_trend) return '趋势'
  if (seg.is_panzheng) return '盘整'
  return '进行中'
}

export function slTrendClass(seg: SameLevelSegDto | null | undefined): string {
  if (!seg) return ''
  if (seg.is_trend) return 'slt-trend'
  if (seg.is_panzheng) return 'slt-panzheng'
  return 'slt-ongoing'
}

export interface MechanicalHint {
  action: string // 「机械持有」/「机械观望」/「机械卖出」
  reason: string
  class: string // sl-mech-hold / sl-mech-sell / sl-mech-watch
}

/**
 * 第105课机械操作提示：取**最后一段**走势类型定动作。
 *   - 上涨段（盘整/趋势）⇒ 机械持有（直到段结束=背驰/盘整背驰 → 卖出）
 *   - 下跌段 ⇒ 机械观望（避开下跌，原文：只做上涨+盘整段）
 *   - 未完成/无段 ⇒ 暂无信号
 * 若最后一段是上涨且其后无新段 ⇒ 仍持有；最后一笔背驰提示卖出（由 mmds 判定，此处只给段级方向）。
 */
export function slMechanicalHint(segs: SameLevelSegDto[] | null | undefined): MechanicalHint {
  if (!segs || segs.length === 0) {
    return { action: '暂无分段', reason: '第38课同级别分解未产出段', class: 'sl-mech-watch' }
  }
  const last = segs[segs.length - 1]
  const tlabel = slTrendLabel(last)
  if (last.kind === 'up') {
    return {
      action: '机械持有',
      reason: `当前第${(last.index ?? segs.length)}段=上涨${tlabel}（第105课：只做上涨+盘整段）；段结束（背驰/盘整背驰）→机械卖出`,
      class: 'sl-mech-hold',
    }
  }
  if (last.kind === 'down') {
    return {
      action: '机械观望',
      reason: `当前第${(last.index ?? segs.length)}段=下跌${tlabel}（第105课：避开下跌段，等待上涨段确立再进）`,
      class: 'sl-mech-sell',
    }
  }
  return {
    action: '进行中',
    reason: `当前第${(last.index ?? segs.length)}段未完成（${tlabel}），待方向确立`,
    class: 'sl-mech-watch',
  }
}
