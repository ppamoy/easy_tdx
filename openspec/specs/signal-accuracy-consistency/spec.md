# signal-accuracy-consistency Specification

## Purpose
TBD - created by archiving change easy-tdx-changying-chanlun-accuracy. Update Purpose after archive.
## Requirements
### Requirement: 单一信号收益实现
系统 SHALL 提供 `web/signal_ledger.py :: signal_returns()` 作为信号→
N 根收益的唯一实现；缠论信号质量面板、accuracy 审计、回测成交对账
MUST 全部调用该实现，禁止各自重复实现口径。

#### Scenario: 同源输出
- **WHEN** 面板与审计报告对同一信号列表取数
- **THEN** 两处输出的命中率与收益明细逐值一致

### Requirement: 对账单测护栏
单测 SHALL 固化「同一输入两处消费必须一致」的对账断言：面板聚合函数与
审计聚合函数对同一 fixture 的输出差异 MUST 为 0，防止后续口径漂移。

#### Scenario: 口径漂移被拦截
- **WHEN** 任一处实现修改了收益计算方式
- **THEN** 对账单测失败并指出两处输出差异

