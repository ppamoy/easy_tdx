import { createRouter, createWebHistory } from 'vue-router'

import BacktestView from './views/BacktestView.vue'
import ChanlunView from './views/ChanlunView.vue'
import TrainView from './views/TrainView.vue'
import ChangyingView from './views/ChangyingView.vue'
import CompareView from './views/CompareView.vue'
import DiagnosisView from './views/DiagnosisView.vue'
import MonitorView from './views/MonitorView.vue'
import OptimizeView from './views/OptimizeView.vue'
import PortfolioView from './views/PortfolioView.vue'
import ScreeningView from './views/ScreeningView.vue'
import FundamentalView from './views/FundamentalView.vue'
import ServerSettingsView from './views/ServerSettingsView.vue'
import StrategiesView from './views/StrategiesView.vue'

// 单标的回测（/）+ 缠论分析（/chanlun）+ 长赢投资（/changying）+ 动态选股（/screening）+ 组合回测（/portfolio）+ 参数寻优（/optimize）+ 结果对比（/compare）+ 策略库（/strategies）+ 服务器设置（/settings）+ 信号监控（/monitor）+ 技术诊断（/diagnosis）。
const routes = [
  { path: '/', name: 'backtest', component: BacktestView },
  { path: '/chanlun', name: 'chanlun', component: ChanlunView },
  { path: '/train', name: 'train', component: TrainView },
  { path: '/changying', name: 'changying', component: ChangyingView },
  { path: '/screening', name: 'screening', component: ScreeningView },
  { path: '/fundamental', name: 'fundamental', component: FundamentalView },
  { path: '/portfolio', name: 'portfolio', component: PortfolioView },
  { path: '/optimize', name: 'optimize', component: OptimizeView },
  { path: '/compare', name: 'compare', component: CompareView },
  { path: '/strategies', name: 'strategies', component: StrategiesView },
  { path: '/settings', name: 'settings', component: ServerSettingsView },
  { path: '/monitor', name: 'monitor', component: MonitorView },
  { path: '/diagnosis', name: 'diagnosis', component: DiagnosisView },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
