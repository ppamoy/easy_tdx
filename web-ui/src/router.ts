import { createRouter, createWebHistory } from 'vue-router'

import AuditView from './views/AuditView.vue'
import BacktestView from './views/BacktestView.vue'
import ChangyingView from './views/ChangyingView.vue'
import CompareView from './views/CompareView.vue'
import DataCacheView from './views/DataCacheView.vue'
import DiagnosisView from './views/DiagnosisView.vue'
import MonitorView from './views/MonitorView.vue'
import OptimizeView from './views/OptimizeView.vue'
import PortfolioView from './views/PortfolioView.vue'
import ScreeningView from './views/ScreeningView.vue'
import FundamentalView from './views/FundamentalView.vue'
import ServerSettingsView from './views/ServerSettingsView.vue'
import DisplaySettingsView from './views/DisplaySettingsView.vue'
import StrategiesView from './views/StrategiesView.vue'
import LearnView from './views/LearnView.vue'
import StockPickView from './views/StockPickView.vue'
import TodayView from './views/TodayView.vue'
import SignalCheckView from './views/SignalCheckView.vue'
import HybridView from './views/HybridView.vue'
import WatchlistView from './views/WatchlistView.vue'
import PickView from './views/PickView.vue'

// 单标的回测（/）+ 缠论分析（/chanlun）+ 长赢投资（/changying）+ 动态选股（/screening）+ 组合回测（/portfolio）+ 参数寻优（/optimize）+ 结果对比（/compare）+ 策略库（/strategies）+ 服务器设置（/settings）+ 信号监控（/monitor）+ 技术诊断（/diagnosis）+ 吴伟志+缠论融合（/hybrid）。
const routes = [
  { path: '/', name: 'backtest', component: BacktestView },
  { path: '/hybrid', name: 'hybrid', component: HybridView },
  { path: '/watchlist', name: 'watchlist', component: WatchlistView },
  { path: '/chanlun', redirect: { path: '/learn', query: { tab: 'analysis' } } },
  { path: '/train', redirect: { path: '/learn', query: { tab: 'train' } } },
  { path: '/changying', name: 'changying', component: ChangyingView },
  { path: '/screening', name: 'screening', component: ScreeningView },
  { path: '/fundamental', name: 'fundamental', component: FundamentalView },
  { path: '/portfolio', name: 'portfolio', component: PortfolioView },
  { path: '/optimize', name: 'optimize', component: OptimizeView },
  { path: '/compare', name: 'compare', component: CompareView },
  { path: '/strategies', name: 'strategies', component: StrategiesView },
  { path: '/settings', name: 'settings', component: ServerSettingsView },
  { path: '/display-settings', name: 'display-settings', component: DisplaySettingsView },
  { path: '/monitor', name: 'monitor', component: MonitorView },
  { path: '/diagnosis', name: 'diagnosis', component: DiagnosisView },
  { path: '/verify', redirect: { path: '/learn', query: { tab: 'verify' } } },
  { path: '/learn', name: 'learn', component: LearnView },
  { path: '/stock-pick', name: 'stock-pick', component: StockPickView },
  { path: '/today', name: 'today', component: TodayView },
  { path: '/audit', name: 'audit', component: AuditView },
  { path: '/signal-check', name: 'signal-check', component: SignalCheckView },
  { path: '/data-cache', name: 'data-cache', component: DataCacheView },
  { path: '/pick', name: 'pick', component: PickView },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
