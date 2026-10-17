"""缠论架构级偏离小实测（V853）—— 四块各跑一轮真实数据，量化「差多少」。

判据 = docs/缠论108课/ 原文。行为级（AGENTS.md §1），非存在性断言。

  A §2.1  中枢=次级别走势重叠 vs 次级别笔重叠（第17/20课）
           原文：中枢由「次级别走势类型」重叠构成（走势=≥3笔构成）。
           现状：默认 zs_from_xd=False，中枢由「笔」重叠构成。
           实测：同一行情下，笔级中枢(zs_from_xd=False) vs 线段级中枢
                 (zs_from_xd=True，线段=走势) 的数量/构成差异；并验证线段级
                 中枢的构成段是否真为走势(每线段≥3内部笔)。

  B §2.2  2买=次级别1买 vs 第一次回调低点（第17课）
           原文：2买 = 1买后「第一次次级别走势」的1买（次级别背驰低点）。
           现状：2买 = 1买后第一个向下「笔」的低点。
           实测：每个 2买 的锚定笔 low 是否落在某线段端点(走势结束)，
                 还是 mid-线段(单笔回调)。

  C §2.4  同级别分解（第38课）
           原文：三段成中枢、不延伸、第4段起新起(盘整+盘整)、唯一性。
           现状：same_level.py 实现了规则，但 grep 全仓 0 调用方（dead module）。
           实测：直接调 decompose_same_level，验证产出合法走势类型段；并确认
                 pipeline 未接入（wiring gap）。

  D §2.5  区间套状态机（第61课）
           原文：区间套 = 嵌套背驰段逐重链（65→69→71→71内部，四重），状态机
                 ASSUMED(假设进入背驰段)→观察内部→CONFIRMED/REJECTED。
           现状：qujiantao.py 单窗口确认(nested/score)，无状态机、无逐重嵌套。
           实测：真实数据上跑 qujiantao_for_result，统计 method/score 分布，
                 并断言输出结构里**没有** ASSUMED/CONFIRMED/REJECTED 字段
                 （即第61课状态机未实现）。

用法： .venv/bin/python scripts/audit_chanlun_arch_gap_v853.py [--limit N] [--tail M]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import pandas as pd


def load_bars(path: str, tail: int | None) -> pd.DataFrame:
    bars = json.load(open(path))
    if tail and len(bars) > tail:
        bars = bars[-tail:]
    df = pd.DataFrame(bars)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.rename(columns={"datetime": "date"})
    return df


def _bi_kidx(bi):
    return getattr(getattr(bi, "end", None), "k", None)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--tail", type=int, default=900)
    args = ap.parse_args()

    preferred = ["sh000001", "sh600519", "sz000333", "sh600036",
                "sz000001", "sh601318"]
    files = []
    for c in preferred:
        p = f"audit_data/{c}_daily.json"
        if os.path.exists(p):
            files.append(p)
    all_files = sorted(glob.glob("audit_data/*_daily.json"))
    for p in all_files:
        if len(files) >= args.limit:
            break
        if p not in files:
            files.append(p)
    files = files[: args.limit]

    sys.path.insert(0, "src")
    from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig

    # ── A: 中枢 笔级 vs 线段级 ──────────────────────────────────────────
    A = dict(stocks=0, zs_bi=0, zs_xd=0, xd_zs_segs_walks=0, xd_segs_total=0,
             xd_segs_lt3bi=0)  # 线段级中枢构成段里 <3 笔的(非走势)
    # ── B: 2买 at 线段端点 vs 单笔回调 ───────────────────────────────────
    B = dict(buy2_total=0, at_xd_endpoint=0, mid_segment=0, no_xd=0)
    # ── C: 同级别分解 ─────────────────────────────────────────────────────
    C = dict(stocks=0, segs_total=0, segs_with_zs=0, panzheng=0, trend=0,
             max_seg_bis=0)
    # ── D: 区间套状态机 ───────────────────────────────────────────────────
    D = dict(mmd_total=0, qt_nonnull=0, method_counts={}, state_counts={},
             has_state_fields=0, scores=[])

    for p in files:
        code = os.path.basename(p).replace("_daily.json", "")
        try:
            df = load_bars(p, args.tail)
            if len(df) < 100:
                continue
        except Exception as e:  # noqa: BLE001
            print(f"[{code}] LOAD SKIP: {e}")
            continue

        # --- A: 两种中枢构法 ---
        try:
            r_bi = ChanlunAnalyser(code=code, frequency="daily",
                                   config=ChanlunConfig(zs_from_xd=False)).process_klines(df)
            r_xd = ChanlunAnalyser(code=code, frequency="daily",
                                   config=ChanlunConfig(zs_from_xd=True)).process_klines(df)
        except Exception as e:  # noqa: BLE001
            print(f"[{code}] A SKIP: {e}")
            continue
        A["stocks"] += 1
        A["zs_bi"] += len(r_bi.zss)
        A["zs_xd"] += len(r_xd.zss)
        # 线段级中枢的构成段(线段)是否真为走势(≥3笔)
        for z in r_xd.zss:
            for seg in getattr(z, "lines", []) or []:
                A["xd_segs_total"] += 1
                # 线段对象的内部笔：尝试常见属性
                inner = (getattr(seg, "bis", None) or getattr(seg, "lines", None)
                         or getattr(seg, "_bis", None) or [])
                n = len(inner) if inner else 0
                if n:
                    A["xd_zs_segs_walks"] += 1
                    if n < 3:
                        A["xd_segs_lt3bi"] += 1

        # --- B: 2买 锚点 vs 线段端点 ---
        xds = getattr(r_bi, "xds", []) or []
        xd_endpts = []  # (k_idx, val)
        for xd in xds:
            try:
                xd_endpts.append((xd.start.k.k_index, xd.start.val))
                xd_endpts.append((xd.end.k.k_index, xd.end.val))
            except Exception:  # noqa: BLE001
                pass
        buy2 = [m for m in r_bi.mmds if m.mmd_type.value in ("2buy", "2buy_s")]
        B["buy2_total"] += len(buy2)
        for m in buy2:
            bi = m.bi
            if bi is None:
                continue
            try:
                bi_k = bi.end.k.k_index
                bi_low = bi.low
            except Exception:  # noqa: BLE001
                B["no_xd"] += 1
                continue
            if not xd_endpts:
                B["no_xd"] += 1
                continue
            # 找最近线段端点(按 k_index 距离)
            nearest = min(xd_endpts, key=lambda e: abs(e[0] - bi_k))
            if abs(nearest[0] - bi_k) <= 1:  # 紧贴端点 ⇒ 走势结束
                B["at_xd_endpoint"] += 1
            else:
                B["mid_segment"] += 1

        # --- C: 同级别分解（直接调，不走 pipeline）---
        try:
            from easy_tdx.chanlun.same_level import decompose_same_level
            segs = decompose_same_level(r_bi.bis)
            C["stocks"] += 1
            C["segs_total"] += len(segs)
            for s in segs:
                if s.has_zs:
                    C["segs_with_zs"] += 1
                if s.is_panzheng:
                    C["panzheng"] += 1
                if s.is_trend:
                    C["trend"] += 1
        except Exception as e:  # noqa: BLE001
            print(f"[{code}] C SKIP: {e}")

        # --- D: 区间套输出结构（递归口径，无 30min 数据）---
        try:
            from easy_tdx.chanlun.qujiantao import qujiantao_for_result
            qt_list = qujiantao_for_result(r_bi)
            D["mmd_total"] += len(r_bi.mmds)
            for qt in qt_list:
                if qt is None:
                    continue
                D["qt_nonnull"] += 1
                m = qt.get("method", "?")
                D["method_counts"][m] = D["method_counts"].get(m, 0) + 1
                st = qt.get("state", "?")
                D["state_counts"][st] = D["state_counts"].get(st, 0) + 1
                D["scores"].append(qt.get("score", 0.0))
                # 状态机字段? 第61课应有 ASSUMED/CONFIRMED/REJECTED
                for f in ("state", "assumed", "confirmed", "rejected"):
                    if f in qt:
                        D["has_state_fields"] += 1
                        break
        except Exception as e:  # noqa: BLE001
            print(f"[{code}] D SKIP: {e}")

    # ── 汇总 ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("架构级偏离小实测（V853，行为级）")
    print("=" * 70)
    print(f"样本：{A['stocks']} 只日线，tail={args.tail}")
    print()
    print("A §2.1 中枢=次级别走势重叠 vs 笔重叠（第17/20课）")
    print(f"  笔级中枢(zs_from_xd=False, 现状默认): {A['zs_bi']} 个")
    print(f"  线段级中枢(zs_from_xd=True, 线段=走势): {A['zs_xd']} 个")
    if A["xd_segs_total"]:
        print(f"  线段级中枢构成段总数: {A['xd_segs_total']}"
              f"（其中可读到内部笔的 {A['xd_zs_segs_walks']}，<3笔的非走势 {A['xd_segs_lt3bi']}）")
    diff = A['zs_bi'] - A['zs_xd']
    print(f"  ⇒ 数量差: 笔级比线段级多 {diff} 个"
          f"（笔级把单笔回调也当中枢构成段，原文要求走势重叠 ⇒ 笔级偏多）")
    print()
    print("B §2.2 2买=次级别1买 vs 第一次回调低点（第17课）")
    print(f"  2买总数: {B['buy2_total']}")
    print(f"  锚点紧贴线段端点(走势结束, 近原文): {B['at_xd_endpoint']}")
    print(f"  锚点在 mid-线段(单笔回调, 非原文): {B['mid_segment']}")
    print(f"  无线段可对照: {B['no_xd']}")
    tot = B['at_xd_endpoint'] + B['mid_segment']
    if tot:
        print(f"  ⇒ {B['mid_segment']}/{tot} = {B['mid_segment']/tot*100:.0f}% "
              f"的 2买 落在单笔回调(非次级别1买)")
    print()
    print("C §2.4 同级别分解（第38课）—— same_level.py 是否 wired")
    print(f"  直接调用 decompose_same_level 成功: {C['stocks']} 只")
    print(f"  产出走势类型段: {C['segs_total']} 段（含中枢 {C['segs_with_zs']}，"
          f"盘整 {C['panzheng']}，趋势 {C['trend']}）")
    # wiring 检查（静态 grep）
    import subprocess
    r = subprocess.run(
        ["grep", "-rln", "decompose_same_level", "src/easy_tdx/"],
        capture_output=True, text=True)
    callers = [x for x in r.stdout.strip().split("\n")
               if x and "same_level.py" not in x and "__pycache__" not in x
               and not x.endswith(".pyc")]
    print(f"  pipeline 调用方数: {len(callers)}（grep src/easy_tdx/ 排除自身）"
          f"{' ⇒ ❌ dead module，第38课未接入' if not callers else ''}")
    print()
    print("D §2.5 区间套状态机（第61课）—— 逐重嵌套背驰段链")
    print(f"  高级别买卖点总数: {D['mmd_total']}")
    print(f"  qujiantao 非 None: {D['qt_nonnull']}")
    print(f"  method 分布: {D['method_counts']}")
    print(f"  state 分布(第61课): {D['state_counts']}"
          f"{' ⇒ ✅ 状态机已上线' if D['has_state_fields'] else ' ⇒ ❌ 无第61课状态机(单窗口确认)'}")
    print(f"  输出含状态机字段(state/assumed/confirmed/rejected): {D['has_state_fields']}")
    if D["scores"]:
        sc = sorted(D["scores"])
        print(f"  score: min={sc[0]:.2f} med={sc[len(sc)//2]:.2f} max={sc[-1]:.2f}")
    print()
    print("判定：A/B/C/D 的「差多少」见上行；优先级建议见 docs/CHANLUN_FIDELITY_AUDIT_V852.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
