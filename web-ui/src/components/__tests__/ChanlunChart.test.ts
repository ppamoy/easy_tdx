// ChanlunChart 渲染结构测试（v590）：验证 MACD 副图、背驰主图/副图、
// 买卖点标注、中枢区域、笔/线段/分型都进入 ECharts option。
import { describe, expect, test, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const setOption = vi.fn()
let lastOption: any = null

vi.mock('../../echarts-setup', () => {
  const noop = () => undefined
  const stub = {
    init: () => ({
      setOption: (opt: any) => {
        lastOption = opt
        setOption(opt)
      },
      resize: noop,
      dispose: noop,
    }),
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
})
