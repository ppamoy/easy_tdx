<script setup lang="ts">
// 单篇缠论概念讲解卡（V420）：标题 + 定义 + 判定规则 + 图例说明。
import type { Lesson } from '../content/lessons'

defineProps<{ lesson: Lesson }>()
</script>

<template>
  <article class="lesson-card">
    <header class="lesson-head">
      <h2 class="lesson-title">{{ lesson.title }}</h2>
      <span class="lesson-subtitle">{{ lesson.subtitle }}</span>
    </header>
    <section class="lesson-section">
      <h3>定义</h3>
      <p class="lesson-def">{{ lesson.definition }}</p>
    </section>
    <section class="lesson-section">
      <h3>判定规则</h3>
      <ul class="lesson-rules">
        <li v-for="(r, i) in lesson.rules" :key="i">{{ r }}</li>
      </ul>
    </section>
    <section class="lesson-section diagram">
      <h3>图表标注</h3>
      <p class="lesson-diagram">{{ lesson.diagramNote }}</p>
    </section>
  </article>
</template>

<style scoped>
.lesson-card {
  border: 1px solid #2a2e3a;
  border-radius: 8px;
  padding: 20px;
}
.lesson-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 16px;
}
.lesson-title {
  margin: 0;
  font-size: 20px;
}
.lesson-subtitle {
  color: #94a3b8;
  font-size: 13px;
}
.lesson-section {
  margin-bottom: 16px;
}
.lesson-section h3 {
  font-size: 14px;
  color: #60a5fa;
  margin: 0 0 8px;
}
.lesson-def {
  line-height: 1.7;
  color: #e5e7eb;
}
.lesson-rules {
  padding-left: 18px;
  line-height: 1.8;
  color: #cbd5e1;
}
.lesson-diagram {
  color: #fbbf24;
  line-height: 1.6;
}
</style>
