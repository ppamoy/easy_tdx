# 更新日志 V70

## [V70] — 2026-08-26

**缠论模型精准度再提升 - 条件212-215集成**（量峰检测+时间衰减+假突破过滤+置信度校准）

### 新增

- **`_calc_volume_peak_detection_v70`**（`src/easy_tdx/chanlun/mmd.py`）—— 分时量峰检测（条件212）。检测突破/反转时的成交量峰值，确认信号真实性。买入信号需放量突破（≥1.5倍均值）= 量峰确认；无量突破 = 假突破风险。返回 `peak_ratio`, `peak_detected`, `volume_strength`, `confidence_adjust`, `msg`。

- **`_calc_signal_time_decay_v70`**（`src/easy_tdx/chanlun/mmd.py`）—— 信号时间窗口衰减（条件213）。根据信号出现后的K线数量应用指数衰减：新信号（≤5根）完整置信度，中期（6-15根）线性衰减，长期（>15根）指数快速衰减。返回 `bar_count`, `decay_factor`, `signal_age`, `confidence_adjust`, `msg`。

- **`_calc_false_breakout_filter_v70`**（`src/easy_tdx/chanlun/mmd.py`）—— 假突破二次过滤（条件214）。突破后价格需持续N根K线维持在突破水平之上/之下。持续≥3根=真突破，快速回归=假突破。返回 `sustained_bars`, `is_sustained`, `breakout_quality`, `confidence_adjust`, `msg`。

- **`_calc_final_confidence_calibration_v70`**（`src/easy_tdx/chanlun/mmd.py`）—— 信号置信度最终校准（条件215）。综合所有前置条件的置信度调整，计算正负调整数量，输出校准等级（high/medium/low/critical）和校准后置信度。返回 `total_adjust`, `calibrated_confidence`, `calibration_level`, `adjust_count`, `positive_adjusts`, `negative_adjusts`, `msg`。

### 前端集成

- **`web-ui/src/types.ts`**：已有 V70 接口类型定义（`volume_peak_detection_v70`, `signal_time_decay_v70`, `false_breakout_filter_v70`, `final_confidence_calibration_v70`）
- **`web-ui/src/views/DiagnosisView.vue`**：新增 4 个 V70 诊断卡片 + CSS 样式（`.v70-vp`, `.v70-decay`, `.v70-fb`, `.v70-cali`）
- **`src/easy_tdx/web/routers/diagnosis.py`**：暴露 4 个 V70 字段到 API 响应

### 测试

- `TestV70ConditionGroup` / `TestV70MMDFields` / `TestV70BacktestValidator` / `TestV70MultiStock` 测试类已通过
- 全部 V64 backtest 测试通过：**79 passed**
- TypeScript 编译零错误
- Web UI 构建成功

---

## 核心功能清单（更新后）

### 缠论买卖点增强（V58-V70）
| 版本 | 条件范围 | 核心能力 |
|------|----------|----------|
| V58-V59 | 172-179 | 多TF趋势+量能验证+ATR止损+自适应参数 |
| V60 | 180-183 | RSI背离+MA间距+中枢距离+KDJ确认 |
| V61 | 184-185 | MACD背离融合+综合评分 |
| V62 | 186-189 | BOLL带宽确认+动态阈值 |
| V63 | 190-191 | 中枢权重优化+多周期衰减 |
| V65 | 192-195 | 量价背离+回踩确认+波动率压缩+新鲜度 |
| V66 | 196-199 | MACD加速+量价配合+多TF共振+执行优先级 |
| V67 | 200-203 | 中枢背驰量化+多级别一致性+轨迹健康+动态止损 |
| V68 | 204-207 | 缺口趋势+区间套+资金流向+市场风格 |
| V69 | 208-211 | 量价背离二次确认+结构完整性评分+多指标背离融合+回踩深度量化 |
| **V70** | **212-215** | **量峰检测+时间衰减+假突破过滤+置信度校准** |

### 诊断系统
| 功能 | 状态 |
|------|------|
| MACD/KDJ/RSI/BOLL/均线/成交量/ATR分析 | ✅ |
| 综合评分+仓位建议+止损止盈 | ✅ |
| V67-V70 缠论条件卡片 | ✅ |

---

## 测试结果

```
tests/unit/test_chanlun_v64_backtest.py ... 79 passed in 0.97s
TypeScript: 零错误
Web UI build: ✓ built in 3.45s
```

---

## 使用方式

### Web UI
```
http://localhost:8000/diagnosis   # 技术诊断（含V69/V70全部卡片）
http://localhost:8000/chanlun     # 缠论分析
```

### API
```bash
# V70 返回字段
GET /api/v1/diagnosis/quick?market=SZ&code=000001

# 新增字段：
# - volume_peak_detection_v70: {peak_ratio, peak_detected, volume_strength, confidence_adjust, msg}
# - signal_time_decay_v70: {bar_count, decay_factor, signal_age, confidence_adjust, msg}
# - false_breakout_filter_v70: {sustained_bars, is_sustained, breakout_quality, confidence_adjust, msg}
# - final_confidence_calibration_v70: {total_adjust, calibrated_confidence, calibration_level, adjust_count, positive_adjusts, negative_adjusts, msg}
```

---

**版本**: V70  
**完成日期**: 2026-08-26  
**测试状态**: ✅ 79 passed (V64 backtest)  
**构建状态**: ✅ Web UI 构建成功，TypeScript 零错误
