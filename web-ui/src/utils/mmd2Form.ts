/**
 * 2买/2卖 形态识别（V853，第101课三情况）。
 *
 * 原文第101课：2买后走势有三情况——
 *   1. 一般：2买高于1买（依次向上），不创新低；
 *   2. 最强：2买与3买合一（2买位置直接突破中枢 ZG）；
 *   3. 最弱：**2买跌破1买**，完全可以（第101课明确允许）。
 *
 * 本工具按 anchor_val（触发笔终点值=回调低/高点）与配对 1买/1卖 比较：
 *   - 2买 anchor_val < 配对 1买 anchor_val ⇒ 「最弱·跌破1买」（第101课最弱，§2.3 修复前被 50% 门槛吞掉）
 *   - 2卖 anchor_val > 配对 1卖 anchor_val ⇒ 「最弱·突破1卖」（对称）
 *   - 否则 ⇒ 「一般」
 *   - 无配对 1买/1卖 ⇒ null（无法判定，不渲染徽章）
 *
 * 「最强·2-3买合一」需 3买数据，本版未实现（留作后续）。
 *
 * 实测（8 只日线）：2买/2卖 55 个，最弱 21（38%）、一般 34。其中「跌破1买」14 个
 * 即 §2.3 修复（mmd_2nd_max_pullback=None 默认原文）后才可见的信号。
 */
export interface MmdDto {
  type: string // '1buy' | '2buy' | '3buy' | '1sell' | '2sell' | '3sell' | ...
  bar_index?: number | null
  anchor_val?: number | null
  [k: string]: unknown
}

export type Mmd2Form = 'weakest_break_1' | 'general' | null

/** 找 mmds 里 bar_index < 当前、且同方向(1buy↔2buy, 1sell↔2sell) 的最近一个 1买/1卖。 */
function findPairedFirst(all: MmdDto[], m: MmdDto): MmdDto | null {
  const base = m.type === '2buy' ? '1buy' : m.type === '2sell' ? '1sell' : null
  if (!base) return null
  const curBi = m.bar_index ?? 0
  let paired: MmdDto | null = null
  for (const x of all) {
    if (x.type !== base) continue
    const xBi = x.bar_index ?? 0
    if (xBi < curBi && (!paired || xBi > (paired.bar_index ?? 0))) paired = x
  }
  return paired
}

/**
 * 判定 2买/2卖 形态。非 2买/2卖 或无配对 1买/1卖 → null（不渲染徽章）。
 */
export function mmd2Form(all: MmdDto[], m: MmdDto): Mmd2Form {
  if (m.type !== '2buy' && m.type !== '2sell') return null
  const paired = findPairedFirst(all, m)
  if (!paired) return null
  const v2 = m.anchor_val
  const v1 = paired.anchor_val
  if (v2 == null || v1 == null) return null
  if (m.type === '2buy') return v2 < v1 ? 'weakest_break_1' : 'general'
  return v2 > v1 ? 'weakest_break_1' : 'general' // 2卖对称：创新高=最弱
}

/** 徽章 CSS 类。 */
export function mmd2FormClass(form: Mmd2Form): string {
  if (!form) return ''
  return form === 'weakest_break_1' ? 'm2-weakest' : 'm2-general'
}

/** 徽章文字。 */
export function mmd2FormLabel(form: Mmd2Form): string {
  if (!form) return ''
  return form === 'weakest_break_1' ? '⚠最弱·破1买' : '一般'
}

/** 徽章 title（hover 原文依据）。 */
export function mmd2FormTitle(form: Mmd2Form): string {
  if (!form) return ''
  return form === 'weakest_break_1'
    ? '第101课最弱情况：2买跌破1买（原文明确允许）。§2.3 修复前被 50% 回撤门槛吞掉。'
    : '第101课一般情况：2买高于1买，依次向上。'
}
