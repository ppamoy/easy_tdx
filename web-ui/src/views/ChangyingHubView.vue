<script setup lang="ts">
// 长赢投资 hub（V853）：把散落的 3 个长赢 view 收拢为单入口 3 tab，
// 与 LearnView（缠论 hub）同构。不改动 3 个子 view 内部，仅 tab 包装。
// 对齐 docs/PRODUCT_REQUIREMENTS.md P1：历史时点基本面选股（核心）+ 四季树粮菜概览 + 融合信号。
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import ChangyingView from './ChangyingView.vue'
import FundamentalView from './FundamentalView.vue'
import HybridView from './HybridView.vue'

type Tab = 'select' | 'overview' | 'fusion'

const route = useRoute()
const initial = (['select', 'overview', 'fusion'] as Tab[]).includes(
  route.query.tab as Tab,
)
  ? (route.query.tab as Tab)
  : 'select' // 默认历史时点选股（P1 核心）
const tab = ref<Tab>(initial)
</script>

<template>
  <div class="changying-hub">
    <div class="hub-tabs">
      <button :class="['tab', { active: tab === 'select' }]" @click="tab = 'select'">
        📊 历史时点选股
      </button>
      <button :class="['tab', { active: tab === 'overview' }]" @click="tab = 'overview'">
        🌱 投资概览（四季·树粮菜）
      </button>
      <button :class="['tab', { active: tab === 'fusion' }]" @click="tab = 'fusion'">
        🔗 融合信号（树粮菜+缠论）
      </button>
    </div>

    <FundamentalView v-if="tab === 'select'" />
    <ChangyingView v-else-if="tab === 'overview'" />
    <HybridView v-else-if="tab === 'fusion'" />
  </div>
</template>

<style scoped>
.changying-hub {
  padding: 16px;
}
.hub-tabs {
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
</style>
