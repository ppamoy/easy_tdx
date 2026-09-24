## ADDED Requirements
### Requirement: 难度分级出题
训练会话服务 SHALL 支持难度分级（easy/medium/hard）出题，且同 seed 出题顺序可复现。强制（MUST）。
- `POST /api/v1/chanlun/train/session` 接受 `difficulty: easy|medium|hard` 与 `seed: int`
- 后端按候选点特征打分：easy = 高置信度买卖点（conf ≥ 0.8）或无干扰项；medium = 常规信号；hard = 低置信度信号 + 分型干扰项密集
- 同 (code, category, difficulty, seed) 出题顺序可复现
#### Scenario: 选择困难模式
- **WHEN** 用户在训练配置选「困难」并开始训练
- **THEN** 候选点以低置信度信号和分型干扰项为主，且用相同 seed 重开时出题顺序一致

### Requirement: 随机标的选择
训练配置 SHALL 提供「随机标的」能力，从当前周期可交易代码池随机选择并回填 code 输入。强制（MUST）。
- 训练配置提供「随机标的」按钮：从当前周期可交易代码池随机选一只（前端本地池即可，池可配）
- 随机后 code 输入框同步更新，可再手动改回
#### Scenario: 随机选标的
- **WHEN** 用户点击「🎲 随机标的」
- **THEN** code 变为池中随机 6 位代码（如 600519），页面刷新训练数据
