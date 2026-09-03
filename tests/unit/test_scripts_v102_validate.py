"""V384: V102 实证脚本运行时回归。

validate_v102_advice.py（V321/V334/V346）与 advice_batch_validate.py（V325/V335）
是 V102 建议实证的关键脚本，但此前无任何 pytest 覆盖——主要输出分支
（默认终端报告 / --md Markdown 报告）若回归会静默影响文档引用与无行情验证。
两个脚本都用 importlib 加载并真实运行 main()，断言返回 0 与报告结构。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"


def _load_script(name: str):
    """按文件名加载 scripts/ 下的脚本模块。"""
    path = _SCRIPTS / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _kline_df(n: int = 120, base: float = 100.0) -> pd.DataFrame:
    """合成日线 DataFrame（供 advice_batch_validate 的 fake 客户端返回）。"""
    closes = [base] * n
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": closes,
            "close": closes,
            "high": [base + 1.0] * n,
            "low": [base - 1.0] * n,
            "vol": [1e6] * n,
            "amount": [1e8] * n,
        }
    )


def _synthetic_klines_df(n: int = 150) -> pd.DataFrame:
    """有波动的震荡上行行情（与 test_offline_chain 同风格，真实分析产生 3买/3卖）。"""
    import math
    import random

    rng = random.Random(7)
    price = 50.0
    rows = []
    for i in range(n):
        drift = 0.12 if i >= n // 3 else 0.0
        wave = 0.6 * math.sin(i / 6.0)
        price = max(1.0, price + drift + wave * 0.12 + rng.uniform(-0.2, 0.2))
        rows.append(
            {
                "date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=i),
                "open": round(price - 0.1, 3),
                "close": round(price, 3),
                "high": round(price + 0.4, 3),
                "low": round(price - 0.4, 3),
                "vol": 1_000_000.0,
                "amount": 1_000_000.0 * price,
            }
        )
    return pd.DataFrame(rows)


class _FakeBatchClient:
    """advice_batch_validate 的 MAC 客户端替身（get_stock_kline 返回合成 K 线）。"""

    def get_stock_kline(self, market: object, code: str, **kwargs: object) -> pd.DataFrame:
        return _synthetic_klines_df()


class _FakeBatchCtx:
    def __enter__(self) -> _FakeBatchClient:
        return _FakeBatchClient()

    def __exit__(self, *args: object) -> bool:
        return False


# ── validate_v102_advice（合成行情直接跑，无网络） ──


def test_validate_v102_advice_default_runs(monkeypatch, capsys) -> None:
    """V384: validate_v102_advice 默认模式返回 0，输出汇总与出场分布。"""
    mod = _load_script("validate_v102_advice.py")
    monkeypatch.setattr(sys, "argv", ["validate_v102_advice.py"])

    rc = mod.main()
    captured = capsys.readouterr()

    assert rc == 0
    assert "V102 决策支持建议执行实证" in captured.out
    assert "胜率" in captured.out
    assert "出场分布" in captured.out


def test_validate_v102_advice_md_runs(monkeypatch, capsys) -> None:
    """V384: --md 模式输出 Markdown 报告（标题/表格/汇总/出场分布）。"""
    mod = _load_script("validate_v102_advice.py")
    monkeypatch.setattr(sys, "argv", ["validate_v102_advice.py", "--md"])

    rc = mod.main()
    captured = capsys.readouterr()

    assert rc == 0
    assert "# V102 建议执行实证报告（合成行情回放）" in captured.out
    assert "| # | 入场 | 止损 | 止盈1 | 出场价 | 原因 | 收益% |" in captured.out
    assert "**汇总**" in captured.out
    assert "**出场分布**" in captured.out


# ── advice_batch_validate（patch 网络客户端 + 合成 K 线） ──


def test_advice_batch_validate_md_runs(monkeypatch, capsys) -> None:
    """V384: advice_batch_validate --md 返回 0，输出批量 Markdown 报告。"""
    mod = _load_script("advice_batch_validate.py")
    monkeypatch.setattr(sys, "argv", ["advice_batch_validate.py", "--md", "SZ", "000001"])

    with patch("easy_tdx.cli.conn.get_mac_client", return_value=_FakeBatchCtx()):
        rc = mod.main()
    captured = capsys.readouterr()

    assert rc == 0
    assert "# V102 批量建议实证报告" in captured.out
    assert "扫描标的" in captured.out  # 合成行情可能无 3买/3卖 → 无建议提示（脚本正常行为）
