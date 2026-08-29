# 更新日志 V84

## [V84] — 2026-08-29

**P0 首个核心模块落地：缠论学习回测（逐步揭示训练 + 逐笔复盘讲解）**

根据产品需求梳理（docs/PRODUCT_REQUIREMENTS.md），实现两大支柱中的第一根：用户通过回测学习缠论买卖点、培养盘感、验证本模型准确性。

### 新增后端接口

- **POST /api/v1/chanlun/train/session**（src/easy_tdx/web/routers/chanlun.py）—— 创建缠论学习训练会话，返回：
  - bars：K 线（与 /bars 同列格式）
  - bis/xds/zss/mmds/fractals/bcs/boll：完整缠论结构
  - candidates：训练候选点（买卖点信号 + 采样分型干扰项），供前端逐步揭示时暂停提问，每个含 index/date/kind/signal(类型+置信度+质量评级)
  - mmd_outcomes：每个买卖点的信号后 5/10/20 日收益 + 5 日窗口最高/最低（复盘验证准确率用）
- 逻辑抽取为纯函数 build_train_session_payload(result, df, category)，可独立单测，接口体复用该函数避免重复。

### 前端训练页

- **新增 web-ui/src/views/TrainView.vue** + 路由 /train + 导航「缠论学习」：
  - 🎯 **逐步揭示训练**：K 线只揭示到当前位置（蓝色虚线揭示游标），到达关键候选点暂停提问「买 / 卖 / 观望」；提交后揭示缠论引擎真实信号（含置信度/质量评级）、方向判定、事后 N 日验证框（5/10/20 日收益 + 窗口区间）；计分板（题数/命中/命中率/得分），训练完成页展示汇总。
  - 📖 **复盘讲解**：逐笔列出全部买卖点信号，展示类型/日期/置信度/事后 20 日收益/✓✗验证/结构说明——即「本模型在历史上的准确率报告」。
  - 训练候选点需 ≥30 根背景 K 线，兼顾「有上下文 + 有转折点」。
- **ChanlunChart.vue 新增 revealIndex 揭示游标支持**：只渲染前 revealIndex+1 根 K 线及其范围内的笔/线段/中枢/分型/买卖点/背驰，并在揭示位置画蓝色虚线竖线；非训练模式不启用，行为与之前完全一致。

### 测试与浏览器验证

- **新增 tests/unit/test_chanlun_v84_train_session.py**（3 用例）：用合成 K 线跑完整缠论管道，验证会话负载结构齐全、candidates 覆盖买卖点信号与分型干扰项且坐标合法、mmd_outcomes 事后收益计算正确。
- **Playwright 浏览器实测**（web-ui/scripts/train-screenshot.mjs，开发版 + 生产版 dist 均验证）：
  - 逐步揭示 6+ 轮问答：用户判断 → 引擎揭示真实信号（如 1sell 置信度15%·S级 / 1buy 54%·S级 / 2sell_s）→ 事后验证框出现 → 计分正确累计
  - 复盘页 13 个买卖点信号全部渲染，事后 20 日收益 ✓/✗ 判定正确
  - console / page 零错误
- 全量回归：chanlun 相关单测 52 通过；vue-tsc 类型检查通过。

### 验证结果示例（000001 日线 400 根，Playwright 实测）

| 轮次 | 候选点 | 用户判断 | 引擎信号 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | 顶分型(34) | 买入 | 无信号 | ❌ 应观望 |
| 2 | 转折点(39) | 卖出 | 1sell 15%·S | ✅ 正确 |
| 3 | 底分型(56) | 观望 | 无信号 | ✅ 正确 |
| 4 | 转折点(71) | 卖出 | 1buy 54%·S | ❌ 应为买入 |
| 5 | 底分型(85) | 观望 | 无信号 | ✅ 正确 |

截图：docs/chanlun-screenshots/train_flow.png、train_review.png
