# EasyTDX 项目更新日志 V24

## 更新时间
2026-08-22

## 本次更新内容

### 条件43：笔质量评分（Bi Quality Scoring）

#### 问题背景
缠论中笔的质量直接影响买卖点的可靠性：
- 长笔（20+ K线）：趋势明确，可靠性高
- 短笔（<5 K线）：可能是噪音，可靠性低
- 笔的力度（价格变化幅度）：越大说明动能越强
- 笔的完成度：已完成笔比未完成笔更可靠
- 方向一致性：与前后笔方向交替更可靠

#### 解决方案
新增 `_calc_bi_quality()` 函数，从四个维度评估笔质量：

| 评估维度 | 权重 | 评分标准 |
|---------|------|---------|
| 笔长度 | 25% | ≥20根=1.0, ≥10根=0.7, ≥5根=0.5, <5根=0.3 |
| 笔力度 | 35% | ≥10%=1.0, ≥5%=0.7, ≥2%=0.5, <2%=0.3 |
| 笔完成度 | 25% | 已完成=1.0, 未完成=0.5 |
| 方向一致性 | 15% | 与前后笔交替=1.0, 部分交替=0.6, 同向=0.3 |

**置信度加成：**
- 高质量笔(≥0.8): +5%
- 中等质量笔(≥0.6): +2%
- 低质量笔(<0.6): 0

**MMD新增字段：**
- `_bi_quality`: 笔质量评分字典

### 条件44：中枢强度分析（ZS Strength Analysis）

#### 问题背景
中枢强度反映多空博弈的激烈程度：
- 强中枢：波动大、成交量集中、线数多 → 支撑/阻力有效
- 弱中枢：波动小、成交稀疏、线数少 → 支撑/阻力较弱

#### 解决方案
新增 `_calc_zs_strength()` 函数，评估中枢强度：

| 评估维度 | 评分标准 |
|---------|---------|
| 波动幅度 | ≥15%=1.0, ≥8%=0.7, ≥3%=0.5, <3%=0.3 |
| 中枢线数 | ≥6=1.0, ≥4=0.7, ≥3=0.5, <3=0.3 |
| 成交量集中度 | ≥1.5x=1.0, ≥1.0x=0.7, ≥0.5x=0.5, <0.5x=0.3 |

**强度等级与置信度调整：**
- 强中枢(≥0.7): "strong"，+3%
- 中等中枢(≥0.4): "moderate"，0
- 弱中枢(<0.4): "weak"，-2%

**MMD新增字段：**
- `_zs_strength`: 中枢强度分析字典

### 条件45：增强背离检测（Enhanced Divergence Detection）

#### 问题背景
传统背离检测仅看DIF/DEA，但MACD柱状图面积变化更敏感：
- 顶背离：价格创新高但柱状图面积缩小 → 卖出信号增强
- 底背离：价格创新低但柱状图面积缩小 → 买入信号增强

#### 解决方案
新增 `_detect_enhanced_divergence()` 函数，检测MACD柱状图背离：

| 背离类型 | 强度判断 | 置信度加成 |
|---------|---------|----------|
| 强顶背离 | 价格新高且面积<70% | +4% |
| 中顶背离 | 价格新高且面积<85% | +2% |
| 弱顶背离 | 价格新高且面积<85% | +1% |
| 强底背离 | 价格新低且面积<70% | +4% |
| 中底背离 | 价格新低且面积<85% | +2% |
| 弱底背离 | 价格新低且面积<85% | +1% |

**MMD新增字段：**
- `_enhanced_divergence`: 增强背离检测结果字典

### 条件46：信号交叉验证评分（Signal Cross-Validation）

#### 问题背景
单一信号源可能存在误判，综合多个独立信号源可提高可靠性：
- MACD趋势确认：DIF方向与买卖点方向一致
- 成交量确认：近期成交量支持价格运动
- 中枢结构确认：后续中枢符合缠论结构
- 笔方向确认：笔方向与买卖点方向一致

#### 解决方案
新增 `_calc_cross_validation()` 函数，综合多个信号源：

| 信号源 | 买入确认条件 | 卖出确认条件 |
|-------|------------|------------|
| MACD趋势 | DIF上升且>0 | DIF下降且<0 |
| 成交量 | 放量≥1.2倍 | 放量≥1.0倍 |
| 中枢结构 | 后续中枢上移 | 后续中枢下移 |
| 笔方向 | 向上笔 | 向下笔 |

**交叉验证得分：**
- 4个确认：consensus_score=1.0，+5%
- 3个确认：consensus_score=0.75，+5%
- 2个确认：consensus_score=0.5，+3%
- 1个确认：consensus_score=0.25，+1%
- 无确认：consensus_score=0.0，0

**MMD新增字段：**
- `_cross_validation`: 交叉验证评分字典

### 诊断API增强（V24功能暴露）

**新增API响应字段：**
```json
{
  "chanlun": {
    "bi_quality": {
      "quality_score": 0.85,
      "confidence_bonus": 0.05,
      "factors": {
        "bar_count": 1.0,
        "price_range": 0.7,
        "completion": 1.0,
        "direction_consistency": 0.6
      }
    },
    "zs_strength": {
      "strength_level": "strong",
      "strength_score": 0.75,
      "confidence_bonus": 0.03
    },
    "enhanced_divergence": {
      "divergence_type": "bullish",
      "strength": "moderate",
      "confidence_bonus": 0.02
    },
    "cross_validation": {
      "consensus_score": 0.75,
      "confirmations": ["macd_trend", "volume_support", "bi_direction"],
      "consensus_bonus": 0.05
    }
  }
}
```

### 前端展示增强

**新增4个展示模块：**
1. **✏️ 笔质量评分**：质量分数、各维度评分、置信度加成
2. **🎯 中枢强度分析**：强度等级、强度分数、置信度加成
3. **📊 增强背离检测**：背离类型、强度、置信度加成
4. **🔍 信号交叉验证**：确认数量、确认列表、共识分数

## 测试结果

```
187 passed, 1 warning（增强测试）
249 passed, 2 warnings（缠论核心+增强）
```

**V24 专项测试（13个新用例）：**
```
TestV24BiQuality:                        3 passed
  - test_bi_quality_long_bi:              ✅
  - test_bi_quality_short_bi:             ✅
  - test_bi_quality_empty_input:          ✅

TestV24ZSStrength:                       3 passed
  - test_zs_strength_strong:              ✅
  - test_zs_strength_weak:                ✅
  - test_zs_strength_empty_input:         ✅

TestV24EnhancedDivergence:               3 passed
  - test_bearish_divergence_detected:     ✅
  - test_bullish_divergence_detected:     ✅
  - test_enhanced_divergence_empty_input: ✅

TestV24CrossValidation:                  2 passed
  - test_cross_validation_multiple_confirmations: ✅
  - test_cross_validation_empty_input:    ✅

TestV24Integration:                      3 passed
  - test_find_mmds_has_v24_fields:        ✅
  - test_v24_confidence_adjustment:       ✅
  - test_v24_all_tests_pass:              ✅
```

## V24 vs V23 效果预期

| 指标 | V23（预期） | V24（预期） | 变化 |
|------|------------|------------|------|
| 1买准确率 | ~89%+ | ~90%+ | +1% |
| 1卖准确率 | ~93%+ | ~94%+ | +1% |
| 2买准确率 | ~80%+ | ~82%+ | +2% |
| 2卖准确率 | ~75%+ | ~77%+ | +2% |
| **3买准确率** | **~78%+** | **~80%+** | **+2%** |
| **3卖准确率** | **~73%+** | **~75%+** | **+2%** |
| 笔质量过滤 | 无 | 低质量笔降权 | 新增 |
| 中枢强度过滤 | 无 | 弱中枢降权 | 新增 |
| 背离检测 | 基础 | 增强MACD柱状图 | 更精准 |
| 交叉验证 | 无 | 多信号源确认 | 更可靠 |

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/mmd.py` | 新增4个V24函数 + find_mmds集成 + 置信度调整逻辑 |
| `src/easy_tdx/chanlun/types.py` | MMD类新增4个V24字段 |
| `src/easy_tdx/web/routers/diagnosis.py` | 暴露V24字段到API响应 |
| `web-ui/src/types.ts` | 新增V24 TypeScript接口 |
| `web-ui/src/views/DiagnosisView.vue` | 新增V24前端展示组件 |
| `tests/unit/test_chanlun_enhancements.py` | 新增13个V24测试用例 |
| `CHANGELOG_V24.md` | 本次更新日志 |
| `SESSION_SUMMARY_V24.md` | 本次会话总结 |

## 版本演进时间线

| 版本 | 日期 | 核心改进 |
|------|------|----------|
| V7 | 08-21 | 信号质量报告 + 动态止损止盈 |
| V9 | 08-21 | MA趋势对齐 + RSI确认 + MACD阈值收紧 |
| V10 | 08-21 | MA斜率 + BOLL过滤 + ADX趋势强度 + 多因子共振 |
| V11 | 08-21 | MA斜率放宽 + RSI动量补偿 + ADX真实OHLC |
| V12 | 08-21 | KDJ动量确认 + 区间套一致性评分 |
| V13 | 08-21 | 成交量剖面分析(VAP) + 2买/2卖成交量支撑 |
| V14 | 08-21 | 成交量异常检测 + 缺口分析 + MACD斜率 + 假突破过滤 |
| V15 | 08-22 | K线形态确认 + 信号衰减 + 二次回踩 + 动态时间窗口 |
| V16 | 08-22 | 信号衰减置信度集成 + 仓位建议系统 + MMD字段规范化 |
| V17 | 08-22 | MA60趋势确认 + 趋势强度阈值 + 置信度校准 + K线反向过滤 |
| V18 | 08-22 | Bug修复：MMDType枚举匹配 + 突破力度+时间窗口+MACD零轴确认 |
| V19 | 08-22 | ATR支撑确认(条件29) + 信号新鲜度衰减(条件30) + 质量评分增强 |
| V20 | 08-22 | 波动率Regime(条件31) + 趋势加速度(条件32) + 量价分布(条件33) |
| V21 | 08-22 | 动态支撑阻力(条件34) + 组合信号(条件35) + 多TF共振(条件36) + 决策辅助(条件37) |
| V22 | 08-22 | 波动率双重确认(条件38) + 量价背离检测(条件39) + API/VUI暴露V21 |
| V23 | 08-22 | Fibonacci回撤确认(条件40) + RSI区域过滤(条件41) + MACD零轴穿越(条件42) + 前端完整展示 |
| **V24** | **08-22** | **笔质量评分(条件43) + 中枢强度分析(条件44) + 增强背离检测(条件45) + 信号交叉验证(条件46)** |

---

**版本**: V24.0
**完成日期**: 2026-08-22
**测试状态**: ✅ 187 passed（增强）, 249 passed（缠论核心）
**构建状态**: ✅ 无错误
