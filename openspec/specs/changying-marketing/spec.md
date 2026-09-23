# changying-marketing Specification

## Purpose
TBD - created by archiving change easy-tdx-changying-chanlun-accuracy. Update Purpose after archive.
## Requirements
### Requirement: 全市场标记覆盖
系统 SHALL 能在凌晨窗口对 A 股（SH/SZ）全部总市值 ≥100 亿元的标的计算
树/粮/菜标记（分类 + 得分 + 打分明细），并把全量结果沉淀到本地 SQLite
（`~/.easy_tdx/changying_marks.db`），不做 top-N 截断。

#### Scenario: 全量标记落库
- **WHEN** 执行 `easy-tdx changying-mark` 且行情与财报数据可用
- **THEN** `changying_marks` 表行数 ≥ 当日市值 ≥100 亿标的总数
- **THEN** 每行含 symbol/market/category/score/scores_json/total_mcap_yi/report_date/updated_at
- **THEN** 摘要输出 by_category 统计与 total_scanned

#### Scenario: 市值门槛排除
- **WHEN** 某标的总市值 < 100 亿或市值不可得
- **THEN** 该标的不进入 marks 表（市值不可得视为不满足硬门槛）

### Requirement: 半年频调度与窗口锁
凌晨调度 SHALL 按财报对齐的半年频跑全量标记（默认 1 月/7 月首个周六
00:05），非窗口期仅在 gpcw 缓存出现新报告期时兜底重跑；调度线程 SHALL
进程内互斥，防止重复刷新。

#### Scenario: 半年主跑
- **WHEN** 调度线程在 1 月/7 月首个周六 00:05 之后唤醒
- **THEN** 执行一次全量 marks 刷新并在日志记录 count 与耗时

#### Scenario: 非窗口期跳过
- **WHEN** 周六调度唤醒但非 1/7 月主跑窗口且无新报告期
- **THEN** 跳过全量刷新，仅记录自检日志（marks.updated_at 与标的数）

### Requirement: 半成品保护
marks 刷新 SHALL 在落库前校验结果规模：本次标的数 ≥ 上次成功快照的 80%，
校验失败 SHALL 拒绝覆盖并记录告警，保证白天消费方不会读到半量数据。

#### Scenario: 拒绝半量覆盖
- **WHEN** 本次刷新合格标的数 < 上期 80%（如行情主机中途故障）
- **THEN** marks 表保留上次全量快照不变，日志输出告警与实际数量

### Requirement: 白天读取路径切换
`/stock-pick` 本地路径 SHALL 优先读 marks 全量表（source=local-full），
支持按 category/markets 过滤与 top_n 截断；marks 表为空时回退旧
changying_pool（source=local），再为空才走在线扫描（source=online）。

#### Scenario: 读全量标记
- **WHEN** marks 表非空且用户请求 stock_type=tree
- **THEN** 返回全部树型标的（受 top_n 截断），source=local-full

#### Scenario: 回退链
- **WHEN** marks 表为空但 changying_pool 有数据
- **THEN** 返回 pool 数据且 source=local；两者皆空走在线扫描

