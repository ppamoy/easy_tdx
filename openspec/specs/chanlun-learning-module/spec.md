# chanlun-learning-module Specification

## Purpose
TBD - created by archiving change easy-tdx-v590-three-module-refactor. Update Purpose after archive.
## Requirements
### Requirement: 单页多 Tab 容器
/learn 作为唯一缠论测试学习入口，Tab 包括：看图分析、理论教学、盘感训练、买卖点实证、进度。切换 Tab 不丢用户上下文。本要求为强制约束（MUST）。

#### Scenario: Tab 导航完整
- **WHEN** 打开 /learn
- **THEN** 可见 5 个 Tab：看图分析、理论教学、盘感训练、买卖点实证、进度，且均有点击内容

#### Scenario: 旧入口兼容
- **WHEN** 访问 /chanlun、/train、/verify
- **THEN** 显示对应 Tab 内容或 302/前端重定向到 /learn 的对应 Tab，不出现空白页

### Requirement: 看图分析 Tab
在页内完成单标的缠论分析：输入代码/周期/区间，展示 ChanlunChart（笔/线段/中枢/买卖点/背驰/分型）与结构统计。本要求为强制约束（MUST）。

#### Scenario: 页内分析
- **WHEN** 用户在看图分析 Tab 输入标的并提交
- **THEN** 同页渲染 ChanlunChart 与 bis/xds/zss/mmds/bcs 结构数量

### Requirement: 理论与盘感训练复用
理论教学使用 TheoryLessons + LessonCard；盘感训练复用既有 TrainView 子组件（难度、随机标的、逐步揭示、V102 建议、错误归因）。本要求为强制约束（MUST）。

#### Scenario: 训练可完成一题
- **WHEN** 在盘感训练 Tab 随机出一题并作答
- **THEN** 揭示答案、给 V102 建议与事后表现，答错时给出正确解读

### Requirement: 买卖点实证复用
买卖点实证 Tab 复用 SignalVerifyView 子组件：标的清单、一次一只、买卖点标注、逐根 K 线揭示、同级别中枢。本要求为强制约束（MUST）。

#### Scenario: 实证逐根揭示
- **WHEN** 打开实证 Tab 选择一只预跑标的
- **THEN** 展示买卖点标注，可下一根/快进逐根揭示买卖点之后的 K 线

### Requirement: 进度与错题
进度 Tab 展示历史成绩曲线、分周期/难度命中率；错题复习可用（MistakesReview）。本要求为强制约束（MUST）。

#### Scenario: 进度可见
- **WHEN** 用户已有训练记录并打开进度 Tab
- **THEN** 显示掌握度矩阵、最近命中率折线与错题列表入口

