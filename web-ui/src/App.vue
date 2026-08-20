<script setup lang="ts">
// 根组件：顶部标题栏 + 路由出口 + 全局自选股面板。
import { onMounted, onUnmounted } from 'vue'
import WatchlistPanel from './components/WatchlistPanel.vue'

// 快捷键：Ctrl+Shift+W 切换自选股面板
function handleKeydown(e: KeyboardEvent) {
  if (e.ctrlKey && e.shiftKey && e.key === 'W') {
    e.preventDefault()
    const btn = document.querySelector('.watchlist-toggle') as HTMLButtonElement
    if (btn) btn.click()
  }
}

onMounted(() => document.addEventListener('keydown', handleKeydown))
onUnmounted(() => document.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <div class="app">
    <header class="app-header">
      <h1>easy-tdx 回测</h1>
      <nav class="app-nav">
        <RouterLink to="/" active-class="active">单标的回测</RouterLink>
        <RouterLink to="/chanlun" active-class="active">缠论分析</RouterLink>
        <RouterLink to="/changying" active-class="active">长赢投资</RouterLink>
        <RouterLink to="/screening" active-class="active">动态选股</RouterLink>
        <RouterLink to="/portfolio" active-class="active">组合回测</RouterLink>
        <RouterLink to="/optimize" active-class="active">参数寻优</RouterLink>
        <RouterLink to="/compare" active-class="active">结果对比</RouterLink>
        <RouterLink to="/strategies" active-class="active">策略库</RouterLink>
        <RouterLink to="/settings" active-class="active">服务器设置</RouterLink>
        <RouterLink to="/monitor" active-class="active">信号监控</RouterLink>
        <RouterLink to="/diagnosis" active-class="active">技术诊断</RouterLink>
      </nav>
    </header>
    <main class="app-main">
      <RouterView />
    </main>
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
  overflow: hidden;
}
</style>
