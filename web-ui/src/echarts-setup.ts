// ECharts 按需引入。只注册用到的图表类型，避免全量引入（~1MB → ~400KB）。
// 用到的：candlestick（K线）、line（净值/回撤曲线）、scatter（分型/买卖点/背驰标注）、
// heatmap（寻优热力图）+ markLine（笔/线段）、markArea（中枢）、markPoint。

import * as echarts from 'echarts/core'
import { BarChart, CandlestickChart, HeatmapChart, LineChart, ScatterChart } from 'echarts/charts'
import {
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

echarts.use([
  CanvasRenderer,
  CandlestickChart,
  LineChart,
  BarChart,
  HeatmapChart,
  ScatterChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  DataZoomComponent,
  MarkPointComponent,
  MarkLineComponent,
  MarkAreaComponent,
  VisualMapComponent,
])

// 默认涨跌色常量（红涨绿跌）。运行时响应式配色见 colors.ts，组件请用 upColor/downColor。
export const UP_COLOR = '#ef4146'
export const DOWN_COLOR = '#18a058'

/**
 * 分型（顶/底）统一色：白色。
 * 分型只是结构端点（顶=三K高点、底=三K低点），不表达多空方向；红/绿留给买卖点
 * 专用，否则「绿色顶分型」会与卖点撞色、被误读成信号。顶/底之间靠三角朝向
 * （顶▼/底▲）区分，不靠颜色。
 */
export const FX_COLOR = '#ffffff'
/** 分型描边色：白三角压在浅色高亮/K线上影上会糊，深色描边保证可分离。 */
export const FX_BORDER_COLOR = '#1f2430'

// 注册内联 dark 主题（echarts/core 不预置 'dark' 主题数据）。
// 覆盖坐标轴文字、分割线等默认浅色样式，适配深色背景。
echarts.registerTheme('dark', {
  backgroundColor: 'transparent',
  textStyle: { color: '#8b919e' },
  title: { textStyle: { color: '#e6e8eb' }, subtextStyle: { color: '#8b919e' } },
  legend: { textStyle: { color: '#8b919e' } },
  tooltip: {
    backgroundColor: 'rgba(26,29,38,0.95)',
    borderColor: '#2a2e3a',
    textStyle: { color: '#e6e8eb' },
  },
  categoryAxis: {
    axisLine: { lineStyle: { color: '#2a2e3a' } },
    axisLabel: { color: '#5c6370' },
    splitLine: { show: false },
  },
  valueAxis: {
    axisLine: { lineStyle: { color: '#2a2e3a' } },
    axisLabel: { color: '#5c6370' },
    splitLine: { lineStyle: { color: '#2a2e3a' } },
  },
})

export default echarts
