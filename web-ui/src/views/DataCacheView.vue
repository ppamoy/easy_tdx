<script setup lang="ts">
// K线数据缓存查看页面：展示所有已缓存到本地的K线数据。
// 显示：股票代码、有数据的级别、时间区间、K线根数。
import { onMounted, ref, computed } from 'vue'
import { fetchCacheOverview, formatError } from '../api'
import type { CacheOverview } from '../types'

const overview = ref<CacheOverview | null>(null)
const loading = ref(false)
const error = ref('')
const searchQuery = ref('')
const sortBy = ref<'symbol' | 'bars' | 'levels'>('symbol')
const expandedStock = ref<string | null>(null)

onMounted(loadCache)

async function loadCache() {
  loading.value = true
  error.value = ''
  try {
    overview.value = await fetchCacheOverview()
  } catch (e) {
    error.value = formatError(e)
  } finally {
    loading.value = false
  }
}

const filteredStocks = computed(() => {
  if (!overview.value) return []
  let stocks = overview.value.stocks
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    stocks = stocks.filter(
      (s) => s.symbol.toLowerCase().includes(q) || s.code.includes(q),
    )
  }
  const sorted = [...stocks]
  if (sortBy.value === 'symbol') {
    sorted.sort((a, b) => a.symbol.localeCompare(b.symbol))
  } else if (sortBy.value === 'bars') {
    sorted.sort((a, b) => b.total_bars - a.total_bars)
  } else if (sortBy.value === 'levels') {
    sorted.sort((a, b) => b.level_count - a.level_count)
  }
  return sorted
})

function toggleExpand(symbol: string) {
  expandedStock.value = expandedStock.value === symbol ? null : symbol
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatBars(n: number): string {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}万`
  return n.toLocaleString()
}
</script>

<template>
  <div class="data-cache-view">
    <h2>📊 K线数据缓存</h2>
    <p class="subtitle">已下载到本地的K线数据。每次API取数后自动保存，下次直接读盘。</p>

    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else-if="overview">
      <!-- 汇总统计 -->
      <div class="stats-bar">
        <div class="stat-item">
          <span class="stat-value">{{ overview.total_stocks }}</span>
          <span class="stat-label">缓存股票</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ overview.total_files }}</span>
          <span class="stat-label">缓存文件</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ formatBars(overview.total_bars) }}</span>
          <span class="stat-label">K线总根数</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ overview.categories.length }}</span>
          <span class="stat-label">级别种类</span>
        </div>
      </div>

      <!-- 搜索和排序 -->
      <div class="toolbar">
        <input
          v-model="searchQuery"
          class="search-input"
          placeholder="搜索股票代码..."
        />
        <select v-model="sortBy" class="sort-select">
          <option value="symbol">按代码排序</option>
          <option value="bars">按K线数排序</option>
          <option value="levels">按级别数排序</option>
        </select>
      </div>

      <!-- 数据表格 -->
      <div class="table-container">
        <table class="cache-table">
          <thead>
            <tr>
              <th>股票代码</th>
              <th>有数据级别</th>
              <th>K线总数</th>
              <th>时间区间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="stock in filteredStocks" :key="stock.symbol">
              <tr class="stock-row" @click="toggleExpand(stock.symbol)">
                <td class="stock-code">{{ stock.symbol }}</td>
                <td class="levels-cell">
                  <span
                    v-for="level in stock.levels"
                    :key="level.category"
                    class="level-badge"
                    :class="{ minute: level.category.includes('min') }"
                  >
                    {{ level.label }}
                    <span class="bar-count">{{ formatBars(level.bar_count) }}</span>
                  </span>
                </td>
                <td class="bar-total">{{ formatBars(stock.total_bars) }}</td>
                <td class="date-range">
                  {{ stock.levels[0]?.start_date }} ~ {{ stock.levels[0]?.end_date }}
                </td>
                <td>
                  <span class="expand-btn">{{ expandedStock === stock.symbol ? '收起' : '详情' }}</span>
                </td>
              </tr>
              <tr v-if="expandedStock === stock.symbol" class="detail-row">
                <td colspan="5">
                  <div class="detail-content">
                    <table class="detail-table">
                      <thead>
                        <tr>
                          <th>级别</th>
                          <th>K线根数</th>
                          <th>开始时间</th>
                          <th>结束时间</th>
                          <th v-if="stock.levels.some(l => l.file_size)">文件大小</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr v-for="level in stock.levels" :key="level.category">
                          <td>{{ level.label }}</td>
                          <td>{{ level.bar_count.toLocaleString() }}</td>
                          <td>{{ level.start_date }}</td>
                          <td>{{ level.end_date }}</td>
                          <td v-if="level.file_size">{{ formatSize(level.file_size) }}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
      <div v-if="filteredStocks.length === 0" class="no-data">
        未找到匹配的缓存数据
      </div>
    </template>
    <div v-else class="no-data">暂无缓存数据。分析股票后数据会自动保存。</div>
  </div>
</template>

<style scoped>
.data-cache-view {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.subtitle {
  color: #888;
  font-size: 14px;
  margin-bottom: 16px;
}

.stats-bar {
  display: flex;
  gap: 24px;
  margin-bottom: 20px;
  padding: 16px;
  background: #f5f7fa;
  border-radius: 8px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #4096ff;
}

.stat-label {
  font-size: 12px;
  color: #999;
}

.toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.search-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}

.sort-select {
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
  background: white;
}

.table-container {
  overflow-x: auto;
}

.cache-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.cache-table th {
  text-align: left;
  padding: 10px 12px;
  background: #fafafa;
  border-bottom: 2px solid #eee;
  font-weight: 600;
  color: #666;
  white-space: nowrap;
}

.stock-row {
  cursor: pointer;
  transition: background 0.15s;
}

.stock-row:hover {
  background: #f0f7ff;
}

.cache-table td {
  padding: 10px 12px;
  border-bottom: 1px solid #f0f0f0;
}

.stock-code {
  font-weight: 600;
  color: #333;
}

.levels-cell {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.level-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 4px;
  background: #e6f4ff;
  color: #1677ff;
  font-size: 12px;
  white-space: nowrap;
}

.level-badge.minute {
  background: #fff7e6;
  color: #fa8c16;
}

.bar-count {
  font-size: 11px;
  opacity: 0.7;
}

.bar-total {
  font-weight: 600;
  color: #52c41a;
}

.date-range {
  color: #999;
  font-size: 13px;
  white-space: nowrap;
}

.expand-btn {
  color: #1677ff;
  font-size: 13px;
  cursor: pointer;
}

.detail-row td {
  padding: 0;
  background: #fafbfc;
}

.detail-content {
  padding: 12px 24px;
}

.detail-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.detail-table th {
  text-align: left;
  padding: 6px 12px;
  color: #999;
  border-bottom: 1px solid #eee;
}

.detail-table td {
  padding: 6px 12px;
  border-bottom: 1px solid #f5f5f5;
}

.loading,
.error,
.no-data {
  text-align: center;
  padding: 40px;
  color: #999;
}

.error {
  color: #ff4d4f;
}
</style>
