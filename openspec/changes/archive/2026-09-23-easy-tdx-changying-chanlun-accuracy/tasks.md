# 任务清单：长盈全市场标记 + 准确性审计 + 图表全历史回溯

## Phase 1 — 全市场树粮菜标记（R1）

- [x] 1.1 新建 `fundamental/marks.py`：ChangyingMarkStore（SQLite 建表
      changying_marks + 索引）、`refresh_changying_marks()`（scan_market
      全量调用，top_n 不截断、min_mcap_yi=100）、`load_changying_marks()`、
      80% 半成品保护校验
- [x] 1.2 CLI `easy-tdx changying-mark`（--markets/--min-mcap-yi/--force/
      --top 输出摘要），保留 `changying-refresh` 兼容
- [x] 1.3 调度改造（cmd_web.py）：半年主跑窗口（1/7 月首个周六 00:05）+
      新报告期兜底 + 进程内互斥锁 + 自检日志；替代每天 top20 刷新
- [x] 1.4 /stock-pick 本地路径切换 marks 优先（source=local-full），回退链
      local-full → local → online；单元测试覆盖回退链
- [x] 1.5 单测：marks 落库/半成品保护/市值排除/回退链（test_changying_marks.py）
- [x] 1.6 真实验证：手动跑一次 changying-mark，确认 ≥1000 只落库、
      树/粮/菜分布合理、/stock-pick 页面数据覆盖面提升

## Phase 2 — 准确性审计管道（R2/R4）

- [x] 2.1 新建 `web/signal_ledger.py`：`signal_returns()` 唯一信号→收益
      实现（QFQ bars、N 根窗口、超额口径与 chanlun_validator 对齐）
- [x] 2.2 chanlun_validator / SignalAccuracyPanel 后端改为调用 signal_ledger
      （口径统一，R4）
- [x] 2.3 新建 `audit/accuracy.py`：长盈分层前瞻收益（tree/grain/vegetable
      × 20/60/250 日）、缠论买卖点类型化命中率、图表对账三模块
- [x] 2.4 CLI `easy-tdx audit-accuracy`（--samples/--markets/--out）+
      JSON/Markdown 双格式落盘 ~/.easy_tdx/audit/
- [x] 2.5 Web 路由 `web/routers/audit.py`：GET /audit/accuracy 与
      /history；前端新增审计页（表格 + 数据新鲜度标记）
- [x] 2.6 单测：point-in-time 无未来函数断言、对账单测（面板 vs 审计逐值
      一致）、伪造指标哨兵（数据缺失必须输出 null）
- [x] 2.7 真实验证：对 ≥30 只样本跑 audit-accuracy，Web 端可查且数字与
      落盘 JSON 一致

## Phase 3 — 图表全历史回溯（R3）

- [x] 3.1 `web/klines.py` 新增 `fetch_paged_bars()`：≤800/页循环翻页、
      时间戳去重、lookback 参数（默认 800，上限 20000）
- [x] 3.2 /bars 接入 lookback 参数 + total_returned/earliest_ts 响应字段；
      参数校验与 422 语义单测
- [x] 3.3 前端 `api.ts` 增加 loadEarlierBars()；KlineChart / ChanlunChart
      增加「加载更早 / 回最新」按钮 + 视口保持逻辑
- [x] 3.4 回测/选股/学习/看板四个视图接入（含买卖点随窗口重算对齐）——V722 全视图接入：ChanlunView/DiagnosisView/ScreeningView/BacktestView/StockPickView/TodayView/SignalVerifyView 均支持「加载更早」全历史回溯（Chanlun/Screening/Backtest 扩窗后重跑 /chanlun/analyze 使买卖点/中枢随窗口重算；后端 /chanlun/analyze、stock-pick timing、verify detail 均走 fetch_paged_bars 分页，count 上限放宽）
- [x] 3.5 单测：跨页重叠去重、不足 lookback、标注随窗口 index 重定位
      （组件测试）；前端 vitest 全绿
- [x] 3.6 真实验证：任选一票翻到最早可得 K 线，标注无错位

## Phase 4 — 收尾

- [x] 4.1 CHANGELOG.md 记录本次变更（版本号递增）
- [x] 4.2 全量验证：pytest 单测全绿 + vue-tsc/eslint/vitest 全绿 +
      openspec validate 通过
- [x] 4.3 归档 openspec change（若全部任务完成）——1.1–4.3 全部完成，V722 已提交（e17e24a）后归档
