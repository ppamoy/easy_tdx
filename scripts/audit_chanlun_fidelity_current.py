"""缠论保真度「当前代码」行为级验证（AGENTS.md §1：行为级，禁止存在性断言）。

以缠论 108 课原文为判据，对**当前** ChanlunAnalyser 在真实日线上的行为做四项
硬验证（不是"代码里有没有写这行"，而是"跑出来的结果是否真的符合原文"）：

  V1  ZG/ZD = A/C 两段（第20课）：zg==min(lines[0].high, lines[2].high)，
      zd==max(lines[0].low, lines[2].low)。原文没有 g3。
  V2  中枢延伸 ≤ 9 段（第33课：3+6）：无 zs 的 lines/bi_count > 9。
  V3  2买 可低于 1买（第101课「最弱情况…这是完全可以的」）：
      统计 2buy 中 bi.low <= 对应 1buy.low 的占比（应 > 0，否则说明仍强制高于）。
  V4  1买 必须下跌确立（第21课）：每个 1buy 锚点之前应已存在 ≥2 个依次
      同向向下中枢。复用 _downtrend_established 直接断言。

用法：
  .venv/bin/python scripts/audit_chanlun_fidelity_current.py [--limit N] [--tail M]
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=8, help="股票数")
    ap.add_argument("--tail", type=int, default=1200, help="每只取最近 N 根")
    ap.add_argument(
        "--codes",
        nargs="*",
        default=None,
        help="指定代码（如 sh000001 sz000333），覆盖 --limit",
    )
    args = ap.parse_args()

    # 多样化样本：含指数、白马、成长、ST 风格
    preferred = [
        "sh000001", "sh600519", "sz000333", "sh600036", "sz000001",
        "sh601318", "sz000858", "sh600009",
    ]
    if args.codes:
        files = [f"audit_data/{c}_daily.json" for c in args.codes]
    else:
        files = []
        for c in preferred:
            p = f"audit_data/{c}_daily.json"
            if os.path.exists(p):
                files.append(p)
        # 补足到 limit
        all_files = sorted(glob.glob("audit_data/*_daily.json"))
        for p in all_files:
            if len(files) >= args.limit:
                break
            if p not in files:
                files.append(p)
        files = files[: args.limit]

    # 延迟导入，避免 --help 时拉起整个 chanlun 栈
    sys.path.insert(0, "src")
    from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig
    from easy_tdx.chanlun.mmd import _downtrend_established, _uptrend_established

    cfg = ChanlunConfig()  # 默认 = 原文口径（V851 后）

    rows = []
    totals = dict(zss=0, zg_ok=0, zg_bad=0, over9=0, buy2_le_buy1=0,
                  buy2_total=0, buy1_downtrend_ok=0, buy1_total=0,
                  sell1_uptrend_ok=0, sell1_total=0)

    for p in files:
        code = os.path.basename(p).replace("_daily.json", "")
        try:
            df = load_bars(p, args.tail)
            if len(df) < 100:
                continue
            an = ChanlunAnalyser(code=code, frequency="daily", config=cfg)
            r = an.process_klines(df)
        except Exception as e:  # noqa: BLE001
            print(f"[{code}] SKIP: {e}")
            continue

        bis = r.bis
        zss = r.zss
        mmds = r.mmds

        # V1: ZG/ZD A/C 口径
        zg_ok = zg_bad = 0
        for z in zss:
            lines = z.lines
            if len(lines) < 3:
                continue
            # 原文：ZG=min(g1,g2)=min(lines[0].high, lines[2].high)
            exp_zg = min(lines[0].high, lines[2].high)
            exp_zd = max(lines[0].low, lines[2].low)
            if abs(z.zg - exp_zg) < 1e-9 and abs(z.zd - exp_zd) < 1e-9:
                zg_ok += 1
            else:
                zg_bad += 1
                if zg_bad <= 3:
                    print(
                        f"[{code}] ZG/ZD不符: zg={z.zg:.2f}(exp {exp_zg:.2f}) "
                        f"zd={z.zd:.2f}(exp {exp_zd:.2f}) lines={[ (round(l.high,2),round(l.low,2)) for l in lines[:4]]}"
                    )

        # V2: 中枢 ≤ 9 段
        over9 = [z for z in zss if (len(z.lines) > 9)]

        # V3: 2买 可低于 1买（第101课）
        buy1 = [m for m in mmds if m.mmd_type.value == "1buy"]
        buy2 = [m for m in mmds if m.mmd_type.value in ("2buy", "2buy_s")]
        buy2_le = 0
        for m2 in buy2:
            # 找其前最近的 1buy
            b2low = m2.bi.low if m2.bi else None
            if b2low is None:
                continue
            prev1 = [m1 for m1 in buy1 if m1.bi and m1.bi.index < m2.bi.index]
            if not prev1:
                continue
            b1low = max(prev1, key=lambda m: m.bi.index).bi.low
            if b2low <= b1low:
                buy2_le += 1

        # V4: 1买 下跌确立 / 1卖 上涨确立
        buy1_ok = sell1_ok = 0
        for m in mmds:
            if m.mmd_type.value == "1buy" and m.bi:
                if _downtrend_established(zss, m.bi):
                    buy1_ok += 1
            elif m.mmd_type.value == "1sell" and m.bi:
                if _uptrend_established(zss, m.bi):
                    sell1_ok += 1

        rows.append({
            "code": code, "bars": len(df), "bis": len(bis), "zss": len(zss),
            "zg_ok": zg_ok, "zg_bad": zg_bad, "over9": len(over9),
            "1buy": len(buy1), "2buy": len(buy2), "2buy_le_1buy": buy2_le,
            "1buy_down_ok": buy1_ok, "1sell": len([m for m in mmds if m.mmd_type.value=="1sell"]),
            "1sell_up_ok": sell1_ok,
        })
        totals["zss"] += len(zss)
        totals["zg_ok"] += zg_ok
        totals["zg_bad"] += zg_bad
        totals["over9"] += len(over9)
        totals["buy2_total"] += len(buy2)
        totals["buy2_le_buy1"] += buy2_le
        totals["buy1_total"] += len(buy1)
        totals["buy1_downtrend_ok"] += buy1_ok
        totals["sell1_total"] += len([m for m in mmds if m.mmd_type.value=="1sell"])
        totals["sell1_uptrend_ok"] += sell1_ok

    # 汇总
    print("\n" + "=" * 70)
    print("逐股明细：")
    print(f"{'code':<10}{'bars':>6}{'bis':>5}{'zss':>5}{'zg_ok':>6}{'zg_bad':>7}{'over9':>6}"
          f"{'1buy':>5}{'1buy↓':>6}{'2buy':>5}{'2≤1买':>6}{'1sell':>6}{'1sell↑':>7}")
    for r in rows:
        print(f"{r['code']:<10}{r['bars']:>6}{r['bis']:>5}{r['zss']:>5}{r['zg_ok']:>6}"
              f"{r['zg_bad']:>7}{r['over9']:>6}{r['1buy']:>5}{r['1buy_down_ok']:>6}"
              f"{r['2buy']:>5}{r['2buy_le_1buy']:>6}{r['1sell']:>6}{r['1sell_up_ok']:>7}")

    print("\n" + "=" * 70)
    print("总计（行为级判定）：")
    print(f"  V1 ZG/ZD A/C口径(第20课): {totals['zg_ok']} 符合 / {totals['zg_bad']} 不符 "
          f"（{'✅ 全符合' if totals['zg_bad']==0 else '❌ 有不符'}）")
    print(f"  V2 中枢≤9段(第33课): {totals['over9']} 个超限 / {totals['zss']} 总中枢 "
          f"（{'✅ 全符合' if totals['over9']==0 else '❌ 有超限'}）")
    print(f"  V3 2买可≤1买(第101课): {totals['buy2_le_buy1']} 个2买低于1买 / {totals['buy2_total']} 总2买 "
          f"（{'✅ 允许低于' if totals['buy2_le_buy1']>0 else ('— 无样本' if totals['buy2_total']==0 else '⚠️ 0个低于(可能仍强制高于)')}）")
    print(f"  V4 1买下跌确立(第21课): {totals['buy1_downtrend_ok']}/{totals['buy1_total']} 1买已确立 "
          f"（{'✅ 全符合' if totals['buy1_downtrend_ok']==totals['buy1_total'] and totals['buy1_total']>0 else '❌ 有未确立'}）")
    print(f"  V4 1卖上涨确立(第21课): {totals['sell1_uptrend_ok']}/{totals['sell1_total']} 1卖已确立 "
          f"（{'✅ 全符合' if totals['sell1_uptrend_ok']==totals['sell1_total'] and totals['sell1_total']>0 else '❌ 有未确立'}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
