<script setup lang="ts">
// 错题复习（V426）：列出用户答错的买卖点判断题，含正确解读。
import { onMounted, ref } from 'vue'
import { formatError } from '../api'

interface Mistake {
  id: number
  symbol: string
  category: string
  difficulty: string
  question_date: string | null
  signal_type: string
  user_choice: string
  actual: string
  explanation: string
}

const player = ref('学员')
const mistakes = ref<Mistake[]>([])
const loading = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const resp = await fetch(`/api/v1/learn/mistakes?player=${encodeURIComponent(player.value)}`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const d = await resp.json()
    mistakes.value = d.items ?? []
  } catch (e) {
    error.value = formatError(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="mistakes-panel">
    <div class="mistakes-head">
      <h3>📝 错题复习（{{ mistakes.length }} 道）</h3>
      <input v-model="player" class="player-input" placeholder="学员名" @change="load" />
      <button class="ghost" @click="load" :disabled="loading">
        {{ loading ? '加载中…' : '🔄 刷新' }}
      </button>
    </div>

    <div v-if="error" class="error-banner">⚠ {{ error }}</div>

    <div v-if="mistakes.length === 0" class="mistakes-empty">
      暂无错题。答错的买卖点判断会自动记录到这里。
    </div>

    <div v-else class="mistakes-list">
      <div v-for="m in mistakes" :key="m.id" class="mistake-item">
        <div class="mistake-meta">
          <span class="mistake-symbol">{{ m.symbol }} · {{ m.category }} · {{ m.difficulty }}</span>
          <span class="mistake-date">{{ m.question_date }}</span>
        </div>
        <div class="mistake-choice">
          你的判断 <b>{{ m.user_choice }}</b
          >，实际 <b>{{ m.actual }}</b
          >（{{ m.signal_type }}）
        </div>
        <div v-if="m.explanation" class="mistake-explanation">💡 {{ m.explanation }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mistakes-panel {
  padding: 16px;
}
.mistakes-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.mistakes-head h3 {
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
.mistakes-empty {
  color: #94a3b8;
  padding: 24px;
  text-align: center;
}
.mistakes-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.mistake-item {
  border: 1px solid #2a2e3a;
  border-radius: 6px;
  padding: 10px;
}
.mistake-meta {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}
.mistake-symbol {
  font-family: monospace;
  color: #60a5fa;
  font-size: 12px;
}
.mistake-date {
  color: #94a3b8;
  font-size: 11px;
}
.mistake-choice {
  color: #e5e7eb;
  font-size: 13px;
  margin-bottom: 6px;
}
.mistake-explanation {
  color: #cbd5e1;
  font-size: 12px;
  line-height: 1.6;
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
