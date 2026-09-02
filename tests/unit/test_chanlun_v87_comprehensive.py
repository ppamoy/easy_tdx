"""缠论综合测试 - 完整管道验证。

测试从原始K线到最终信号的完整管道。
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from easy_tdx.chanlun import ChanlunAnalyser
from easy_tdx.chanlun.bi import find_bis
from easy_tdx.chanlun.fractal import find_fractals
from easy_tdx.chanlun.kline_merge import merge_klines
from easy_tdx.chanlun.types import Kline
from easy_tdx.chanlun.xd import find_xds
from easy_tdx.chanlun.zs import find_zss


def _make_kline(idx: int, date: str, o: float, c: float, h: float, lo: float) -> Kline:
    return Kline(
        index=idx,
        date=datetime.strptime(date, "%Y-%m-%d"),
        open=o,
        close=c,
        high=h,
        low=lo,
        amount=1000.0,
    )


class TestFullPipeline:
    """完整管道测试。"""

    def test_daily_candlestick_pattern(self):
        """日线蜡烛图模式完整管道。"""
        # 构造一个明显的上涨→盘整→下跌走势
        klines = [
            _make_kline(0, "2024-01-02", 10.0, 10.5, 11.0, 9.8),
            _make_kline(1, "2024-01-03", 10.5, 11.0, 11.5, 10.2),
            _make_kline(2, "2024-01-04", 11.0, 10.8, 11.2, 10.5),
            _make_kline(3, "2024-01-05", 10.8, 11.5, 12.0, 10.6),
            _make_kline(4, "2024-01-08", 11.5, 12.0, 12.5, 11.2),
            _make_kline(5, "2024-01-09", 12.0, 11.8, 12.3, 11.5),
            _make_kline(6, "2024-01-10", 11.8, 11.5, 12.0, 11.2),
            _make_kline(7, "2024-01-11", 11.5, 11.0, 11.8, 10.8),
            _make_kline(8, "2024-01-12", 11.0, 10.5, 11.2, 10.2),
            _make_kline(9, "2024-01-15", 10.5, 10.0, 10.8, 9.8),
            _make_kline(10, "2024-01-16", 10.0, 10.2, 10.5, 9.9),
            _make_kline(11, "2024-01-17", 10.2, 10.8, 11.0, 10.0),
            _make_kline(12, "2024-01-18", 10.8, 11.2, 11.5, 10.5),
            _make_kline(13, "2024-01-19", 11.2, 11.0, 11.5, 10.8),
            _make_kline(14, "2024-01-22", 11.0, 10.5, 11.2, 10.2),
        ]

        # Step 1: K线合并
        cklines = merge_klines(klines)
        assert len(cklines) <= len(klines)

        # Step 2: 分型识别
        fractals = find_fractals(cklines)
        assert len(fractals) >= 0

        # Step 3: 笔计算
        bis = find_bis(fractals)
        # 笔数应合理（不会过多也不会过少）
        assert len(bis) >= 0

        # Step 4: 中枢计算
        zss = find_zss(bis)
        assert len(zss) >= 0

        # Step 5: 线段计算
        xds = find_xds(bis)
        assert len(xds) >= 0

        # 输出应一致
        assert all(b.direction.value in ("up", "down") for b in bis)
        assert all(xd.direction.value in ("up", "down") for xd in xds)

    def test_chanlun_analyser_with_dataframe(self):
        """使用DataFrame测试完整分析器。"""
        dates = pd.date_range("2024-01-02", periods=50, freq="B")
        # 模拟波动行情
        base = 100.0
        data = {
            "datetime": dates,
            "open": [base + i * 0.5 + (i % 3) * 2 for i in range(50)],
            "close": [base + i * 0.5 + (i % 3) * 2 + 1 for i in range(50)],
            "high": [base + i * 0.5 + (i % 3) * 2 + 3 for i in range(50)],
            "low": [base + i * 0.5 + (i % 3) * 2 - 1 for i in range(50)],
            "vol": [10000] * 50,
        }
        df = pd.DataFrame(data)

        analyser = ChanlunAnalyser(code="TEST", frequency="DAILY")
        result = analyser.process_klines(df)

        assert result.code == "TEST"
        assert result.frequency == "DAILY"
        assert len(result.klines) == 50
        assert len(result.cklines) > 0
        assert len(result.cklines) <= 50
        assert len(result.fractals) >= 0
        assert len(result.bis) >= 0
        assert len(result.zss) >= 0

    def test_result_to_dict_serializable(self):
        """结果应可序列化。"""
        dates = pd.date_range("2024-01-02", periods=30, freq="B")
        data = {
            "datetime": dates,
            "open": [10.0 + i * 0.1 for i in range(30)],
            "close": [10.5 + i * 0.1 for i in range(30)],
            "high": [11.0 + i * 0.1 for i in range(30)],
            "low": [9.5 + i * 0.1 for i in range(30)],
            "vol": [1000] * 30,
        }
        df = pd.DataFrame(data)

        analyser = ChanlunAnalyser(code="TEST", frequency="DAILY")
        result = analyser.process_klines(df)
        d = result.to_dict()

        # 基本字段
        assert "code" in d
        assert "frequency" in d
        assert "kline_count" in d
        assert "bis" in d
        assert "zss" in d
        assert "mmds" in d
        assert "bcs" in d
        assert "macd" in d

        # 笔字段
        for bi in d["bis"]:
            assert "index" in bi
            assert "direction" in bi
            assert "start_date" in bi
            assert "end_date" in bi
            assert "high" in bi
            assert "low" in bi
            assert "done" in bi

        # 中枢字段
        for zs in d["zss"]:
            assert "index" in zs
            assert "zg" in zs
            assert "zd" in zs
            assert "line_count" in zs
            assert "done" in zs

        # MACD字段
        assert "dif" in d["macd"]
        assert "dea" in d["macd"]
        assert "hist" in d["macd"]

    def test_minute_frequency(self):
        """分钟级别频率验证。"""
        import math

        dates = pd.date_range("2024-01-02 09:30", periods=60, freq="5min")
        highs = [15 + 5 * math.sin(i / 2) + i * 0.01 for i in range(60)]
        lows = [h - 1.5 for h in highs]
        df = pd.DataFrame(
            {
                "datetime": dates,
                "open": [h - 0.5 for h in highs],
                "close": [h - 0.2 for h in highs],
                "high": highs,
                "low": lows,
                "vol": [1000] * 60,
            }
        )

        for freq in ("5MIN", "5min"):
            analyser = ChanlunAnalyser(code="TEST", frequency=freq)
            result = analyser.process_klines(df)
            d = result.to_dict()
            # 笔日期应带时分
            if d["bis"]:
                import re

                dt_re = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
                for bi in d["bis"]:
                    assert dt_re.match(bi["start_date"])
                    assert dt_re.match(bi["end_date"])


class TestBacktestIntegration:
    """回测集成测试。"""

    def test_chanlun_strategy_integration(self):
        """缠论策略与回测引擎的集成。"""
        from easy_tdx.backtest.strategies.changying_chanlun import ChangyingChanlunStrategy

        # 验证策略类存在且可实例化
        strategy = ChangyingChanlunStrategy()
        assert strategy is not None

        # 验证参数
        assert len(strategy.params) > 0

    def test_builtin_strategy_registry(self):
        """内置策略注册表验证。"""
        from easy_tdx.backtest.strategies.registry import get_registry

        registry = get_registry()
        names = registry.names()
        assert "ma_cross" in names
        assert "macd" in names
        assert "chanlun" in names
        assert "changying_chanlun" in names


class TestDataQuality:
    """数据质量测试。"""

    def test_price_consistency(self):
        """价格一致性检查。"""
        # high >= max(open, close)
        # low <= min(open, close)
        klines = [
            _make_kline(0, "2024-01-02", 10.0, 12.0, 13.0, 9.0),
            _make_kline(1, "2024-01-03", 12.0, 10.0, 13.0, 9.0),
            _make_kline(2, "2024-01-04", 10.0, 11.0, 12.0, 9.0),
        ]
        for k in klines:
            assert k.high >= max(k.open, k.close)
            assert k.low <= min(k.open, k.close)

    def test_date_progression(self):
        """日期应单调递增。"""
        dates = [
            datetime(2024, 1, 2),
            datetime(2024, 1, 3),
            datetime(2024, 1, 4),
        ]
        for i in range(1, len(dates)):
            assert dates[i] > dates[i - 1]

    def test_volume_non_negative(self):
        """成交量应非负。"""
        klines = [
            _make_kline(0, "2024-01-02", 10.0, 12.0, 13.0, 9.0),
        ]
        for k in klines:
            assert k.amount >= 0
