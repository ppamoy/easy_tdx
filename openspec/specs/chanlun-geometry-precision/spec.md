# chanlun-geometry-precision Specification

## Purpose
TBD - created by archiving change easy-tdx-v590-three-module-refactor. Update Purpose after archive.
## Requirements
### Requirement: 分型极值精确定位
分型端点必须锚定产生极值的原始 K 线（顶分型取最高点、底分型取最低点）。find_fractals 比较口径使用合并后缠论K线的真实极值来源，bar_index 指向产生极值的那根原始 K 线，val 等于该极值价。本要求为强制约束（MUST）。

#### Scenario: 顶分型落在最高价
- **WHEN** 对含包含关系的合成K线运行 ChanlunAnalyser.process_klines
- **THEN** 每个顶分型的 val 等于其 bar_index 指向原始K线的 high，且 bar_index 为该 K 线实际产生最高点的索引

#### Scenario: 底分型落在最低价
- **WHEN** 同上运行分析
- **THEN** 每个底分型的 val 等于其 bar_index 指向原始K线的 low

### Requirement: 笔端点锚定极值且首尾相连
find_bis 产出的每支笔，start/end 分型 val 必须等于各自锚定原始K线的极值；bi[i].end 与 bi[i+1].start 必须共享同一根 K 线且价格相等。原先静默丢弃真实转折点的过滤（弱笔/趋势一致性/分型稳定性）改为可配置且只降分不丢点。本要求为强制约束（MUST）。

#### Scenario: 笔端点与 K 线极值对齐
- **WHEN** 对任意 K 线运行 find_bis
- **THEN** 对每支笔，start_val 等于 start_index 所在原始K线极值（向上笔起点为低点、向下笔起点为高点），end_val 等于 end_index 所在原始K线极值

#### Scenario: 笔首尾相连
- **WHEN** 生成多支连续笔之后
- **THEN** bi[i].end 与 bi[i+1].start 的 index 和 val 完全相等，方向交替

#### Scenario: 弱笔不再静默删除
- **WHEN** config.bi_weak_skip 关闭或使用默认配置时遇到价格变动很小的转折点
- **THEN** 该转折点仍作为分型保留，笔端点仍取真实极值，仅 quality 打分标记弱笔，不产生悬空端点

### Requirement: 线段端点与特征序列转折点一致
find_xds 每段起点/终点必须是某一支笔的端点分型，且与相邻线段共享转折点。收尾分支不得通过 max/min 重选端点导致与前一段不连续。本要求为强制约束（MUST）。

#### Scenario: 线段端点落在笔端点上
- **WHEN** 得到 ≥2 段线段后逐一校验
- **THEN** 每段 xd.start、xd.end 均等于某支 bi 的端点分型，且 xd[i].end 与 xd[i+1].start 为同一分型

#### Scenario: 线段方向与端点极值一致
- **WHEN** 分析任意形态
- **THEN** 向上线段终点价 > 起点价、向下线段终点价 < 起点价，并且终点类型与方向匹配（向上线段终点为顶分型/高点）

### Requirement: 中枢 zg/zd 与 gg/dd 语义唯一且标注正确
zs 序列化的 zg=重叠区间最高的低点、zd=重叠区间最低的高点、gg=中枢最高、dd=中枢最低。前端按 zg/zd 画中枢矩形、gg/dd 画极值，禁止混用。本要求为强制约束（MUST）。

#### Scenario: 中枢区间正确
- **WHEN** 扫描出多段中枢
- **THEN** 每个 zs 满足 zg > zd、zg <= gg、zd >= dd，且 start_index/end_index 落在构成中枢的笔范围内

#### Scenario: 前端中枢标注无混淆
- **WHEN** ChanlunChart 渲染 zss
- **THEN** 矩形上沿用 zg、下沿用 zd，不在中枢矩形内误用 gg/dd

### Requirement: 买卖点与背驰标注锚定触发笔终点
mmd 的标注点价格改为触发笔终点分型 val（而非 bars 的 low/high 乘偏移）；bc 在主图给出可核对标注并指向触发笔终点，副图仍展示 MACD 依据。本要求为强制约束（MUST）。

#### Scenario: 买点精确落在触发笔终点
- **WHEN** 渲染含 BUY_1/BUY_2/BUY_3 标注的图
- **THEN** 每个买点标注坐标价格等于该触发笔终点分型 val，bar_index 等于该分型 bar_index，不是粗略偏移

#### Scenario: 背驰标注可核对
- **WHEN** 渲染含 bc=true 的背驰
- **THEN** 主图在触发笔终点显示类型与方向，副图对应柱被点亮，二者可对照

