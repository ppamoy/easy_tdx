# 更新日志 V74

## [V74] — 2026-08-26

**缠论模型精准度再提升 - 条件228-231集成**（量价背离二次确认+趋势动能持续+中枢重叠度+信号共振深度）

### 新增

- **`_calc_volume_price_divergence_secondary_v74`**（`src/easy_tdx/chanlun/mmd.py`）—— 量价背离二次确认（条件228）。检测价格趋势与成交量变化的背离关系：买入信号时价格回升但量能萎缩→bullish divergence增强置信；放量滞涨→bearish warning降低置信。返回 `divergence_type`, `divergence_strength`, `confirm_signal`, `confidence_adjust`, `msg`。

- **`_calc_trend_momentum_continuity_v74`**（`src/easy_tdx/chanlun/mmd.py`）—— 趋势动能持续验证（条件229）。计算短(5根)/中(10根)/长(20根)三个时间窗口的价格动量，统计同向比例：三周期一致且动量≥0.5→strong增强；两周期一致→moderate；一致≤1→weakening降权。返回 `momentum_score`, `short_term`, `mid_term`, `long_term`, `continuity`, `confidence_adjust`, `msg`。

- **`_calc_zhongshu_overlap_density_v74`**（`src/easy_tdx/chanlun/mmd.py`）—— 中枢重叠度评估（条件230）。分析当前价格附近最近5个历史中枢的重叠密度：价格处于多个中枢重叠区域内→strong_support/strong_resistance增强；重叠度≥30%→moderate；远离中枢密集区→weak降权。返回 `overlap_density`, `nearby_zs_count`, `distance_to_zs`, `signal_strength`, `confidence_adjust`, `msg`。

- **`_calc_signal_resonance_depth_v74`**（`src/easy_tdx/chanlun/mmd.py`）—— 信号共振深度评分（条件231）。从6个独立维度评估信号确认强度：MACD方向、KDJ方向、RSI方向、均线排列方向、成交量配合、价格相对20日区间位置。一致维度≥83%→deep增强；≥67%→moderate；≤33%→shallow降权。返回 `depth_score`, `confirming_dimensions`, `total_dimensions`, `resonance_level`, `confidence_adjust`, `msg`。

### 前端集成

- **`web-ui/src/types.ts`**：新增 4 个 V74 接口类型定义
- **`web-ui/src/views/DiagnosisView.vue`**：新增 4 个 V74 诊断卡片 + CSS 样式（`.v74-vpd`, `.v74-tmc`, `.v74-zod`, `.v74-srd`）
- **`src/easy_tdx/web/routers/diagnosis.py`**：暴露 4 个 V74 字段到 API 响应，新增 V74 条件计数逻辑
- **`src/easy_tdx/chanlun/types.py`**：新增 4 个 V74 MMD 字段声明
- **`src/easy_tdx/backtest/chanlun_validator.py`**：新增 `ConditionGroup.V74` 枚举值（条件228-231）

### 测试

- 新增 `TestV74ConditionGroup` / `TestV74MMDFields` / `TestV74BacktestValidator` / `TestV74Functions` 测试类
- 全部 V74 测试通过：**12 passed**
- 全量缠论测试通过：**1047 passed**（含V74）
- TypeScript 编译零错误
- Web UI 构建成功

---

## 核心功能清单（更新后）

### 缠论买卖点增强（V58-V74）
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
| **V74** | **228-231** | **量价背离二次确认+趋势动能持续+中枢重叠度+信号共振深度** |

### 诊断系统
| 功能 | 状态 |
|------|------|
| MACD/KDJ/RSI/BOLL/均线/成交量/ATR分析 | ✅ |
| 综合评分+仓位建议+止损止盈 | ✅ |
| V67-V74 缠论条件卡片（共 32 张） | ✅ |

---

## 测试结果

```
tests/unit/test_chanlun_v64_backtest.py (V74) ... 12 passed in 1.23s
tests/unit/test_chanlun*.py ... 1047 passed in 6.59s
TypeScript: 零错误
Web UI build: ✓ built in 3.55s
```

---

## 使用方式

### Web UI
```
http://localhost:8000/diagnosis   # 技术诊断（含V69-V74全部卡片）
http://localhost:8000/chanlun     # 缠论分析
```

### API
```bash
# V74 返回字段
GET /api/v1/diagnosis/quick?market=SZ&code=000001

# 新增字段：
# - volume_price_divergence_secondary_v74: {divergence_type, divergence_strength, confirm_signal, confidence_adjust, msg}
# - trend_momentum_continuity_v74: {momentum_score, short_term, mid_term, long_term, continuity, confidence_adjust, msg}
# - zhongshu_overlap_density_v74: {overlap_density, nearby_zs_count, distance_to_zs, signal_strength, confidence_adjust, msg}
# - signal_resonance_depth_v74: {depth_score, confirming_dimensions, total_dimensions, resonance_level, confidence_adjust, msg}
```

---

**版本**: V74  
**完成日期**: 2026-08-26  
**测试状态**: ✅ 1047 passed (chanlun core) + 12 passed (V74)  
**构建状态**: ✅ Web UI 构建成功，TypeScript 零错误
