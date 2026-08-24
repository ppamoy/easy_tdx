# EasyTDX 项目更新日志 V60

## 更新时间
2026-08-27

## 背景：技术指标深度确认增强
V59引入了波动率自适应MA和ATR倍数，但缺乏对RSI背离、MA排列间距、中枢距离和KDJ超买超卖状态的深度确认。本次更新聚焦多维度技术指标验证，通过RSI背离检测、MA间距评分、中枢距离增强和KDJ确认四个条件进一步提升买卖点判断精准度。

---

## 条件180: RSI深度背离过滤（RSI Deep Divergence Filter）

**函数**: `_calc_rsi_deep_divergence_v60()`

检测价格与RSI的深度背离信号：
- 深度底背离（3买）：价格创新低但RSI未创新低，按价格新低幅度分档：
  - 深度(>5%) → +4%置信度
  - 中度(2%-5%) → +2%置信度
  - 浅度(<2%) → +1%置信度
- 深度顶背离（3卖）：价格创新高但RSI未创新高，同档位+4%/+2%/+1%
- 无背离且价格创新低/高 → -1%置信度

**决策帮助**：背离是趋势反转的早期信号，深度背离比轻微背离更可靠。

---

## 条件181: MA排列间距强度评分（MA Alignment Spacing Score）

**函数**: `_calc_ma_spacing_strength_v60()`

计算MA5/MA20/MA60之间的间距比例，评估均线排列健康程度：
- 多头排列间距大(>3%) → 强趋势，+3%置信度
- 多头排列间距中(1.5%-3%) → 中等趋势，+1.5%置信度
- 多头排列间距小(<1.5%) → 弱趋势，+0.5%置信度
- 均线纠缠 → -2%置信度（不确定性强）
- 空头排列 → -3%置信度（对3买/3卖均不利）

**决策帮助**：均线间距是趋势强度的直接度量，间距越大趋势越可靠。

---

## 条件182: 中枢支撑/阻力距离评分增强（ZhongShu Distance Score Enhanced）

**函数**: `_calc_zs_distance_enhanced_v60()`

在中枢距离评分基础上增加多维度评估：
- 价格位置分类：above_zs / inside_zs / below_zs
- 突破/跌破后回踩/反弹确认检测（最近10根K线）
- 距离中枢上沿/下沿的百分比
- 中枢宽度与价格波动的关系
- 3买：刚突破(<5%) → +2%，距离过远(>15%) → -1%
- 3卖：刚跌破(<5%) → +2%，距离过远(>15%) → -1%
- 回踩确认后额外+2%

**决策帮助**：区分有效突破和假突破，回踩确认显著提升信号可信度。

---

## 条件183: KDJ超买超卖确认（KDJ Overbought/Oversold Confirmation）

**函数**: `_calc_kdj_ob_os_confirm_v60()`

利用KDJ的J值验证买卖信号的合理性：
- 3买：J值在超卖区(<30)且趋势向上 → +3%
- 3买：J值从中性区刚从超卖回升 → +2%
- 3买：J值在超买区(>80) → -3%（警惕）
- 3卖：J值在超买区(>80)且趋势向下 → +3%
- 3卖：J值从中性区刚从超买回落 → +2%
- 3卖：J值在超卖区(<30) → -3%（警惕）

**决策帮助**：KDJ J值是短期动能的敏感指标，与缠论信号方向一致时增强信心。

---

## 测试结果

```
============================= test session starts ==============================
tests/unit/test_chanlun_v60.py::TestRSIDeepDivergenceV60::test_insufficient_data PASSED
tests/unit/test_chanlun_v60.py::TestRSIDeepDivergenceV60::test_non_buy3_sell3_signal PASSED
tests/unit/test_chanlun_v60.py::TestRSIDeepDivergenceV60::test_basic_structure PASSED
tests/unit/test_chanlun_v60.py::TestRSIDeepDivergenceV60::test_confidence_bounds PASSED
tests/unit/test_chanlun_v60.py::TestMASpacingStrengthV60::test_insufficient_data PASSED
tests/unit/test_chanlun_v60.py::TestMASpacingStrengthV60::test_bullish_alignment PASSED
tests/unit/test_chanlun_v60.py::TestMASpacingStrengthV60::test_bearish_alignment_for_buy PASSED
tests/unit/test_chanlun_v60.py::TestMASpacingStrengthV60::test_entangled_ma PASSED
tests/unit/test_chanlun_v60.py::TestZSDistanceEnhancedV60::test_no_zs PASSED
tests/unit/test_chanlun_v60.py::TestZSDistanceEnhancedV60::test_above_zs_buy_signal PASSED
tests/unit/test_chanlun_v60.py::TestZSDistanceEnhancedV60::test_below_zs_buy_signal PASSED
tests/unit/test_chanlun_v60.py::TestKDJOverboughtOversoldV60::test_insufficient_data PASSED
tests/unit/test_chanlun_v60.py::TestKDJOverboughtOversoldV60::test_basic_structure PASSED
tests/unit/test_chanlun_v60.py::TestFindMMDsV60Integration::test_v60_integration_pass PASSED
============================== 27 passed in 0.84s ==============================
V59+V60合计: 58 passed
```

## 版本说明

- 版本号：1.51.0 → 1.52.0
- 总条件数：179 → 183个
- 所有V60条件对3买/3卖生效
- 置信度调整范围：-3% ~ +4%（单条件最大影响）
- **关键改进**：RSI背离检测 + MA间距评分 + 中枢距离增强 + KDJ确认

---

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/mmd.py` | 新增条件180-183函数，集成到find_mmds_v39（+501行） |
| `src/easy_tdx/chanlun/types.py` | 新增4个V60字段定义（+6行） |
| `src/easy_tdx/web/routers/diagnosis.py` | 新增V60字段到诊断API响应（+8行） |
| `web-ui/src/types.ts` | 新增V60 TypeScript类型定义（+47行） |
| `web-ui/src/views/DiagnosisView.vue` | 新增4个V60诊断卡片展示（+80行） |
| `tests/unit/test_chanlun_v60.py` | 新增V60专项测试（27个） |
| `CHANGELOG_V60.md` | 本次更新日志 |
| `SESSION_SUMMARY_V60.md` | 本次会话总结 |
| `pyproject.toml` | 版本号 1.51.0 → 1.52.0 |

## V59→V60 核心改进对比

| 维度 | V59 | V60 | 变化 |
|------|-----|-----|------|
| 条件总数 | 179 | 183 | +4 |
| RSI背离检测(180) | ❌ 无 | ✅ 深度背离分档 | 新增 |
| MA间距评分(181) | ❌ 无 | ✅ 排列方向+间距强度 | 新增 |
| 中枢距离增强(182) | ⚠️ 基础距离 | ✅ 位置+回踩确认 | 增强 |
| KDJ确认(183) | ❌ 无 | ✅ J值+趋势+区域 | 新增 |
| 版本号 | 1.51.0 | 1.52.0 | +1 |
| 专项测试 | 31 | 27 | +27 |
| V59+V60合计 | 31 | 58 | +27 |

## 下一步优化方向（V61+）

1. **回测验证**：运行真实股票数据回测，验证V60四个条件对3买/3卖准确率的实际提升
2. **MACD背离融合**：在RSI背离基础上增加MACD柱状图背离检测
3. **BOLL带宽确认**：利用BOLL带宽判断突破有效性
4. **多信号综合评分**：将V58-V60所有条件的置信度加权融合为综合评分
5. **Web UI视觉优化**：根据综合质量评分等级给卡片加边框颜色（S级金色边框等）

---
**版本**: V60
**完成日期**: 2026-08-27
**测试状态**: ✅ 27 passed（V60专项），58 passed（V59+V60合计）
**构建状态**: 需重新构建 web-ui
