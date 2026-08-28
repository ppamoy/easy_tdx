# 更新日志 V81

## [V81] — 2026-08-28

**缠论模型精准度再提升 - 条件256-259集成（波动率状态转换+支撑阻力强度+量价能量分布+执行窗口）**

### 新增

- **`_calc_volatility_regime_transition_v81`**（`src/easy_tdx/chanlun/mmd.py`）—— 波动率状态转换检测（条件256）。基于ATR序列评估当前波动率 regime（compressed/normal/elevated/expanding）及转换方向，检测波动率压缩突破和前兆。返回 `regime`, `transition_type`, `atr_ratio`, `atr_change_pct`, `confidence_adjust`, `msg`。

- **`_calc_support_resistance_strength_v81`**（`src/easy_tdx/chanlun/mmd.py`）—— 关键支撑阻力强度验证（条件257）。扫描近期K线识别支撑/阻力位（局部极值点），评估买卖点与最近SR位的距离和测试次数。返回 `strength_level`, `nearest_sr_dist_pct`, `sr_count`, `confidence_adjust`, `msg`。

- **`_calc_volume_price_energy_distribution_v81`**（`src/easy_tdx/chanlun/mmd.py`）—— 量价能量分布验证（条件258）。将成交量分布分为高/中/低能量区，评估买卖点所处能量区间的合理性。上涨信号在高能量区加分，下跌信号在低能量区加分。返回 `energy_zone`, `energy_score`, `volume_concentration`, `confidence_adjust`, `msg`。

- **`_calc_signal_execution_window_v81`**（`src/easy_tdx/chanlun/mmd.py`）—— 信号执行窗口评估（条件259）。综合波动率和流动性评估信号的可执行性窗口：高波动+低流动性→窗口差，需谨慎；低波动+高流动性→窗口优，可执行。返回 `window_quality`, `volatility_score`, `liquidity_score`, `confidence_adjust`, `msg`。

### 后端集成

- **MMD 类新增4个V81字段**（`src/easy_tdx/chanlun/types.py`）：`_volatility_regime_transition_v81`, `_support_resistance_strength_v81`, `_volume_price_energy_distribution_v81`, `_signal_execution_window_v81`
- **ConditionGroup 新增 V81**（`src/easy_tdx/backtest/chanlun_validator.py`）：条件范围(256, 259)，描述"波动率状态转换+支撑阻力强度+量价能量分布+执行窗口"
- **诊断API增强**（`src/easy_tdx/web/routers/diagnosis.py`）：新增V81四维度量摘要 + 4个V81条件字段到 chanlun 响应
- **缠论分析API增强**（`src/easy_tdx/web/routers/chanlun.py`）：MMD摘要新增V81字段 + v81_summary 顶层摘要

### 前端集成

- **`web-ui/src/types.ts`**：`DiagnosisChanlun` 新增4个V81可选字段；`DiagnosisResult` 新增 `v81_summary` 接口
- **`web-ui/src/views/DiagnosisView.vue`**：
  - 新增 `v81QualityLabel` 函数
  - 新增 V81 四维度量摘要卡片（Hero区域）
  - 新增4个V81条件卡片（波动率转换/支撑阻力/量价能量/执行窗口）
  - 新增 V81 CSS 样式（v81-summary-row, v81-tag, v81-vrt, v81-srs, v81-vped, v81-sew）
- **`web-ui/src/views/ChanlunView.vue`**：MMD表格数据映射新增V81字段

### 测试

- **`tests/unit/test_chanlun_v81.py`**（20 个测试用例）：
  - `TestV81ConditionGroup`：枚举存在性、条件范围(256-259)、描述文案
  - `TestV81MMDFields`：MMD对象包含4个V81字段
  - `TestV81BacktestValidator`：单组/多组合验证、summary输出
  - `TestV81Functions`：波动率转换（压缩/数据不足/买卖点差异）、支撑阻力（强/数据不足/字段完整）、量价能量（买入/卖出/数据不足/无量）、执行窗口（有利/数据不足/字段完整）、综合冒烟、V79/V80兼容性

---

## 核心功能清单（更新后）

### 缠论买卖点增强（V58-V81，共 88 个增强条件）
| 版本 | 条件范围 | 核心能力 |
|------|----------|----------|
| V80 | 252-255 | 中枢距离验证+量能配合度+均线排列强度+盈亏比动态评估 |
| **V81** | **256-259** | **波动率状态转换+支撑阻力强度+量价能量分布+执行窗口评估** |

### 诊断系统
| 功能 | 状态 |
|------|------|
| V77-V81 四维度量摘要（Hero区域） | ✅ |
| V77-V81 缠论条件卡片（共 52 张） | ✅ |
