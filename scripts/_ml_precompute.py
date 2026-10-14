#!/usr/bin/env python3
"""多级别回测的**共享预计算 + 磁盘缓存**。

## 为什么必须有这个模块
30min 序列每只约 4000 根，``ChanlunAnalyser.process_klines`` 实测 **20 秒/只**
（O(n²)：500 根 0.38s → 3976 根 21.4s）。方案矩阵有 6~10 个方案，若每个方案
各自全量分析一次：285 只 × 20s × 10 方案 ≈ **16 小时**，全量根本跑不动。

而所有多级别方案共用**同一份**日线/30min 分析结果 —— 差别只在"消费哪些信号"。
故只需每只算一次，落盘缓存，后续所有脚本/方案复用。

## 缓存键的诚实说明
缓存键 = (code, 日线行数, 日线首末时间, 30min 行数, 30min 首末时间, 配置指纹)。
只要输入数据或缠论配置变了，键就变，不会读到陈旧结果。
⚠️ 但**代码逻辑变了不会自动失效** —— 若改了 ``analyser``/``mmd`` 的算法，
必须手动清 ``audit_cache/`` 或在键里加代码版本。已在 ``CONFIG_FP`` 里带上
缠论配置指纹，算法改动请手动 `rm -rf audit_cache`。

## 防未来函数的边界（重要）
本模块对次级别做**一次性全量分析**再落盘。这本身**不是**未来函数 ——
因为消费端（``ChanlunMLStrategy.next``）只取「信号 datetime <= 当前日线 bar
时刻」的信号，按时间推进。但**必须注意**：
- 笔/中枢/买卖点的确认需要后续 K 线，故序列**尾部**的几根信号在真实交易时
  尚未确认。回测中这些尾部信号仍会被消费 ⇒ 存在**边界未来性**。
- 已由 ``scripts/verify_ml_pit.py`` 用"截断序列重跑对比"实测：前 200 根
  范围内逐位一致 ✅（截断只影响尾部，不影响已消费的历史决策）。
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402
from easy_tdx.chanlun.qujiantao import compute_qujiantao_cross_period  # noqa: E402

D = ROOT / "audit_data"
DM = ROOT / "audit_data_min"
CACHE = ROOT / "audit_cache"
EXCLUDE = {"sh000300", "sh000001"}

# 缠论配置指纹：配置变了缓存自动失效（算法变了需手动清）
CONFIG_FP = hashlib.md5(
    json.dumps(ChanlunConfig().to_dict() if hasattr(ChanlunConfig(), "to_dict")
               else {"bi_type": "new"}, sort_keys=True).encode()
).hexdigest()[:8]

_BUY = ("1buy", "2buy", "2buy_s", "3buy")
_SELL = ("1sell", "2sell", "2sell_s", "3sell")


def _fp(df: pd.DataFrame) -> str:
    return f"{len(df)}|{str(df['datetime'].iloc[0])}|{str(df['datetime'].iloc[-1])}"


def load_pair(code: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """读日线 + 30min，并把日线**截断**到次级别覆盖区间。"""
    d = pd.DataFrame(json.loads((D / f"{code}_daily.json").read_text()))
    d["datetime"] = pd.to_datetime(d["datetime"])
    s = pd.DataFrame(json.loads((DM / f"{code}_30min.json").read_text()))
    s["datetime"] = pd.to_datetime(s["datetime"])
    d = d[d["datetime"] >= s["datetime"].iloc[0]].reset_index(drop=True)
    return d, s


def cache_path(code: str, d: pd.DataFrame, s: pd.DataFrame) -> Path:
    key = f"{code}|{_fp(d)}|{_fp(s)}|{CONFIG_FP}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE / f"{code}_{h}.json"


def compute(code: str) -> dict | None:
    """算一只是（日线信号 + 30min 信号 + 区间套确认表），带磁盘缓存。"""
    d, s = load_pair(code)
    if len(d) < 80 or len(s) < 80:
        return None
    p = cache_path(code, d, s)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            pass

    cfg = ChanlunConfig()
    rh = ChanlunAnalyser(code=code, frequency="daily", config=cfg).process_klines(d)
    rs = ChanlunAnalyser(code=code, frequency="30min", config=cfg).process_klines(s)

    # ── 主周期信号（入场 + 兜底出场）──
    # ⚠️ 排序必须与 ChanlunMLStrategy.init() **逐位一致**：按 mmds 原始顺序
    #    append，再用 Python 稳定排序 sort(key=bar)。若这里改成二级键排序
    #    （如 (bar, t)），同一 bar 上的多条信号顺序会变 ⇒ 信号序号错位 ⇒
    #    区间套确认表错位 ⇒ 静默错配。曾想当然写成 (bar, t)，已改回。
    main_tuples: list[tuple[int, str, float, int]] = []
    nested_by_mmd: dict[int, bool] = {}
    for i, m in enumerate(rh.mmds):
        t = str(m.mmd_type.value)
        if t not in _BUY and t not in _SELL:
            continue
        bar = int(m.bi.end.bar_index) if m.bi else -1
        if bar >= 0:
            main_tuples.append((bar, t, float(getattr(m, "confidence", 0.0)), i))
    main_tuples.sort(key=lambda x: x[0])  # 稳定排序，与 init() 同构

    # ── 真·区间套：日线买点 ↔ 30min 结构（供 sub_entry_scope=nested）──
    qt = compute_qujiantao_cross_period(
        rh.mmds, bis_low=rs.bis, zss_low=rs.zss, bcs_low=rs.bcs, mmds_low=rs.mmds,
    )
    for i, q in enumerate(qt):
        nested_by_mmd[i] = bool(q.get("nested")) if q else False

    main_raw = [{"bar": b, "t": t, "c": c} for b, t, c, _ in main_tuples]
    main_nested = {i: nested_by_mmd.get(mi, False) for i, (_, _, _, mi) in enumerate(main_tuples)}

    # ── 次级别信号（出场）──
    dts = s["datetime"].reset_index(drop=True)
    sub_tuples: list[tuple[str, str, float]] = []
    for m in rs.mmds:
        t = str(m.mmd_type.value)
        if t not in _SELL:
            continue
        bar = int(m.bi.end.bar_index) if m.bi else -1
        if 0 <= bar < len(dts):
            sub_tuples.append((str(dts.iloc[bar]), t, float(getattr(m, "confidence", 0.0))))
    sub_tuples.sort(key=lambda x: x[0])  # 稳定排序，与 init() 同构
    sub_raw = [{"dt": a, "t": b, "c": c} for a, b, c in sub_tuples]

    out = {
        "code": code,
        "n_daily": len(d),
        "n_min": len(s),
        "t0": str(d["datetime"].iloc[0]),
        "t1": str(d["datetime"].iloc[-1]),
        "main": main_raw,
        "sub": sub_raw,
        "main_nested": {str(k): v for k, v in main_nested.items()},
    }
    CACHE.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False))
    return out


def build(codes: list[str], workers: int = 2, log_every: int = 10) -> dict[str, dict]:
    """批量预计算（进程池）。返回 code → 结果。"""
    from concurrent.futures import ProcessPoolExecutor

    out: dict[str, dict] = {}
    todo = [c for c in codes if not cache_path(c, *load_pair(c)).exists()] \
        if False else list(codes)  # 命中判断在子进程里做（load_pair 更安全）
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, r in enumerate(ex.map(compute, todo, chunksize=1)):
            if r:
                out[r["code"]] = r
            if (i + 1) % log_every == 0:
                print(f"  预计算 {i+1}/{len(todo)}", flush=True)
    return out


def list_codes() -> list[str]:
    codes = [p.name.split("_")[0] for p in sorted(DM.glob("*_30min.json"))]
    return [c for c in codes if c not in EXCLUDE]


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    codes = list_codes()
    if a.limit:
        codes = codes[: a.limit]
    print(f"预计算 {len(codes)} 只（日线+30min+区间套），并行度 {a.workers}")
    r = build(codes, workers=a.workers)
    print(f"\n完成 {len(r)}/{len(codes)} 只，缓存目录 {CACHE}")
