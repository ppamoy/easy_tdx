<script setup lang="ts">
// 缠论学习页容器（V420）：理论教学 / 盘感训练 / 学习中心。
// D1：TrainView 训练核心复用为子组件，不重写；学习中心 Phase 5 接入。
import { ref } from 'vue'
import TheoryLessons from '../components/TheoryLessons.vue'
import ProgressDashboard from '../components/ProgressDashboard.vue'
import MistakesReview from '../components/MistakesReview.vue'
import TrainView from './TrainView.vue'

const tab = ref<'theory' | 'train' | 'center'>('theory')
</script>

<template>
  <div class="learn-view">
    <div class="learn-tabs">
      <button :class="['tab', { active: tab === 'theory' }]" @click="tab = 'theory'">
        📚 理论教学
      </button>
      <button :class="['tab', { active: tab === 'train' }]" @click="tab = 'train'">
        🎯 盘感训练
      </button>
      <button :class="['tab', { active: tab === 'center' }]" @click="tab = 'center'">
        📊 学习中心
      </button>
    </div>

    <TheoryLessons v-if="tab === 'theory'" />
    <TrainView v-else-if="tab === 'train'" />
    <div v-else class="center-stack">
      <ProgressDashboard />
      <MistakesReview />
    </div>
  </div>
</template>

<style scoped>
.learn-view {
  padding: 16px;
}
.learn-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  border-bottom: 1px solid #2a2e3a;
  padding-bottom: 8px;
}
.tab {
  background: transparent;
  border: none;
  color: #94a3b8;
  padding: 8px 14px;
  cursor: pointer;
  font-size: 14px;
}
.tab.active {
  color: #e5e7eb;
  font-weight: 600;
  border-bottom: 2px solid #2563eb;
}
.center-placeholder {
  color: #94a3b8;
  padding: 40px;
  text-align: center;
}
.center-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
