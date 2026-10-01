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


# ── 4. build_train_session_payload（训练教学候选点契约，V344） ──


class _TrainFakeResult:
    """build_train_session_payload 所需的鸭子类型结果对象（可控序列化）。"""

    def __init__(
        self,
        mmds: list,
        code: str = "SZ000001",
        klines: list | None = None,
        fractals: list | None = None,
    ) -> None:
        self.code = code
        self.frequency = "daily"
        self.mmds = mmds
        self.klines = klines or []
        self.fractals = fractals or []
        self.boll = None
        self._date = "2024-05-01"
        self._to_dict: dict = {"bis": [], "xds": [], "zss": [], "bcs": [], "boll": None, "macd": {}}

    def _fmt_dt(self, dt: object) -> str:
        return self._date

    def _fx_anchor_datetime(self, fx: object) -> str:
        return self._date

    def to_dict(self) -> dict:
        return self._to_dict

    def valid_fractals_to_dict(self) -> list:
        """与 ChanlunAnalyser.valid_fractals_to_dict 对齐的 mock。"""
        return self.fractals


def _train_df(n: int = 40) -> pd.DataFrame:
    closes = [100.0] * n
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": closes,
            "close": closes,
            "high": [101.0] * n,
            "low": [99.0] * n,
            "vol": [1e6] * n,
            "amount": [1e8] * n,
        }
    )


def _v102_mmd_with_bi(mmd_maker, mmd_type: str) -> object:
    mmd = mmd_maker(mmd_type, idx=10)
    mmd._signal_quality_scorecard = {"overall_grade": "A"}
    mmd._decision_support = {"action_recommendation": "买入"}
    mmd._historical_pattern_match = {"win_rate": 0.7}
    return mmd


def _attach_bi(mmd: object, index: int = 10) -> None:
    mmd.bi = MagicMock()
    mmd.bi.index = index
    mmd.bi.end = MagicMock()
    mmd.bi.end.k = MagicMock()
    mmd.bi.end.k.k_index = index
    mmd.bi.end.k.date = pd.Timestamp("2024-05-01")


def test_train_candidates_include_v102_grade_advice() -> None:
    """V383: 训练教学候选点携带 v102_grade / v102_advice（V344 卡片数据源）。"""
    from easy_tdx.chanlun.types import MMD, MMDType
    from easy_tdx.web.routers.chanlun import build_train_session_payload

    mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
    mmd.confidence = 0.8
    mmd._signal_quality_scorecard = {"overall_grade": "A"}
    mmd._decision_support = {"action_recommendation": "买入"}
    _attach_bi(mmd)

    payload = build_train_session_payload(_TrainFakeResult([mmd]), _train_df(), "DAY")

    cands = [c for c in payload["candidates"] if c["kind"] == "mmd"]
    assert len(cands) == 1
    sig = cands[0]["signal"]
    assert sig["type"] == "3buy"
    assert sig["v102_grade"] == "A"
    assert sig["v102_advice"] == "买入"


def test_train_candidates_missing_v102_is_none() -> None:
    """V383: 无 V102 数据的候选点 v102_grade/v102_advice 为 None。"""
    from easy_tdx.chanlun.types import MMD, MMDType
    from easy_tdx.web.routers.chanlun import build_train_session_payload

    mmd = MMD(mmd_type=MMDType.SELL_3, msg="3卖")
    mmd.confidence = 0.6
    _attach_bi(mmd)

    payload = build_train_session_payload(_TrainFakeResult([mmd]), _train_df(), "DAY")

    cands = [c for c in payload["candidates"] if c["kind"] == "mmd"]
    assert len(cands) == 1
    sig = cands[0]["signal"]
    assert sig["v102_grade"] is None
    assert sig["v102_advice"] is None


# ── 5. diagnose_stock（诊断页 latest_mmd / recent_signals 契约） ──


async def test_diagnose_stock_includes_v102_fields() -> None:
    """V383: 诊断页 latest_mmd 与 recent_signals 携带 V102 四字段。"""
    from easy_tdx.chanlun.analyser import ChanlunResult
    from easy_tdx.chanlun.types import MMD, MMDType
    from easy_tdx.web.routers.diagnosis import diagnose_stock
    from easy_tdx.web.schemas import StockIdentifier

    mmd = MMD(mmd_type=MMDType.BUY_3, msg="3买")
    mmd.confidence = 0.8
    mmd._multi_signal_correlation = {"dense": False}
    mmd._signal_quality_scorecard = {"overall_grade": "A"}
    mmd._decision_support = {"action_recommendation": "买入"}
    mmd._historical_pattern_match = {"win_rate": 0.7}
    _attach_bi(mmd)

    result = ChanlunResult(frequency="daily", mmds=[mmd])
    result._fmt_dt = MagicMock(return_value="2024-05-01")  # type: ignore[method-assign]

    def _fake_anchor(fx: object) -> object:
        return pd.Timestamp("2024-05-01")

    result._fx_anchor_datetime = _fake_anchor  # type: ignore[method-assign]

    with (
        patch("easy_tdx.web.routers.diagnosis.get_client") as mock_get_client,
        patch("easy_tdx.chanlun.ChanlunAnalyser") as mock_analyser,
        patch(
            "easy_tdx.chanlun.mmd.calc_signal_quality_report",
            return_value={"grade": "A", "score": 85},
        ),
    ):
        mock_client = AsyncMock()
        mock_client.get_security_bars = AsyncMock(return_value=_kline_df())
        mock_get_client.return_value = mock_client
        mock_analyser.return_value.process_klines.return_value = result

        req = StockIdentifier(market="SZ", code="000001")
        resp = await diagnose_stock(req, mock_client, mac_client=None)

    assert "error" not in resp
    chan = resp["chanlun"]
    lm = chan["latest_mmd"]
    assert lm["v102_signal_quality"]["overall_grade"] == "A"
    assert lm["v102_decision_support"]["action_recommendation"] == "买入"
    assert lm["v102_pattern_match"]["win_rate"] == 0.7
    assert lm["v102_multi_signal_correlation"] == {"dense": False}

    recent = [s for s in chan.get("recent_signals", []) if s["type"] == "3buy"]
    assert recent, "recent_signals 应包含 3buy"
    r = recent[0]
    assert r["v102_signal_quality"]["overall_grade"] == "A"
    assert r["v102_decision_support"]["action_recommendation"] == "买入"
    assert r["v102_pattern_match"]["win_rate"] == 0.7
    assert r["v102_multi_signal_correlation"] == {"dense": False}
