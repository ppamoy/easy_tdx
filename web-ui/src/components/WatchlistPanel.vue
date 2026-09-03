<script setup lang="ts">
// 全局自选股面板：从任意页面快速切换股票、查看简要信息。
// 数据来自 localStorage，跨页面共享。

import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

interface WatchItem {
  code: string
  market: string
  symbol: string
  name?: string
  category?: string
}

const router = useRouter()
const isOpen = ref(false)
const items = ref<WatchItem[]>([])
const search = ref('')
const addMarket = ref('SH')
const addCode = ref('')

// 从 localStorage 加载自选股
function loadWatchlist() {
  try {
    const raw = localStorage.getItem('easy_tdx_global_watchlist')
    if (raw) items.value = JSON.parse(raw)
  } catch {
    items.value = []
  }
}

// 保存到 localStorage
function saveWatchlist() {
  try {
    localStorage.setItem('easy_tdx_global_watchlist', JSON.stringify(items.value))
  } catch {
    /* ignore */
  }
}

// 添加到自选
function doAdd() {
  const code = addCode.value.trim()
  if (!code.match(/^\d{6}$/)) return
  const exists = items.value.find((i) => i.code === code)
  if (exists) return
  items.value.unshift({ code, market: addMarket.value, symbol: `${addMarket.value}${code}` })
  saveWatchlist()
  addCode.value = ''
}

// 移除自选
function removeFromWatch(index: number) {
  items.value.splice(index, 1)
  saveWatchlist()
}

// 过滤后的列表
const filtered = computed(() => {
  if (!search.value) return items.value
  const q = search.value.toLowerCase()
  return items.value.filter(
    (i) => i.code.includes(q) || i.symbol.toLowerCase().includes(q) || (i.name ?? '').includes(q),
  )
})

// 跳转到缠论分析页
function goToChanlun(item: WatchItem) {
  router.push({ path: '/chanlun', query: { symbol: item.code, market: item.market } })
  isOpen.value = false
}

// 跳转到回测页
function goToBacktest(item: WatchItem) {
  router.push({ path: '/', query: { symbol: item.code, category: 'DAY' } })
  isOpen.value = false
}

// 跳转到技术诊断页
function goToDiagnosis(item: WatchItem) {
  router.push({ path: '/diagnosis', query: { code: item.code, market: item.market } })
  isOpen.value = false
}

onMounted(loadWatchlist)
</script>

<template>
  <!-- 浮动按钮 -->
  <button
    class="watchlist-toggle"
    :class="{ open: isOpen }"
    @click="isOpen = !isOpen"
    title="自选股 (Ctrl+Shift+W)"
  >
    <span class="toggle-icon">⭐</span>
    <span v-if="items.length > 0" class="badge">{{ items.length }}</span>
  </button>

  <!-- 面板 -->
  <transition name="slide">
    <div v-if="isOpen" class="watchlist-panel">
      <div class="panel-header">
        <h3>⭐ 自选股</h3>
        <button class="close-btn" @click="isOpen = false">✕</button>
      </div>

      <!-- 搜索 -->
      <div class="search-box">
        <input v-model="search" placeholder="搜索代码/名称..." maxlength="20" />
      </div>

      <!-- 列表 -->
      <div v-if="filtered.length === 0" class="empty-state">
        <p>暂无自选股</p>
        <p class="hint">在缠论分析页点击「👁 加入监控」添加</p>
      </div>
      <div v-else class="watchlist-items">
        <div v-for="(item, i) in filtered" :key="item.symbol + i" class="watch-item">
          <div class="item-info">
            <span class="item-symbol">{{ item.symbol }}</span>
            <span v-if="item.name" class="item-name">{{ item.name }}</span>
            <span v-if="item.category" class="item-cat">{{ item.category }}</span>
          </div>
          <div class="item-actions">
            <button class="ghost tiny" @click="goToChanlun(item)">缠论</button>
            <button class="ghost tiny" @click="goToDiagnosis(item)">诊断</button>
            <button class="ghost tiny" @click="goToBacktest(item)">回测</button>
            <button class="remove-btn" @click="removeFromWatch(i)">×</button>
          </div>
        </div>
      </div>

      <!-- 快捷添加 -->
      <div class="add-section">
        <div class="add-row">
          <select v-model="addMarket" class="market-select">
            <option value="SH">沪市</option>
            <option value="SZ">深市</option>
          </select>
          <input
            v-model="addCode"
            placeholder="6位代码"
            maxlength="6"
            class="code-input"
            @keyup.enter="doAdd"
          />
          <button class="primary tiny" @click="doAdd">添加</button>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
/* 浮动按钮 */
.watchlist-toggle {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: var(--accent);
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  z-index: 1000;
  transition:
    transform 0.2s,
    background 0.2s;
}
.watchlist-toggle:hover {
  transform: scale(1.05);
  background: #5aa0ff;
}
.watchlist-toggle.open {
  background: #ef4444;
}
.toggle-icon {
  font-size: 22px;
}
.badge {
  position: absolute;
  top: -4px;
  right: -4px;
  background: #ef4444;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  min-width: 18px;
  height: 18px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
}

/* 面板 */
.watchlist-panel {
  position: fixed;
  bottom: 88px;
  right: 24px;
  width: 320px;
  max-height: 480px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.panel-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}
.close-btn {
  background: none;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
  font-size: 16px;
  padding: 2px 6px;
}
.close-btn:hover {
  color: var(--text);
}

/* 搜索 */
.search-box {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
}
.search-box input {
  width: 100%;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 13px;
  color: var(--text);
  box-sizing: border-box;
}
.search-box input:focus {
  outline: none;
  border-color: var(--accent);
}

/* 列表 */
.watchlist-items {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.watch-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  background: rgba(255, 255, 255, 0.02);
  border-radius: 6px;
  margin-bottom: 4px;
  transition: background 0.1s;
}
.watch-item:hover {
  background: rgba(255, 255, 255, 0.06);
}
.item-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.item-symbol {
  font-family: var(--font-mono);
  font-weight: 600;
  font-size: 13px;
  color: var(--text);
}
.item-name {
  font-size: 11px;
  color: var(--text-muted);
}
.item-cat {
  font-size: 10px;
  padding: 1px 4px;
  background: rgba(255, 255, 255, 0.06);
  border-radius: 3px;
  color: var(--text-dim);
}
.item-actions {
  display: flex;
  gap: 4px;
  align-items: center;
}
.remove-btn {
  background: none;
  border: none;
  color: var(--text-dim);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  padding: 2px 4px;
}
.remove-btn:hover {
  color: #ef4444;
}

/* 添加区 */
.add-section {
  padding: 10px 12px;
  border-top: 1px solid var(--border);
}
.add-row {
  display: flex;
  gap: 6px;
  align-items: center;
}
.market-select {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 6px;
  font-size: 12px;
  color: var(--text);
  width: 50px;
}
.code-input {
  flex: 1;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 13px;
  color: var(--text);
  font-family: var(--font-mono);
}
.code-input:focus {
  outline: none;
  border-color: var(--accent);
}
.tiny {
  font-size: 11px;
  padding: 4px 8px;
}

/* 空状态 */
.empty-state {
  padding: 24px 16px;
  text-align: center;
  color: var(--text-dim);
  font-size: 13px;
}
.empty-state .hint {
  font-size: 11px;
  margin-top: 4px;
  opacity: 0.7;
}

/* 过渡动画 */
.slide-enter-active,
.slide-leave-active {
  transition:
    opacity 0.2s,
    transform 0.2s;
}
.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
</style>
