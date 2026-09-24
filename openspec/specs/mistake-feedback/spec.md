# mistake-feedback Specification

## Purpose
TBD - created by archiving change easy-tdx-chanlun-learning. Update Purpose after archive.
## Requirements
### Requirement: 错题正确解读
答错时答案面板 SHALL 展示「正确解读」区块，含真实信号类型与置信度、V102 建议方向、事后 20 日实际表现。强制（MUST）。
- 用户答错时，答案面板除对错标记外，额外展示「正确解读」区块
- 解读内容由后端候选点 `signal.explanation` 提供（由 mmd.msg + V102 决策支持拼接）
- 解读至少包含：真实信号类型与置信度、V102 建议方向、事后 20 日实际表现一句话
#### Scenario: 买入判断错误
- **WHEN** 用户对某候选点选择「买入」，但缠论引擎为卖出信号
- **THEN** 展示「正确解读：模型识别为 1卖（置信度 92%），V102 建议卖出，事后 20 日 -6.3%，你的买入判断与模型方向相反」

### Requirement: 错题入集
系统 SHALL 在答错时自动将错题写入错题集，记录标的/周期/难度/日期/信号类型/用户选择/实际方向/解读。强制（MUST）。
- 每次答错自动写入错题集（`POST /learn/mistakes` 或随 score 一并提交）
- 错题集含 symbol/category/difficulty/日期/信号类型/用户选择/实际方向/解读
#### Scenario: 错题进入复习列表
- **WHEN** 用户完成一次训练（含 3 道错题）
- **THEN** /learn 的「错题复习」列表新增 3 条记录，可按周期/难度筛选

