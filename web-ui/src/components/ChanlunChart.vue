<script setup lang="ts">
// 缠论分析图表：K 线 + 笔（虚线）+ 线段（实线）+ 中枢 + 买卖点 + 分型 + 背驰。
// 遵循缠论理论：笔用细虚线，线段用细实线。

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import echarts, { FX_BORDER_COLOR, FX_COLOR, FX_SYMBOL } from '../echarts-setup'
import { colorScheme, downColor, upColor } from '../colors'
import { fmt2 } from '../format'
import type { Bar } from '../types'

const props = withDefaults(
  defineProps<{
    bars: Bar[]
    bis: ChanlunBi[]
    xds: ChanlunXd[]
    /** 走势段（ZSD）：由同向线段合并，粗实线显示。 */
    zsds?: ChanlunXd[]
    /** 趋势段（QSD）：具备明确方向的走势段，粗虚线显示。 */
    qsds?: ChanlunXd[]
    /** 是否显示走势段/趋势段（默认 true）。 */
    showZsds?: boolean
    zss: ChanlunZs[]
    mmds: ChanlunMmd[]
    fxs?: ChanlunFx[]
    /** 缠论有效分型（笔端点分型，顶底交替且不共用K线）。提供时优先用于展示，
     *  消除原始 fractals 中重叠的「底-顶-底」噪声。
     *  注意：仅在该 prop「完全未传」（undefined）时才回退 fxs；若调用方传了
     *  空数组，表示本窗口确实没有合规分型，绝不能再退回含违规对的原始列表。 */
    validFxs?: ChanlunFx[]
    bcs?: ChanlunBc[]
    frequency?: string
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
    /** 是否显示分型符号（默认 true）。 */
    showFractals?: boolean
    /** 是否显示买卖点标注（默认 true）。 */
    showMmds?: boolean
    /** 是否显示背驰标注（默认 true）。 */
    showBcs?: boolean
    /** 是否显示中枢区域（默认 true）。 */
    showZss?: boolean
    /** 是否显示买卖点类型文字标注（默认 false）。 */
    showMmdLabels?: boolean
    /**
     * 同级别中枢：只渲染该 index 的中枢（买卖点所属中枢，MMD.zs 引用）。
     * 未传（undefined）时渲染全部中枢。
     */
    singleZsIndex?: number
  }>(),
  {
    frequency: 'daily',
    showZsds: true,
    showFractals: true,
    showMmds: true,
    showBcs: true,
    showZss: true,
    showMmdLabels: false,
  },
)

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
  // V853 原文第20课定理二 / 第33课：中枢升级标记
  level?: number
  upgraded?: boolean
  upgrade_from?: number[]
}

interface ChanlunMmd {
  type: string
  date: string | null
  msg: string
  /** 触发笔终点极值锚定的原始K线索引 */
  bar_index?: number
  /** 触发笔终点分型极值价（买点=底分型低点，卖点=顶分型高点），标注必须用该值 */
  anchor_val?: number | null
  /** V735 第29课背驰-转折定理后置验证：
   *  true=反弹触及中枢DD/GG（符合定理）
   *  false=未触及（该点可能不是真背驰，⚠️标注）
   *  null/undefined=数据不足（最新信号，未知） */
  rebound_verified?: boolean | null
}

interface ChanlunFx {
  fx_type: 'ding' | 'di'
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
  /** 背驰触发笔终点分型极值价与索引，用于主图标注 */
  anchor_val?: number | null
  anchor_bar_index?: number | null
}

/**
 * 买卖点某一类型的完整视觉定义。
 * 图上（ECharts option）与图例（DOM）共用同一份，避免两处配置漂移。
 */
interface MmdVisual {
  /** ECharts symbol 名（买卖点统一 triangle，朝向由 series 级 symbolRotate 决定）。 */
  symbol: string
  /** 图例里的字形，与图上实际朝向一致：买点 ▲、卖点 ▼。 */
  glyph: string
  /** 图例 DOM 的 class 钩子（端到端脚本按它取 computed 颜色）。 */
  cls: string
  /** 图例文案，如「一类买点 (1buy)」。 */
  label: string
  /** 图上/图例颜色：买点=上涨色、卖点=下跌色。 */
  color: string
  /** 图上符号尺寸（px）。 */
  size: number
  /** 图上不透明度：1类最实、3类最淡。 */
  opacity: number
  /** 图例字形字号（px），与 size 同向变化，让用户能靠大小分辨 1/2/3 类。 */
  fontSize: number
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
 *
 * 防御：bar_index 在范围内时，对日线及以上周期校验其指向的 bar 日期是否与
 * 端点自带 date 一致；不一致说明分析帧与 props.bars 帧长漂移（如取数翻页多返
 * 导致分析 bar 数 > 前端 bars 数），bar_index 已指向另一根 K 线，此时回退到
 * 日期匹配，避免分型/笔/中枢等所有索引锚定的标记整体错位
 * （用户反馈「2023-06-13~16 日线全部标记底分型」即此错位所致）。
 * 仅对 dateStr 无时分（日线/周/月，每天/周/月唯一一根）做该校验——分钟线
 * 日期匹配不可靠，仍信任后端 bar_index（与下方 findBarIndex 注释一致）。
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
    // 仅对「日线及以上」周期做日期校验：其每天/周/月唯一一根 K 线，日期前缀
    // 是可靠的单 bar 键，可用来识别 bar_index 是否因帧长漂移而指向了另一根。
    // 分钟级日期匹配不可靠（一天多根），仍信任后端 bar_index（与 findBarIndex
    // 注释一致）。判定「日线及以上」= dateStr 无时分，或时分全为 00:00。
    const s = dateStr.replace(' ', 'T')
    const timePart = s.length > 10 ? s.slice(11) : ''
    const dailyGrade = !timePart || timePart === '00:00:00' || timePart === '00:00'
    if (dailyGrade && dateStr) {
      const bar = props.bars[idx]
      if (bar && bar.datetime.slice(0, 10) !== dateStr.slice(0, 10)) {
        const dateIdx = findBarIndex(keyIndex, dateStr)
        if (dateIdx !== -1) idx = dateIdx
      }
    }
  } else {
    idx = findBarIndex(keyIndex, dateStr)
  }
  return idx >= revealLimit ? -1 : idx
}

// V723: 前置拼接（加载更早）时保持 dataZoom 视口不跳变（spec: chart-history-navigation
// 「增量加载 MUST 保持当前 dataZoom 视口不跳变」）。检测方式：首根 datetime 变化
// 且长度增加 = prepend；此时把旧绝对窗口 [a,b] 平移 delta 根后再换算回百分比。
// 其余重渲染（训练揭示推进等）维持原有默认缩放行为，不引入 UX 变化。
let prevBarsLen = 0
let prevFirstKey = ''
let zoomKeep: { start: number; end: number } | null = null

function render() {
  if (!container.value || props.bars.length === 0) return
  if (!chart) chart = echarts.init(container.value, 'dark')
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
    // inside 与 slider 两个 dataZoom 都需同步，否则范围不一致。
    const dzArr = option.dataZoom as { start: number; end: number }[]
    for (const dz of dzArr ?? []) {
      dz.start = zoomKeep.start
      dz.end = zoomKeep.end
    }
    zoomKeep = null
  }
  chart.setOption(option, true)
  // 开发/调试专用：暴露图表实例供 playwright 等浏览器测试检查内部状态
  if (import.meta.env.DEV) {
    ;(window as unknown as Record<string, unknown>).__CHANLUN_CHART__ = chart
  }
}

// ── 分型配色（顶/底统一白色，常量定义见 echarts-setup.ts）──
// 分型只是结构端点（顶=三K高点、底=三K低点），不表达多空方向；红/绿留给买卖点
// 专用，否则图上会出现「绿色顶分型」这种与卖点撞色、易被误读成信号的标记。
// 顶/底之间靠三角朝向（顶▼/底▲）区分，不靠颜色。

// ── 买卖点的视觉配置（唯一真源）──
// 图上 ECharts option 与侧边图例 DOM 都从 MMD_VISUAL 取值，杜绝「图上改了、
// 图例没改」的两套配置漂移（历史上图例曾用 ●/■/◆ 而图上已是 ▲/▼）。
//   形状：买点=底→向上三角▲，卖点=顶→向下三角▼（卖点系列 symbolRotate:180）
//   类型（1/2/3）：只用 「大小 + 不透明度」区分——1类=大且实、3类=小且淡
//   颜色：买点=上涨色、卖点=下跌色，跟随全局涨跌配色。不写死「绿买红卖」，
//         否则与 K 线涨跌色相反会误读。
/**
 * 类型档位：图上符号尺寸（px）+ 不透明度。1类最实最大、3类最淡最小。
 * 图例字号不在这里写死，而是按 LEGEND_FONT_SCALE 从 size 等比算出，保证图例的
 * 「大小」与图上档位永远同步变化（写死过一次就必然漂移）。
 * 缩放系数取 1.1 而非更小值：早期 0.8 时图例字形只有 14.4px vs 9.6px，截图目视
 * 被判为「大小一致、看不出区分」，等于没区分；放大到 1.1（19.8 vs 13.2）才够看。
 */
const LEGEND_FONT_SCALE = 1.1
/**
 * 档位间距刻意拉开（22/15/11）：原先的 18/14/12 三档在图上挨着时肉眼难辨，
 * 达不到「用大小区分 1/2/3 类」的目的。
 */
const MMD_TIER: Record<string, { size: number; opacity: number }> = {
  '1buy': { size: 22, opacity: 1 },
  '2buy': { size: 15, opacity: 0.8 },
  '2buy_s': { size: 15, opacity: 0.72 },
  '3buy': { size: 11, opacity: 0.6 },
  '1sell': { size: 22, opacity: 1 },
  '2sell': { size: 15, opacity: 0.8 },
  '2sell_s': { size: 15, opacity: 0.72 },
  '3sell': { size: 11, opacity: 0.6 },
}
/** 图例展示顺序（key 与后端 MMDType 取值一致）：先买后卖、每方向按 1→2→类2→3。 */
const MMD_LEGEND_ORDER = [
  '1buy',
  '2buy',
  '2buy_s',
  '3buy',
  '1sell',
  '2sell',
  '2sell_s',
  '3sell',
] as const
const MMD_LEGEND_LABEL: Record<string, string> = {
  '1buy': '一类买点 (1buy)',
  '2buy': '二类买点 (2buy)',
  '2buy_s': '类二买 (2buy_s)',
  '3buy': '三类买点 (3buy)',
  '1sell': '一类卖点 (1sell)',
  '2sell': '二类卖点 (2sell)',
  '2sell_s': '类二卖 (2sell_s)',
  '3sell': '三类卖点 (3sell)',
}
/** 图例 DOM 的 class 钩子（scripts/verify_mmd_colors.py 用它取 computed 色）。 */
const MMD_LEGEND_CLASS: Record<string, string> = {
  '1buy': 'buy-1',
  '2buy': 'buy-2',
  '2buy_s': 'buy-2s',
  '3buy': 'buy-3',
  '1sell': 'sell-1',
  '2sell': 'sell-2',
  '2sell_s': 'sell-2s',
  '3sell': 'sell-3',
}

const MMD_VISUAL = computed<Record<string, MmdVisual>>(() => {
  const buy = upColor.value // 买点=上涨色
  const sell = downColor.value // 卖点=下跌色
  const out: Record<string, MmdVisual> = {}
  for (const key of MMD_LEGEND_ORDER) {
    const tier = MMD_TIER[key]
    const isBuyKey = key.includes('buy')
    out[key] = {
      symbol: 'triangle', // 买点 ▲；卖点由 series 级 symbolRotate:180 翻成 ▼
      glyph: isBuyKey ? '▲' : '▼', // 图例字形，与图上实际朝向一致
      cls: MMD_LEGEND_CLASS[key],
      label: MMD_LEGEND_LABEL[key],
      color: isBuyKey ? buy : sell,
      size: tier.size,
      opacity: tier.opacity,
      // 由图上尺寸等比算出，不写死 → 调 size 时图例自动跟着变
      fontSize: +(tier.size * LEGEND_FONT_SCALE).toFixed(1),
    }
  }
  return out
})
/** 侧边图例列表（v-for 渲染，样式全部内联绑定 → 配色/大小/透明度与图上同源）。 */
const mmdLegendItems = computed(() =>
  MMD_LEGEND_ORDER.map((key) => ({ key, ...MMD_VISUAL.value[key] })),
)
/** 图上打点取配置：未知类型回退到与方向一致的中性档位，不静默变黑。 */
function mmdVisual(type: string): MmdVisual {
  const known = MMD_VISUAL.value[type]
  if (known) return known
  const isBuy = type.includes('buy')
  return {
    symbol: 'triangle',
    glyph: isBuy ? '▲' : '▼',
    cls: '',
    label: type,
    color: isBuy ? upColor.value : downColor.value,
    size: 14,
    opacity: 0.8,
    fontSize: +(14 * LEGEND_FONT_SCALE).toFixed(1),
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
  const dates = keys.map((k) => (isIntraday ? k.replace('T', ' ').slice(5, 16) : k.slice(0, 10)))

  const ohlc = props.bars.slice(0, revealLimit).map((b) => [b.open, b.close, b.low, b.high])

  // ── MACD 副图数据（dif/dea/hist 与 bars 一一对应，按揭示窗口截断）──
  // 缠论背驰由笔内 MACD 红绿柱面积判断（后端 calc_macd_force），
  // 副图展示 MACD 便于用户核对背驰依据；数据缺失时副图退化为空。
  const macdHist: number[] = (props.macd?.hist ?? []).slice(0, revealLimit)
  const macdDif: number[] = (props.macd?.dif ?? []).slice(0, revealLimit)
  const macdDea: number[] = (props.macd?.dea ?? []).slice(0, revealLimit)

  // 揭示游标竖线（标记训练当前揭示到的位置）
  const cursorMarkLines = revealActive
    ? [
        {
          xAxis: Math.max(revealLimit - 1, 0),
          lineStyle: { color: '#60a5fa', width: 1, type: 'dashed' as const },
          label: {
            show: true,
            formatter: '揭示位',
            color: '#60a5fa',
            fontSize: 10,
            position: 'insideEndTop' as const,
          },
        },
      ]
    : []

  // ── 分型的 MarkPoint ──
  // 紧凑模式下不显示「顶/底」文字标签，只画小圆点（268 个分型每个都带文字会严重遮挡 K 线）。
  // 颜色：顶/底统一白色，不跟涨跌配色。分型只是结构端点（顶=高点、底=低点），
  //       不表达多空方向；若套用红绿色会与买卖点语义混淆（红/绿留给买卖点专用）。
  // 优先使用缠论有效分型（笔端点，顶底交替且不共用K线）。
  // 只在调用方「完全没传」validFxs 时才回退原始 fractals（此时无从选择）；
  // 不再把「传了但为空」当成回退信号——后端正常必定返回 valid_fractals，空数组
  // 表示本窗口确实没有合规分型，此时退回含大量违规对的原始列表，会在图上画出
  // 「12-17底→12-18顶→12-19底」这类共用K线的伪分型。
  const fractalSrc = props.validFxs ?? props.fxs
  const fxPoints =
    props.showFractals === false
      ? []
      : (fractalSrc ?? [])
          .map((fx) => {
            const idx = findAnchorIndex(keyIndex, fx.bar_index, fx.date, revealLimit)
            if (idx === -1 || idx >= revealLimit) return null
            // 端点直接锚定在分型极值价上（fx.val），而不是用 K 线高/低偏移：
            // 用户反馈「端点没在K线极值上」——分型标记必须精确落在极值点。
            const price = fx.val
            return {
              coord: [idx, price],
              itemStyle: { color: FX_COLOR },
              // 用户要求：笔端点（分型）用小圆点，不用三角形。
              // 圆点是旋转对称的，symbolRotate 对它无效 → 顶/底改用 y 轴偏移区分：
              // 顶分型画在最高价**上方**（symbolOffset 负 y），底分型画在最低价**下方**。
              symbol: FX_SYMBOL,
              fxType: fx.fx_type,
              symbolSize: props.compact ? 5 : 8,
              label: {
                show: props.showFractalLabels === true && !props.compact,
                formatter: fx.fx_type === 'ding' ? '顶' : '底',
                color: FX_COLOR,
                fontSize: 9,
                position: fx.fx_type === 'ding' ? 'top' : 'bottom',
              },
            }
          })
          .filter(Boolean)

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
        color: isUp ? upColor.value : downColor.value,
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

  // ── 走势段（ZSD）的 MarkLine（粗实线） ──
  const zsdMarkLines =
    props.showZsds === false
      ? []
      : (props.zsds ?? [])
          .filter((zsd) => {
            const si = findAnchorIndex(keyIndex, zsd.start_index, zsd.start_date, revealLimit)
            const ei = findAnchorIndex(keyIndex, zsd.end_index, zsd.end_date, revealLimit)
            return si !== -1 && ei !== -1
          })
          .map((zsd) => {
            const si = findAnchorIndex(keyIndex, zsd.start_index, zsd.start_date, revealLimit)
            const ei = findAnchorIndex(keyIndex, zsd.end_index, zsd.end_date, revealLimit)
            const isUp = zsd.direction === 'up'
            const lineStyle = {
              color: isUp ? 'rgba(34,197,94,0.55)' : 'rgba(239,68,68,0.55)',
              width: props.compact ? 2 : 3,
              type: 'solid' as const,
            }
            const startY = zsd.start_val ?? (isUp ? zsd.low : zsd.high)
            const endY = zsd.end_val ?? (isUp ? zsd.high : zsd.low)
            return [
              { coord: [si, startY], lineStyle, label: { show: false }, symbol: 'none' },
              { coord: [ei, endY], lineStyle, label: { show: false }, symbol: 'none' },
            ]
          })

  // ── 趋势段（QSD）的 MarkLine（粗虚线） ──
  const qsdMarkLines =
    props.showZsds === false
      ? []
      : (props.qsds ?? [])
          .filter((qsd) => {
            const si = findAnchorIndex(keyIndex, qsd.start_index, qsd.start_date, revealLimit)
            const ei = findAnchorIndex(keyIndex, qsd.end_index, qsd.end_date, revealLimit)
            return si !== -1 && ei !== -1
          })
          .map((qsd) => {
            const si = findAnchorIndex(keyIndex, qsd.start_index, qsd.start_date, revealLimit)
            const ei = findAnchorIndex(keyIndex, qsd.end_index, qsd.end_date, revealLimit)
            const isUp = qsd.direction === 'up'
            const lineStyle = {
              color: isUp ? '#16a34a' : '#dc2626',
              width: props.compact ? 2 : 3,
              type: 'dashed' as const,
            }
            const startY = qsd.start_val ?? (isUp ? qsd.low : qsd.high)
            const endY = qsd.end_val ?? (isUp ? qsd.high : qsd.low)
            return [
              { coord: [si, startY], lineStyle, label: { show: false }, symbol: 'none' },
              { coord: [ei, endY], lineStyle, label: { show: false }, symbol: 'none' },
            ]
          })

  // ── 中枢的 MarkArea ──
  const zsMarkAreas =
    props.showZss === false
      ? []
      : props.zss
          .filter((zs) => {
            // 同级别中枢过滤：指定 singleZsIndex 时只渲染该中枢
            if (props.singleZsIndex !== undefined && zs.index !== props.singleZsIndex) {
              return false
            }
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

  const mmdBuyPoints =
    props.showMmds === false
      ? []
      : props.mmds
          .filter((m) => m.date != null && m.type.includes('buy'))
          .map((m) => {
            const idx = findAnchorIndex(keyIndex, m.bar_index, m.date!, revealLimit)
            if (idx === -1) return null
            let price: number
            if (
              m.anchor_val !== undefined &&
              m.anchor_val !== null &&
              Number.isFinite(m.anchor_val)
            ) {
              price = m.anchor_val
            } else {
              price = props.bars[idx].low * (1 - 0.005)
            }
            const v = mmdVisual(m.type)
            // V735 第29课：1买/1卖后置验证未通过（反弹未触及中枢DD/GG）
            // ⇒ 标记⚠，提示该点可能不是真背驰
            const showWarn = m.rebound_verified === false
            return {
              name: m.type,
              coord: [idx, price],
              itemStyle: {
                color: v.color,
                opacity: v.opacity,
              },
              symbol: v.symbol,
              symbolSize: v.size,
              label: showWarn
                ? { show: true, formatter: '⚠', color: '#e74c3c', fontSize: 14, position: 'inside' }
                : { show: false },
            }
          })
          .filter(Boolean)
  const mmdSellPoints =
    props.showMmds === false
      ? []
      : props.mmds
          .filter((m) => m.date != null && !m.type.includes('buy'))
          .map((m) => {
            const idx = findAnchorIndex(keyIndex, m.bar_index, m.date!, revealLimit)
            if (idx === -1) return null
            let price: number
            if (
              m.anchor_val !== undefined &&
              m.anchor_val !== null &&
              Number.isFinite(m.anchor_val)
            ) {
              price = m.anchor_val
            } else {
              price = props.bars[idx].high * (1 + 0.005)
            }
            const v = mmdVisual(m.type)
            // V735 第29课：1买/1卖后置验证未通过（反弹未触及中枢DD/GG）
            const showWarn = m.rebound_verified === false
            return {
              name: m.type,
              coord: [idx, price],
              itemStyle: {
                color: v.color,
                opacity: v.opacity,
              },
              symbol: v.symbol,
              symbolSize: v.size,
              label: showWarn
                ? { show: true, formatter: '⚠', color: '#e74c3c', fontSize: 14, position: 'inside' }
                : { show: false },
            }
          })
          .filter(Boolean)

  // ── 背驰标记 ──
  // 背驰画在 MACD 副图上：y 取该位置 MACD 柱值（无柱数据时退化为 0），
  // 使「背」标记直接落在对应柱子上，直观展示背驰的 MACD 面积依据。
  const bcPoints =
    props.showBcs === false
      ? []
      : (props.bcs ?? [])
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

  // ── 背驰主图标注 ──
  // 在 K 线主图的触发笔终点分型极值上再标一个「背」，与副图 MACD 柱对照。
  const bcPricePoints =
    props.showBcs === false
      ? []
      : (props.bcs ?? [])
          .filter((bc) => bc.bc && bc.anchor_bar_index != null && bc.anchor_val != null)
          .map((bc) => {
            const idx = findAnchorIndex(keyIndex, bc.anchor_bar_index!, bc.date!, revealLimit)
            if (idx === -1) return null
            return {
              coord: [idx, bc.anchor_val],
              itemStyle: { color: '#ff9500' },
              symbol: 'roundRect',
              symbolSize: [12, 8],
              label: {
                show: true,
                formatter: '背',
                color: '#ff9500',
                fontSize: 9,
                position: 'top' as const,
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
          } else if (p.seriesName === '走势段(粗实线)') {
            html += `<div>${p.marker} 走势段</div>`
          } else if (p.seriesName === '趋势段(粗虚线)') {
            html += `<div>${p.marker} 趋势段</div>`
          } else if (p.seriesName === '顶分型' || p.seriesName === '底分型') {
            html += `<div>${p.marker} ${p.seriesName}</div>`
          } else if (p.seriesName === '买点' || p.seriesName === '卖点') {
            html += `<div>${p.marker} ${p.name}</div>`
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
        ...((props.zsds?.length ?? 0) > 0 ? ['走势段(粗实线)'] : []),
        ...((props.qsds?.length ?? 0) > 0 ? ['趋势段(粗虚线)'] : []),
        ...(props.showZss !== false && props.zss.length ? ['中枢'] : []),
        ...(props.showFractals !== false && props.fxs && props.fxs.length
          ? ['顶分型', '底分型']
          : []),
        ...(mmdBuyPoints.length ? ['买点'] : []),
        ...(mmdSellPoints.length ? ['卖点'] : []),
        ...(props.showBcs !== false && props.bcs && props.bcs.some((bc) => bc.bc)
          ? ['背驰', '背驰(主图)']
          : []),
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
      {
        // 滚轮缩放：以鼠标所在 K 线为中心放大/缩小。
        // 初始显示最后 ~150 根K线（含 TDX 追加的最新数据），
        // 用户可滚轮缩放、底部滑块拖动平移查看任意区间。
        type: 'inside',
        xAxisIndex: [0, 1],
        start: props.bars.length > 150 ? 100 - (150 / props.bars.length) * 100 : 0,
        end: 100,
        zoomOnMouseWheel: true,
        moveOnMouseWheel: false,
        moveOnMouseMove: true,
      },
      {
        type: 'slider',
        bottom: 8,
        start: props.bars.length > 150 ? 100 - (150 / props.bars.length) * 100 : 0,
        end: 100,
        textStyle: { color: '#5c6370' },
        xAxisIndex: [0, 1],
      },
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
          color: upColor.value,
          color0: downColor.value,
          borderColor: upColor.value,
          borderColor0: downColor.value,
        },
        markLine: cursorMarkLines.length
          ? {
              silent: true,
              symbol: 'none',
              label: { show: false },
              data: cursorMarkLines,
            }
          : undefined,
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
      // 走势段（粗实线）：无数据时不创建空 series，避免图例/ tooltip 出现空项
      ...(zsdMarkLines.length
        ? [
            {
              name: '走势段(粗实线)',
              type: 'line',
              xAxisIndex: 0,
              yAxisIndex: 0,
              data: [],
              symbol: 'none',
              lineStyle: { width: 0 },
              markLine: {
                silent: true,
                symbol: 'none',
                label: { show: false },
                data: zsdMarkLines,
              },
            },
          ]
        : []),
      // 趋势段（粗虚线）：无数据时不创建空 series
      ...(qsdMarkLines.length
        ? [
            {
              name: '趋势段(粗虚线)',
              type: 'line',
              xAxisIndex: 0,
              yAxisIndex: 0,
              data: [],
              symbol: 'none',
              lineStyle: { width: 0 },
              markLine: {
                silent: true,
                symbol: 'none',
                label: { show: false },
                data: qsdMarkLines,
              },
            },
          ]
        : []),
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
          itemStyle: {
            color: 'rgba(255,200,50,0.08)',
            borderColor: 'rgba(255,200,50,0.3)',
            borderType: 'dashed',
          },
        },
      },
      // 分型标记：顶/底拆成两个独立 scatter 序列，各自用 series 级固定 symbol。
      // 用户要求（2026-10-10）：笔端点改用**小圆点**（FX_SYMBOL='circle'），不用三角形。
      // 圆点是旋转对称的，旋转属性对其无效 → 顶/底改由 symbolOffset 的 y 方向区分：
      // 顶分型往上偏（负 y，落在最高价上方）、底分型往下偏（正 y，落在最低价下方）。
      // 颜色顶/底统一白色（FX_COLOR）：分型是结构端点而非多空信号，红/绿只给买卖点用。
      {
        name: '顶分型',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
        symbol: FX_SYMBOL,
        // 圆形无法通过 symbolRotate 区分朝向，改用「往极值外侧再偏一格」表达顶/底：
        // 顶分型在最高价上方 → y 负方向偏移。
        symbolOffset: [0, props.compact ? -4 : -6],
        // 深色描边：白点压在白系高亮/上影线上易糊，加一圈描边保证能分离。
        symbolSize: props.compact ? 7 : 10,
        itemStyle: { color: FX_COLOR, borderColor: FX_BORDER_COLOR, borderWidth: 1 },
        data: (fxPoints as any[])
          .filter((p) => p.fxType === 'ding')
          .map((p) => ({
            value: [p.coord[0], p.coord[1]],
            label: {
              show: props.showFractalLabels === true && !props.compact,
              formatter: p.label.formatter,
              color: p.label.color,
              fontSize: 9,
              position: p.label.position,
            },
          })),
        labelLayout: { hideOverlap: true },
        z: 12,
      },
      {
        name: '底分型',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
        symbol: FX_SYMBOL,
        // 底分型在最低价下方 → y 正方向偏移（与顶分型对称）。
        symbolOffset: [0, props.compact ? 4 : 6],
        symbolSize: props.compact ? 7 : 10,
        itemStyle: { color: FX_COLOR, borderColor: FX_BORDER_COLOR, borderWidth: 1 },
        data: (fxPoints as any[])
          .filter((p) => p.fxType === 'di')
          .map((p) => ({
            value: [p.coord[0], p.coord[1]],
            label: {
              show: props.showFractalLabels === true && !props.compact,
              formatter: p.label.formatter,
              color: p.label.color,
              fontSize: 9,
              position: p.label.position,
            },
          })),
        labelLayout: { hideOverlap: true },
        z: 12,
      },
      // 买点（v598：图标区分类型，无文字标注）
      {
        name: '买点',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
        // 买点（买点=底→向上三角▲；类型靠 symbolSize + opacity 区分）
        data: (mmdBuyPoints as any[]).map((p) => ({
          name: p.name,
          value: [p.coord[0], p.coord[1]],
          symbol: p.symbol,
          symbolSize: p.symbolSize,
          // opacity 必须透传：1/2/3 类的「浓淡」区分全靠它，丢了就只剩大小一维
          itemStyle: { color: p.itemStyle.color, opacity: p.itemStyle.opacity },
        })),
        label: {
          show: props.showMmdLabels === true && !props.compact,
          formatter: (params: any) => params?.name ?? '',
          color: '#e2e8f0',
          fontSize: 9,
          position: 'top' as const,
        },
        labelLayout: { hideOverlap: true },
      },
      // 卖点（v598：整体旋转 180°，triangle 变为向下三角，circle/diamond 对称不受影响）
      {
        name: '卖点',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
        symbolRotate: 180,
        // 卖点（整体旋转 180°，triangle 变向下三角▼；类型靠 symbolSize + opacity 区分）
        data: (mmdSellPoints as any[]).map((p) => ({
          name: p.name,
          value: [p.coord[0], p.coord[1]],
          symbol: p.symbol,
          symbolSize: p.symbolSize,
          // opacity 必须透传：1/2/3 类的「浓淡」区分全靠它，丢了就只剩大小一维
          itemStyle: { color: p.itemStyle.color, opacity: p.itemStyle.opacity },
        })),
        label: {
          show: props.showMmdLabels === true && !props.compact,
          formatter: (params: any) => params?.name ?? '',
          color: '#e2e8f0',
          fontSize: 9,
          position: 'top' as const,
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
        data: (bcPoints as any[]).map((p) => ({
          value: [p.coord[0], macdHist[p.coord[0]] ?? 0],
          symbol: p.symbol,
          symbolSize: p.symbolSize,
          itemStyle: { color: p.itemStyle.color },
          label: {
            show: true,
            formatter: p.label.formatter,
            color: p.label.color,
            fontSize: 9,
            position: 'top',
          },
        })),
        labelLayout: { hideOverlap: true },
      },
      // 背驰主图标注（落在触发笔终点分型极值上，与副图对照）
      {
        name: '背驰(主图)',
        type: 'scatter',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: (bcPricePoints as any[]).map((p) => ({
          value: [p.coord[0], p.coord[1]],
          symbol: p.symbol,
          symbolSize: p.symbolSize,
          itemStyle: { color: p.itemStyle.color },
          label: {
            show: true,
            formatter: p.label.formatter,
            color: p.label.color,
            fontSize: 9,
            position: 'top',
          },
        })),
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
          color: (params: any) =>
            (params.value ?? 0) >= 0 ? 'rgba(239,65,70,0.85)' : 'rgba(24,160,88,0.85)',
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
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart?.dispose()
  chart = null
})
watch(
  () => [
    props.bars,
    props.bis,
    props.xds,
    props.zss,
    props.mmds,
    props.fxs,
    props.validFxs,
    props.bcs,
    props.macd,
    props.revealIndex,
  ],
  render,
)
// 全局涨跌配色变化时重渲染（红涨绿跌 ↔ 绿涨红跌）。
watch(colorScheme, render)
</script>

<template>
  <div class="chanlun-layout">
    <div ref="container" class="chanlun-chart"></div>
    <aside
      v-if="
        (props.showMmds !== false && props.mmds.length) ||
        (props.showBcs !== false && props.bcs && props.bcs.some((b) => b.bc))
      "
      class="mmd-legend"
    >
      <div class="mmd-legend-title">买卖点图例</div>
      <template v-if="props.showMmds !== false && props.mmds.length">
        <!-- 图例从 MMD_VISUAL 取字形/颜色/大小/透明度，与图上打点同源：
             买点统一 ▲、卖点统一 ▼；颜色跟随全局涨跌配色；1/2/3 类靠大小+浓淡区分。 -->
        <div
          v-for="item in mmdLegendItems"
          :key="item.key"
          class="mmd-legend-item"
          :title="item.label"
        >
          <span
            class="ic"
            :class="item.cls"
            :style="{
              color: item.color,
              opacity: item.opacity,
              fontSize: item.fontSize + 'px',
              lineHeight: 1,
            }"
            >{{ item.glyph }}</span
          >
          {{ item.label }}
        </div>
      </template>
      <template v-if="props.showBcs !== false && props.bcs && props.bcs.some((b) => b.bc)">
        <div class="legend-sep"></div>
        <div class="mmd-legend-item"><span class="ic bc">▭</span> 背驰(主图)</div>
        <div class="mmd-legend-item"><span class="ic bc-sub">▭</span> 背驰(副图 MACD)</div>
      </template>
      <div class="legend-sep"></div>
      <div class="mmd-legend-item">
        <span class="ic" style="color: #e74c3c; font-size: 14px">⚠</span>
        1买/1卖后置验证未通过(反弹未触及中枢DD/GG)
      </div>
    </aside>
  </div>
</template>

<style scoped>
.chanlun-layout {
  display: flex;
  gap: 8px;
  width: 100%;
}
.chanlun-chart {
  flex: 1;
  min-width: 0;
  /* 双面板：主图（K线+缠论结构）+ MACD 副图，560 太矮导致所有元素挤在一起 */
  height: 760px;
}
.mmd-legend {
  flex-shrink: 0;
  width: 132px;
  padding: 8px;
  border: 1px solid #2a2e3a;
  border-radius: 6px;
  font-size: 12px;
  color: #cbd5e1;
  align-self: flex-start;
}
.mmd-legend-title {
  font-weight: 600;
  margin-bottom: 6px;
  color: #e5e7eb;
}
.mmd-legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  line-height: 1.9;
}
.ic {
  display: inline-block;
  /* 买卖点字形按 1/2/3 类放大缩小（10~15px），固定槽宽保证文案左对齐不跳动 */
  width: 18px;
  text-align: center;
}
/* 买卖点图例的颜色/大小/透明度全部内联绑定自 MMD_VISUAL（与图上同源），
   此处不再写死买点/卖点色系——写死会让图例与图在换配色后漂移。 */
.bc {
  color: #ff9500;
}
.bc-sub {
  color: #ff9500;
  opacity: 0.8;
}
.legend-sep {
  height: 1px;
  background: #2a2e3a;
  margin: 6px 0;
}

/* 响应式高度：在小屏幕上缩小图表高度 */
@media (max-width: 768px) {
  .chanlun-chart {
    height: 560px;
  }
}
</style>
