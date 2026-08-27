# 更新日志 V80

## [V80] — 2026-08-28

**缠论模型精准度再提升 - 条件252-255集成（中枢距离+量能配合+均线排列+盈亏比）**

### 新增

- **`_calc_mmd_zhongshu_distance_v80`**（`src/easy_tdx/chanlun/mmd.py`）—— 买卖点与中枢距离验证（条件252）。评估当前买卖点与最近完成中枢的距离关系，买入信号在中枢上方0-5%区间加分，过远（>10%）减分；卖出信号反之。返回 `distance_score`, `nearest_zs_dist_pct`, `zs_position`, `confidence_adjust`, `msg`。

- **`_calc_volume_confirmation_v80`**（`src/easy_tdx/chanlun/mmd.py`）—— 量能配合度评分（条件253）。评估近期成交量与价格趋势的配合程度：上涨+放量→加分，上涨+缩量→减分（量价背离），下跌+缩量→加分。返回 `confirmation_score`, `vol_ratio`, `volume_trend`, `price_trend`, `confidence_adjust`, `msg`。

- **`_calc_ma_alignment_strength_v80`**（`src/easy_tdx/chanlun/mmd.py`）—— 均线排列强度确认（条件254）。评估MA5/MA10/MA20/MA60的多空排列状态及价格相对位置。多头排列且价格在上方→+5%，空头排列且价格在下方→+5%，排列混乱→-2%。返回 `alignment_score`, `ma_alignment`, `price_position`, `confidence_adjust`, `msg`。

- **`_calc_dynamic_risk_reward_v80`**（`src/easy_tdx/chanlun/mmd.py`）—— 盈亏比动态评估（条件255）。基于近期波动区间动态评估止损止盈距离和盈亏比。盈亏比≥3:1→+4%，≥2:1→+2%，<1:1→-4%。返回 `rr_ratio`, `stop_loss_pct`, `take_profit_pct`, `risk_level`, `confidence_adjust`, `msg`。

### Bug修复

- **修复 `startswith("BUY")` / `startswith("SELL")` 逻辑错误**：MMDType枚举值为小写（`'1buy'`, `'3sell'`等），但V58-V80的所有增强函数使用了 `mmd.mmd_type.value.startswith("BUY")` 导致买/卖信号判断全部失效。已统一替换为 `"buy" in mmd.mmd_type.value` 模式，与项目其他地方保持一致。涉及33处修改。

- **修复 `_df.py` 日期解析容错**：`pd.to_datetime` 添加 `errors='coerce'` 参数，丢弃日期解析失败的脏数据行，避免TDX服务器偶尔返回非法年/月/日导致崩溃。

### 后端集成

- **MMD 类新增4个V80字段**（`src/easy_tdx/chanlun/types.py`）：`_mmd_zhongshu_distance_v80`, `_volume_confirmation_v80`, `_ma_alignment_strength_v80`, `_dynamic_risk_reward_v80`
- **ConditionGroup 新增 V80**（`src/easy_tdx/backtest/chanlun_validator.py`）：条件范围(252, 255)，描述"中枢距离+量能配合+均线排列+盈亏比"
- **诊断API增强**（`src/easy_tdx/web/routers/diagnosis.py`）：新增4个V80字段到 chanlun 响应 + v80_summary 顶层摘要 + condition_counts 支持
- **缠论推荐API增强**（`src/easy_tdx/web/routers/chanlun.py`）：新增 v80_summary 到响应

### 前端集成

- **`web-ui/src/types.ts`**：`DiagnosisChanlun` 新增4个V80可选字段；`DiagnosisResult` 新增 `v80_summary` 接口
- **`web-ui/src/views/DiagnosisView.vue`**：
  - 新增 `v80QualityLabel` 函数
  - 新增 V80 四维度量摘要卡片（Hero区域）
  - 新增4个V80条件卡片（中枢距离/量能配合/均线排列/盈亏比）
  - 新增 V80 CSS 样式（v80-msd, v80-vcf, v80-mas, v80-drr, v80-summary-row, v80-tag）
- **`web-ui/src/components/ChanlunChart.vue`**：图例动态显示（仅在有对应数据时显示笔/线段/中枢/分型/买卖点/背驰）
- **`web-ui/src/views/BacktestView.vue`**：
  - 缠论分析添加错误处理与错误状态显示
  - 限制K线数量为800根避免超时
  - 改进Pydantic验证错误解析

### 测试

- **`tests/unit/test_chanlun_v80.py`**（26 个测试用例）：
  - `TestV80ConditionGroup`：枚举存在性、条件范围(252-255)、描述文案
  - `TestV80MMDFields`：MMD对象包含4个V80字段
  - `TestV80BacktestValidator`：单组/多组合验证、summary输出
  - `TestV80Functions`：中枢距离（买入/卖出/数据不足）、量能配合（上涨放量/上涨缩量/下跌缩量/数据不足）、均线排列（多头/空头/混乱/数据不足）、盈亏比（极佳/良好/卖出/数据不足）、综合冒烟、V79兼容性

### 测试结果

- V79+V80+回测验证器联合测试：**180 passed**
- 全部缠论+回测单元测试：**762 passed, 1 warning**
- TypeScript编译：**零错误**
- Web UI构建：**built in 4.77s**

### API 验证

```bash
# 诊断API - V80字段
curl "http://127.0.0.1:8000/api/v1/diagnosis/quick?market=SZ&code=000001"
# 返回:
# v80_summary: {"quality_level": "moderate", "total_adjust": 0.06, ...}
# mmd_zhongshu_distance_v80: {"distance_score": 0.2, "zs_position": "above", ...}
# volume_confirmation_v80: {"confirmation_score": 0.65, "price_trend": "up", ...}
# ma_alignment_strength_v80: {"alignment_score": 0.9, "ma_alignment": "bullish", ...}
# dynamic_risk_reward_v80: {"rr_ratio": 3.21, "risk_level": "excellent", ...}

# 缠论推荐API - V80摘要
curl -X POST "http://127.0.0.1:8000/api/v1/chanlun/recommend" \
  -H "Content-Type: application/json" \
  -d '{"market":"SZ","code":"000001"}'
# 返回:
# v80_summary: {"zs_position": "...", "volume_confirmed": "↑↓", ...}
```

---

## 核心功能清单（更新后）

### 缠论买卖点增强（V58-V80）
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
| V79 | 248-251 | 分型稳定性验证+距离安全阈值+多级别结构一致性+动能持续性 |
| **V80** | **252-255** | **中枢距离验证+量能配合度+均线排列强度+盈亏比动态评估** |

### 诊断系统
| 功能 | 状态 |
|------|------|
| MACD/KDJ/RSI/BOLL/均线/成交量/ATR分析 | ✅ |
| 综合评分+仓位建议+止损止盈 | ✅ |
| V67-V79 缠论条件卡片（共 44 张） | ✅ |
| V76-V78 四维度量摘要（Hero区域） | ✅ |
| **V79 四维度量摘要（Hero区域）** | ✅ |
| **V80 四维度量摘要（Hero区域）** | ✅ **新增** |
| **V80 四维度量分析卡片（4张）** | ✅ **新增** |

### 前端优化
| 功能 | 状态 |
|------|------|
| 缠论图表图例动态显示 | ✅ **新增** |
| 回测页缠论分析错误处理 | ✅ **新增** |
| K线数量限制（800根） | ✅ **新增** |
