# 能力审计：缠论模型/画图 与 长盈选股+择时+历史验证

> 生成依据：交叉核对 openspec 文档
> （openspec/changes/easy-tdx-v590-three-module-refactor/specs 下的
> chanlun-geometry-precision、stock-selection-module，以及
> easy-tdx-chanlun-learning/specs/signal-backtest-verification）
> 与代码/测试。

## 1. 缠论模型与缠论画图（能力要求：基于缠论原文，非简化版）

### 已满足（几何锚定 / 标注精度）
- **分型/笔/线段/中枢/买卖点/背驰几何锚定**：端点必须落在产生极值的原始K线上（bar_index/val），笔首尾相连、线段端点共享（几何精度 spec 的 MUST 均有金标）。
- **多级别递归**：低级别线段作为高级别笔，输出 levels.bi / levels.xd。
- **走势段/趋势段**：zsds/qsds 模型与绘制。
- **图表展示控制**：走势段/趋势段、分型、买卖点、背驰、中枢显隐开关，买卖点文字标注，紧凑线宽，空 series 优化，tooltip/图例。
- **网站联动**：URL 同步、显隐偏好 localStorage 持久化、复制分享链接。

### 未满足（结构判定仍为简化版 —— 明确差距）
- src/easy_tdx/chanlun/xd.py 顶部自述：线段为「特征序列 + 包含处理」的标准简化实现，未覆盖原文的「笔破坏」与「多义性」全部情形。
- 笔破坏虽提供 xd_bi_pohuai 开关，但默认关闭。
- 缠论原文的线段多义性 / 第二特征序列 / 严格第一特征与笔破坏的完整判定尚未实现。
- 笔类型仍含 new/old/simple，simple 属明显简化。

**结论**：几何/画图精度达标；但「结构判定给出严格原文完整版」当前不满足，需继续实现线段多义性、默认开启并校准笔破坏，以及剔除 simple 简化口径。

## 2. 基本面（长盈模型）选股 + 缠论择时 + 历史数据验证（能力要求）

### 已满足
- 第一步长盈基本面选股池：/stock-pick/screen，fundamental/changying_pool.py、screen/ 评分（树/粮/菜 + 明细 + 排序），并在 Web（StockPickView / Screening）暴露。
- 第二步缠论择时：/stock-pick/timing，对池内做截至目标日的缠论分析（买卖点/背驰/中枢 + 操作建议）；/screening/scan、/screening/evaluate 亦提供选股池与评估。
- 历史数据验证：/screening/verify 调用 backtest/screening_verify.py，给出选股日后前瞻收益/命中率/超额收益；/backtest/run（+optimize/portfolio）提供择时回测；signal-accuracy 提供信号后验。
- 测试证据：test_backtest_screening_verify.py、test_changying_pool.py、test_changying_scanner.py、test_changying_golden.py、test_stock_pick_router.py、test_screening_router.py 等 60 项全通过（约 40s）。

**结论**：能力要求 2（长盈选股 + 择时 + 历史验证）当前可满足。

## 建议下一步（围绕差距）
1. 实现缠论线段多义性确定性选择（严格第一特征 + 第二特征序列），并补充原文金标。
2. 将笔破坏默认开启并校准默认行为（会改变既有金标，需逐项复核）。
3. 移除或显式标注 simple 笔口径，保持原文口径唯一。
