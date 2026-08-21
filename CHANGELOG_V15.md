# EasyTDX 项目更新日志 V15

## 更新时间
2026-08-22

## 本次更新内容

### 缠论买卖点模型 V15 增强

#### 核心改进

**1. K线形态确认（Candlestick Pattern Confirmation）**

新增 `_detect_kline_pattern()` 函数，检测回踩/反抽笔末端的K线形态。

| 形态 | 意义 | 置信度加成 |
|------|------|-----------|
| 锤子线（Hammer） | 下跌末端下影线长，看涨反转 | +3% |
| 阳吞没（Bullish Engulfing） | 后阳包前阴，强势看涨 | +3% |
| 十字星（Doji） | 开盘≈收盘，犹豫信号 | 不加成 |
| 阴吞没（Bearish Engulfing） | 后阴包前阳，看跌 | 3卖时使用 |

**2. 信号衰减检测（Signal Aging Detection）**

新增 `_calc_signal_aging()` 函数，检测信号产生后是否已过久未触发交易。

| 信号年龄 | 衰减系数 |
|---------|---------|
| ≤5根K线 | 1.0（无衰减） |
| 5-9根K线 | 0.9（轻微衰减） |
| 9-15根K线 | 0.8（中度衰减） |
| >15根K线 | 0.5（严重衰减，信号可能已失效） |

**3. 二次回踩确认（Break-Retest-Break Pattern）**

新增 `_check_break_retest_break()` 函数，检测突破-回踩-再突破模式。

- 突破中枢 → 回踩不破zg → 再次向上突破 = 更强的3买信号
- 回踩深度<50% = 多头强势，额外+2%置信度
- 该模式在消息中显示"二次确认(回踩XX%)"

**4. 动态时间窗口（Dynamic Time Window）**

新增 `_get_dynamic_time_window()` 函数，根据波动率动态调整突破后等待天数。

| 波动率 | 时间窗口调整 |
|--------|------------|
| >3%（高波动） | +3根K线 |
| <1%（低波动） | -2根K线 |
| 1%-3%（正常） | 不变 |

#### 信号质量报告增强（V15）

`calc_signal_quality_report()` 新增字段：

| 字段 | 说明 |
|------|------|
| `signal_aging` | 信号衰减信息 `{aged, age_bars, decay_factor}` |
| `kline_pattern` | K线形态名称（hammer/bullish_engulfing等） |

前端显示：
- K线形态以绿色tag展示（锤子线✅/阳吞没✅）
- 信号时效显示新鲜/已衰减状态

### 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/mmd.py` | 新增4个V15函数；3买/3卖增加K线形态+二次回踩条件；置信度计算增加信号衰减+K线形态+二次回踩加成；信号报告新增V15字段 |
| `web-ui/src/types.ts` | `DiagnosisSignalReport` 新增 `signal_aging`、`kline_pattern`；`DiagnosisChanlunMmd` 新增 `kline_pattern` |
| `web-ui/src/views/DiagnosisView.vue` | 新增K线形态显示、信号时效显示 |
| `tests/unit/test_chanlun_enhancements.py` | 新增 `TestV15Enhancements` 类（10个测试用例） |
| `CHANGELOG_V15.md` | 本次更新日志 |

---

## 过滤条件完整列表（V15）

### 3买过滤条件（22项）

| 条件 | 说明 |
|------|------|
| 1-10 | 基础缠论结构条件 |
| 11 | MA斜率确认 |
| 12 | BOLL位置过滤 |
| 13 | ADX趋势强度过滤 |
| 14 | RSI动量确认 |
| 15 | KDJ动量确认 |
| 16 | 成交量异常检测 |
| 17 | 缺口分析 |
| 18 | MACD柱状图斜率确认 |
| 19 | 假突破过滤 |
| **20** | **V15新增 K线形态确认（锤子线/阳吞没增强）** |
| **21** | **V15新增 二次回踩确认（break-retest-break）** |
| **22** | **V15新增 动态时间窗口（基于波动率）** |

### 3卖过滤条件（22项）

与3买对称，方向相反。

---

## 预期效果

| 指标 | V14 | V15（预期） |
|------|-----|------------|
| 1买准确率 | 90%+ | 90%+（保持不变） |
| 2买准确率 | 80%+ | 80%+（保持不变） |
| 3买准确率 | 72%+ | **75%+**（K线形态+二次回踩过滤假突破） |
| 1卖准确率 | 93%+ | 93%+（保持不变） |
| 2卖准确率 | 75%+ | 75%+（保持不变） |
| 3卖准确率 | 68%+ | **70%+** |

---

## 测试状态

```
=========================== 1090 passed, 2 skipped in 100.23s ============================
- test_chanlun_enhancements.py: 71 passed（含10个V15新增测试）
- test_chanlun.py: 33 passed
- test_diagnosis_router.py: 4 passed
- test_chanlun_phase2.py: 12 passed
- test_chanlun_phase3.py: 10 passed
- 其他单元测试: 960 passed
```

---

**版本**: V15.0  
**完成日期**: 2026-08-22  
**测试状态**: ✅ 1090 passed  
**构建状态**: ✅ 无错误
