# 缠论买卖点模型精修总结报告

## 项目概述

基于吴伟志《长赢：穿越股市的牛熊周期》理论和历史回测结果，对 easy_tdx 项目的缠论买卖点模型进行全面精修。

## 回测结果（V1版本）

使用10只A股龙头股票，测试最近500个交易日数据：

| 买卖点类型 | 样本数 | 准确率 | 评价 |
|------------|--------|--------|------|
| **1买** | 10 | **80%** | ⭐⭐⭐ 优秀 |
| **2买** | 10 | **70%** | ⭐⭐ 良好 |
| **3买** | 89 | **57%** | ⭐ 一般 |
| **1卖** | 10 | **90%** | ⭐⭐⭐ 优秀 |
| **2卖** | 3 | **67%** | ⭐⭐ 良好 |
| **3卖** | 92 | **50%** | ⭐ 一般 |
| **合计** | 214 | **57.5%** | - |

## 发现的问题

### 1. 三类买卖点准确率偏低
- 3买准确率仅57%，3卖仅50%，接近随机水平
- 主要原因：过滤条件不足，产生大量假信号

### 2. 二类买卖点确认不够严格
- 仅检查低点不创新低，缺乏幅度限制
- 可能导致假突破信号

### 3. 可视化显示不够清晰
- 买卖点类型和强度没有明显区分
- 背驰信息没有完整展示

## 精修改进（V2版本）

### 1. 一类买卖点（保持核心逻辑）

**改进点：**
- 增加背驰强度标签：strong/moderate/weak
- 使用MACD面积作为力度指标（更准确）
- 动态调整阈值（根据趋势强度）

```python
# 背驰强度判断
if ratio < 0.5: strength = "strong"    # 强背驰，高置信度
elif ratio < 0.7: strength = "moderate"  # 中等背驰
else: strength = "weak"              # 弱背驰，需谨慎
```

### 2. 二类买卖点（增加确认条件）

**改进后逻辑：**
```python
# 2买确认条件：
1. 低点不创新低：bi.low > buy_1_low
2. 回调幅度不超过原下跌的70%
3. 回调时间短（不超过10根K线）
```

### 3. 三类买卖点（严格过滤）

**新增4个过滤条件：**
```python
# 条件1：回踩不破zg（已满足）
if bi.low <= zs.zg:
    break

# 条件2：回调时间不超过10根K线
if time_span > 10:
    continue

# 条件3：回调幅度不超过突破幅度的60%
if break_bi_up.low - bi.low > breakout_range * 0.6:
    continue

# 条件4：中枢内部有背驰时，突破笔力度要足够
if force_ratio_in_zs > 0.9 and break_force < first_bi_force * 0.7:
    continue
```

### 4. 去重机制

**问题：** 同一位置可能出现多个买卖点信号  
**解决：** 按优先级保留最高级别信号
```python
priority = {
    BUY_1: 6, BUY_2: 5, BUY_3: 4,
    SELL_1: 3, SELL_2: 2, SELL_3: 1
}
```

### 5. 可视化改进

**颜色方案：**
- 1买：绿色三角形 (size=18)
- 2买：浅绿色圆形 (size=14)
- 3买：淡绿色小圆 (size=10)
- 1卖：红色圆针 (size=18)
- 2卖：浅红色圆形 (size=14)
- 3卖：淡红色小圆 (size=10)

**新增显示：**
- 背驰强度标签
- 买卖点类型标签
- 中枢重叠区域高亮

## 修改文件清单

| 文件 | 修改内容 | 大小 |
|------|----------|------|
| `src/easy_tdx/chanlun/mmd.py` | 精修买卖点识别逻辑 | 18KB |
| `src/easy_tdx/chanlun/beichi.py` | 优化背驰判断 | 6KB |
| `src/easy_tdx/chanlun/analyser.py` | 传递收盘价用于计算 | 10KB |
| `web-ui/src/components/ChanlunChart.vue` | 改进可视化显示 | 14KB |
| `web-ui/src/views/ChanlunView.vue` | 支持新数据结构 | 11KB |
| `web-ui/src/views/BacktestView.vue` | 缠论策略支持 | 18KB |

## 测试验证

```bash
# 缠论核心测试
$ python3 -m pytest tests/unit/test_chanlun*.py -v
============================== 55 passed in 0.89s ==============================

# 完整单元测试
$ python3 -m pytest tests/unit/ -q
======================== 995 passed, 1 skipped in 43.62s ========================
```

## 使用方法

### CLI命令
```bash
# 分析单只股票
easy-tdx chanlun SZ 000001 --table

# 多级别分析
easy-tdx chanlun SZ 000001 --multi-level 30MIN --table
```

### Python API
```python
from easy_tdx.chanlun import ChanlunAnalyser

analyser = ChanlunAnalyser(code="SZ000001", frequency="DAILY")
result = analyser.process_klines(df)

# 获取买卖点
for mmd in result.mmds:
    print(f"{mmd.mmd_type.value}: {mmd.msg}")

# 获取背驰
for bc in result.bcs:
    print(f"{bc.bc_type.value}: {bc.msg}")
```

### Web API
```bash
# 缠论分析接口
POST /api/v1/chanlun/analyze
{
  "market": "SZ",
  "code": "000001",
  "category": "DAY",
  "count": 800
}
```

## 预期效果

| 指标 | V1版本 | V2版本（预期） | 提升 |
|------|--------|----------------|------|
| 1买准确率 | 80% | 85%+ | +5% |
| 1卖准确率 | 90% | 90%+ | 持平 |
| 3买准确率 | 57% | 65%+ | +8% |
| 3卖准确率 | 50% | 60%+ | +10% |
| 总准确率 | 57.5% | 65%+ | +7.5% |

## 缠论理论遵循

### 一类买卖点（背驰点）
- **定义**：趋势末端、最后一个中枢外侧、背驰确认
- **严格标准**：力度比率 < 0.8
- **适用场景**：趋势反转交易

### 二类买卖点（确认点）
- **定义**：1买/1卖后的第一次回调/反弹
- **确认条件**：不创新低/高 + 幅度限制
- **适用场景**：顺势加仓

### 三类买卖点（突破点）
- **定义**：突破中枢后回踩不破zg/zd
- **严格过滤**：时间、幅度、力度三重验证
- **适用场景**：突破交易

## 后续优化方向

1. **多时间框架分析**：结合日线+30分钟线交叉验证
2. **机器学习增强**：使用历史数据训练分类器
3. **实时预警系统**：监控买卖点信号出现
4. **回测引擎集成**：自动执行买卖点策略

## 相关文档

- `CHANLUN_BACKTEST_REPORT.md` - 详细回测报告
- `CHANLUN_V2_IMPROVEMENTS.md` - V2版本改进说明
- `CHANLUN_IMPROVEMENTS.md` - 缠论功能说明

---

**版本**: V2.0  
**更新日期**: 2026-08-17  
**测试状态**: ✅ 全部通过 (995 passed, 1 skipped)
