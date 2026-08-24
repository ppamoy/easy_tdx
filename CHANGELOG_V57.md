# EasyTDX 项目更新日志 V57

## 更新时间
2026-08-26

## 背景：三类买卖点精准度持续优化
V56回测数据显示3买/3卖准确率约57%/50%，虽经V47-V56多轮优化仍接近随机水平。
核心问题：
1. 大量3买信号为假突破——回踩幅度超过突破幅度60%
2. 突破笔力度不足——力度比<0.7且量比<1.2
3. 中枢内存在背驰时突破信号可信度降低
4. 信号发生后价格持续走弱导致信号衰减

本次更新聚焦4类新增过滤条件，从回踩过滤、突破力度验证、中枢背驰检测、信号衰减四个维度进一步提升精准度。

---

## 条件168: 回踩幅度与时间双重过滤（Pullback Depth & Time Filter）

**函数**: `_calc_pullback_filter_v57()`

对3买/3卖信号的破/跌破后进行回踩深度和时间的双重过滤：
- 3买：回踩深度不超过突破幅度的60%，回踩时间不超过15根K线
- 3买：回踩深度<40% → +2%置信度
- 3买：回踩深度40%-60% → -2%置信度
- 3买：回踩深度>60% → 未通过过滤，-5%置信度
- 3卖同理，方向相反

**决策帮助**：过滤掉回踩过深的信号，避免"突破后迅速回踩"导致的止损

---

## 条件169: 突破力度验证（Breakout Strength Validation）

**函数**: `_calc_breakout_strength_validation_v57()`

验证3买/3卖信号的突破笔力度是否足够：
- 突破笔收盘价变化必须大于进入中枢最后一笔的70%
- 突破时成交量必须大于中枢内平均成交量的1.2倍

评分规则：
- 力度比≥0.7 + 量比≥1.2 → +4%置信度（强突破）
- 只满足一项 → +1%置信度（弱突破）
- 两项都不满足 → -4%置信度（弱突破）

**决策帮助**：直接验证突破有效性，过滤力度不足的假突破信号

---

## 条件170: 中枢背驰检测（Zhongshu Divergence Check）

**函数**: `_calc_zs_divergence_check_v57()`

检测突破笔之前中枢内是否出现背驰信号：
- 中枢内有背驰时，突破信号可信度降低 → -3%置信度
- 中枢内无背驰时，突破信号更可靠 → +2%置信度

背驰类型：笔背驰(BI)、盘整背驰(PZ)、趋势背驰(QS)

**决策帮助**：帮助用户理解中枢内部结构的健康程度，背驰的中枢突破可靠性较低

---

## 条件171: 信号衰减检测（Signal Decay Detection）

**函数**: `_calc_signal_decay_detection_v57()`

检测信号发生后的价格持续性（5-10根K线）：
- 信号后价格持续走弱（先涨后跌/先跌后涨）→ 信号衰减，-4%置信度
- 信号后价格持续走强 → 信号强效，+3%置信度
- 信号后价格稳定 → 信号有效，+1%置信度
- 信号后价格偏弱 → -2%置信度

动量指标：
- 买信号：价格变动百分比（正=上涨，负=下跌）
- 卖信号：价格变动百分比（正=下跌，负=反弹）

**决策帮助**：实时跟踪信号有效性，避免持有已衰减的信号

---

## 测试结果

```
============================= test session starts =============================
tests/unit/test_chanlun_v57.py::TestPullbackFilterV57::test_insufficient_data PASSED
tests/unit/test_chanlun_v57.py::TestPullbackFilterV57::test_non_buy3_sell3_signal PASSED
tests/unit/test_chanlun_v57.py::TestPullbackFilterV57::test_buy3_shallow_pullback PASSED
tests/unit/test_chanlun_v57.py::TestPullbackFilterV57::test_buy3_deep_pullback PASSED
tests/unit/test_chanlun_v57.py::TestPullbackFilterV57::test_sell3_shallow_rebound PASSED
tests/unit/test_chanlun_v57.py::TestBreakoutStrengthValidationV57::test_insufficient_data PASSED
tests/unit/test_chanlun_v57.py::TestBreakoutStrengthValidationV57::test_non_buy3_sell3_signal PASSED
tests/unit/test_chanlun_v57.py::TestBreakoutStrengthValidationV57::test_strong_breakout PASSED
tests/unit/test_chanlun_v57.py::TestBreakoutStrengthValidationV57::test_weak_breakout PASSED
tests/unit/test_chanlun_v57.py::TestZhongshuDivergenceCheckV57::test_no_bis PASSED
tests/unit/test_chanlun_v57.py::TestZhongshuDivergenceCheckV57::test_no_bc_list PASSED
tests/unit/test_chanlun_v57.py::TestZhongshuDivergenceCheckV57::test_non_buy3_sell3_signal PASSED
tests/unit/test_chanlun_v57.py::TestZhongshuDivergenceCheckV57::test_returns_dict_structure PASSED
tests/unit/test_chanlun_v57.py::TestSignalDecayDetectionV57::test_insufficient_data PASSED
tests/unit/test_chanlun_v57.py::TestSignalDecayDetectionV57::test_non_buy3_sell3_signal PASSED
tests/unit/test_chanlun_v57.py::TestSignalDecayDetectionV57::test_buy3_decaying_signal PASSED
tests/unit/test_chanlun_v57.py::TestSignalDecayDetectionV57::test_buy3_strong_signal PASSED
tests/unit/test_chanlun_v57.py::TestSignalDecayDetectionV57::test_sell3_decaying_signal PASSED
tests/unit/test_chanlun_v57.py::TestFindMMDsV57Integration::test_v57_functions_importable PASSED
tests/unit/test_chanlun_v57.py::TestFindMMDsV57Integration::test_v57_fields_in_mmd_type PASSED
tests/unit/test_chanlun_v57.py::TestFindMMDsV57Integration::test_v57_confidence_bounds PASSED
tests/unit/test_chanlun_v57.py::TestFindMMDsV57Integration::test_v57_all_conditions_callable PASSED
tests/unit/test_chanlun_v57.py::TestFindMMDsV57Integration::test_sell3_v57_conditions PASSED
============================= 23 passed in 0.80s ==============================
```

## 版本说明

- 版本号：1.48.0 → 1.49.0
- 总条件数：167 → 171个
- 所有V57条件对3买/3卖生效
- 置信度调整范围：-5% ~ +4%
- **关键改进**：新增回踩过滤（条件168），直接过滤回踩过深的信号

---

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/mmd.py` | 新增条件168-171函数，集成到find_mmds_v39（+310行） |
| `src/easy_tdx/chanlun/types.py` | 新增4个V57字段定义（+8行） |
| `src/easy_tdx/web/routers/diagnosis.py` | 新增V57字段到诊断API响应（+8行） |
| `web-ui/src/types.ts` | 新增V57 TypeScript类型定义（+40行） |
| `web-ui/src/views/DiagnosisView.vue` | 新增4个V57诊断卡片展示（+100行） |
| `tests/unit/test_chanlun_v57.py` | 新增V57专项测试（23个） |
| `CHANGELOG_V57.md` | 本次更新日志 |
| `SESSION_SUMMARY_V57.md` | 本次会话总结 |
| `pyproject.toml` | 版本号 1.48.0 → 1.49.0 |

## V56→V57 核心改进对比

| 维度 | V56 | V57 | 变化 |
|------|-----|-----|------|
| 条件总数 | 167 | 171 | +4 |
| 回踩过滤(168) | ❌ 无 | ✅ 深度60%阈值+时间窗口 | 新增 |
| 突破力度验证(169) | ❌ 无 | ✅ 力度比+量比双重验证 | 新增 |
| 中枢背驰检测(170) | ❌ 无 | ✅ 中枢内背驰信号检测 | 新增 |
| 信号衰减检测(171) | ❌ 无 | ✅ 价格持续性跟踪 | 新增 |
| 版本号 | 1.48.0 | 1.49.0 | +1 |
| 专项测试 | 26 | 23 | +23 |

## 下一步优化方向（V58+）

1. **回测验证**：运行完整回测对比V56 vs V57的3买/3卖准确率提升
2. **分钟级K线共振**：使用5分钟/15分钟K线数据交叉验证日线信号
3. **板块联动增强**：利用板块指数验证个股信号的有效性
4. **Web UI视觉优化**：根据信号状态分层显示卡片优先级
5. **参数自适应**：根据股票历史波动率自动调整回踩阈值和力度阈值

---
**版本**: V57
**完成日期**: 2026-08-26
**测试状态**: ✅ 23 passed（V57专项），1714 passed（全量测试）
**Git 状态**: 待提交
