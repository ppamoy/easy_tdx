# 网站重构：回测 / 选股 / 缠论测试学习 三大模块 + 缠论画图精度修复（easy-tdx-v590-three-module-refactor）

## 动机（Motivation）

用户对当前 easy_tdx Web 端提出两个明确诉求：

1. 缠论画图仍不够精确：笔和线段没有落在 K 线的最高/最低点；笔、线段、中枢、背驰、三类买卖点的标注也不够准确。
2. 网站收敛为三个功能：
   - 保留现有回测页面；
   - 选股：用户可选不同时间，先用长盈理论选出基本面好的标的池，再用缠论进行择时交易；
   - 缠论测试学习页面。

当前 App.vue 导航暴露 15 个路由（单标的回测 / 缠论分析 / 缠论学习 / 长赢投资 / 动态选股 / 长赢选股 / 组合回测 / 参数寻优 / 结果对比 / 策略库 / 服务器设置 / 信号监控 / 技术诊断），功能碎片化。选股被拆成「长赢投资 / 动态选股 / 长赢选股」三页，缠论被拆成「缠论分析 / 缠论学习 / 训练」多页，不符合「就三个功能」的预期。本 change 做产品级收敛，而不是继续堆页面。

## 现状盘点（Audit）

| 维度 | 现状 | 结论 |
|---|---|---|
| 导航 | router.ts 15 条路由、App.vue 12 个导航链接 | 需要收敛为 3 个主导航入口 |
| 回测 | BacktestView.vue（/，1763 行）功能完整 | 保留，最小改动 |
| 选股 | ScreeningView.vue（长赢动态选股+缠论回测）、FundamentalView.vue（长赢选股）、ChangyingView.vue（长赢投资）三页割裂 | 合并为单页「选股」，做「基本面→择时」两步流 |
| 长盈基本面 | fundamental/screener.py 已有 point-in-time 树粮菜打分引擎；fundamental/router 已提供选股 API | 复用，但需与缠论择时串联 |
| 缠论择时 | changying_chanlun.py 策略存在；screening.py 已能做「选股+缠论买卖点」但用硬编码 30 只热门池 | 统一时间语义 + 可扩展标的池 |
| 缠论学习 | easy-tdx-chanlun-learning 已交付 7 能力（理论/可视化/难度/错题/进度/排行榜/实证），散落在 /train、/learn、/verify、/chanlun | 合并为单页多 Tab |
| 缠论画图精度 | 模型层已有 high_k_index/low_k_index/bar_index/start_val/end_val 锚点与 tests/unit/test_chanlun_geometry.py 不变量测试；但笔算法仍有多处「静默跳过真实极值」的过滤（弱笔/趋势一致性/分型稳定性），线段特征序列取中间特征笔、中枢 zg/zd 语义与 gg/dd 易混 | 需要结构性修复 + 金标回归 |

### 精度问题根因（先查再写，非臆测）

- fractal.py：分型只比较「中间缠论K线 vs 左右缠论K线」，严格模式下未明确把合并组内的真实极值来源 K 线作为左右比较对象；bar_index 已锚定极值来源，但 find_fractals 的三根 K 线比较口径与「落最高/最低点」的视觉期望仍可能不一致。
- bi.py：_check_bi_endpoint_consistency、_validate_bi_price_direction、_is_weak_bi、_check_fractal_stability、_check_trend_consistency 等多层过滤会跳过/替换真实的分型转折点，导致笔端点没有取到局部最高/最低点。
- xd.py：线段结束点取「特征分型中间元素的前一支同向笔终点」，逻辑对标准特征序列是正确的，但收尾分支用 max/min(bi.end.val) 重新选点，可能与共享转折点不连续。
- zs.py：zg=重叠区间最高的低点、zd=重叠区间最低的高点，语义正确；但 gg/dd 与 zg/zd 容易在序列化/前端混用。
- 标注：mmd 已输出 bar_index，但前端 mmdMarkPoints 的 price 仍用 bars[idx].low/high 乘偏移，没有锚定触发笔终点的真实极值价；bc 标注在 MACD 副图 y=柱值，主图缺少背驰标注上下文。

## 目标形态（Target）

    easy_tdx Web
    ├── 回测        /           保留现有单标的回测（组合/寻优入口软隐藏）
    ├── 选股        /stock-pick 单页两步流：时间选择 → 长盈基本面选股池 → 缠论择时
    └── 缠论测试学习 /learn      单页多 Tab：分析 / 理论 / 盘感训练 / 买卖点实证 / 进度

其余页面（组合回测、参数寻优、结果对比、策略库、信号监控、技术诊断、服务器设置）路由保留但移出主导航，服务器设置以页脚齿轮进入，避免破坏既有 URL 与书签。

## 能力域概述（Spec Overview）

1. chanlun-geometry-precision — 缠论画图精度：分型/笔/线段/中枢/背驰/三类买卖点端点必须锚定真实极值；结构判定修正；金标回归测试。
2. navigation-simplification — 导航收敛为三大模块 + 服务器设置齿轮 + 旧路由软隐藏。
3. stock-selection-module — 选股单页两步流：可选时间（point-in-time）→ 长盈树粮菜基本面池 → 缠论择时（买卖点/背驰/中枢/择时结论）。
4. chanlun-learning-module — 缠论测试学习单页合并：分析 + 理论教学 + 盘感训练 + 买卖点实证 + 进度。
5. backtest-page — 回测页保留回归：不做功能删减，纳入新导航与门禁回归。

## 影响评估（Impact）

- 前端：App.vue 导航收敛；新增 StockPickView.vue（或改造 ScreeningView.vue）；LearnView.vue 由 70 行容器扩展为多 Tab 容器；ChanlunChart.vue 修正买卖点/背驰标注锚定；删除/隐藏冗余导航项。
- 后端：新增/改造选股路由（时间语义统一、长盈基本面 + 缠论择时两步、标的池可配置）；精度修复集中在 chanlun/{fractal,bi,xd,zs,mmd,beichi}.py；web/routers/chanlun.py 序列化补齐标注锚点字段。
- 数据：选股复用离线 .day / 长盈财报缓存；无新持久化表（进度/错题已存在）。
- 测试：后端 pytest（几何不变量金标、选股两步流契约）；前端 vitest（导航、ChanlunChart 标注、选股流程冒烟）+ vue-tsc/vite build。

## 成功标准（Success Criteria）

1. 主导航只有 3 个入口：回测、选股、缠论测试学习；旧路由仍可直达。
2. 选股页用户可选任意历史时间，先得到长盈基本面标的池（树粮菜+评分），再对池内标的做缠论择时（买卖点/背驰/中枢/操作建议），两步结果可解释。
3. 缠论测试学习页一个页面内可完成：看图分析、理论学习、盘感训练、买卖点实证、进度查看。
4. 精度修复后：所有笔/线段端点价格等于其锚定原始K线的最高/最低点；笔首尾相连；线段方向与端点极值一致；中枢 zg/zd 与 gg/dd 不混用；买卖点/背驰标注锚定触发笔终点。
5. 全部门禁通过：ruff / mypy / pytest / vue-tsc / vite build / vitest。
