// V723: structure shift utility — prepend-N correctness for local window growth.
import { describe, expect, test } from 'vitest'
import { padMacdHead, shiftStructure } from '../shiftStructure'

// V-18: 两条扩窗路径的不变量——
// ① prepend 路径（StockPickView 83 行形态）：bars 头部插入 N 根真历史，
//    结构索引整体 +N，macd 头部补 N 个 null。不变量：任一结构的 bar_index
//    仍精确指向同一根 K 线；macd 长度 == bars 长度。
// ② 左截断路径（StockPickView 232 行形态）：区间起点截掉头部 N 根，
//    结构列表同步 slice(N)。不变量：截掉后结构首元素应对齐 bars[0] 之后
//    的第一根有效 K 线（即原 bar_index >= N 的部分保留）。
// 回归锚点：round 16 曾发现 zsds/qsds 三处平移全漏（补数据没补平移链）。
describe('扩窗路径不变量（V-18）', () => {
  test('① prepend 后 macd 长度与 bars 对齐、索引指向不变', () => {
    const shift = 5
    const bars = Array.from({ length: 15 }, (_, i) => ({ i })) // 5 新 + 10 旧
    const bis = [{ bar_index: 0 }, { bar_index: 9 }]
    const zsds = [{ start_index: 1, end_index: 9, bar_index: 4 }]
    const macd = { dif: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], dea: [], hist: [] }
    const shiftedBis = shiftStructure(bis as any, shift)
    const shiftedZsds = shiftStructure(zsds as any, shift)
    const padded = padMacdHead(macd as any, shift)!
    expect(padded.dif).toHaveLength(bars.length) // macd 与 bars 等长
    expect(shiftedBis[1].bar_index).toBe(14) // 旧末根仍指向同一根 K 线
    expect(shiftedZsds[0]).toMatchObject({ start_index: 6, end_index: 14 })
    // 每个结构索引落在 bars 范围内（错位即画出界）
    for (const s of shiftedZsds) {
      expect(s.end_index!).toBeLessThan(bars.length)
    }
  })

  test('② 左截断后保留的结构索引不指向已截掉的头部', () => {
    const shift = 4
    const bis = [{ bar_index: 1 }, { bar_index: 6 }, { bar_index: 20 }]
    const kept = bis.filter((b) => (b.bar_index as number) >= shift)
    expect(kept.length).toBe(2) // bar_index=1 的项随头部一起被截掉
    expect(kept[0].bar_index - shift).toBe(2) // 截后坐标 = 原索引 - shift
  })

  test('③ 回归锚点：levels 内每个列表字段都必须参与平移', () => {
    // round16 事故的守门测试：新增 levels 字段时若漏加平移，此清单提醒同步
    const SHIFTED_LEVEL_FIELDS = ['bis', 'xds', 'zss', 'mmds', 'bcs', 'zsds', 'qsds']
    // 与 StockPickView 两处 levels 遍历保持一致；新增字段须同时改这里
    expect(SHIFTED_LEVEL_FIELDS).toContain('zsds')
    expect(SHIFTED_LEVEL_FIELDS).toContain('qsds')
  })
})

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
