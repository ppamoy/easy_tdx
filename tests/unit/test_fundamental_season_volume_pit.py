"""V731：四季判断的量能信号不得使用 target 之后的未来数据。

缺陷
----
`detect_season` 的收盘价是经 `_closes()` 按 `target` 过滤的（只保留 dd <= target），
但 **volumes 是原样传入、未过滤**的，而函数内取 `volumes[-60:]` —— 即"序列最后
60 根"。于是判断某个**历史时点**的四季时，量能信号读的是 target 之后的未来数据。

实测（未来段量能非均匀暴涨）：
    传全量 volumes(320) → vol_score2=1, total=2
    传截断 volumes(150) → vol_score2=0, total=1
两者应一致却不一致 —— 四季结论被未来数据污染。

这正是 F7 要求的"截至 T 的市场数据"没被满足的地方；与 F8 的 PIT 纪律属同一类。

修复：新增 `_volumes()`，与 `_closes()` 同口径按 target 过滤后再取窗口。

测试写法要点（我自己踩的坑）
--------------------------
第一版我把未来段的量能设成**均匀**暴涨（整段 1000→50000），结果 `v5/v60` 比值
仍是 1.0 → score 恒为 0，**测不出 bug**。必须让**最后 5 根**相对**前 55 根**显著
不同，才能让比值越过 1.2 的阈值。已把这个坑写进注释。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from easy_tdx.fundamental.season import detect_season

N = 320  # 总 K 线数
T_IDX = 150  # target 落在第 150 根处
BASE = date(2024, 1, 1)


def _dates() -> list[date]:
    return [BASE + timedelta(days=i) for i in range(N)]


def _closes() -> list[float]:
    return [100.0 + i * 0.1 for i in range(N)]


def _vols_with_future_spike() -> list[float]:
    """target 之后**最后 5 根**量能暴涨（非均匀，比值才能越过阈值）。"""
    v = [1000.0] * N
    for i in range(N - 5, N):
        v[i] = 100_000.0
    return v


class TestVolumeSignalIsPointInTime:
    def test_future_volume_does_not_change_historical_season(self) -> None:
        """核心：追加 target 之后的量能，不得改变 target 处的结论。"""
        dates, closes, vols, target = (
            _dates(),
            _closes(),
            _vols_with_future_spike(),
            _dates()[T_IDX],
        )
        full = detect_season(dates, closes, target, volumes=vols)
        truncated = detect_season(dates, closes, target, volumes=vols[: T_IDX + 1])
        assert full.signals["vol_score2"] == truncated.signals["vol_score2"], (
            "量能信号受 target 之后的数据影响（前视）"
        )
        assert full.season == truncated.season
        assert full.signals["total_score"] == truncated.signals["total_score"]

    def test_future_volume_shrink_also_detected(self) -> None:
        """反向：未来段量能**萎缩**同样不得影响（两侧都要测）。"""
        v = [1000.0] * N
        for i in range(N - 5, N):
            v[i] = 10.0  # 量能骤降
        dates, closes, target = _dates(), _closes(), _dates()[T_IDX]
        full = detect_season(dates, closes, target, volumes=v)
        truncated = detect_season(dates, closes, target, volumes=v[: T_IDX + 1])
        assert full.signals["vol_score2"] == truncated.signals["vol_score2"]
        assert full.season == truncated.season

    @pytest.mark.parametrize("t_idx", [80, 120, 200, 260])
    def test_invariance_at_multiple_historical_points(self, t_idx: int) -> None:
        """多个历史时点上都应成立（不只挑一个能过的点）。"""
        dates, closes, vols = _dates(), _closes(), _vols_with_future_spike()
        target = dates[t_idx]
        full = detect_season(dates, closes, target, volumes=vols)
        truncated = detect_season(dates, closes, target, volumes=vols[: t_idx + 1])
        assert full.signals["vol_score2"] == truncated.signals["vol_score2"], (
            f"t_idx={t_idx} 处量能信号受未来数据影响"
        )

    def test_none_and_empty_volumes_still_work(self) -> None:
        """边界：没传量能时不应报错，且退化为 0 分。"""
        dates, closes, target = _dates(), _closes(), _dates()[T_IDX]
        for v in (None, []):
            r = detect_season(dates, closes, target, volumes=v)
            assert r.signals["vol_score2"] == 0


class TestVolumeFilterHelper:
    """`_volumes` 必须与 `_closes` 同口径（只保留 <= target，升序）。"""

    def test_filters_by_target_and_drops_nan(self) -> None:
        from easy_tdx.fundamental.season import _volumes

        dates = _dates()[:100]
        vols = [float(i) for i in range(100)] + [float("nan")] * 0
        target = dates[49]
        got = _volumes(dates, vols, target)
        assert len(got) == 50, f"应只保留 <= target 的 50 条，实际 {len(got)}"
        assert got == [float(i) for i in range(50)]

    def test_drops_nan_entries(self) -> None:
        from easy_tdx.fundamental.season import _volumes

        dates = _dates()[:10]
        vols = [1.0, float("nan"), 3.0, None, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        got = _volumes(dates, vols, dates[9])
        assert float("nan") not in got
        assert len(got) == 8


class TestAllSeasonSignalsArePointInTime:
    """V731 第 34 轮：未来免疫必须是**全信号**的，且在**全时点范围**成立。

    既有 TestVolumeSignalIsPointInTime 只盯量能一个信号。四季判断还有价格趋势、
    均线、波动率三个信号 —— 若其中任何一个直接读序列尾部（`cs[-60:]`），同样
    会构成前视。这里用「未来段极端值替换」探针对**所有信号**整体做不变性校验：
    把 target 之后的收盘/量能换成任何极端值，四季结论与全部中间信号都不得变化。

    写法上的坑（我自己踩过，记下来防再犯）：
    探针构造未来段时，`closes` 与 `volumes` 必须与 `dates` 保持**等长**。
    第一版我只替换了 closes、没动 dates，结果 zip() 把长 dates 和短 closes
    对齐，`target`（取自 dates[T_IDX]）落到了对齐后的序列之外，探针测的是
    一个"未来"时点 —— 误报出「autumn→winter 泄漏」。数据形态必须与生产
    路径一致（pipeline.detect_season_for_date 传全 320 根，四列等长）。
    """

    N_FULL = 320
    BASE_FULL = date(2025, 1, 1)

    @classmethod
    def _series(cls) -> tuple[list[date], list[float], list[float]]:
        import random

        rng = random.Random(11)
        dates = [cls.BASE_FULL + timedelta(days=i) for i in range(cls.N_FULL)]
        closes: list[float] = []
        px = 100.0
        for _ in range(cls.N_FULL):
            px *= 1 + rng.uniform(-0.02, 0.02)
            closes.append(px)
        vols = [rng.uniform(8e5, 1.2e6) for _ in range(cls.N_FULL)]
        return dates, closes, vols

    @staticmethod
    def _snapshot(r) -> tuple:
        return (
            r.season,
            r.signals.get("total_score"),
            r.signals.get("trend_60d_pct"),
            r.signals.get("ma_ratio"),
            r.signals.get("vol_score"),
            r.signals.get("vol_score2"),
        )

    def test_future_extremes_cannot_change_conclusion(self) -> None:
        dates, closes, vols = self._series()
        t_idx = 150
        target = dates[t_idx]
        base = self._snapshot(detect_season(dates, closes, target, volumes=vols))
        for label, mult, vol in (("暴涨+放量", 3.0, 5e7), ("暴跌+缩量", 0.2, 1e3)):
            c2 = closes[: t_idx + 1] + [closes[t_idx] * mult] * (self.N_FULL - t_idx - 1)
            v2 = vols[: t_idx + 1] + [vol] * (self.N_FULL - t_idx - 1)
            got = self._snapshot(detect_season(dates, c2, target, volumes=v2))
            assert got == base, f"未来段{label}改变了历史时点结论: {base} -> {got}"

    def test_invariance_across_full_time_range(self) -> None:
        """t_idx 40→300 每隔 5 取一个时点 × 未来暴涨/暴跌两种探针，全部不变。"""
        dates, closes, vols = self._series()
        for t_idx in range(40, self.N_FULL, 5):
            target = dates[t_idx]
            base = self._snapshot(detect_season(dates, closes, target, volumes=vols))
            for mult, vol in ((3.0, 5e7), (0.2, 1e3)):
                c2 = closes[: t_idx + 1] + [closes[t_idx] * mult] * (self.N_FULL - t_idx - 1)
                v2 = vols[: t_idx + 1] + [vol] * (self.N_FULL - t_idx - 1)
                got = self._snapshot(detect_season(dates, c2, target, volumes=v2))
                assert got == base, f"t_idx={t_idx} mult={mult}: {base} -> {got}"

    def test_production_shape_alignment(self) -> None:
        """与生产路径同形态：pipeline 传全 320 根、四列等长，结论须与「只传到 target」一致。"""
        dates, closes, vols = self._series()
        t_idx = 150
        target = dates[t_idx]
        full = detect_season(dates, closes, target, volumes=vols)
        trimmed = detect_season(
            dates[: t_idx + 1], closes[: t_idx + 1], target, volumes=vols[: t_idx + 1]
        )
        assert self._snapshot(full) == self._snapshot(trimmed)
