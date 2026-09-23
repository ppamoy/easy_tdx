# bi-pohuai-default-on Specification

## Purpose
TBD - created by archiving change easy-tdx-chanlun-original-strict. Update Purpose after archive.
## Requirements
### Requirement: 笔破坏默认开启
ChanlunConfig.xd_bi_pohuai 默认值由 False 改为 True。强制（MUST）。
#### Scenario: 默认值
- **WHEN** 构造默认 ChanlunConfig()
- **THEN** xd_bi_pohuai 为 True

### Requirement: 笔破坏语义唯一且可解释
向上线段出现向下笔且其 low 低于线段起点底分型 low（或向下线段出现向上笔 high 高于起点顶分型 high）时，在破坏笔之前结束线段；判定必须可复现。强制（MUST）。
#### Scenario: 向上被向下笔破坏
- **WHEN** 构造向上段后续向下笔跌破起点
- **THEN** 线段在破坏笔之前结束，终点为之前同向笔端点

#### Scenario: 向下被向上笔破坏
- **WHEN** 构造向下段后续向上笔升破起点
- **THEN** 线段在破坏笔之前结束

### Requirement: 金标校准受控
既有受默认 False 影响的线段金标需在更新快照前逐项说明，并把「默认开启」后的结果重新固化；不得未经说明直接全量重写快照。强制（MUST）。
#### Scenario: 校准留痕
- **WHEN** 存在受默认值变更影响的既有断言/快照
- **THEN** 在 change 的 tasks 或变更说明中标出 affected files，并给出更新后的金标值

