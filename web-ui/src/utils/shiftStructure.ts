// V723: prepend earlier bars + shift structure indexes (local window growth).
//
// Server structures (bis/xds/zss/mmds/fxs/bcs + macd series) are computed for
// the request window; start_index/end_index/bar_index/anchor_bar_index are
// window-relative offsets. When the view prepends real history bars locally
// (no re-analysis), these indexes must shift by N = earlier.length or the
// chart draws structures at the wrong bars.

interface IndexFields {
  start_index?: number | null
  end_index?: number | null
  bar_index?: number | null
  anchor_bar_index?: number | null
  [k: string]: unknown
}

function shiftItem<T extends IndexFields>(item: T, shift: number): T {
  const out: IndexFields = { ...item }
  for (const key of ['start_index', 'end_index', 'bar_index', 'anchor_bar_index'] as const) {
    const v = out[key]
    if (typeof v === 'number') out[key] = v + shift
  }
  return out as T
}

/** Shift a structure list by `shift` bars (no-op for shift 0 / empty). */
export function shiftStructure<T extends IndexFields>(
  items: T[] | undefined | null,
  shift: number,
): T[] {
  if (!items || shift === 0) return items ?? []
  return items.map((it) => shiftItem(it, shift))
}

interface MacdSeries {
  dif: (number | null)[]
  dea: (number | null)[]
  hist: (number | null)[]
}

/** Pad macd series heads with null (aligned with prepended bars). */
export function padMacdHead<T extends MacdSeries>(
  macd: T | undefined | null,
  shift: number,
): T | undefined {
  if (!macd || shift === 0) return macd ?? undefined
  const pre = (): (number | null)[] => [
    ...Array.from({ length: shift }, () => null),
  ]
  return {
    ...macd,
    dif: [...pre(), ...macd.dif],
    dea: [...pre(), ...macd.dea],
    hist: [...pre(), ...macd.hist],
  } as T
}
