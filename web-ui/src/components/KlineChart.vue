<script setup lang="ts">
// K线主图 + 买卖点标注（ECharts candlestick + markPoint）。
// 核心难点：把 trades 的 datetime 对齐到 K线时间轴——按 datetime 字符串建 index map。

import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import echarts, { DOWN_COLOR, UP_COLOR } from '../echarts-setup'
import { fmt2 } from '../format'
import type { Bar, Trade } from '../types'

const props = defineProps<{
  bars: Bar[]
  trades: Trade[]
}>()

const container = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

// V723: prepend（加载更早）时保持 dataZoom 视口不跳变（spec: chart-history-navigation）。
// 与 ChanlunChart 同一策略：首根变化+长度增加 => 旧绝对窗口平移 delta 根。
let prevBarsLen = 0
let prevFirstKey = ''
let zoomKeep: { start: number; end: number } | null = null

function render() {
  if (!container.value || props.bars.length === 0) return
  chart ??= echarts.init(container.value, 'dark')
  const firstKey = props.bars[0]?.datetime ?? ''
  const len = props.bars.length
  const isPrepend = prevBarsLen > 0 && len > prevBarsLen && firstKey !== prevFirstKey
  if (isPrepend) {
    const opt = chart.getOption() as { dataZoom?: { start?: number; end?: number }[] } | undefined
    const dz = opt?.dataZoom?.[0]
    if (dz && typeof dz.start === 'number' && typeof dz.end === 'number') {
      const delta = len - prevBarsLen
      const a = (dz.start / 100) * prevBarsLen
      const b = (dz.end / 100) * prevBarsLen
      zoomKeep = {
        start: Math.max(0, Math.min(100, ((a + delta) / len) * 100)),
        end: Math.max(0, Math.min(100, ((b + delta) / len) * 100)),
      }
    }
  }
  prevBarsLen = len
  prevFirstKey = firstKey
  const option = buildOption()
  if (zoomKeep) {
    const dzArr = option.dataZoom as { start: number; end: number }[]
    if (dzArr?.[0]) {
      dzArr[0].start = zoomKeep.start
      dzArr[0].end = zoomKeep.end
    }
    zoomKeep = null
  }
  chart.setOption(option, true)
}

/** 构建 ECharts 配置。trades 的 datetime 对齐到 K线 index。 */
function buildOption(): echarts.EChartsCoreOption {
  // 用完整 datetime 做 index key（避免分钟线 slice(0,10) 把同日 bar 折叠）。
  // datetime 已由 api.ts 归一化为 "YYYY-MM-DDTHH:MM:SS" 格式。
  const keys = props.bars.map((b) => b.datetime)
  const keyIndex = new Map<string, number>()
  keys.forEach((k, i) => keyIndex.set(k, i))

  // x 轴显示：日线只显示日期 YYYY-MM-DD，分钟线显示 MM-DD HH:mm。
  // 判断分钟线：datetime 有非零时分秒（日线归一化后是 T00:00:00）。
  // 不能用 length > 10 判断——日线带 T00:00:00 后缀长度也是 19。
  const isIntraday = keys.some((k) => {
    const time = k.slice(11, 19) // HH:MM:SS 部分
    return time && time !== '00:00:00'
  })
  const dates = keys.map((k) => (isIntraday ? k.replace('T', ' ').slice(5, 16) : k.slice(0, 10)))

  const ohlc = props.bars.map((b) => [b.open, b.close, b.low, b.high])

  // 买卖点 markPoint：按 trade.datetime 查 K线 index，price 定位 y 轴。
  // 注意：回测引擎的 trades datetime 目前是日线精度（YYYY-MM-DDT00:00:00），
  // 分钟线回测时可能无法精确对齐到具体分钟 bar——这是引擎层限制，前端做容错。
  const markPoints: Array<{
    name: string
    coord: [number, number]
    itemStyle: { color: string }
    symbol: string
    symbolSize: number
  }> = []
  for (const t of props.trades) {
    if (t.rejected) continue
    // 归一化 trade datetime 与 bar key 同格式
    const tKey = t.datetime.slice(0, 19).replace(' ', 'T')
    let idx = keyIndex.get(tKey)
    if (idx === undefined) {
      // 引擎 trade 精度不足（日线回测分钟线场景）：退回按日期首根 bar 匹配
      const dayPrefix = tKey.slice(0, 10)
      idx = keys.findIndex((k) => k.startsWith(dayPrefix))
      if (idx === -1) continue
    }
    const isBuy = t.direction === 'BUY'
    markPoints.push({
      name: t.direction,
      coord: [idx, t.price],
      itemStyle: { color: isBuy ? UP_COLOR : DOWN_COLOR },
      symbol: isBuy ? 'triangle' : 'pin',
      symbolSize: 14,
    })
  }

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      valueFormatter: (v: number | string) => fmt2(Number(v)),
    },
    legend: { data: ['K线'], top: 0 },
    grid: { left: '8%', right: '3%', top: 30, bottom: 60 },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: true,
      axisLine: { onZero: false },
      splitLine: { show: false },
      // 强制显示原始日期字符串，避免 ECharts 把 "2024-01-15" 当时间对象
      // 解析后默认按 {MM}-{dd} {HH}:{mm} 显示（丢年份）
      axisLabel: {
        formatter: (v: string) => v,
      },
    },
    yAxis: {
      scale: true,
      splitLine: { lineStyle: { color: '#2a2e3a' } },
      axisLabel: { formatter: (v: number) => fmt2(v) },
    },
    dataZoom: [{ type: 'slider', bottom: 10, start: 60, end: 100 }],
    series: [
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
        markPoint: {
          data: markPoints,
          label: { show: false },
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
  const el = container.value
  if (el) {
    el.addEventListener('wheel', (e: WheelEvent) => e.stopPropagation(), {
      passive: false,
      capture: true,
    })
  }
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
watch(() => [props.bars, props.trades], render)
</script>

<template>
  <div ref="container" class="kline-chart"></div>
</template>

<style scoped>
.kline-chart {
  width: 100%;
  height: 420px;
}
</style>
