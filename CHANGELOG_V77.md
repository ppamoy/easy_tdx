# 更新日志 V77

## [V77] — 2026-08-27

**缠论模型精准度再提升 - 条件240-243集成（量能分布深度+中枢结构权重+信号新鲜度+价格动能加速度）**

### 新增

- **`_calc_volume_distribution_depth_v77`**（`src/easy_tdx/chanlun/mmd.py`）—— 量能分布深度分析（条件240）。分析成交量在价格区间的分布深度，识别筹码集中区（accumulation/distribution/low_zone/high_zone/neutral），评估支撑/阻力距离，返回 `energy_zone`, `volume_rank`, `support_distance`, `resistance_distance`, `confidence_adjust`, `msg`。

- **`_calc_zhongshu_structure_weight_v77`**（`src/easy_tdx/chanlun/mmd.py`）—— 中枢结构权重评估（条件241）。评估当前买卖点最近的中枢对信号的支撑/压制作用，根据距离中枢远近和信号方向给予权重评分，返回 `weight_score`, `nearest_zs_dist`, `zs_level`, `confidence_adjust`, `msg`。

- **`_calc_signal_freshness_validation_v77`**（`src/easy_tdx/chanlun/mmd.py`）—— 信号新鲜度验证（条件242）。根据信号产生后的K线数量计算新鲜度评分（very_fresh/fresh/aging/stale），超过阈值则降低置信度，返回 `freshness_score`, `bars_since_signal`, `age_label`, `confidence_adjust`, `msg`。

- **`_calc_price_momentum_acceleration_v77`**（`src/easy_tdx/chanlun/mmd.py`）—— 价格动能加速度（条件243）。计算价格二阶差分（加速度），判断动能方向（accelerating_up/growing_up/flat/decelerating/sharp_reversal）和强度，返回 `acceleration`, `momentum_direction`, `acceleration_strength`, `confidence_adjust`, `msg`。

### 后端集成

- **MMD 类新增4个V77字段**（`src/easy_tdx/chanlun/types.py`）：`_volume_distribution_depth_v77`, `_zhongshu_structure_weight_v77`, `_signal_freshness_validation_v77`, `_price_momentum_acceleration_v77`
- **ConditionGroup 新增 V77**（`src/easy_tdx/backtest/chanlun_validator.py`）：条件范围(240, 243)，描述"量能分布深度分析+中枢结构权重评估+信号新鲜度验证+价格动能加速度"
- **诊断API增强**（`src/easy_tdx/web/routers/diagnosis.py`）：新增4个V77字段到 chanlun 响应 + 多股对比condition_counts支持

### 前端集成

- **`web-ui/src/types.ts`**：`DiagnosisChanlun` 新增4个V77可选字段
- **`web-ui/src/views/DiagnosisView.vue`**：新增4个V77条件卡片（量能分布深度/中枢结构权重/信号新鲜度/动能加速度）+ CSS样式

### 测试

- **`tests/unit/test_chanlun_v77.py`**（25 个测试用例）：
  - `TestV77ConditionGroup`：枚举存在性、条件范围(240-243)、描述文案
  - `TestV77MMDFields`：MMD对象包含4个V77字段
  - `TestV77BacktestValidator`：单组/多组合验证、summary输出
  - `TestV77Functions`：量能分布（买入低位/卖出高位/数据不足/量能确认）、中枢权重（近/远/无/不足）、新鲜度（新鲜/衰老/不足/范围）、动能加速度（加速/衰减/不足/卖出/横盘）、综合冒烟测试

### 测试结果

- V75+V76+V77 联合测试：**63 passed**
- TypeScript编译：**零错误**
- Web UI构建：**built in 7.60s**

### API 验证

```bash
curl "http://127.0.0.1:8000/api/v1/diagnosis/quick?market=SZ&code=000001"
# 返回:
# v76_summary: {"structure_integrity": "invalid", "validity_score": 0.1, ...}
# volume_distribution_depth_v77: {"energy_zone": "high_zone", "volume_rank": 1.0, ...}
# zhongshu_structure_weight_v77: {"weight_score": 0.7, "zs_level": "1F", ...}
# signal_freshness_validation_v77: {"freshness_score": 0.9, "age_label": "fresh", ...}
# price_momentum_acceleration_v77: {"acceleration": 0.00171, "momentum_direction": "growing_up", ...}
```

---

## 核心功能清单（更新后）

### 缠论买卖点增强（V58-V77）
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
| V69 | 208-211 | 量价背离二次确认+结构完整性+多指标背离+回踩深度 |
| V70 | 212-215 | 量峰检测+时间衰减+假突破过滤+置信度校准 |
| V71 | 216-219 | 均线排列强度+多周期均线共振+历史胜率+动态风险收益 |
| V72 | 220-223 | 均线收敛发散+支撑阻力距离+量价结构质量+信号衰减速度 |
| V73 | 224-227 | 买卖点位置风险+中枢突破验证+多指标一致性+波动率适配 |
| V74 | 228-231 | 量价背离二次确认+趋势动能持续+中枢重叠度+信号共振深度 |
| V75 | 232-235 | 回调深度验证+中枢回踩确认+量峰持续评分+多信号时间一致性 |
| V76 | 236-239 | 价格结构完整性+趋势方向对齐+波动率自适应置信度+最终有效性 |
| **V77** | **240-243** | **量能分布深度+中枢结构权重+信号新鲜度+价格动能加速度** |

### 诊断系统
| 功能 | 状态 |
|------|------|
| MACD/KDJ/RSI/BOLL/均线/成交量/ATR分析 | ✅ |
| 综合评分+仓位建议+止损止盈 | ✅ |
| V67-V77 缠论条件卡片（共 44 张） | ✅ |
| V76 四维验证摘要（Hero区域） | ✅ |
| V77 四维度量分析卡片 | ✅ |
