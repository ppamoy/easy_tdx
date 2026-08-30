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

---

# 长赢基本面选股截图（V85–V89）

用 Playwright（web-ui/scripts/fundamental-scan-screenshot.mjs）打开 /fundamental，运行选股/批量验证/全市场扫描后截图。

| 文件 | 说明 |
| --- | --- |
| fundamental_config.png | 单日选股配置（历史日期 + 自选池 + 类型） |
| fundamental_result.png | 单日选股结果表（EPS/ROE/毛利率/负债率/同比/后续收益） |
| fundamental_detail.png | 单行展开树粮菜三张打分明细 |
| verify_config.png | 批量时点验证配置（多日期 + 自选池） |
| verify_result.png | 批量验证汇总（α/跑赢徽章 + 按分类统计表） |
| scan_config_result.png | V88 全市场扫描：5550 只全市场扫描，树 280/粮 4249/菜 942，Top 50 结果表 + 季节卡 + 统计栏 |
| scan_detail.png | V88 全市场扫描行展开树粮菜打分明细 |
| v89_scan_cache.png | V89 全市场扫描（缓存命中）：统计栏 💾 财报缓存徽章（3 期 / 3.9MB），50 行结果表 + 季节卡 + 明细展开，console 零错误 |
| v90_train_leaderboard.png | V90 训练排行榜：学员/得分/命中率/标的/周期 排名表，前三名高亮，console 零错误 |
| v91_sina_fallback.png | V91 全市场扫描新浪补充：2019-11-15 gpcw 无覆盖时 3 只自选池全部由新浪产出（数据源列橙色「新浪」徽章），console 零错误 |

V88 全市场扫描验证要点（/fundamental → 🔭 全市场扫描，2026-09-01，沪+深）：

- 全市场扫描 5550 只（gpcw 2026Q2 全量），by_category 树 280 / 粮 4249 / 菜 942
- 结果表 Top 50 正常渲染（截断 +5421 提示），季节「春季·播种期」卡片正确
- 首行明细展开：🌳49 / 🌾100 / 🥬30 三张明细卡，字段与 API 一致；console / page 零错误