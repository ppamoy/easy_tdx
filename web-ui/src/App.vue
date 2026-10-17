<script setup lang="ts">
// 根组件：顶部标题栏 + 分组主导航 + 路由出口 + 全局自选股面板。
// V853：扁平 8 项导航重构成分组导航，对齐 PRODUCT_REQUIREMENTS 两模块愿景
// （缠论学习回测 P0 + 长赢选股 P1）。路由全保留，仅改导航分组 + 软隐藏集合。
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

// 分组导航展示的路径集合（非此集合的页面显示软隐藏提示，但 URL 仍直达）。
// V853：分组后核心路径扩充——长赢选股(/fundamental)、今日可操作(/today)、
// 树粮菜融合(/hybrid)、缠论选股(/pick)、组合/寻优/对比/策略库/自选股看板 均入导航。
const route = useRoute()
const CORE_PATHS = [
  '/learn', '/', '/signal-check', // 缠论学习回测
  '/changying', '/today', // 长赢选股
  '/pick', // 选股
  '/portfolio', '/optimize', '/compare', '/strategies', '/watchlist', // 工具
]
// ⚠️ /stock-pick+/screening（已并入 /pick hub 的 tab）、/fundamental+/hybrid（已并入 /changying hub 的 tab）、
// /audit（与 /signal-check 重复，口径更旧）、/diagnosis、/monitor：软隐藏，
// URL 保留直达以免破坏书签；后续逐步并入对应模块。
const isSoftHidden = computed(
  () => !CORE_PATHS.some((p) => route.path === p || route.path.startsWith(p + '/')),
)

onMounted(() => document.addEventListener('keydown', handleKeydown))
onUnmounted(() => document.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <div class="app">
    <header class="app-header">
      <h1>easy-tdx</h1>
      <nav class="app-nav">
        <div class="nav-group">
          <span class="nav-label">缠论学习回测</span>
          <RouterLink to="/learn" active-class="active">缠论学习</RouterLink>
          <RouterLink to="/" active-class="active">单标的回测</RouterLink>
          <RouterLink to="/signal-check" active-class="active">买卖点核对</RouterLink>
        </div>
        <div class="nav-group">
          <span class="nav-label">长赢选股</span>
          <RouterLink to="/changying" active-class="active">长赢投资</RouterLink>
          <RouterLink to="/today" active-class="active">今日可操作</RouterLink>
          <RouterLink to="/trade" active-class="active">⚡ 实战交易</RouterLink>
        </div>
        <div class="nav-group">
          <span class="nav-label">选股</span>
          <RouterLink to="/pick" active-class="active">选股（缠论买点·长盈·动态）</RouterLink>
        </div>
        <div class="nav-group">
          <span class="nav-label">工具</span>
          <RouterLink to="/portfolio" active-class="active">组合</RouterLink>
          <RouterLink to="/optimize" active-class="active">寻优</RouterLink>
          <RouterLink to="/compare" active-class="active">对比</RouterLink>
          <RouterLink to="/strategies" active-class="active">策略库</RouterLink>
          <RouterLink to="/watchlist" active-class="active">自选股</RouterLink>
        </div>
      </nav>
    </header>
    <main class="app-main">
      <div v-if="isSoftHidden" class="soft-hidden-banner">
        该页已并入对应模块——缠论分析请用「缠论学习」，长赢/选股请用「长赢选股 / 缠论选股」
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
  gap: 20px;
  padding: 0 16px;
  min-height: 48px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  flex-wrap: wrap;
}
.app-header h1 {
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
}
.app-nav {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  align-items: center;
}
.nav-group {
  display: flex;
  align-items: center;
  gap: 6px;
}
.nav-group + .nav-group {
  border-left: 1px solid var(--border);
  padding-left: 18px;
}
.nav-label {
  color: var(--text-dim);
  font-size: 11px;
  opacity: 0.7;
  white-space: nowrap;
  margin-right: 2px;
}
.app-nav a {
  color: var(--text-dim);
  text-decoration: none;
  font-size: 13px;
  padding: 4px 2px;
  border-bottom: 2px solid transparent;
  white-space: nowrap;
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
  gap: 16px;
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
