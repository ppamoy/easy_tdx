# backend-coverage Specification

## Purpose
由 change easy-tdx-v386-quality-hardening 归档生成（V-33 收官，2026-09-30）。
## Requirements
### Requirement: 零覆盖策略补测
系统 SHALL 为当前测试目录中零引用的 15 个注册策略（atr_breakout/bbi/bias_reversal/dmi/donchian/ema_cross/emv/keltner/obv_breakout/rsi_divergence/rsi_macd_combo/supertrend/triple_ma/volume_breakout/wr_reversal）提供参数化测试。

#### Scenario: 策略参数校验
- **WHEN** 用合法参数实例化任一零覆盖策略
- **THEN** 策略实例化成功且参数被正确解析

#### Scenario: 策略产生信号
- **WHEN** 向任一零覆盖策略喂入足够长度的合成行情
- **THEN** 策略在回测循环中不抛异常，并产出可序列化的交易记录或明确的无信号状态

#### Scenario: 短数据与空数据边界
- **WHEN** 向策略喂入空数据或短于指标预热期的数据
- **THEN** 策略安全降级为不交易而非崩溃

### Requirement: 零覆盖路由契约测试
系统 SHALL 为当前零测试文件的 Web 路由模块（announcement/block/board_mac/ex_market/finance/fundamental/indicator/mac_data/mac_quotes/realtime/server）提供契约测试。

#### Scenario: 成功响应契约
- **WHEN** 以合法参数调用任一路由
- **THEN** 响应结构符合其 response_model 声明的字段契约

#### Scenario: 错误分支契约
- **WHEN** 以非法参数或空数据调用路由
- **THEN** 路由返回可预期的错误结构而非 500 崩溃

### Requirement: 覆盖率门槛提升
系统 SHALL 将后端覆盖率门槛从 60 提升到 65，并保持 CI 全绿。

#### Scenario: 覆盖率门禁
- **WHEN** CI 运行单元测试并统计覆盖率
- **THEN** 覆盖率低于 65 时 job 失败

#### Scenario: 覆盖率报告
- **WHEN** CI 完成覆盖率统计
- **THEN** 产出可查看的覆盖率报告或摘要，标识未覆盖模块

