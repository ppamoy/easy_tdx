# 前端 IA 重整方案（V853，待用户确认）

> 判据：`docs/PRODUCT_REQUIREMENTS.md` 两模块愿景（缠论学习回测 P0 + 长赢选股 P1）。
> 现状：`web-ui/src/router.ts` **24 条扁平路由、零分组**，选股 5 个重叠 view、长赢散在 3 个、缠论散在 6 个——用户反馈"很乱、不是我想要的"。
> 本方案先映射现状→两模块、点出冗余/孤儿，再提合并后的 IA，**待你确认后再动手**。

## 1. 现状映射（每条路由扫了页面用途）

### 模块一：缠论学习回测（P0）相关 —— 散在 6 个 view
| 路由 | view | 用途（grep 实测） | 处置建议 |
|---|---|---|---|
| `/learn` | LearnView | 学习 hub（analysis/train/verify 三 tab）| **保留为主入口** |
| `/` | BacktestView | 单标的回测（含缠论图 + 买卖点）| 并入 LearnView?analysis 或作"实盘/回测"独立入口 |
| `/audit` | AuditView | 模型准确性审计（长盈三维分层）| 并入"验证"区（P0 的"验证准确性"） |
| `/diagnosis` | DiagnosisView | 技术诊断（输入→结果） | 并入 analysis tab 的"诊断"子区 |
| `/signal-check` | SignalCheckView | 买卖点核对（最新买卖点提示） | 并入 analysis tab 或 verify tab |
| `/monitor` | MonitorView | 信号监控（股票列表+历史准确度） | 并入 verify tab 或独立"监控" |

### 模块二：长赢选股（P1）相关 —— 散在 3 + 5 个 view
| 路由 | view | 用途 | 处置建议 |
|---|---|---|---|
| `/fundamental` | FundamentalView | **P1/P2 长赢基本面选股**（单日+批量时点+全市场）| **保留为长赢主入口** |
| `/changying` | ChangyingView | 长赢投资（四季周期卡片+树粮菜概念） | 并入 FundamentalView 作"当前季节"面板 |
| `/hybrid` | HybridView | 吴伟志+缠论融合（树粮草+四季+缠论买卖点+方向过滤+评分） | 并入 FundamentalView 或 TodayView 作"融合信号" |
| `/today` | TodayView | 今日可操作（选股池→批量择时→四季仓位） | **保留**——长赢的"今日该买该卖"实盘入口 |
| `/screening` | ScreeningView | 动态选股（通用） | 与 stock-pick/pick 合并为一个"选股"入口（缠论/长赢双模式） |
| `/stock-pick` | StockPickView | 选股（长盈/缠论 tabs） | 同上合并 |
| `/pick` | PickView | 缠论选股·买点推荐 | 同上合并 |

### 工具（回测/策略）
| 路由 | view | 处置 |
|---|---|---|
| `/portfolio` `/optimize` `/compare` `/strategies` | 组合/寻优/对比/策略库 | 归入"回测工具"分组 |

### 设置/数据
| 路由 | view | 处置 |
|---|---|---|
| `/settings` `/display-settings` `/data-cache` `/watchlist` | 服务器/显示/缓存/自选股 | 归入"设置"分组 |

## 2. 合并后 IA 提案（24 → ~9 入口，分组导航）

```
缠论学习回测（P0）
  ├ 学习训练     /learn          （analysis/train/verify 三 tab，主入口）
  ├ 单标的回测   /（或并入 learn）
  └ 模型验证     /audit（并入 verify tab）
长赢选股（P1）
  ├ 历史时点选股 /fundamental    （四季+树粮菜+基本面选股，主入口）
  ├ 今日可操作   /today          （选股池→择时→四季仓位，实盘入口）
  └ 融合信号     /hybrid（并入 fundamental 或 today）
选股
  └ 选股         /pick（合并 screening/stock-pick/pick，缠论/长赢双模式）
回测工具
  └ 组合/寻优/对比/策略库 /portfolio /optimize /compare /strategies
设置
  └ 服务器/显示/缓存/自选股 /settings /display-settings /data-cache /watchlist
```

## 3. 冗余/孤儿清单（待实现时逐个核实，勿直接删）
- **选股 5 合 1**：screening / stock-pick / pick / today（部分）/ fundamental——需逐个看模板，确认无独有功能再并。
- **长赢 3 合 1**：changying（概念卡）/ fundamental（数据）/ hybrid（融合）——概念卡可作 fundamental 的"季节说明"折叠区。
- **缠论 6 合 ~3**：backtest/learn/audit/diagnosis/signal-check/monitor——LearnView 已是 hub，其余并入其 tab。
- `/diagnosis` `/signal-check` `/monitor` `/data-cache` `/display-settings`：低频，可收进"设置/工具"二级。

## 4. 执行计划（确认后）
1. **先核实**：逐个读重叠 view 模板，确认合并无功能丢失（AGENTS.md §2 区分既有）。
2. **分组导航**：加一个分组侧边栏（缠论学习回测/长赢选股/选股/工具/设置），路由暂不删（redirect 兼容）。
3. **逐步合并**：先并最长赢 3 view（概念卡→折叠区）、再并选股 5→1、再并缠论散件入 LearnView tab。
4. **每步回归**：jsdom 测试 + tsc + 真实浏览器行为级验证（AGENTS.md §1/§5）。
5. **模型保真并行**：§2.2 字面口径（待你定向）、§2.5 四重链、死字段已清理（本轮）。

## 5. 待你拍板的点
- **合并激进程度**：A 只加分组导航、路由全保留（最稳）；B 加导航 + 合并长赢/选股（中等）；C 彻底重构为两模块（最干净、风险最高）。
- **树粮菜 vs 树粮草**：PRODUCT_REQUIREMENTS 写"树粮菜"，hybrid.py 写"树粮草"——以哪个为准统一？
- **先做哪个模块**：缠论学习回测（P0，买卖点精准展示）还是长赢选股（P1，树粮菜/四季直观）？
