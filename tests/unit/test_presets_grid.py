"""策略参数预设网格的回归测试。

覆盖点：
1. 每个已登记策略**真的存在于策略注册表**（不是写了名字却找不到实现）——
   否则「一键寻优」会在运行时才发现策略不存在。
2. 笛卡尔积不超过上限（否则优化器会拒绝或跑爆）。
3. 预设里写的参数名必须是该策略**真的接受**的参数 —— 写错会静默无效。
4. ``get_preset`` 未登记时返回空 dict（调用方依赖这个行为做跳过）。
5. **chanlun_ml 必须没有登记** —— 它被全量回测证伪了（见
   docs/CHANLUN_MULTI_LEVEL_FULL_THEORY.md）。这条是防止有人
   "顺手"把它加回去而不看实测结论。
"""

from __future__ import annotations

from easy_tdx.backtest.optimizer import MAX_GRID_POINTS
from easy_tdx.backtest.strategies.presets import STRATEGY_PRESETS, get_preset
from easy_tdx.backtest.strategies.registry import get_registry


def test_preset_names_are_registered_strategies():
    """预设里写的每个 key 都必须是真实存在的策略名。"""
    known = set(get_registry().names())
    missing = [n for n in STRATEGY_PRESETS if n not in known]
    assert not missing, (
        f"预设登记了不存在的策略：{missing}。可用策略数 {len(known)}"
    )


def test_grid_size_within_cap():
    """每个策略的笛卡尔积不得超过优化器上限。"""
    for name, grid in STRATEGY_PRESETS.items():
        n = 1
        for vals in grid.values():
            n *= len(vals)
        assert n <= MAX_GRID_POINTS, f"{name} 的网格 {n} 超过上限 {MAX_GRID_POINTS}"


def test_preset_params_are_actual_strategy_params():
    """预设参数名必须是该策略**真的接受**的参数 —— 写错会静默无效。"""
    reg = get_registry()
    for name, grid in STRATEGY_PRESETS.items():
        valid = {p.name for p in reg.get(name).params}
        bad = [k for k in grid if k not in valid]
        assert not bad, f"{name} 的预设参数 {bad} 不合法（合法：{sorted(valid)}）"


def test_get_preset_unknown_returns_empty():
    assert get_preset("__definitely_not_a_strategy__") == {}


def test_chanlun_ml_not_preset_because_falsified():
    """chanlun_ml 已被全量实测证伪 ⇒ 不得登记进预设网格。

    依据（docs/CHANLUN_MULTI_LEVEL_FULL_THEORY.md，285 只）：
    - 11 个方案（区间套 / 本级别买→次级别卖 / 买点组合）**没有一个**通过
      三条判据（vsBH 显著、vsA1 为正、vsRND 为正且显著）
    - 次级别用 30min 或 60min 都一样全部为负
    - 样本外符号翻转 ⇒ 那是仓位/市场状态效应，不是选股能力

    若将来真有方案通过，应当**同时**更新本测试的注释和那份文档，
    而不是直接把断言删掉。
    """
    assert "chanlun_ml" not in STRATEGY_PRESETS
    assert get_preset("chanlun_ml") == {}
