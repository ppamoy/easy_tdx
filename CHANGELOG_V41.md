# EasyTDX 项目更新日志 V41

## 更新时间
2026-08-23

## 本次更新内容

### 条件111：量价能量分布分析（Volume-Price Energy Distribution）
**新增函数：**
- `_calc_volume_price_energy_dist(mmd, closes, volumes, highs, lows)`

**检测逻辑：**
- 基于已有 `_calc_volume_profile` 分析成交量分布
- 买入信号：价格处于高成交量支撑区（距离<2%）→ +3%；支撑区边缘（距离<5%）→ +1%
- 卖出信号：价格处于高成交量阻力区（距离<2%）→ +3%；阻力区边缘（距离<5%）→ +1%
- 价格处于低成交量真空区 → -1%；价格接近强阻力/支撑但方向相反 → -2%
- 防止在支撑不足区域追涨、阻力不足区域杀跌

**MMD新增字段：**
- `_volume_price_energy_dist`: 量价能量分布字典

### 条件112：量能周期检测（Volume Cycle Detection）
**新增函数：**
- `_calc_volume_cycle_detection(closes, volumes)`

**检测逻辑：**
- 比较短期(10日)、中期(20日)、长期(50日)成交量均值
- 扩张周期（短期>长期×1.2）：趋势延续性强
- 收缩周期（短期<长期×0.8）：趋势可能衰竭
- 量价配合度：价格上涨时成交量同步放大 → +2%
- 防止逆势操作时的过度自信

**MMD新增字段：**
- `_volume_cycle_detection`: 量能周期字典
**全局存储：** `find_mmds_v39._last_volume_cycle`

### 条件113：走势预测（Post-Signal Trajectory Prediction）
**新增函数：**
- `_calc_post_signal_trajectory(closes, volumes, macd_data)`

**检测逻辑：**
- MACD柱状图斜率判断动能方向
- 价格加速度（二阶差分）判断趋势延续性
- 成交量确认：放量上涨加分，放量下跌减分
- 综合评分生成方向预测（up/down/neutral）
- 计算预期收益区间和置信度
- 方向与信号一致 → +2%；方向相反 → -2%

**MMD新增字段：**
- `_post_signal_trajectory`: 走势预测字典
**全局存储：** `find_mmds_v39._last_trajectory_prediction`

### 条件114：动态质量分层（Dynamic Quality Tier Classification）
**新增函数：**
- `_calc_quality_tier_classification(mmds, all_confidences)`

**检测逻辑：**
- 综合置信度+联合评分+质量评分计算综合质量分
- 按质量分排序，动态分配S/A/B/C层级
- S级（前10%）：+3%；A级（10%-30%）：+1%
- B级（30%-70%）：无调整；C级（后30%）：-1%
- 根据买卖点类型独立排名，避免不同类型间不公平比较

**MMD新增字段：**
- `_quality_tier_classification`: 质量分层字典（含tier和rank）

### 条件115：反转风险评估（Reversal Risk Assessment）
**新增函数：**
- `_calc_reversal_risk_assessment(closes, volumes, highs, lows, macd_data, volatility)`

**检测逻辑：**
- RSI超买（>75）→ +0.3风险；RSI超卖（<25）→ +0.25风险
- MACD顶底背离检测 → +0.35风险
- 量价背离（价格上涨但缩量）→ +0.2风险
- 趋势加速度衰减 → +0.15风险
- 风险等级：low(<0.2)/medium(0.2-0.4)/high(0.4-0.6)/extreme(>0.6)
- 高风险时信号置信度减3%-8%
- 防止在高反转风险区域追涨杀跌

**MMD新增字段：**
- `_reversal_risk_assessment`: 反转风险评估字典
**全局存储：** `find_mmds_v39._last_reversal_risk`

## 核心架构改进

### find_mmds_v41 新函数
- 完整集成条件101-115
- 与 `find_mmds_v40` 接口完全兼容
- ChanlunAnalyser 已切换至使用 `find_mmds_v41`

### ChanlunAnalyser 升级
- `analyser.py` 已将 `find_mmds_v40` 替换为 `find_mmds_v41`
- 所有缠论分析自动获得V41增强

### API 与 Web UI 接入
- `src/easy_tdx/web/routers/diagnosis.py`：暴露5个V41字段到API
- `web-ui/src/types.ts`：新增V41 TypeScript接口

## 测试结果

```
======================== 459 passed, 1 warning in 3.09s ========================
V41专项测试: 16 passed
V40专项测试: 21 passed
V39专项测试: 21 passed
缠论核心测试: 33 passed
```

**V41 专项测试：**
```
TestV41VolumePriceEnergyDist:                2 passed
TestV41VolumeCycleDetection:                 2 passed
TestV41PostSignalTrajectory:                 2 passed
TestV41QualityTierClassification:            2 passed
TestV41ReversalRiskAssessment:               2 passed
TestV41Integration:                          6 passed
```

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/mmd.py` | 新增5个V41函数 + find_mmds_v41 + find_mmds_v39集成（条件111-115） |
| `src/easy_tdx/chanlun/types.py` | MMD类新增5个V41字段 |
| `src/easy_tdx/chanlun/analyser.py` | 切换至 find_mmds_v41 |
| `src/easy_tdx/web/routers/diagnosis.py` | 暴露V41 5个字段到API |
| `web-ui/src/types.ts` | 新增V41 TypeScript接口 |
| `tests/unit/test_chanlun_enhancements.py` | 新增16个V41测试用例 |
| `CHANGELOG_V41.md` | 本次更新日志 |

## V41 vs V40 效果预期

| 指标 | V40 | V41 | 变化 |
|------|-----|-----|------|
| 条件总数 | 110 | 115 | +5 |
| 量价能量分析 | 无 | 成交量剖面支撑/阻力识别 | 新增 |
| 量能周期 | 无 | 扩张/收缩周期检测 | 新增 |
| 走势预测 | 无 | MACD动能锥+价格加速度预测 | 新增 |
| 质量分层 | 无 | S/A/B/C动态分层 | 新增 |
| 反转风险 | 无 | 多指标综合反转风险评估 | 新增 |

## 核心设计理念

V41的核心改进思路是"**能量验证+方向预测+风险预警**"：

1. **量价能量分布**：成交量是价格的"能量"，高成交量区域代表市场共识强的价格水平。V41通过分析成交量剖面，判断当前价格是否处于有足够"能量支撑"的位置，避免在虚假突破处追涨。

2. **量能周期检测**：成交量周期与价格周期存在内在关联。V41通过多时间窗口成交量比较，识别当前处于扩张还是收缩周期，顺势而为，避免逆势操作。

3. **走势预测**：单一信号的准确性有限，但结合MACD动能和价格加速度的综合预测可以提供方向参考。V41的预测模型作为辅助参考，不与缠论主信号冲突。

4. **动态质量分层**：不同买卖点的综合质量差异很大。V41通过动态分层让优质信号获得额外加成，低质量信号被适当降权，使置信度更能反映真实可靠性。

5. **反转风险评估**：任何趋势都有反转的可能。V41通过多项指标综合评估当前反转风险，在高风险区域降低信号置信度，保护用户避免在趋势末端追涨杀跌。

---

**版本**: V41.0
**完成日期**: 2026-08-23
**测试状态**: ✅ 459 passed（缠论专项），1 warning，0 failures
**构建状态**: ✅ Web UI 类型定义更新完成
**Git 状态**: ✅ 待提交
