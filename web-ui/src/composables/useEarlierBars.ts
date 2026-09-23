// V722: 「加载更早 / 回最新」共享逻辑（图表全历史回溯）。
// 各视图数据容器形状不同（store.ohlcv / 局部 ref），这里只封装
// loadEarlierBars 的取数 + 状态管理，拼接与重分析由调用方决定。
import { computed, ref } from 'vue'

import { loadEarlierBars } from '../api'
import type { Bar, Category } from '../types'

export interface EarlierBarsOptions {
  code: () => string
  category: () => Category
  earliest: () => string
  detectMarket: (code6: string) => string
  batchSize?: number
}

export function useEarlierBars(opts: EarlierBarsOptions) {
  const loading = ref(false)
  const exhausted = ref(false)
  const error = ref('')
  const lastBatch = ref(0)

  const canLoad = computed(
    () => !loading.value && !exhausted.value && opts.earliest().length > 0,
  )

  async function fetchEarlier(): Promise<Bar[]> {
    const earliest = opts.earliest()
    if (!earliest || loading.value) return []
    loading.value = true
    error.value = ''
    try {
      const market = opts.detectMarket(opts.code())
      const earlier = await loadEarlierBars(
        market,
        opts.code(),
        opts.category(),
        earliest,
        opts.batchSize ?? 800,
      )
      lastBatch.value = earlier.length
      if (earlier.length < (opts.batchSize ?? 800)) exhausted.value = true
      return earlier
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
      return []
    } finally {
      loading.value = false
    }
  }

  function resetToLatest() {
    exhausted.value = false
    lastBatch.value = 0
  }

  return { loading, exhausted, error, canLoad, lastBatch, fetchEarlier, resetToLatest }
}
