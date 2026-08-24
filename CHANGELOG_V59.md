# EasyTDX 项目更新日志 V59

## 更新时间
2026-08-26

## 背景：参数自适应与信号质量深度评估
V58引入了多时间框架趋势一致性、量能验证、ATR止损和综合评分四个条件，但所有参数（MA周期、ATR倍数、波动率阈值）都是硬编码的。不同波动率环境的股票应采用不同的参数设置。本次更新聚焦参数自适应和信号质量深度评估。

---

## 条件176: 波动率自适应MA周期（Volatility-Adaptive MA Period）

**函数**: `_calc_volatility_adaptive_ma_v59()`

根据当前股票波动率动态调整MA周期，使均线系统适应市场环境：
- 高波动(>4%)：MA3/MA10/MA30，提高响应速度；-2%置信度（噪音大）
- 低波动(<1%)：MA8/MA30/MA90，减少震荡干扰；+2%置信度（趋势稳定）
- 正常波动(1%-4%)：MA5/MA20/MA60，保持默认

**决策帮助**：避免在市场剧烈波动时使用过长的均线滞后，或在低波动市场过度反应。

---

## 条件177: ATR倍数自适应（ATR Multiplier Adaptation）

**函数**: `_calc_atr_multiplier_adapt_v59()`

根据波动率环境动态调整ATR止损倍数：
- 极高波动(>5%)：3x ATR止损，-2%置信度（风险极高）
- 高波动(3%-5%)：2.5x ATR止损，-1%置信度
- 低波动(<1%)：1.5x ATR止损，+1%置信度（可收紧止损）
- 正常波动：2x ATR止损，0%调整

**决策帮助**：高波动股票自动放宽止损距离避免被洗出，低波动股票收紧止损减少损失。

---

## 条件178: 多时间框架共振信号（Multi-TF Resonance Signal）

**函数**: `_calc_multi_tf_resonance_signal_v59()`

交叉验证日线和短周期（近5根K线）的趋势与动量一致性：
- 短周期涨+中期涨 → 共振强(2分)，+4%置信度
- 仅一级共振 → 共振中(1分)，+1%置信度
- 短周期跌+中期跌 → 强反向(-2分)，-4%置信度（对买信号）
- 仅一级反向 → 弱反向(-1分)，-1%置信度

**决策帮助**：避免在短周期趋势与日线信号冲突时交易，过滤逆势假信号。

---

## 条件179: 信号衰减速度评估（Signal Decay Speed）

**函数**: `_calc_signal_decay_speed_v59()`

测量信号产生后价格远离信号点的速度：
- 快速远离(≥3%) → 强信号，+3%置信度
- 中等远离(1.5%-3%) → 中等信号，+1%置信度
- 缓慢远离(0%-1.5%) → 弱信号，-1%置信度
- 反向运动(<0%) → 假信号，-4%置信度

**决策帮助**：量化信号有效性，区分真突破和假突破。

---

## 测试结果

```
============================= test session starts ==============================
tests/unit/test_chanlun_v59.py::TestVolatilityAdaptiveMAV59::test_insufficient_data PASSED
tests/unit/test_chanlun_v59.py::TestVolatilityAdaptiveMAV59::test_normal_volatility PASSED
tests/unit/test_chanlun_v59.py::TestVolatilityAdaptiveMAV59::test_high_volatility PASSED
tests/unit/test_chanlun_v59.py::TestVolatilityAdaptiveMAV59::test_low_volatility PASSED
tests/unit/test_chanlun_v59.py::TestATRMultiplierAdaptV59::test_normal_volatility PASSED
tests/unit/test_chanlun_v59.py::TestMultiTFResonanceSignalV59::test_strong_resonance_up PASSED
tests/unit/test_chanlun_v59.py::TestMultiTFResonanceSignalV59::test_opposite_resonance PASSED
tests/unit/test_chanlun_v59.py::TestSignalDecaySpeedV59::test_fast_rise_strong_signal PASSED
tests/unit/test_chanlun_v59.py::TestSignalDecaySpeedV59::test_reversal_fake_signal PASSED
tests/unit/test_chanlun_v59.py::TestFindMMDsV59Integration::test_v59_integration_pass PASSED
============================== 31 passed in 0.84s ==============================
全量测试: 1775 passed
```

## 版本说明

- 版本号：1.50.0 → 1.51.0
- 总条件数：175 → 179个
- 所有V59条件对3买/3卖生效
- 置信度调整范围：-4% ~ +4%（单条件最大影响）
- **关键改进**：参数自适应（MA周期+ATR倍数）+ 多TF共振 + 信号衰减速度

---

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/mmd.py` | 新增条件176-179函数，集成到find_mmds_v39（+280行） |
| `src/easy_tdx/chanlun/types.py` | 新增4个V59字段定义（+6行） |
| `src/easy_tdx/web/routers/diagnosis.py` | 新增V59字段到诊断API响应（+8行） |
| `web-ui/src/types.ts` | 新增V59 TypeScript类型定义（+40行） |
| `web-ui/src/views/DiagnosisView.vue` | 新增4个V59诊断卡片展示（+100行） |
| `tests/unit/test_chanlun_v59.py` | 新增V59专项测试（31个） |
| `CHANGELOG_V59.md` | 本次更新日志 |
| `SESSION_SUMMARY_V59.md` | 本次会话总结 |
| `pyproject.toml` | 版本号 1.50.0 → 1.51.0 |

## V58→V59 核心改进对比

| 维度 | V58 | V59 | 变化 |
|------|-----|-----|------|
| 条件总数 | 175 | 179 | +4 |
| 波动率自适应MA(176) | ❌ 无 | ✅ 3/5/8周期自适应 | 新增 |
| ATR倍数自适应(177) | ❌ 固定2x | ✅ 1.5x-3x动态 | 增强 |
| 多TF共振信号(178) | ⚠️ 仅趋势一致 | ✅ 短+中周期交叉验证 | 增强 |
| 信号衰减速度(179) | ❌ 无 | ✅ 价格远离速度评估 | 新增 |
| 版本号 | 1.50.0 | 1.51.0 | +1 |
| 专项测试 | 29 | 31 | +31 |

## 下一步优化方向（V60+）

1. **回测验证**：运行真实股票数据回测，验证V59参数自适应对3买/3卖准确率的实际提升
2. **分钟级K线融合**：引入5分钟/15分钟级别指标（如KDJ/RSI）作为短周期共振的补充
3. **板块联动增强**：利用同板块多只股票的信号一致性增强个股信号可信度
4. **置信度校准模型**：基于历史回测数据，建立条件权重自适应学习机制

---
**版本**: V59
**完成日期**: 2026-08-26
**测试状态**: ✅ 31 passed（V59专项），1775 passed（全量）
**Git 状态**: 待提交
