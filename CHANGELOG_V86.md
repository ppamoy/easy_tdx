# 更新日志 V86

## [V86] — 2026-08-30

**P1 进阶：批量时点验证（F9 选股回测验证）——用历史数据验证「长赢理论是否跑赢」**

> 承接 V85（P1 核心：gpcw 指标层 + 树粮菜量化 + 单日历史时点选股）。
> 本次落地需求文档 F9：把「单日选股」升级为「**多历史时点批量验证**」——
> 跨多个历史日期分别选股，汇总树粮菜命中率与平均收益，并与同期上证指数对比，
> 给出「长赢理论是否跑赢基准」的可量化结论。

### 新增：批量验证管线（`easy_tdx/fundamental/pipeline.py`）

- `index_performance(target)` — 上证指数（SH 000001）在目标日之后的 20/60/250 交易日涨幅（基准）
- `run_verify(targets, pool)` — 多时点编排：逐时点选股（复用 `run_screen`）→ 附指数基准
- `_summarize_periods(...)` — 汇总：
  - 按分类（🌳树 / 🌾粮 / 🥬菜）统计样本数、平均收益、命中率（收益>0 占比）
  - 总体 + 指数基准平均
  - `beats_index`：各周期 alpha（总体平均 − 指数平均）与是否跑赢

### 新增：API

- `POST /api/v1/fundamental/verify` — `{dates: [多个 YYYY-MM-DD], pool: [...]}`
  → `{periods: [{date, season, results, index}], summary: {by_category, overall, index, beats_index}}`

### 新增：前端「批量时点验证」模式（`web-ui/src/views/FundamentalView.vue`）

- 页面顶部「单日选股 / 批量时点验证」双模式切换
- 批量模式：多日期输入 + 自选池 → 「🎯 长赢选股 vs 上证指数」α/跑赢徽章卡片
- 汇总表：树/粮/菜 × 总体 × 上证指数，含各周期平均收益与命中率
- 每个历史时点一张明细卡片（代码/分类/报告期/后续收益）

### 实测验证（Playwright，浏览器控制台零报错）

- `/fundamental` 批量验证 3 个历史时点（2024-04-15 / 2025-04-15 / 2025-10-15）× 6 只自选池：
  - 18 条选股样本；总体 +20日平均 3.3%（命中率 67%）
  - 上证指数同期 +20日 2.9% → **+20日 α +0.38 跑赢**；+60日/+250日暂跑输（样本受窗口限制）
  - 截图：`docs/chanlun-screenshots/verify_config.png / verify_result.png`

### 测试

- `tests/unit/test_fundamental_p1.py` 新增 `TestBatchVerify`（2 例，纯逻辑不依赖网络）：
  汇总统计（分类计数/均值/命中率）、空样本与 alpha/跑赢判定 —— 全部通过
- 全量 P1 测试 15 个通过；ruff 检查通过

### 已知限制 / 下一步

- 250 日收益只对较早时点可用（如 2025-10-15 尚无 250 日数据，如实显示 None）
- 更早历史（<2021）财报需新浪补充；全市场扩展与在线数据补充仍在 P2
