# 更新日志 V75

## [V75] — 2026-08-26

**缠论模型精准度再提升 - 条件232-235集成（回调深度验证+中枢回踩确认+量峰持续评分+多信号时间一致性）**

### 新增

- **`_calc_pullback_depth_validation_v75`**（`src/easy_tdx/chanlun/mmd.py`）—— 回调深度验证（条件232）。检测买入/卖出信号后价格回调深度是否符合健康趋势的斐波那契回撤位（≤23.6%浅回/≤38.2%正常/≤50%过度/>50%危险），返回 `pullback_depth`, `max_retracement`, `fibonacci_level`, `confirm_signal`, `confidence_adjust`, `msg`。

- **`_calc_zhongshu_retracement_confirm_v75`**（`src/easy_tdx/chanlun/mmd.py`）—— 中枢区间回踩确认（条件233）。验证价格相对最近中枢的位置（内部/上方/下方）及反弹强度，判断中枢支撑/阻力有效性，返回 `retracement_type`, `nearest_zs_dist`, `bounce_strength`, `confirm_signal`, `confidence_adjust`, `msg`。

- **`_calc_volume_peak_duration_v75`**（`src/easy_tdx/chanlun/mmd.py`）—— 量峰持续时间评分（条件234）。统计连续放量天数（volume > 1.5x 均价）和均量比，判断资金流入持续性，返回 `peak_duration`, `avg_vol_ratio`, `peak_days`, `confirm_signal`, `confidence_adjust`, `msg`。

- **`_calc_multi_signal_time_consistency_v75`**（`src/easy_tdx/chanlun/mmd.py`）—— 多信号时间一致性（条件235）。检测 MACD/KDJ/均线/成交量/RSI 五个辅助信号的出现时间集中度，计算一致率得分（7天内密集→高一致），返回 `consistency_score`, `signal_dates`, `alignment_ratio`, `confirm_signal`, `confidence_adjust`, `msg`。

### 前端集成（已由 V74 session 前置完成）

- **`web-ui/src/types.ts`**：已包含 4 个 V75 接口类型定义
- **`web-ui/src/views/DiagnosisView.vue`**：已包含 4 个 V75 诊断卡片 + CSS 样式（`.v75-pdv`, `.v75-zrc`, `.v75-vpd2`, `.v75-mstc`）
- **`src/easy_tdx/web/routers/diagnosis.py`**：已暴露 4 个 V75 字段到 API 响应
- **`src/easy_tdx/chanlun/types.py`**：已包含 4 个 V75 MMD 字段声明
- **`src/easy_tdx/backtest/chanlun_validator.py`**：已包含 `ConditionGroup.V75` 枚举值（条件232-235）

### 本次修复

- **修复测试**：`tests/unit/test_chanlun_v64_backtest.py` 中 `TestConditionGroup.test_all_groups_defined` 缺失 V75，现已补充
- **新增测试文件**：`tests/unit/test_chanlun_v75.py`（17 个测试用例全覆盖）

### 测试

- 新增 `TestV75ConditionGroup` / `TestV75MMDFields` / `TestV75BacktestValidator` / `TestV75Functions` 测试类
- V75 专项测试：**17 passed**
- V74+V75 联合测试：**144 passed**
- 全量缠论测试：**2029 passed**（含 V75）
- TypeScript 编译零错误
- Web UI 构建成功：**built in 6.11s**

---

## 核心功能清单（更新后）

### 缠论买卖点增强（V58-V75）
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
| V71 | 216-219 | 均线排列强度+多周期均线共振+历史胜率回溯+动态风险收益比 |
| V72 | 220-223 | 均线收敛发散+支撑阻力距离+量价结构质量+信号衰减速度 |
| V73 | 224-227 | 买卖点位置风险+中枢突破验证+多指标一致性+波动率环境适配 |
| V74 | 228-231 | 量价背离二次确认+趋势动能持续+中枢重叠度+信号共振深度 |
| **V75** | **232-235** | **回调深度验证+中枢回踩确认+量峰持续评分+多信号时间一致性** |

### 诊断系统
| 功能 | 状态 |
|------|------|
| MACD/KDJ/RSI/BOLL/均线/成交量/ATR分析 | ✅ |
| 综合评分+仓位建议+止损止盈 | ✅ |
| V67-V75 缠论条件卡片（共 36 张） | ✅ |

---

## 测试结果

```
tests/unit/test_chanlun_v75.py ... 17 passed in 1.97s
tests/unit/test_chanlun_v64_backtest.py (V74+V75) ... 144 passed in 2.42s
tests/unit/ (全量) ... 2029 passed in 92.73s
TypeScript: 零错误
Web UI build: ✓ built in 6.11s
```

---

## 使用方式

### Web UI
```
http://localhost:8000/diagnosis   # 技术诊断（含V69-V75全部卡片）
http://localhost:8000/chanlun     # 缠论分析
```

### API
```bash
# V75 返回字段
GET /api/v1/diagnosis/quick?market=SZ&code=000001

# 新增字段：
# - pullback_depth_validation_v75: {pullback_depth, max_retracement, fibonacci_level, confirm_signal, confidence_adjust, msg}
# - zhongshu_retracement_confirm_v75: {retracement_type, nearest_zs_dist, bounce_strength, confirm_signal, confidence_adjust, msg}
# - volume_peak_duration_v75: {peak_duration, avg_vol_ratio, peak_days, confirm_signal, confidence_adjust, msg}
# - multi_signal_time_consistency_v75: {consistency_score, signal_dates, alignment_ratio, confirm_signal, confidence_adjust, msg}
```

---

**版本**: V75  
**完成日期**: 2026-08-26  
**测试状态**: ✅ 2029 passed (chanlun core + V75)  
**构建状态**: ✅ Web UI 构建成功，TypeScript 零错误
