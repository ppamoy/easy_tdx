# 更新日志 V71

## [V71] — 2026-08-26

**缠论模型精准度再提升 - 条件216-219集成**（均线排列强度+多周期共振+历史胜率+动态风险收益）

### 新增

- **`_calc_ma_alignment_strength_v71`**（`src/easy_tdx/chanlun/mmd.py`）—— 均线排列强度评估（条件216）。评估当前价格相对于多条均线（MA20/MA60/MA120）的排列状态：多头排列（MA20>MA60>MA120）增强买入信号，空头排列减弱买入信号，混合排列降低置信度。返回 `alignment`, `strength`, `confidence_adjust`, `msg`。

- **`_calc_multi_tf_ma_resonance_v71`**（`src/easy_tdx/chanlun/mmd.py`）—— 多周期均线共振确认（条件217）。短中长期均线（MA5/MA10, MA20/MA60, MA60/MA120）同时发出同向信号时增强置信度。共振数=3时置信度+8%，共振数=2时+4%。返回 `short_aligned`, `mid_aligned`, `long_aligned`, `resonance_count`, `confidence_adjust`, `msg`。

- **`_calc_mmd_history_winrate_v71`**（`src/easy_tdx/chanlun/mmd.py`）—— 买卖点历史胜率回溯（条件218）。对最近200根K线中的历史类似形态进行胜率回溯分析，统计价格形态与后续走势的关联性。胜率≥60%且样本≥5时置信度+4%。返回 `lookback_winrate`, `sample_count`, `confidence_adjust`, `msg`。

- **`_calc_dynamic_rr_optimization_v71`**（`src/easy_tdx/chanlun/mmd.py`）—— 动态风险收益比优化（条件219）。根据当前ATR波动率动态调整止损止盈比例：低波动市场止损1.5x ATR止盈4x，中等波动2x/4.5x，高波动2.5x/5x。返回 `stop_loss_pct`, `take_profit_pct`, `rr_ratio`, `atr_based_sl`, `atr_based_tp`, `msg`。

### 前端集成

- **`web-ui/src/types.ts`**：新增 4 个 V71 接口类型定义
- **`web-ui/src/views/DiagnosisView.vue`**：新增 4 个 V71 诊断卡片 + CSS 样式（`.v71-ma`, `.v71-res`, `.v71-win`, `.v71-rr`）
- **`src/easy_tdx/web/routers/diagnosis.py`**：暴露 4 个 V71 字段到 API 响应，新增 V71 条件计数逻辑
- **`src/easy_tdx/backtest/chanlun_validator.py`**：新增 `ConditionGroup.V71` 枚举值（条件216-219）

### 测试

- 新增 `TestV71ConditionGroup` / `TestV71MMDFields` / `TestV71BacktestValidator` / `TestV71MultiStock` / `TestV71Functions` 测试类
- 全部 V64 backtest 测试通过：**91 passed**
- 缠论核心测试通过：**531 passed**
- TypeScript 编译零错误
- Web UI 构建成功

---

## 核心功能清单（更新后）

### 缠论买卖点增强（V58-V71）
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
| V70 | 212-215 | 量峰检测+时间衰减+假突破过滤+置信度校准 |
| **V71** | **216-219** | **均线排列强度+多周期均线共振+历史胜率回溯+动态风险收益比** |

### 诊断系统
| 功能 | 状态 |
|------|------|
| MACD/KDJ/RSI/BOLL/均线/成交量/ATR分析 | ✅ |
| 综合评分+仓位建议+止损止盈 | ✅ |
| V67-V71 缠论条件卡片（共20张） | ✅ |

---

## 测试结果

```
tests/unit/test_chanlun_v64_backtest.py ... 91 passed in 1.30s
tests/unit/test_chanlun*.py ... 531 passed in 4.79s
TypeScript: 零错误
Web UI build: ✓ built in 5.76s
```

---

## 使用方式

### Web UI
```
http://localhost:8000/diagnosis   # 技术诊断（含V69-V71全部卡片）
http://localhost:8000/chanlun     # 缠论分析
```

### API
```bash
# V71 返回字段
GET /api/v1/diagnosis/quick?market=SZ&code=000001

# 新增字段：
# - ma_alignment_strength_v71: {alignment, strength, confidence_adjust, msg}
# - multi_tf_ma_resonance_v71: {short_aligned, mid_aligned, long_aligned, resonance_count, confidence_adjust, msg}
# - mmd_history_winrate_v71: {lookback_winrate, sample_count, confidence_adjust, msg}
# - dynamic_rr_optimization_v71: {stop_loss_pct, take_profit_pct, rr_ratio, atr_based_sl, atr_based_tp, msg}
```

---

**版本**: V71  
**完成日期**: 2026-08-26  
**测试状态**: ✅ 91 passed (V64 backtest) + 531 passed (chanlun core)  
**构建状态**: ✅ Web UI 构建成功，TypeScript 零错误
