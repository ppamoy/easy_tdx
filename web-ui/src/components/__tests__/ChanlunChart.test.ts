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
  return { default: stub, UP_COLOR: '#ef4146', DOWN_COLOR: '#18a058' }
})

import ChanlunChart from '../ChanlunChart.vue'

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
          { type: 'di', date: fdate(88), val: 8.6, bar_index: 88 },
          { type: 'ding', date: fdate(150), val: 14.0, bar_index: 150 },
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
    expect(buyMmd?.symbol[0]).toBe('triangle') // 1buy → ▲
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
          { type: 'di', date: fdate(88), val: 8.6, bar_index: 88 },
          { type: 'ding', date: fdate(150), val: 14.0, bar_index: 150 },
        ],
        showFractals: false,
        zss: [],
        mmds: [],
        frequency: 'daily',
        compact: true,
      },
      attachTo: document.body,
    })

    expect(findSeries('分型')?.data).toHaveLength(0)
    expect(lastOption.legend.data).not.toContain('分型')
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
