# backtest-page Specification

## Purpose
TBD - created by archiving change easy-tdx-v590-three-module-refactor. Update Purpose after archive.
## Requirements
### Requirement: 回测页功能零删减
BacktestView.vue 保持现有单标的回测能力（策略选择、参数、结果、权益曲线、买卖明细）不变，导航收敛后仍可从主导航进入。本要求为强制约束（MUST）。

#### Scenario: 回测可执行
- **WHEN** 在回测页选择策略与参数并运行
- **THEN** 返回与变更前一致的回测结果结构（权益曲线 + 买卖明细 + 指标）

#### Scenario: 子入口可访问
- **WHEN** 回测页内存在组合回测/参数寻优/结果对比等既有子入口
- **THEN** 这些入口仍可访问（保留 URL 或从回测页进入），不因导航收敛而消失

### Requirement: 回测与新导航一致
回测作为三大主导航之首，激活态、页面标题与路由 / 保持一致。本要求为强制约束（MUST）。

#### Scenario: 导航激活
- **WHEN** 当前在 / 回测页
- **THEN** 顶部「回测」导航项高亮

