"""V731：背驰「离开段」取法的事实锁定 + 力度长度偏置归一。

⚠️ 本文件初版曾基于一个**已被证伪**的论断，现予更正并保留记录：

    错误论断：「find_zss 关闭中枢时已把离开笔并入 zs.lines，故 lines[-1]
               即离开笔，`+1` 取到反向笔 ⇒ 趋势背驰恒不命中。」
    实测证伪：真实 find_zss **不会**把离开笔放进 lines —— 它记录在
              `zs.exit_bi`（见 tests/unit/test_chanlun_golden_samples.py::
              test_find_zss_records_enter_exit_bi：lines=[1,2,3]、
              enter_bi=0、exit_bi=4）。且对已关闭中枢，`lines[-1].index + 1`
              **恰好等于 exit_bi.index**（5 个 fixture 全部吻合）。
              故 `+1` 的取法是正确的，已回退相关改动。
    教训：当时我用「lines[-1] 是否突破自身 ZG/ZD」来判定「是否离开笔」，
          但中枢内末笔本就可能触及边界，该判据不足以区分二者 —— 间接证据
          冒充了结构事实。正确做法是查 `zs.exit_bi`。

本文件现在锁定的是实测事实本身，并覆盖 bi_force_normalize 开关两侧。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import MMDType

# 复用仓库既有的合成笔构造器（与 golden_samples 一致口径）
from tests.unit.test_chanlun_golden_samples import _mk_bi  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _mk(bars: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    from datetime import datetime, timedelta

    rows = []
    dt = datetime(2024, 1, 2)
    for o, c, h, l in bars:
        rows.append(
            {"datetime": dt, "open": o, "close": c, "high": h, "low": l, "vol": 1e6}
        )
        dt += timedelta(days=1)
    return pd.DataFrame(rows)


def _seg(n: int, start: float, end: float) -> list[tuple[float, float, float, float]]:
    """生成 n 根从 start 线性走到 end 的 K 线。"""
    out = []
    for i in range(n):
        a = start + (end - start) * i / n
        b = start + (end - start) * (i + 1) / n
        out.append((a, b, max(a, b) + 0.05, min(a, b) - 0.05))
    return out


def _textbook_downtrend(leave_bars: int = 30, leave_drop: float = 2.5):
    """下跌趋势（两个依次下移中枢）+ 缓慢离开段 → 教科书 1买。"""
    bars: list[tuple[float, float, float, float]] = []
    bars += _seg(12, 20.0, 16.0)
    bars += _seg(6, 16.0, 17.0)
    bars += _seg(6, 17.0, 16.0)
    bars += _seg(6, 16.0, 17.0)
    bars += _seg(14, 17.0, 14.0)
    bars += _seg(6, 14.0, 15.0)
    bars += _seg(6, 15.0, 14.0)
    bars += _seg(6, 14.0, 15.0)
    bars += _seg(leave_bars, 15.0, 15.0 - leave_drop)
    bars += _seg(8, 15.0 - leave_drop, 15.0)
    bars += _seg(6, 15.0, 13.2)
    bars += _seg(8, 13.2, 16.0)
    return ChanlunAnalyser(
        code="T", frequency="daily", config=ChanlunConfig()
    ).process_klines(_mk(bars))


class TestZsLeavingSegmentFact:
    """锁定「离开段 = lines[-1].index + 1 = zs.exit_bi」这一实测事实。

    这条事实是趋势背驰取法正确性的前提；一旦将来有人把离开笔并入 lines，
    本类会立刻失败并提示重新核对取法（而不是默默算错）。
    """

    @pytest.mark.parametrize(
        "fixture",
        [
            "chanlun_000001_daily.json",
            "chanlun_000001_weekly.json",
            "chanlun_000001_30min.json",
            "chanlun_000333_daily.json",
        ],
    )
    def test_plus_one_matches_exit_bi(self, fixture: str) -> None:
        rows = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
        res = ChanlunAnalyser(
            code="T", frequency="daily", config=ChanlunConfig()
        ).process_klines(pd.DataFrame(rows))
        closed = [z for z in res.zss if z.exit_bi is not None]
        assert closed, f"{fixture} 无已关闭中枢，用例前提不成立"
        for zs in closed:
            assert zs.lines[-1].index + 1 == zs.exit_bi.index, (
                f"{fixture} ZS{zs.index}: lines[-1]+1={zs.lines[-1].index + 1} "
                f"!= exit_bi={zs.exit_bi.index}（离开段取法前提已变，需复核 +1 逻辑）"
            )

    def test_leaving_bi_is_outside_lines(self) -> None:
        """离开笔不在 lines 内（否则 +1 会错）。"""
        from easy_tdx.chanlun.zs import find_zss

        bis_ = [
            _mk_bi(0, "down", 30.0, 20.0),
            _mk_bi(1, "up", 15.0, 8.0),
            _mk_bi(2, "down", 14.0, 7.0),
            _mk_bi(3, "up", 13.0, 6.0),
            _mk_bi(4, "down", 7.0, 5.0),
        ]
        zs = find_zss(bis_, ChanlunConfig())[0]
        assert [b.index for b in zs.lines] == [1, 2, 3]
        assert zs.exit_bi is bis_[4]


class TestBiForceNormalize:
    """bi_force_normalize 开关两侧都要验证（开启生效 + 关闭保持历史行为）。"""

    def test_force_is_length_biased_when_raw(self) -> None:
        """同一跌幅下，慢段的**原始**力度反而更大 —— 即归一要消除的偏置。

        在纯斜线上量测（避免笔结构随段长变化导致口径不干净）：
        跌幅同为 10 点，5 根走完 vs 20 根走完。
        """
        from easy_tdx.chanlun.macd import calc_macd_force

        def _ramp(n: int, drop: float = 10.0, p0: float = 100.0):
            return [p0 - drop * i / n for i in range(n + 1)]

        # 长度偏置在「段长 ≲ 20 根」区间内稳定成立（再长时 MACD 柱随价格
        # 走平而自然收敛，面积反而回落，属另一现象）。
        fast = calc_macd_force(_ramp(5), 0, 5)["hist_down_sum"]
        slow = calc_macd_force(_ramp(20), 0, 20)["hist_down_sum"]
        assert slow > fast, (
            f"预期慢段原始 MACD 面积更大（长度偏置），实得 slow={slow:.4f} "
            f"fast={fast:.4f}"
        )

    def test_normalize_monotonic(self) -> None:
        """归一后：同一跌幅下，段越长（越慢）单位根力度越小。"""
        from easy_tdx.chanlun.macd import calc_macd_force

        def _ramp(n: int, drop: float = 10.0, p0: float = 100.0):
            return [p0 - drop * i / n for i in range(n + 1)]

        per_bar = []
        for n in (10, 20, 40, 80):
            s = calc_macd_force(_ramp(n), 0, n)["hist_down_sum"]
            per_bar.append(s / (n + 1))
        for i in range(len(per_bar) - 1):
            assert per_bar[i + 1] < per_bar[i], (
                f"归一后单位根力度应随段变长单调下降，实得 {per_bar}"
            )

    def test_flag_off_keeps_history(self) -> None:
        """关闭开关（默认）时行为与历史一致，不引入回归。"""
        rows = json.loads(
            (FIXTURES / "chanlun_000333_daily.json").read_text(encoding="utf-8")
        )
        got = ChanlunAnalyser(
            code="T", frequency="daily", config=ChanlunConfig(bi_force_normalize=False)
        ).process_klines(pd.DataFrame(rows))
        assert MMDType.BUY_1 in [m.mmd_type for m in got.mmds]
        assert ChanlunConfig().bi_force_normalize is False, "默认应关闭以保持历史行为"

    def test_flag_on_does_not_break_signals(self) -> None:
        """开启开关后真实样本信号不应消失。"""
        for fixture, expect in (
            ("chanlun_000001_daily.json", MMDType.SELL_1),
            ("chanlun_000333_daily.json", MMDType.BUY_1),
        ):
            rows = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
            got = ChanlunAnalyser(
                code="T",
                frequency="daily",
                config=ChanlunConfig(bi_force_normalize=True),
            ).process_klines(pd.DataFrame(rows))
            types = [m.mmd_type for m in got.mmds]
            assert expect in types, f"{fixture} 开启归一后丢失 {expect}，实际: {types}"

    def test_config_exposed(self) -> None:
        assert "bi_force_normalize" in ChanlunConfig().to_dict()

    def test_zero_force_protection(self) -> None:
        """归一后仍需保留 curr_force > 0 保护，避免 0 力度笔被判强背驰。

        先验事实（另见 test_chanlun_v731_ref_zs_no_lookahead.py::
        TestZeroForceNotBeichi）：000001_daily 的 BI6/BI9 力度恰为 0。
        此处直接断言这些零力度笔不会被判为强背驰。
        """
        from easy_tdx.chanlun.mmd_conditions import (
            _calc_bi_force,
            _is_strong_beichi,
        )

        rows = json.loads(
            (FIXTURES / "chanlun_000001_daily.json").read_text(encoding="utf-8")
        )
        res = ChanlunAnalyser(
            code="T", frequency="daily", config=ChanlunConfig()
        ).process_klines(pd.DataFrame(rows))
        closes = [k.close for k in res.klines]
        zero_bis = [
            b
            for b in res.bis
            if _calc_bi_force(b, closes, b.index, False) == 0.0
        ]
        assert zero_bis, "样本中应存在零力度笔，否则本用例失去意义"
        for b in zero_bis:
            assert not _is_strong_beichi(
                b, res.bis, res.zss, closes, 0.8, normalize_by_bars=True
            ), f"零力度笔 BI{b.index} 被判为强背驰" 


class TestZeroForcePrevBiSkipped:
    """prev_force == 0 的对比笔应被跳过（继续向前找），而不是终止搜索。

    Bug：中枢内部的笔 MACD 力度常恰为 0（实测 51 笔中 8 笔 = 16%）。旧代码
    遇到第一个同向笔就 break，若它恰好是零力度中枢内笔，则背驰判定被永久扼杀。
    教科书下跌趋势形态（audit_mmd_ground_truth.py Case1）因此完全无 1买。
    """

    def test_textbook_downtrend_prev_bi_is_zero_force(self) -> None:
        """前提：背驰段的前一同向笔确实力度为 0（否则本类失去意义）。"""
        from easy_tdx.chanlun.mmd_conditions import _calc_bi_force

        res = _textbook_downtrend()
        closes = [k.close for k in res.klines]
        bi7 = res.bis[7]
        prev = next(
            b for b in reversed(res.bis[: bi7.index]) if b.direction.value == "down"
        )
        assert _calc_bi_force(prev, closes, prev.index, False) == 0.0, (
            f"前提不成立：BI{prev.index} 力度非 0"
        )
        # 而真正该比的进入段 BI3 力度 > 0
        assert _calc_bi_force(res.bis[3], closes, 3, False) > 0

    def test_beichi_detected_past_zero_force_prev(self) -> None:
        """跳过零力度对比笔后，应能与更早的进入段建立背驰。"""
        from easy_tdx.chanlun.mmd_conditions import _is_strong_beichi

        res = _textbook_downtrend()
        closes = [k.close for k in res.klines]
        # 归一后 BI7(0.0619) < BI3(0.1208)*0.8 成立
        assert _is_strong_beichi(
            res.bis[7],
            res.bis,
            res.zss,
            closes,
            0.8,
            direction="down",
            normalize_by_bars=True,
        ), "归一后跳过零力度对比笔应能判定为背驰"

    def test_zero_force_curr_does_not_become_beichi(self) -> None:
        """当前笔自身力度为 0 时，不得判为背驰（保留 V731a 保护）。"""
        from easy_tdx.chanlun.mmd_conditions import (
            _calc_bi_force,
            _is_strong_beichi,
        )

        res = _textbook_downtrend()
        closes = [k.close for k in res.klines]
        zero = [b for b in res.bis if _calc_bi_force(b, closes, b.index, False) == 0.0]
        assert zero, "样本应含零力度笔"
        for b in zero:
            assert not _is_strong_beichi(b, res.bis, res.zss, closes, 0.8)


class TestBreakoutRetestUsesZgZd:
    """突破回踩验证必须以 ZG/ZD 为基准，而非 GG/DD。

    原文：中枢区间由 ZG/ZD 界定，3买 = 回抽不跌回**中枢区间**；
    GG/DD 只是区间内的极值（含毛刺），不是边界。
    实测 5 个 fixture 的 9 个中枢：GG/DD 区间比 ZG/ZD 大 31.6%~530%。
    """

    def test_gg_dd_is_wider_than_zg_zd(self) -> None:
        """前提事实：GG/DD 区间确实比 ZG/ZD 宽（否则本类无意义）。"""
        import json as _json

        rows = _json.loads(
            (FIXTURES / "chanlun_000001_daily.json").read_text(encoding="utf-8")
        )
        res = ChanlunAnalyser(
            code="T", frequency="daily", config=ChanlunConfig()
        ).process_klines(pd.DataFrame(rows))
        assert res.zss
        for zs in res.zss:
            assert (zs.gg - zs.dd) >= (zs.zg - zs.zd), (
                f"ZS{zs.index}: GG/DD 区间不应窄于 ZG/ZD"
            )

    def test_validation_boundary_follows_zg_zd(self) -> None:
        """同一信号下，把 gg/dd 换成 zg/zd 会改变结果 ⇒ 证明代码确在用前者。

        改为期望：函数应产出与「手工用 zg/zd 计算」一致的判定。
        """
        import copy as _copy
        import json as _json

        from easy_tdx.chanlun.mmd import _calc_breakout_retest_validation

        rows = _json.loads(
            (FIXTURES / "chanlun_000001_daily.json").read_text(encoding="utf-8")
        )
        res = ChanlunAnalyser(
            code="T", frequency="daily", config=ChanlunConfig()
        ).process_klines(pd.DataFrame(rows))
        closes = [k.close for k in res.klines]
        vols = [getattr(k, "vol", 0) or 0 for k in res.klines]
        checked = 0
        for m in res.mmds:
            got = _calc_breakout_retest_validation(m, res.bis, res.zss, closes, vols)
            # 手工用 zg/zd 复算「回踩区」是否一致：把 gg/dd 对齐到 zg/zd 后
            # 结果应与当前实现相同 —— 因为实现现在就是用 zg/zd。
            z = _copy.copy(m.zs)
            z.gg, z.dd = z.zg, z.zd
            m2 = _copy.copy(m)
            m2.zs = z
            expect = _calc_breakout_retest_validation(
                m2, res.bis, res.zss, closes, vols
            )
            assert got == expect, (
                f"{m.mmd_type.value}: 实现未按 zg/zd 计算 "
                f"(got={got} expect={expect})"
            )
            checked += 1
        assert checked, "无信号可校验"

    def test_gg_inflates_range(self) -> None:
        """GG/DD 会显著拉伸区间（记录量级，防止有人把边界改回 gg/dd）。"""
        import json as _json

        rows = _json.loads(
            (FIXTURES / "chanlun_000001_weekly.json").read_text(encoding="utf-8")
        )
        res = ChanlunAnalyser(
            code="T", frequency="daily", config=ChanlunConfig()
        ).process_klines(pd.DataFrame(rows))
        zs = res.zss[0]
        base = zs.zg - zs.zd
        wide = zs.gg - zs.dd
        assert wide > base * 2, (
            f"预期 GG/DD 区间显著大于 ZG/ZD（实测应约 +530%），实得 "
            f"{wide:.2f} vs {base:.2f}"
        )


class TestSecondTypeSpanWindowConfigurable:
    """2买/2卖 回调笔的时间窗口上限应可配置（默认 0 = 不限，纯原文口径）。

    旧实现硬编码 15（2买/2卖）/ 20（类二买/类二卖）根K线——原文并无此限制，
    实测静默吞掉 28% 的候选（46 个相邻笔间隔中 13 个 > 15 根），且绝对根数
    阈值在周线/月线上跨周期不等价。
    """

    def test_default_is_unlimited(self) -> None:
        assert ChanlunConfig().mmd_2nd_span_max_bars == 0
        assert "mmd_2nd_span_max_bars" in ChanlunConfig().to_dict()

    def test_span_gate_actually_applies(self) -> None:
        """设为极小值时应能拦掉信号；不设时不应拦 —— 两侧都要验证。"""
        rows = json.loads(
            (FIXTURES / "chanlun_000333_daily.json").read_text(encoding="utf-8")
        )
        got_open = ChanlunAnalyser(
            code="T", frequency="daily", config=ChanlunConfig(mmd_2nd_span_max_bars=0)
        ).process_klines(pd.DataFrame(rows))
        got_tight = ChanlunAnalyser(
            code="T", frequency="daily", config=ChanlunConfig(mmd_2nd_span_max_bars=1)
        ).process_klines(pd.DataFrame(rows))
        types_open = [m.mmd_type.value for m in got_open.mmds]
        types_tight = [m.mmd_type.value for m in got_tight.mmds]
        assert "2buy" in types_open, f"不限时 2买 应存在，实得 {types_open}"
        assert "2buy" not in types_tight, (
            f"收紧到 1 根时 2买 应被拦掉，实得 {types_tight}"
        )

    def test_adjacent_bis_share_endpoints(self) -> None:
        """前提事实：相邻笔共享端点 ⇒ 旧的 time_to_leave>30 恒为 0（死代码）。"""
        for fixture in (
            "chanlun_000001_daily.json",
            "chanlun_000333_daily.json",
            "chanlun_600519_daily.json",
        ):
            rows = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
            res = ChanlunAnalyser(
                code="T", frequency="daily", config=ChanlunConfig()
            ).process_klines(pd.DataFrame(rows))
            deltas = {
                res.bis[i + 1].start.k.k_index - res.bis[i].end.k.k_index
                for i in range(len(res.bis) - 1)
            }
            assert deltas == {0}, f"{fixture}: 相邻笔应共享端点，实得 {deltas}"


class TestNonCanonicalHeuristicsAreInert:
    """工程启发式（非原文）在实测样本上不应吞掉任何信号。

    _MIN_1ST_GAP_BIS=5（相邻1买隔几笔）与 _MIN_REBOUND_RATIO=0.03（3%反弹
    去重）都是**工程去重**，缠论原文并无此要求。它们只是为了避免同一底部
    反复标注。本测试锁定「当前 5 个 fixture 上关闭它们不改变任何信号」，
    一旦它们开始吞掉真实信号，这里就会失败并要求重新评估。
    """

    def test_heuristics_do_not_change_signals(self) -> None:
        import easy_tdx.chanlun.mmd as mmd_mod

        for fixture in sorted(FIXTURES.glob("chanlun_*.json")):
            rows = json.loads(fixture.read_text(encoding="utf-8"))
            df = pd.DataFrame(rows)
            before = [
                m.mmd_type.value
                for m in ChanlunAnalyser(
                    code="T", frequency="daily", config=ChanlunConfig()
                ).process_klines(df).mmds
            ]
            saved = (
                mmd_mod._MIN_1ST_GAP_BIS,
                mmd_mod._MIN_REBOUND_RATIO,
            )
            try:
                mmd_mod._MIN_1ST_GAP_BIS = 0
                mmd_mod._MIN_REBOUND_RATIO = 0.0
                after = [
                    m.mmd_type.value
                    for m in ChanlunAnalyser(
                        code="T", frequency="daily", config=ChanlunConfig()
                    ).process_klines(df).mmds
                ]
            finally:
                mmd_mod._MIN_1ST_GAP_BIS, mmd_mod._MIN_REBOUND_RATIO = saved

            assert before == after, (
                f"{fixture.name}: 工程启发式改变了信号 {before} -> {after}，"
                "需重新评估其是否符合原文"
            )

    def test_gap_threshold_is_documentable(self) -> None:
        """_MIN_1ST_GAP_BIS 存在且被注释标注为非原文（防止误当原文规则使用）。"""
        from easy_tdx.chanlun.mmd import _MIN_1ST_GAP_BIS

        assert _MIN_1ST_GAP_BIS == 5


class TestSecondTypeDependsOnFirstType:
    """已知实现偏差：2买/2卖 **依附** 1买/1卖 的存在（而非仅依附其结构）。

    ⚠️ V731 二次修正（初版措辞过高，已被实测证伪）：
    初版称这是「级联失效 / 检测器缺陷被放大到下游」，暗示 2买 自身结构合法
    却被无辜丢弃。**实测不支持该说法**：严格按同一力度口径扫描，「结构候选
    集」与「已标 1买 集」在所有 fixture 和两种口径下都**完全相等**（见下
    test_structural_candidates_are_identical）——当某口径下 1买 消失时，支撑
    它的「背驰 + 跌破中枢下沿」结构在该口径下同样不成立。不是下游被牵连，
    而是**两级口径一致地认为没有背驰**。

    真实机制（教科书 Case1 实测，跌破 zd 的候选均为笔 3/5/7）：
        norm=False → trend=1.00, below=[3,5,7], beichi=[]   → 无 1买、无 2买
        norm=True  → trend=1.00, below=[3,5,7], beichi=[7]  → 1买 + 2买
    差异自始至终只发生在 `_is_strong_beichi` 这一个环节，trend_strength
    闸门（≥2 同向中枢）并未参与。

    故本测试只锁定「2买 依赖 1买 存在」这一结构性事实，不再声称它是级联 bug。
    是否解耦属设计取舍，而非修 bug。
    """

    def _case1_bars(self):
        def seg(n: int, o: float, c: float, jitter: float = 0.05):
            out = []
            for i in range(n):
                t0 = o + (c - o) * (i / n)
                t1 = o + (c - o) * ((i + 1) / n)
                lo, hi = min(t0, t1), max(t0, t1)
                out.append((t0, t1, hi + jitter, lo - jitter))
            return out

        b = []
        b += seg(12, 20.0, 16.0)
        b += seg(6, 16.0, 17.0) + seg(6, 17.0, 16.0) + seg(6, 16.0, 17.0)
        b += seg(14, 17.0, 14.0)
        b += seg(6, 14.0, 15.0) + seg(6, 15.0, 14.0) + seg(6, 14.0, 15.0)
        b += seg(30, 15.0, 12.5)   # 背驰离开段，创新低
        b += seg(8, 12.5, 15.0)    # 反弹（离开笔）
        b += seg(6, 15.0, 14.0)    # 回调不创新低 → 教科书 2买
        b += seg(8, 14.0, 16.0)
        return b

    def test_structural_candidates_are_identical(self) -> None:
        """关键反证：结构候选集 == 已标 1买 集 ⇒ 不存在「下游被牵连」。

        这是推翻初版「级联失效」论断的实测依据。若某一口径下存在「满足
        down笔 + low<ref_zs.zd + 同口径背驰」却没被标成 1买 的笔，说明
        确实有结构被无辜丢弃（级联成立）；实测在所有 fixture 和两种力度
        口径下都为空集差异。
        """
        from easy_tdx.chanlun.mmd import (
            _is_strong_beichi,
            _reference_zs_for_bi,
        )

        for fixture in sorted(FIXTURES.glob("chanlun_*.json")):
            rows = json.loads(fixture.read_text(encoding="utf-8"))
            for norm in (False, True):
                res = ChanlunAnalyser(
                    code="T",
                    frequency="daily",
                    config=ChanlunConfig(bi_force_normalize=norm),
                ).process_klines(pd.DataFrame(rows))
                closes = [k.close for k in res.klines]
                marked = {
                    m.bi.index
                    for m in res.mmds
                    if m.mmd_type.value == "1buy" and m.bi
                }
                cands = set()
                for bi in res.bis:
                    if bi.direction.value != "down":
                        continue
                    rz = _reference_zs_for_bi(res.zss, bi)
                    if rz is None or bi.low >= rz.zd:
                        continue
                    if _is_strong_beichi(
                        bi,
                        res.bis,
                        res.zss,
                        closes,
                        0.8,
                        normalize_by_bars=norm,
                    ):
                        cands.add(bi.index)
                assert cands == marked, (
                    f"{fixture.name} norm={norm}: 结构候选 {sorted(cands)} != "
                    f"已标 1买 {sorted(marked)} —— 若出现此差异，说明确有合法"
                    "结构被下游丢弃（级联成立），需重新评估本类的定性"
                )

    def test_norm_false_has_no_divergence_candidate(self) -> None:
        """教科书 Case1：norm=False 下连背驰候选都没有 ⇒ 差异源于力度口径。"""
        from easy_tdx.chanlun.mmd import (
            _is_strong_beichi,
            _reference_zs_for_bi,
        )

        rows = []
        dt = datetime(2024, 1, 2)
        for o, c, h, l in self._case1_bars():
            rows.append(
                {
                    "datetime": dt,
                    "open": o,
                    "close": c,
                    "high": h,
                    "low": l,
                    "vol": 1e6,
                }
            )
            dt += timedelta(days=1)
        res = ChanlunAnalyser(
            code="T", frequency="daily", config=ChanlunConfig()
        ).process_klines(pd.DataFrame(rows))
        closes = [k.close for k in res.klines]

        below = []
        beichi = []
        for bi in res.bis:
            if bi.direction.value != "down":
                continue
            rz = _reference_zs_for_bi(res.zss, bi)
            if rz is None or bi.low >= rz.zd:
                continue
            below.append(bi.index)
            if _is_strong_beichi(
                bi, res.bis, res.zss, closes, 0.8, normalize_by_bars=False
            ):
                beichi.append(bi.index)

        assert below, f"前置假设失败：应有跌破 zd 的笔，实得 {below}"
        assert beichi == [], (
            f"norm=False 下应无背驰候选（这才是 1买/2买 消失的真正原因），"
            f"实得 {beichi}"
        )

    def test_cascade_suppresses_valid_2buy(self) -> None:
        """1买 消失 → 结构合法的 2买 也连带消失（记录偏差）。"""
        from datetime import datetime as _dt, timedelta as _td

        rows = []
        dt = _dt(2024, 1, 2)
        for o, c, h, l in self._case1_bars():
            rows.append(
                {
                    "datetime": dt,
                    "open": o,
                    "close": c,
                    "high": h,
                    "low": l,
                    "vol": 1e6,
                }
            )
            dt += _td(days=1)
        df = pd.DataFrame(rows)

        opened = [
            m.mmd_type.value
            for m in ChanlunAnalyser(
                code="T",
                frequency="daily",
                config=ChanlunConfig(bi_force_normalize=True),
            ).process_klines(df).mmds
        ]
        closed = [
            m.mmd_type.value
            for m in ChanlunAnalyser(
                code="T", frequency="daily", config=ChanlunConfig()
            ).process_klines(df).mmds
        ]

        assert "1buy" in opened, f"归一化开启时应有 1buy，实得 {opened}"
        assert "2buy" in opened, f"归一化开启时应有 2buy，实得 {opened}"
        # 级联：不看 2买 自身判据，仅仅因为 1买 没检出就消失
        assert "1buy" not in closed, f"前置事实变更：现在默认也能检出 1buy：{closed}"
        assert "2buy" not in closed, (
            "级联事实变更：2buy 现已能在无 1buy 时独立出现 —— 说明解耦已完成，"
            f"请重新评估本测试的语义与实际信号 {closed}"
        )


class TestSecondTypeSpanCrossPeriodEquivalence:
    """同一形态在**不同周期**下应给出相同结论 —— 实测并不成立。

    绝对根数阈值（旧硬编码 15 根）在日线/周线/月线含义完全不同：同一个
    回调结构在日线上是 N 根，周线约 N/5、月线约 N/20。因此同一个 2买
    在日线被拒、在周线却被放行（或反之）。

    实测（长回调 18 根）：
        span 上限不限      → 2buy 存在
        span 上限 15（日线）→ 2buy 消失   ← 形态没变，只因周期标尺被砍
        span 上限 75（周线缩放）→ 2buy 恢复
    """

    def _bars(self, pullback_bars: int):
        def seg(n: int, o: float, c: float, jitter: float = 0.05):
            out = []
            for i in range(n):
                t0 = o + (c - o) * (i / n)
                t1 = o + (c - o) * ((i + 1) / n)
                lo, hi = min(t0, t1), max(t0, t1)
                out.append((t0, t1, hi + jitter, lo - jitter))
            return out

        b: list = []
        b += seg(12, 20.0, 16.0)
        b += seg(6, 16.0, 17.0) + seg(6, 17.0, 16.0) + seg(6, 16.0, 17.0)
        b += seg(14, 17.0, 14.0)
        b += seg(6, 14.0, 15.0) + seg(6, 15.0, 14.0) + seg(6, 14.0, 15.0)
        b += seg(30, 15.0, 12.5)
        b += seg(8, 12.5, 15.0)
        b += seg(pullback_bars, 15.0, 14.0)   # 回调不创新低 → 2买
        b += seg(8, 14.0, 16.0)
        flat = b
        rows = []
        dt = datetime(2024, 1, 2)
        for o, c, h, l in flat:
            rows.append(
                {"datetime": dt, "open": o, "close": c, "high": h, "low": l, "vol": 1e6}
            )
            dt += timedelta(days=1)
        return pd.DataFrame(rows)

    def _types(self, pullback_bars: int, span_limit: int) -> list[str]:
        cfg = ChanlunConfig(
            bi_force_normalize=True, mmd_2nd_span_max_bars=span_limit
        )
        return [
            m.mmd_type.value
            for m in ChanlunAnalyser(
                code="T", frequency="daily", config=cfg
            ).process_klines(self._bars(pullback_bars)).mmds
        ]

    def test_long_pullback_rejected_by_daily_limit(self) -> None:
        """18 根回调：不限时有 2buy，日线 15 根上限时被砍掉。"""
        assert "2buy" in self._types(18, 0)
        assert "2buy" not in self._types(18, 15)

    def test_period_normalized_limit_restores_signal(self) -> None:
        """同一结构按周线缩放（15*5=75）后 2buy 恢复 —— 证明两周期不等价。"""
        assert "2buy" in self._types(18, 75)

    def test_short_pullback_unaffected(self) -> None:
        """短回调（6 根）在任何阈值下都应检出 —— 对照组。"""
        for lim in (0, 15, 75):
            assert "2buy" in self._types(6, lim), f"短回调在 span={lim} 下丢失"


class TestBiForceNormalizeTradeoff:
    """bi_force_normalize 开/关各有盲区 ⇒ 不应贸然翻转默认值。

    教科书形态（下跌趋势 + 背驰离开段创新低 + 回调不创新低）下，只改变
    「离开段的行进根数」（= 下跌快慢，趋势垂体/盘跌的区别），结构完全一致
    （实测均为 5 笔 down、2 个中枢、同一最低价），但两种力度口径的检出情况
    不同：

    V732 重测（波动率阈值改为逐笔 as-of 后，矩阵已变化，原结论已证伪并更新）：

        同时被两者检出     : n = 48..80（慢跌，两者一致）
        仅 raw 面积检出    : n = 8..12 （急跌）
        仅 单位根归一 检出 : n = 20..44（缓跌 ← 教科书「背驰」的典型形态）
        两者都漏           : n = 16

    ⚠️ 与 V731 记录的差异：n=48 原属「仅归一」，修复后 raw 也能检出
    （原因：旧实现用**全序列尾部**的 ATR 波动率算全局阈值，把末尾反弹段的
    高波动率套到了背驰笔上，导致阈值档位误判；改为按背驰笔自身位置 as-of
    取值后，该笔判定回到真实波动率，raw 口径得以检出）。
    这是**召回变好**，不是回归 —— 已用 scripts/audit_mmd_ground_truth.py
    （6/6）与 scripts/audit_future_leak_real.py（224 组 0 违反）双向确认。

    结论（仍成立）：normalize=True 在 20~44 根区间救回教科书背驰，但在极急跌
    区间会漏。两者都不完备，故 config 默认保持 False，由调用方按风格显式选择。
    一旦有人做出能同时覆盖 n=8..80 的改进，这里的断言会失败提示重估。
    """

    def _case(self, leaving_bars: int) -> pd.DataFrame:
        def seg(n: int, o: float, c: float, jitter: float = 0.05):
            out = []
            for i in range(n):
                t0 = o + (c - o) * (i / n)
                t1 = o + (c - o) * ((i + 1) / n)
                lo, hi = min(t0, t1), max(t0, t1)
                out.append((t0, t1, hi + jitter, lo - jitter))
            return out

        b: list = []
        b += seg(12, 20.0, 16.0)
        b += seg(6, 16.0, 17.0) + seg(6, 17.0, 16.0) + seg(6, 16.0, 17.0)
        b += seg(14, 17.0, 14.0)
        b += seg(6, 14.0, 15.0) + seg(6, 15.0, 14.0) + seg(6, 14.0, 15.0)
        b += seg(leaving_bars, 15.0, 12.5)      # 背驰离开段，创新低
        b += seg(8, 12.5, 15.0)                 # 反弹
        b += seg(6, 15.0, 14.0)                 # 回调不创新低
        b += seg(8, 14.0, 16.0)
        rows = []
        dt = datetime(2024, 1, 2)
        for o, c, h, l in b:
            rows.append(
                {"datetime": dt, "open": o, "close": c, "high": h, "low": l, "vol": 1e6}
            )
            dt += timedelta(days=1)
        return pd.DataFrame(rows)

    def _has_1buy(self, leaving_bars: int, normalize: bool) -> bool:
        return any(
            m.mmd_type.value == "1buy"
            for m in ChanlunAnalyser(
                code="T",
                frequency="daily",
                config=ChanlunConfig(bi_force_normalize=normalize),
            ).process_klines(self._case(leaving_bars)).mmds
        )

    def test_normalize_recovers_slow_decline(self) -> None:
        """20~44 根缓跌：只有归一能检出（教科书写照）。

        V732：n=48 已从本组移出 —— 波动率阈值改为 as-of 后 raw 也能检出（见
        类 docstring），故此处只断言 20/32/40。n=48 由
        test_slow_segment_both_agree 覆盖为「两者都检出」。
        """
        for n in (20, 32, 40):
            assert not self._has_1buy(n, False), f"n={n}: raw 不应检出"
            assert self._has_1buy(n, True), f"n={n}: 归一应检出"

    def test_raw_recovers_sharp_decline(self) -> None:
        """8~12 根急跌：只有 raw 能检出 ⇒ 归一并非严格更优。"""
        for n in (8, 12):
            assert self._has_1buy(n, False), f"n={n}: raw 应检出"
            assert not self._has_1buy(n, True), f"n={n}: 归一不应检出"

    def test_both_miss_exists(self) -> None:
        """n=16 两者都漏 ⇒ 说明需要更好的力度口径，而非简单翻转开关。"""
        assert not self._has_1buy(16, False)
        assert not self._has_1buy(16, True)

    def test_slow_segment_both_agree(self) -> None:
        """48 根以上慢跌两者一致（对照组：确认改动没有全局破坏召回）。

        V732：下界由 56 下调为 48 —— as-of 修复后 n=48 的 raw 也检出了。
        """
        for n in (48, 56, 72):
            assert self._has_1buy(n, False), f"n={n}: raw 应检出"
            assert self._has_1buy(n, True), f"n={n}: 归一应检出"


class TestBiForceDimensionMixing:
    """_calc_bi_force 量纲混用审计（原 P1 遗留项，本轮完成）。

    _calc_bi_force 有**两条返回路径**，数值不同量纲：
      1. MACD 柱面积和（hist_down_sum / hist_up_sum）—— 正常路径
      2. abs(bi.high - bi.low) 振幅 —— 三条降级路径：
         (a) closes is None 或空
         (b) start_idx<0 或 end_idx>=len(closes)（closes 被裁剪/笔越界）
         (c) calc_macd_force 抛异常

    实测两条路径的数值比：中位 **3.2 倍**，范围 **1.0~12.0 倍**（000333_daily
    的 10 个笔）。背驰判定是 `curr_force < prev_force * threshold` 的**比值
    比较**，一旦同一比较里 curr 走 MACD、prev 走振幅，结果彻底失真。

    好消息：**正常链路不会混用**——analyser 里 closes 由同一份 klines 导出，
    实测 5 个 fixture 共 51 个笔，越界（走降级）的 **0 个**。

    风险只在 closes 被外部裁剪时（增量加载/拼接/部分重算）。实测后果：
        closes 长度 160 → 降级笔 0，背驰命中 [2]
        closes 长度 60  → 降级笔 7，背驰命中 [2]
        closes 长度 40  → 降级笔 8，背驰命中 []（结果已漂移）
    故本测试锁定「完整 closes 下两操作数同路径」这一不变量。
    """

    def _res_and_closes(self, fixture: str = "chanlun_000333_daily.json"):
        rows = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
        res = ChanlunAnalyser(
            code="T", frequency="daily", config=ChanlunConfig()
        ).process_klines(pd.DataFrame(rows))
        return res, [k.close for k in res.klines]

    def test_no_degraded_path_on_complete_closes(self) -> None:
        """完整 closes 下不应有笔走降级路径（量纲混用的前提不成立）。"""
        for fixture in sorted(p.name for p in FIXTURES.glob("chanlun_*.json")):
            res, closes = self._res_and_closes(fixture)
            degraded = [
                bi.index
                for bi in res.bis
                if bi.start.bar_index < 0 or bi.end.bar_index >= len(closes)
            ]
            assert degraded == [], (
                f"{fixture}: 完整 closes 下仍有笔走降级路径 {degraded}"
            )

    def test_paths_differ_by_an_order_of_magnitude(self) -> None:
        """两条路径数值确实差很大 —— 记录量级，防止有人以为可互换。"""
        from easy_tdx.chanlun.mmd_conditions import _calc_bi_force

        res, closes = self._res_and_closes()
        ratios = []
        for i, bi in enumerate(res.bis):
            macd_v = _calc_bi_force(bi, closes, i)
            amp_v = _calc_bi_force(bi, None, i)   # 强制走振幅降级
            if macd_v > 0:
                ratios.append(amp_v / macd_v)
        assert ratios, "无有效笔"
        assert min(ratios) > 0.5 and max(ratios) > 5, (
            f"两条路径应相差显著，实测比值 {min(ratios):.2f}~{max(ratios):.2f}"
        )

    def test_truncated_closes_shifts_divergence(self) -> None:
        """closes 被裁剪 ⇒ 降级路径介入 ⇒ 背驰结果漂移（记录风险，非断言正确值）。"""
        from easy_tdx.chanlun.mmd import _is_strong_beichi

        res, full = self._res_and_closes()
        hits_full = [
            bi.index
            for bi in res.bis
            if bi.direction.value == "down"
            and _is_strong_beichi(bi, res.bis, res.zss, full, 0.8)
        ]
        short = full[:40]
        hits_short = [
            bi.index
            for bi in res.bis
            if bi.direction.value == "down"
            and _is_strong_beichi(bi, res.bis, res.zss, short, 0.8)
        ]
        degraded = sum(
            1 for bi in res.bis if bi.end.bar_index >= len(short)
        )
        assert degraded > 0, f"前置假设失败：裁剪后应有降级笔，实得 {degraded}"
        assert hits_full != hits_short, (
            f"裁剪后结果应漂移，实得 full={hits_full} short={hits_short}"
        )


class TestBlindSpotN16IsGenuineBoundary:
    """n=16 盲区是**真实边界情形**，不是某个口径的 bug。

    精确比值（背驰段笔7 / 进入段笔3，阈值 0.8）：
        n=12 → raw 0.795 ✓ | 归一 0.918    | 振幅 0.839
        n=16 → raw 0.954   | 归一 0.841    | 振幅 0.839   ← 三者都不过
        n=20 → raw 1.044   | 归一 0.746 ✓  | 振幅 0.839
        n=30 → raw 1.059   | 归一 0.512 ✓  | 振幅 0.839
        n=40 → raw 0.949   | 归一 0.347 ✓  | 振幅 0.839

    关键结论：振幅口径对该形态**恒为 0.839**（>0.8），任何 n 都判不出背驰
    ⇒ 把 _calc_bi_force 的降级路径（振幅）当作备选方案是无效的。
    n=16 三者都不过，是因为各口径在此确实接近等价，属本质上的边界情形。
    """

    def _forces(self, n: int) -> tuple[float, float, float, float]:
        from easy_tdx.chanlun.mmd_conditions import _calc_bi_force

        res, rows = None, []
        dt = datetime(2024, 1, 2)

        def seg(k: int, o: float, c: float, jitter: float = 0.05):
            out = []
            for i in range(k):
                t0 = o + (c - o) * (i / k)
                t1 = o + (c - o) * ((i + 1) / k)
                lo, hi = min(t0, t1), max(t0, t1)
                out.append((t0, t1, hi + jitter, lo - jitter))
            return out

        b: list = []
        b += seg(12, 20.0, 16.0)
        b += seg(6, 16.0, 17.0) + seg(6, 17.0, 16.0) + seg(6, 16.0, 17.0)
        b += seg(14, 17.0, 14.0)
        b += seg(6, 14.0, 15.0) + seg(6, 15.0, 14.0) + seg(6, 14.0, 15.0)
        b += seg(n, 15.0, 12.5)
        b += seg(8, 12.5, 15.0) + seg(6, 15.0, 14.0) + seg(8, 14.0, 16.0)
        for o, c, h, l in b:
            rows.append(
                {"datetime": dt, "open": o, "close": c, "high": h, "low": l, "vol": 1e6}
            )
            dt += timedelta(days=1)
        res = ChanlunAnalyser(
            code="T", frequency="daily", config=ChanlunConfig()
        ).process_klines(pd.DataFrame(rows))
        closes = [k.close for k in res.klines]
        pos = {bi.index: i for i, bi in enumerate(res.bis)}
        b3, b7 = res.bis[pos[3]], res.bis[pos[7]]
        raw = _calc_bi_force(b7, closes, pos[7]) / _calc_bi_force(b3, closes, pos[3])
        nrm = (
            _calc_bi_force(b7, closes, pos[7], normalize_by_bars=True)
            / _calc_bi_force(b3, closes, pos[3], normalize_by_bars=True)
        )
        amp = abs(b7.high - b7.low) / abs(b3.high - b3.low)
        return raw, nrm, amp, 0.8

    def test_n12_raw_only(self) -> None:
        raw, nrm, _amp, th = self._forces(12)
        assert raw < th and nrm >= th

    def test_n16_all_fail(self) -> None:
        raw, nrm, amp, th = self._forces(16)
        assert raw >= th, f"raw 应不过，实得 {raw}"
        assert nrm >= th, f"归一应不过，实得 {nrm}"
        assert amp >= th, f"振幅应不过，实得 {amp}"

    def test_amplitude_never_recovers(self) -> None:
        """振幅口径对该形态恒定 ~0.839 ⇒ 不是可行的补救方案（对照组）。"""
        seen = set()
        for n in (12, 16, 20, 30, 40):
            _, _, amp, th = self._forces(n)
            seen.add(amp < th)
            assert abs(amp - 0.839) < 0.02, f"n={n}: 振幅比应近 0.839，实得 {amp:.3f}"
        assert seen == {False}, f"振幅口径不应在任何 n 下判出背驰，实得 {seen}"
