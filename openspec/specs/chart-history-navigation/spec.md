# chart-history-navigation Specification

## Purpose
TBD - created by archiving change easy-tdx-changying-chanlun-accuracy. Update Purpose after archive.
## Requirements
### Requirement: 服务端分页取数
`GET /bars` SHALL 新增可选参数 `lookback`（默认 800，上限 20000）：
内部按 ≤800 根一页从最新 bar 向过去循环翻页、按时间戳去重拼接后一次性
返回；响应 SHALL 附带 `total_returned` 与 `earliest_ts` 字段。

#### Scenario: 跨页取 3000 根
- **WHEN** 请求 /bars?lookback=3000 且标的上市 ≥3000 根
- **THEN** 返回 3000 根无重复 bar，earliest_ts 为最早一根的时间戳

#### Scenario: 上市历史不足
- **WHEN** 请求 lookback=5000 但该标的仅上市 1200 根
- **THEN** 返回全部 1200 根且不报错

### Requirement: 图表向前向后加载
所有展示 K 线的页面（回测/选股/学习/看板）SHALL 提供「加载更早」与
「回最新」操作：向左增量拉取更早一页并拼接到图表，向右恢复到最新
窗口；增量加载 MUST 保持当前 dataZoom 视口不跳变。

#### Scenario: 向左加载更早
- **WHEN** 用户在图表点击「加载更早」
- **THEN** 图表左侧新增一批更早 K 线，原视口位置保持，标注重算不丢失

#### Scenario: 回到最新
- **WHEN** 用户点击「回最新」
- **THEN** 图表恢复为最新窗口数据，右侧无缺口

### Requirement: 标注随窗口一致
买卖点/树粮菜标签等标注 SHALL 只对已加载窗口内的数据计算并显示；
窗口变化（加载更多）后标注 MUST 与可见 K 线保持对齐，不出现错位或
残留旧窗口标注。

#### Scenario: 标注对齐
- **WHEN** 图表加载更早历史后
- **THEN** 买卖点标记按新窗口 index 重新定位，无错位
- **THEN** 不再显示已移出窗口的标注

