# EasyTDX 项目更新日志 V18

## 更新时间
2026-08-22

## 本次更新内容

### Bug修复：MMDType 枚举值匹配错误（影响 V8-V18 所有版本）

#### 问题描述

`MMDType` 枚举值为 `"1buy"`, `"2buy"`, `"3buy"`, `"1sell"`, `"2sell"`, `"3sell"`。
但代码中多处使用 `startswith("buy")` / `startswith("sell")` 判断买卖类型，
导致所有带数字前缀的类型（`"3buy"`, `"2buy"` 等）**永远匹配不上**。

V16 changelog 声称修复了此问题（仅修复了 line 392 的 `is_buy` 变量），
但遗漏了 `_calc_confidence`、`_calc_confluence_bonus` 和 `diagnosis.py` 中的其他 9 处。

#### 影响范围

| 位置 | 影响 |
|------|------|
| `_calc_confidence` V8 MACD 位置确认 | 3买/3卖/2买/2卖的 MACD 加成全部失效，错误进入卖出分支 |
| `_calc_confidence` V8 趋势方向加成 | 所有买点的上升趋势加成失效 |
| `_calc_confidence` V14 成交量异常加成 | 3买/3卖的成交量放大加成失效 |
| `_calc_confluence_bonus` MACD 零轴确认 | 跨级别 MACD 确认加成失效 |
| `_calc_confluence_bonus` 波动率加成 | 低波动市场买点加成失效 |
| `diagnosis.py` 多信号共振 | 3买确认加成失效 |
| `diagnosis.py` 诊断评分 MACD | MACD 评分逻辑对所有类型失效 |

#### 修复内容

将所有 `mmd.mmd_type.value.startswith("buy")` 替换为 `"buy" in mmd.mmd_type.value`，
将 `mmd.mmd_type.value.startswith("sell")` 替换为 `"sell" in mmd.mmd_type.value`。

共修复 **9 处**（`mmd.py` 7 处 + `diagnosis.py` 2 处）。

### V18 缠论增强功能（原计划，现已可正常生效）

**1. 突破力度确认（条件26）**
- 3买突破笔力度需大于进入中枢的笔（避免弱势突破）
- 3卖跌破笔力度需大于进入中枢的笔

**2. 回踩时间窗口限制（条件27）**
- 回踩/反抽笔不超过 25 根 K 线（防止信号过度衰减）

**3. MACD 零轴确认（条件28）**
- 3买时 MACD DIF 应在零轴上方（趋势多头确认）
- 3卖时 MACD DIF 应在零轴下方（趋势空头确认）

**4. 基础置信度上调**
- 3买：0.60 → 0.62（过滤增强后预期准确率 ~65%）
- 3卖：0.55 → 0.57（过滤增强后预期准确率 ~60%）

### 测试结果

```
1116 passed, 1 skipped, 1 warning in 57.20s
- chanlun 核心测试: 152 passed
- V18 新增测试: 9 passed（含 1 个 bugfix 验证用例）
- 诊断路由测试: 全部通过
```

---

## 文件变更

| 文件 | 修改内容 |
|------|----------|
| `src/easy_tdx/chanlun/mmd.py` | 修复 7 处 `startswith("buy"/"sell")` → `"buy"/"sell" in mmd_type.value` |
| `src/easy_tdx/web/routers/diagnosis.py` | 修复 2 处 `startswith("buy"/"sell")` → `"buy"/"sell" in mmd_type.value` |
| `pyproject.toml` | 版本 1.20.8 → 1.20.9 |
| `CHANGELOG_V18.md` | 本次更新日志 |

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
| V17 | 08-22 | MA60趋势确认 + 趋势强度阈值 + 置信度校准 + K线反向过滤 + 成交量增强 |
| **V18** | **08-22** | **Bug修复：MMDType枚举值匹配 + 突破力度+时间窗口+MACD零轴确认** |

---

**版本**: V18.0
**完成日期**: 2026-08-22
**测试状态**: ✅ 1116 passed, 1 skipped
**构建状态**: ✅ 无错误
