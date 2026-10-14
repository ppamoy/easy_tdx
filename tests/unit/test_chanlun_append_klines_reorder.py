"""V731：append_klines 去重后必须重排序（否则回补历史 K 线会算错分型）。

缺陷（实测确认）：

`append_klines` 拼接后做 `drop_duplicates(subset=["datetime"], keep="last")`
但**没有重排序**。`keep="last"` 保留的是靠后出现的那条，所以当 `df_new` 里
含**更早日期**（数据回补/修正）时，那根 K 线会被留在序列**末尾**，时间序列
不再单调递增。

实测（5 根 K 线，追加 01-07 + 回补 01-01）：
    去重后顺序 = [01-02, 01-03, 01-06, 01-07, 01-01]  ← 01-01 跑到最后
    正确顺序 → 分型 0 个；乱序 → 分型 2 个（多出来的分型是错的）

缠论的分型/笔/中枢/线段**全部依赖 K 线顺序**，序列乱序会静默产出错误结构
（不抛异常、不报警，只是结果不对）—— 属于最难发现的那类 bug。

修复：去重后按 datetime 稳定排序（mergesort，同 datetime 保持原相对次序）。
"""

from __future__ import annotations

import pandas as pd
import pytest

from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig


def _rows() -> list[dict]:
    return [
        {
            "datetime": "2025-01-02T15:00:00",
            "open": 10.0,
            "close": 10.2,
            "high": 10.3,
            "low": 9.9,
            "vol": 100,
            "amount": 1000.0,
        },
        {
            "datetime": "2025-01-03T15:00:00",
            "open": 10.2,
            "close": 10.5,
            "high": 10.6,
            "low": 10.1,
            "vol": 100,
            "amount": 1000.0,
        },
        {
            "datetime": "2025-01-06T15:00:00",
            "open": 10.5,
            "close": 10.1,
            "high": 10.7,
            "low": 10.0,
            "vol": 100,
            "amount": 1000.0,
        },
    ]


def _backfill() -> list[dict]:
    """含一条**更早**日期（回补）与一条更新的。"""
    return [
        {
            "datetime": "2025-01-01T15:00:00",
            "open": 9.8,
            "close": 9.9,
            "high": 10.0,
            "low": 9.7,
            "vol": 100,
            "amount": 1000.0,
        },
        {
            "datetime": "2025-01-07T15:00:00",
            "open": 10.1,
            "close": 10.8,
            "high": 10.9,
            "low": 10.0,
            "vol": 100,
            "amount": 1000.0,
        },
    ]


def _signature(result) -> tuple:
    return (
        len(result.bis),
        len(result.fractals),
        len(result.valid_fractals),
        len(result.zss),
        len(result.mmds),
    )


class TestAppendKlinesReordersAfterDedup:
    """回补历史 K 线时，结果必须与「一次算全量」一致。"""

    def test_backfill_matches_full_recompute(self) -> None:
        base = _rows()
        # 参照：一次性按时间排序后算
        expect = ChanlunAnalyser(code="000001", frequency="daily", config=ChanlunConfig(zs_from_xd=False)).process_klines(
            pd.DataFrame(sorted(base + _backfill(), key=lambda r: r["datetime"]))
        )

        a = ChanlunAnalyser(code="000001", frequency="daily", config=ChanlunConfig(zs_from_xd=False))
        a.process_klines(pd.DataFrame(base))
        got = a.append_klines(pd.DataFrame(_backfill()))

        assert _signature(got) == _signature(expect), (
            f"append 结果 {_signature(got)} != 全量重算 {_signature(expect)}"
        )

    def test_sequence_is_monotonic_after_append(self) -> None:
        """直接断言：内部保留的 K 线序列必须按时间递增。"""
        a = ChanlunAnalyser(code="000001", frequency="daily", config=ChanlunConfig(zs_from_xd=False))
        a.process_klines(pd.DataFrame(_rows()))
        a.append_klines(pd.DataFrame(_backfill()))
        times = [str(k.date) for k in a._result.klines]
        assert times == sorted(times), f"K 线序列未排序: {times}"

    def test_order_independent_result(self) -> None:
        """反向锁定：新数据里两条的先后顺序不影响结果。"""
        b1 = _backfill()
        b2 = list(reversed(b1))

        def run(new_rows: list[dict]) -> tuple:
            a = ChanlunAnalyser(code="000001", frequency="daily", config=ChanlunConfig(zs_from_xd=False))
            a.process_klines(pd.DataFrame(_rows()))
            return _signature(a.append_klines(pd.DataFrame(new_rows)))

        assert run(b1) == run(b2), "新数据内部顺序不应影响结果"


class TestAppendKlinesNormalPathUnchanged:
    """对照组：只追加更新的 K 线时，行为与修复前一致。"""

    def test_append_newer_only_still_works(self) -> None:
        a = ChanlunAnalyser(code="000001", frequency="daily", config=ChanlunConfig(zs_from_xd=False))
        r0 = a.process_klines(pd.DataFrame(_rows()))
        n0 = len(r0.klines)
        newer = [
            {
                "datetime": "2025-01-07T15:00:00",
                "open": 10.1,
                "close": 10.8,
                "high": 10.9,
                "low": 10.0,
                "vol": 100,
                "amount": 1000.0,
            },
        ]
        r1 = a.append_klines(pd.DataFrame(newer))
        assert len(r1.klines) == n0 + 1

    def test_duplicate_datetime_is_deduped(self) -> None:
        """同日重复追加：不应变长（keep=last 覆盖旧值）。"""
        a = ChanlunAnalyser(code="000001", frequency="daily", config=ChanlunConfig(zs_from_xd=False))
        r0 = a.process_klines(pd.DataFrame(_rows()))
        n0 = len(r0.klines)
        same = [dict(_rows()[0], close=99.0)]  # 同一天，改收盘价
        r1 = a.append_klines(pd.DataFrame(same))
        assert len(r1.klines) == n0, "重复 datetime 应被去重而非追加"

    def test_append_requires_init(self) -> None:
        a = ChanlunAnalyser(code="000001", frequency="daily", config=ChanlunConfig(zs_from_xd=False))
        with pytest.raises(RuntimeError):
            a.append_klines(pd.DataFrame(_rows()))
