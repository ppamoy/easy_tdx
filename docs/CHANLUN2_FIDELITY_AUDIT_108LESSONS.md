# chanlun2 原文保真审计（108课）

> 严格按108课原文从头实现的缠论模型2。与现有 `easy_tdx.chanlun` 并存，不污染。
> 本文档记录 chanlun2 相对原文的实现对照，以及它修复了现有模型的哪些架构缺口。

## 一、核心递归定义对照

| 原文课次 | 原文定义 | chanlun2 实现 | 现有chanlun缺口 |
|---|---|---|---|
| 第17课 | 中枢=至少3个连续**次级别走势类型**重叠 | `zs.find_zs_from_moves`：3个次级别走势(Move)重叠 | **偏差12**：用「笔」构中枢，违背第91课「笔不能构中枢」 |
| 第17课 | 最低级别中枢=至少3个该级别K线重叠 | `zs.find_zs_lowest_level`：3根合并K线价格重叠 | 现有无独立最低级别中枢（混用笔） |
| 第17课 | 走势=趋势+盘整；趋势=≥2同向中枢 | `trend.TrendKind`：TREND_UP/DOWN/PANZHENG/INCOMPLETE | — |
| 第17课 | 「向上+向下+向上」必然产生中枢 | `zs` 三段重叠即构中枢 | — |
| 第20课 | ZG=min(g1,g2), ZD=max(d1,d2) | `ZS.zg/zd` 严格按前两段重叠 | — |
| 第20课 | GG/G/D/DD 四指标 | `ZS.gg/g/d/dd` | — |
| 第20课 | 中枢延伸=任意[dn,gn]与[ZD,ZG]重叠 | `ZS.overlaps_interval` + 中心定理一 | — |
| 第20课 | 趋势前后中枢不重叠 | `find_zs_from_moves` 扫描到不重叠才新中枢 | — |

## 二、背驰对照（第24课）

| 原文定义 | chanlun2 实现 | 现有chanlun缺口 |
|---|---|---|
| C段MACD柱子面积<A段面积 | `divergence._macd_area_for_moves`（面积非峰值） | **偏差**：用峰值而非面积 |
| B中枢把黄白线回拉0轴附近 | `Divergence.dif_returned_to_zero` | **偏差**：完全缺失0轴检查 |
| A/B/C三段，B是另一中枢 | `detect_divergence` 严格A/B/C结构 | — |
| 趋势背驰≠盘整背驰 | `DivergenceKind.TREND/PANZHENG` 两类型 | **偏差5/SM-5**：盘整背驰混标1买 |

## 三、三类买卖点对照

| 原文课次 | 原文定义 | chanlun2 实现 | 现有chanlun缺口 |
|---|---|---|---|
| 第27课 | 1买=趋势背驰构成 | `MMDType.BUY_1` 仅趋势背驰 | SM-5：盘整背驰混标1买 |
| 第53课 | 盘整背驰≠第一类买卖点 | `MMDType.PANZHENG_BUY/SELL` 单独标 | 偏差5：不区分 |
| 第101课 | 2买=1买次级别回抽后再次探底，无根数限制 | `find_second_class_mmd` 无K线根数硬编码 | **偏差13**：硬编码30根 |
| 第20课 | 3买卖=第一次回试不破ZG | `find_third_class_mmd` 取after[0]（第一次） | **SM-3**：非第一次，按中枢数截断 |
| 第61课 | 至少5段次级别 | `find_third_class_mmd` 校验len≥5 | SM-3：无5段校验 |

## 四、走势分解对照（第38课）

| 原文定义 | chanlun2 实现 | 现有chanlun缺口 |
|---|---|---|
| 三段构中枢（固定） | `decompose_same_level` 取连续3段 | **SL-2**：config.zs_min_lines 可变3~5 |
| 延伸出6段才拆两个盘整 | `extend_count>=3` 时拆分 | — |
| 走势类型=趋势/盘整，无none | `TrendKind` 无none类别 | **SL-4**：自创`kind="none"` |
| 同级别分解 | `decompose_same_level` | — |

## 五、K线与笔对照

| 原文课次 | 定义 | chanlun2 实现 |
|---|---|---|
| 第65课 | 包含关系合并（向上高高取高低低取高） | `kline_merge.merge_klines` |
| 第67课 | 顶底分型（第二根高低点极值） | `fractal.find_fractals` |
| 第62课 | 笔=相邻顶底+中间至少1根K线 | `move.find_moves`（k_index差≥2） |

## 六、区间套对照（第83课）

| 原文定义 | chanlun2 实现 | 现有chanlun缺口 |
|---|---|---|
| 大级别买卖点=次级别买卖点逐级收敛 | `level_synth.refine_with_lower_level` | 现有level_synth用合成数据（自述非真实） |
| 跨周期真实数据 | 只接受真实多周期K线 | 现有qujiantao同序列递归伪低级别（偏差，已修synthetic标记） |
| 防未来函数 | 次级别结束不晚于大级别信号 | — |

## 七、真链路验证（§5）

### 600519日线（真TDX数据，8001端口）
- 2296合并K线 → 589笔 → 435最低中枢(K线重叠,非笔构) → 170走势段 → 70买卖点
- 买卖点分布：buy1(趋势背驰)/buy2(无根数)/sell1/sell2

### 区间套跨周期（cross_timeframe=True）
- nested 70, confirmed 5
- 日线sell1 2025-09-02 → 30分sell1 2025-07-30（L2收敛，防未来函数：次级别日期早于大级别）

## 八、模块结构

```
src/easy_tdx/chanlun2/
├── __init__.py        # 包说明
├── types.py           # 类型系统（KLine/MergedK/Fractal/Move/ZS/Trend/MMD/Divergence）
├── kline_merge.py     # K线包含合并（第65课）
├── fractal.py         # 顶底分型（第67课）
├── move.py            # 笔/走势段（第62课）
├── zs.py              # 中枢递归（第17/20课）
├── trend.py           # 同级别分解（第17/38课）
├── divergence.py      # 背驰（第24课MACD面积+0轴）
├── mmd.py             # 三类买卖点（第20/27/101/61课）
├── level_synth.py     # 区间套跨周期（第83课）
└── analyser.py        # 主入口编排
```

API: `/api/v1/chanlun2/analyze`（复用现有取数层，返回完整分析结果+区间套）

## 九、测试

- `tests/unit/test_chanlun2.py`：13单元测试，每个钉住一条原文定义
- `tests/unit/test_chanlun2_router.py`：2行为级测试（真fixture数据跑端点）
- 全部通过，无回归（现有chanlun测试不受影响）
