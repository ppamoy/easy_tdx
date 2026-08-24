# EasyTDX 项目更新日志 V61

## 更新时间
2026-08-27

## 背景：技术指标融合与综合决策评分
V60引入了RSI背离、MA间距、中枢距离和KDJ确认四个独立条件，但缺乏多指标融合和综合决策评分。本次更新聚焦两个核心改进：MACD柱状图背离与RSI背离的融合验证，以及跨V58-V61所有条件的综合质量评分系统。

---

## 条件184: MACD柱状图背离融合（MACD Histogram Divergence Fusion）

**函数**: `_calc_macd_histogram_divergence_v61()`

检测价格与MACD柱状图的背离信号，并与RSI背离进行融合确认：
- 深度底背离（价格新低+MACD柱未新低）→ 强烈确认3买
- 深度顶背离（价格新高+MACD柱未新高）→ 强烈确认3卖
- 与RSI背离双确认 → 额外+2%置信度（融合加成）
- 无背离且价格创新高/低 → -1%置信度

**决策帮助**：双指标背离确认比单一指标更可靠，融合机制显著提升信号可信度。

---

## 条件185: 综合多信号评分（Composite Signal Score）

**函数**: `_calc_composite_signal_score_v61()`

聚合V58-V61所有条件的置信度调整，生成综合质量评分：
- S级（≥75%）：金色边框，强烈推荐
- A级（≥60%）：绿色边框，建议操作
- B级（≥45%）：蓝色边框，可考虑
- C级（≥30%）：橙色边框，谨慎操作
- D级（<30%）：红色边框，不建议操作

包含：
- 综合评分（0~100%）
- 有效条件数统计
- 各条件贡献明细
- 自动决策建议文本
- 颜色等级可视化

**决策帮助**：用户一目了然看到信号质量等级，快速判断是否值得操作。

---

## 测试结果

```
============================= test session starts ==============================
tests/unit/test_chanlun_v61.py::TestMACDHistogramDivergenceV61::test_insufficient_data PASSED
tests/unit/test_chanlun_v61.py::TestMACDHistogramDivergenceV61::test_non_buy3_sell3_signal PASSED
tests/unit/test_chanlun_v61.py::TestMACDHistogramDivergenceV61::test_basic_structure_buy3 PASSED
tests/unit/test_chanlun_v61.py::TestMACDHistogramDivergenceV61::test_basic_structure_sell3 PASSED
tests/unit/test_chanlun_v61.py::TestMACDHistogramDivergenceV61::test_confidence_bounds PASSED
tests/unit/test_chanlun_v61.py::TestMACDHistogramDivergenceV61::test_rsi_fusion_fields PASSED
tests/unit/test_chanlun_v61.py::TestMACDHistogramDivergenceV61::test_msg_format PASSED
tests/unit/test_chanlun_v61.py::TestCompositeSignalScoreV61::test_basic_structure PASSED
tests/unit/test_chanlun_v61.py::TestCompositeSignalScoreV61::test_quality_tier_s PASSED
tests/unit/test_chanlun_v61.py::TestCompositeSignalScoreV61::test_quality_tier_d PASSED
tests/unit/test_chanlun_v61.py::TestCompositeSignalScoreV61::test_quality_tier_colors PASSED
tests/unit/test_chanlun_v61.py::TestCompositeSignalScoreV61::test_recommendation_map PASSED
tests/unit/test_chanlun_v61.py::TestCompositeSignalScoreV61::test_sell3_composite PASSED
tests/unit/test_chanlun_v61.py::TestCompositeSignalScoreV61::test_no_conditions PASSED
tests/unit/test_chanlun_v61.py::TestCompositeSignalScoreV61::test_breakdown_format PASSED
tests/unit/test_chanlun_v61.py::TestFindMMDsV61Integration::test_v61_functions_importable PASSED
tests/unit/test_chanlun_v61.py::TestFindMMDsV61Integration::test_v61_fields_in_mmd_type PASSED
tests/unit/test_chanlun_v61.py::TestFindMMDsV61Integration::test_v61_confidence_bounds PASSED
tests/unit/test_chanlun_v61.py::TestFindMMDsV61Integration::test_v61_all_conditions_callable PASSED
tests/unit/test_chanlun_v61.py::TestFindMMDsV61Integration::test_sell3_v61_conditions PASSED
tests/unit/test_chanlun_v61.py::TestFindMMDsV61Integration::test_v61_integration_pass PASSED
============================== 21 passed in 1.60s ==============================
V59+V60+V61 合计: 79 passed
```

## 版本说明

- 版本号：1.52.0 → 1.53.0
- 总条件数：183 → 185个
- 所有V61条件对3买/3卖生效
- 置信度调整范围：-1% ~ +6%（单条件最大影响，含融合加成）
- **关键改进**：MACD+RSI双指标背离融合 + 综合质量等级评分

---

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/mmd.py` | 新增条件184-185函数，集成到find_mmds_v39（+336行） |
| `src/easy_tdx/chanlun/types.py` | 新增2个V61字段定义（+4行） |
| `src/easy_tdx/web/routers/diagnosis.py` | 新增V61字段到诊断API响应（+4行） |
| `web-ui/src/types.ts` | 新增V61 TypeScript类型定义（+25行） |
| `web-ui/src/views/DiagnosisView.vue` | 新增V61诊断卡片展示（+46行） |
| `tests/unit/test_chanlun_v61.py` | 新增V61专项测试（21个） |
| `CHANGELOG_V61.md` | 本次更新日志 |
| `pyproject.toml` | 版本号 1.52.0 → 1.53.0 |

## V60→V61 核心改进对比

| 维度 | V60 | V61 | 变化 |
|------|-----|-----|------|
| 条件总数 | 183 | 185 | +2 |
| MACD背离融合(184) | ❌ 无 | ✅ RSI+MACD双指标融合 | 新增 |
| 综合评分(185) | ❌ 无 | ✅ S/A/B/C/D五级质量分层 | 新增 |
| 版本号的 | 1.52.0 | 1.53.0 | +1 |
| 专项测试 | 27 | 21 | +21 |
| V59+V60+V61合计 | 58 | 79 | +21 |

## 下一步优化方向（V62+）

1. **BOLL带宽确认**：利用BOLL带宽判断突破有效性，过滤假突破信号
2. **回测验证框架**：建立系统化回测流程，量化验证V58-V61条件的实际准确率提升
3. **动态阈值自适应**：根据市场波动率动态调整各条件的阈值参数
4. **多股票对比分析**：在同一诊断页面展示多只股票的信号质量对比

---
**版本**: V61
**完成日期**: 2026-08-27
**测试状态**: ✅ 21 passed（V61专项），79 passed（V59+V60+V61合计）
**构建状态**: 需重新构建 web-ui（npm run build）
