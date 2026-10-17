"""53课 line139 原文铁律回归：「黄白线都没拉回0轴不是背驰」。

趋势背驰要求 B 段（中枢2）把 MACD 黄白线（DIF/DEA）回拉到 0 轴附近。
若中枢2 期间 DIF 始终远离 0 轴（持续强跌无反弹），不构成标准背驰。

本测试覆盖 `_check_zero_axis_pullback`：
- 有 0 轴回拉（中枢2 期间 DIF 回到 0 附近/穿越）→ True
- 无 0 轴回拉（中枢2 期间 DIF 始终深负）→ False

§7 沉淀：revert `_check_zero_axis_pullback` 为恒 True（no-op）→ 本测试 FAIL。
"""

from types import SimpleNamespace as NS

from easy_tdx.chanlun.mmd_conditions import _check_zero_axis_pullback


def _mk_zs(start_bar: int, end_bar: int) -> NS:
    """构造最小 ZS mock：_check_zero_axis_pullback 只读 lines[0].start.bar_index
    与 lines[-1].end.bar_index。"""
    return NS(lines=[NS(start=NS(bar_index=start_bar), end=NS(bar_index=end_bar))])


def test_zero_axis_pullback_detected_when_dif_returns_near_zero():
    """中枢2 期间 DIF 从深负回拉到 0 附近 → 应判定有 0 轴回拉（True）。

    价格构造：先大跌 30 根（DIF 深负），再反弹 20 根形成中枢2（DIF 回拉接近 0），
    再小跌 20 根。中枢2 期间 min|DIF| 应远小于趋势峰值。
    """
    closes = (
        [100 - i * 2 for i in range(30)]  # 30→34，大跌，DIF 深负
        + [40 + i * 0.5 for i in range(20)]  # 40→50，反弹，DIF 回拉
        + [50 - i * 2 for i in range(20)]  # 50→10，小跌
    )
    zs1 = _mk_zs(0, 10)  # 中枢1（趋势段前段）
    zs2 = _mk_zs(30, 50)  # 中枢2（反弹段，DIF 回拉）
    assert _check_zero_axis_pullback(closes, zs1, zs2) is True


def test_no_pullback_when_dif_stays_far_from_zero():
    """中枢2 期间 DIF 始终深负（持续强跌，无反弹）→ 应判定无 0 轴回拉（False）。

    价格构造：70 根持续强跌，中枢2 期间 DIF 仍远离 0 轴 → 原文判定非背驰。
    """
    closes = [100 - i * 3 for i in range(70)]  # 100→-110，持续强跌
    zs1 = _mk_zs(0, 10)
    zs2 = _mk_zs(30, 50)  # 中枢2 仍在强跌段，DIF 深负不回拉
    assert _check_zero_axis_pullback(closes, zs1, zs2) is False


def test_pullback_via_zero_crossing():
    """DIF 穿越 0 轴（相邻异号）也应判为 0 轴回拉（True）。

    价格构造：先跌（DIF 负）后涨（DIF 转 正）→ 中枢2 期间 DIF 穿越 0 轴。
    """
    closes = (
        [100 - i * 2 for i in range(30)]  # 大跌，DIF 负
        + [40 + i * 3 for i in range(20)]  # 大涨，DIF 穿越 0 转正
        + [100 - i * 2 for i in range(20)]  # 再跌
    )
    zs1 = _mk_zs(0, 10)
    zs2 = _mk_zs(30, 50)
    assert _check_zero_axis_pullback(closes, zs1, zs2) is True


def test_none_closes_passes_through():
    """无 closes 数据时保守放行（True），避免误杀无 MACD 数据的场景。"""
    assert _check_zero_axis_pullback(None, _mk_zs(0, 10), _mk_zs(30, 50)) is True
