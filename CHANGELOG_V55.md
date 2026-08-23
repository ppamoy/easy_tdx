# EasyTDX 项目更新日志 V55

## 更新时间
2026-08-26

## 背景：多时间框架共振与弱势股风险识别
V54回测数据显示3买准确率已达65%+，但仍存在两类误判场景：
1. 信号发出后短期动能与中长期趋势冲突（假突破）
2. 弱势股（低流动性+高波动+连续下跌）的买入信号可靠性低

本次更新聚焦2类新增维度：
1. 多时间框架共振过滤（条件160）—— 识别信号与趋势的一致性
2. 中枢级别权重自适应（条件161）—— 不同级别中枢给予差异化置信度
3. 弱势股专项风险检测（条件162）—— 针对低流动性/高波动股票的风险降级
4. 信号趋势对齐验证（条件163）—— 顺势/逆势买卖点分类验证

---

## 条件160: 多时间框架共振过滤（Multi-Timeframe Resonance Filter）

**函数**: `_calc_multi_tf_resonance_filter_v55()`

通过日线K线内部结构模拟多时间框架共振：
- 信号后短期动能（5根K线）与中长期动能（20根K线）方向一致 → 共振确认 +3% ✅
- 短期与中长期动能方向相反 → 时间框架冲突 -5% 🚨
- 仅一个时间框架支持 → 部分共振 +1%

**决策帮助**：直接识别信号与趋势的一致性，过滤短期假突破信号

---

## 条件161: 中枢级别权重自适应（Zhongshu Level Weight Adaptation）

**函数**: `_calc_zhongshu_level_weight_v55()`

根据突破中枢的笔数赋予不同置信度权重：
- 小级别中枢（≤3笔）：+2%
- 日线级别中枢（4-7笔）：+4%
- 周线级别中枢（8-12笔）：+6%
- 月线级别中枢（≥13笔）：+8%
- 完成中枢额外+1分

**决策帮助**：大级别中枢突破的3买/3卖信号可信度更高，应给予更多权重

---

## 条件162: 弱势股专项风险检测（Weak Stock Risk Detection）

**函数**: `_calc_weak_stock_risk_v55()`

针对招商银行、长江电力等弱势特征股票进行专项检测：
- ATR/价格 > 3% → 高波动风险 +2分
- 近期成交量 < 20日均量×0.6 → 低流动性风险 +2分
- 价格处于近60日20%分位以下 → 价格弱势 +2分
- 连续下跌 > 5天 → 弱势确认 +2分

对买入信号：风险越高置信度扣减越大（最多-8%）
对卖出信号：弱势特征越多卖出越可靠（最多+5%）

**决策帮助**：避免在弱势股上过度依赖买入信号，提升3买信号质量

---

## 条件163: 信号与趋势方向对齐验证（Signal Trend Alignment Validation）

**函数**: `_calc_signal_trend_alignment_v55()`

验证买卖点信号是否与当前主要趋势方向一致：
- 上升趋势中的买入信号 → +2%（顺势买入）✅
- 下降趋势中的卖出信号 → +2%（顺势卖出）✅
- 上升趋势中的卖出信号 → -2%（逆势卖出风险）⚠️
- 下降趋势中的买入信号 → -2%（逆势买入风险）⚠️
- 震荡市中的信号 → 0%（中性）

趋势判断基于：MA5/MA10/MA20/MA60排列状态 + 价格相对MA60位置 + 20日动量

**决策帮助**：顺势信号质量高于逆势信号，帮助用户理解信号背后的趋势环境

---

## 测试结果

```
============================= test session starts =============================
tests/unit/test_chanlun_v55.py::TestMultiTFResonanceFilterV55::test_insufficient_data PASSED
tests/unit/test_chanlun_v55.py::TestMultiTFResonanceFilterV55::test_none_bi PASSED
tests/unit/test_chanlun_v55.py::TestMultiTFResonanceFilterV55::test_non_buy3_sell3_signal PASSED
tests/unit/test_chanlun_v55.py::TestMultiTFResonanceFilterV55::test_importable PASSED
tests/unit/test_chanlun_v55.py::TestZhongshuLevelWeightV55::test_no_zss PASSED
tests/unit/test_chanlun_v55.py::TestZhongshuLevelWeightV55::test_none_bi PASSED
tests/unit/test_chanlun_v55.py::TestZhongshuLevelWeightV55::test_importable PASSED
tests/unit/test_chanlun_v55.py::TestWeakStockRiskV55::test_insufficient_data PASSED
tests/unit/test_chanlun_v55.py::TestWeakStockRiskV55::test_empty_data PASSED
tests/unit/test_chanlun_v55.py::TestWeakStockRiskV55::test_none_bi PASSED
tests/unit/test_chanlun_v55.py::TestWeakStockRiskV55::test_importable PASSED
tests/unit/test_chanlun_v55.py::TestSignalTrendAlignmentV55::test_insufficient_data PASSED
tests/unit/test_chanlun_v55.py::TestSignalTrendAlignmentV55::test_empty_data PASSED
tests/unit/test_chanlun_v55.py::TestSignalTrendAlignmentV55::test_none_bi PASSED
tests/unit/test_chanlun_v55.py::TestSignalTrendAlignmentV55::test_importable PASSED
tests/unit/test_chanlun_v55.py::TestFindMMDsV55Integration::test_v55_functions_importable PASSED
tests/unit/test_chanlun_v55.py::TestFindMMDsV55Integration::test_v55_fields_in_mmd_type PASSED
tests/unit/test_chanlun_v55.py::TestFindMMDsV55Integration::test_v55_confidence_bounds PASSED
tests/unit/test_chanlun_v55.py::TestFindMMDsV55Integration::test_v55_all_conditions_callable PASSED
tests/unit/test_chanlun_v55.py::TestFindMMDsV55Integration::test_sell3_v55_conditions PASSED
============================= 20 passed in 0.68s ==============================
```

## 版本说明

- 版本号：1.46.0 → 1.47.0
- 总条件数：159 → 163个
- 所有V55条件对3买/3卖生效（条件161对所有信号生效）
- 置信度调整范围：-8% ~ +8%
- 新增弱势股检测、趋势对齐验证等决策辅助信息

---

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/mmd.py` | 新增条件160-163函数，集成到find_mmds_v39 |
| `src/easy_tdx/chanlun/types.py` | 新增4个V55字段定义 |
| `src/easy_tdx/web/routers/diagnosis.py` | 新增V55字段到诊断API响应 |
| `web-ui/src/types.ts` | 新增V55 TypeScript类型定义 |
| `web-ui/src/views/DiagnosisView.vue` | 新增4个V55诊断卡片展示 |
| `tests/unit/test_chanlun_v55.py` | 新增V55专项测试（20个） |
| `CHANGELOG_V55.md` | 本次更新日志 |
| `pyproject.toml` | 版本号 1.46.0 → 1.47.0 |

## V54→V55 核心改进对比

| 维度 | V54 | V55 | 变化 |
|------|-----|-----|------|
| 条件总数 | 159 | 163 | +4 |
| 多TF共振(160) | ❌ 无 | ✅ 短中长期动能方向一致性验证 | 新增 |
| 中枢级别权重(161) | ❌ 无 | ✅ 不同级别中枢差异化置信度 | 新增 |
| 弱势股风险(162) | ❌ 无 | ✅ 高波动+低流动性+价格弱势专项检测 | 新增 |
| 趋势对齐验证(163) | ❌ 无 | ✅ 顺势/逆势信号分类验证 | 新增 |
| 版本号 | 1.46.0 | 1.47.0 | +1 |
| 测试通过数 | 1645 | 1665+ | +20 |

## 下一步优化方向（V56+）

1. 运行完整回测，对比V54 vs V55的3买/3卖准确率提升幅度
2. 针对弱势股专项优化（如招商银行、长江电力等样本）
3. 增加分钟级K线共振（5分钟/15分钟K线交叉验证）
4. 优化Web UI展示信号质量分层的视觉优先级
5. 考虑增加板块联动分析（同板块其他股票趋势验证）

---
**版本**: V55
**完成日期**: 2026-08-26
**测试状态**: ✅ 20 passed（V55专项）
**Git 状态**: 待提交
