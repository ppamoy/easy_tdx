#!/usr/bin/env python3
"""第17课「中枢=次级别走势类型重叠」的跨周期口径修正 —— 索引映射（V851）。

## 缺陷（前一轮已量化，本轮修复）

`analyser.py: process_klines_cross_timeframe`：

    lower_xds = lower.process_klines(lower_tf_df).xds   # 30min 线段
    cross_zss = find_zss(lower_xds)                     # ZS.lines = 30min 线段
    find_mmds_v44(bis, cross_zss, ...)                  # bis = 日线笔

`ZS.lines[*].index` 是 **30min 线段序号**；`mmd.py` 9 处把它当**日线笔下标**用：

    mmd.py:2874   next_first_bi_idx_map[z.index] = z2.lines[0].index
    mmd.py:2891   superseded_at = next_first_bi_idx_map.get(zs.index)
    mmd.py:2928   last_idx = zs.lines[-1].index
    mmd.py:3125   retest_bi = bis[last_idx + 1]
    mmd.py:3148/3477   if bi.index >= (zs.lines[-1].index ...)
    mmd.py:3124/3356/3686  _calc_bi_force(..., zs.lines[0].index)

前一轮实测日期差 **3930–4365 天**（约12年）：拿 30min 线段末段（2026）去索引
日线笔数组，取到 2014 年的笔。

## 修法（边界映射，不动 mmd.py 的 9 处）

在 `process_klines_cross_timeframe` 里，把 `cross_zss` 的每条线对象的
`.index` **重写为日线笔下标**：

    对每个 30min 线段 L，找「终点时间最接近 L 终点」的日线笔 bi，
    令 L.index = bi.index

这样 `mmd.py` 无需改动，语义也正确：
- `zs.lines[-1].index` → 该中枢在日线笔序列中的位置
- `bis[last_idx+1]`   → 中枢之后的第一根日线笔（回试段）
- `bi.index >= zs.lines[-1].index` → 中枢之后的日线笔

### 为什么用「终点时间最接近」而不是「包含」

日线笔与 30min 线段是不同粒度的划分，端点几乎不可能精确对齐。
第17课口径下中枢由次级别走势构成，日线笔是**上级别的观察尺度**；
把次级别线段归到"其终点之后最近的那根日线笔"是保守且确定的选择
（保证 `bis[idx+1]` 不早于该线段结束）。

### 副作用（必须实测，不能推理）

`_calc_bi_force(line, closes, line.index)` 也用 `.index` 取 closes/macd。
重写 index 后，这些调用改拿**日线**的 closes —— 这正是原代码意图
（`closes` 是日线 closes），所以是**修复**而非破坏。

## 验证

- 正对照：映射后 `bis[zs.lines[-1].index]` 与 `zs.lines[-1]` 的日期差应 ≈ 0 天
- 反对照：映射前日期差 4000+ 天（前一轮已测）
- 开关两侧：cross_timeframe 路径 vs 默认路径，信号数都应有合理值
- 回归：`-k chanlun` 全量，diff 失败集合
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


def load_pair(code: str):
    dp = DAILY_DIR / f"{code}_daily.json"
    lp = LOWER_DIR / f"{code}_30min.json"
    if not dp.exists() or not lp.exists():
        return None, None
    drows = json.loads(dp.read_text(encoding="utf-8"))
    lrows = json.loads(lp.read_text(encoding="utf-8"))
    ddf = pd.DataFrame(drows)
    ldf = pd.DataFrame(lrows)
    ddf["datetime"] = pd.to_datetime(ddf["datetime"])
    ldf["datetime"] = pd.to_datetime(ldf["datetime"])
    return ddf, ldf


def _line_end_ts(line) -> pd.Timestamp | None:
    k = getattr(line, "end", None)
    k = getattr(k, "k", None)
    if k is None:
        return None
    ts = getattr(k, "date", None)
    if ts is None:
        return None
    try:
        return pd.Timestamp(ts)
    except Exception:
        return None


def audit(code: str, fix: bool) -> dict:
    ddf, ldf = load_pair(code)
    if ddf is None:
        return {"code": code, "skip": True}

    cfg = ChanlunConfig()
    a = ChanlunAnalyser(code=code, frequency="daily", config=cfg)

    # 复刻 process_klines_cross_timeframe 的关键步骤
    lower = ChanlunAnalyser(config=cfg)
    lower_result = lower.process_klines(ldf)
    lower_xds = lower_result.xds
    if len(lower_xds) < 3:
        return {"code": code, "skip": True, "reason": "次级别线段<3"}

    from easy_tdx.chanlun.zs import find_zss

    cross_zss = find_zss(lower_xds, config=cfg)
    result = a.process_klines(ddf)
    bis = result.bis

    if fix:
        _remap_indices(cross_zss, bis)

    # 测量：每个中枢的末段 index 对应的日线笔，与末段自身的时间差
    deltas = []
    out_of_range = 0
    for zs in cross_zss:
        if not zs.lines:
            continue
        last = zs.lines[-1]
        idx = last.index
        if idx < 0 or idx >= len(bis):
            out_of_range += 1
            continue
        zs_end = _line_end_ts(last)
        bi_end = _line_end_ts(bis[idx])
        if zs_end is not None and bi_end is not None:
            deltas.append(abs((zs_end - bi_end).days))

    return {
        "code": code,
        "skip": False,
        "n_xds": len(lower_xds),
        "n_bis": len(bis),
        "n_zss": len(cross_zss),
        "out_of_range": out_of_range,
        "max_delta_days": max(deltas) if deltas else None,
        "median_delta_days": sorted(deltas)[len(deltas) // 2] if deltas else None,
    }


def _remap_indices(cross_zss, bis) -> int:
    """把 30min 线段的 .index 重写为日线笔下标（按终点时间最近）。"""
    if not bis:
        return 0
    # 日线笔终点时间序列
    bi_ts = []
    for b in bis:
        k = getattr(getattr(b, "end", None), "k", None)
        ts = getattr(k, "date", None) if k is not None else None
        bi_ts.append(pd.Timestamp(ts) if ts is not None else None)

    remapped = 0
    for zs in cross_zss:
        for line in zs.lines:
            k = getattr(getattr(line, "end", None), "k", None)
            ts = getattr(k, "date", None) if k is not None else None
            if ts is None:
                continue
            ts = pd.Timestamp(ts)
            # 找终点时间 >= line 终点的第一根日线笔；若都在前面，取最后一根
            target = len(bis) - 1
            for i, bts in enumerate(bi_ts):
                if bts is not None and bts >= ts:
                    target = i
                    break
            if line.index != target:
                line.index = target
                remapped += 1
    return remapped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--fix", action="store_true")
    args = ap.parse_args()

    codes = sorted({p.name.split("_")[0] for p in LOWER_DIR.glob("*.json")})
    if args.limit:
        codes = codes[: args.limit]

    print(f"跨周期索引映射审计 —— {len(codes)} 只标的，fix={args.fix}\n", flush=True)
    print(f"{'code':<10} {'xds':>5} {'bis':>5} {'zss':>5} {'越界':>5} "
          f"{'最大日期差':>10} {'中位日期差':>10}", flush=True)
    print("-" * 62, flush=True)
    for code in codes:
        r = audit(code, args.fix)
        if r.get("skip"):
            print(f"{code:<10} 跳过: {r.get('reason', '无数据')}", flush=True)
            continue
        print(
            f"{r['code']:<10} {r['n_xds']:>5} {r['n_bis']:>5} {r['n_zss']:>5} "
            f"{r['out_of_range']:>5} "
            f"{str(r['max_delta_days']):>10} {str(r['median_delta_days']):>10}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
