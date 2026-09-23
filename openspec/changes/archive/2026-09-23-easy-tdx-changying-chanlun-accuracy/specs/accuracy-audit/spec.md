# accuracy-audit 规范（模型准确性审计）

## ADDED Requirements

### Requirement: 长盈分层前瞻收益审计
审计管道 SHALL 对 marks 表中树/粮/菜各类抽样 ≥30 只（不足全量），以标记
日为基期用复权价计算 +20/+60/+250 日前瞻收益，输出每类的收益分位数
（P25/P50/P75）、胜率与样本数；计算 MUST 使用 point-in-time 标记（披露日
≤ 标记日）与 QFQ 复权价，不得引入未来函数。

#### Scenario: 输出真实分层统计
- **WHEN** 执行 `easy-tdx audit-accuracy --samples 30`
- **THEN** 报告含 changying 字段：每类样本数、P25/P50/P75、胜率、基期日期
- **THEN** 所有数字可由报告内 per_symbol 明细复核求和得出

#### Scenario: 无未来函数
- **WHEN** 审计某标的标记日 D
- **THEN** 打分输入仅使用披露日 ≤ D 的财报期；前瞻收益价格取 D 之后的 bars

### Requirement: 缠论买卖点信号质量审计
审计管道 SHALL 对抽样标的跑缠论分析，按买卖点类型（1/2/3 类买卖点 +
背驰）统计信号后 N 根的超额命中率与平均超额收益，口径 MUST 与
`backtest/chanlun_validator.py` 一致（同一函数实现）。

#### Scenario: 类型化命中率
- **WHEN** 审计完成
- **THEN** 报告含 chanlun 字段：按 mmd 类型的信号数、命中率、平均超额收益
- **THEN** 与 /stock-pick/timing 的 signal_quality 历史胜率同口径

### Requirement: 图表数据对账
审计 SHALL 抽样比对图表取数（/bars）与缠论分析输入的 K 线：同一
(market, code, category) 的最后一根 bar 时间戳 MUST 一致，不一致计入
mismatches 并在报告头部标红。

#### Scenario: 对账不一致被捕获
- **WHEN** /bars 与缠论管道对同一标的返回不同最后 bar 时间戳
- **THEN** 报告 mismatches 含该标的及两侧时间戳

### Requirement: 审计报告落盘与查询
审计结果 SHALL 以 JSON + Markdown 双格式落盘 `~/.easy_tdx/audit/`，
文件名含日期；Web 端 SHALL 提供 `GET /audit/accuracy`（最新报告）与
`GET /audit/accuracy/history`（历史列表），前端新增审计页展示。

#### Scenario: Web 查看审计
- **WHEN** 审计已跑且用户打开 /audit 页面
- **THEN** 页面展示三类审计结果、样本数、生成时间与数据新鲜度标记

#### Scenario: 禁止伪造指标
- **WHEN** 审计任一环节无法获得真实行情/财报数据
- **THEN** 对应字段输出 null 并标注数据缺失，绝不以合成值填充
