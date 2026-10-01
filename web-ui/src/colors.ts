// 全局涨跌配色（响应式）。独立于 echarts-setup，避免被图表 mock 拦截后丢失响应式状态。
// 红涨绿跌（A 股惯例）或 绿涨红跌（国际惯例），可在「显示设置」页切换。
// 状态为响应式 ref，组件 buildOption 时读取 .value，watch 变化即可重渲染。
import { computed, ref } from 'vue'

const RED = '#ef4146'
const GREEN = '#18a058'

export type ColorScheme = 'red-up' | 'green-up'

function loadScheme(): ColorScheme {
  try {
    const s = typeof localStorage !== 'undefined' ? localStorage.getItem('easy-tdx.colorScheme') : null
    return s === 'green-up' ? 'green-up' : 'red-up'
  } catch {
    return 'red-up'
  }
}

/** 当前配色方案（响应式）。 */
export const colorScheme = ref<ColorScheme>(loadScheme())
/** 上涨色（响应式 computed）。 */
export const upColor = computed(() => (colorScheme.value === 'red-up' ? RED : GREEN))
/** 下跌色（响应式 computed）。 */
export const downColor = computed(() => (colorScheme.value === 'red-up' ? GREEN : RED))

/** 切换配色方案并持久化到 localStorage。 */
export function setColorScheme(s: ColorScheme): void {
  colorScheme.value = s
  try {
    localStorage.setItem('easy-tdx.colorScheme', s)
  } catch {
    /* localStorage 不可用时静默 */
  }
}
