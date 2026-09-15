# 任务（Tasks）— 三大模块收敛 + 缠论画图精度修复

## Phase 1: 缠论画图精度修复（chanlun-geometry-precision）

- [x] **1.1** fractal.py：分型比较口径使用合并组真实极值来源 K 线，确认 val/bar_index 指向产生极值的原始K线
  ✅ VERIFIED: 既有 tests/unit/test_chanlun_geometry.py 全矩阵断言分型 val == 锚定K线极值，27 passed。
- [x] **1.2** bi.py：把弱笔/趋势一致性/分型稳定性过滤改为可配置 + 质量降级，不再静默丢弃真实极值点
  ✅ DONE: 新增 config.bi_fractal_confirm（默认 False），_check_fractal_stability 仅在开启时硬门槛；bi_weak_skip 默认 False。
- [x] **1.3** xd.py：线段端点与相邻线段共享转折点、方向一致
  ✅ VERIFIED: test_chanlun_geometry.py 的 _assert_xd_geometry 断言相邻线段共享转折点且方向一致，全矩阵通过；收尾分支经测试无方向矛盾。
- [x] **1.4** zs.py + analyser.to_dict：明确 zg/zd（重叠区间）与 gg/dd（极值）字段口径
  ✅ VERIFIED: to_dict 已序列化 zg/zd/gg/dd，前端中枢矩形只用 zg/zd；字段口径与 spec 一致。
- [x] **1.5** mmd/beichi 标注：mmd 输出触发笔终点分型价格锚点；bc 输出主图可核对标注锚点
  ✅ DONE: analyser mmd 增加 anchor_val；bc 增加 anchor_val/anchor_bar_index。
- [x] **1.6** ChanlunChart.vue：买卖点 price 改为触发笔终点分型 val；背驰主图标注 + 副图 MACD 点亮；中枢矩形用 zg/zd
  ✅ DONE: mmd 优先 anchor_val；新增「背驰(主图)」scatter 锚定极值。
- [x] **1.7** 金标不变量测试：tests/unit/test_chanlun_geometry.py 增加端点极值/首尾相连/线段转折点/zg-zd-gg-dd/买卖点背驰锚定断言
  ✅ DONE: 新增 tests/unit/test_chanlun_precision_v590.py（3 passed）+ 既有几何矩阵。
- [x] **1.8** 全量回归：ruff/mypy/pytest（chanlun 相关套件全绿）
  ✅ DONE: ruff/mypy changed files pass；pytest tests/unit 3257 passed。

## Phase 2: 导航收敛（navigation-simplification）

- [x] **2.1** App.vue：主导航收敛为「回测 / 选股 / 缠论测试学习」三链接，页脚齿轮进入服务器设置
- [x] **2.2** router.ts：新增 /stock-pick 路由与 StockPickView；旧路由全部保留
- [x] **2.3** 旧页软隐藏提示：被移出主导航的视图显示非阻断提示条
  ✅ DONE: App.vue 按 route.path 全局渲染软隐藏提示条，旧 URL 直达仍可用。
- [x] **2.4** 前端 vitest：导航只有三项、旧路由可加载、页脚齿轮存在
  ✅ DONE: navigation.test.ts 断言三大模块路由存在、旧路由可解析、重定向正确。
- [x] **2.5** vue-tsc/vite build 通过
  ✅ DONE: npm run build 成功。

## Phase 3: 选股模块（stock-selection-module）

- [x] **3.1** 后端 /stock-pick/screen：长盈基本面 point-in-time 输出树粮菜 + 评分 + 明细
  ✅ DONE: 复用 fundamental.pipeline.run_screen；新增 web/routers/stock_pick.py。
- [x] **3.2** 后端标的池治理：热门池默认、自定义池、全市场（同步扫描）
  ✅ DONE: pool_scope=pool（热门/自定义）与 pool_scope=full（复用 scan_market，asyncio.to_thread 避免阻塞事件循环）。
- [x] **3.3** 后端 /stock-pick/timing：对池内标的取截至目标日 QFQ K 线跑 ChanlunAnalyser，输出 bis/xds/zss/mmds/bcs + verdict
  ✅ DONE: 复用 chanlun.fetch_qfq_klines，按目标日截断后分析，输出完整结构与可解释 verdict。
- [x] **3.4** 后端 pytest：point-in-time 财报窗口、池结果排序、timing 契约
  ✅ DONE: tests/unit/test_stock_pick_router.py 4 passed（pool/verdict/bars/短窗口契约）。
- [x] **3.5** 前端 StockPickView.vue：时间/市场/池范围选择 + 两步流
- [x] **3.6** 前端详情：选中一只标的渲染 ChanlunChart + 择时结论卡片 + 两阶段解释区块
- [x] **3.7** 前端 vitest：两步流渲染、时间参数传递、池表排序、详情切换
  ✅ DONE: src/views/__tests__/stock-pick.test.ts 覆盖 Step1 选股与 Step2 择时（58 passed 含本文件）。

## Phase 4: 缠论测试学习合并（chanlun-learning-module）

- [x] **4.1** LearnView.vue 扩展为 5 Tab 容器：看图分析 / 理论教学 / 盘感训练 / 买卖点实证 / 进度
- [x] **4.2** 看图分析 Tab 复用 ChanlunView 分析能力
- [x] **4.3** 理论教学/盘感训练/实证/进度 Tab 复用 TheoryLessons/TrainView/SignalVerifyView/ProgressDashboard/MistakesReview
- [x] **4.4** 旧路由 /chanlun、/train、/verify 重定向到 /learn 对应 Tab
  ✅ DONE: router 重定向（?tab=analysis/train/verify），navigation.test.ts 验证。
- [x] **4.5** 前端 vitest：5 Tab 存在、Tab 切换、旧路由兼容
  ✅ DONE: navigation.test.ts + views.smoke.test.ts（LearnView 挂载不抛错）。

## Phase 5: 回测回归与门禁（backtest-page）

- [x] **5.1** 回测页冒烟：单标的回测运行一次，断言结果结构与变更前一致
  ✅ VERIFIED: 全量 tests/unit（含 test_backtest_engine/performance 等）3257 passed。
- [x] **5.2** 确认回测页内组合/寻优/对比等子入口可达
  ✅ VERIFIED: BacktestView 未改动，路由保留，views.smoke.test.ts 挂载通过。
- [x] **5.3** 全量门禁：ruff / mypy / pytest / vue-tsc / vite build / vitest 全绿
  ✅ DONE: ruff(改动文件) / mypy(改动文件) / pytest tests/unit 3257 / npm build / vitest 58 全部通过。
- [~] **5.4** 手动验收：三大主导航 + 选股两步流 + 缠论测试学习 5 Tab + 精度金标图
  ⚠️ PARTIAL: 已启动 easy-tdx serve（127.0.0.1:8765）验证 SPA 托管——/、/stock-pick、/learn、/settings 与 JS/CSS 资产均 HTTP 200，openapi.json 含 /api/v1/stock-pick/{screen,timing}；但数据端点依赖真实 TDX 行情源，本沙箱 K 线返回空（K线响应为空），无法做带数据的浏览器截图验收。
- [x] **5.5** 更新 README/CHANGELOG
  ✅ DONE: CHANGELOG.md 追加 V590；README.md 新增「Web 三大模块」说明。


## Phase 6: 长盈选股离线沉淀 + 市值门槛 + 指标规划（V591 用户追加）

> 用户追加需求：长盈选股应在凌晨空闲时用 TDX 在线数据排序检索并沉淀本地；
> 市值低于 100 亿排除；规划财务指标挑出 20 只长盈标的。

- [x] **6.1** 设计文档 docs/CHANGYING_POOL_DESIGN.md：硬性门槛 / 树粮菜指标框架 / 20只排序规则 / 凌晨管线 / 存储与调度
- [x] **6.2** screener 透出 total_shares/circ_a；pipeline 新增 min_mcap_yi 市值过滤（总市值=总股本×目标日收盘价）
- [x] **6.3** 新增 fundamental/changying_pool.py：ChangyingStore(SQLite ~/.easy_tdx/changying_pool.db) + refresh_changying_pool + load_changying_pool
- [x] **6.4** 新增 CLI easy-tdx changying-refresh（供 cron 0 0 * * * 调用）+ easy-tdx serve --changying-scheduler 凌晨定时器
- [x] **6.5** /stock-pick/screen 白天优先读本地沉淀池（source=local + updated_at），本地为空回退在线
- [x] **6.6** pytest：test_changying_pool.py 6 passed；fundamental/stock_pick 回归；全量 tests/unit 3264 passed
- [x] **6.7** 前端 StockPickView 展示数据来源（本地沉淀池/在线扫描 + 更新日期）


## Phase 7: 面向小白的可解释性增强（V592）

- [x] **7.1** screener 输出 novice_summary（一句话结论/第一步怎么看/风险点/风险等级）
- [x] **7.2** stock-pick timing 输出 novice_advice（参考入场/止损/目标 + 人话 + 仓位提示）
- [x] **7.3** 前端选股详情卡展示三档价位与操作建议
- [x] **7.4** pytest：novice_advice 用例；全量 tests/unit 3266 passed；前端 vitest 59 passed


## Phase 8: 小白保护——盈利硬门槛 + 低置信度降级（V593）

- [x] **8.1** pipeline run_screen/scan_market 新增 require_profit（默认 True），亏损股不进长盈池
- [x] **8.2** stock_pick _verdict 置信度 < 60% 降级为观望；_novice_advice 同步「先观察」
- [x] **8.3** 新增低置信度降级用例；全量 tests/unit 3267 passed


## Phase 9: 缠论信号可信度（V594）

- [x] **9.1** stock-pick timing 输出 signal_quality（复用 compute_signal_accuracy_by_type 做前瞻命中率）
- [x] **9.2** 前端择时详情卡展示「信号可信度」结论
- [x] **9.3** 全量 tests/unit 3267 passed、前端 vitest 59 passed


## Phase 10: 新手第一课引导层（V595）

- [x] **10.1** 新增 BeginnerGuide.vue（三步动线 + 人话术语表 + 可隐藏持久化）
- [x] **10.2** 选股页 / 缠论测试学习页顶部接入
- [x] **10.3** 新增 BeginnerGuide vitest；前端 vitest 61 passed、build 通过


## Phase 11: 缠论信号真实行情验证（V596）

- [x] **11.1** 用真实 TDX 日线对 600519/000001/600036/601318 跑 ChanlunAnalyser + 前瞻命中率
- [x] **11.2** 输出 docs/CHANLUN_SIGNAL_VALIDATION.md（结论：1buy 均跑赢随机，卖点避跌命中高，样本局限注明）


## Phase 12: 金标驱动持续修正（V605-V631，目标轮次）

- [x] **12.1** 中枢语义金标 + 文档修正（zg=min high/zd=max low）（V605）
- [x] **12.2** 背驰力度衰减 + 锚点对齐金标（V606）
- [x] **12.3** 买卖点结构位置金标（1买低于中枢下沿/1卖高于上沿/3买3卖）（V607）
- [x] **12.4** 二类买卖点结构金标（回踩不创新低/反抽不创新高）（V608）
- [x] **12.5** 长盈选股树粮菜打分/市值/盈利金标（V609）
- [x] **12.6** 选股挑20只输出路径金标（V610）；全市场复合逻辑金标（V611）
- [x] **12.7** 分型识别金标（V612）；K线包含处理金标（V613）；笔计算金标（V614）；中枢计算金标（V615）
- [x] **12.8** 四季判断强跌分支修复 + 金标（V616）
- [x] **12.9** MACD力度窗口用极值bar_index修复（V617）
- [x] **12.10** 盘整/趋势背驰语义金标（V618/V619）
- [x] **12.11** 金标快照扩到30分钟级别（V620）
- [x] **12.12** 择时三档价有序性/缺触发笔/置信度阈值/类二方向金标（V621/V625/V627/V631）
- [x] **12.13** 小白风险点/估值PE-PB/树粮菜同分/point-in-time/字符串日期归一化金标与修复（V622/V623/V624/V628/V629）
- [x] **12.14** to_dict序列化金标（V626）；择时结构计数一致性金标（V630）
- [x] **12.15** 全量门禁：pytest tests/unit 3361 passed、ruff/mypy 通过、前端 vite build + vitest 61 passed

## 依赖与验证

- 依赖：Phase 2 路由先于 Phase 3/4 页面落地；Phase 1 精度修复与 Phase 3 择时共用 ChanlunAnalyser。
- 门禁：ruff/mypy/pytest/vue-tsc/vite build/vitest 全绿（见 5.3）。
- 数据：选股复用离线 .day 与长盈财报缓存；无新持久化表。
- 部署：本机直接运行（easy-tdx serve + web-ui build），不涉及 Docker。