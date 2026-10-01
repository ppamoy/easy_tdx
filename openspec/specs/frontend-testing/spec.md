# frontend-testing Specification

## Purpose
由 change easy-tdx-v386-quality-hardening 归档生成（V-33 收官，2026-09-30）。
## Requirements
### Requirement: 前端测试框架
系统 SHALL 在 web-ui 中引入 vitest 作为统一测试运行器，并支持对 .ts 纯函数与 .vue 单文件组件编写测试。

#### Scenario: 运行纯函数测试
- **WHEN** 开发者在 web-ui 目录执行测试命令
- **THEN** grading 目录下已有的评级用例（迁移到 vitest 后）全部执行并通过

#### Scenario: 运行组件测试
- **WHEN** 测试目标是一个 .vue 组件
- **THEN** vitest 能挂载该组件并断言其渲染输出与交互行为

### Requirement: 关键组件测试覆盖
系统 SHALL 为 V102DecisionCard 组件提供测试，覆盖有完整 V102 建议、字段缺失、无建议三种数据形态的渲染结果。

#### Scenario: 有完整建议
- **WHEN** V102DecisionCard 收到含操作建议、入场、止损、止盈、仓位、RRR 的完整数据
- **THEN** 卡片渲染出全部字段且无空白占位

#### Scenario: 字段缺失
- **WHEN** V102DecisionCard 收到缺失止损或止盈的数据
- **THEN** 卡片以占位符或省略方式安全渲染且不抛异常

#### Scenario: 无建议
- **WHEN** V102DecisionCard 收到无 V102 建议的数据
- **THEN** 卡片渲染「无建议」空态而非报错

### Requirement: 视图冒烟测试
系统 SHALL 为每个视图页提供至少一个冒烟测试，断言其能挂载并渲染关键标题/容器，防止路由级渲染回归。

#### Scenario: 视图挂载
- **WHEN** 任一视图页被挂载
- **THEN** 该视图不抛运行时错误并渲染出预期的根容器或标题

### Requirement: 前端测试接入 CI
系统 SHALL 在 CI 的 frontend job 中运行前端测试与类型检查，使测试失败阻断合并。

#### Scenario: CI 运行前端测试
- **WHEN** 代码推送到 main 或发起 PR
- **THEN** CI 在构建前端的同时运行 vitest，任一测试失败则 job 失败

