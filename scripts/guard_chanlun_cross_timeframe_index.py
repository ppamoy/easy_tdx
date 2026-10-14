#!/usr/bin/env python3
"""跨周期索引口径守门（V851，AGENTS.md §7 沉淀）。

## 守的规则

`process_klines_cross_timeframe` 用**次级别线段**构中枢，
`find_zss(lower_xds)` 产出的 `ZS.lines[*].index` 是**次级别线段序号**。
`mmd.py` 有 9 处把它当**日线笔下标**用：

    mmd.py:2874   next_first_bi_idx_map[z.index] = z2.lines[0].index
    mmd.py:2891   superseded_at = next_first_bi_idx_map.get(zs.index)
    mmd.py:2928   last_idx = zs.lines[-1].index
    mmd.py:3125   retest_bi = bis[last_idx + 1]
    mmd.py:3148/3477   if bi.index >= (zs.lines[-1].index ...)
    mmd.py:3124/3356/3686  _calc_bi_force(..., zs.lines[0].index)

如果谁把 `_remap_cross_zs_indices` 删掉/改坏，`bis[zs.lines[-1].index]`
会重新指向时间上相差数千天的笔。本脚本量化这个错位并 fail。

## 判据

对每个中枢末段 L：`|end(L) - end(bis[L.index])|` 的**最大日期差**
必须 <= MAX_DELTA_DAYS（默认 90 天）。

- 修复后实测：3–46 天（14 只标的）
- 修复前实测：3901–4382 天

## 牙齿验证（已做，2026-10-14）

    # 好样本：当前代码 → exit 0（14/14 通过，最大 46 天）
    .venv/bin/python scripts/guard_chanlun_cross_timeframe_index.py --limit 14

    # 坏样本：把 `if line.index != target:` 改成 `if False and ...`
    #         （让 _remap_cross_zs_indices 退化为 no-op）
    # → exit 1，日期差回到 3901–4382 天
    sed 's/            if line.index != target:/            if False and line.index != target:/' \
      src/easy_tdx/chanlun/analyser.py > /tmp/bad_analyser.py
    # 实测输出：
    #   sh000001 最大日期差= 4345 天 ❌
    #   sh000300 最大日期差= 4382 天 ❌
    #   sh600000 最大日期差= 4054 天 ❌

⇒ 脚本真的在读 index、真的在比日期，不是恒定 exit 0。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402

DAILY_DIR = ROOT / "audit_data"
LOWER_DIR = ROOT / "audit_data" / "kline_30min"
MAX_DELTA_DAYS = 90


def _end_ts(o):
    k = getattr(getattr(o, "end", None), "k", None)
    ts = getattr(k, "date", None) if k is not None else None
    return pd.Timestamp(ts) if ts is not None else None


def check(code: str) -> tuple[int, int]:
    """返回 (最大日期差, 越界次数)。"""
    dp = DAILY_DIR / f"{code}_daily.json"
    lp = LOWER_DIR / f"{code}_30min.json"
    if not dp.exists() or not lp.exists():
        return -1, 0
    ddf = pd.DataFrame(json.loads(dp.read_text(encoding="utf-8")))
    ldf = pd.DataFrame(json.loads(lp.read_text(encoding="utf-8")))
    ddf["datetime"] = pd.to_datetime(ddf["datetime"])
    ldf["datetime"] = pd.to_datetime(ldf["datetime"])

    a = ChanlunAnalyser(config=ChanlunConfig())
    r = a.process_klines_cross_timeframe(ddf, ldf)
    bis = r.bis if hasattr(r, "bis") else []
    if not bis:
        return -1, 0

    worst = 0
    out_of_range = 0
    for zs in r.zss:
        if not zs.lines:
            continue
        last = zs.lines[-1]
        idx = last.index
        if idx < 0 or idx >= len(bis):
            out_of_range += 1
            continue
        a_ts, b_ts = _end_ts(last), _end_ts(bis[idx])
        if a_ts is None or b_ts is None:
            continue
        worst = max(worst, abs((a_ts - b_ts).days))
    return worst, out_of_range


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=14)
    args = ap.parse_args()

    codes = sorted({p.name.split("_")[0] for p in LOWER_DIR.glob("*.json")})
    if args.limit:
        codes = codes[: args.limit]

    print(f"跨周期索引口径守门 —— {len(codes)} 只标的，阈值 {MAX_DELTA_DAYS} 天\n", flush=True)
    worst_all = 0
    bad: list[str] = []
    oor_total = 0
    for code in codes:
        worst, oor = check(code)
        if worst < 0:
            continue
        oor_total += oor
        worst_all = max(worst_all, worst)
        flag = "❌" if worst > MAX_DELTA_DAYS or oor else "✅"
        if worst > MAX_DELTA_DAYS or oor:
            bad.append(code)
        print(f"  {code:<10} 最大日期差={worst:>5} 天  越界={oor}  {flag}", flush=True)

    print(f"\n全体最大日期差 = {worst_all} 天；越界总数 = {oor_total}", flush=True)
    if bad:
        print(f"\n❌ {len(bad)} 只标的索引口径错位：{', '.join(bad)}", flush=True)
        print("   检查 src/easy_tdx/chanlun/analyser.py 的 _remap_cross_zs_indices", flush=True)
        return 1
    print(f"\n✅ 全部标的索引口径正确（<= {MAX_DELTA_DAYS} 天，无越界）", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
