# 更新日志 V79

## [V79] — 2026-08-28

**缠论模型精准度再提升 - 条件248-251集成（分型稳定性+距离安全+多级别一致+动能持续）**

### 新增

- **`_calc_fractal_stability_validation_v79`**（`src/easy_tdx/chanlun/mmd.py`）—— 分型稳定性验证（条件248）。检验顶底分型是否被后续K线破坏，买入信号检查顶分型稳定性，卖出信号检查底分型稳定性。稳定→+3%，弱稳定→-1%，被破坏→-4%。返回 `stability_score`, `fractal_status`, `confidence_adjust`, `msg`。

- **`_calc_mmd_distance_safety_v79`**（`src/easy_tdx/chanlun/mmd.py`）—— 买卖点距离安全阈值（条件249）。评估当前买卖点与最近同向买卖点的K线距离，避免追高/杀跌。过近(<5根)→-4%，适中(5-20根)→0%，充足(>20根)→+3%，孤立→+2%。返回 `distance_score`, `bars_to_nearest`, `safety_level`, `confidence_adjust`, `msg`。

- **`_calc_multi_level_structure_consistency_v79`**（`src/easy_tdx/chanlun/mmd.py`）—— 多级别结构一致性评分（条件250）。评估短(5日)/中(20日)/长(60日)周期均线趋势与信号方向的一致性。全一致→+6%，部分一致→+3%，矛盾→-2%至-4%。返回 `consistency_score`, `short_align`, `mid_align`, `long_align`, `confidence_adjust`, `msg`。

- **`_calc_price_momentum_continuity_v79`**（`src/easy_tdx/chanlun/mmd.py`）—— 价格动能持续性评分（条件251）。计算价格加速度（二阶导）、一阶动量、成交量趋势，综合评估动能是否持续。三因子全支持→+4%，两因子→+2%，一因子→-2%，无支持→-4%。返回 `momentum_score`, `acceleration`, `vol_trend`, `momentum_level`, `confidence_adjust`, `msg`。

### 后端集成

- **MMD 类新增4个V79字段**（`src/easy_tdx/chanlun/types.py`）：`_fractal_stability_validation_v79`, `_mmd_distance_safety_v79`, `_multi_level_structure_consistency_v79`, `_price_momentum_continuity_v79`
- **ConditionGroup 新增 V79**（`src/easy_tdx/backtest/chanlun_validator.py`）：条件范围(248, 251)，描述"分型稳定性验证+买卖点距离安全阈值+多级别结构一致性评分+价格动能持续性评分"
- **诊断API增强**（`src/easy_tdx/web/routers/diagnosis.py`）：新增4个V79字段到 chanlun 响应 + v79_summary 顶层摘要 + condition_counts 支持

### 前端集成

- **`web-ui/src/types.ts`**：`DiagnosisChanlun` 新增4个V79可选字段；`DiagnosisResponse` 新增 `v79_summary` 接口
- **`web-ui/src/views/DiagnosisView.vue`**：
  - 新增 `v79QualityLabel` 函数
  - 新增 V79 四维度量摘要卡片（Hero区域）
  - 新增4个V79条件卡片（分型稳定性/距离安全/多级别一致/动能持续）
  - 新增 V79 CSS 样式（v79-fsv, v79-mds, v79-mls, v79-pmc, v79-summary-row, v79-tag）

### 测试

- **`tests/unit/test_chanlun_v79.py`**（27 个测试用例）：
  - `TestV79ConditionGroup`：枚举存在性、条件范围(248-251)、描述文案
  - `TestV79MMDFields`：MMD对象包含4个V79字段
  - `TestV79BacktestValidator`：单组/多组合验证、summary输出
  - `TestV79Functions`：分型稳定性（买入稳定/卖出稳定/不足/被破坏）、距离安全（安全/过近/不足/空列表）、多级别一致（全一致/矛盾/不足/买卖对比）、动能持续（强劲/衰竭/中性/不足/无成交量/级别枚举）、综合冒烟、V78一致性

### 测试结果

- V75+V76+V77+V78+V79 联合测试：**116 passed**
- TypeScript编译：**零错误**
- Web UI构建：**built in 5.11s**

### API 验证

```bash
curl "http://127.0.0.1:8000/api/v1/diagnosis/quick?market=SZ&code=000001"
# 返回:
# fractal_stability_validation_v79: {"stability_score": 0.9, "fractal_status": "stable", ...}
# mmd_distance_safety_v79: {"distance_score": 0.85, "safety_level": "safe", ...}
# multi_level_structure_consistency_v79: {"consistency_score": 0.95, "short_align": true, ...}
# price_momentum_continuity_v79: {"momentum_score": 0.9, "momentum_level": "strong", ...}
```

---

## 核心功能清单（更新后）

### 缠论买卖点增强（V58-V79）
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
| V76 | 236-239 | 价格结构完整性+趋势方向对齐+波动率自适应置信度+买卖点最终有效性 |
| V77 | 240-243 | 量能分布深度+中枢结构权重+信号新鲜度+价格动能加速度 |
| V78 | 244-247 | 周期位置评分+多信号共识+波动率压缩突破+资金流向背离 |
| **V79** | **248-251** | **分型稳定性验证+距离安全阈值+多级别结构一致性+动能持续性** |

### 诊断系统
| 功能 | 状态 |
|------|------|
| MACD/KDJ/RSI/BOLL/均线/成交量/ATR分析 | ✅ |
| 综合评分+仓位建议+止损止盈 | ✅ |
| V67-V78 缠论条件卡片（共 48 张） | ✅ |
| V76 四维验证摘要（Hero区域） | ✅ |
| V77 四维度量分析卡片 | ✅ |
| V78 四维度量分析卡片 | ✅ |
| **V79 四维度量分析卡片** | ✅ **新增** |
| **V79 四维度量摘要（Hero区域）** | ✅ **新增** |
