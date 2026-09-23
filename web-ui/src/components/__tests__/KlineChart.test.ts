// KlineChart 渲染测试（V723）：prepend 视口保持（chart-history-navigation spec）。
import { describe, expect, test, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const setOption = vi.fn()
let lastOption: any = null
let mockedZoom: any = undefined

const instance = {
  setOption: (opt: any) => {
    lastOption = opt
    setOption(opt)
  },
  resize: () => undefined,
  dispose: () => undefined,
  getOption: () => mockedZoom,
}

vi.mock('../../echarts-setup', () => {
  const noop = () => undefined
  const stub = {
    init: () => instance,
    use: noop,
    registerTheme: noop,
  }
  return { default: stub, UP_COLOR: '#ef4146', DOWN_COLOR: '#18a058' }
})

import KlineChart from '../KlineChart.vue'

function bar(i: number) {
  const d = new Date(Date.UTC(2024, 0, 2 + i)).toISOString().slice(0, 10) + 'T00:00:00'
  return {
    datetime: d,
    open: 10,
    close: 10.1,
    high: 10.4,
    low: 9.6,
    vol: 1000 + i,
    amount: 0,
  }
}

const bars = Array.from({ length: 100 }, (_, i) => bar(i))

describe('V723: KlineChart 加载更早视口保持', () => {
  test('prepend 后 dataZoom 窗口平移 delta', async () => {
    const w = mount(KlineChart, { props: { bars, trades: [] } })
    await flushPromises()
    mockedZoom = { dataZoom: [{ start: 70, end: 100 }] }
    const earlier = Array.from({ length: 50 }, (_, i) => bar(i - 50))
    await w.setProps({ bars: [...earlier, ...bars] })
    await flushPromises()
    // 绝对 [70,100) 平移 +50 => [120,150)/150 = [80%,100%]
    expect(lastOption.dataZoom[0].start).toBe(80)
    expect(lastOption.dataZoom[0].end).toBeCloseTo(100, 5)
    w.unmount()
  })

  test('同长度更新不平移（默认 start=60 不变）', async () => {
    const w = mount(KlineChart, { props: { bars, trades: [] } })
    await flushPromises()
    mockedZoom = { dataZoom: [{ start: 10, end: 30 }] }
    await w.setProps({ bars: [...bars] })
    await flushPromises()
    expect(lastOption.dataZoom[0].start).toBe(60)
    w.unmount()
  })
})
