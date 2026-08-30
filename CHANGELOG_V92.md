# 更新日志 V92

## [V92] — 2026-08-30

**质量工程：全仓 `mypy src/` 归零（500 → 0）—— CI mypy 门槛从全红到全绿**

> 路线图 P2 已全部落地（V88–V91）。本次转向**代码质量硬门槛**：修复全仓 mypy 严格模式
> 错误至 `mypy src/` 零错误（CI mypy job 的 `mypy src/` 步骤此前一直失败）。

### 修复规模（10 个文件，500 → 0 错误）

- **`chanlun/types.py`（225 → 0）**：补 `from typing import Any`；`_signal_aging` 泛型参数；
  运行时动态挂载的 MMD 字段（`_vol_regime`/`_trend_accel`/`_vol_regime_dual`/`_vol_price_divergence`/
  `_vol_dist_at_zg`/`_vol_dist_at_zd`）在 dataclass 中显式声明
- **`chanlun/mmd.py`（220 → 0）**：
  - 23 个私有辅助函数 `closes/highs/lows/volumes` 签名放宽为 Optional + 顶部空值守卫（语义不变）；
  - 函数对象运行时属性（`find_mmds._last_*`）改用 `setattr` + `type: ignore[attr-defined]`；
  - 修复 3 处**真实运行时缺陷**：`mmd.zs.get(...)`（ZS 是 dataclass 非 dict）、`zs.bcs`（应为 `zs.lines`）、
    `find_mmds_v39` 引用未定义变量 `trend_strength`/`bc_list`（此前被 try 吞掉、条件从未生效）——现已正确初始化；
  - `_calc_bi_force`/`_calc_breakout_force_ratio` 参数放宽为 `Line`（BI/XD 基类）；
  - v75 多信号时间一致性：macd 参数从 `list[dict]` 改为 `dict[str, list[float]]` 并重写金叉/死叉检测
    （此前签名与调用不匹配、该分支运行时必然抛错被吞）；
  - 大量 `result: dict[str, Any]` 注解、None 守卫、ndarray→list 转换、未定义变量修复
- **`chanlun/analyser.py`（6 → 0）**：`mmd.quality` 改用 `getattr`；BOLL ndarray → list
- **`web/routers/chanlun.py`（13 → 0）**：`_to_json_safe` 返回包 `cast`；`buy/sell_signals` float；
  V79 一致性摘要提取局部变量
- **`web/routers/diagnosis.py`（14 → 0）**：`_detect_divergence` ndarray→list；`strength/chanlun_score` 类型；
  `cast` 包裹 JSON 返回；修复 `multi_stock_comparison` 用错字段（`stock.category/exchange` → `market/code`）
- **`web/routers/screening.py`（2 → 0）/ `monitor.py`（1 → 0）**：dict/Task 泛型参数；Task 注解去引号
- **`backtest/strategies/chanlun.py`（1 → 0）/ `changying_chanlun.py`（11 → 0）**：参数/返回注解；
  `_analyser`/`_chanlun_result` 类型标注；`_history` 泛型
- **`MyTT.pyi`**：DMI 参数 `M/N` → `M1/M2`、BIAS 参数 `N1/N2/N3` → `L1/L2/L3`（与实际实现一致）

### 质量验证

- `mypy src/`：**0 错误**（基线 500；CI mypy job 门槛全绿）
- 全量单元测试：**2264 通过**，无回归
- ruff：10 个改动文件**无新增违规**（既有历史遗留 E501 等不在本次范围，共 1300+ 项另立任务）
- 顺手修复的运行时缺陷均有单测/既有用例覆盖（chanlun 相关 52 例全部通过）

### 说明

- 本次为纯类型/质量修复，无功能行为变化（除上述 3 处被 try 吞掉的真实 bug 修复外）
- ruff 全量 1300+ 项历史遗留（E501 长行等）另立 V93+ 任务
