<script setup lang="ts">
// 选股 hub（V853）：把散落的 3 个选股 view 收拢为单入口 3 tab，
// 与 ChangyingHubView / LearnView 同构。不改动子 view 内部，仅 tab 包装。
// 对齐 docs/PRODUCT_REQUIREMENTS.md：缠论买点选股 + 长盈基本面两步 + 动态选股回测。
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import PickView from './PickView.vue'
import StockPickView from './StockPickView.vue'
import ScreeningView from './ScreeningView.vue'

type Tab = 'buy' | 'twostep' | 'dynback'

const route = useRoute()
const initial = (['buy', 'twostep', 'dynback'] as Tab[]).includes(route.query.tab as Tab)
  ? (route.query.tab as Tab)
  : 'buy' // 默认缠论买点（保留原 /pick 行为，最少惊讶）
const tab = ref<Tab>(initial)
</script>

<template>
  <div class="pick-hub">
    <div class="hub-tabs">
      <button :class="['tab', { active: tab === 'buy' }]" @click="tab = 'buy'">
        🎯 缠论买点（按日期+级别）
      </button>
      <button :class="['tab', { active: tab === 'twostep' }]" @click="tab = 'twostep'">
        📊 长盈基本面+缠论（两步流）
      </button>
      <button :class="['tab', { active: tab === 'dynback' }]" @click="tab = 'dynback'">
        ⏳ 动态选股+缠论回测
      </button>
    </div>

    <PickView v-if="tab === 'buy'" />
    <StockPickView v-else-if="tab === 'twostep'" />
    <ScreeningView v-else-if="tab === 'dynback'" />
  </div>
</template>

<style scoped>
.pick-hub {
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
