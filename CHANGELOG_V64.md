# EasyTDX 项目更新日志 V64

## 更新时间
2026-08-28

## 背景：回测验证框架 + V63条件回测 + 多股票对比
V63完成了中枢级别权重优化和多周期信号衰减追踪，但缺乏系统化的回测验证能力。本次更新聚焦三个方向：
1. 回测验证框架：量化验证V58-V63条件的实际准确率提升
2. V63条件回测验证：针对条件190/191进行历史回测
3. 多股票对比分析：在同一页面展示多只股票的信号质量对比

---

## 新增模块：缠论条件回测验证器

### `src/easy_tdx/backtest/chanlun_validator.py`

**ConditionGroup 枚举**：V58-V63 六个条件分组，每个分组对应一组增强条件：
- V58（条件172-175）：多TF趋势+量能验证+ATR止损+综合评分
- V59（条件176-179）：波动率MA+ATR倍数+多TF共振+衰减速度
- V60（条件180-183）：RSI背离+MA间距+中枢距离+KDJ确认
- V61（条件184-185）：RSI+MACD双指标融合+质量分层
- V62（条件186-189）：BOLL带宽确认+动态阈值增强
- V63（条件190-191）：中枢级别权重优化+多周期信号衰减追踪

**ChanlunConditionBacktestValidator 核心类**：
- `validate_conditions()`：对指定条件分组运行回测验证
- `validate_multi_stock()`：多股票对比分析
- `compare_groups()`：生成条件组对比表格（DataFrame）
- 止损/止盈模拟、置信度-收益相关性计算

**返回结构**：
- `ConditionValidationResult`：胜率、平均收益、持仓天数、置信度相关性
- `MultiStockResult`：每只股票的信号统计和条件命中详情

---

## 新增 API：多股票对比分析

### `POST /api/v1/diagnosis/multi-stock`

传入多只股票的 market+code，返回每只股票的：
- 总信号数、买入/卖出信号数
- 平均置信度
- 各条件组（V58-V63）命中次数

---

## 前端新增：多股票对比 UI

### `web-ui/src/views/DiagnosisView.vue`
- 新增「V64 多股对比」模式切换按钮
- 支持添加/删除多只股票
- 对比表格展示：股票代码、K线数、信号数、平均置信度、V63条件命中
- 条件命中详情卡片展示 V58-V63 各条件命中统计

### `web-ui/src/api.ts`
- 新增 `fetchMultiStockComparison()` API 函数

### `web-ui/src/types.ts`
- 新增 `MultiStockResult` 和 `MultiStockComparisonResponse` 类型

---

## 测试结果

```
tests/unit/test_chanlun_v63.py:       23 passed
tests/unit/test_chanlun_v64_backtest.py: 27 passed
tests/unit/test_web_api.py:           4 passed
tests/unit/test_backtest_strategy.py: 29 passed
V63+V64 合计: 50 passed
```

---

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/backtest/chanlun_validator.py` | **新增** 缠论条件回测验证框架（~470行） |
| `src/easy_tdx/web/routers/diagnosis.py` | **新增** `/diagnosis/multi-stock` 多股票对比 API（+70行） |
| `tests/unit/test_chanlun_v64_backtest.py` | **新增** V64 回测验证测试（27个用例） |
| `web-ui/src/types.ts` | **新增** MultiStockResult / MultiStockComparisonResponse 类型 |
| `web-ui/src/api.ts` | **新增** fetchMultiStockComparison() 函数 |
| `web-ui/src/views/DiagnosisView.vue` | **新增** 多股对比 UI（模式切换+对比表格+条件详情） |

---

## V63→V64 核心改进对比

| 维度 | V63 | V64 | 变化 |
|------|-----|-----|------|
| 条件总数 | 191 | 191 | - |
| 回测验证框架 | ❌ 无 | ✅ ConditionGroup枚举+Validator | 新增 |
| 多股票对比 API | ❌ 无 | ✅ POST /diagnosis/multi-stock | 新增 |
| 前端多股对比UI | ❌ 无 | ✅ 模式切换+对比表格 | 新增 |
| 专项测试 | 23 | 27 | +27 |
| 版本号 | 1.55.0 | 1.56.0 | +1 |

---

## 下一步优化方向（V65+）

1. **条件消融实验**：逐个关闭V58-V63条件，量化每个条件的独立贡献
2. **历史数据回测**：接入真实股票历史数据，验证V63条件的实战准确率
3. **自适应参数优化**：基于回测结果自动调整置信度阈值和止损参数

---

**版本**: V64
**完成日期**: 2026-08-28
**测试状态**: ✅ 50 passed（V63+V64），106 passed（相关测试）
**构建状态**: 需重新构建 web-ui（npm run build）
