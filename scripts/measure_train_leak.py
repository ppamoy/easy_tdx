"""测量 build_train_session_payload 在各 reveal_limit 下的「未来信息」泄露量。

对每个顶层 key：
  - list[dict]：按已知索引字段（end_index / bar_index / start_index / anchor_bar_index）
    统计 index > reveal_limit 的条目数，并给出样例。
  - bars：len(bars) - (reveal_limit+1)
  - dict-of-list（macd/boll）：len(list) - (reveal_limit+1)
  - levels：递归下钻。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.web.routers.chanlun import build_train_session_payload

FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "chanlun_000333_daily.json"

IDX_FIELDS = ("end_index", "bar_index", "anchor_bar_index", "start_index")


def load():
    rows = json.loads(FIX.read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    res = ChanlunAnalyser(code="000333", frequency="daily", config=ChanlunConfig()).process_klines(df)
    return df, res


def item_idx(item: dict) -> int | None:
    for f in IDX_FIELDS:
        v = item.get(f)
        if isinstance(v, int):
            return v
    return None


def scan_list(items, n: int) -> tuple[int, int, dict | None]:
    """返回 (总条目数, 越界条目数, 越界样例)。"""
    if not isinstance(items, list):
        return (0, 0, None)
    over = []
    for it in items:
        if not isinstance(it, dict):
            continue
        ix = item_idx(it)
        if ix is None:
            continue  # 无法判定（如 fractals 有 bar_index，mmds 有 bar_index）
        if ix > n:
            over.append(it)
    sample = None
    if over:
        s = dict(over[0])
        for k in list(s):
            if isinstance(s[k], (dict, list)) and len(str(s[k])) > 60:
                s[k] = str(s[k])[:60] + "..."
        sample = s
    return (len(items), len(over), sample)


def scan_levels(levels, n: int, path: str, out: list) -> None:
    if not isinstance(levels, dict):
        return
    for lname, lv in levels.items():
        if not isinstance(lv, dict):
            continue
        for key in ("bis", "xds", "zss", "mmds", "bcs", "zsds", "qsds"):
            arr = lv.get(key)
            if not isinstance(arr, list) or not arr:
                continue
            total, over, sample = scan_list(arr, n)
            if total:
                out.append((f"{path}.{lname}.{key}", total, over, sample))


def main() -> None:
    df, res = load()
    print(f"fixture bars = {len(df)}, analyser bis={len(res.bis)} mmds={len(res.mmds)} "
          f"bcs={len(res.bcs)} zsds={len(res.zsds)} qsds={len(res.qsds)} zss={len(res.zss)}")
    for n in (0, 30, 50, 80):
        p = build_train_session_payload(res, df, "daily", "medium", 0, reveal_limit=n)
        print(f"\n===== reveal_limit={n} =====")
        print(f"{'key':<28}{'total':>7}{'over':>7}  sample")
        rows = []
        for key in sorted(p):
            v = p[key]
            if key == "bars":
                over = max(len(v) - (n + 1), 0)
                rows.append((key, len(v), over, f"last_dt={v[-1]['datetime']}" if v else None))
            elif isinstance(v, list):
                total, over, sample = scan_list(v, n)
                rows.append((key, total, over, sample))
            elif isinstance(v, dict) and any(isinstance(x, list) for x in v.values()):
                # macd / boll
                lens = {k: len(x) for k, x in v.items() if isinstance(x, list)}
                over = max(max(lens.values(), default=0) - (n + 1), 0)
                rows.append((key, max(lens.values(), default=0), over, f"lens={lens}"))
            elif key == "levels":
                sub = []
                scan_levels(v, n, "levels", sub)
                for name, total, over, sample in sub:
                    rows.append((name, total, over, sample))
        for name, total, over, sample in rows:
            flag = "  <-- LEAK" if over else ""
            print(f"{name:<28}{total:>7}{over:>7}  {sample}{flag}")
    # 复盘模式对照
    p = build_train_session_payload(res, df, "daily", "medium", 0, reveal_limit=None)
    print("\n===== reveal_limit=None (review) =====")
    print(f"{'key':<28}{'total':>7}")
    for key in sorted(p):
        v = p[key]
        if isinstance(v, list):
            print(f"{key:<28}{len(v):>7}")
        elif isinstance(v, dict) and any(isinstance(x, list) for x in v.values()):
            lens = {k: len(x) for k, x in v.items() if isinstance(x, list)}
            print(f"{key:<28}{max(lens.values(), default=0):>7}  {lens}")
    print("levels keys:", list((p.get('levels') or {}).keys()))


if __name__ == "__main__":
    sys.exit(main())
