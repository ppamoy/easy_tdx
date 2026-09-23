# 提案：长盈选股 + 缠论择时准确性审计与图表全部可回溯（飞轮审计第 1 轮）

## 为什么做（Why）

项目的唯一目的：**通过图表向用户证明「长盈选股 + 缠论择时」的准确性**。
凡是不能支撑这个目的的东西都是负资产。本变更聚焦用户点名的两大痛点：

1. **全市场树/粮/菜标记没有按用户要求落地**——凌晨应跑 A 股全部市值 ≥100 亿
   的标的并标记树/粮/菜（该数据半年/季度更新即可），现状只有 top 20 的
   「标的池」，大部分合格标的没有标记，用户看到的选股结果覆盖面严重不足。
2. **准确性没有被系统性审计过**——长盈模型（树粮菜打分）、缠论模型（分型/笔/
   中枢/三类买卖点/背驰）、图表展示（标注与数据对齐）三层是否自洽、是否可信，
   缺少一份机器可验证的审计报告；图表也还没有做到「任何同级别 K 线都能往前/
   往后查看」。

审计发现（2026-09-23 现场核查）：

- `refresh_changying_pool()` 默认 `top_n=20`：全市场打分后**只沉淀 20 只**，
  其余几千只合格标的的树/粮/菜标记被丢弃。
- `cmd_web.py` 内置的凌晨调度线程每天跑一次 top 20，而树/粮/菜维度依赖的
  财报本来就该半年/季度一更——频次错了、范围也错了。
- `/bars` 接口 `count` 上限 800 且 TDX 协议单次偏移 `start` 为 uint16，前端
  图表一次最多看 800 根，**无法翻到更早的历史**（MAC 翻页管道存在但图表未接入）。
- 缠论买卖点历史胜率面板（`SignalAccuracyPanel`）存在，但其口径没有与
  回测引擎的成交记录对账——「模型说准」和「回测账本说准」可能不一致。

## 变更内容（What Changes）

- **R1 全市场标记**：新增 `easy-tdx changying-mark` 命令 + 凌晨调度任务：
  对 A 股（SH/SZ，BJ 可选）全部总市值 ≥100 亿标的做树/粮/菜标记并全量
  沉淀 SQLite；调度周期改为**财报对齐的半年频**（每期财报披露完成后跑一次，
  默认 1 月/7 月首个周末，可配置），替代现在的每天 top20。
- **R2 准确性审计管道**：新增 `easy-tdx audit-accuracy`：长盈模型前瞻收益
  分层审计 + 缠论买卖点信号质量审计 + 图表数据对账，输出 JSON/Markdown
  双格式审计报告落盘 `~/.easy_tdx/audit/`，Web 端 `/audit/accuracy` 可查。
- **R3 图表全历史可回溯**：`/bars` 分页上限提升（内部循环翻页），前端所有
  K 线图（回测/选股/学习/看板）接入「往前/往后加载更多」+ 保留 dataZoom
  双向缩放；标记（买卖点/树粮菜标签）随窗口数据重算，保证标注与可见 K 线
  一致。
- **R4 对账口径统一**：缠论信号胜率面板与回测引擎成交记录用同一套
  信号→收益计算，杜绝两处口径各说各话。

## 影响（Impact）

- 受影响规范：`changying-marketing`（新增）、`accuracy-audit`（新增）、
  `chart-history-navigation`（新增）、`signal-accuracy-consistency`（新增）。
- 受影响代码：`fundamental/changying_pool.py`、`fundamental/pipeline.py`、
  `cli/cmd_changying.py`、`cli/cmd_web.py`、`web/klines.py`、
  `web/routers/bars.py`、`web/routers/stock_pick.py`、
  `web/routers/audit.py`（新增）、`backtest/chanlun_validator.py`、
  `web-ui/src/components/{KlineChart,ChanlunChart}.vue` 及 4 个视图。
- 不破坏现有 `/stock-pick` API 契约：本地池读取路径改为读全量标记表，
  `source` 字段从 `local` 细分为 `local-full`（语义升级，向后兼容）。

## 成功标准（Success Criteria）

1. `changying_marks` 表 ≥ 全市场市值 ≥100 亿标的数（2026-09 约 1200+ 只），
   每行带树/粮/菜分类与得分；刷新命令真实跑通并落库。
2. `easy-tdx audit-accuracy` 对 30 只以上样本输出真实（非伪造）前瞻收益
   分层统计与买卖点命中率，报告可从 Web 查看且数字与落盘 JSON 一致。
3. 任一图表可向后翻到该级别 K 线的最早可得历史（MAC 分页管道内），向前
   可到最新 bar，全程标注不丢失、不错位。
4. 全量单测 + 前端 vitest/vue-tsc/eslint 全绿；不引入新的未来函数
   （point-in-time 审计项显式检查披露日 ≤ target）。
