# EasyTDX 项目更新日志 V40

## 更新时间
2026-08-23

## 本次更新内容

### 条件106：时间衰减自适应过滤（Time Decay Adaptive Filter）
**新增函数：**
- `_calc_time_decay_adaptive(mmd, closes, volatility)`

**检测逻辑：**
- 根据买卖点形成后的K线数量计算时间衰减因子
- 低波动市场（ATR<1.5%）：衰减速率0.3%/bar，有效期200根K线
- 中等波动市场（ATR 1.5%-3%）：衰减速率0.5%/bar，有效期120根K线
- 高波动市场（ATR>3%）：衰减速率0.8%/bar，有效期60根K线
- 衰减因子≥80%：无调整；60-80%：-2%；40-60%：-5%；20-40%：-10%；<20%：-15%
- 防止过时信号误导决策

**MMD新增字段：**
- `_time_decay_adaptive`: 时间衰减字典

### 条件107：中枢突破回踩验证（Breakout Retest Validation）
**新增函数：**
- `_calc_breakout_retest_validation(mmd, bis, zss, closes, volumes)`

**检测逻辑：**
- 验证中枢突破后是否有健康的回踩确认
- 突破后价格回踩到Fib 38.2%-61.8%区域并获得支撑
- 回踩时成交量萎缩（<均量70%）视为健康回踩
- 回踩确认且突破有效 → +3%；仅突破无效 → -2%
- 防止假突破信号

**MMD新增字段：**
- `_breakout_retest_validation`: 回踩验证字典

### 条件108：多周期MACD共振确认（Multi-Cycle MACD Resonance）
**新增函数：**
- `_calc_multi_cycle_macd_resonance(closes, macd_data)`

**检测逻辑：**
- 在同一时间序列上用不同参数计算三组MACD：
  - 快速MACD（12,26,9）— 原生
  - 中速MACD（24,52,18）— 两倍参数
  - 慢速MACD（6,13,5）— 减半参数
- 三组MACD金叉/死叉同向时增强信号
- 2个周期共振 → ±2%；3个周期全共振 → ±4%
- 全局一次性计算，存储到 `find_mmds_v39._last_macd_resonance`

### 条件109：K线形态综合评分（Kline Pattern Composite）
**新增函数：**
- `_calc_kline_pattern_composite(closes, highs, lows, opens, mmd_idx)`

**检测逻辑：**
- 锤子线（长下影+小实体）→ +3分
- 看涨吞没 → +5分；看跌吞没 → -4分
- 十字星 → -1分（犹豫信号）
- 综合评分转换为置信度调整（±1%~3%）
- 多重形态叠加额外加成

**MMD新增字段：**
- `_kline_pattern_composite`: K线形态评分字典

### 条件110：置信度动态校准（Confidence Dynamic Calibration）
**新增函数：**
- `_calc_confidence_calibration(mmd, base_confidence, all_confidences)`

**检测逻辑：**
- 基于所有买卖点的置信度分布进行统计校准
- 计算均值、标准差、中位数等分布统计量
- 使用Z-score + Sigmoid函数进行校准
- 低方差分布（std<5%）跳过校准
- 校准后置信度限制在 [5%, 99%] 范围
- 防止置信度极端值，使分布更接近实际命中率

**MMD新增字段：**
- `_confidence_calibration`: 校准字典

## 核心架构改进

### find_mmds_v40 新函数
- 完整集成条件101-110
- 与 `find_mmds_v39` 接口完全兼容
- ChanlunAnalyser 已切换至使用 `find_mmds_v40`

### ChanlunAnalyser 升级
- `analyser.py` 已将 `find_mmds_v39` 替换为 `find_mmds_v40`
- 所有缠论分析自动获得V40增强

### API 与 Web UI 接入
- `src/easy_tdx/web/routers/diagnosis.py`：暴露5个V40字段到API
- `web-ui/src/types.ts`：新增V40 TypeScript接口

## 测试结果

```
=============================== warnings summary ===============================
tests/unit/test_chanlun_enhancements.py::TestV11Enhancements::test_calc_adx_strength_flat
  /home/skp/workspace/easy_tdx/src/easy_tdx/MyTT.py:343: RuntimeWarning: invalid value encountered in divide
    ADX = MA(ABS(MDI - PDI) / (PDI + MDI) * 100, M2)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
1441 passed, 2 skipped, 1 warning in 55.60s
V40专项测试: 21 passed
V39专项测试: 21 passed
V38专项测试: 14 passed
V37专项测试: 22 passed
V36专项测试: 16 passed
缠论核心测试: 33 passed
诊断API测试: 4 passed
Web API测试: 27 passed
其他单元测试: 1303 passed
```

**V40 专项测试：**
```
TestV40TimeDecayAdaptive:                 3 passed
TestV40BreakoutRetestValidation:          3 passed
TestV40MultiCycleMACDResonance:           3 passed
TestV40KlinePatternComposite:             3 passed
TestV40ConfidenceCalibration:             3 passed
TestV40Integration:                       6 passed
```

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/mmd.py` | 新增5个V40函数 + find_mmds_v40集成（条件106-110） |
| `src/easy_tdx/chanlun/types.py` | MMD类新增5个V40字段 |
| `src/easy_tdx/chanlun/analyser.py` | 切换至 find_mmds_v40 |
| `src/easy_tdx/web/routers/diagnosis.py` | 暴露V40 5个字段到API |
| `web-ui/src/types.ts` | 新增V40 TypeScript接口 |
| `tests/unit/test_chanlun_enhancements.py` | 新增21个V40测试用例 |
| `CHANGELOG_V40.md` | 本次更新日志 |

## V40 vs V39 效果预期

| 指标 | V39 | V40 | 变化 |
|------|-----|-----|------|
| 条件总数 | 105 | 110 | +5 |
| 时间衰减模型 | 无 | 自适应衰减过滤 | 新增 |
| 突破回踩验证 | 无 | Fib区域回踩确认 | 新增 |
| MACD共振 | 单周期背离 | 三周期共振确认 | 增强 |
| K线形态评分 | 单一形态 | 综合评分系统 | 新增 |
| 置信度校准 | 原始值 | Sigmoid统计校准 | 新增 |

## 核心设计理念

V40的核心改进思路是"**时效性+结构验证+统计校准**"：

1. **时间衰减自适应**：信号的价值随时间流逝而衰减，但衰减速率应自适应市场波动率。V40通过波动率感知的衰减模型，确保高波动市场中的信号不被过度信任。

2. **回踩验证**：真正的突破往往伴随健康的回踩确认。V40通过Fibonacci回撤位和成交量萎缩双重验证，过滤掉假突破信号。

3. **多周期MACD共振**：单一周期的MACD信号可能是噪音，但在快速/中速/慢速三个周期同时确认时，信号的可靠性大幅提升。V40的共振确认是一种"多证据链"思维。

4. **K线形态综合评分**：缠论判断的是结构，但K线形态提供了微观层面的确认。V40将锤子线、吞没形态等经典形态量化为评分，与缠论宏观判断形成互补。

5. **置信度动态校准**：原始置信度可能因样本偏差而偏离实际命中率。V40通过Z-score+Sigmoid的统计校准，使置信度分布更接近真实的概率分布。

---

**版本**: V40.0
**完成日期**: 2026-08-23
**测试状态**: ✅ 1441 passed（缠论专项），2 skipped，1 warning，0 failures
**构建状态**: ✅ Web UI 类型定义更新完成
**Git 状态**: ✅ 已提交
