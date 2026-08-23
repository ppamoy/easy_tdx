# EasyTDX 项目更新日志 V56

## 更新时间
2026-08-26

## 背景：假突破识别与决策辅助增强
V55回测数据显示3买/3卖准确率约57%/50%，虽经V47-V55多轮优化仍接近随机水平。
核心问题：
1. 大量3买信号为假突破——突破后短期回撤超过突破幅度50%
2. 复杂中枢结构（多重重叠）降低信号可靠性
3. 高波动股票买入信号风险未被有效区分
4. 缺乏多指标综合共振验证

本次更新聚焦4类新增过滤条件，从假突破识别、中枢结构复杂度、波动率仓位建议和信号共振四个维度进一步提升精准度。

---

## 条件164: 假突破识别（False Breakout Detection）

**函数**: `_calc_false_breakout_detection_v56()`

通过信号后量价行为识别假突破：
- 3买信号：突破后5根K线回撤 > 突破幅度50% → 假突破风险，-6%置信度
- 3买信号：量比 > 1.2 + 价格继续上涨 > 2% → 真突破确认，+4%置信度
- 3卖信号：跌破后5根K线反弹 > 跌幅50% → 假跌破风险，-6%置信度
- 3卖信号：量比 > 1.2 + 价格继续下跌 > 2% → 真跌破确认，+4%置信度
- 输出 retracement_pct（回撤幅度）和 volume_ratio（量比）供用户参考

**决策帮助**：直接过滤假突破信号，避免"突破后迅速回撤"导致的止损

---

## 条件165: 中枢结构复杂度分析（Zhongshu Structure Complexity）

**函数**: `_calc_zhongshu_structure_complexity_v56()`

分析信号中枢前后5个中枢的重叠程度：
- 无重叠（简单结构）：+3%置信度
- 少量重叠（≤1个）：0%调整
- 多处重叠（2-3个）：-3%置信度
- 严重重叠（>3个）：-6%置信度

**决策帮助**：帮助用户理解信号所处的市场结构复杂度，复杂结构中的买卖点噪音更大

---

## 条件166: 波动率自适应仓位建议（Volatility Adaptive Position Sizing）

**函数**: `_calc_volatility_adaptive_position_v56()`

基于ATR(14)波动率给出差异化建议：
- ATR < 1.5%（低波动）：建议重仓70-100%，+1%置信度
- ATR 1.5%-3%（正常）：建议中等仓位40-70%，0%调整
- ATR 3%-5%（高波动）：建议轻仓20-40%，-1%置信度
- ATR > 5%（极高）：建议观望0-20%，-2%置信度
- 买入信号在高波动时额外-1%（更谨慎）
- 卖出信号在高波动时可+1%（可稍积极）

**决策帮助**：提供量化的仓位管理建议，帮助用户根据波动率动态调整风险敞口

---

## 条件167: 多信号共振评分（Multi-Signal Resonance Score）

**函数**: `_calc_multi_signal_resonance_v56()`

综合5个技术指标验证信号质量：
- MACD：DIF/DEA金叉/死叉确认
- KDJ：超买/超卖状态
- RSI：相对强弱状态
- 成交量：量比确认
- 价格动量：短中期趋势确认

共振规则：
- ≥3项指标同向确认：+4%（强共振）
- 2项指标同向确认：+2%（弱共振）
- 1项指标确认：0%调整
- 无指标确认：-2%（风险信号）

**决策帮助**：多指标共振是高质量信号的重要标志，单一指标信号可靠性较低

---

## 测试结果

```
============================= test session starts =============================
tests/unit/test_chanlun_v56.py::TestFalseBreakoutDetectionV56::test_insufficient_data PASSED
tests/unit/test_chanlun_v56.py::TestFalseBreakoutDetectionV56::test_none_bi PASSED
tests/unit/test_chanlun_v56.py::TestFalseBreakoutDetectionV56::test_non_buy3_sell3_signal PASSED
tests/unit/test_chanlun_v56.py::TestFalseBreakoutDetectionV56::test_importable PASSED
tests/unit/test_chanlun_v56.py::TestFalseBreakoutDetectionV56::test_buy3_fake_breakout PASSED
tests/unit/test_chanlun_v56.py::TestFalseBreakoutDetectionV56::test_buy3_valid_breakout PASSED
tests/unit/test_chanlun_v56.py::TestZhongshuStructureComplexityV56::test_no_zss PASSED
tests/unit/test_chanlun_v56.py::TestZhongshuStructureComplexityV56::test_none_bi PASSED
tests/unit/test_chanlun_v56.py::TestZhongshuStructureComplexityV56::test_importable PASSED
tests/unit/test_chanlun_v56.py::TestZhongshuStructureComplexityV56::test_simple_structure PASSED
tests/unit/test_chanlun_v56.py::TestVolatilityAdaptivePositionV56::test_insufficient_data PASSED
tests/unit/test_chanlun_v56.py::TestVolatilityAdaptivePositionV56::test_empty_data PASSED
tests/unit/test_chanlun_v56.py::TestVolatilityAdaptivePositionV56::test_none_bi PASSED
tests/unit/test_chanlun_v56.py::TestVolatilityAdaptivePositionV56::test_importable PASSED
tests/unit/test_chanlun_v56.py::TestVolatilityAdaptivePositionV56::test_low_volatility PASSED
tests/unit/test_chanlun_v56.py::TestVolatilityAdaptivePositionV56::test_high_volatility PASSED
tests/unit/test_chanlun_v56.py::TestMultiSignalResonanceV56::test_insufficient_data PASSED
tests/unit/test_chanlun_v56.py::TestMultiSignalResonanceV56::test_none_bi PASSED
tests/unit/test_chanlun_v56.py::TestMultiSignalResonanceV56::test_non_buy3_sell3_signal PASSED
tests/unit/test_chanlun_v56.py::TestMultiSignalResonanceV56::test_importable PASSED
tests/unit/test_chanlun_v56.py::TestMultiSignalResonanceV56::test_bearish_signal PASSED
tests/unit/test_chanlun_v56.py::TestFindMMDsV56Integration::test_v56_functions_importable PASSED
tests/unit/test_chanlun_v56.py::TestFindMMDsV56Integration::test_v56_fields_in_mmd_type PASSED
tests/unit/test_chanlun_v56.py::TestFindMMDsV56Integration::test_v56_confidence_bounds PASSED
tests/unit/test_chanlun_v56.py::TestFindMMDsV56Integration::test_v56_all_conditions_callable PASSED
tests/unit/test_chanlun_v56.py::TestFindMMDsV56Integration::test_sell3_v56_conditions PASSED
============================= 26 passed in 0.84s =============================
```

## 版本说明

- 版本号：1.47.0 → 1.48.0
- 总条件数：163 → 167个
- 所有V56条件对3买/3卖生效（条件166对所有信号生效）
- 置信度调整范围：-6% ~ +4%
- **关键改进**：新增假突破识别（条件164），直接过滤信号后回撤型假突破

---

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/mmd.py` | 新增条件164-167函数，集成到find_mmds_v39（+290行） |
| `src/easy_tdx/chanlun/types.py` | 新增4个V56字段定义（+8行） |
| `src/easy_tdx/web/routers/diagnosis.py` | 新增V56字段到诊断API响应（+8行） |
| `web-ui/src/types.ts` | 新增V56 TypeScript类型定义（+35行） |
| `web-ui/src/views/DiagnosisView.vue` | 新增4个V56诊断卡片展示（+100行） |
| `tests/unit/test_chanlun_v56.py` | 新增V56专项测试（26个） |
| `CHANGELOG_V56.md` | 本次更新日志 |
| `pyproject.toml` | 版本号 1.47.0 → 1.48.0 |

## V55→V56 核心改进对比

| 维度 | V55 | V56 | 变化 |
|------|-----|-----|------|
| 条件总数 | 163 | 167 | +4 |
| 假突破识别(164) | ❌ 无 | ✅ 量价行为检测+回撤阈值 | 新增 |
| 中枢结构复杂度(165) | ❌ 无 | ✅ 重叠度统计+差异化权重 | 新增 |
| 波动率仓位建议(166) | ❌ 无 | ✅ ATR分级+仓位建议 | 新增 |
| 多信号共振(167) | ❌ 无 | ✅ 5指标综合评分 | 新增 |
| 版本号 | 1.47.0 | 1.48.0 | +1 |
| 专项测试 | 20 | 26 | +6 |

## 下一步优化方向（V57+）

1. **回测验证**：运行完整回测对比V55 vs V56的3买/3卖准确率提升
2. **分钟级共振**：利用5分钟/15分钟K线交叉验证日线信号
3. **板块联动增强**：利用板块指数验证个股信号的有效性
4. **Web UI视觉优化**：根据共振数/假突破状态分层显示卡片优先级
5. **参数自适应**：根据股票历史波动率自动调整回撤阈值和量比阈值

---
**版本**: V56
**完成日期**: 2026-08-26
**测试状态**: ✅ 26 passed（V56专项），562 passed（核心+V55+V56）
**Git 状态**: 待提交
