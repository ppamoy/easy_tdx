# 更新日志 V78

## [V78] — 2026-08-28

**缠论模型精准度再提升 - 条件244-247集成（周期位置评分+多信号共识+波动率压缩+资金流向背离）**

### 新增

- **`_calc_mmd_cycle_position_v78`**（`src/easy_tdx/chanlun/mmd.py`）—— 买卖点周期位置评分（条件244）。评估当前买卖点在60日波段中的相对位置，买入在底部加分、在顶部减分，卖出反之。返回 `position_score`, `cycle_position`, `distance_to_low`, `distance_to_high`, `confidence_adjust`, `msg`。

- **`_calc_multi_signal_consensus_v78`**（`src/easy_tdx/chanlun/mmd.py`）—— 多信号时间窗口一致性（条件245）。在20根K线窗口内统计附近买卖点方向，判断强共识/中共识/分歧/孤立。返回 `consensus_score`, `nearby_buy_count`, `nearby_sell_count`, `consensus_level`, `confidence_adjust`, `msg`。

- **`_calc_volatility_compression_breakout_v78`**（`src/easy_tdx/chanlun/mmd.py`）—— 波动率压缩突破预测（条件246）。基于布林带宽度的历史百分位判断压缩/扩张状态，结合 percent_b 预测突破方向。返回 `compression_score`, `boll_width_percentile`, `breakout_direction`, `confidence_adjust`, `msg`。

- **`_calc_fund_flow_divergence_v78`**（`src/easy_tdx/chanlun/mmd.py`）—— 资金流向与价格背离检测（条件247）。计算20日量价相关系数，检测看涨/看跌背离和量价齐升/齐跌。返回 `divergence_type`, `money_flow_score`, `volume_price_correlation`, `confidence_adjust`, `msg`。

### 后端集成

- **MMD 类新增4个V78字段**（`src/easy_tdx/chanlun/types.py`）：`_mmd_cycle_position_v78`, `_multi_signal_consensus_v78`, `_volatility_compression_breakout_v78`, `_fund_flow_divergence_v78`
- **ConditionGroup 新增 V78**（`src/easy_tdx/backtest/chanlun_validator.py`）：条件范围(244, 247)，描述"买卖点周期位置评分+多信号时间窗口一致性+波动率压缩突破预测+资金流向背离检测"
- **诊断API增强**（`src/easy_tdx/web/routers/diagnosis.py`）：新增4个V78字段到 chanlun 响应 + 多股对比condition_counts支持

### 前端集成

- **`web-ui/src/types.ts`**：`DiagnosisChanlun` 新增4个V78可选字段
- **`web-ui/src/views/DiagnosisView.vue`**：新增4个V78条件卡片（周期位置/信号共识/波动率压缩/资金流向背离）+ CSS样式

### 测试

- **`tests/unit/test_chanlun_v78.py`**（26 个测试用例）：
  - `TestV78ConditionGroup`：枚举存在性、条件范围(244-247)、描述文案
  - `TestV78MMDFields`：MMD对象包含4个V78字段
  - `TestV78BacktestValidator`：单组/多组合验证、summary输出
  - `TestV78Functions`：周期位置（底部买入/顶部卖出/不足/中部）、信号共识（强共识/孤立/不足/等级）、波动率压缩（压缩/扩张/不足/百分位）、资金流向（看涨背离/量价齐升/中性/不足/相关系数）、综合冒烟、V77一致性

### 测试结果

- V75+V76+V77+V78 联合测试：**89 passed**
- TypeScript编译：**零错误**
- Web UI构建：**built in 4.41s**

### API 验证

```bash
curl "http://127.0.0.1:8000/api/v1/diagnosis/quick?market=SZ&code=000001"
# 返回:
# mmd_cycle_position_v78: {"position_score": 0.9, "cycle_position": "top", ...}
# multi_signal_consensus_v78: {"consensus_score": 0.5, "consensus_level": "isolated", ...}
# volatility_compression_breakout_v78: {"compression_score": 0.3, "breakout_direction": "up_continuing", ...}
# fund_flow_divergence_v78: {"divergence_type": "neutral", "money_flow_score": 0.5, ...}
```

---

## 核心功能清单（更新后）

### 缠论买卖点增强（V58-V78）
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
| **V78** | **244-247** | **周期位置评分+多信号共识+波动率压缩突破+资金流向背离** |

### 诊断系统
| 功能 | 状态 |
|------|------|
| MACD/KDJ/RSI/BOLL/均线/成交量/ATR分析 | ✅ |
| 综合评分+仓位建议+止损止盈 | ✅ |
| V67-V78 缠论条件卡片（共 48 张） | ✅ |
| V76 四维验证摘要（Hero区域） | ✅ |
| V77 四维度量分析卡片 | ✅ |
| V78 四维度量分析卡片 | ✅ |
