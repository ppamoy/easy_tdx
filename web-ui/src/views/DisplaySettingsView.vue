<script setup lang="ts">
// 显示设置页面：涨跌配色（红涨绿跌 ↔ 绿涨红跌）等全局外观偏好。
// 配色状态为响应式 ref（colors.ts），切换后立即生效并持久化到 localStorage，
// 所有 ECharts 图表（K线/缠论/长赢）与涨跌色文本随之重渲染。
import { computed } from 'vue'
import { colorScheme, downColor, setColorScheme, upColor } from '../colors'
import type { ColorScheme } from '../colors'

const options: { value: ColorScheme; label: string; desc: string }[] = [
  { value: 'red-up', label: '红涨绿跌', desc: 'A 股惯例：上涨为红，下跌为绿' },
  { value: 'green-up', label: '绿涨红跌', desc: '国际惯例：上涨为绿，下跌为红' },
]

const current = computed(() => colorScheme.value)

function pick(s: ColorScheme) {
  setColorScheme(s)
}
</script>

<template>
  <div class="display-settings">
    <h2>显示设置</h2>
    <p class="hint">涨跌配色影响全局所有 K 线图与涨跌数值，切换后即时生效并记住偏好。</p>

    <section class="card">
      <h3>涨跌配色</h3>
      <div class="scheme-options">
        <button
          v-for="opt in options"
          :key="opt.value"
          class="scheme-option"
          :class="{ active: current === opt.value }"
          @click="pick(opt.value)"
        >
          <div class="scheme-label">{{ opt.label }}</div>
          <div class="scheme-desc">{{ opt.desc }}</div>
          <!-- K 线预览：两阳一阴 -->
          <div class="candle-preview">
            <span class="candle up">
              <i class="body" :style="{ background: upColor, borderColor: upColor }"></i>
            </span>
            <span class="candle up">
              <i class="body" :style="{ background: upColor, borderColor: upColor }"></i>
            </span>
            <span class="candle down">
              <i class="body" :style="{ background: downColor, borderColor: downColor }"></i>
            </span>
          </div>
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.display-settings {
  max-width: 720px;
  margin: 0 auto;
  padding: 24px 16px 48px;
}
.display-settings h2 {
  margin: 0 0 8px;
  color: #e6e8eb;
}
.hint {
  margin: 0 0 24px;
  color: #8b919e;
  font-size: 14px;
}
.card {
  background: #1a1d24;
  border: 1px solid #2a2e3a;
  border-radius: 10px;
  padding: 20px;
}
.card h3 {
  margin: 0 0 16px;
  color: #e6e8eb;
  font-size: 16px;
}
.scheme-options {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.scheme-option {
  flex: 1 1 240px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 18px 16px;
  background: #14171d;
  border: 2px solid #2a2e3a;
  border-radius: 8px;
  cursor: pointer;
  color: #c9ced6;
  transition: border-color 0.15s, background 0.15s;
  font: inherit;
}
.scheme-option:hover {
  border-color: #3a4050;
  background: #181b22;
}
.scheme-option.active {
  border-color: #3b82f6;
  background: #0f1a2e;
}
.scheme-label {
  font-size: 16px;
  font-weight: 600;
  color: #e6e8eb;
}
.scheme-desc {
  font-size: 12px;
  color: #8b919e;
}
.candle-preview {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 56px;
  margin-top: 6px;
}
.candle {
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
  justify-content: flex-end;
}
.candle .body {
  display: block;
  width: 16px;
  height: 34px;
  border-radius: 2px;
}
.candle.up .body {
  height: 44px;
}
.candle.down .body {
  height: 26px;
}
</style>
