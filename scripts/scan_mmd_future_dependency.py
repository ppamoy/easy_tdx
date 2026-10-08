#!/usr/bin/env python3
"""扫描「哪些 mmd 评分助手会用到信号之后的未来数据」。

背景
----
第 25/26 轮分别在置信度与质量评分里发现同一类缺陷：下游助手读的是**传入数组的
尾部**（`closes[-N:]`），而给历史信号打分时传入的是**整段序列**，于是用到了
信号之后的未来数据 —— 同一买卖点的评分只因"后来多录入了数据"就改变，
F2 复盘讲解与 F3 训练数据因此不可复现。

这里不再靠"读代码看函数尾部"，而是**行为级**判定：把输入数组换成更长的一份
（同一个 mmd 对象），输出是否改变 —— 改变即"依赖信号之后的数据"。

重要：命中不等于 bug
--------------------
"动态止损""信号后走势健康度""信号后资金流"等函数**本来就该**看信号之后的数据，
那是设计意图。所以本脚本输出两类：

  A 组 POST_INTENT  —— 名字/文档明确表明"信号之后"语义，命中属预期，不应裁剪
  B 组 NEEDS_REVIEW —— 未表明向后看语义却命中，**应当**是 point-in-time，需逐个核实

用法
----
    python scripts/scan_mmd_future_dependency.py            # 全量扫描
    python scripts/scan_mmd_future_dependency.py --all      # 含 A 组
"""

from __future__ import annotations

import argparse
import ast
import inspect
import math
import pathlib
import sys

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun import mmd_conditions as MC  # noqa: E402

SHORT, LONG = 400, 500

# 名字/文档中出现这些词 → 该函数"向后看"是**设计意图**，命中不计入待修
POST_INTENT = (
    "post_signal", "trajectory", "after_signal", "fund_flow", "execution_window",
    "stop_loss", "take_profit", "dynamic_atr", "dynamic_sl", "dynamic_tp",
    "rr_optimization", "risk_reward", "dynamic_stop", "stop_tp", "atr_adaptive",
    "atr_multiplier", "decay", "freshness", "aging", "execut", "recent_range",
    "signal_history", "age_decay", "time_decay", "signal_decay",
)

# 已修复的入口。注意：**不是**从候选里剔除 —— 保留它们是为了做「已知修复不得回归」
# 的自检（第 27 轮教训：一旦剔除，这些函数若再次引入前视，本脚本就再也抓不到了）。
ALREADY_FIXED = {"_calc_confidence", "_calc_confidence_v47", "_calc_mmd_quality"}

ARRAYS = ("closes", "highs", "lows", "volumes", "macd_data")


def _bars(n: int) -> pd.DataFrame:
    """合成有笔有中枢的序列（与既有探测脚本同一口径，保证可比）。"""
    base = pd.Timestamp("2024-01-01")
    rows = []
    for i in range(n):
        px = 10.0 + 2.0 * math.sin(i / 11.0) + 0.6 * math.sin(i / 3.0)
        o, c = px, px + 0.05 * math.sin(i / 5.0)
        rows.append({
            "datetime": (base + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
            "open": round(o, 4), "close": round(c, 4),
            "high": round(max(o, c) + 0.05, 4), "low": round(min(o, c) - 0.05, 4),
            "vol": 1000 + (i % 7) * 50, "amount": 10000.0,
        })
    return pd.DataFrame(rows)


def _candidate_functions():
    """返回所有「接受 mmd + 数组型参数」且自身没做裁剪的函数名。"""
    src = (ROOT / "src/easy_tdx/chanlun/mmd_conditions.py").read_text()
    tree = ast.parse(src)
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.FunctionDef):
            continue
        params = [a.arg for a in fn.args.args]
        if "mmd" not in params:
            continue
        if not any(n in params for n in ARRAYS):
            continue
        body = ast.get_source_segment(src, fn) or ""
        if "_truncate_to_signal_window" in body:
            continue
        out.append(fn.name)
    return sorted(set(out))


def _post_intent(name: str) -> bool:
    if any(p in name.lower() for p in POST_INTENT):
        return True
    fn = getattr(MC, name, None)
    doc = ""
    try:
        doc = (inspect.getdoc(fn) or "").lower()
    except Exception:
        pass
    return any(p in doc for p in POST_INTENT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="连 A 组（有意为之）也一起列出")
    args = ap.parse_args()

    ds, dl = _bars(SHORT), _bars(LONG)
    cols = lambda d: {k: d[k].tolist() for k in ("close", "high", "low", "vol")}
    short, long = cols(ds), cols(dl)
    # ⚠️ 不能只用一个信号：命中与否依赖信号位置（第 27 轮教训 —— 单信号采样会漏报）。
    # 取覆盖不同位置的若干信号逐个试，任一命中即记为命中。
    from easy_tdx.chanlun.analyser import ChanlunAnalyser as _CA
    _res = _CA(code="000001", frequency="daily").process_klines(ds)
    zss = _res.zss
    mmds = sorted(_res.mmds, key=lambda mm: mm.bi.end.k.k_index)
    if not mmds:
        print("❌ 合成数据未产生任何买卖点，脚本无法工作（数据/参数需调整）")
        return 2
    probe_mmds = mmds[:1] + mmds[len(mmds) // 2:len(mmds) // 2 + 1] + mmds[-1:]
    mmd = mmds[len(mmds) // 2]  # 默认取中位信号，覆盖度最好

    base = {
        "mmd": mmd, "trend_strength": 0.5, "trend_direction": "up",
        "volatility": 0.02, "zss": zss,
        "macd_data": {"dif": [0.0] * SHORT, "dea": [0.0] * SHORT, "hist": [0.0] * SHORT},
    }
    src_map = {"closes": "close", "highs": "high", "lows": "low", "volumes": "vol"}

    group_b, group_a, skipped = [], [], []
    for name in _candidate_functions():
        fn = getattr(MC, name, None)
        if not callable(fn):
            continue
        try:
            params = inspect.signature(fn).parameters
        except Exception:
            skipped.append(name)
            continue

        # ⚠️ 必须测多种入参配置：第 27 轮教训 —— 只传「齐全」的 macd_data 时，
        # _calc_mmd_quality 的命中被掩盖（11/11 信号全变 vs 0/1 命中）。
        # 真实调用里可选数组常常是 None，所以 None 形态必须先测。
        optional_arrays = [
            p for p in params.values()
            if p.name in ARRAYS and p.default is not inspect.Parameter.empty
        ]
        configs = [None]  # None = macd_data 等可选数组传 None
        if optional_arrays:
            configs.append("full")

        def build(cols_, mode: str | None):
            kw = {}
            for p in params.values():
                if p.name in src_map:
                    kw[p.name] = cols_[src_map[p.name]]
                elif p.name in ARRAYS:
                    # 可选数组：None 模式下传 None，full 模式下传实际数据
                    kw[p.name] = None if mode is None else base.get(p.name)
                elif p.name in base:
                    kw[p.name] = base[p.name]
                elif p.default is inspect.Parameter.empty:
                    return None
            return kw

        hit = False
        for probe in probe_mmds:
            if hit:
                break
            base["mmd"] = probe
            for mode in configs:
                ka, kb = build(short, mode), build(long, mode)
                if ka is None:
                    continue
                try:
                    ra, rb = fn(**ka), fn(**kb)
                except Exception:
                    continue
                if not _safe_eq(ra, rb):
                    hit = True
                    break
        base["mmd"] = mmd
        if not hit:
            skipped.append(name)
            continue
        (group_a if _post_intent(name) else group_b).append(name)

    regressions = sorted(set(group_a + group_b) & ALREADY_FIXED)
    group_a = [n for n in group_a if n not in ALREADY_FIXED]
    group_b = [n for n in group_b if n not in ALREADY_FIXED]

    total = len(_candidate_functions())
    hits = len(group_a) + len(group_b)
    print(f"扫描 {total} 个「mmd + 数组」助手（跳过 {len(skipped)} 个）")
    print(f"其中 {hits} 个的输出会随输入变长而改变（即依赖信号之后的数据）\n")
    print(f"A 组 名字/文档表明「信号之后」是有意为之 : {len(group_a)} 个  → 不应裁剪")
    print(f"B 组 未表明向后看却依赖未来数据         : {len(group_b)} 个  → 应逐个核实")
    if group_b:
        print("\n=== B 组明细（真正的待办）===")
        for n in sorted(group_b):
            print(f"  {n}")
    if args.all and group_a:
        print("\n=== A 组明细（预期行为，仅供参考）===")
        for n in sorted(group_a):
            print(f"  {n}")
    if regressions:
        print("\n❌ 已修复的函数又出现了前视（回归！）：")
        for n in regressions:
            print(f"  {n}")
        return 1
    print("✅ 自检通过：已修复的三个入口仍无前视")
    print(
        "\n注意：命中不等于 bug —— 需结合函数语义判断它是否本就该看信号之后的数据。"
        "\n本脚本只负责把「依赖未来数据」这件事**测出来**，不做语义裁决。"
    )
    return 0


def _safe_eq(a, b) -> bool:
    """深比较；不可比较时退化为 repr 比较（避免把差异漏掉）。"""
    try:
        return bool(a == b)
    except Exception:
        pass
    try:
        return repr(a) == repr(b)
    except Exception:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
