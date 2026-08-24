# EasyTDX 项目更新日志 V62

## 更新时间
2026-08-28

## 背景：BOLL带宽确认与动态阈值
V61引入了MACD背离融合和综合评分系统，但缺乏对突破有效性的直接验证和波动率自适应机制。本次更新聚焦两个核心改进：BOLL带宽突破/压缩确认（过滤假突破）和基于ATR的动态阈值自适应（根据市场波动率调整信号阈值）。

---

## 条件186: BOLL带宽突破确认（BOLL Bandwidth Breakout Confirmation）

**函数**: `_calc_boll_bandwidth_breakout_confirm_v62()`

检测3买/3卖时BOLL带宽是否处于有效突破状态：
- 3买：价格突破BOLL上轨 + 带宽较前期扩张 → 突破有效，+3%
- 3卖：价格跌破BOLL下轨 + 带宽较前期扩张 → 突破有效，+3%
- 价格接近轨道但未突破 → +1%（潜在突破）
- 带宽持续收缩 → -1%（可能即将反转，信号质量下降）

**决策帮助**：BOLL带宽扩张确认突破有效性，有效过滤假突破信号。

---

## 条件187: BOLL带宽压缩反弹确认（BOLL Bandwidth Reversal Confirmation）

**函数**: `_calc_boll_bandwidth_reversal_confirm_v62()`

在BOLL带宽压缩后，检测价格是否出现有效反弹/回踩确认：
- 3买：带宽低位(分位数<30%) + 价格从下轨附近反弹 → 反弹有效，+2%
- 3卖：带宽低位(分位数<30%) + 价格从上轨附近回落 → 回落有效，+2%
- 带宽低位但无反弹/回落确认 → +0.5%

**决策帮助**：BOLL带宽压缩后往往伴随方向选择，确认反弹/回踩后入场更安全。

---

## 条件188: 动态阈值-波动率状态切换（Dynamic Threshold Volatility Regime）

**函数**: `_calc_dynamic_threshold_volatility_regime_v62()`

根据当前波动率环境动态调整信号阈值：
- 高波动（ATR%>3%）：放宽阈值，降低置信度要求（-2%）
- 低波动（ATR%<1%）：收紧阈值，提高置信度要求（+2%）
- 正常波动：保持默认阈值

**决策帮助**：不同波动率环境下，同一信号的可靠性不同，动态调整避免在高波动期过度乐观。

---

## 条件189: 动态阈值-ATR倍数自适应（Dynamic Threshold ATR Multiplier Adaptive）

**函数**: `_calc_dynamic_threshold_atr_multiplier_v62()`

根据当前ATR动态调整止损距离的倍数：
- 高波动（ATR%>4%）：使用更大ATR倍数（2.5x），避免频繁触发止损
- 中波动（ATR%>2.5%）：使用2.2x倍数
- 低波动（ATR%<0.8%）：使用更小ATR倍数（1.5x），收紧止损减少损失
- 正常波动：使用默认倍数（2x）

**决策帮助**：动态止损距离适应市场波动，减少震荡市中的假止损触发。

---

## 测试结果

```
============================= test session starts ==============================
tests/unit/test_chanlun_v59.py: 31 passed
tests/unit/test_chanlun_v60.py: 27 passed
tests/unit/test_chanlun_v61.py: 21 passed
tests/unit/test_chanlun_v62.py: 39 passed
V59+V60+V61+V62 合计: 118 passed
==============================================================================
```

## 版本说明

- 版本号：1.53.0 → 1.54.0
- 总条件数：185 → 189个
- 所有V62条件对3买/3卖生效
- 置信度调整范围：-2% ~ +3%（单条件最大影响）
- **关键改进**：BOLL带宽突破/压缩确认 + ATR动态阈值自适应

---

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/mmd.py` | 新增条件186-189函数，集成到find_mmds_v39（+406行），修复ATR计算bug |
| `src/easy_tdx/chanlun/types.py` | 新增4个V62字段定义（已在未提交变更中） |
| `src/easy_tdx/web/routers/diagnosis.py` | 新增V62字段到诊断API响应（已在未提交变更中） |
| `web-ui/src/types.ts` | 新增V62 TypeScript类型定义（已在未提交变更中） |
| `web-ui/src/views/DiagnosisView.vue` | 新增V62诊断卡片展示（已在未提交变更中） |
| `web-ui/src/style.css` | 修复页面滚动问题（已在未提交变更中） |
| `web-ui/src/components/*.vue` | 修复图表滚轮事件吞没问题（已在未提交变更中） |
| `tests/unit/test_chanlun_v62.py` | 新增V62专项测试（39个） |
| `CHANGELOG_V62.md` | 本次更新日志 |
| `pyproject.toml` | 版本号 1.53.0 → 1.54.0 |

## 下一步优化方向（V63+）

1. **回测验证框架**：建立系统化回测流程，量化验证V58-V62条件的实际准确率提升
2. **多股票对比分析**：在同一诊断页面展示多只股票的信号质量对比
3. **中枢级别权重优化**：根据中枢级别动态调整各条件的权重
4. **实时信号衰减监控**：跟踪信号随时间衰减速度，辅助判断入场时机

---

**版本**: V62
**完成日期**: 2026-08-28
**测试状态**: ✅ 39 passed（V62专项），118 passed（V59+V60+V61+V62合计）
**构建状态**: 需重新构建 web-ui（npm run build）
