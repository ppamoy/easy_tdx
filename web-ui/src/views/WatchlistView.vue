<template>
  <div class="watchlist-view">
    <h2>自选股看板</h2>
    <p class="subtitle">全池融合扫描 · 方向过滤+技术评分+缠论买卖点</p>

    <!-- 顶部状态栏 -->
    <div class="status-bar">
      <div class="status-item" v-if="scanData.scan_time">
        <span class="status-label">扫描时间</span>
        <span class="status-value">{{ scanData.scan_time }}</span>
      </div>
      <div class="status-item">
        <span class="status-label">市场季节</span>
        <span class="status-value" :class="`season-${scanData.season}`">
          {{ seasonLabel(scanData.season) }}
        </span>
      </div>
      <div class="status-item">
        <span class="status-label">扫描数量</span>
        <span class="status-value">{{ scanData.total_scanned || 0 }}</span>
      </div>
      <div class="status-item">
        <span class="status-label">可操作</span>
        <span class="status-value execute-count">{{ scanData.execute_count || 0 }}</span>
      </div>
      <button class="btn-refresh" @click="loadData" :disabled="loading">
        {{ loading ? '加载中...' : '刷新' }}
      </button>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="loading">加载中...</div>

    <!-- 无数据 -->
    <div v-else-if="!scanData.results || scanData.results.length === 0" class="empty">
      <p>尚无扫描结果</p>
      <p class="hint">请先运行：<code>.venv/bin/python scripts/scan_pool.py</code></p>
    </div>

    <!-- 数据表格 -->
    <div v-else class="table-container">
      <table class="watchlist-table">
        <thead>
          <tr>
            <th>股票</th>
            <th>分类</th>
            <th>季节</th>
            <th>最新信号</th>
            <th>评分</th>
            <th>决策</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in sortedResults" :key="row.code"
              :class="`row-${row.final_signal}`"
              @click="goAnalyze(row)">
            <td class="td-name">
              <span class="stock-name">{{ row.name || row.code }}</span>
              <span class="stock-code">{{ row.code }}</span>
            </td>
            <td>
              <span class="cat-badge" :class="`cat-${row.category}`">
                {{ row.category_label || row.category || '?' }}
              </span>
              <span v-if="row.is_long_term" class="tree-icon">🌳</span>
            </td>
            <td>
              <span :class="`season-badge season-${scanData.season}`">
                {{ seasonLabel(scanData.season) }}
              </span>
            </td>
            <td>
              <span v-if="row.latest_signal" :class="`sig-${row.latest_signal.is_buy ? 'buy' : 'sell'}`">
                {{ signalLabel(row.latest_signal.signal_type) }}
              </span>
              <span v-else class="sig-none">无</span>
            </td>
            <td class="td-score">
              <span v-if="row.score">{{ row.score.total }}</span>
              <span v-else>-</span>
            </td>
            <td>
              <span class="action-badge" :class="`action-${row.final_signal}`">
                {{ actionLabel(row.final_signal) }}
              </span>
            </td>
            <td class="td-reason">
              <span v-if="row.reminder" class="reminder-text">🌳 {{ row.reminder.substring(0, 40) }}...</span>
              <span v-else>{{ (row.final_reason || '').substring(0, 50) }}</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 可操作信号汇总 -->
    <div v-if="executeSignals.length > 0" class="execute-summary">
      <h3>🎯 可操作信号（{{ executeSignals.length }} 只）</h3>
      <div v-for="row in executeSignals" :key="row.code" class="execute-card"
           :class="`card-${row.final_signal}`"
           @click="goAnalyze(row)">
        <div class="card-header">
          <span class="card-name">{{ row.name || row.code }}</span>
          <span class="cat-badge" :class="`cat-${row.category}`">{{ row.category_label }}</span>
          <span class="action-badge" :class="`action-${row.final_signal}`">
            {{ actionLabel(row.final_signal) }}
          </span>
        </div>
        <div class="card-detail">
          <span>信号: {{ signalLabel(row.latest_signal?.signal_type) }}</span>
          <span>评分: {{ row.score?.total || '-' }}</span>
          <span v-if="row.is_long_term">🌳 长期持有</span>
        </div>
        <div class="card-reason">{{ row.final_reason }}</div>
        <div v-if="row.reminder" class="card-reminder">🌳 {{ row.reminder }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const loading = ref(false)
const scanData = ref<any>({})

const loadData = async () => {
  loading.value = true
  try {
    const resp = await fetch('/api/v1/hybrid/watchlist')
    scanData.value = await resp.json()
  } catch (e) {
    console.error('加载失败', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => loadData())

const sortedResults = computed(() => {
  const results = scanData.value.results || []
  // execute 排最前，然后 observe，最后 reject
  const order = { execute: 0, observe: 1, reject: 2 }
  return [...results].sort((a, b) => {
    const oa = order[a.final_signal as keyof typeof order] ?? 3
    const ob = order[b.final_signal as keyof typeof order] ?? 3
    return oa - ob
  })
})

const executeSignals = computed(() =>
  (scanData.value.results || []).filter((r: any) => r.final_signal === 'execute')
)

const seasonLabel = (s: string) => ({
  spring: '春·播种', summer: '夏·生长', autumn: '秋·收获',
  winter: '冬·休眠', unknown: '未知',
}[s] || s)

const signalLabel = (t: string) => ({
  buy_1: '1买', buy_2: '2买', buy_3: '3买',
  sell_1: '1卖', sell_2: '2卖', sell_3: '3卖',
}[t] || t)

const actionLabel = (a: string) => ({
  execute: '✅ 执行', observe: '👀 观察', reject: '❌ 忽略',
}[a] || a)

const goAnalyze = (row: any) => {
  router.push({ path: '/hybrid', query: { code: row.code, market: row.market } })
}
</script>

<style scoped>
.watchlist-view {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}
.subtitle {
  color: #888;
  font-size: 13px;
  margin-bottom: 16px;
}
.status-bar {
  display: flex;
  gap: 24px;
  align-items: center;
  padding: 12px 20px;
  background: #1a1a2e;
  border-radius: 8px;
  margin-bottom: 16px;
}
.status-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.status-label {
  font-size: 11px;
  color: #666;
}
.status-value {
  font-size: 14px;
  font-weight: bold;
  color: #ddd;
}
.execute-count {
  color: #4ade80;
  font-size: 18px;
}
.btn-refresh {
  margin-left: auto;
  padding: 6px 20px;
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
}
.btn-refresh:hover { background: #1d4ed8; }
.btn-refresh:disabled { opacity: 0.5; cursor: not-allowed; }

.loading, .empty {
  text-align: center;
  padding: 40px;
  color: #666;
}
.empty .hint {
  font-size: 12px;
  margin-top: 8px;
}
.empty code {
  background: #1a1a2e;
  padding: 2px 8px;
  border-radius: 4px;
  color: #4ade80;
}

.table-container {
  overflow-x: auto;
}
.watchlist-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.watchlist-table th {
  text-align: left;
  padding: 10px 12px;
  background: #16213e;
  color: #888;
  font-weight: normal;
  border-bottom: 2px solid #333;
  white-space: nowrap;
}
.watchlist-table td {
  padding: 8px 12px;
  border-bottom: 1px solid #1a1a2e;
  color: #ccc;
}
.watchlist-table tr:hover {
  background: #16213e;
  cursor: pointer;
}
.row-execute { background: rgba(74, 222, 128, 0.05); }
.row-execute:hover { background: rgba(74, 222, 128, 0.1); }

.td-name { white-space: nowrap; }
.stock-name { font-weight: bold; color: #eee; }
.stock-code { color: #666; font-size: 11px; margin-left: 6px; }
.td-score { text-align: center; font-weight: bold; }
.td-reason { max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.cat-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 12px;
  font-weight: bold;
}
.cat-tree { background: #166534; color: #4ade80; }
.cat-grain { background: #78350f; color: #fbbf24; }
.cat-vegetable { background: #1e3a8a; color: #60a5fa; }
.tree-icon { margin-left: 4px; }

.season-badge { font-size: 12px; }
.season-spring { color: #4ade80; }
.season-summer { color: #fbbf24; }
.season-autumn { color: #f97316; }
.season-winter { color: #60a5fa; }

.sig-buy { color: #f87171; font-weight: bold; }
.sig-sell { color: #60a5fa; font-weight: bold; }
.sig-none { color: #555; }

.action-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 3px;
  font-size: 12px;
  font-weight: bold;
  white-space: nowrap;
}
.action-execute { background: #166534; color: #4ade80; }
.action-observe { background: #78350f; color: #fbbf24; }
.action-reject { background: #1a1a2e; color: #555; }

.reminder-text { color: #4ade80; }

.execute-summary {
  margin-top: 24px;
}
.execute-summary h3 {
  color: #4ade80;
  margin-bottom: 12px;
}
.execute-card {
  padding: 14px 18px;
  background: #1a1a2e;
  border-left: 4px solid #4ade80;
  border-radius: 4px;
  margin-bottom: 10px;
  cursor: pointer;
}
.execute-card:hover { background: #16213e; }
.card-header {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 6px;
}
.card-name {
  font-weight: bold;
  color: #eee;
  font-size: 15px;
}
.card-detail {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #888;
  margin-bottom: 4px;
}
.card-reason {
  font-size: 13px;
  color: #ccc;
}
.card-reminder {
  font-size: 12px;
  color: #4ade80;
  margin-top: 6px;
  padding: 6px 10px;
  background: rgba(74, 222, 128, 0.05);
  border-radius: 3px;
}
</style>
