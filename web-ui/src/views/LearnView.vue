<!-- 缠论测试学习单页（v590）：5 个 Tab 合并。 -->
<script setup lang="ts">
// 缠论测试学习单页（v590）：看图分析 / 理论教学 / 盘感训练 / 买卖点实证 / 进度。
// 复用既有组件，不重写能力；支持 ?tab=analysis|theory|train|verify|progress 直达。
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import ChanlunView from './ChanlunView.vue'
import SignalVerifyView from './SignalVerifyView.vue'
import TheoryLessons from '../components/TheoryLessons.vue'
import ProgressDashboard from '../components/ProgressDashboard.vue'
import MistakesReview from '../components/MistakesReview.vue'
import TrainView from './TrainView.vue'

type Tab = 'analysis' | 'theory' | 'train' | 'verify' | 'progress'
const route = useRoute()
const initial = (['analysis', 'theory', 'train', 'verify', 'progress'] as Tab[]).includes(
  route.query.tab as Tab,
)
  ? (route.query.tab as Tab)
  : 'analysis'
const tab = ref<Tab>(initial)
</script>

<template>
  <div class="learn-view">
    <div class="learn-tabs">
      <button :class="['tab', { active: tab === 'analysis' }]" @click="tab = 'analysis'">
        📈 看图分析
      </button>
      <button :class="['tab', { active: tab === 'theory' }]" @click="tab = 'theory'">
        📚 理论教学
      </button>
      <button :class="['tab', { active: tab === 'train' }]" @click="tab = 'train'">
        🎯 盘感训练
      </button>
      <button :class="['tab', { active: tab === 'verify' }]" @click="tab = 'verify'">
        🔍 买卖点实证
      </button>
      <button :class="['tab', { active: tab === 'progress' }]" @click="tab = 'progress'">
        📊 进度
      </button>
    </div>

    <ChanlunView v-if="tab === 'analysis'" />
    <TheoryLessons v-else-if="tab === 'theory'" />
    <TrainView v-else-if="tab === 'train'" />
    <SignalVerifyView v-else-if="tab === 'verify'" />
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
  flex-wrap: wrap;
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
.center-stack {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
