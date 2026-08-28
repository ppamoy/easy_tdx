# 更新日志 V82

## [V82] — 2026-08-28

**缠论模型精准度再提升 - 条件260-263集成（时间衰减+回踩确认+MACD共振+波动率压缩）**

### 新增

- **`_calc_mmd_age_decay_v82`**（`src/easy_tdx/chanlun/mmd.py`）—— 买卖点时间衰减验证（条件260）。计算买卖点信号生成以来的K线数量，评估信号新鲜度。新鲜信号（<60根）加分，陈旧信号（>300根）减分。返回 `age_bars`, `age_label`, `confidence_adjust`, `msg`。

- **`_calc_breakout_retest_confirm_v82`**（`src/easy_tdx/chanlun/mmd.py`）—— 中枢突破回踩确认（条件261）。检测买卖点是否经过中枢突破后的回踩确认：突破后价格回踩突破位再展开→强确认加分，直接突破无回踩→弱确认。返回 `retest_detected`, `retest_quality`, `confidence_adjust`, `msg`。

- **`_calc_macd_multi_tf_resonance_v82`**（`src/easy_tdx/chanlun/mmd.py`）—— 多级别MACD共振验证（条件262）。分析MACD柱状图的多周期特征：短期加速度+中期趋势方向是否一致。多头共振加分，空头共振减分，冲突中性。返回 `short_acceleration`, `mid_trend`, `resonance`, `confidence_adjust`, `msg`。

- **`_calc_volatility_compression_breakout_v82`**（`src/easy_tdx/chanlun/mmd.py`）—— 波动率压缩突破确认（条件263）。基于BOLL带宽评估波动率压缩状态和突破力度。极端压缩后突破→强信号加分，高压缩但突破弱→减分。返回 `compression_level`, `breakout_strength`, `volume_confirm`, `confidence_adjust`, `msg`。

### 后端集成

- **MMD 类新增4个V82字段**（`src/easy_tdx/chanlun/types.py`）：`_mmd_age_decay_v82`, `_breakout_retest_confirm_v82`, `_macd_multi_tf_resonance_v82`, `_volatility_compression_breakout_v82`
- **ConditionGroup 新增 V82**（`src/easy_tdx/backtest/chanlun_validator.py`）：条件范围(260, 263)，描述"时间衰减+回踩确认+MACD共振+波动率压缩"
- **诊断API增强**（`src/easy_tdx/web/routers/diagnosis.py`）：新增V82四维度量摘要 + 4个V82条件字段到 chanlun 响应
- **缠论分析API增强**（`src/easy_tdx/web/routers/chanlun.py`）：MMD摘要新增V82字段 + v82_summary 顶层摘要

### 前端集成

- **`web-ui/src/types.ts`**：`DiagnosisChanlun` 新增4个V82可选字段；`DiagnosisResult` 新增 `v82_summary` 接口；`ChanlunMmd` 新增V81/V82类型定义
- **`web-ui/src/views/DiagnosisView.vue`**：
  - 新增 `v82QualityLabel` 函数
  - 新增 V82 四维度量摘要卡片（Hero区域）
  - 新增4个V82条件卡片（时间衰减/回踩确认/MACD共振/波动率压缩）
  - 新增 V82 CSS 样式（v82-summary-row, v82-tag, v82-mad, v82-brc, v82-mtr, v82-vcb）
- **`web-ui/src/views/ChanlunView.vue`**：MMD表格数据映射新增V81/V82字段；移除未使用的标签辅助函数（TS6133修复）

### 测试

- **`tests/unit/test_chanlun_v82.py`**（20 个测试用例）：
  - `TestV82ConditionGroup`：枚举存在性、条件范围(260-263)、描述文案
  - `TestV82MMDFields`：MMD对象包含4个V82字段
  - `TestV82BacktestValidator`：单组/多组合验证、summary输出
  - `TestV82Functions`：时间衰减（买入新鲜/卖出陈旧/数据不足）、回踩确认（有回踩/数据不足）、MACD共振（多头共振/数据不足）、波动率压缩（极端压缩/数据不足）、综合冒烟、V81兼容性

---

## 核心功能清单（更新后）

### 缠论买卖点增强（V58-V82，共 92 个增强条件）
| 版本 | 条件范围 | 核心能力 |
|------|----------|----------|
| V81 | 256-259 | 波动率状态转换+支撑阻力强度+量价能量分布+执行窗口评估 |
| **V82** | **260-263** | **时间衰减验证+回踩确认+MACD共振+波动率压缩突破** |

### 诊断系统
| 功能 | 状态 |
|------|------|
| V77-V82 四维度量摘要（Hero区域） | ✅ |
| V77-V82 缠论条件卡片（共 60 张） | ✅ |
