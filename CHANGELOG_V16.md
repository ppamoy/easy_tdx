# EasyTDX 项目更新日志 V16

## 更新时间
2026-08-22

## 本次更新内容

### 缠论买卖点模型 V16 增强

#### 核心改进

**1. 信号衰减集成到置信度计算（Bugfix）**

V15新增的信号衰减（signal_aging）此前仅在报告函数中计算展示，未实际影响置信度评分。
V16修复此问题：
- `find_mmds()` 现在在计算置信度后自动计算并存储 `_signal_aging` 到MMD对象
- `_calc_confidence()` 正确使用存储的衰减数据降低过期信号置信度
- 确保"信号越老置信度越低"的逻辑贯穿整个系统

**2. 仓位建议系统（Position Sizing）**

新增 `_calc_position_sizing()` 函数，基于缠论信号综合评估给出仓位建议：

| 因素 | 影响 |
|------|------|
| 基础置信度 | 0.85+→70%仓位，0.75+→55%，0.65+→40%，0.55+→25%，<0.55→10% |
| 信号衰减 | 过期信号降仓40%，偏老信号降仓20%，新鲜信号加仓5% |
| K线形态 | 锤子线/阳吞没+5%，十字星不变，阴吞没-5% |
| 波动率 | 高波动(>3%)降仓30%，低波动(<1%)加仓10% |
| 质量评级 | S级+10%，A级+5%，C级-5%，D级-15% |

**3. MMD类字段规范化**

将V14/V15的动态属性转为MMD dataclass的显式字段：
- `_vol_spike`, `_gap_up`, `_gap_down`, `_gap_size`
- `_macd_slope_confirmed`, `_vol_profile_support`, `_vol_profile_resistance`
- `_kline_pattern`, `_signal_aging`, `_retest_break`, `_retest_retracement`

**4. K线形态逻辑修复**

修复了`is_buy`判断逻辑（`startswith("buy")`无法匹配`"3buy"`），改为`"buy" in mmd_type.value`。
同时补充了阴吞没形态对卖出信号的正确处理。

### 前端增强

**types.ts**：
- `DiagnosisSignalReport` 新增 `position_sizing` 字段

**DiagnosisView.vue**：
- 新增仓位建议行显示（颜色编码：绿色≥60%、蓝色≥40%、橙色≥20%、红色<20%）
- 新增仓位调整原因列表展示

### 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/types.py` | MMD类新增12个显式enhancement字段 |
| `src/easy_tdx/chanlun/mmd.py` | 新增`_calc_position_sizing()`；修复信号衰减集成；修复is_buy判断 |
| `web-ui/src/types.ts` | 新增`position_sizing`类型定义 |
| `web-ui/src/views/DiagnosisView.vue` | 新增仓位建议UI展示 |
| `tests/unit/test_chanlun_enhancements.py` | 新增TestV16Enhancements类（7个测试用例） |

### 测试结果

```
=========================== 1098 passed, 2 warnings in 73.74s ============================
- test_chanlun_enhancements.py: 78 passed（含7个V16新增测试）
```

---

## 版本演进时间线

| 版本 | 日期 | 核心改进 |
|------|------|----------|
| V7 | 08-21 | 信号质量报告 + 动态止损止盈 |
| V9 | 08-21 | MA趋势对齐 + RSI确认 + MACD阈值收紧 |
| V10 | 08-21 | MA斜率 + BOLL过滤 + ADX趋势强度 + 多因子共振 |
| V11 | 08-21 | MA斜率放宽 + RSI动量补偿 + ADX真实OHLC |
| V12 | 08-21 | KDJ动量确认 + 区间套一致性评分 |
| V13 | 08-21 | 成交量剖面分析(VAP) + 2买/2卖成交量支撑 |
| V14 | 08-21 | 成交量异常检测 + 缺口分析 + MACD斜率 + 假突破过滤 |
| V15 | 08-22 | K线形态确认 + 信号衰减 + 二次回踩 + 动态时间窗口 |
| **V16** | **08-22** | **信号衰减置信度集成 + 仓位建议系统 + MMD字段规范化** |
