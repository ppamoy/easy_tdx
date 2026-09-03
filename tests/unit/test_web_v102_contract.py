"""V382: Web 层 V102 字段契约回归。

Web 是 V102 决策支持的主消费面，chanlun/monitor/screening 三个 router
暴露 v102_* 字段（诊断页另有 advice-simulate 全链路测试），但此前无
「序列化字段契约」测试——若字段遗漏，前端 V102 卡片/徽章会静默空白。
本文件直接契约三类序列化源：
1. ChanlunResult.to_dict()（chanlun/analyze 的 mmds 来源，V327/V102 收尾）
2. SignalMonitor.check_signals（monitor 新信号手工构造，V328）
3. screening._get_latest_mmd（选股候选手工构造，V332）
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd


def _kline_df(n: int = 120, base: float = 100.0) -> pd.DataFrame:
    """构造 120 根日线 DataFrame（供 monitor check_signals 使用）。"""
    closes = [base] * n
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": closes,
            "close": closes,
            "high": [base + 1.0] * n,
            "low": [base - 1.0] * n,
            "vol": [1e6] * n,
        }
    )


# ── 1. ChanlunResult.to_dict()（chanlun/analyze 的 mmds 契约） ──


def test_chanlun_result_to_dict_includes_v102_fields() -> None:
    """V382: to_dict 的 mmds 完整携带 V102 四字段（多信号/质量卡/决策支持/模式匹配）。"""
    from easy_tdx.chanlun.analyser import ChanlunResult
    from easy_tdx.chanlun.types import MMD, MMDType

    mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
    mmd.confidence = 0.8
    mmd._multi_signal_correlation = {"dense": False, "count": 1}
    mmd._signal_quality_scorecard = {"overall_grade": "A", "score": 85}
    mmd._decision_support = {
        "action_recommendation": "买入",
        "entry_price": 10.5,
        "stop_loss": 9.8,
    }
    mmd._historical_pattern_match = {"win_rate": 0.7, "samples": 20}

    result = ChanlunResult(frequency="daily", mmds=[mmd])
    d = result.to_dict()

    item = d["mmds"][0]
    assert item["type"] == "3buy"
    assert item["v102_multi_signal_correlation"] == {"dense": False, "count": 1}
    assert item["v102_signal_quality"]["overall_grade"] == "A"
    assert item["v102_decision_support"]["action_recommendation"] == "买入"
    assert item["v102_pattern_match"]["win_rate"] == 0.7


def test_chanlun_result_to_dict_missing_v102_is_none() -> None:
    """V382: 无 V102 字段的普通 MMD 序列化四字段为 None（getattr 默认安全）。"""
    from easy_tdx.chanlun.analyser import ChanlunResult
    from easy_tdx.chanlun.types import MMD, MMDType

    mmd = MMD(mmd_type=MMDType.SELL_3, msg="3卖")
    mmd.confidence = 0.6

    result = ChanlunResult(frequency="daily", mmds=[mmd])
    item = result.to_dict()["mmds"][0]
    assert item["v102_multi_signal_correlation"] is None
    assert item["v102_signal_quality"] is None
    assert item["v102_decision_support"] is None
    assert item["v102_pattern_match"] is None


# ── 2. SignalMonitor.check_signals（monitor 新信号契约，V328） ──


async def test_monitor_new_signal_includes_v102_fields() -> None:
    """V382: monitor 新信号携带 V102 三字段（质量卡/决策支持/模式匹配）。"""
    from easy_tdx.web.routers.monitor import MonitorTask, SignalMonitor

    mmd = MagicMock()
    mmd.confidence = 0.9
    mmd.mmd_type.value = "3buy"
    mmd.msg = "3买信号"
    mmd._signal_quality_scorecard = {"overall_grade": "A"}
    mmd._decision_support = {"action_recommendation": "买入"}
    mmd._historical_pattern_match = {"win_rate": 0.7}

    result = MagicMock()
    result.mmds = [mmd]
    result._fmt_dt = MagicMock(return_value="2024-05-01")

    client = AsyncMock()
    client.get_security_bars = AsyncMock(return_value=_kline_df())

    with patch("easy_tdx.chanlun.ChanlunAnalyser") as mock_analyser:
        mock_analyser.return_value.process_klines.return_value = result

        mgr = SignalMonitor()
        mgr._tasks["t1"] = MonitorTask(
            task_id="t1",
            stocks=[{"market": "SZ", "code": "000001"}],
            category="DAY",
            confidence_threshold=0.5,
        )
        signals = await mgr.check_signals("t1", client)

    assert len(signals) == 1
    s = signals[0]
    assert s["stock"] == "SZ000001"
    assert s["type"] == "3buy"
    assert s["v102_signal_quality"]["overall_grade"] == "A"
    assert s["v102_decision_support"]["action_recommendation"] == "买入"
    assert s["v102_pattern_match"]["win_rate"] == 0.7


async def test_monitor_new_signal_low_confidence_skipped() -> None:
    """V382: 置信度低于阈值的新信号被过滤（不产生 v102 字段断言的前提）。"""
    from easy_tdx.web.routers.monitor import MonitorTask, SignalMonitor

    mmd = MagicMock()
    mmd.confidence = 0.3  # < threshold 0.5
    mmd.mmd_type.value = "3buy"

    result = MagicMock()
    result.mmds = [mmd]
    result._fmt_dt = MagicMock(return_value="2024-05-01")

    client = AsyncMock()
    client.get_security_bars = AsyncMock(return_value=_kline_df())

    with patch("easy_tdx.chanlun.ChanlunAnalyser") as mock_analyser:
        mock_analyser.return_value.process_klines.return_value = result

        mgr = SignalMonitor()
        mgr._tasks["t1"] = MonitorTask(
            task_id="t1",
            stocks=[{"market": "SZ", "code": "000001"}],
            category="DAY",
            confidence_threshold=0.5,
        )
        signals = await mgr.check_signals("t1", client)

    assert signals == []


# ── 3. screening._get_latest_mmd（选股候选契约，V332） ──


def test_screening_get_latest_mmd_includes_v102_fields() -> None:
    """V382: 选股候选 latest_mmd 携带 V102 三字段。"""
    from easy_tdx.web.routers.screening import _get_latest_mmd

    other = MagicMock()
    other.bi.index = 2
    other.mmd_type.value = "1buy"

    latest = MagicMock()
    latest.bi.index = 5
    latest.mmd_type.value = "3buy"
    latest.bi.end.k.date = pd.Timestamp("2024-05-01")
    latest.bi.low = 10.0
    latest.bi.high = 11.0
    latest._signal_quality_scorecard = {"overall_grade": "A"}
    latest._decision_support = {"action_recommendation": "买入"}
    latest._historical_pattern_match = {"win_rate": 0.7}

    result = MagicMock()
    result.mmds = [other, latest]

    item = _get_latest_mmd(result)
    assert item is not None
    assert item["type"] == "3buy"
    assert item["v102_signal_quality"]["overall_grade"] == "A"
    assert item["v102_decision_support"]["action_recommendation"] == "买入"
    assert item["v102_pattern_match"]["win_rate"] == 0.7


def test_screening_get_latest_mmd_empty_returns_none() -> None:
    """V382: 无买卖点时不产生 latest_mmd（返回 None）。"""
    from easy_tdx.web.routers.screening import _get_latest_mmd

    result = MagicMock()
    result.mmds = []
    assert _get_latest_mmd(result) is None
