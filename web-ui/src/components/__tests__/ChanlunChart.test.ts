// ChanlunChart 渲染结构测试（v590）：验证 MACD 副图、背驰主图/副图、
// 买卖点标注、中枢区域、笔/线段/分型都进入 ECharts option。
import { describe, expect, test, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const setOption = vi.fn()
let lastOption: any = null

// V723: 可控的 mock 实例——测试用例可注入 getOption 返回值，验证 prepend 视口保持
const instance = {
  setOption: (opt: any) => {
    lastOption = opt
    setOption(opt)
  },
  resize: () => undefined,
  dispose: () => undefined,
  getOption: () => mockedZoom, // 测试可覆盖 mockedZoom
}
let mockedZoom: any = undefined

vi.mock('../../echarts-setup', () => {
  const noop = () => undefined
  const stub = {
    init: () => instance,
    use: noop,
    registerTheme: noop,
  }
  return {
    default: stub,
    UP_COLOR: '#ef4146',
    DOWN_COLOR: '#18a058',
    FX_COLOR: '#ffffff',
    FX_BORDER_COLOR: '#1f2430',
    // 必须与真实 echarts-setup.ts 保持一致。测试用 instanceof 之外的方式断言分型形状，
    // 这里写死 'circle' 是为了让「有人把分型改回 triangle」在**测试**里也立刻变红
    // （scripts/check_fx_symbol.py 是第二道闸）。
    FX_SYMBOL: 'circle',
  }
})

import ChanlunChart from '../ChanlunChart.vue'
import { UP_COLOR, DOWN_COLOR, FX_COLOR, FX_SYMBOL } from '../../echarts-setup'
import { setColorScheme } from '../../colors'

function bar(i: number) {
  const d = new Date(Date.UTC(2024, 0, 2 + i)).toISOString().slice(0, 10) + 'T00:00:00'
  const price = 10 + Math.sin(i / 10) + i * 0.01
  return {
    datetime: d,
    open: +(price - 0.1).toFixed(3),
    close: +(price + 0.1).toFixed(3),
    high: +(price + 0.4).toFixed(3),
    low: +(price - 0.4).toFixed(3),
    vol: 1000 + i,
    amount: 0,
  }
}

const bars = Array.from({ length: 160 }, (_, i) => bar(i))
const fdate = (i: number) => bars[i].datetime

function findSeries(name: string) {
  return lastOption.series.find((s: any) => s.name === name)
}

describe('ChanlunChart 结构渲染', () => {
  test('MACD / 背驰 / 买卖点 / 中枢 / 笔 / 线段均渲染', () => {
    mount(ChanlunChart, {
      props: {
        bars,
        bis: [
          {
            index: 0,
            direction: 'up',
            start_date: fdate(88),
            end_date: fdate(115),
            high: 12.6,
            low: 8.6,
            start_val: 8.6,
            end_val: 12.5,
            start_index: 88,
            end_index: 115,
            done: true,
          },
          {
            index: 1,
            direction: 'down',
            start_date: fdate(115),
            end_date: fdate(130),
            high: 12.5,
            low: 10.4,
            start_val: 12.5,
            end_val: 10.4,
            start_index: 115,
            end_index: 130,
            done: true,
          },
          {
            index: 2,
            direction: 'up',
            start_date: fdate(130),
            end_date: fdate(150),
            high: 14.0,
            low: 10.4,
            start_val: 10.4,
            end_val: 14.0,
            start_index: 130,
            end_index: 150,
            done: true,
          },
          {
            index: 3,
            direction: 'down',
            start_date: fdate(150),
            end_date: fdate(158),
            high: 14.0,
            low: 9.5,
            start_val: 14.0,
            end_val: 9.5,
            start_index: 150,
            end_index: 158,
            done: true,
          },
        ],
        xds: [
          {
            index: 0,
            direction: 'up',
            start_date: fdate(88),
            end_date: fdate(130),
            high: 12.6,
            low: 8.6,
            start_val: 8.6,
            end_val: 12.5,
            start_index: 88,
            end_index: 130,
          },
          {
            index: 1,
            direction: 'down',
            start_date: fdate(130),
            end_date: fdate(158),
            high: 14.0,
            low: 9.5,
            start_val: 14.0,
            end_val: 9.5,
            start_index: 130,
            end_index: 158,
          },
        ],
        zss: [
          {
            index: 0,
            zg: 11.8,
            zd: 10.8,
            gg: 12.5,
            dd: 10.4,
            line_count: 3,
            start_date: fdate(100),
            end_date: fdate(126),
            start_index: 100,
            end_index: 126,
            done: true,
          },
        ],
        mmds: [
          { type: '1buy', date: fdate(95), bar_index: 95, anchor_val: 8.0, msg: 'm' },
          { type: '1sell', date: fdate(150), bar_index: 150, anchor_val: 14.0, msg: 'm' },
        ],
        fxs: [
          { fx_type: 'di', date: fdate(88), val: 8.6, bar_index: 88 },
          { fx_type: 'ding', date: fdate(150), val: 14.0, bar_index: 150 },
        ],
        bcs: [
          {
            type: 'bi',
            bc: true,
            date: fdate(148),
            bar_index: 148,
            anchor_val: 12.6,
            anchor_bar_index: 148,
            msg: 'm',
          },
        ],
        macd: {
          dif: bars.map((_, i) => Math.sin(i / 9) * 0.3),
          dea: bars.map((_, i) => Math.sin(i / 9) * 0.2),
          hist: bars.map((_, i) => Math.sin(i / 9) * 0.4),
        },
        frequency: 'daily',
        compact: true,
      },
      attachTo: document.body,
    })

    expect(setOption).toHaveBeenCalled()

    const macdSeries = findSeries('MACD')
    expect(macdSeries).toBeTruthy()
    expect(macdSeries.data).toHaveLength(bars.length)

    const bi = findSeries('笔(虚线)')
    expect(bi?.markLine?.data).toHaveLength(4)

    const xd = findSeries('线段(实线)')
    expect(xd?.markLine?.data).toHaveLength(2)

    const zs = findSeries('中枢')
    expect(zs?.markArea?.data).toHaveLength(1)

    const buyMmd = findSeries('买点')
    expect(buyMmd?.data).toHaveLength(1)
    expect(buyMmd?.data[0].symbol).toBe('triangle') // 1buy → ▲（per-item symbol）
    const sellMmd = findSeries('卖点')
    expect(sellMmd?.data).toHaveLength(1)
    expect(sellMmd?.symbolRotate).toBe(180) // 1sell → ▼

    const bcSub = findSeries('背驰')
    expect(bcSub?.data).toHaveLength(1)

    const bcMain = findSeries('背驰(主图)')
    expect(bcMain).toBeTruthy()
    expect(bcMain?.data).toHaveLength(1)

    // 未提供走势段/趋势段数据时，不创建空 series
    expect(findSeries('走势段(粗实线)')).toBeUndefined()
    expect(findSeries('趋势段(粗虚线)')).toBeUndefined()
  })

  test('走势段/趋势段以独立 series 渲染', () => {
    mount(ChanlunChart, {
      props: {
        bars,
        bis: [],
        xds: [],
        zsds: [
          {
            index: 0,
            direction: 'up',
            start_date: fdate(88),
            end_date: fdate(130),
            high: 12.6,
            low: 8.6,
            start_val: 8.6,
            end_val: 12.5,
            start_index: 88,
            end_index: 130,
          },
        ],
        qsds: [
          {
            index: 0,
            direction: 'down',
            start_date: fdate(130),
            end_date: fdate(158),
            high: 14.0,
            low: 9.5,
            start_val: 14.0,
            end_val: 9.5,
            start_index: 130,
            end_index: 158,
          },
        ],
        zss: [],
        mmds: [],
        frequency: 'daily',
        compact: true,
      },
      attachTo: document.body,
    })

    const zsd = findSeries('走势段(粗实线)')
    expect(zsd?.markLine?.data).toHaveLength(1)
    expect(zsd?.markLine?.data[0][0]?.lineStyle?.width).toBe(2)
    const qsd = findSeries('趋势段(粗虚线)')
    expect(qsd?.markLine?.data).toHaveLength(1)
    expect(qsd?.markLine?.data[0][0]?.lineStyle?.width).toBe(2)
    expect(lastOption.legend.data).toContain('走势段(粗实线)')
    expect(lastOption.legend.data).toContain('趋势段(粗虚线)')
  })

  test('仅趋势段数据时只渲染趋势段 series', () => {
    mount(ChanlunChart, {
      props: {
        bars,
        bis: [],
        xds: [],
        qsds: [
          {
            index: 0,
            direction: 'up',
            start_date: fdate(88),
            end_date: fdate(130),
            high: 12.6,
            low: 8.6,
            start_val: 8.6,
            end_val: 12.5,
            start_index: 88,
            end_index: 130,
          },
        ],
        zss: [],
        mmds: [],
        frequency: 'daily',
        compact: true,
      },
      attachTo: document.body,
    })

    expect(findSeries('走势段(粗实线)')).toBeUndefined()
    expect(findSeries('趋势段(粗虚线)')?.markLine?.data).toHaveLength(1)
  })

  test('仅走势段数据时只渲染走势段 series', () => {
    mount(ChanlunChart, {
      props: {
        bars,
        bis: [],
        xds: [],
        zsds: [
          {
            index: 0,
            direction: 'down',
            start_date: fdate(88),
            end_date: fdate(130),
            high: 12.6,
            low: 8.6,
            start_val: 12.6,
            end_val: 8.6,
            start_index: 88,
            end_index: 130,
          },
        ],
        zss: [],
        mmds: [],
        frequency: 'daily',
        compact: true,
      },
      attachTo: document.body,
    })

    expect(findSeries('走势段(粗实线)')?.markLine?.data).toHaveLength(1)
    expect(findSeries('趋势段(粗虚线)')).toBeUndefined()
  })

  test('showZsds=false 时不渲染走势段/趋势段', () => {
    mount(ChanlunChart, {
      props: {
        bars,
        bis: [],
        xds: [],
        zsds: [
          {
            index: 0,
            direction: 'up',
            start_date: fdate(88),
            end_date: fdate(130),
            high: 12.6,
            low: 8.6,
            start_val: 8.6,
            end_val: 12.5,
            start_index: 88,
            end_index: 130,
          },
        ],
        qsds: [
          {
            index: 0,
            direction: 'down',
            start_date: fdate(130),
            end_date: fdate(158),
            high: 14.0,
            low: 9.5,
            start_val: 14.0,
            end_val: 9.5,
            start_index: 130,
            end_index: 158,
          },
        ],
        showZsds: false,
        zss: [],
        mmds: [],
        frequency: 'daily',
        compact: true,
      },
      attachTo: document.body,
    })

    expect(findSeries('走势段(粗实线)')).toBeUndefined()
    expect(findSeries('趋势段(粗虚线)')).toBeUndefined()
  })

  test('showFractals=false 时不渲染分型 series', () => {
    mount(ChanlunChart, {
      props: {
        bars,
        bis: [],
        xds: [],
        fxs: [
          { fx_type: 'di', date: fdate(88), val: 8.6, bar_index: 88 },
          { fx_type: 'ding', date: fdate(150), val: 14.0, bar_index: 150 },
        ],
        showFractals: false,
        zss: [],
        mmds: [],
        frequency: 'daily',
        compact: true,
      },
      attachTo: document.body,
    })

    expect(findSeries('顶分型')?.data).toHaveLength(0)
    expect(findSeries('底分型')?.data).toHaveLength(0)
    expect(lastOption.legend.data).not.toContain('顶分型')
  })

  test('传了 validFxs 时优先渲染它，不渲染含违规对的原始 fxs', () => {
    // 用户反馈「2024-12-17 底 → 12-18 顶 → 12-19 底」连着三天都标了分型：
    // 原始 fractals 是逐三根滑动窗口扫出来的，相邻分型共用 K 线，违反缠论原文
    // 「相邻分型之间至少 1 根独立K线」的要求。展示层必须优先用笔端点分型。
    const dirtyFx = [
      { fx_type: 'di', date: fdate(100), val: 8.6, bar_index: 100 },
      { fx_type: 'ding', date: fdate(101), val: 9.0, bar_index: 101 }, // 与上共用K线
      { fx_type: 'di', date: fdate(102), val: 8.4, bar_index: 102 }, // 与上共用K线
    ]
    const cleanFx = [{ fx_type: 'di', date: fdate(100), val: 8.6, bar_index: 100 }]

    mount(ChanlunChart, {
      props: {
        bars,
        bis: [],
        xds: [],
        fxs: dirtyFx,
        validFxs: cleanFx,
        zss: [],
        mmds: [],
        frequency: 'daily',
        compact: true,
      },
      attachTo: document.body,
    })

    const top = findSeries('顶分型')
    const bot = findSeries('底分型')
    // 只能画出 validFxs：1 个底、0 个顶。那个违规的 12-18 式「顶」不得出现。
    expect(bot?.data).toHaveLength(1)
    expect(top?.data).toHaveLength(0)
    expect(bot?.data[0].value[0]).toBe(100)
  })

  test('validFxs 为空数组时不得静默回退到脏的 fxs', () => {
    // 「传了但为空」表示本窗口确实没有合规分型。历史上这里写成
    // `validFxs && validFxs.length ? validFxs : fxs`，导致空数组时退回含违规对的
    // 原始列表，伪分型照样画出来——这正是回测页/训练页长期显示错误标注的原因。
    mount(ChanlunChart, {
      props: {
        bars,
        bis: [],
        xds: [],
        fxs: [
          { fx_type: 'di', date: fdate(100), val: 8.6, bar_index: 100 },
          { fx_type: 'ding', date: fdate(101), val: 9.0, bar_index: 101 },
        ],
        validFxs: [],
        zss: [],
        mmds: [],
        frequency: 'daily',
        compact: true,
      },
      attachTo: document.body,
    })

    expect(findSeries('底分型')?.data).toHaveLength(0)
    expect(findSeries('顶分型')?.data).toHaveLength(0)
  })

  test('完全不传 validFxs 时才回退到 fxs（老调用方兼容）', () => {
    mount(ChanlunChart, {
      props: {
        bars,
        bis: [],
        xds: [],
        fxs: [
          { fx_type: 'di', date: fdate(100), val: 8.6, bar_index: 100 },
          { fx_type: 'ding', date: fdate(150), val: 14.0, bar_index: 150 },
        ],
        zss: [],
        mmds: [],
        frequency: 'daily',
        compact: true,
      },
      attachTo: document.body,
    })

    expect(findSeries('底分型')?.data).toHaveLength(1)
    expect(findSeries('顶分型')?.data).toHaveLength(1)
  })

  test('showMmds=false 时不渲染买卖点', () => {
    mount(ChanlunChart, {
      props: {
        bars,
        bis: [],
        xds: [],
        mmds: [
          { type: '1buy', date: fdate(95), bar_index: 95, anchor_val: 8.0, msg: 'm' },
          { type: '1sell', date: fdate(150), bar_index: 150, anchor_val: 14.0, msg: 'm' },
        ],
        showMmds: false,
        zss: [],
        frequency: 'daily',
        compact: true,
      },
      attachTo: document.body,
    })

    expect(findSeries('买点')?.data).toHaveLength(0)
    expect(findSeries('卖点')?.data).toHaveLength(0)
    expect(lastOption.legend.data).not.toContain('买点')
    expect(lastOption.legend.data).not.toContain('卖点')
  })

  test('showBcs=false 时不渲染背驰', () => {
    mount(ChanlunChart, {
      props: {
        bars,
        bis: [],
        xds: [],
        bcs: [
          {
            type: 'bi',
            bc: true,
            date: fdate(148),
            bar_index: 148,
            anchor_val: 12.6,
            anchor_bar_index: 148,
            msg: 'm',
          },
        ],
        showBcs: false,
        zss: [],
        mmds: [],
        frequency: 'daily',
        compact: true,
      },
      attachTo: document.body,
    })

    expect(findSeries('背驰')?.data).toHaveLength(0)
    expect(findSeries('背驰(主图)')?.data).toHaveLength(0)
    expect(lastOption.legend.data).not.toContain('背驰')
  })

  test('showZss=false 时不渲染中枢区域', () => {
    mount(ChanlunChart, {
      props: {
        bars,
        bis: [],
        xds: [],
        zss: [
          {
            index: 0,
            zg: 11.8,
            zd: 10.8,
            gg: 12.5,
            dd: 10.4,
            line_count: 3,
            start_date: fdate(100),
            end_date: fdate(126),
            start_index: 100,
            end_index: 126,
            done: true,
          },
        ],
        showZss: false,
        mmds: [],
        frequency: 'daily',
        compact: true,
      },
      attachTo: document.body,
    })

    expect(findSeries('中枢')?.markArea?.data).toHaveLength(0)
    expect(lastOption.legend.data).not.toContain('中枢')
  })

  test('showMmdLabels=true 时买卖点 label 开启', () => {
    mount(ChanlunChart, {
      props: {
        bars,
        bis: [],
        xds: [],
        mmds: [
          { type: '1buy', date: fdate(95), bar_index: 95, anchor_val: 8.0, msg: 'm' },
          { type: '1sell', date: fdate(150), bar_index: 150, anchor_val: 14.0, msg: 'm' },
        ],
        showMmdLabels: true,
        zss: [],
        frequency: 'daily',
      },
      attachTo: document.body,
    })

    const buy = findSeries('买点')
    expect(buy?.label?.show).toBe(true)
    expect(buy?.data).toHaveLength(1)
    const sell = findSeries('卖点')
    expect(sell?.label?.show).toBe(true)
    expect(sell?.data).toHaveLength(1)
  })

  test('bar_index 与 date 不一致（帧漂移）时回退日期匹配，不画错位', () => {
    // 复现用户反馈「2023-06-13~16 日线全部标记底分型」根因：count>800 时
    // 后端 fetch_paged_bars 多返 bar 使分析帧 > 前端 bars 帧，bar_index 指向
    // 另一根 K 线。findAnchorIndex 必须校验 bar_index 对应 bar 的日期与端点
    // 自带 date 是否一致，不一致则回退日期匹配，否则所有索引锚定的标记错位。
    mount(ChanlunChart, {
      props: {
        bars,
        bis: [],
        xds: [],
        // bar_index=150 但 date=fdate(140)：模拟帧漂移（150 号位是另一根 K 线）
        fxs: [{ fx_type: 'ding', date: fdate(140), val: 14.0, bar_index: 150 }],
        zss: [],
        mmds: [],
        frequency: 'daily',
        compact: true,
      },
      attachTo: document.body,
    })

    const fx = findSeries('顶分型')
    expect(fx?.data).toHaveLength(1)
    // data[0] = {value:[idx,price],...}，取 value[0] 为锚定索引
    expect(fx?.data[0].value[0]).toBe(140)
  })

  test('bar_index 与 date 一致时仍用 bar_index（不误触发回退）', () => {
    mount(ChanlunChart, {
      props: {
        bars,
        bis: [],
        xds: [],
        fxs: [{ fx_type: 'di', date: fdate(88), val: 8.6, bar_index: 88 }],
        zss: [],
        mmds: [],
        frequency: 'daily',
        compact: true,
      },
      attachTo: document.body,
    })

    const fx = findSeries('底分型')
    expect(fx?.data[0].value[0]).toBe(88)
  })

  test('顶/底分型拆成两序列、series 级固定 symbol（均为小圆点，靠上下偏移区分顶/底）', () => {
    // 顶=向下三角▼(symbolRotate:180)，底=向上三角▲(不旋转)
    // 两个独立 scatter 序列、series 级 symbol 固定，100% 可靠。
    mount(ChanlunChart, {
      props: {
        bars,
        bis: [],
        xds: [],
        fxs: [
          { fx_type: 'di', date: fdate(88), val: 8.6, bar_index: 88 },
          { fx_type: 'ding', date: fdate(140), val: 14.0, bar_index: 140 },
          { fx_type: 'di', date: fdate(150), val: 9.5, bar_index: 150 },
        ],
        zss: [],
        mmds: [],
        frequency: 'daily',
        compact: true,
      },
      attachTo: document.body,
    })

    const fxTop = findSeries('顶分型')
    const fxBot = findSeries('底分型')
    // 顶分型序列：1 个点（ding@140）。
    // 用户要求（2026-10-10）：笔端点（分型）用小圆点，不用三角形。
    // 圆点旋转对称 → rotate 失效，顶/底改由 symbolOffset 的 y 符号区分
    // （顶在最高价上方=负 y，底在最低价下方=正 y）。
    expect(fxTop?.data).toHaveLength(1)
    expect(fxTop?.symbol).toBe(FX_SYMBOL)
    expect(fxTop?.symbol).toBe('circle')
    expect(fxTop?.symbolRotate).toBeUndefined() // 圆点不再需要旋转
    // 顶在极值上方（负 y）；且不能退化成 0（那样顶底会重合在同一个点上）
    expect((fxTop?.symbolOffset as number[])?.[1]).toBeLessThan(0)
    // 顶/底统一白色，不跟随涨跌配色（红/绿只给买卖点用）
    expect(fxTop?.itemStyle.color).toBe(FX_COLOR)
    expect(fxTop?.data[0].value[0]).toBe(140)
    // 底分型序列：2 个点（di@88, di@150）
    expect(fxBot?.data).toHaveLength(2)
    expect(fxBot?.symbol).toBe(FX_SYMBOL)
    expect(fxBot?.symbol).toBe('circle')
    expect(fxBot?.symbolRotate).toBeUndefined()
    expect((fxBot?.symbolOffset as number[])?.[1]).toBeGreaterThan(0)
    // 顶底 offset 必须反向，否则画在同一个位置无法区分
    expect((fxBot?.symbolOffset as number[])?.[1]).toBe(
      -((fxTop?.symbolOffset as number[])?.[1] as number),
    )
    expect(fxBot?.itemStyle.color).toBe(FX_COLOR)
    // 顶底同色，靠 offset（上/下）区分，不靠颜色
    expect(fxBot?.itemStyle.color).toBe(fxTop?.itemStyle.color)
    expect(fxBot?.data[0].value[0]).toBe(88)
    expect(fxBot?.data[1].value[0]).toBe(150)
  })

  test('顶/底分型为白色且不随配色方案变化（红涨绿跌 ↔ 绿涨红跌）', () => {
    // 分型是结构端点而非多空信号：两种配色下都必须是白色，
    // 否则会与买卖点（买=上涨色、卖=下跌色）撞色而被误读成信号。
    for (const scheme of ['red-up', 'green-up'] as const) {
      setColorScheme(scheme)
      mount(ChanlunChart, {
        props: {
          bars,
          bis: [],
          xds: [],
          fxs: [
            { fx_type: 'ding', date: fdate(140), val: 14.0, bar_index: 140 },
            { fx_type: 'di', date: fdate(88), val: 8.6, bar_index: 88 },
          ],
          zss: [],
          mmds: [],
          frequency: 'daily',
          compact: true,
        },
        attachTo: document.body,
      })
      const fxTop = findSeries('顶分型')
      const fxBot = findSeries('底分型')
      expect(fxTop?.itemStyle.color).toBe(FX_COLOR)
      expect(fxBot?.itemStyle.color).toBe(FX_COLOR)
      // 明确排除涨跌色，防止有人改回 upColor/downColor
      expect(fxTop?.itemStyle.color).not.toBe(UP_COLOR)
      expect(fxTop?.itemStyle.color).not.toBe(DOWN_COLOR)
      expect(fxBot?.itemStyle.color).not.toBe(UP_COLOR)
      expect(fxBot?.itemStyle.color).not.toBe(DOWN_COLOR)
    }
    setColorScheme('red-up')
  })

  test('分型「顶/底」文字标签也是白色（与符号同色）', () => {
    mount(ChanlunChart, {
      props: {
        bars,
        bis: [],
        xds: [],
        fxs: [{ fx_type: 'ding', date: fdate(140), val: 14.0, bar_index: 140 }],
        zss: [],
        mmds: [],
        frequency: 'daily',
        showFractalLabels: true,
      },
      attachTo: document.body,
    })
    const fxTop = findSeries('顶分型')
    expect(fxTop?.data[0].label.show).toBe(true)
    expect(fxTop?.data[0].label.color).toBe(FX_COLOR)
    expect(fxTop?.data[0].label.formatter).toBe('顶')
  })
})

describe('V723: 加载更早视口保持（chart-history-navigation spec）', () => {
  test('prepend 后 dataZoom 窗口平移 delta，不跳到默认 50-100', async () => {
    const doMount = (bs: any[]) =>
      mount(ChanlunChart, { props: { bars: bs, bis: [], xds: [], zss: [], mmds: [], fxs: [] } })
    const w1 = doMount(bars)
    await flushPromises()
    // 用户已把视口缩放到绝对 [128,160)（后 20%）
    mockedZoom = { dataZoom: [{ start: 80, end: 100 }] }
    // 前置 40 根更早历史：绝对窗口应平移到 [168,200)，即新长度 200 的 [84%,100%]
    const earlier = Array.from({ length: 40 }, (_, i) => bar(i - 40))
    await w1.setProps({ bars: [...earlier, ...bars] })
    await flushPromises()
    const dz = lastOption.dataZoom[0]
    expect(dz.start).toBe(84)
    expect(dz.end).toBeCloseTo(100, 5)
    // 后续普通重渲染不再篡改 zoom（zoomKeep 已消费）
    mockedZoom = undefined
    await w1.setProps({ revealIndex: 100 })
    await flushPromises()
    // revealIndex 触发的 revealActive 会截断渲染长度（100 根），notMerge 重置 zoom
    // 为默认 50 —— 这是 ECharts setOption(option, true) 的固有行为，与 prepend
    // 无关。viewport 保持语义只覆盖「加载更早」这一交互路径。
    expect(lastOption.dataZoom[0].start).toBe(50)
    w1.unmount()
  })

  test('长度不变的数据更新不触发视口平移', async () => {
    const doMount = (bs: any[]) =>
      mount(ChanlunChart, { props: { bars: bs, bis: [], xds: [], zss: [], mmds: [], fxs: [] } })
    const w2 = doMount(bars)
    await flushPromises()
    mockedZoom = { dataZoom: [{ start: 10, end: 30 }] }
    // 同长度替换（如训练揭示推进），非 prepend
    await w2.setProps({ bars: [...bars] })
    await flushPromises()
    expect(lastOption.dataZoom[0].start).toBe(50) // 默认值，未被平移逻辑改写
    w2.unmount()
  })
})

describe('滚轮缩放（inside dataZoom）与全局配色', () => {
  test('含 inside dataZoom 支持滚轮以鼠标为中心缩放', async () => {
    const w = mount(ChanlunChart, {
      props: { bars, bis: [], xds: [], zss: [], mmds: [], fxs: [] },
    })
    await flushPromises()
    const types = lastOption.dataZoom.map((d: any) => d.type)
    expect(types).toContain('inside')
    expect(types).toContain('slider')
    const inside = lastOption.dataZoom.find((d: any) => d.type === 'inside')
    expect(inside.zoomOnMouseWheel).toBe(true)
    w.unmount()
  })

  test('默认红涨绿跌：K 线 color=红 color0=绿', async () => {
    setColorScheme('red-up')
    const w = mount(ChanlunChart, {
      props: { bars, bis: [], xds: [], zss: [], mmds: [], fxs: [] },
    })
    await flushPromises()
    const kl = lastOption.series.find((s: any) => s.name === 'K线')
    expect(kl.itemStyle.color).toBe('#ef4146')
    expect(kl.itemStyle.color0).toBe('#18a058')
    w.unmount()
  })

  // 买卖点配色必须跟随全局涨跌配色（用户反馈：写死绿买红卖与红涨绿跌的K线相反，会误读）
  const mmdProps = () => ({
    bars,
    bis: [],
    xds: [],
    zss: [],
    fxs: [],
    mmds: [
      { type: '1buy', date: fdate(88), bar_index: 88, anchor_val: 8.6 },
      { type: '3buy', date: fdate(100), bar_index: 100, anchor_val: 9.0 },
      { type: '1sell', date: fdate(150), bar_index: 150, anchor_val: 14.0 },
      { type: '3sell', date: fdate(155), bar_index: 155, anchor_val: 13.5 },
    ],
  })

  test('红涨绿跌：买点=红(上涨色)、卖点=绿(下跌色)', async () => {
    setColorScheme('red-up')
    const w = mount(ChanlunChart, { props: mmdProps() })
    await flushPromises()
    const buy = lastOption.series.find((s: any) => s.name === '买点')
    const sell = lastOption.series.find((s: any) => s.name === '卖点')
    // 买点全部取上涨色
    for (const d of buy.data) expect(d.itemStyle.color).toBe('#ef4146')
    // 卖点全部取下跌色
    for (const d of sell.data) expect(d.itemStyle.color).toBe('#18a058')
    w.unmount()
  })

  test('绿涨红跌：买点=绿(上涨色)、卖点=红(下跌色)', async () => {
    setColorScheme('green-up')
    const w = mount(ChanlunChart, { props: mmdProps() })
    await flushPromises()
    const buy = lastOption.series.find((s: any) => s.name === '买点')
    const sell = lastOption.series.find((s: any) => s.name === '卖点')
    for (const d of buy.data) expect(d.itemStyle.color).toBe('#18a058')
    for (const d of sell.data) expect(d.itemStyle.color).toBe('#ef4146')
    w.unmount()
    setColorScheme('red-up') // 还原，避免污染后续用例
  })

  test('1/2/3 类用大小 + 不透明度区分：1类最大最实、3类最小最淡', async () => {
    setColorScheme('red-up')
    const w = mount(ChanlunChart, {
      props: {
        bars,
        bis: [],
        xds: [],
        zss: [],
        fxs: [],
        mmds: [
          { type: '1buy', date: fdate(88), bar_index: 88, anchor_val: 8.6 },
          { type: '2buy', date: fdate(94), bar_index: 94, anchor_val: 8.8 },
          { type: '3buy', date: fdate(100), bar_index: 100, anchor_val: 9.0 },
          { type: '1sell', date: fdate(150), bar_index: 150, anchor_val: 14.0 },
          { type: '2sell', date: fdate(152), bar_index: 152, anchor_val: 13.8 },
          { type: '3sell', date: fdate(155), bar_index: 155, anchor_val: 13.5 },
        ],
      },
      attachTo: document.body,
    })
    await flushPromises()
    const buy = lastOption.series.find((s: any) => s.name === '买点')
    const sell = lastOption.series.find((s: any) => s.name === '卖点')
    const byType = (arr: any[]) =>
      Object.fromEntries(arr.map((d: any) => [d.name, d])) as Record<string, any>

    const b = byType(buy.data)
    const s = byType(sell.data)
    // 大小递减：1类 > 2类 > 3类
    expect(b['1buy'].symbolSize).toBeGreaterThan(b['2buy'].symbolSize)
    expect(b['2buy'].symbolSize).toBeGreaterThan(b['3buy'].symbolSize)
    expect(s['1sell'].symbolSize).toBeGreaterThan(s['2sell'].symbolSize)
    expect(s['2sell'].symbolSize).toBeGreaterThan(s['3sell'].symbolSize)
    // 不透明度递减：1类最实 → 3类最淡
    expect(b['1buy'].itemStyle.opacity).toBeGreaterThan(b['2buy'].itemStyle.opacity)
    expect(b['2buy'].itemStyle.opacity).toBeGreaterThan(b['3buy'].itemStyle.opacity)
    expect(s['1sell'].itemStyle.opacity).toBeGreaterThan(s['2sell'].itemStyle.opacity)
    expect(s['2sell'].itemStyle.opacity).toBeGreaterThan(s['3sell'].itemStyle.opacity)
    // 1类完全不透明（最实）
    expect(b['1buy'].itemStyle.opacity).toBe(1)
    expect(s['1sell'].itemStyle.opacity).toBe(1)
    // 所有买卖点形状统一为 triangle（靠 series 级 symbolRotate 决定 ▲/▼）
    for (const d of [...buy.data, ...sell.data]) expect(d.symbol).toBe('triangle')
    w.unmount()
  })
})

// 图例 DOM 必须与图上打点同源：形状 ▲/▼ 一致、颜色跟随配色、大小随类型变化。
// 历史上图例曾用 ●/■/◆ 而图上已是 ▲/▼（两套配置漂移），本组用例即该 bug 的回归网。
describe('买卖点图例与图上标记一致', () => {
  const legendProps = {
    bars,
    bis: [],
    xds: [],
    zss: [],
    fxs: [],
    mmds: [
      { type: '1buy', date: fdate(88), bar_index: 88, anchor_val: 8.6 },
      { type: '2buy', date: fdate(94), bar_index: 94, anchor_val: 8.8 },
      { type: '3buy', date: fdate(100), bar_index: 100, anchor_val: 9.0 },
    ],
  }

  /** 读图例每一行的「字形 / 内联色 / 内联不透明度 / class」。 */
  function readLegend(w: any) {
    const rows = w.findAll('.mmd-legend-item')
    return rows
      .map((r: any) => {
        const ic = r.find('span.ic')
        if (!ic.exists()) return null
        return {
          glyph: ic.text().trim(),
          cls: ic
            .classes()
            .filter((c: string) => c !== 'ic')
            .join(' '),
          color: (ic.element as HTMLElement).style.color,
          opacity: (ic.element as HTMLElement).style.opacity,
          fontSize: (ic.element as HTMLElement).style.fontSize,
          label: r.text().replace(ic.text(), '').trim(),
        }
      })
      .filter(Boolean) as Array<{
      glyph: string
      cls: string
      color: string
      opacity: string
      fontSize: string
      label: string
    }>
  }

  test('图例形状为 ▲/▼，且与图上 symbol 朝向一致（买▲ / 卖▼）', async () => {
    const w = mount(ChanlunChart, { props: legendProps, attachTo: document.body })
    await flushPromises()
    const rows = readLegend(w)
    expect(rows).toHaveLength(8)
    const glyphs = rows.map((r) => r.glyph)
    // 前 4 行买点全 ▲，后 4 行卖点全 ▼；不得再出现 ●/■/◆/▬ 等旧字形
    expect(glyphs.slice(0, 4)).toEqual(['▲', '▲', '▲', '▲'])
    expect(glyphs.slice(4)).toEqual(['▼', '▼', '▼', '▼'])
    for (const g of glyphs) expect(['▲', '▼']).toContain(g)
    // 图上：买点系列不旋转（▲）、卖点系列 symbolRotate:180（▼）
    const buy = lastOption.series.find((s: any) => s.name === '买点')
    const sell = lastOption.series.find((s: any) => s.name === '卖点')
    expect(buy.symbolRotate).toBeUndefined()
    expect(sell.symbolRotate).toBe(180)
    w.unmount()
  })

  test('图例颜色跟随涨跌配色，且与图上打点颜色完全相同', async () => {
    for (const [scheme, up, down] of [
      ['red-up', 'rgb(239, 65, 70)', 'rgb(24, 160, 88)'],
      ['green-up', 'rgb(24, 160, 88)', 'rgb(239, 65, 70)'],
    ] as const) {
      setColorScheme(scheme)
      const w = mount(ChanlunChart, { props: legendProps, attachTo: document.body })
      await flushPromises()
      const rows = readLegend(w)
      // 图例：买点行=上涨色、卖点行=下跌色
      for (const r of rows.slice(0, 4)) expect(r.color).toBe(up)
      for (const r of rows.slice(4)) expect(r.color).toBe(down)
      // 与图上同源：图例色 == 图上 mmd 点色
      const buy = lastOption.series.find((s: any) => s.name === '买点')
      expect(buy.data[0].itemStyle.color).toBe(up === 'rgb(239, 65, 70)' ? '#ef4146' : '#18a058')
      w.unmount()
    }
    setColorScheme('red-up')
  })

  test('图例大小/浓淡随 1/2/3 类变化，与图上档位一致', async () => {
    const w = mount(ChanlunChart, { props: legendProps, attachTo: document.body })
    await flushPromises()
    const rows = readLegend(w)
    const buy1 = rows[0]
    const buy2 = rows[1]
    const buy3 = rows[3]
    const px = (v: string) => parseFloat(v)
    expect(px(buy1.fontSize)).toBeGreaterThan(px(buy2.fontSize))
    expect(px(buy2.fontSize)).toBeGreaterThan(px(buy3.fontSize))
    expect(parseFloat(buy1.opacity)).toBeGreaterThan(parseFloat(buy2.opacity))
    expect(parseFloat(buy2.opacity)).toBeGreaterThan(parseFloat(buy3.opacity))
    // 图例字号与图上尺寸必须**同向且等比**：这里刻意不写死缩放常量——
    // 该系数在组件里调过一次（0.8→1.1，因 0.8 时目视看不出 1/2/3 差异），
    // 写死就会变成「改了实现就误报」的脆断言。改为断言比值一致。
    const buy = lastOption.series.find((s: any) => s.name === '买点')
    const sizeOf = (t: string) => buy.data.find((d: any) => d.name === t)?.symbolSize as number
    // 字号之比 == 图上尺寸之比（等比缩放 ⇒ 两比值相等）
    expect(px(buy1.fontSize) / px(buy3.fontSize)).toBeCloseTo(sizeOf('1buy') / sizeOf('3buy'), 5)
    // 并且缩放是放大或等比而非缩小到看不出：1类字号不得小于 12px
    expect(px(buy1.fontSize)).toBeGreaterThanOrEqual(12)
    // 不透明度与图上完全一致（浓淡不缩放）
    expect(parseFloat(buy1.opacity)).toBe(buy.data[0].itemStyle.opacity)
    w.unmount()
  })

  test('图例保留 buy-*/sell-* class 钩子（端到端脚本按它取色）', async () => {
    const w = mount(ChanlunChart, { props: legendProps, attachTo: document.body })
    await flushPromises()
    const rows = readLegend(w)
    expect(rows.map((r) => r.cls)).toEqual([
      'buy-1',
      'buy-2',
      'buy-2s',
      'buy-3',
      'sell-1',
      'sell-2',
      'sell-2s',
      'sell-3',
    ])
    w.unmount()
  })

  test('图例文案完整（8 类，含类二买/类二卖）', async () => {
    const w = mount(ChanlunChart, { props: legendProps, attachTo: document.body })
    await flushPromises()
    const labels = readLegend(w).map((r) => r.label)
    expect(labels).toEqual([
      '一类买点 (1buy)',
      '二类买点 (2buy)',
      '类二买 (2buy_s)',
      '三类买点 (3buy)',
      '一类卖点 (1sell)',
      '二类卖点 (2sell)',
      '类二卖 (2sell_s)',
      '三类卖点 (3sell)',
    ])
    w.unmount()
  })
})
