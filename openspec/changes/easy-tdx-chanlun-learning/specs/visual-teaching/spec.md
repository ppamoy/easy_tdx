## ADDED Requirements
### Requirement: 逐步构建可视化
- 盘感训练图（ChanlunChart）在 reveal 模式下，随 K 线推进动态高亮最近成形的笔、线段、中枢
- 中枢成形瞬间：高亮显示构成中枢的笔区间 + 标注 ZG/ZD/GG/DD
- 买卖点触发瞬间：高亮信号 K 线 + 弹出该点 V102 决策摘要
#### Scenario: 揭示到中枢成形
- **WHEN** 训练揭示推进到某笔使中枢成立（第 3 笔重叠）
- **THEN** 图表高亮该中枢矩形（ZG/ZD 边界），并在旁标注「中枢成形 · 区间 [ZD, ZG]」

### Requirement: 结构构建时间线
- 提供「结构时间线」侧栏：按 index 列出已揭示的分型/笔/中枢事件，点击可跳转
- 时间线仅显示 ≤ revealIndex 的结构，随揭示增长
#### Scenario: 点击时间线跳转
- **WHEN** 用户点击时间线中的「笔 #7（13:30 顶分型起）」
- **THEN** 图表跳转至该笔所在区域（revealIndex 调整）并高亮该笔
