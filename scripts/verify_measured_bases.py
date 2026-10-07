#!/usr/bin/env python
"""从**缓存**独立复现 `MEASURED_BASES` 里登记的每个数值。

⚠️⚠️ 为什么要这个脚本：
   `audit_screen_sector_neutral.py` 里的 `MEASURED_BASES` 是**手抄**进去的
   （从审计脚本的控制台输出里 grep 出来的）。手抄的数字会漂——
   基准口径改了、样本换了、缓存重跑了，登记值不会自动更新，
   于是报告里印的数字和实际算出来的**对不上**，而**没人会发现**。

   本脚本**不复用** `audit_chanlun_screen_usefulness.py` 的函数，
   而是照着它的算法**重写一遍**，再逐个和登记值比。
   这样"算法改了"就会表现为"对不上"，而不是静默地继续印旧数字。

用法:
    .venv/bin/python scripts/verify_measured_bases.py
    .venv/bin/python scripts/verify_measured_bases.py --tol 0.02   # 放宽

退出码: 0 = 全部一致; 1 = 有对不上的; 2 = 数据/缓存缺失（**不假装通过**）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from math import erfc, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
H = 20

# ⚠️ 口径名 -> 缓存文件。**必须**是跑审计脚本时真实写出的路径。
#    基准口径统一为 `--benchmark index`（真实沪深300），
#    因为那是 audit_chanlun_screen_usefulness.py 的**默认值**。
BASES: list[tuple[str, str]] = [
    ("any_buy 基线",      "/tmp/u120_base_any_buy_any_any_false.json"),
    ("zs_position=above", "/tmp/u120_above_any_buy_any_above_false.json"),
    ("trend=up",          "/tmp/u120_tup_any_buy_up_any_false.json"),
    ("trend=down",        "/tmp/u120_tdown_any_buy_down_any_false.json"),
    ("has_beichi=true",   "/tmp/u120_bc_any_buy_any_any_true.json"),
    ("zs_position=below", "/tmp/u120_below_any_buy_any_below_false.json"),
    ("signal_type=1buy",  "/tmp/sig_1buy_1buy_any_any_any.json"),
    ("signal_type=2buy",  "/tmp/sig_2buy_2buy_any_any_any.json"),
    ("signal_type=3buy",  "/tmp/sig_3buy_3buy_any_any_any.json"),
    ("signal_type=1sell", "/tmp/sig_1sell_1sell_any_any_any.json"),
]

SCRIPT = ROOT / "scripts" / "audit_screen_sector_neutral.py"


def _index_closes(data: Path) -> np.ndarray | None:
    f = data / "sh000300_daily.json"
    if not f.exists():
        return None
    df = pd.DataFrame(json.loads(f.read_text(encoding="utf-8")))
    if not {"datetime", "close"} <= set(df.columns):
        return None
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df.sort_values("datetime")["close"].to_numpy(float)


def _recompute(cache: Path, ic: np.ndarray) -> tuple[float, float, float]:
    """照 `audit_chanlun_screen_usefulness._benchmark_by_t` + `_rel` 重算。"""
    res = json.loads(cache.read_text(encoding="utf-8"))
    mkt: dict[int, float] = {}
    for r in res:
        for t in list(r.get("hit_pts", [])) + list(r.get("miss_pts", [])):
            if t + H < len(ic):
                mkt[t] = float(ic[t + H] / ic[t] - 1)
    rh: list[float] = []
    rm: list[float] = []
    for r in res:
        for x, t in zip(r.get("hit", []), r.get("hit_pts", [])):
            if t in mkt:
                rh.append(x - mkt[t])
        for x, t in zip(r.get("miss", []), r.get("miss_pts", [])):
            if t in mkt:
                rm.append(x - mkt[t])
    a, b = np.array(rh), np.array(rm)
    d = float(a.mean() - b.mean())
    se = float(np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)))
    t = d / se if se > 0 else float("nan")
    return d, t, erfc(abs(t) / sqrt(2))


def _registered() -> dict[str, tuple[float, float, float]]:
    if not SCRIPT.exists():
        raise FileNotFoundError(
            f"缺同级脚本 {SCRIPT} —— 本脚本要从**它**里面读登记的 MEASURED_BASES。"
            f"请在**完整仓库**里运行。")
    src = SCRIPT.read_text(encoding="utf-8")
    if "MEASURED_BASES" not in src:
        return {}
    block = src[src.index("MEASURED_BASES"):]
    if "LEGACY_60_BASES" in block:
        block = block[: block.index("LEGACY_60_BASES")]
    return {
        m[0]: (float(m[1]), float(m[2]), float(m[3]))
        for m in re.findall(
            r'\("([^"]+)",\s*([+-][\d.]+),\s*([+-][\d.]+),\s*([\d.]+)\)', block)
    }


def _structural_check(reg: dict[str, tuple[float, float, float]]) -> list[str]:
    """不需要行情缓存的**结构自检**——这个可以进 CI。

    ⚠️ CI 上没有 /tmp 下的审计缓存（重跑 10 个口径要 ~2.5 小时），
       所以"数值复现"只能在本地/维护时跑。
       但**登记值本身**的自洽性可以无条件检查：
         - p 必须落在 (0, 1]
         - |t| 与 p 必须**互相自洽**（否则是手抄错的）
         - 口径数必须与 BASES 对得上（漏登记 ⇒ N 偏小 ⇒ 门槛放松）
    """
    problems: list[str] = []
    if len(reg) != len(BASES):
        problems.append(
            f"登记 {len(reg)} 个口径，但 BASES 列了 {len(BASES)} 个 "
            f"⇒ 可能漏登记（会让 Bonferroni 门槛被放松）")
    for label, (d, t, p) in reg.items():
        if not (0.0 < p <= 1.0):
            problems.append(f"{label}: p={p} 不在 (0,1]")
        # |t|=1.96 ⇒ p≈0.05；|t|=2.576 ⇒ p≈0.01。用单调性粗校：
        implied = erfc(abs(t) / sqrt(2))
        if abs(implied - p) > 0.02:
            problems.append(
                f"{label}: t={t} 对应的 p 应≈{implied:.4f}，"
                f"但登记的是 {p:.4f} ⇒ t 与 p **不自洽**（手抄错的迹象）")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol", type=float, default=0.005,
                    help="差值容差（超额用百分点，t/p 用绝对值）")
    ap.add_argument("--data", default=str(ROOT / "audit_data"))
    ap.add_argument("--structural-only", action="store_true",
                    help="只做登记值自洽性检查（不需要行情缓存，CI 用）")
    args = ap.parse_args()

    try:
        reg = _registered()
    except FileNotFoundError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2
    if not reg:
        print("❌ 脚本里没解析到 MEASURED_BASES", file=sys.stderr)
        return 2

    problems = _structural_check(reg)
    if args.structural_only:
        if problems:
            print("❌ 登记值结构自检**未通过**：")
            for x in problems:
                print(f"   - {x}")
            return 1
        print(f"✅ {len(reg)} 个登记口径结构自洽"
              f"（p∈(0,1]、t 与 p 互相自洽、口径数一致）")
        return 0

    data = Path(args.data)
    ic = _index_closes(data)
    if ic is None:
        print(f"❌ 缺指数基准 {data/'sh000300_daily.json'}，无法复现", file=sys.stderr)
        return 2
    try:
        reg = _registered()
    except FileNotFoundError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 2
    if not reg:
        print("❌ 脚本里没解析到 MEASURED_BASES", file=sys.stderr)
        return 2

    missing = [p for _, p in BASES if not Path(p).exists()]
    if missing:
        print(f"❌ 缺 {len(missing)} 份缓存：{missing[:3]} …", file=sys.stderr)
        print("   先跑 scripts/audit_chanlun_screen_usefulness.py", file=sys.stderr)
        return 2

    print(f"{'口径':<20}{'重算%':>8}{'登记%':>8}{'重算t':>8}{'登记t':>7}"
          f"{'重算p':>8}{'登记p':>8}  判定")
    bad = 0
    for label, path in BASES:
        d, t, p = _recompute(Path(path), ic)
        if label not in reg:
            print(f"{label:<20} ⚠️ 未登记")
            bad += 1
            continue
        rd, rt, rp = reg[label]
        ok = (abs(d * 100 - rd) <= args.tol
              and abs(t - rt) <= args.tol * 5
              and abs(p - rp) <= args.tol)
        bad += 0 if ok else 1
        print(f"{label:<20}{d*100:+8.2f}{rd:+8.2f}{t:+8.2f}{rt:+7.2f}"
              f"{p:8.4f}{rp:8.4f}  {'✅' if ok else '❌'}")

    n = len(BASES)
    print(f"\n⇒ {n-bad}/{n} 一致")
    if bad:
        print("⚠️ 登记值与缓存**对不上** ⇒ MEASURED_BASES 已漂移，"
              "报告里印的数字不可信。")
        return 1
    print("✅ 登记值**可从缓存独立复现**（基准=真实沪深300，H=20）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
