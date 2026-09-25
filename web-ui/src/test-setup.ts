// V724: vitest 全局 setup。jsdom 未内置 IndexedDB，
// 用 fake-indexeddb 提供 K 线缓存单测所需的全局实现。
import 'fake-indexeddb/auto'
