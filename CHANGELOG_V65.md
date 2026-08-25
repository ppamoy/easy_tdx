# EasyTDX 项目更新日志 V65

## 更新时间
2026-08-28

## 背景：买卖点精准度再提升
V64 完成了回测验证框架与多股票对比分析，为条件效果量化提供了基础设施。本次 V65 聚焦三个精准度提升方向：
1. 量价背离二次确认（条件192）：在三类买卖点上增加量价背离的三层确认机制
2. 中枢突破回踩确认（条件193）：验证三类买卖点的突破有效性，过滤假突破
3. 波动率压缩突破（条件194）+ 信号新鲜度（条件195）：进一步筛选高质量信号

---

## 新增缠论条件（条件192-195）

### 条件192：量价背离二次确认增强（Volume-Price Divergence Secondary Confirmation）
**路径**: `src/easy_tdx/chanlun/mmd.py` → `_calc_volume_price_divergence_secondary_v65()`

三层确认机制：
- **第一层**：基础量价背离检测（价格创新低但成交量萎缩 / 价格上涨但成交量萎缩）
- **第二层**：背离强度量化（量比 + 价格斜率综合评分）
- **第三层**：背离持续时间（连续N根K线维持背离状态）

返回字段：`diverge_confirmed`, `divergence_strength`, `duration_bars`, `confidence_adjust`, `msg`

### 条件193：中枢突破回踩确认（Breakout Retest Confirmation）
**路径**: `src/easy_tdx/chanlun/mmd.py` → `_calc_breakout_retest_confirmation_v65()`

验证三类买卖点的中枢突破质量：
- 找到最近中枢，检查突破后回踩是否在中枢区间内
- 回踩幅度越小，信号质量越高
- 无回踩直接延续也视为有效突破
- 回撤超过阈值判定为假突破

返回字段：`retest_confirmed`, `retest_depth`, `breakout_valid`, `confidence_adjust`, `msg`

### 条件194：波动率压缩突破信号（Volatility Compression Breakout）
**路径**: `src/easy_tdx/chanlun/mmd.py` → `_calc_volatility_compression_breakout_v65()`

基于BOLL带宽压缩理论：
- 压缩阶段：带宽低于历史25%分位
- 突破确认：价格突破压缩区间中轨，伴随方向判断
- 质量评分：压缩时间越长、突破力度越大，评分越高

返回字段：`compression_detected`, `squeeze_score`, `breakout_strength`, `confidence_adjust`, `msg`

### 条件195：买卖点时间窗口新鲜度（Signal Time Window Freshness）
**路径**: `src/easy_tdx/chanlun/mmd.py` → `_calc_signal_time_window_freshness_v65()`

评估信号的时效性：
- 信号产生后到最新K线的天数（时间衰减）
- 信号后价格走势健康度（趋势是否延续、最大回撤）
- 超过60根K线的信号标记为过期

返回字段：`bars_since_signal`, `trend_health`, `freshness_score`, `confidence_adjust`, `msg`

---

## 回测验证框架扩展

### `src/easy_tdx/backtest/chanlun_validator.py`
- 新增 `ConditionGroup.V64`（回测验证框架本身，无具体条件编号）
- 新增 `ConditionGroup.V65`（条件192-195）
- 更新所有相关映射和描述

### `src/easy_tdx/web/routers/diagnosis.py`
- 单股诊断 API 新增 V65 四个字段返回
- 多股票对比 API 新增 V65 条件命中统计（v65_cond192-195）

---

## 前端更新

### `web-ui/src/types.ts`
- 新增 `volume_price_divergence_secondary_v65` 类型
- 新增 `breakout_retest_confirmation_v65` 类型
- 新增 `volatility_compression_breakout_v65` 类型
- 新增 `signal_time_window_freshness_v65` 类型

### `web-ui/src/views/DiagnosisView.vue`
- 新增 V65 四个条件卡片展示（单股诊断模式）
  - 📊 量价背离二次确认（条件192）
  - 🎯 中枢突破回踩确认（条件193）
  - 🔥 波动率压缩突破（条件194）
  - ⏰ 信号时间窗口新鲜度（条件195）
- 多股票对比表格新增 V65 条件命中列
- 条件命中详情卡片扩展支持 V65

---

## 测试结果

```
tests/unit/test_chanlun_v64_backtest.py:     37 passed（含10个V65测试）
tests/unit/test_chanlun_v63.py:              23 passed
tests/unit/test_web_api.py:                   4 passed
tests/unit/test_backtest_strategy.py:        29 passed
V63+V64+V65 合计: 93 passed（专项）
整体相关测试: 106 passed
ruff/mypy: 通过
```

---

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/mmd.py` | **新增** 条件192-195计算函数（+449行） |
| `src/easy_tdx/chanlun/types.py` | **新增** V65四个MMD字段（+6行） |
| `src/easy_tdx/backtest/chanlun_validator.py` | **扩展** ConditionGroup枚举V64/V65（+13/-12行） |
| `src/easy_tdx/web/routers/diagnosis.py` | **新增** V65字段返回（+17行） |
| `tests/unit/test_chanlun_v64_backtest.py` | **新增** V65测试类（+100行） |
| `web-ui/src/types.ts` | **新增** V65 TypeScript类型（+32行） |
| `web-ui/src/views/DiagnosisView.vue` | **新增** V65 UI展示（+104/-8行） |
| `pyproject.toml` | 版本更新至 1.57.0 |

---

## V64→V65 核心改进对比

| 维度 | V64 | V65 | 变化 |
|------|-----|-----|------|
| 条件总数 | 191 | 195 | +4 |
| 三类买卖点过滤 | 基础 | 量价背离+回踩确认+波动率压缩+新鲜度 | 大幅增强 |
| 回测分组 | V58-V63 | V58-V65 | +2组 |
| 专项测试 | 27 | 37 | +10 |
| 版本号 | 1.56.0 | 1.57.0 | +1 |

---

## 用户决策帮助改进

### V65新增能力：
1. **量价背离二次确认**：避免单一量价指标误判，三层确认提高三类买卖点准确率
2. **中枢突破回踩确认**：过滤假突破信号，减少三类买卖点的虚假入场
3. **波动率压缩突破**：识别横盘后的方向选择，提升趋势启动点的捕捉能力
4. **信号新鲜度评估**：自动过期老化信号，避免执行过时的买卖建议

---

**版本**: V65
**完成日期**: 2026-08-28
**测试状态**: ✅ 37 passed（V64+V65专项），106 passed（整体）
**构建状态**: ✅ web-ui 已构建并部署
