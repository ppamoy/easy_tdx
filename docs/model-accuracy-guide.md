# 模型准确度验证指南（V95–V107）

> 本文档汇总 easy-tdx 自 V95 起新增的「通过历史回测验证模型/策略准确度」能力。
> 目标：让用户不只是看账户盈亏，而是能回答三件事——**信号准不准、稳健不稳健、过不过拟合**。

## 一、验证能力全景

| 版本 | 能力 | 回答的问题 | 入口 |
| --- | --- | --- | --- |
| V95 | 信号前瞻命中率 + 随机入场基准 + 买入持有基准 | 买卖点择时是否真的准 | 回测页「模型准确度验证」 |
| V96 | 缠论买卖点按类型（1买/2买/3买…）命中率 | 哪类缠论信号真的准 | 缠论分析页 / 回测页缠论策略 |
| V97 | 分段稳健性 / 过拟合检查 | 成绩是否只在一段行情里成立 | 回测页「分段稳健性检查」 |
| V98 | 选股结果前瞻收益验证 | 选股模型选的股票是否跑赢未选的 | 动态选股页「验证选股效果」 |
| V99 | 组合/多标的准确度聚合 | 策略放在多只股票上是否整体靠谱 | 组合回测页 |
| V101 | 模型可信度综合评分（0-100） | 散落验证信号汇总成一个可读分数 | 回测页「模型可信度」 |
| V103 | 组合可信度评分 | 组合整体可信度 | 组合回测页 |
| V105 | 样本外验证（训练段 + 未见过数据） | 模型在没见过的数据上是否仍准确 | 回测页「样本外验证」 |
| V106 | 回测页「验证总结」聚合卡片 | 全部验证结论一览可判 | 回测报告顶部 |
| V107 | 信号监控页自选股历史信号准确度 | 盯实时信号前先看该股历史命中率 | 信号监控页「🎯 准确度」 |

## 二、核心概念

- **命中（hit）**：买入后 N 根收益 > 0（择时进场正确）；卖出后 N 根下跌（回避下跌正确）。
- **随机入场基准**：以相同信号数量在全部可入场 bar 上随机采样（可复现 seed，数据不足时直接用全量），作为「抛硬币择时」的下限参照。
- **超额命中率** = 模型命中率 − 随机命中率。>0 说明信号比随机择时更准。
- **模型可信度（V101 权重）**：40% 择时准确度 + 35% 稳健性 + 25% 绩效对比，融合成 0-100 分。
- **样本外验证（V105）**：把区间按时间切训练段（默认 70%）+ 样本外持有段（30%），策略参数固定，在模型从未见过的数据上重跑——检验过拟合最硬的一关。

## 三、如何启用

### 3.1 回测页（最常用）

1. 选择标的与策略，点击「开始回测」。
2. 在「资金与成本」区勾选：
   - **分段稳健性检查**：把区间切成 2~6 段逐段重跑，看各段表现是否一致。
   - **样本外验证**：训练段 + 未见过持有段对比。
3. 报告区依次展示：✅ 验证总结（V106）→ 📊 模型可信度（V101）→ 🎯 模型准确度验证（V95）→ 🧱 分段稳健性（V97）→ 🔬 样本外验证（V105）。
4. 想留存/分享？点工具栏「📋 复制报告」导出 Markdown 摘要（V104）。

### 3.2 缠论分析页

- 分析完成后，「买卖点准确度验证」面板（V96）展示每类买卖点（1buy/2buy/3buy/各 sell）的 5 根命中率与随机基准对比。

### 3.3 动态选股页

- 扫描出符合条件的股票后，点「📈 验证选股效果」（V98）回看选股日后 5/10/20/60 日收益，对比选中组 vs 未选中池。

### 3.4 组合回测页

- 报告展示「组合准确度验证」（V99）与「组合可信度」横幅（V103）。

### 3.5 信号监控页

- 「快速加入的信号」每项有「🎯 准确度」按钮（V107），点击查看该股最近 300 根日线的历史信号命中率。

### 3.6 策略库与对比页

- 保存策略时（V100）自动把准确度/稳健性结论写入快照，策略库卡片直接展示。
- 结果对比页（V102）横向展示多个 task 的 📊 可信度 / 🎯 5根命中率 / 🎯 超额命中率。

## 四、如何解读

- **命中率高于随机基准（超额 > 0）**：择时有正贡献，值得参考。
- **命中率与随机相当**：择时贡献有限，收益可能来自行情本身。
- **分段稳健性显示过拟合 / 样本外衰减**：历史成绩可能不可持续，需谨慎对待。
- **模型可信度 70+ 高 / 50~69 中 / <50 低**：综合信号准确度、稳健性、绩效对比的加权结论。

## 五、代码接口

```python
from easy_tdx.backtest.signal_accuracy import compute_signal_accuracy, compute_signal_accuracy_by_type
from easy_tdx.backtest.model_trust import compute_model_trust, compute_portfolio_trust
from easy_tdx.backtest.robustness import compute_segment_robustness
from easy_tdx.backtest.screening_verify import compute_screening_verify
from easy_tdx.backtest.out_of_sample import compute_out_of_sample

from easy_tdx.backtest import BacktestEngine

engine = BacktestEngine(MyStrategy, cash=1_000_000)
result = engine.run(df)

# 信号前瞻命中率 vs 随机基准（V95）
acc = result.signal_accuracy

# 分段稳健性（V97）
rob = compute_segment_robustness(df, lambda: MyStrategy())

# 模型可信度（V101）
trust = compute_model_trust(result.performance, acc, rob)

# 样本外验证（V105）
oos = compute_out_of_sample(df, lambda: MyStrategy())
```

## 六、测试

对应单元测试：`tests/unit/test_backtest_signal_accuracy.py`、`test_backtest_model_trust.py`、
`test_backtest_robustness.py`、`test_backtest_screening_verify.py`、`test_backtest_portfolio_accuracy.py`、
`test_backtest_portfolio_trust.py`、`test_backtest_out_of_sample.py`。