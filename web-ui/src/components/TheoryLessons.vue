<script setup lang="ts">
// 理论教学页（V420）：概念列表（已读标记）+ 上一篇/下一篇顺序学习。
import { computed, ref } from 'vue'
import LessonCard from '../components/LessonCard.vue'
import { LESSONS } from '../content/lessons'

const READ_KEY = 'chanlun.lesson.read'

const currentIdx = ref(0)
const readIds = ref<Set<string>>(new Set(loadRead()))

function loadRead(): string[] {
  try {
    return JSON.parse(localStorage.getItem(READ_KEY) ?? '[]') as string[]
  } catch {
    return []
  }
}

function persistRead() {
  localStorage.setItem(READ_KEY, JSON.stringify([...readIds.value]))
}

const current = computed(() => LESSONS[currentIdx.value])

function select(idx: number) {
  currentIdx.value = idx
  markRead(idx)
}

function markRead(idx: number) {
  readIds.value.add(LESSONS[idx].id)
  persistRead()
}

function prev() {
  if (currentIdx.value > 0) select(currentIdx.value - 1)
}
function next() {
  if (currentIdx.value < LESSONS.length - 1) select(currentIdx.value + 1)
}

function isRead(id: string): boolean {
  return readIds.value.has(id)
}
</script>

<template>
  <div class="theory-layout">
    <aside class="lesson-nav">
      <div class="nav-head">概念目录（{{ LESSONS.length }} 篇）</div>
      <div
        v-for="(l, i) in LESSONS"
        :key="l.id"
        class="nav-item"
        :class="{ active: i === currentIdx, read: isRead(l.id) }"
        @click="select(i)"
      >
        <span class="nav-idx">{{ i + 1 }}</span>
        <span class="nav-title">{{ l.title }}</span>
        <span v-if="isRead(l.id)" class="nav-read">✓</span>
      </div>
    </aside>

    <main class="lesson-main">
      <LessonCard v-if="current" :lesson="current" />
      <div class="lesson-pager">
        <button class="ghost" :disabled="currentIdx === 0" @click="prev">← 上一篇</button>
        <span class="pager-pos">{{ currentIdx + 1 }} / {{ LESSONS.length }}</span>
        <button class="ghost" :disabled="currentIdx === LESSONS.length - 1" @click="next">
          下一篇 →
        </button>
      </div>
    </main>
  </div>
</template>

<style scoped>
.theory-layout {
  display: flex;
  gap: 12px;
}
.lesson-nav {
  width: 220px;
  flex-shrink: 0;
  border: 1px solid #2a2e3a;
  border-radius: 8px;
  overflow: hidden;
}
.nav-head {
  padding: 8px 12px;
  font-weight: 600;
  border-bottom: 1px solid #2a2e3a;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
}
.nav-item:hover {
  background: #1f2937;
}
.nav-item.active {
  background: #1e3a5f;
}
.nav-item.read {
  opacity: 0.85;
}
.nav-idx {
  color: #60a5fa;
  font-family: monospace;
}
.nav-title {
  flex: 1;
}
.nav-read {
  color: #22c55e;
}
.lesson-main {
  flex: 1;
  min-width: 0;
}
.lesson-pager {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}
.pager-pos {
  color: #94a3b8;
}
button.ghost {
  background: transparent;
  border: 1px solid #2a2e3a;
  color: #e5e7eb;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
}
button.ghost:disabled {
  opacity: 0.4;
  cursor: default;
}
button.ghost:not(:disabled):hover {
  background: #1f2937;
}
</style>
