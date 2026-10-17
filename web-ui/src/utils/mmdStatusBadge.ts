/**
 * 1买/1卖 + 3买/3卖 状态徽章（V853 工具①③）。
 *
 * 工具① 1买趋势背驰定位器（第21/27/29课）：
 *   1买本身已含「下跌确立 + C段MACD面积<A」（趋势背驰点）。第29课后置验证
 *   rebound_verified：True=反弹触及中枢DD/GG（背驰-转折定理符合，确立）；
 *   False=未触及（可能不是真背驰，疑似）；null=数据不足（待验证）。
 *
 * 工具③ 3买突破ZG回踩定位器（第20课）：
 *   3买锚定价 anchor_val = 回踩低点；zs_zg = 中枢上沿。
 *   不破ZG（anchor_val > zs_zg）⇒ 合法3买 + 安全距离 = anchor_val - zs_zg。
 *   3卖对称：anchor_val < zs_zd（不破ZD）。
 *   （3买检测已过滤破ZG，此徽章显式呈现安全距离，离ZG越近风险越高。）
 */
export interface MmdStatusDto {
  type: string
  anchor_val?: number | null
  zs_zg?: number | null
  zs_zd?: number | null
  rebound_verified?: boolean | null
  [k: string]: unknown
}

// ── 工具① 1买/1卖 背驰确立状态（第29课后置验证）──
export type Buy1Status = 'confirmed' | 'suspect' | 'pending' | null

export function mmd1Status(m: MmdStatusDto | null | undefined): Buy1Status {
  if (!m || (m.type !== '1buy' && m.type !== '1sell')) return null
  const rv = m.rebound_verified
  if (rv === true) return 'confirmed'
  if (rv === false) return 'suspect'
  return 'pending'
}

export function mmd1StatusLabel(s: Buy1Status): string {
  if (!s) return ''
  if (s === 'confirmed') return '✓背驰确立'
  if (s === 'suspect') return '⚠疑似背驰'
  return '?待验证'
}

export function mmd1StatusClass(s: Buy1Status): string {
  if (!s) return ''
  if (s === 'confirmed') return 'b1-confirmed'
  if (s === 'suspect') return 'b1-suspect'
  return 'b1-pending'
}

export function mmd1StatusTitle(s: Buy1Status): string {
  if (!s) return ''
  if (s === 'confirmed') return '第29课背驰-转折定理：反弹触及中枢DD/GG，背驰确立（可交易转折点）。'
  if (s === 'suspect') return '第29课：反弹未触及中枢极值，可能不是真背驰（疑似，谨慎）。'
  return '第29课后置验证数据不足（最新信号），待后续行情验证。'
}

// ── 工具③ 3买/3卖 ZG安全距离（第20课）──
export interface Buy3Status {
  ok: boolean // 不破ZG/ZD
  gap: number | null // 安全距离（正=不破，负=破）
  label: string
  class: string
  title: string
}

export function mmd3Status(m: MmdStatusDto | null | undefined): Buy3Status | null {
  if (!m || (m.type !== '3buy' && m.type !== '3sell')) return null
  const a = m.anchor_val
  if (a == null) return null
  if (m.type === '3buy') {
    const zg = m.zs_zg
    if (zg == null) return null
    const gap = +(a - zg).toFixed(2)
    return {
      ok: gap > 0,
      gap,
      label: `回踩${a} vs ZG${zg}`,
      class: gap > 0 ? 'b3-ok' : 'b3-bad',
      title: `第20课：3买=突破中枢ZG后回踩不破ZG。回踩 ${a} ${gap > 0 ? '高于' : '跌破'} ZG ${zg}（差 ${gap > 0 ? '+' : ''}${gap}）。`,
    }
  }
  // 3卖对称：回踩不破ZD
  const zd = m.zs_zd
  if (zd == null) return null
  const gap = +(zd - a).toFixed(2) // ZD - 回踩高点
  return {
    ok: gap > 0,
    gap,
    label: `回踩${a} vs ZD${zd}`,
    class: gap > 0 ? 'b3-ok' : 'b3-bad',
    title: `第20课：3卖=跌破中枢ZD后回踩不破ZD。回踩 ${a} ${gap > 0 ? '低于' : '突破'} ZD ${zd}（差 ${gap > 0 ? '+' : ''}${gap}）。`,
  }
}
