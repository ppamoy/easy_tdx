# line-segment-original-fidelity Specification

## Purpose
TBD - created by archiving change easy-tdx-chanlun-original-strict. Update Purpose after archive.
## Requirements
### Requirement: 线段结束采用「第一特征序列分型」为主口径
向上线段以「向下特征序列顶分型」结束，向下线段以「向上特征序列底分型」结束；分型需在包含处理后判断。结束点必须是某支笔的端点分型，并与相邻线段共享转折点。强制（MUST）。
#### Scenario: 特征序列分型结束线段
- **WHEN** 对含标准特征序列的笔序列运行 find_xds
- **THEN** 线段终点由特征序列分型中间元素之前的同向笔终点确定，且与下一线段起点共享同一分型

### Requirement: 多义性做「确定性取舍」而非静默 max/min
当第一特征序列分型存在多个等价结束候选（多义性）时，须按统一确定性规则选终点（例如「最早确认、且后续特征不否定」），同一输入永远同一输出，禁止用收尾 max/min 重选导致与前端不连续。强制（MUST）。
#### Scenario: 多候选确定性
- **WHEN** 同一序列出现两个合法结束位置
- **THEN** 返回结果与再次运行时完全一致，且端点仍落在笔端点分型上、相邻线段共享转折点

### Requirement: 第二特征序列作为否定/确认
在第一特征序列分型成立但存在缺口或需确认时，依据缠论原文的第二特征序列逻辑决定是否结束；未实现部分须在代码注释中显式标注「TODO/原文分歧」，不得静默近似。强制（MUST）。
#### Scenario: 缺口 + 第二特征确认
- **WHEN** 特征序列出现区间缺口
- **THEN** 依据第二特征确认后才结束；否则继续，最终仍保证确定性

### Requirement: 收尾不换取端点
序列收尾（数据用尽）时线段终点取「最后已完成且方向一致的同向笔分型」，不得用 max/min 换出非共享端点。强制（MUST）。
#### Scenario: 收尾端点
- **WHEN** 数据末尾为向上段
- **THEN** 线段终点为最后仍符合方向的上同向笔终点分型，且该端点必为某笔分型，不与前段断裂

