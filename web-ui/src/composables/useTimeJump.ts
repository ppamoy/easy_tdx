// V723: 「按日期跳转 / 回最新」共享逻辑（任意时间区间查看 K 线）。
// 与 useEarlierBars（往前翻页）互补：这里按起止日期一次性取历史区间，
// 拼接/重分析/结构平移由调用方决定——各视图数据容器形状不同。
import { ref } from 'vue'

import { fetchBarsRange } from '../api'
import type { Bar, Category } from '../types'

export interface TimeJumpOptions {
  code: () => string
  category: () => Category
  detectMarket: (code6: string) => string
}

/** 校验 YYYY-MM-DD（空串视为未填，由调用方决定是否必填）。 */
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

export function useTimeJump(opts: TimeJumpOptions) {
  const jumpStart = ref('')
  const jumpEnd = ref('')
  const jumping = ref(false)
  const jumpError = ref('')

  function resetToLatest() {
    jumpStart.value = ''
    jumpEnd.value = ''
    jumpError.value = ''
  }

  /** 按当前输入取区间 K 线；非法输入返回 null（错误写入 jumpError）。 */
  async function fetchRange(): Promise<Bar[] | null> {
    const start = jumpStart.value.trim()
    const end = jumpEnd.value.trim()
    if (!DATE_RE.test(start)) {
      jumpError.value = '请输入开始日期（YYYY-MM-DD）'
      return null
    }
    if (end && !DATE_RE.test(end)) {
      jumpError.value = '结束日期格式应为 YYYY-MM-DD'
      return null
    }
    if (end && end < start) {
      jumpError.value = '结束日期不能早于开始日期'
      return null
    }
    const code = opts.code()
    if (!/^\d{6}$/.test(code)) {
      jumpError.value = '请输入 6 位股票代码'
      return null
    }
    jumping.value = true
    jumpError.value = ''
    try {
      const market = opts.detectMarket(code)
      const bars = await fetchBarsRange(market, code, opts.category(), start, end || undefined)
      if (bars.length === 0) {
        jumpError.value = '该区间没有行情数据（可能早于上市日或非交易日）'
        return null
      }
      return bars
    } catch (e) {
      jumpError.value = e instanceof Error ? e.message : String(e)
      return null
    } finally {
      jumping.value = false
    }
  }

  return { jumpStart, jumpEnd, jumping, jumpError, fetchRange, resetToLatest }
}
