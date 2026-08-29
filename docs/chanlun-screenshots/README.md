# 缠论 K 线图浏览器实测截图（V83）

用 Playwright（web-ui/scripts/chanlun-screenshot.mjs）打开 /chanlun，等待缠论分析完成后截图。

| 文件 | 说明 |
| --- | --- |
| 000001_DAY_800_full.png | 平安银行 日线 800 根，整图（笔虚线 / 线段实线 / 中枢 / 分型 / 买卖点 / 背驰全量叠加） |
| 000001_DAY_800_zoom.png | 同上，缩放最近 ~140 根，检查买卖点标签可读性 |
| 600519_DAY_500_zoom.png | 贵州茅台 日线 500 根，缩放最近区域 |
| 000001_MIN60_600_zoom.png | 平安银行 60 分钟线 600 根，缩放最近区域 |
| prod_000001_DAY_800.png | 生产构建（web-ui/dist 经 FastAPI 托管，端口 8000）复测 |

验证结论（图表内部状态，读取 echarts getOption）：

- 000001 日线 800 根：笔 133/133 markLine、线段 15/15、中枢 16/16、分型 268、买卖点 17、背驰 35 —— 与后端 /api/v1/chanlun/analyze 计数完全一致；买卖点坐标 0 个越界；console / page 零错误。
- 数据一致性：笔/线段起止日期全部命中分型日期；中枢 dd≤zd≤zg≤gg 且起止落在 K 线窗口内；买卖点/背驰日期均落在 800 根 K 线窗口内。
- 修复要点：ECharts 按需注册补 ScatterChart + MarkAreaComponent（此前分型/买卖点/背驰不可见、中枢无边框）；fetchBars 新增 maxCount，缠论页 K 线窗口与分析窗口对齐（8000 → 800），叠加层不再压缩到右端 10%。
