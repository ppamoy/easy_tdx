/**
 * 「买卖点核对」页核心统计逻辑的单元测试。
 *
 * 页面把「信号 vs 随机基准」的判定写在组件里，这里抽出**同构的纯函数**复算，
 * 保证判定规则可测、可复核（组件里的实现必须与这里一致）。
 *
 * 覆盖：
 *   1. 命中率/超额的计算方向（买点看涨、卖点看跌）
 *   2. **只有胜过随机才算有效** —— 这是本页的核心主张，必须有牙：
 *      一个「信号全对但这段行情本身也在涨」的合成序列，必须判为无效
 *   3. 随机基准可复现（固定种子）
 */

import { describe, expect, it } from 'vitest'

describe('买卖点核对：信号 vs 随机基准', () => {
  const HORIZON = 5

  /** 与页面 stats computed 同构的实现 */
  function rng(seed: number) {
    let s = seed >>> 0
    return () => {
      s = (s * 1664525 + 1013904223) >>> 0
      return s / 4294967296
    }
  }

  function calc(closes: number[], idxs: number[], isBuy: boolean, seedBase: number) {
    const n = closes.length
    const usable = idxs.filter((i) => i + HORIZON < n)
    if (!usable.length) return null
    const fwd = usable.map((i) => closes[i + HORIZON] / closes[i] - 1)
    const avg = (fwd.reduce((a, b) => a + b, 0) / fwd.length) * 100
    const hitRate =
      fwd.filter((r) => (isBuy ? r > 0 : r < 0)).length / fwd.length

    const rand = rng(42 + seedBase)
    const eligible = n - HORIZON
    const rndFwd: number[] = []
    for (let k = 0; k < fwd.length; k++) {
      const j = Math.floor(rand() * eligible)
      rndFwd.push(closes[j + HORIZON] / closes[j] - 1)
    }
    const rndAvg = (rndFwd.reduce((a, b) => a + b, 0) / rndFwd.length) * 100
    const rndHit = rndFwd.filter((r) => (isBuy ? r > 0 : r < 0)).length / rndFwd.length

    const excess = avg - rndAvg
    let verdict = '❌ 无效'
    if (excess > 1 && hitRate > rndHit) verdict = '✅ 有效'
    else if (excess > 0 && hitRate > rndHit) verdict = '⚠️ 偏弱'
    return { avg, hitRate, rndAvg, rndHit, excess, verdict }
  }

  it('买点方向：上涨算命中', () => {
    // 单调上涨序列：任何买点都命中
    const closes = Array.from({ length: 50 }, (_, i) => 100 + i)
    const r = calc(closes, [0, 5, 10], true, 1)!
    expect(r.hitRate).toBe(1)
    expect(r.avg).toBeGreaterThan(0)
  })

  it('卖点方向：下跌算命中', () => {
    const closes = Array.from({ length: 50 }, (_, i) => 100 - i * 0.5)
    const r = calc(closes, [0, 5, 10], false, 1)!
    expect(r.hitRate).toBe(1)
  })

  it('牙齿：慢牛行情里「买点全中」也必须判为无效（因为随机也全中）', () => {
    // 关键用例：这段行情**本身**在稳步上涨，任何时刻买入都能赚。
    // 信号的 100% 命中率**没有信息量** ⇒ 必须判 ❌，不能判 ✅。
    const closes = Array.from({ length: 200 }, (_, i) => 100 * Math.pow(1.002, i))
    const r = calc(closes, [10, 30, 50, 70, 90], true, 1)!
    // 前提：信号确实全中、且收益为正
    expect(r.hitRate).toBe(1)
    expect(r.avg).toBeGreaterThan(0)
    // 判据：不能胜过随机 ⇒ 无效
    expect(r.rndHit).toBe(1)
    expect(r.hitRate > r.rndHit).toBe(false)
    expect(r.verdict).toBe('❌ 无效')
  })

  it('牙齿：真有信息量的信号（买在局部低点）判为有效', () => {
    // 构造：整体横盘（随机基准≈0），但信号专挑**局部低点** ⇒ 超额明显
    const closes: number[] = []
    for (let i = 0; i < 200; i++) {
      // 10 根一周期的正弦，谷底在 phase=7 附近
      const phase = i % 10
      closes.push(100 + 5 * Math.sin((phase / 10) * Math.PI * 2))
    }
    const lows = [7, 17, 27, 37, 47, 57, 67, 77].filter((i) => i + HORIZON < 200)
    const r = calc(closes, lows, true, 1)!
    // 前提：整体横盘 ⇒ 随机基准接近 0
    expect(Math.abs(r.rndAvg)).toBeLessThan(1)
    // 判据：买在谷底 ⇒ 超额为正且明显
    expect(r.excess).toBeGreaterThan(1)
    expect(r.verdict).toBe('✅ 有效')
  })

  it('随机基准可复现（同种子同结果）', () => {
    const closes = Array.from({ length: 100 }, (_, i) => 100 + Math.sin(i) * 3)
    const a = calc(closes, [5, 15, 25], true, 1)!
    const b = calc(closes, [5, 15, 25], true, 1)!
    expect(a.rndAvg).toBe(b.rndAvg)
    expect(a.rndHit).toBe(b.rndHit)
  })

  it('数据不足时返回 null（不产生假结论）', () => {
    const closes = [1, 2, 3]
    expect(calc(closes, [0], true, 1)).toBeNull()
  })
})
