// V724: K 线历史本地缓存（IndexedDB）。
//
// 设计要点（配合 api.ts fetchBars 的增量编排）：
// - 只缓存「已收盘的历史序列」：键为 market:code:category 的整段升序 Bar 数组。
// - 打开图表时先用缓存渲染，再向服务器要一小段增量校准（见 api.ts）。
// - 服务器返回的前复权历史可能因除权整体重算（价格全变）：api.ts 采样比对
//   close，命中则整体重取并回写，本地永远不会留下错价历史。
// - 所有操作静默容错：隐私模式/存储满/IndexedDB 不可用时缓存层直接透明失效。

const DB_NAME = 'easy_tdx_bars'
const DB_VERSION = 1
const STORE = 'series'

import type { Bar } from '../types'

export interface BarsCacheEntry {
  key: string
  bars: BarRecord[]
  updated_at: string
}

/** 与 api.ts 的 Bar 结构一致（运行时同构，仅类型引用）。 */
export type BarRecord = Bar

/** 缓存键：市场:代码:周期，同一序列全量覆盖写。 */
export function barsCacheKey(market: string, code: string, category: string): string {
  return `${market}:${code}:${category}`
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('IndexedDB unavailable'))
      return
    }
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'key' })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error ?? new Error('IndexedDB open failed'))
  })
}

async function withStore<T>(
  mode: IDBTransactionMode,
  fn: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await openDB()
  try {
    const tx = db.transaction(STORE, mode)
    const req = fn(tx.objectStore(STORE))
    return await new Promise<T>((resolve, reject) => {
      req.onsuccess = () => resolve(req.result)
      req.onerror = () => reject(req.error ?? new Error('IndexedDB request failed'))
    })
  } finally {
    db.close()
  }
}

/** 读取一条序列缓存；无记录/结构不符返回 null。 */
export async function loadBarsSeries(key: string): Promise<Bar[] | null> {
  try {
    const entry = (await withStore('readonly', (s) => s.get(key) as IDBRequest<BarsCacheEntry | undefined>)) as
      | BarsCacheEntry
      | undefined
    if (entry && Array.isArray(entry.bars) && entry.bars.length > 0) {
      return entry.bars as unknown as Bar[]
    }
    return null
  } catch {
    return null
  }
}

/** 覆盖写一条序列缓存（静默容错，失败不影响调用方）。 */
export async function saveBarsSeries(key: string, bars: Bar[]): Promise<void> {
  try {
    const entry: BarsCacheEntry = {
      key,
      bars: bars as unknown as BarRecord[],
      updated_at: new Date().toISOString(),
    }
    await withStore('readwrite', (s) => s.put(entry) as unknown as IDBRequest<unknown>)
  } catch {
    // 缓存写失败不影响功能（隐私模式 / 配额满）
  }
}

export async function clearBarsSeries(key: string): Promise<void> {
  try {
    await withStore('readwrite', (s) => s.delete(key) as unknown as IDBRequest<unknown>)
  } catch {
    // 忽略
  }
}

export async function clearAllBarsCache(): Promise<void> {
  try {
    await withStore('readwrite', (s) => s.clear() as unknown as IDBRequest<unknown>)
  } catch {
    // 忽略
  }
}
