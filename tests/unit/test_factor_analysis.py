# tests/unit/test_factor_analysis.py
"""Test FactorAnalyzer and FactorReport."""

from __future__ import annotations

import numpy as np
import pandas as pd

from easy_tdx.factor.analysis import FactorAnalyzer, FactorReport


def _make_factor_and_return(
    n_dates: int = 50,
    n_stocks: int = 20,
    seed: int = 42,
    ic: float = 0.05,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    rows_f, rows_r = [], []
    for d in range(n_dates):
        factor_vals = rng.normal(0, 1, n_stocks)
        noise = rng.normal(0, 1, n_stocks)
        returns = ic * factor_vals + (1 - ic) * noise
        for s in range(n_stocks):
            rows_f.append({"date": 20240101 + d, "code": f"{s:06d}", "test_factor": factor_vals[s]})
            rows_r.append({"date": 20240101 + d, "code": f"{s:06d}", "forward_5d": returns[s]})
    return pd.DataFrame(rows_f), pd.DataFrame(rows_r)


class TestFactorReport:
    def test_report_fields(self):
        report = FactorReport(
            name="test",
            ic_mean=0.05,
            ic_std=0.1,
            ir=0.5,
            ic_positive_rate=0.6,
            quantile_returns={"q1": -0.01, "q2": 0.0, "q3": 0.01, "q4": 0.02, "q5": 0.03},
            top_minus_bottom=0.04,
            turnover_rate=0.3,
            autocorr=0.8,
            ic_series=pd.Series([0.1, 0.05, -0.02]),
        )
        assert report.name == "test"
        assert report.ir == 0.5


class TestFactorAnalyzerIC:
    def test_invalid_n_quantiles_raises(self):
        """V531: n_quantiles < 2 应显式报错。"""
        import pytest

        fd, rd = _make_factor_and_return(ic=0.1)
        with pytest.raises(ValueError, match="n_quantiles"):
            FactorAnalyzer(fd, rd, factor_col="test_factor", return_col="forward_5d", n_quantiles=1)

    def test_compute_ic_returns_series(self):
        fd, rd = _make_factor_and_return(ic=0.1)
        analyzer = FactorAnalyzer(fd, rd, factor_col="test_factor", return_col="forward_5d")
        ic_series = analyzer.compute_ic()
        assert isinstance(ic_series, pd.Series)
        assert len(ic_series) == 50

    def test_positive_ic_detected(self):
        fd, rd = _make_factor_and_return(ic=0.3)
        analyzer = FactorAnalyzer(fd, rd, factor_col="test_factor", return_col="forward_5d")
        ic_series = analyzer.compute_ic()
        assert ic_series.mean() > 0.05

    def test_zero_ic_detected(self):
        fd, rd = _make_factor_and_return(ic=0.0)
        analyzer = FactorAnalyzer(fd, rd, factor_col="test_factor", return_col="forward_5d")
        ic_series = analyzer.compute_ic()
        assert abs(ic_series.mean()) < 0.15

    def test_compute_ic_unknown_method_raises(self):
        """V528: 拼写错误的方法名应显式报错，而非静默回退 pearson。"""
        import pytest

        fd, rd = _make_factor_and_return(ic=0.1)
        analyzer = FactorAnalyzer(fd, rd, factor_col="test_factor", return_col="forward_5d")
        with pytest.raises(ValueError, match="未知 IC 方法"):
            analyzer.compute_ic(method="kendall")


class TestFactorAnalyzerQuantile:
    def test_quantile_returns(self):
        fd, rd = _make_factor_and_return(ic=0.1)
        analyzer = FactorAnalyzer(fd, rd, factor_col="test_factor", return_col="forward_5d")
        qr = analyzer.compute_quantile_returns()
        assert isinstance(qr, pd.DataFrame)
        assert len(qr.columns) == 5

    def test_monotonic_with_positive_ic(self):
        fd, rd = _make_factor_and_return(ic=0.3)
        analyzer = FactorAnalyzer(fd, rd, factor_col="test_factor", return_col="forward_5d")
        qr = analyzer.compute_quantile_returns()
        means = qr.mean()
        assert means.iloc[-1] > means.iloc[0]


class TestFactorAnalyzerReport:
    def test_full_report(self):
        fd, rd = _make_factor_and_return(ic=0.1)
        analyzer = FactorAnalyzer(fd, rd, factor_col="test_factor", return_col="forward_5d")
        report = analyzer.full_report()
        assert isinstance(report, FactorReport)
        assert report.name == "test_factor"
        assert isinstance(report.ic_mean, float)
        assert len(report.quantile_returns) == 5
        assert "q1" in report.quantile_returns

    def test_report_ic_positive_rate(self):
        fd, rd = _make_factor_and_return(ic=0.3)
        analyzer = FactorAnalyzer(fd, rd, factor_col="test_factor", return_col="forward_5d")
        report = analyzer.full_report()
        assert report.ic_positive_rate > 0.5

    def test_ic_positive_rate_excludes_nan(self, monkeypatch):
        """V523: ic_positive_rate 只统计有效截面（NaN 截面不算「非正」）。"""
        fd, rd = _make_factor_and_return(ic=0.3)
        analyzer = FactorAnalyzer(fd, rd, factor_col="test_factor", return_col="forward_5d")
        # 模拟部分截面样本不足（IC=NaN）
        monkeypatch.setattr(
            analyzer, "compute_ic", lambda *a, **k: pd.Series([0.1, float("nan"), 0.2, 0.3])
        )
        report = analyzer.full_report()
        # 3 个有效截面全部为正 → 1.0（而非把 NaN 当非正算成 0.75）
        assert report.ic_positive_rate == 1.0

    def test_ic_std_single_valid(self, monkeypatch):
        """V536: 1 个有效截面 + N 个 NaN 时 ic_std 应为 0（而非 NaN）。"""
        fd, rd = _make_factor_and_return(ic=0.1)
        analyzer = FactorAnalyzer(fd, rd, factor_col="test_factor", return_col="forward_5d")
        monkeypatch.setattr(
            analyzer, "compute_ic", lambda *a, **k: pd.Series([0.1, float("nan"), float("nan")])
        )
        report = analyzer.full_report()
        assert report.ic_mean == 0.1
        assert report.ic_std == 0.0
        assert report.ir == 0.0

    def test_top_minus_bottom_uses_top_quantile(self):
        """V518: top_minus_bottom 用最高分位 q{n_quantiles}，而非硬编码 q5。"""
        fd, rd = _make_factor_and_return(n_dates=50, n_stocks=30, ic=0.2)
        analyzer = FactorAnalyzer(
            fd, rd, factor_col="test_factor", return_col="forward_5d", n_quantiles=10
        )
        report = analyzer.full_report()
        assert len(report.quantile_returns) == 10
        expected = report.quantile_returns["q10"] - report.quantile_returns["q1"]
        assert abs(report.top_minus_bottom - expected) < 1e-9

    def test_top_minus_bottom_dropped_quantile(self, monkeypatch):
        """V533: qcut 丢分位（q{n} 为 NaN）时顶底收益回退到实际最高分位。"""
        fd, rd = _make_factor_and_return(ic=0.2)
        analyzer = FactorAnalyzer(
            fd, rd, factor_col="test_factor", return_col="forward_5d", n_quantiles=5
        )
        # 模拟重复值导致 qcut 丢分位：q4/q5 全 NaN
        qr = pd.DataFrame(
            {
                "q1": [0.01, 0.01],
                "q2": [0.02, 0.02],
                "q3": [0.05, 0.05],
                "q4": [np.nan, np.nan],
                "q5": [np.nan, np.nan],
            }
        )
        monkeypatch.setattr(analyzer, "compute_quantile_returns", lambda: qr)
        report = analyzer.full_report()
        # 顶底 = q3 - q1 = 0.05 - 0.01 = 0.04（跳过 NaN 的 q4/q5）
        assert abs(report.top_minus_bottom - 0.04) < 1e-9


class TestFactorAnalyzerDecay:
    def test_decay_returns_dataframe(self):
        fd, rd = _make_factor_and_return(ic=0.1)
        analyzer = FactorAnalyzer(fd, rd, factor_col="test_factor", return_col="forward_5d")
        decay = analyzer.compute_decay(max_lag=5)
        assert isinstance(decay, pd.DataFrame)
        assert len(decay) == 5


class TestFactorAnalyzerTurnover:
    def test_turnover_in_range(self):
        fd, rd = _make_factor_and_return(ic=0.1)
        analyzer = FactorAnalyzer(fd, rd, factor_col="test_factor", return_col="forward_5d")
        to = analyzer.compute_turnover()
        assert 0 <= to <= 1
