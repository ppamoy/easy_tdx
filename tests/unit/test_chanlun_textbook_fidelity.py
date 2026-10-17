"""缠论**原文保真度**验证（教科书案例，标准答案先于代码给定）。

动机：缠论回测结论（docs/CHANLUN_MULTI_LEVEL_FULL_THEORY.md）全部挂在
"这份实现"头上。若实现偏离缠论原文，那些结论说明的是 bug 而不是缠论。
本文件就是来封住这个口子的。

与既有 ~90 个 chanlun 测试的区别：
  既有测试大多**mock BI/ZS 对象**再断言函数行为（回归锁），或断言硬编码数值。
  本文件改为：构造 **K 线序列** → 走**完整 analyser 管道** → 断言
  **原文定义的买卖点**出现在原文规定的位置。
  标准答案写在注释里，**先于**实现给出，不是从代码输出反推的。

原文定义（标准答案，用来判分）：
  3买：中枢形成后向上突破 zg，其后回踩**不破** zg（回踩低点 > ZG）
  3卖：中枢形成后向下跌破 zd，其后反抽**不破** zd（反抽高点 < ZD）

每个 case 都配**负向对照**（该出现时出现 / 不该出现时不出现），
否则"永远返回空"也能通过。

⚠️ 构造要点（踩过的坑，改数据时别丢）：
  1. 相同 K 线会被**合并**成一根 ⇒ 每段必须有波动（amp）和渐变
  2. 最后一笔需要**后续 K 线确认**才能成立 ⇒ 必须留 tail；
     tail 的方向也要与末段一致，否则末笔不会被确认
  3. 中枢需要**连续三笔重叠**，走势至少要有 4 笔
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig

AMP = 0.35


def _leg(p0: float, p1: float, n: int, amp: float = AMP) -> list[tuple]:
    """从 p0 渐变到 p1 的 n 根 K 线，返回 (high, low, open, close)。"""
    out = []
    for i in range(n):
        mid = p0 + (p1 - p0) * ((i + 1) / n)
        hi, lo = mid + amp, mid - amp
        out.append((hi, lo, lo + (hi - lo) * 0.3, lo + (hi - lo) * 0.7))
    return out


def _build(points: list[float], ns: list[int], tail: int = 3) -> list[tuple]:
    """按 关键点序列 + 每段根数 构造走势；tail 用于确认最后一笔。

    ⚠️ tail 必须**反向**于末段：末段向下（回踩）要接一段向上才能确认底分型，
    末段向上（反抽）要接一段向下才能确认顶分型。接同向会判定不了末笔
    （实测：接同向时 3buy/3sell 全部消失）。
    """
    seq: list[tuple] = []
    for a, b, n in zip(points, points[1:], ns):
        seq += _leg(a, b, n)
    if tail:
        last_dir = 1 if points[-1] >= points[-2] else -1
        seq += _leg(points[-1], points[-1] - 0.5 * last_dir, tail)
    return seq


def _run(seq: list[tuple], **cfg):
    dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(len(seq))]
    df = pd.DataFrame({
        "datetime": dates,
        "open": [c[2] for c in seq],
        "close": [c[3] for c in seq],
        "high": [c[0] for c in seq],
        "low": [c[1] for c in seq],
        "vol": [100000] * len(seq),
    })
    # V735 Round 10：默认 zs_from_xd=True 改为线段构中枢（第91课），
    # 但本测试用合成短序列（<30根），线段不足3根无法构中枢。
    # 显式设 zs_from_xd=False 用笔构中枢，测试买卖点逻辑本身。
    cfg.setdefault("zs_from_xd", False)
    return ChanlunAnalyser(
        code="TEST", frequency="daily", config=ChanlunConfig(**cfg)
    ).process_klines(df)


def _types(res) -> set[str]:
    return {m.mmd_type.value for m in getattr(res, "mmds", [])}


def _bis(res) -> list[tuple]:
    return [(b.direction.value, round(b.low, 2), round(b.high, 2)) for b in res.bis]


def _zss(res) -> list[tuple]:
    return [(round(z.zd, 2), round(z.zg, 2)) for z in res.zss]


# 走势：[10,20,18,21,19] 形成中枢 ≈[18.65,20.35]，26 向上离开，末段回踩
NS = [5, 4, 4, 4, 6, 6]


# ══════════════════════════════════════════════════════════════════════════════
# 3买 / 3卖（原文定义最结构化，应最容易判对）
# ══════════════════════════════════════════════════════════════════════════════

def test_3buy_fires_when_pullback_stays_above_zg():
    """教科书 3买：中枢(18.65~20.35) → 向上离开到 26 → 回踩到 22（> ZG）⇒ 出 3buy。"""
    res = _run(_build([10, 20, 18, 21, 19, 26, 22], NS))

    assert len(res.bis) >= 4, f"笔太少：{_bis(res)}"
    assert len(res.zss) >= 1, f"未识别中枢：{_bis(res)}"
    zg = res.zss[0].zg
    assert "3buy" in _types(res), (
        f"回踩低点 22 > ZG {zg:.2f}，按原文应出 3buy，实际没有。"
        f"笔={_bis(res)} 中枢={_zss(res)} 信号={_types(res)}"
    )


def test_3buy_suppressed_when_pullback_reenters_zs():
    """负向对照：回踩跌回中枢内部（17 < ZG）⇒ 不得出 3buy。

    与上例唯一区别是回踩更深。若本例也出 3buy，
    说明实现没有真正检查「不破 zg」这条原文判据。
    """
    res = _run(_build([10, 20, 18, 21, 19, 26, 17], NS))
    assert len(res.zss) >= 1, f"未识别中枢：{_bis(res)}"
    assert "3buy" not in _types(res), (
        f"回踩已跌回中枢内（17 < ZG {res.zss[0].zg:.2f}）仍出 3buy ⇒ "
        f"未检查「不破 zg」。信号={_types(res)}"
    )


def test_3sell_fires_when_rebound_stays_below_zd():
    """教科书 3卖（3买镜像）：中枢(9.65~11.35) → 向下离开到 5 → 反抽到 9（< ZD）。"""
    res = _run(_build([20, 10, 12, 9, 11, 5, 9], NS))

    assert len(res.bis) >= 4, f"笔太少：{_bis(res)}"
    assert len(res.zss) >= 1, f"未识别中枢：{_bis(res)}"
    assert "3sell" in _types(res), (
        f"反抽高点 9 < ZD {res.zss[0].zd:.2f}，按原文应出 3sell。"
        f"笔={_bis(res)} 中枢={_zss(res)} 信号={_types(res)}"
    )


def test_3buy_boundary_pullback_exactly_at_zg_is_rejected():
    """边界：回踩**恰好等于** ZG ⇒ 不算 3buy（`low <= zg` 即视为破）。

    实测标定：ZD/ZG = [18.65, 20.35]，末笔 low=20.35 时不出信号，
    low=20.40 时出。

    ⚠️ 牙齿的边界（诚实声明）：本用例**能**检出卖侧 `>=`→`>` 的写错
    （见 test_3sell_boundary_rebound_exactly_at_zd_is_rejected，实测变红），
    但**检不出**买侧 `<=`→`<`：因为构造出来的 low 与 ZG 是浮点近似相等
    （20.35 vs 20.350000000000002），两种写法在该点上判定一致。
    想真正锁住买侧边界，需要一个 low 与 ZG **精确位相等**的构造，
    目前 AMP 渐变生成做不到。此处保留用例（它仍锁住「贴边不出信号」
    这一可观测行为），但不宣称它覆盖了 `<=`/`<` 的差异。
    """
    res = _run(_build([10, 20, 18, 21, 19, 26, 20.70], NS))
    assert len(res.zss) >= 1, f"未识别中枢：{_bis(res)}"
    last_low = res.bis[-1].low
    zg = res.zss[0].zg
    assert last_low <= zg + 1e-9, f"构造失效：末笔 low={last_low} 未贴到 ZG={zg}"
    assert "3buy" not in _types(res), (
        f"回踩恰等于 ZG（{zg:.2f}）不应算 3buy。信号={_types(res)}"
    )


def test_3buy_boundary_pullback_just_above_zg_is_accepted():
    """边界（另一侧）：回踩**略高于** ZG ⇒ 算 3buy。

    与上例配对，锁定「严格 >」语义。两个用例合起来才构成边界的牙齿。
    """
    res = _run(_build([10, 20, 18, 21, 19, 26, 20.80], NS))
    assert len(res.zss) >= 1, f"未识别中枢：{_bis(res)}"
    zg = res.zss[0].zg
    assert res.bis[-1].low > zg, f"构造失效：末笔 low 未高于 ZG={zg}"
    assert "3buy" in _types(res), f"回踩略高于 ZG 应算 3buy。信号={_types(res)}"


def test_3sell_suppressed_when_rebound_reenters_zs():
    """负向对照：反抽回到中枢内部（13 > ZD）⇒ 不得出 3sell。"""
    res = _run(_build([20, 10, 12, 9, 11, 5, 13], NS))
    assert len(res.zss) >= 1, f"未识别中枢：{_bis(res)}"
    assert "3sell" not in _types(res), (
        f"反抽已回到中枢内（13 > ZD {res.zss[0].zd:.2f}）仍出 3sell。"
        f"信号={_types(res)}"
    )


def test_3sell_boundary_rebound_exactly_at_zd_is_rejected():
    """边界：反抽**恰好等于** ZD ⇒ 不算 3sell（`high >= zd` 即视为破）。

    实测标定：ZD=9.65，末笔 high=9.65 时不出信号，9.55 时出。
    锁住卖侧边界，与买侧成对。
    """
    res = _run(_build([20, 10, 12, 9, 11, 5, 9.30], NS))
    assert len(res.zss) >= 1, f"未识别中枢：{_bis(res)}"
    last_high = res.bis[-1].high
    zd = res.zss[0].zd
    assert last_high >= zd - 1e-9, f"构造失效：末笔 high={last_high} 未贴到 ZD={zd}"
    assert "3sell" not in _types(res), f"反抽恰等于 ZD（{zd:.2f}）不应算 3sell"


def test_3sell_boundary_rebound_just_below_zd_is_accepted():
    """边界（另一侧）：反抽**略低于** ZD ⇒ 算 3sell。"""
    res = _run(_build([20, 10, 12, 9, 11, 5, 9.20], NS))
    assert len(res.zss) >= 1, f"未识别中枢：{_bis(res)}"
    zd = res.zss[0].zd
    assert res.bis[-1].high < zd, f"构造失效：末笔 high 未低于 ZD={zd}"
    assert "3sell" in _types(res), f"反抽略低于 ZD 应算 3sell。信号={_types(res)}"


# ══════════════════════════════════════════════════════════════════════════════
# 结构性不变量（缠论公理，违反即实现有错）
# ══════════════════════════════════════════════════════════════════════════════

CASES = {
    "3买走势": [10, 20, 18, 21, 19, 26, 22],
    "3卖走势": [20, 10, 12, 9, 11, 5, 9],
}


@pytest.mark.parametrize("pts", list(CASES.values()), ids=list(CASES))
def test_bi_directions_alternate(pts):
    """笔方向必须严格交替 —— 缠论不存在相邻同向笔。"""
    res = _run(_build(pts, NS))
    dirs = [b.direction.value for b in res.bis]
    for i in range(len(dirs) - 1):
        assert dirs[i] != dirs[i + 1], f"第 {i}/{i+1} 笔同向（{dirs[i]}）：{dirs}"


@pytest.mark.parametrize("pts", list(CASES.values()), ids=list(CASES))
def test_bi_endpoints_contiguous(pts):
    """相邻笔必须首尾相接：第 i 笔终点 = 第 i+1 笔起点。"""
    res = _run(_build(pts, NS))
    for i in range(len(res.bis) - 1):
        a, b = res.bis[i], res.bis[i + 1]
        assert a.end.val == pytest.approx(b.start.val), (
            f"第 {i} 笔终点 {a.end.val} ≠ 第 {i+1} 笔起点 {b.start.val}"
        )


@pytest.mark.parametrize("pts", list(CASES.values()), ids=list(CASES))
def test_zs_zd_le_zg(pts):
    """中枢下沿 ≤ 上沿（区间不得倒置）。"""
    res = _run(_build(pts, NS))
    for z in res.zss:
        assert z.zd <= z.zg, f"中枢区间倒置：zd={z.zd} > zg={z.zg}"


@pytest.mark.parametrize("pts", list(CASES.values()), ids=list(CASES))
def test_zs_range_within_constituent_bis(pts):
    """中枢区间必须是构成笔的重叠区，不得超出构成笔范围。"""
    res = _run(_build(pts, NS))
    for z in res.zss:
        if not z.lines:
            continue
        lo = min(b.low for b in z.lines)
        hi = max(b.high for b in z.lines)
        assert z.zd >= lo - 1e-9, f"ZD={z.zd} 低于构成笔最低 {lo}"
        assert z.zg <= hi + 1e-9, f"ZG={z.zg} 高于构成笔最高 {hi}"


def test_flat_market_produces_no_1buy():
    """横盘无趋势不应产生 1买 —— 原文：1买 是趋势反转点，盘整顶底不算。"""
    seq: list[tuple] = []
    for i in range(60):
        base = 10.0 + (0.15 if i % 2 else 0.0)
        seq.append((base + 0.1, base - 0.1, base, base + 0.02))
    res = _run(seq)
    assert "1buy" not in _types(res), f"横盘无趋势仍出 1买：{_types(res)}"


# ══════════════════════════════════════════════════════════════════════════════
# 1买 / 2买（审计发现的**关键空白**：此前没有任何结构定义级断言）
#
# 背景（scripts 审计，2026-10-10）：mmd.py 的买侧「回撤不超过 50%」门槛
# 曾是**死代码**（值赋给 `_` 后丢弃），导致回撤 99% 也标 2买，而卖侧真门槛
# ⇒ 买卖两侧不对称 ⇒ 回测**系统性做多偏误**。V731 已修，但**当时没有任何
# 单测抓到过它**（人工对照才发现）。下面两例就是来自动锁住这条的。
# ══════════════════════════════════════════════════════════════════════════════

# 下跌趋势 + 两中枢 ⇒ 1买 出现在低位 8.65，其后回调段用作 2买 判据
_1BUY_BASE = [30, 20, 25, 15, 20, 10, 14, 9, 13]
_1BUY_NS = [5, 4, 4, 4, 4, 4, 4, 4, 4]


def test_1buy_appears_after_downtrend_with_two_zs():
    """1买：下跌趋势（≥2 个同向下跌中枢）后的背驰低点 ⇒ 出 1buy。

    构造：30→20→25→15→20→10→14→9→13，形成两个下跌中枢。
    实测：1buy 出现在 low=8.65（最后的背驰低点）。
    """
    res = _run(_build(_1BUY_BASE + [11], _1BUY_NS + [4]))
    assert len(res.zss) >= 2, f"下跌中枢不足 2 个：{_zss(res)}"
    assert "1buy" in _types(res), (
        f"下跌趋势+背驰应出 1buy。笔={_bis(res)} 中枢={_zss(res)} 信号={_types(res)}"
    )


def test_2buy_shallow_pullback_after_1buy():
    """2买（浅回调）：1买 后回调**不破** 1买 低点且回撤浅 ⇒ 应有 2买族信号。

    实测标定：回调到 11 / 10.5 时出 `2buy_s`（类二买）；回调到 ≤10 时消失。
    """
    res = _run(_build(_1BUY_BASE + [11], _1BUY_NS + [4]))
    types = _types(res)
    assert "1buy" in types, f"前置条件不成立：无 1buy，{types}"
    assert types & {"2buy", "2buy_s"}, (
        f"1买 后浅回调（不破前低）应出 2买族信号，实际 {types}"
    )


def test_2buy_allowed_on_deep_pullback_lesson101():
    """2买（深回调 / 跌破 1买）：第101课原文口径下**应**标 2买。

    第101课答疑1（逐字）：「最弱的情况：**第二类买点跌破第一类买点**，也就是
    第二类买点比第一类买点低，**这是完全可以的**」；第17课「第一类买点出现后
    **第一次次级别回调**制造的低点……第二类买点」（无任何回撤深度门槛）。

    ⇒ 默认 `mmd_2nd_max_pullback=None`（纯原文口径）时：
       - 深回调（回到 1买 附近，9.5 > 1买 8.65）⇒ 2买 **应出现**（第一个回调低点即 2买）；
       - 跌破 1买（8.3 < 1买 8.65，第101课「最弱情况」）⇒ 2买 **也应出现**。

    ⚠️ 本测试取代旧 `test_2buy_suppressed_on_deep_pullback`。那条锁的是 V731
    「系统性做多偏误」的 50% 回撤门槛——但该门槛在数学上封死了第101课「最弱情况」
    （行为级实测 scripts/audit_chanlun_fidelity_current.py V3：0.5 时 0/10 低于 1买，
    None 时 11/26）。原文是判据，回测偏误是结果，不能反过来否决原文（V735 §5）。
    50% 门槛保留为**可配工程口径**，下面同步锁其旧行为（两侧对照，AGENTS.md §4）。
    """
    # —— 原文口径（默认 mmd_2nd_max_pullback=None）——
    # 深回调（9.5，回到 1买 附近但未破）⇒ 2买 应出现
    res = _run(_build(_1BUY_BASE + [9.5], _1BUY_NS + [4]))
    types = _types(res)
    assert "1buy" in types, f"前置条件不成立：无 1buy，{types}"
    assert "2buy" in types, (
        f"第17/101课原文口径：第一次回调低点即 2买，无深度门槛。深回调（9.5）应出 2buy。"
        f"实际信号={types}"
    )

    # 第101课「最弱情况」：2买 跌破 1买（8.3 < 1买 8.65）⇒ 2买 仍应出现
    res_below = _run(_build(_1BUY_BASE + [8.3], _1BUY_NS + [4]))
    types_below = _types(res_below)
    assert "1buy" in types_below, f"前置条件不成立：无 1buy，{types_below}"
    assert "2buy" in types_below, (
        f"第101课「最弱情况：第二类买点跌破第一类买点……这是完全可以的」。"
        f"2买跌破 1买（8.3 < 8.65）仍应出 2buy。实际信号={types_below}"
    )

    # —— 工程口径（mmd_2nd_max_pullback=0.5，旧默认行为）两侧对照 ——
    # 同一深回调（9.5）在 50% 门槛下 ⇒ 不出 2买（旧行为保留，可显式开启）
    res_eng = _run(_build(_1BUY_BASE + [9.5], _1BUY_NS + [4]), mmd_2nd_max_pullback=0.5)
    types_eng = _types(res_eng)
    assert "1buy" in types_eng, f"前置条件不成立：无 1buy，{types_eng}"
    assert not (types_eng & {"2buy", "2buy_s"}), (
        f"工程口径 mmd_2nd_max_pullback=0.5：深回调（>50%）应抑制 2买族（旧行为）。"
        f"实际信号={types_eng}"
    )
