/**
 * 买卖点画图「字段契约」回归测试（V731 审计）。
 *
 * 背景（审计发现）：后端 analyser._mmd_dict_core 为每个买卖点输出
 * anchor_val = 分型极值价（1买=底分型低点、1卖=顶分型高点），
 * ChanlunChart 用它在**真实买卖点价格**上画标记；缺失时会退化为
 * 「该K线 low*0.995 / high*1.005」的视觉偏移值 —— 图上标记价格与
 * 模型识别的买卖点价格不符。
 *
 * 历史上（V731 之前）ChanlunView.mapMmds 漏映射 anchor_val，
 * 而 mapBcs 却映射了，导致买卖点标记静默退化、背驰标记正常。
 * 本测试锁死「图上标记必须落在后端 anchor_val 上」，防止回归。
 *
 * 同时锁死 bar_index 搬运（横轴锚定）与全 8 种类型覆盖。
 */

import { describe, expect, test, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'

// V731: 与 ChanlunChart.test.ts 同款 echarts 桩——jsdom 无 canvas，
// 不 stub 的话 zrender 会在 clearRect 上抛错。
let lastOption: any = null
const instance = {
  setOption: (opt: any) => {
    lastOption = opt
  },
  resize: () => undefined,
  dispose: () => undefined,
  getOption: () => undefined,
}
vi.mock('../../echarts-setup', () => {
  const noop = () => undefined
  return {
    default: { init: () => instance, use: noop, registerTheme: noop },
    UP_COLOR: '#ef4146',
    DOWN_COLOR: '#18a058',
    FX_COLOR: '#ffffff',
    FX_BORDER_COLOR: '#1f2430',
  }
})

import ChanlunChart from '../ChanlunChart.vue'
import type { ChanlunMmd } from '../ChanlunChart.vue'

const MMD_TYPES = [
  '1buy',
  '2buy',
  '2buy_s',
  '3buy',
  '1sell',
  '2sell',
  '2sell_s',
  '3sell',
] as const

/** 构造 n 根单调递增的 K 线：bar_index 与下标一一对应，且价格可预测。 */
function mkBars(n: number) {
  return Array.from({ length: n }, (_, i) => {
    const day = (i % 28) + 1
    return {
      // ChanlunChart.buildIndexMap 用 datetime 前 19 字符建索引，必须提供
      datetime: `2024-01-${String(day).padStart(2, '0')}T00:00:00`,
      date: `2024-01-${String(day).padStart(2, '0')}`,
      open: 10 + i * 0.1,
      close: 10 + i * 0.1 + 0.05,
      high: 10 + i * 0.1 + 0.1,
      low: 10 + i * 0.1 - 0.1,
      vol: 1000 + i,
      amount: 0,
    }
  })
}

function mkMmd(type: string, idx: number, anchor: number | undefined): ChanlunMmd {
  const day = (idx % 28) + 1
  const m: ChanlunMmd = {
    type,
    date: `2024-01-${String(day).padStart(2, '0')}`,
    msg: 'test',
    bar_index: idx,
  }
  if (anchor !== undefined) m.anchor_val = anchor
  return m
}

async function renderWith(mmds: ChanlunMmd[], n = 60) {
  lastOption = null
  const wrapper = mount(ChanlunChart, {
    props: {
      bars: mkBars(n),
      mmds,
      bis: [],
      xds: [],
      zss: [],
      fxs: [],
      bcs: [],
    },
    global: { plugins: [createPinia()] },
    // 必须挂到真实 DOM：render() 里 `if (!container.value) return` 否则直接跳过
    attachTo: document.body,
  })
  await flushPromises()
  wrapper.unmount()
  return { opt: lastOption }
}

/**
 * 买卖点在 ChanlunChart 里是「买点/卖点」两条 scatter series 的 data
 * （不是 markPoint），data 项为 { name, value:[xIdx, price], ... }。
 */
function collectMarkPoints(opt: any): any[] {
  const out: any[] = []
  for (const s of opt?.series ?? []) {
    if (s?.name !== '买点' && s?.name !== '卖点') continue
    for (const d of s?.data ?? []) {
      out.push({ name: d.name, coord: d.value })
    }
  }
  return out.filter(Boolean)
}

describe('买卖点画图字段契约（anchor_val / bar_index）', () => {
  test('ChanlunChart 使用 anchor_val 作为标记价格，而非 low/high 偏移', async () => {
    // 第 30 根 K 线 low = 10+3.0-0.1 = 12.9；fallback 会画 12.9*0.995 = 12.8355
    // 这里 anchor_val 给 12.50，与 fallback 明显不同，可区分两条分支
    const { opt } = await renderWith([mkMmd('1buy', 30, 12.5)])
    const buy = collectMarkPoints(opt).find((p: any) => p.name === '1buy')
    expect(buy, '应画出 1buy 标记').toBeTruthy()
    // 纵轴必须精确等于 anchor_val（12.5），不能是 12.8355 之类的偏移值
    expect(buy.coord[1]).toBeCloseTo(12.5, 6)
    // 横轴必须精确等于 bar_index
    expect(buy.coord[0]).toBe(30)
  })

  test('anchor_val 缺失时静默退化为 low*0.995（现状对照，用于证明契约价值）', async () => {
    const bars = mkBars(60)
    const { opt } = await renderWith([mkMmd('1buy', 30, undefined)])
    const buy = collectMarkPoints(opt).find((p: any) => p.name === '1buy')
    expect(buy).toBeTruthy()
    // 退化分支：12.9 * 0.995 —— 说明 anchor_val 一旦丢失，标记价格即失真
    expect(buy.coord[1]).toBeCloseTo(bars[30].low * 0.995, 6)
  })

  test('全部 8 种买卖点类型都能取到视觉定义（无 undefined 导致漏画）', async () => {
    const mmds = MMD_TYPES.map((t, i) => mkMmd(t, 8 + i * 3, 11 + i))
    const { opt } = await renderWith(mmds)
    const names = new Set(collectMarkPoints(opt).map((p: any) => p.name))
    for (const t of MMD_TYPES) {
      expect(names.has(t), `买卖点类型 ${t} 未画出`).toBe(true)
    }
  })
})
