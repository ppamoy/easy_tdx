# 任务（Tasks）— 缠论学习页面

## Phase 1: 理论教学（theory-lessons）

- [ ] **1.1** 新建 `web-ui/src/content/lessons/`，编写 6 篇 Markdown 概念讲解（fractal/bi/segment/zs/mmd/beichi）
- [ ] **1.2** 新建 `LessonCard.vue`：Markdown 渲染 + ChanlunChart 静态图例插槽
- [ ] **1.3** 新建 `TheoryLessons.vue`：概念列表（localStorage 已读标记）+ 上一篇/下一篇导航
- [ ] **1.4** 新建 `LearnView.vue` 容器 + `/learn` 路由（含子 Tab：理论/训练/学习中心）
- [ ] **1.5** vitest：LessonCard 渲染 + TheoryLessons 已读标记 + LearnView 冒烟

## Phase 2: 逐步构建可视化（visual-teaching）

- [ ] **2.1** ChanlunChart 扩展：中枢成形高亮（revealIndex 处新成中枢 → ZG/ZD 矩形 + 标注）
- [ ] **2.2** ChanlunChart 扩展：买卖点触发高亮（信号 K 线 + V102 摘要弹出）
- [ ] **2.3** TrainPractice.vue 新增「结构时间线」侧栏（分型/笔/中枢事件列表，点击跳转）
- [ ] **2.4** vitest：中枢高亮/信号高亮/时间线跳转逻辑

## Phase 3: 难度分级 + 随机标的（difficulty-tiering）

- [ ] **3.1** 后端 `train/session` 支持 `difficulty` + `seed`：候选点特征打分排序截取，seed 复现
- [ ] **3.2** 后端单测：同 (code,category,difficulty,seed) 出题一致 + 不同难度题集特征差异
- [ ] **3.3** 前端训练配置加难度选择 + 「🎲 随机标的」按钮（本地代码池）
- [ ] **3.4** vitest：难度参数传递 + 随机标的更新

## Phase 4: 错误归因（mistake-feedback）

- [ ] **4.1** 后端 build_train_session_payload 扩展 `candidate.signal.explanation`（msg + V102 拼接）
- [ ] **4.2** 前端答错时渲染「正确解读」区块（信号/V102 建议/事后表现一句话）
- [ ] **4.3** 后端新端点：`POST /learn/mistakes`（写入错题集）+ `GET /learn/mistakes?player`
- [ ] **4.4** 前端「错题复习」列表（按周期/难度筛选）
- [ ] **4.5** 后端 pytest（explanation 拼接 + mistakes 读写契约）+ 前端 vitest

## Phase 5: 学习进度（progress-tracking）

- [ ] **5.1** 后端 `POST /learn/progress` + `GET /learn/progress?player`（按 category×difficulty 聚合）
- [ ] **5.2** SQLite 迁移：train_scores 加 difficulty 列；新建 learn_progress / learn_mistakes 表
- [ ] **5.3** `ProgressDashboard.vue`：掌握度矩阵表格
- [ ] **5.4** `ProgressDashboard.vue`：最近 20 次命中率折线图
- [ ] **5.5** 后端 pytest（聚合正确性）+ 前端 vitest

## Phase 6: 排行榜增强（leaderboard-enhance）

- [ ] **6.1** 后端 leaderboard 支持 `category`/`difficulty` 筛选 + 分组汇总（总人数/平均命中率/最高分）
- [ ] **6.2** 前端排行榜加筛选下拉 + 汇总行
- [ ] **6.3** 后端 pytest（筛选/汇总契约）+ 前端 vitest

## Phase 7: 买卖点实证复盘（signal-backtest-verification）

- [ ] **7.1** 后端预置 20 只大市值/大成交量标的池（常量/配置，code+name+market）
- [ ] **7.2** 后端 `POST /verify/signals/prerun`：批量跑 20 只标的缠论分析（DAY、400 根），结果缓存内存/文件
- [ ] **7.3** 后端 `GET /verify/signals/list`：返回 20 只清单 + 预跑状态；`GET /verify/signals/detail?code`：单标的买卖点 + MMD.zs 同级别中枢 + 基础K线
- [ ] **7.4** 后端 pytest：预跑缓存正确性 + detail 返回 MMD.zs 同级别中枢 + 标的池数量/字段契约
- [ ] **7.5** 前端 `SignalVerify.vue`：左列表（20 只）+ 右单标的详情（一次一只）+ 上一只/下一只切换
- [ ] **7.6** 详情图：买卖点标注（类型+置信度）+ 买卖点后逐根 K 线揭示（下一根/快进10根/跳到末尾）
- [ ] **7.7** ChanlunChart 支持「仅显示当前买卖点 MMD.zs 同级别中枢」+ reveal 逐根游标
- [ ] **7.8** 前端 vitest：列表/切换/逐根揭示/同级别中枢渲染

## 依赖与验证

- 依赖：Phase 1 容器先行（LearnView + /learn 路由），Phase 2-7 为子模块，可并行开发
- 门禁：每阶段提交前 ruff/mypy/pytest/vue-tsc/vite build/vitest 全绿
- 数据：SQLite（train_store 同库），迁移脚本幂等（IF NOT EXISTS / ADD COLUMN 前检查）
