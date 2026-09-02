"""V366/V367: 离线 V102 建议链路端到端运行时回归。

用合成 .day 文件（append_daily_bars 生成）通过 CliRunner 依次调用
offline advice --file / advice-batch --dir / watch --dir --out，
把 V366 联调抓出的 3 类运行时 bug 固化为 pytest 回归：
1. 函数体内使用 pd.DataFrame 但缺 pandas 局部导入（NameError）
2. advice 把 dict 传入只接受 DataFrame 的 print_output（AttributeError）
3. advice-batch 空建议报告读取缺失的 stop_rate/tp_rate/expire_rate（KeyError）
"""

from __future__ import annotations

import math
import random
from pathlib import Path
from unittest.mock import MagicMock

from click.testing import CliRunner

from easy_tdx.cli.cmd_offline import _watch_signal_row, offline
from easy_tdx.models.bar import SecurityBar
from easy_tdx.offline.write_daily import append_daily_bars


def _synthetic_bars(n: int = 150, seed: int = 7, base: float = 50.0) -> list[SecurityBar]:
    """构造一段震荡上行的合成日线（与 scripts/offline_chain_demo.py 同风格）。"""
    rng = random.Random(seed)
    bars: list[SecurityBar] = []
    price = base
    for i in range(n):
        drift = 0.12 if i >= n // 3 else 0.0
        wave = 0.6 * math.sin(i / 6.0)
        price = max(1.0, price + drift + wave * 0.12 + rng.uniform(-0.2, 0.2))
        bars.append(
            SecurityBar(
                open=round(price - 0.1, 3),
                close=round(price, 3),
                high=round(price + 0.4, 3),
                low=round(price - 0.4, 3),
                vol=1_000_000.0,
                amount=1_000_000.0 * price,
                year=2023 + i // 250,
                month=1 + (i % 250) // 21,
                day=1 + (i % 250) % 21,
                hour=0,
                minute=0,
            )
        )
    return bars


def _make_lday(tmp_path: Path) -> tuple[Path, Path]:
    """生成两个合成 .day 文件，返回 (lday 目录, 第一只文件路径)。"""
    lday = tmp_path / "lday"
    lday.mkdir()
    day_a = lday / "sh600000.day"
    day_b = lday / "sz000001.day"
    append_daily_bars(day_a, _synthetic_bars(150, seed=7), 0.01, 0.01)
    append_daily_bars(day_b, _synthetic_bars(150, seed=11, base=30.0), 0.01, 0.01)
    return lday, day_a


def test_offline_advice_file_runs(tmp_path: Path) -> None:
    """V366: offline advice --file 运行时不再 NameError（pandas 导入修复）。"""
    _lday, day_a = _make_lday(tmp_path)
    runner = CliRunner()
    res = runner.invoke(
        offline,
        ["advice", "SH", "600000", "--file", str(day_a), "--output", "json"],
    )
    assert res.exit_code == 0, res.output
    assert '"bars": 150' in res.output  # JSON 输出含 K 线数


def test_offline_advice_batch_runs(tmp_path: Path) -> None:
    """V366: advice-batch --dir 运行时无 KeyError（空建议报告字段缺失防护）。"""
    lday, _ = _make_lday(tmp_path)
    runner = CliRunner()
    res = runner.invoke(
        offline,
        ["advice-batch", "--dir", str(lday), "--output", "json"],
    )
    assert res.exit_code == 0, res.output
    # 两只标的都不应出现 error 行（此前空建议报告会 KeyError: 'stop_rate'）
    assert '"error"' not in res.output
    assert '"symbol":"SH600000"' in res.output
    assert '"symbol":"SZ000001"' in res.output


def test_offline_watch_with_out_runs(tmp_path: Path) -> None:
    """V365/V366: watch --dir --out 运行时正常，状态文件被写回。"""
    lday, _ = _make_lday(tmp_path)
    state = tmp_path / "watch_state.json"
    jsonl = tmp_path / "signals.jsonl"
    runner = CliRunner()
    res = runner.invoke(
        offline,
        [
            "watch",
            "--dir",
            str(lday),
            "--state",
            str(state),
            "--out",
            str(jsonl),
            "--output",
            "json",
        ],
    )
    assert res.exit_code == 0, res.output
    # 状态文件必然写回；JSONL 仅在发现新信号时创建（合成数据无 3买/3卖 属预期）
    assert state.is_file()


def test_watch_signal_row_includes_advice_fields():
    """V368: watch 新信号 JSONL 行含 V102 建议的入场/止损/止盈字段。"""
    mmd = MagicMock()
    mmd.mmd_type.value = "3buy"
    mmd.confidence = 0.72
    mmd._signal_quality_scorecard = {"overall_grade": "A"}
    mmd._decision_support = {
        "action_recommendation": "买入",
        "entry_price": 10.5,
        "stop_loss": 9.8,
        "take_profit_1": 11.6,
    }
    row = _watch_signal_row("SH600000", mmd, "2024-03-15")
    assert row["symbol"] == "SH600000"
    assert row["type"] == "3buy"
    assert row["date"] == "2024-03-15"
    assert row["v102_grade"] == "A"
    assert row["advice"] == "买入"
    assert row["entry_price"] == 10.5
    assert row["stop_loss"] == 9.8
    assert row["take_profit_1"] == 11.6


def test_watch_signal_row_missing_decision_is_null():
    """V368: 无决策支持数据时，入场/止损/止盈字段为 None（不崩溃）。"""
    mmd = MagicMock()
    mmd.mmd_type.value = "3sell"
    mmd.confidence = 0.6
    mmd._signal_quality_scorecard = None
    mmd._decision_support = None
    row = _watch_signal_row("SZ000001", mmd, "2024-03-15")
    assert row["entry_price"] is None
    assert row["stop_loss"] is None
    assert row["take_profit_1"] is None
    assert row["v102_grade"] is None
