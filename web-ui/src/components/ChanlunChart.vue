<script setup lang="ts">
// 缠论分析图表：K 线 + 笔（虚线）+ 线段（实线）+ 中枢 + 买卖点 + 分型 + 背驰。
// 遵循缠论理论：笔用细虚线，线段用细实线。

import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import echarts, { DOWN_COLOR, UP_COLOR } from '../echarts-setup'
import { fmt2 } from '../format'
import type { Bar } from '../types'

const props = defineProps<{
  bars: Bar[]
  bis: ChanlunBi[]
  xds: ChanlunXd[]
  zss: ChanlunZs[]
  mmds: ChanlunMmd[]
  fxs?: ChanlunFx[]
  bcs?: ChanlunBc[]
  frequency: string
}>()

interface ChanlunBi {
  index: number
  direction: 'up' | 'down'
  start_date: string
  end_date: string
  high: number
  low: number
  done: boolean
}

interface ChanlunXd {
  index: number
  direction: 'up' | 'down'
  start_date: string
  end_date: string
  high: number
  low: number
}

interface ChanlunZs {
  index: number
  zg: number
  zd: number
  gg: number
  dd: number
  line_count: number
  start_date: string
  end_date: string
  done: boolean
}

interface ChanlunMmd {
  type: string
  date: string | null
  msg: string
}

interface ChanlunFx {
  type: 'ding' | 'di'
  date: string
  val: number
}

interface ChanlunBc {
  type: 'bi' | 'pz' | 'qs'
  bc: boolean
  date: string | null
  msg: string
}

const container = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

// 将 datetime 对齐到 K 线索引（取前 19 字符，格式 YYYY-MM-DDTHH:MM:SS）
function buildIndexMap(): Map<string, number> {
  const keys = props.bars.map((b) => b.datetime.slice(0, 19).replace(' ', 'T'))
  const keyIndex = new Map<string, number>()
  keys.forEach((k, i) => keyIndex.set(k, i))
  return keyIndex
}

function findBarIndex(keyIndex: Map<string, number>, dateStr: string): number {
  // 精确匹配
  const exact = keyIndex.get(dateStr.slice(0, 19).replace(' ', 'T'))
  if (exact !== undefined) return exact
  // 按日期前缀匹配
  const prefix = dateStr.slice(0, 10)
  for (let i = 0; i < props.bars.length; i++) {
    if (props.bars[i].datetime.slice(0, 10) === prefix) return i
  }
  return -1
}

function render() {
  if (!container.value || props.bars.length === 0) return
  if (!chart) chart = echarts.init(container.value, 'dark')
  chart.setOption(buildOption(), true)
}

function buildOption(): echarts.EChartsCoreOption {
  const keyIndex = buildIndexMap()
  const keys = props.bars.map((b) => b.datetime)

  // x 轴显示格式
  const isIntraday = keys.some((k) => {
    const time = k.slice(11, 19)
    return time && time !== '00:00:00'
  })
  const dates = keys.map((k) =>
    isIntraday ? k.replace('T', ' ').slice(5, 16) : k.slice(0, 10),
  )

  const ohlc = props.bars.map((b) => [b.open, b.close, b.low, b.high])

  // ── 分型的 MarkPoint ──
  const fxPoints = (props.fxs ?? []).map((fx) => {
    const idx = findBarIndex(keyIndex, fx.date)
    if (idx === -1) return null
    const bar = props.bars[idx]
    const price = fx.type === 'ding' ? bar.high * 1.002 : bar.low * 0.998
    return {
      coord: [idx, price],
      itemStyle: { color: fx.type === 'ding' ? DOWN_COLOR : UP_COLOR },
      symbol: fx.type === 'ding' ? 'triangle' : 'diamond',
      symbolSize: 8,
      label: {
        show: true,
        formatter: fx.type === 'ding' ? '顶' : '底',
        color: fx.type === 'ding' ? DOWN_COLOR : UP_COLOR,
        fontSize: 9,
        position: fx.type === 'ding' ? 'top' : 'bottom',
      },
    }
  }).filter(Boolean)

  // ── 笔的 MarkLine（细虚线） ──
  const biMarkLines = props.bis
    .filter((bi) => {
      const si = findBarIndex(keyIndex, bi.start_date)
      const ei = findBarIndex(keyIndex, bi.end_date)
      return si !== -1 && ei !== -1
    })
    .map((bi) => {
      const si = findBarIndex(keyIndex, bi.start_date)
      const ei = findBarIndex(keyIndex, bi.end_date)
      const isUp = bi.direction === 'up'
      return {
        coord: [si, bi.high],
        endCoord: [ei, bi.low],
        lineStyle: {
          color: isUp ? UP_COLOR : DOWN_COLOR,
          width: 1,
          type: 'dashed',
          opacity: 0.7,
        },
        label: { show: false },
        symbol: ['circle', 'circle'],
        symbolSize: 6,
      }
    })

  // ── 线段的 MarkLine（细实线） ──
  const xdMarkLines = props.xds
    .filter((xd) => {
      const si = findBarIndex(keyIndex, xd.start_date)
      const ei = findBarIndex(keyIndex, xd.end_date)
      return si !== -1 && ei !== -1
    })
    .map((xd) => {
      const si = findBarIndex(keyIndex, xd.start_date)
      const ei = findBarIndex(keyIndex, xd.end_date)
      return {
        coord: [si, xd.high],
        endCoord: [ei, xd.low],
        lineStyle: {
          color: 'rgba(200,120,255,0.9)',
          width: 1.5,
          type: 'solid',
        },
        label: { show: false },
        symbol: ['circle', 'circle'],
        symbolSize: 8,
      }
    })

  // ── 中枢的 MarkArea ──
  const zsMarkAreas = props.zss
    .filter((zs) => {
      const si = findBarIndex(keyIndex, zs.start_date)
      const ei = findBarIndex(keyIndex, zs.end_date)
      return si !== -1 && ei !== -1
    })
    .map((zs) => {
      const si = findBarIndex(keyIndex, zs.start_date)
      const ei = findBarIndex(keyIndex, zs.end_date)
      return [
        { coord: [si, zs.zg], itemStyle: { color: 'rgba(255,200,50,0.08)' } },
        { coord: [ei, zs.zd] },
      ]
    })

  // ── 买卖点的 MarkPoint ──
  const mmdMarkPoints = props.mmds
    .filter((m) => m.date !== null)
    .map((m) => {
      const idx = findBarIndex(keyIndex, m.date!)
      if (idx === -1) return null
      const isBuy = m.type.includes('buy')
      const priceOffset = isBuy ? -0.005 : 0.005
      const price = isBuy
        ? props.bars[idx].low * (1 + priceOffset)
        : props.bars[idx].high * (1 - priceOffset)
      
      // 根据买卖点类型选择图标和颜色
      const isType1 = m.type.startsWith('1')
      const isType3 = m.type.startsWith('3')
      const symbolSize = isType1 ? 18 : (isType3 ? 14 : 12)
      const color = isBuy ? (isType1 ? '#22c55e' : (isType3 ? '#86efac' : '#4ade80')) : (isType1 ? '#ef4444' : (isType3 ? '#fca5a5' : '#f87171'))
      const symbol = isBuy ? 'triangle' : 'pin'
      
      return {
        name: m.type,
        coord: [idx, price],
        itemStyle: { color },
        symbol,
        symbolSize,
        label: {
          show: true,
          formatter: m.type,
          color,
          fontSize: 10,
          position: isBuy ? 'bottom' : 'top',
        },
      }
    })
    .filter(Boolean)

  // ── 背驰标记 ──
  const bcPoints = (props.bcs ?? [])
    .filter((bc) => bc.bc && bc.date !== null)
    .map((bc) => {
      const idx = findBarIndex(keyIndex, bc.date!)
      if (idx === -1) return null
      const bar = props.bars[idx]
      const isDown = bc.type === 'bi' || bc.type === 'pz'
      return {
        coord: [idx, isDown ? bar.high * 1.01 : bar.low * 0.99],
        itemStyle: { color: '#ff9500' },
        symbol: 'rect',
        symbolSize: [12, 6],
        label: {
          show: true,
          formatter: '背',
          color: '#ff9500',
          fontSize: 9,
          position: 'top',
        },
      }
    })
    .filter(Boolean)

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      valueFormatter: (v: number | string) => fmt2(Number(v)),
      formatter: (params: any) => {
        if (!Array.isArray(params) || params.length === 0) return ''
        const first = params[0]
        let html = `<div style="font-size:12px;color:#ccc;margin-bottom:4px">${first.axisValue}</div>`
        for (const p of params) {
          if (p.seriesType === 'candlestick') {
            const d = p.value
            html += `<div>${p.marker} O:${fmt2(d[1])} C:${fmt2(d[2])} H:${fmt2(d[3])} L:${fmt2(d[4])}</div>`
          } else if (p.seriesName === '笔(虚线)') {
            html += `<div>${p.marker} 笔[${p.seriesIndex ?? ''}]</div>`
          } else if (p.seriesName === '线段(实线)') {
            html += `<div>${p.marker} 线段[${p.seriesIndex ?? ''}]</div>`
          } else if (p.seriesName === '分型') {
            html += `<div>${p.marker} ${p.name === '顶' ? '顶分型' : '底分型'}</div>`
          } else if (p.seriesName === '买卖点') {
            html += `<div>${p.marker} ${p.name}: ${p.data?.label?.formatter ?? ''}</div>`
          } else if (p.seriesName === '背驰') {
            html += `<div>${p.marker} 背驰</div>`
          } else {
            html += `<div>${p.marker} ${p.seriesName}: ${fmt2(p.value?.[1] ?? p.value)}</div>`
          }
        }
        return html
      },
    },
    legend: {
      data: ['K线', '笔(虚线)', '线段(实线)', '中枢', '分型', '买卖点', '背驰'],
      top: 2,
      textStyle: { color: '#999', fontSize: 11 },
      itemWidth: 14,
      itemHeight: 8,
    },
    grid: { left: '8%', right: '3%', top: 32, bottom: 60 },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: true,
      axisLine: { onZero: false, lineStyle: { color: '#2a2e3a' } },
      splitLine: { show: false },
      axisLabel: { formatter: (v: string) => v, color: '#5c6370' },
    },
    yAxis: {
      type: 'value',
      scale: true,
      splitLine: { lineStyle: { color: '#2a2e3a' } },
      axisLabel: { formatter: (v: number) => fmt2(v), color: '#5c6370' },
    },
    dataZoom: [
      { type: 'inside', start: 50, end: 100 },
      { type: 'slider', bottom: 10, start: 50, end: 100, textStyle: { color: '#5c6370' } },
    ],
    series: [
      // K 线
      {
        name: 'K线',
        type: 'candlestick',
        data: ohlc,
        itemStyle: {
          color: UP_COLOR,
          color0: DOWN_COLOR,
          borderColor: UP_COLOR,
          borderColor0: DOWN_COLOR,
        },
      },
      // 笔（虚线）
      {
        name: '笔(虚线)',
        type: 'line',
        data: [],
        symbol: 'none',
        lineStyle: { width: 0 },
        markLine: {
          silent: true,
          symbol: ['circle', 'circle'],
          label: { show: false },
          data: biMarkLines,
        },
      },
      // 线段（实线）
      {
        name: '线段(实线)',
        type: 'line',
        data: [],
        symbol: 'none',
        lineStyle: { width: 0 },
        markLine: {
          silent: true,
          symbol: ['circle', 'circle'],
          label: { show: false },
          data: xdMarkLines,
        },
      },
      // 中枢区域
      {
        name: '中枢',
        type: 'line',
        data: [],
        symbol: 'none',
        lineStyle: { width: 0 },
        markArea: {
          silent: true,
          label: { show: false },
          data: zsMarkAreas,
          itemStyle: { color: 'rgba(255,200,50,0.08)', borderColor: 'rgba(255,200,50,0.3)', borderType: 'dashed' },
        },
      },
      // 分型标记
      {
        name: '分型',
        type: 'scatter',
        data: (fxPoints as any[]).map((p) => [p.coord[0], p.coord[1]]),
        symbol: (fxPoints as any[]).map((p) => p.symbol),
        symbolSize: (fxPoints as any[]).map((p) => p.symbolSize),
        itemStyle: {
          color: (params: any) => (fxPoints as any[])[params.dataIndex]?.itemStyle.color,
        },
        label: {
          show: true,
          formatter: (params: any) => (fxPoints as any[])[params.dataIndex]?.label.formatter,
          color: (params: any) => (fxPoints as any[])[params.dataIndex]?.label.color,
          fontSize: 9,
          position: (params: any) => (fxPoints as any[])[params.dataIndex]?.label.position ?? 'top',
        },
      },
      // 买卖点（根据类型使用不同颜色和大小）
      {
        name: '买卖点',
        type: 'scatter',
        data: (mmdMarkPoints as any[]).map((p) => [p.coord[0], p.coord[1]]),
        symbol: (mmdMarkPoints as any[]).map((p) => p.symbol),
        symbolSize: (mmdMarkPoints as any[]).map((p) => p.symbolSize),
        itemStyle: {
          color: (params: any) => (mmdMarkPoints as any[])[params.dataIndex]?.itemStyle.color,
        },
        label: {
          show: true,
          formatter: (params: any) => (mmdMarkPoints as any[])[params.dataIndex]?.label.formatter,
          color: (params: any) => (mmdMarkPoints as any[])[params.dataIndex]?.label.color,
          fontSize: 10,
          position: (params: any) => (mmdMarkPoints as any[])[params.dataIndex]?.label.position ?? 'top',
        },
      },
      // 背驰标记
      {
        name: '背驰',
        type: 'scatter',
        data: (bcPoints as any[]).map((p) => [p.coord[0], p.coord[1]]),
        symbol: (bcPoints as any[]).map((p) => p.symbol),
        symbolSize: (bcPoints as any[]).map((p) => p.symbolSize),
        itemStyle: {
          color: (params: any) => (bcPoints as any[])[params.dataIndex]?.itemStyle.color,
        },
        label: {
          show: true,
          formatter: (params: any) => (bcPoints as any[])[params.dataIndex]?.label.formatter,
          color: (params: any) => (bcPoints as any[])[params.dataIndex]?.label.color,
          fontSize: 9,
          position: 'top',
        },
      },
    ],
  }
}

function resize() {
  chart?.resize()
}

onMounted(() => {
  render()
  window.addEventListener('resize', resize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
watch(() => [props.bars, props.bis, props.xds, props.zss, props.mmds, props.fxs, props.bcs], render)
</script>

<template>
  <div ref="container" class="chanlun-chart"></div>
</template>

<style scoped>
.chanlun-chart {
  width: 100%;
  height: 560px;
}
</style>
