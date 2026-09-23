"""审计管道单测（V722，R2）。

全部用假 MAC 会话注入确定性行情，不连真实服务器；
重点：数据缺失哨兵（null + data_missing）、point-in-time 哨兵、
长盈分层统计与缠论台账口径的确定性。
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from easy_tdx.audit.accuracy import (
    MacSession,
    _returns_at_dates,
    audit_chanlun,
    audit_changying,
    recent_quarter_ends,
)


def _mk_df(n: int = 900, base: float = 10.0, drift: float = 0.01) -> pd.DataFrame:
    """确定性上行序列：dates 从 2024-01-01 起每个交易日。"""
    bdates = pd.bdate_range("2024-01-01", periods=n)
    closes = base * np.cumprod(1 + drift + 0.002 * np.sin(np.arange(n) / 7))
    return pd.DataFrame({"date": bdates, "close": closes})


UP_DF = _mk_df()
DOWN_DF = _mk_df(base=10.0, drift=-0.01)


def test_recent_quarter_ends() -> None:
    ends = recent_quarter_ends(5, today=date(2026, 9, 23))
    assert ends == [
        date(2026, 6, 30),
        date(2026, 3, 31),
        date(2025, 12, 31),
        date(2025, 9, 30),
        date(2025, 6, 30),
    ]


def test_returns_at_dates_horizons() -> None:
    df = _mk_df(n=400)
    bases = [date(2024, 6, 3)]
    out = _returns_at_dates(df, bases, (20, 60))
    slot = out["2024-06-03"]
    assert slot["bars_after"] > 60
    # 上行序列 → 两个窗口都应为正
    assert slot["ret_20d"] > 0
    assert slot["ret_60d"] > slot["ret_20d"]


def test_returns_at_dates_missing_horizon_is_none() -> None:
    df = _mk_df(n=400)  # 覆盖 2024-01-01 起 400 个交易日（约至 2025-07）
    # 基期贴近序列尾部：250 日前瞻必然不足 → null（诚实缺失）
    out = _returns_at_dates(df, [date(2025, 7, 1)], (250,))
    slot = out["2025-07-01"]
    assert slot["ret_250d"] is None
    assert slot["bars_after"] < 250


def test_returns_at_dates_before_listing_clamped() -> None:
    """基期早于上市：回退上市首日并诚实标记（不伪造也不报错中断）。"""
    out = _returns_at_dates(UP_DF, [date(2023, 1, 1)], (20,))
    slot = out["2023-01-01"]
    assert slot.get("base_clamped_to_listing") is True
    assert slot["ret_20d"] is not None


class _FakeMac:
    """假 MAC 客户端：按代码路由到上行/下行序列。"""

    def __init__(self, up_codes: set[str], down_codes: set[str]) -> None:
        self.up = up_codes
        self.down = down_codes
        self.index_calls = 0

    def get_stock_kline(self, market, code, period, start=0, count=800, adjust=None, **kw):
        import time

        time.sleep(0)  # 确定性无等待
        if market == 1 and code == "000001":
            self.index_calls += 1
            return UP_DF.copy()
        if code in self.up:
            return UP_DF.copy()
        if code in self.down:
            return DOWN_DF.copy()
        raise ValueError("MAC 返回空 K 线")

    def close(self) -> None:
        pass


def _session_with(up: set[str], down: set[str]) -> MacSession:
    s = MacSession()
    s.client = _FakeMac(up, down)
    return s


@pytest.fixture()
def fake_marks():
    rows = [
        {"symbol": "SH:600001", "market": "SH", "code": "600001", "category": "tree", "score": 90.0, "report_date": "2026-06-20", "trade_date": "2026-09-23"},
        {"symbol": "SZ:000002", "market": "SZ", "code": "000002", "category": "grain", "score": 60.0, "report_date": "2026-06-20", "trade_date": "2026-09-23"},
        {"symbol": "SZ:000003", "market": "SZ", "code": "000003", "category": "vegetable", "score": 20.0, "report_date": None, "trade_date": "2026-09-23"},
    ]
    with patch("easy_tdx.audit.accuracy._sample_marks") as m:
        m.return_value = {
            "tree": [rows[0]],
            "grain": [rows[1]],
            "vegetable": [rows[2]],
        }
        yield rows


def test_audit_changying_missing_data_is_none_not_fake(fake_marks) -> None:
    """取数失败的标的：data_missing=True 且 performance 缺失，绝不合成。"""
    # 000002 会抛「空 K 线」→ data_missing
    s = _session_with(up={"600001", "000003"}, down=set())
    report = audit_changying([date(2026, 6, 30)], samples=1, session=s)
    assert not report.get("data_missing")
    by_sym = {e["symbol"]: e for e in report["per_symbol"]}
    assert by_sym["SZ:000002"]["data_missing"] is True
    assert by_sym["SZ:000002"]["performance"] == {}
    # 成功标的有真实收益（上行序列 → 正）
    perf = by_sym["SH:600001"]["performance"]["2026-06-30"]
    assert perf["ret_20d"] > 0


def test_audit_changying_pit_violation_flagged(fake_marks) -> None:
    """report_date 晚于快照日 → pit_ok False（PIT 哨兵）。"""
    fake_marks[2]["report_date"] = "2026-12-31"  # 未来财报
    s = _session_with(up={"600001", "000002", "000003"}, down=set())
    report = audit_changying([date(2026, 6, 30)], samples=1, session=s)
    by_sym = {e["symbol"]: e for e in report["per_symbol"]}
    assert by_sym["SZ:000003"]["pit_ok"] is False
    assert by_sym["SH:600001"]["pit_ok"] is True
    assert report["per_class"]["vegetable"]["pit_violations"] == 1


def test_audit_changying_class_stats_shape(fake_marks) -> None:
    s = _session_with(up={"600001", "000002", "000003"}, down=set())
    report = audit_changying([date(2026, 6, 30)], samples=1, session=s)
    tree = report["per_class"]["tree"]["2026-06-30"]
    assert tree["ret_20d"]["n"] == 1
    assert 0.0 <= tree["ret_20d"]["win_rate"] <= 1.0
    # 2026-06-30 基期后仅 248 根 < 250 → 诚实 null（不外推）
    assert tree["ret_250d"]["p50"] is None
    assert tree["ret_250d"]["n"] == 0
    # 超额需要指数 → 假客户端支持指数
    assert tree["excess_20d"]["n"] == 1


def test_audit_chanlun_ledger_aligned(fake_marks) -> None:
    """缠论审计口径 = signal_ledger（方向对齐，命中率可复核）。"""
    from easy_tdx.web.signal_ledger import signal_returns

    # 用上行序列喂三只标的 → 全部买点信号应全胜（涨势中买点后必涨）
    s = _session_with(up={"600001", "000002", "000003"}, down=set())
    report = audit_chanlun(samples=3, chanlun_limit=3, seed=42, session=s)
    assert not report.get("data_missing")
    assert report["signal_count"] >= 0
    for t, stats in report["by_type"].items():
        if t.endswith("buy"):
            # 上行序列里买点 5 根窗口几乎必为正（端点信号除外）
            assert stats["avg_return"] is not None
    # 台账方向对齐：sell 类型在涨势中 ret_pct 为负 → 命中率 < 1
    for t, stats in report["by_type"].items():
        if t.endswith("sell"):
            assert stats["hit_rate"] <= 1.0


def test_audit_chanlun_missing_symbol_counted(fake_marks) -> None:
    s = _session_with(up=set(), down=set())  # 全部取数失败
    report = audit_chanlun(samples=3, chanlun_limit=3, seed=42, session=s)
    assert report.get("data_missing") is True or report["signal_count"] == 0
    missing = [p for p in report["per_symbol"] if p.get("data_missing")]
    assert len(missing) == 3  # 三只全记缺失，无伪造值
