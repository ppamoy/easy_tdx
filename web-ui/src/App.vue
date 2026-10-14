<script setup lang="ts">
// 根组件：顶部标题栏 + 三大主导航 + 路由出口 + 全局自选股面板。
// v590：主导航收敛为「回测 / 选股 / 缠论测试学习」，其余页面软隐藏，
// 服务器设置收敛到页脚齿轮入口。
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import WatchlistPanel from './components/WatchlistPanel.vue'

// 快捷键：Ctrl+Shift+W 切换自选股面板
function handleKeydown(e: KeyboardEvent) {
  if (e.ctrlKey && e.shiftKey && e.key === 'W') {
    e.preventDefault()
    const btn = document.querySelector('.watchlist-toggle') as HTMLButtonElement
    if (btn) btn.click()
  }
}

// 软隐藏旧页：主导航收敛后仍保留 URL 直达，但给非核心页一个非阻断提示。
const route = useRoute()
const CORE_PATHS = ['/', '/stock-pick', '/pick', '/learn', '/today', '/signal-check']
// ⚠️ 准确性审计（/audit）已从主导航移除：它的功能与 /signal-check 的
// 「准不准」面板重复，且口径更旧（无 Bonferroni 校正）。保留 URL 直达
// 以免破坏已有书签，但入口收敛到 5 个。
const isSoftHidden = computed(
  () => !CORE_PATHS.some((p) => route.path === p || route.path.startsWith(p)),
)

onMounted(() => document.addEventListener('keydown', handleKeydown))
onUnmounted(() => document.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <div class="app">
    <header class="app-header">
      <h1>easy-tdx</h1>
      <nav class="app-nav">
        <RouterLink to="/" active-class="active">回测</RouterLink>
        <RouterLink to="/stock-pick" active-class="active">选股</RouterLink>
        <RouterLink to="/pick" active-class="active">缠论选股</RouterLink>
        <RouterLink to="/hybrid" active-class="active">吴伟志+缠论</RouterLink>
        <RouterLink to="/watchlist" active-class="active">自选股看板</RouterLink>
        <RouterLink to="/today" active-class="active">今日可操作</RouterLink>
        <RouterLink to="/signal-check" active-class="active">买卖点核对</RouterLink>
        <RouterLink to="/learn" active-class="active">缠论测试学习</RouterLink>
      </nav>
    </header>
    <main class="app-main">
      <div v-if="isSoftHidden" class="soft-hidden-banner">
        该页已移出主导航，请从「回测 / 选股 / 缠论测试学习」使用核心功能
      </div>
      <RouterView />
    </main>
    <footer class="app-footer">
      <RouterLink to="/display-settings" class="settings-link" title="显示设置">🎨 显示设置</RouterLink>
      <RouterLink to="/settings" class="settings-link" title="服务器设置">⚙ 服务器设置</RouterLink>
      <RouterLink to="/data-cache" class="settings-link" title="K线数据缓存">📊 数据缓存</RouterLink>
    </footer>
    <WatchlistPanel />
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
}
.app-header {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 0 20px;
  height: 48px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.app-header h1 {
  font-size: 16px;
  font-weight: 600;
}
.app-nav {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}
.app-nav a {
  color: var(--text-dim);
  text-decoration: none;
  font-size: 13px;
  padding: 4px 0;
  border-bottom: 2px solid transparent;
}
.app-nav a:hover {
  color: var(--text);
}
.app-nav a.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}
.app-main {
  flex: 1;
  overflow: auto;
}
.soft-hidden-banner {
  margin: 8px 20px 0;
  padding: 8px 12px;
  font-size: 12px;
  color: #fbbf24;
  background: rgba(251, 191, 36, 0.08);
  border: 1px solid rgba(251, 191, 36, 0.25);
  border-radius: 4px;
}
.app-footer {
  flex-shrink: 0;
  padding: 4px 20px;
  border-top: 1px solid var(--border);
  background: var(--bg-panel);
  display: flex;
  justify-content: flex-end;
}
.settings-link {
  color: var(--text-dim);
  text-decoration: none;
  font-size: 12px;
}
.settings-link:hover {
  color: var(--accent);
}
</style>
