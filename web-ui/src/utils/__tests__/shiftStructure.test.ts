// V723: structure shift utility — prepend-N correctness for local window growth.
import { describe, expect, test } from 'vitest'
import { padMacdHead, shiftStructure } from '../shiftStructure'

describe('shiftStructure', () => {
  test('shifts all index fields by N and preserves null anchors', () => {
    const items = [
      { start_index: 0, end_index: 10, bar_index: 3 },
      { start_index: 10, end_index: 20, bar_index: null },
      { start_index: null, end_index: undefined, anchor_bar_index: 7 },
    ]
    const out = shiftStructure(items as any, 5)
    expect(out[0]).toMatchObject({ start_index: 5, end_index: 15, bar_index: 8 })
    expect(out[1].bar_index).toBeNull()
    expect(out[2].start_index).toBeNull()
    expect(out[2].end_index).toBeUndefined()
    expect(out[2].anchor_bar_index).toBe(12)
  })

  test('shift 0 returns same reference semantics (no-op)', () => {
    const items = [{ bar_index: 2 }]
    expect(shiftStructure(items as any, 0)).toBe(items)
  })

  test('handles undefined/null list and non-integer guards', () => {
    expect(shiftStructure(undefined, 4)).toEqual([])
    expect(shiftStructure(null, 4)).toEqual([])
    const out = shiftStructure([{ bar_index: 1.5 } as any], 3)
    expect(out[0].bar_index).toBe(1.5 + 3)
  })

  test('does not mutate input', () => {
    const items = [{ bar_index: 2 }]
    shiftStructure(items as any, 9)
    expect(items[0].bar_index).toBe(2)
  })
})

describe('padMacdHead', () => {
  test('pads dif/dea/hist heads with null and preserves tail', () => {
    const macd = { dif: [1, 2], dea: [3, 4], hist: [5, 6] }
    const out = padMacdHead(macd, 3)!
    expect(out.dif).toEqual([null, null, null, 1, 2])
    expect(out.dea).toEqual([null, null, null, 3, 4])
    expect(out.hist).toEqual([null, null, null, 5, 6])
  })

  test('shift 0 returns same object', () => {
    const macd = { dif: [1], dea: [2], hist: [3] }
    expect(padMacdHead(macd, 0)).toBe(macd)
  })

  test('undefined input yields undefined', () => {
    expect(padMacdHead(undefined, 5)).toBeUndefined()
  })
})
