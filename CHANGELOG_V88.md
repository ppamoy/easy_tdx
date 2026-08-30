# 更新日志 V88

## [V88] — 2026-08-30

**P2 首个模块落地：全市场基本面扫描 —— 历史时点选股从自选池扩展到全市场**

> 承接 V85–V87（P1 长赢基本面选股：gpcw 指标层 + 树粮菜量化 + point-in-time + 批量时点验证 + 新浪回退）。
> 本次落地路线图 P2 第一项「全市场扫描」：历史时点选股不再局限于自选池，
> 直接用 gpcw 财报对**全市场**逐只打分排序，返回树/粮/菜 Top N。

### 新增：批量 point-in-time（`easy_tdx/fundamental/indicators.py`）

- **`pick_reports_bulk(frame, target, *, markets=None)`** —— 向量化版 `pick_report`：
  一次对整张指标帧（全市场几千只股票）完成「披露日 ≤ target」截断 + 按 code+market
  取披露日最新一期。规则与逐股 `pick_report` 完全一致（缺失披露日用报告期近似且 ≤100 天），
  但把 O(N²) 逐股遍历降为向量化 groupby —— 实测全市场 5394 条记录 0.0s 完成。

### 新增：全市场扫描编排（`easy_tdx/fundamental/pipeline.py`）

- **`scan_market(target, *, markets=("SH","SZ"), stock_type="all", top_n=50, min_score=15, with_performance=True)`**：
  - 按目标日期自动选择 gpcw 报告期 → 全市场记录 → 批量 point-in-time → 逐只树粮菜打分
  - 按分类得分降序返回 top_n（默认 50），附 `by_category` 分类计数与 `truncated` 截断提示
  - 可选附带 top_n 结果的后续 20/60/250 日表现（只对返回结果计算，避免全市场几千次行情请求）

### 新增：API（`easy_tdx/web/routers/fundamental.py`）

- **POST `/api/v1/fundamental/scan`** — `{date, markets, stock_type, top_n, min_score, with_performance}`
  → `{date, total_scanned, by_category, results(树/粮/菜+得分+明细), season, truncated|warning}`

### 前端：全市场扫描第三模式（`web-ui/src/views/FundamentalView.vue`）

- `/fundamental` 页面「📌 单日选股 / 📈 批量时点验证 / 🔭 全市场扫描」三模式切换
- 扫描模式配置：历史日期 + 市场勾选（沪/深）+ 股票类型 + Top N + 最低分类分 + 是否附带后续表现
- 结果区：季节卡片 + 全市场统计栏（扫描数/树/粮/菜/Top N/截断+）+ 结果表（代码/分类/得分/报告期/
  EPS/ROE/毛利率/净利率/负债率/同比/后续 N 日），每行可展开树粮菜三张打分明细

### 实测验证（Playwright，浏览器控制台零报错）

- `/fundamental` 全市场扫描 2026-09-01（沪+深）：**5550 只全市场扫描**，
  树 280 / 粮 4249 / 菜 942，返回 Top 50（截断 +5421），季节「春季·播种期」
- 首行明细展开验证（🌳49 / 🌾100 / 🥬30 三张明细卡渲染），console/page 零错误
- 截图：`docs/chanlun-screenshots/scan_config_result.png / scan_detail.png`
- API 端到端：`/api/v1/fundamental/scan` 返回 5550 只扫描 + 分类统计 + 得分排序（真实 gpcw 数据）

### 质量

- 新增 7 个测试（`tests/unit/test_fundamental_p1.py`）：`TestPickReportsBulk`（批量截断/市场过滤/
  与逐股 pick_report 结果一致/空帧）+ `TestScanMarket`（排序 top_n/类型过滤/空数据警告）
- 顺手修复 V85–V87 遗留 mypy 问题：`season.py`（类型标注/`_closes`/`detect_season`/`_stdev`）、
  `screener.py`（max key 类型）、`sina_adapter.py`（浮点返回/嵌套函数标注）——
  `mypy src/easy_tdx/fundamental/` 全绿
- 全量单测 **2241 通过**；ruff 全绿；vue-tsc 类型检查 + vite 构建通过

### 已知限制 / 下一步（P2 后续）

- 全市场扫描当前依赖 gpcw 财报下载（本地缓存 zip）；更早历史时点沿用 V87 新浪回退
- 后续：在线数据补充与财务指标缓存（SQLite/parquet）、训练成绩持久化/排行榜
