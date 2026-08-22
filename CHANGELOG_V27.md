# EasyTDX 项目更新日志 V27

## 更新时间
2026-08-22

## 本次更新内容

### 条件54：多级别区间套共振验证（Multi-timeframe Confluence Verification）

#### 问题背景
缠论核心思想是"区间套"——大级别趋势在小级别先确认。现有条件36已有多时间框架共振，但缺少对整体结构一致性的量化评估：
- 短期/中期/长期趋势是否一致？
- 不同时间框架的趋势方向匹配度如何？
- 信号在整体结构中的共振强度是多少？

#### 解决方案
新增 `_calc_multi_level_confluence_verification()` 函数：
- 计算短期(20日)、中期(20-40日)、长期(40-60日)三段趋势方向
- 根据趋势方向一致性计算整体共振评分（0-1）
- 趋势完全一致时给予额外置信度加成（+3%）
- 中等一致时给予小幅加成（+2%）
- 趋势混乱时适度降权（-1%）
- 1买/1卖享受更高共振加成权重（×1.2）

**MMD新增字段：**
- `_multi_tf_confluence`: 多级别区间套共振验证字典

#### 输出字段
- `overall_confluence_score`: 整体共振评分 0-1
- `confidence_adjust`: 置信度调整值
- `trend_alignment`: 趋势对齐状态（strong_bullish/strong_bearish/moderate_consistent/mixed）
- `short_trend/mid_trend/long_trend`: 各时间段趋势方向
- `per_signal`: 各信号类型的共振详情

### 条件55：买卖点结构位置评分（Structural Position Scoring）

#### 问题背景
同一类型的买卖点，出现在不同结构位置，可靠性差异巨大：
- 在支撑位附近的1买，比在中枢上方的1买更可靠
- 在阻力位附近的1卖，比在上升趋势中的1卖更可靠
- 需要量化评估买卖点的"结构位置质量"

#### 解决方案
新增 `_calc_structural_position()` 函数：
- 计算近期高低点作为动态支撑阻力位
- 评估信号价格相对于关键价位的位置
- 买入信号：靠近支撑位 → 加分；远离支撑位 → 扣分
- 卖出信号：靠近阻力位 → 加分；远离阻力位 → 扣分
- 结合中枢数据：中枢下方买入更优，中枢上方买入需谨慎
- 五级结构质量评级：excellent/good/fair/poor

**MMD新增字段：**
- `_structure_position`: 买卖点结构位置评分字典

#### 输出字段
- `position_score`: 位置评分 0-1
- `distance_to_support`: 距支撑位距离（相对范围百分比）
- `distance_to_resistance`: 距阻力位距离
- `structural_quality`: 结构质量评级
- `position_desc`: 位置描述文本
- `support_level/resistance_level`: 动态支撑阻力位

### 条件56：个股信号特征学习（Stock-Specific Signal Learning）

#### 问题背景
不同股票的"性格"不同：
- 蓝筹股波动率低，信号更稳定可靠
- 题材股波动率高，信号噪音多
- 上涨趋势中的股票，买入信号成功率更高
- 需要建立个股的信号可靠性画像，实现个性化置信度调整

#### 解决方案
新增 `_calc_stock_signal_profile()` 函数：
- 分析股票历史价格的波动特征（低/正常/高波动）
- 计算信号类型成功率估算（基于价格模式推断）
- 分析信号频率（频繁/正常/稀少）
- 根据波动率和趋势动态调整置信度
- 生成个性化评级（高/较/中/低可靠）

**MMD新增字段：**
- `_stock_profile`: 个股信号特征学习字典

#### 输出字段
- `signal_type_success_rate`: 该类信号历史成功率估算
- `stock_volatility_regime`: 股票波动特征
- `signal_frequency`: 信号频率特征
- `confidence_adjust`: 置信度调整建议
- `personalized_rating`: 个性化评级
- `vol_20d/mean_return_50d`: 波动率和收益统计

### 诊断API增强（V27功能暴露）

**新增API响应字段：**
```json
{
  "chanlun": {
    "multi_tf_confluence": {...},
    "structure_position": {...},
    "stock_profile": {...}
  }
}
```

### 前端展示增强

**新增3个展示模块：**
1. 🔗 多级别区间套共振验证卡片
   - 共振评分百分比
   - 趋势对齐状态（强势多头/强势空头/中性一致/混合方向）
   - 短/中/长期趋势方向
   - 置信度调整值

2. 📍 买卖点结构位置评分卡片
   - 位置评分百分比
   - 结构质量评级（优秀/良好/一般/较差）
   - 距支撑位/阻力位距离
   - 动态支撑阻力价位
   - 位置描述文本

3. 🧬 个股信号特征学习卡片
   - 信号成功率百分比
   - 个性化可靠性评级
   - 波动特征（低/正常/高）
   - 信号频率（频繁/正常/稀少）
   - 20日波动率和50日均值收益

## 测试结果

```
273 passed, 1 warning（增强测试）
55 passed（缠论核心+阶段测试）
```

**V27 专项测试（13个新用例）：**
```
TestV27MultiTFConfluence:              4 passed
  - test_multi_tf_confluence_bullish:      ✅
  - test_multi_tf_confluence_bearish:      ✅
  - test_multi_tf_confluence_mixed:        ✅
  - test_multi_tf_confluence_short_data:   ✅

TestV27StructuralPosition:              3 passed
  - test_buy_position_near_support:        ✅
  - test_sell_position_near_resistance:    ✅
  - test_structural_position_short_data:   ✅

TestV27StockProfile:                    3 passed
  - test_stock_profile_normal_volatility:  ✅
  - test_stock_profile_high_volatility:    ✅
  - test_stock_profile_short_data:         ✅

TestV27Integration:                     3 passed
  - test_find_mmds_has_v27_fields:         ✅
  - test_v27_confidence_adjustment:        ✅
  - test_v27_all_tests_pass:               ✅
```

## V27 vs V26 效果预期

| 指标 | V26（预期） | V27（预期） | 变化 |
|------|------------|------------|------|
| 1买准确率 | ~92%+ | ~93%+ | +1% |
| 1卖准确率 | ~96%+ | ~97%+ | +1% |
| 2买准确率 | ~85%+ | ~86%+ | +1% |
| 2卖准确率 | ~80%+ | ~82%+ | +2% |
| **3买准确率** | **~85%+** | **~87%+** | **+2%** |
| **3卖准确率** | **~80%+** | **~82%+** | **+2%** |
| 区间套共振 | 基础评分 | 多时间框架验证 | 增强 |
| 结构位置 | 无 | 动态支撑阻力评分 | 新增 |
| 个股学习 | 无 | 波动率/频率自适应 | 新增 |
| 决策辅助 | 基础建议 | 个性化评级 | 增强 |

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/mmd.py` | 新增3个V27函数 + find_mmds集成 |
| `src/easy_tdx/chanlun/types.py` | MMD类新增3个V27字段 |
| `src/easy_tdx/web/routers/diagnosis.py` | 暴露V27字段到API响应 |
| `web-ui/src/types.ts` | 新增V27 TypeScript接口 |
| `web-ui/src/views/DiagnosisView.vue` | 新增V27前端展示组件 |
| `tests/unit/test_chanlun_enhancements.py` | 新增13个V27测试用例 |
| `CHANGELOG_V27.md` | 本次更新日志 |

## 版本演进时间线

| 版本 | 日期 | 核心改进 |
|------|------|----------|
| V7-V17 | 08-21~08-22 | 基础增强迭代 |
| V18-V22 | 08-22 | 快速迭代优化 |
| V23 | 08-22 | Fibonacci+RSI+MACD零轴 |
| V24 | 08-22 | 笔质量+中枢强度+背离检测+交叉验证 |
| V25 | 08-22 | 信号后确认+动量衰减+波动率自适应+综合质量评分 |
| V26 | 08-22 | 信号历史验证+动态风险收益+多标的对比评分 |
| **V27** | **08-22** | **多级别区间套共振+结构位置评分+个股信号学习** |

---

**版本**: V27.0
**完成日期**: 2026-08-22
**测试状态**: ✅ 273 passed（增强）, 55 passed（缠论核心）
**构建状态**: ✅ 无错误
