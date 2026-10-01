# 能力审计：缠论模型/画图 与 长盈选股+择时+历史验证

> V-27 复核（2026-09-30）：「未满足」差距三系已全部落地，见 §1 修订；§2 不变。
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

### ~~未满足~~ → 已满足（V726 起陆续收敛，V-27 复核 2026-09-30）
以下三条差距已在后续版本全部落地（原文保留见 git 历史）：
- **线段多义性/第二特征序列**：`XD_TIEBREAK_EARLIEST` 确定性取舍（V602）+
  缺口待确认 `gap_pending` + 第二特征序列裁决（V730 P1-3/P1-4，第67/71课）+
  收尾同向端点不换取（V725）；金标 `test_chanlun_xd_tail` 等锁定。
- **笔破坏默认开启**：`config.xd_bi_pohuai = True`（bi-pohuai-default-on spec，
  已归档），`test_chanlun_xd_pohuai` 锁定开/关两侧差异。
- **simple 口径收敛**：显式配置时一次性 legacy 告警（bi-type-convergence spec，
  V726 归档），默认 new 不受影响。

**结论（V-27 复核）**：几何/画图精度与结构判定均达原文口径；§1 全部能力要求满足。
§2（长盈选股+择时+历史验证）结论不变，引用测试现 65 项全通过（26.5s 实测）。

## 2. 基本面（长盈模型）选股 + 缠论择时 + 历史数据验证（能力要求）

### 已满足
- 第一步长盈基本面选股池：/stock-pick/screen，fundamental/changying_pool.py、screen/ 评分（树/粮/菜 + 明细 + 排序），并在 Web（StockPickView / Screening）暴露。
- 第二步缠论择时：/stock-pick/timing，对池内做截至目标日的缠论分析（买卖点/背驰/中枢 + 操作建议）；/screening/scan、/screening/evaluate 亦提供选股池与评估。
- 历史数据验证：/screening/verify 调用 backtest/screening_verify.py，给出选股日后前瞻收益/命中率/超额收益；/backtest/run（+optimize/portfolio）提供择时回测；signal-accuracy 提供信号后验。
- 测试证据：test_backtest_screening_verify.py、test_changying_pool.py、test_changying_scanner.py、test_changying_golden.py、test_stock_pick_router.py、test_screening_router.py 等 60 项全通过（约 40s）。

**结论**：能力要求 2（长盈选股 + 择时 + 历史验证）当前可满足。

## 建议下一步（围绕差距）——✅ 全部完成（见 §1 V-27 复核）
1. ✅ 线段多义性确定性选择 + 原文金标（V602/V725/V730，test_chanlun_xd_tail 等）。
2. ✅ 笔破坏默认开启并锁定开/关两侧（bi-pohuai-default-on spec，金标受控更新）。
3. ✅ simple 显式 legacy 标注（bi-type-convergence spec，V726）。
