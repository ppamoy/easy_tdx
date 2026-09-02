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
  /** 揭示游标（训练模式）：只显示前 revealIndex+1 根 K 线及其范围内的叠加层 */
  revealIndex?: number
  /**
   * 紧凑模式（回测页）：分型符号更小，减少视觉噪声。
   * 分型「顶/底」文字标签一律默认关闭（268 个分型全标文字是图上最乱的部分）。
   */
  compact?: boolean
  /**
   * MACD 序列（dif/dea/hist，与 bars 一一对应），用于绘制 MACD 副图。
   * 缠论背驰判断基于笔内 MACD 红绿柱面积（calc_macd_force），
   * 显示副图让用户能直观核对背驰依据。
   */
  macd?: {
    dif: number[]
    dea: number[]
    hist: number[]
  }
  /** 是否显示分型「顶/底」文字标签（默认 false）。 */
  showFractalLabels?: boolean
}>()

interface ChanlunBi {
  index: number
  direction: 'up' | 'down'
  start_date: string
  end_date: string
  high: number
  low: number
  /** 端点分型价格（start=起始分型 val，end=结束分型 val），比区间 high/low 更精确 */
  start_val?: number
  end_val?: number
  /** 端点锚定的原始K线索引（后端按极值来源输出），优先于日期匹配 */
  start_index?: number
  end_index?: number
  done: boolean
}

interface ChanlunXd {
  index: number
  direction: 'up' | 'down'
  start_date: string
  end_date: string
  high: number
  low: number
  /** 端点分型价格（start=起始分型 val，end=结束分型 val），比区间 high/low 更精确 */
  start_val?: number
  end_val?: number
  /** 端点锚定的原始K线索引（后端按极值来源输出），优先于日期匹配 */
  start_index?: number
  end_index?: number
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
  start_index?: number
  end_index?: number
  done: boolean
  // v89: 中枢质量评分
  quality_score?: number | null
  grade?: string | null
  width_pct?: number | null
}

interface ChanlunMmd {
  type: string
  date: string | null
  msg: string
  /** 触发笔终点极值锚定的原始K线索引 */
  bar_index?: number
}

interface ChanlunFx {
  type: 'ding' | 'di'
  date: string
  val: number
  /** 分型极值锚定的原始K线索引（后端按极值来源输出），优先于日期匹配 */
  bar_index?: number
}

interface ChanlunBc {
  type: 'bi' | 'pz' | 'qs'
  bc: boolean
  date: string | null
  msg: string
  /** 背驰锚定K线索引 */
  bar_index?: number
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
  // 防御：date 可能缺失（undefined/null/空串），直接返回 -1，由调用方过滤掉
  if (!dateStr) return -1
  const s = dateStr.replace(' ', 'T')
  // 1) 精确匹配（YYYY-MM-DDTHH:MM:SS）
  const exact = keyIndex.get(s.slice(0, 19))
  if (exact !== undefined) return exact
  // 2) 16 位（分钟线后端输出 YYYY-MM-DD HH:MM 无秒）：补 :00 再匹配
  const exactMin = keyIndex.get(s.slice(0, 16) + ':00')
  if (exactMin !== undefined) return exactMin
  // 3) 按日期前缀匹配：日线每周期只有一根，安全；分钟线退避到当天首根会错位，
  //    因此分钟级别必须依赖 start_index/end_index 锚点（后端已输出）。
  const prefix = dateStr.slice(0, 10)
  for (let i = 0; i < props.bars.length; i++) {
    if (props.bars[i].datetime.slice(0, 10) === prefix) return i
  }
  return -1
}

/**
 * 优先使用后端给出的原始K线索引锚点（分钟线日期匹配不可靠），否则回退日期匹配。
 * 与旧 findIdx 一致：超出训练揭示窗口（revealLimit）的端点返回 -1，由各 filter 丢弃。
 */
function findAnchorIndex(
  keyIndex: Map<string, number>,
  barIndex: number | undefined,
  dateStr: string,
  revealLimit: number,
): number {
  let idx = -1
  if (
    barIndex !== undefined &&
    barIndex !== null &&
    Number.isInteger(barIndex) &&
    barIndex >= 0 &&
    barIndex < props.bars.length
  ) {
    idx = barIndex
  } else {
    idx = findBarIndex(keyIndex, dateStr)
  }
  return idx >= revealLimit ? -1 : idx
}

function render() {
  if (!container.value || props.bars.length === 0) return
  if (!chart) chart = echarts.init(container.value, 'dark')
  chart.setOption(buildOption(), true)
  // 开发/调试专用：暴露图表实例供 playwright 等浏览器测试检查内部状态
  if (import.meta.env.DEV) {
    ;(window as unknown as Record<string, unknown>).__CHANLUN_CHART__ = chart
  }
}

function buildOption(): echarts.EChartsCoreOption {
  const keyIndex = buildIndexMap()
  // 训练模式的揭示游标：只渲染前 revealIndex+1 根 K 线，其后的数据不显示
  const revealActive = props.revealIndex !== undefined && props.revealIndex !== null
  const revealLimit = revealActive
    ? Math.min(Math.max(props.revealIndex as number, 0) + 1, props.bars.length)
    : props.bars.length
  const keys = props.bars.slice(0, revealLimit).map((b) => b.datetime)

  // x 轴显示格式
  const isIntraday = keys.some((k) => {
    const time = k.slice(11, 19)
    return time && time !== '00:00:00'
  })
  const dates = keys.map((k) =>
    isIntraday ? k.replace('T', ' ').slice(5, 16) : k.slice(0, 10),
  )

  const ohlc = props.bars.slice(0, revealLimit).map((b) => [b.open, b.close, b.low, b.high])

  // ── MACD 副图数据（dif/dea/hist 与 bars 一一对应，按揭示窗口截断）──
  // 缠论背驰由笔内 MACD 红绿柱面积判断（后端 calc_macd_force），
  // 副图展示 MACD 便于用户核对背驰依据；数据缺失时副图退化为空。
  const macdHist: number[] = (props.macd?.hist ?? []).slice(0, revealLimit)
  const macdDif: number[] = (props.macd?.dif ?? []).slice(0, revealLimit)
  const macdDea: number[] = (props.macd?.dea ?? []).slice(0, revealLimit)

  // 揭示游标竖线（标记训练当前揭示到的位置）
  const cursorMarkLines = revealActive
    ? [{
        xAxis: Math.max(revealLimit - 1, 0),
        lineStyle: { color: '#60a5fa', width: 1, type: 'dashed' as const },
        label: { show: true, formatter: '揭示位', color: '#60a5fa', fontSize: 10, position: 'insideEndTop' as const },
      }]
    : []

  // ── 分型的 MarkPoint ──
  // 紧凑模式下不显示「顶/底」文字标签，只画小圆点（268 个分型每个都带文字会严重遮挡 K 线）。
  const fxPoints = (props.fxs ?? []).map((fx) => {
    const idx = findAnchorIndex(keyIndex, fx.bar_index, fx.date, revealLimit)
    if (idx === -1 || idx >= revealLimit) return null
    // 端点直接锚定在分型极值价上（fx.val），而不是用 K 线高/低偏移：
    // 用户反馈「端点没在K线极值上」——分型标记必须精确落在极值点。
    const price = fx.val
    return {
      coord: [idx, price],
      itemStyle: { color: fx.type === 'ding' ? DOWN_COLOR : UP_COLOR },
      symbol: fx.type === 'ding' ? 'triangle' : 'diamond',
      symbolSize: props.compact ? 5 : 8,
      label: {
        show: props.showFractalLabels === true && !props.compact,
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
      const si = findAnchorIndex(keyIndex, bi.start_index, bi.start_date, revealLimit)
      const ei = findAnchorIndex(keyIndex, bi.end_index, bi.end_date, revealLimit)
      return si !== -1 && ei !== -1
    })
    .map((bi) => {
      const si = findAnchorIndex(keyIndex, bi.start_index, bi.start_date, revealLimit)
      const ei = findAnchorIndex(keyIndex, bi.end_index, bi.end_date, revealLimit)
      const isUp = bi.direction === 'up'
      // ECharts 6 的 markLine 两点标记必须是 [起点, 终点] 二元组数组，
      // 不再支持旧的 {coord, endCoord} 单对象形式（会导致 ECharts 内部崩溃）。
      const lineStyle = {
        color: isUp ? UP_COLOR : DOWN_COLOR,
        width: 1,
        type: 'dashed' as const,
        opacity: 0.7,
      }
      // 精确锚点：优先用端点分型价格（start_val/end_val），与买卖点/分型取同一价位源；
      // 老数据无 start_val 时回退到区间 high/low。
      // start_val 就是起点分型的极值（向上笔=底分型低点，向下笔=顶分型高点），
      // end_val 就是终点分型的极值（向上笔=顶分型高点，向下笔=底分型低点），
      // 因此 startY 恒取 biStartVal、endY 恒取 biEndVal —— 不能按方向交换，
      // 否则向下笔会把起点画在低位、终点画在高位，线方向反转且端点悬空。
      const biStartVal = bi.start_val ?? (isUp ? bi.low : bi.high)
      const biEndVal = bi.end_val ?? (isUp ? bi.high : bi.low)
      const startY = biStartVal
      const endY = biEndVal
      return [
        { coord: [si, startY], lineStyle, label: { show: false }, symbol: 'circle', symbolSize: 6 },
        { coord: [ei, endY], lineStyle, label: { show: false }, symbol: 'circle', symbolSize: 6 },
      ]
    })

  // ── 线段的 MarkLine（细实线） ──
  const xdMarkLines = props.xds
    .filter((xd) => {
      const si = findAnchorIndex(keyIndex, xd.start_index, xd.start_date, revealLimit)
      const ei = findAnchorIndex(keyIndex, xd.end_index, xd.end_date, revealLimit)
      return si !== -1 && ei !== -1
    })
    .map((xd) => {
      const si = findAnchorIndex(keyIndex, xd.start_index, xd.start_date, revealLimit)
      const ei = findAnchorIndex(keyIndex, xd.end_index, xd.end_date, revealLimit)
      const isUp = xd.direction === 'up'
      // ECharts 6 的 markLine 两点标记必须是 [起点, 终点] 二元组数组。
      const lineStyle = {
        color: isUp ? 'rgba(34,197,94,0.85)' : 'rgba(239,68,68,0.85)',
        width: 1.5,
        type: 'solid' as const,
      }
      // 精确锚点：优先用端点分型价格（start_val/end_val）锚定线段两端，
      // 与买卖点/分型价位源一致；老数据无 start_val 时回退到区间 high/low。
      // start_val/end_val 已按线段方向编码（向上线段起点=底分型低点、终点=顶分型高点；
      // 向下线段起点=顶分型高点、终点=底分型低点），故 startY=start_val、endY=end_val，
      // 不能按方向交换，否则向下线段会被画成向上且端点悬空。
      const xdStartVal = xd.start_val ?? (isUp ? xd.low : xd.high)
      const xdEndVal = xd.end_val ?? (isUp ? xd.high : xd.low)
      const startY = xdStartVal
      const endY = xdEndVal
      return [
        { coord: [si, startY], lineStyle, label: { show: false }, symbol: 'circle', symbolSize: 8 },
        { coord: [ei, endY], lineStyle, label: { show: false }, symbol: 'circle', symbolSize: 8 },
      ]
    })

  // ── 中枢的 MarkArea ──
  const zsMarkAreas = props.zss
    .filter((zs) => {
      const si = findAnchorIndex(keyIndex, zs.start_index, zs.start_date ?? '', revealLimit)
      const ei = findAnchorIndex(keyIndex, zs.end_index, zs.end_date ?? '', revealLimit)
      return si !== -1 && ei !== -1
    })
    .map((zs) => {
      const si = findAnchorIndex(keyIndex, zs.start_index, zs.start_date ?? '', revealLimit)
      const ei = findAnchorIndex(keyIndex, zs.end_index, zs.end_date ?? '', revealLimit)
      return [
        { coord: [si, zs.zg], itemStyle: { color: 'rgba(255,200,50,0.08)' } },
        { coord: [ei, zs.zd] },
      ]
    })

  // ── 买卖点的 MarkPoint ──
  const mmdMarkPoints = props.mmds
    .filter((m) => m.date != null)
    .map((m) => {
      const idx = findAnchorIndex(keyIndex, m.bar_index, m.date!, revealLimit)
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
  // 背驰画在 MACD 副图上：y 取该位置 MACD 柱值（无柱数据时退化为 0），
  // 使「背」标记直接落在对应柱子上，直观展示背驰的 MACD 面积依据。
  const bcPoints = (props.bcs ?? [])
    .filter((bc) => bc.bc && bc.date != null)
    .map((bc) => {
      const idx = findAnchorIndex(keyIndex, bc.bar_index, bc.date!, revealLimit)
      if (idx === -1) return null
      const histVal = macdHist[idx]
      const y = histVal !== undefined && Number.isFinite(histVal) ? histVal : 0
      return {
        coord: [idx, y],
        itemStyle: { color: '#ff9500' },
        symbol: 'rect',
        symbolSize: [12, 6],
        label: {
          show: true,
          formatter: '背',
          color: '#ff9500',
          fontSize: 9,
          position: y >= 0 ? 'top' : 'bottom',
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
          } else if (p.seriesName === 'MACD') {
            html += `<div>${p.marker} MACD: ${fmt2(p.value ?? 0)}</div>`
          } else if (p.seriesName === 'DIF') {
            html += `<div>${p.marker} DIF: ${fmt2(p.value ?? 0)}</div>`
          } else if (p.seriesName === 'DEA') {
            html += `<div>${p.marker} DEA: ${fmt2(p.value ?? 0)}</div>`
          } else {
            html += `<div>${p.marker} ${p.seriesName}: ${fmt2(p.value?.[1] ?? p.value)}</div>`
          }
        }
        return html
      },
    },
    legend: {
      data: [
        'K线',
        ...(props.bis.length ? ['笔(虚线)'] : []),
        ...(props.xds.length ? ['线段(实线)'] : []),
        ...(props.zss.length ? ['中枢'] : []),
        ...(props.fxs && props.fxs.length ? ['分型'] : []),
        ...(props.mmds.length ? ['买卖点'] : []),
        ...(props.bcs && props.bcs.some(bc => bc.bc) ? ['背驰'] : []),
        ...(macdHist.length ? ['MACD', 'DIF', 'DEA'] : []),
      ],
      top: 2,
      textStyle: { color: '#999', fontSize: 11 },
      itemWidth: 14,
      itemHeight: 8,
    },
    // 双面板布局：主图（K线 + 缠论结构）+ MACD 副图。
    // grid/xAxis/yAxis 均为数组，各 series 通过 gridIndex/xAxisIndex/yAxisIndex 归属面板。
    grid: [
      { left: '8%', right: '3%', top: 34, height: '52%' },
      { left: '8%', right: '3%', top: '62%', height: '22%' },
    ],
    xAxis: [
      {
        type: 'category',
        data: dates,
        boundaryGap: true,
        axisLine: { onZero: false, lineStyle: { color: '#2a2e3a' } },
        splitLine: { show: false },
        axisLabel: { show: false }, // 主图不显示日期，避免与副图重复
      },
      {
        type: 'category',
        data: dates,
        boundaryGap: true,
        gridIndex: 1,
        axisLine: { onZero: false, lineStyle: { color: '#2a2e3a' } },
        axisLabel: { formatter: (v: string) => v, color: '#5c6370' },
      },
    ],
    yAxis: [
      {
        type: 'value',
        scale: true,
        splitLine: { lineStyle: { color: '#2a2e3a' } },
        axisLabel: { formatter: (v: number) => fmt2(v), color: '#5c6370' },
      },
      {
        type: 'value',
        scale: true,
        gridIndex: 1,
        splitLine: { lineStyle: { color: '#2a2e3a' } },
        axisLabel: { formatter: (v: number) => fmt2(v), color: '#5c6370' },
      },
    ],
    dataZoom: [
      { type: 'slider', bottom: 8, start: 50, end: 100, textStyle: { color: '#5c6370' }, xAxisIndex: [0, 1] },
    ],
    series: [
      // K 线
      {
        name: 'K线',
        type: 'candlestick',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: ohlc,
        itemStyle: {
          color: UP_COLOR,
          color0: DOWN_COLOR,
          borderColor: UP_COLOR,
          borderColor0: DOWN_COLOR,
        },
        markLine: cursorMarkLines.length ? {
          silent: true,
          symbol: 'none',
          label: { show: false },
          data: cursorMarkLines,
        } : undefined,
      },
      // 笔（虚线）
      {
        name: '笔(虚线)',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
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
        xAxisIndex: 0,
        yAxisIndex: 0,
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
        xAxisIndex: 0,
        yAxisIndex: 0,
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
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: (fxPoints as any[]).map((p) => [p.coord[0], p.coord[1]]),
        symbol: (fxPoints as any[]).map((p) => p.symbol),
        symbolSize: (fxPoints as any[]).map((p) => p.symbolSize),
        itemStyle: {
          color: (params: any) => (fxPoints as any[])[params.dataIndex]?.itemStyle.color,
        },
        label: {
          show: props.showFractalLabels === true && !props.compact,
          formatter: (params: any) => (fxPoints as any[])[params.dataIndex]?.label.formatter,
          color: (params: any) => (fxPoints as any[])[params.dataIndex]?.label.color,
          fontSize: 9,
          position: (params: any) => (fxPoints as any[])[params.dataIndex]?.label.position ?? 'top',
        },
        labelLayout: { hideOverlap: true },
      },
      // 买卖点（根据类型使用不同颜色和大小）
      {
        name: '买卖点',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
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
        labelLayout: { hideOverlap: true },
      },
      // 背驰标记（画在 MACD 副图上：背驰本质是某笔 MACD 面积较前笔缩小，
      // 在副图对应位置标「背」便于与柱子直观对照）
      {
        name: '背驰',
        type: 'scatter',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: (bcPoints as any[]).map((p) => [
          p.coord[0],
          macdHist[p.coord[0]] ?? 0,
        ]),
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
        labelLayout: { hideOverlap: true },
      },
      // ── MACD 副图：红绿柱 + DIF/DEA 线 ──
      {
        name: 'MACD',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: macdHist,
        barWidth: '60%',
        itemStyle: {
          color: (params: any) => ((params.value ?? 0) >= 0 ? 'rgba(239,65,70,0.85)' : 'rgba(24,160,88,0.85)'),
        },
      },
      {
        name: 'DIF',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: macdDif,
        showSymbol: false,
        lineStyle: { color: '#fbbf24', width: 1 },
      },
      {
        name: 'DEA',
        type: 'line',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: macdDea,
        showSymbol: false,
        lineStyle: { color: '#60a5fa', width: 1 },
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
  // 在捕获阶段阻止图表容器吞没滚轮事件，确保页面可以滚动
  const el = container.value
  if (el) {
    el.addEventListener('wheel', (e: WheelEvent) => e.stopPropagation(), { passive: false, capture: true })
  }
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
watch(() => [props.bars, props.bis, props.xds, props.zss, props.mmds, props.fxs, props.bcs, props.macd, props.revealIndex], render)
</script>

<template>
  <div ref="container" class="chanlun-chart"></div>
</template>

<style scoped>
.chanlun-chart {
  width: 100%;
  /* 双面板：主图（K线+缠论结构）+ MACD 副图，560 太矮导致所有元素挤在一起 */
  height: 760px;
}

/* 响应式高度：在小屏幕上缩小图表高度 */
@media (max-width: 768px) {
  .chanlun-chart {
    height: 560px;
  }
}
</style>
