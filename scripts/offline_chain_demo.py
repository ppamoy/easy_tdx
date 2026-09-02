#!/usr/bin/env python3
"""V366: 离线 V102 建议链路端到端联调演示（无需网络/通达信）。

用合成日线生成临时 .day 文件，依次调用：
  1. offline advice --file    （单标建议回放）
  2. offline advice-batch --dir（批量建议实证）
  3. offline watch --dir --out （信号监控 + JSONL 落盘）
验证六级链路（V351-V365）在无网络环境可完整衔接。

运行：
    cd /home/skp/workspace/easy_tdx
    source .venv/bin/activate
    python scripts/offline_chain_demo.py
"""

from __future__ import annotations

import math
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _synthetic_bars(n: int = 120, seed: int = 7, base: float = 50.0) -> list[dict]:
    """构造一段震荡上行的合成日线（与 validate_v102_advice 同风格）。"""
    rng = random.Random(seed)
    bars: list[dict] = []
    price = base
    for i in range(n):
        drift = 0.12 if i >= n // 3 else 0.0
        wave = 0.6 * math.sin(i / 6.0)
        price = max(1.0, price + drift + wave * 0.12 + rng.uniform(-0.2, 0.2))
        o = price - 0.1
        c = price
        h = max(o, c) + abs(0.9 * math.sin(i / 5.0)) + 0.2
        lo = min(o, c) - abs(0.9 * math.cos(i / 5.0)) - 0.2
        bars.append(
            {
                "year": 2023 + i // 250,
                "month": 1 + (i % 250) // 21,
                "day": 1 + (i % 250) % 21,
                "open": round(o, 3),
                "close": round(c, 3),
                "high": round(h, 3),
                "low": round(lo, 3),
                "vol": 1_000_000.0,
                "amount": 1_000_000.0 * c,
            }
        )
    return bars


def _write_day_file(path: Path, bars: list[dict]) -> None:
    from easy_tdx.models.bar import SecurityBar
    from easy_tdx.offline.write_daily import append_daily_bars

    sec_bars = [
        SecurityBar(
            open=b["open"],
            close=b["close"],
            high=b["high"],
            low=b["low"],
            vol=b["vol"],
            amount=b["amount"],
            year=b["year"],
            month=b["month"],
            day=b["day"],
            hour=0,
            minute=0,
        )
        for b in bars
    ]
    # price_coeff/vol_coeff：A 股日线 0.01 / 0.01
    append_daily_bars(path, sec_bars, 0.01, 0.01)


def _run(sub_args: list[str], cwd: Path) -> tuple[int, str]:
    """执行 easy-tdx 子命令并返回 (退出码, stdout 前 600 字)。"""
    exe = shutil.which("easy-tdx")
    if exe is None:
        return 1, "easy-tdx 不在 PATH（请先 pip install -e . 或激活 venv）"
    res = subprocess.run([exe, *sub_args], cwd=cwd, capture_output=True, text=True, timeout=180)
    out = (res.stdout or "") + (res.stderr or "")
    return res.returncode, out[:600].strip()


def main() -> int:
    print("=" * 64)
    print("离线 V102 建议链路端到端联调（V351-V365 六级）")
    print("=" * 64)

    workdir = Path(tempfile.mkdtemp(prefix="easy_tdx_chain_demo_"))
    try:
        # 1. 合成两个 .day 文件（sh600000 / sz000001）
        lday = workdir / "lday"
        lday.mkdir()
        bars_a = _synthetic_bars(150, seed=7)
        bars_b = _synthetic_bars(150, seed=11, base=30.0)
        _write_day_file(lday / "sh600000.day", bars_a)
        _write_day_file(lday / "sz000001.day", bars_b)
        print(f"\n1) 合成 .day 数据 -> {lday}")
        print(f"   sh600000.day: {len(bars_a)} 根 | sz000001.day: {len(bars_b)} 根")

        # 2. 单标建议回放（V351/V352/V364）
        print("\n2) offline advice --file（单标建议回放）")
        rc, out = _run(
            [
                "offline",
                "advice",
                "SH",
                "600000",
                "--file",
                str(lday / "sh600000.day"),
                "--output",
                "json",
            ],
            workdir,
        )
        print(f"   exit={rc}")
        print("   " + out.replace("\n", "\n  ") if out else "   (无输出)")
        if rc != 0:
            print("✗ 单标建议回放失败")
            return 1

        # 3. 批量建议实证（V353）
        print("\n3) offline advice-batch --dir（批量建议实证）")
        rc, out = _run(
            [
                "offline",
                "advice-batch",
                "--dir",
                str(lday),
                "--output",
                "json",
            ],
            workdir,
        )
        print(f"   exit={rc}")
        print("   " + out.replace("\n", "\n  ") if out else "   (无输出)")
        if rc != 0:
            print("✗ 批量建议实证失败")
            return 1

        # 4. 信号监控 + JSONL 落盘（V354/V358/V360/V365）
        state = workdir / "watch_state.json"
        jsonl = workdir / "signals.jsonl"
        print("\n4) offline watch --dir --out（信号监控 + JSONL 落盘）")
        rc, out = _run(
            [
                "offline",
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
            workdir,
        )
        print(f"   exit={rc}")
        print("   " + out.replace("\n", "\n  ") if out else "   (无输出)")
        if rc != 0:
            print("✗ 信号监控失败")
            return 1
        if jsonl.is_file():
            n = len(jsonl.read_text(encoding="utf-8").strip().splitlines())
            print(f"   JSONL 落盘: {jsonl}（{n} 行）")

        # 5. 汇总
        print("\n" + "=" * 64)
        print("✓ 离线链路六级全部衔接成功（无需网络）")
        print(f"  临时目录: {workdir}")
        print("=" * 64)
        return 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
