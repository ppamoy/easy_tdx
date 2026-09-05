<script setup lang="ts">
// 学习进度面板（V424）：掌握度矩阵——按周期×难度统计命中率/题数。
import { computed, onMounted, ref } from 'vue'
import { formatError } from '../api'

const player = ref('学员')
const matrix = ref<
  Record<string, Record<string, { rounds: number; total_asked: number; hit_rate: number }>>
>({})
const loading = ref(false)
const error = ref('')

const CATEGORIES = ['DAY', 'WEEK', 'MIN_5', 'MIN_15', 'MIN_30', 'MIN_60']
const DIFFICULTIES = ['easy', 'medium', 'hard'] as const

const hasData = computed(() => Object.keys(matrix.value).length > 0)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const resp = await fetch(`/api/v1/learn/progress?player=${encodeURIComponent(player.value)}`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const d = await resp.json()
    matrix.value = d.matrix ?? {}
  } catch (e) {
    error.value = formatError(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="progress-panel">
    <div class="progress-head">
      <h3>📊 学习进度（掌握度矩阵）</h3>
      <input v-model="player" class="player-input" placeholder="学员名" @change="load" />
      <button class="ghost" @click="load" :disabled="loading">
        {{ loading ? '加载中…' : '🔄 刷新' }}
      </button>
    </div>

    <div v-if="error" class="error-banner">⚠ {{ error }}</div>

    <div v-if="!hasData" class="progress-empty">
      暂无学习记录。完成一次「逐步揭示训练」后这里会显示各周期×难度的命中率。
    </div>

    <table v-else class="matrix-table">
      <thead>
        <tr>
          <th>周期 \\ 难度</th>
          <th v-for="d in DIFFICULTIES" :key="d">{{ d }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="cat in CATEGORIES" :key="cat">
          <td class="cat-cell">{{ cat }}</td>
          <td v-for="d in DIFFICULTIES" :key="d">
            <div v-if="matrix[cat]?.[d]" class="cell">
              <div class="hit">{{ matrix[cat][d].hit_rate }}%</div>
              <div class="asked">{{ matrix[cat][d].total_asked }} 题</div>
            </div>
            <div v-else class="cell empty">—</div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.progress-panel {
  padding: 16px;
}
.progress-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.progress-head h3 {
  margin: 0;
}
.player-input {
  background: #111827;
  border: 1px solid #2a2e3a;
  color: #e5e7eb;
  padding: 6px 10px;
  border-radius: 6px;
}
.error-banner {
  background: #7f1d1d;
  color: #fecaca;
  padding: 8px 12px;
  border-radius: 6px;
  margin-bottom: 12px;
}
.progress-empty {
  color: #94a3b8;
  padding: 24px;
  text-align: center;
}
.matrix-table {
  width: 100%;
  border-collapse: collapse;
}
.matrix-table th,
.matrix-table td {
  border: 1px solid #2a2e3a;
  padding: 8px 12px;
  text-align: center;
}
.matrix-table th {
  color: #94a3b8;
  font-weight: 500;
}
.cat-cell {
  font-family: monospace;
  color: #60a5fa;
}
.cell .hit {
  font-size: 16px;
  font-weight: 700;
  color: #22c55e;
}
.cell .asked {
  font-size: 11px;
  color: #94a3b8;
}
.cell.empty {
  color: #6b7280;
}
button.ghost {
  background: transparent;
  border: 1px solid #2a2e3a;
  color: #e5e7eb;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
}
button.ghost:hover {
  background: #1f2937;
}
</style>
