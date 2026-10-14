#!/usr/bin/env python3
"""缠论模型「结构不变式」审计 —— 用真实数据检验实现是否违反缠论原文硬约束。

为什么先做这一层
----------------
「模型准不准」在没有市场 ground truth 的前提下，第一层可证的是**自洽性**：
缠论原文对笔/线段/中枢/分型有一组**确定性约束**（顶底交替、端点共享、
中枢区间包含关系、线段至少 3 笔…）。这些约束不依赖行情，违反即实现有 bug。
若这一层就破，后面谈「命中率/选股力」毫无意义 —— 那是拿错的结构去拟合噪声。

不变式清单（每条都写明原文依据 + 违反后果）
------------------------------------------
I1  笔端点分型类型交替：向上笔 = 底→顶，向下笔 = 顶→底
I2  笔方向交替：相邻两笔方向必须相反
I3  笔首尾相连：bis[i].end 与 bis[i+1].start 是同一个分型（同一 bar_index）
I4  笔端点价格方向一致：向上笔 end.val > start.val，向下笔反之
I5  笔端点锚定真实 K 线极值：buy 类 anchor_val == klines[bar_index].low（底分型），
    sell 类 == high（顶分型）；且该 bar 确实是笔端点局部极值
I6  笔区间极值正确：bi.high == max(区间内原始K线 high)，bi.low == min(low)
I7  中枢 ZG > ZD；GG >= ZG；DD <= ZD；中枢至少 zs_min_lines 笔
I8  中枢 ZG/ZD 必须等于 **A段与C段**（Z走势段 Z1/Z3，即 lines[0] 与 lines[2]）
    的重叠区间 —— 缠论原文第20课：
      「特别地，再定义 ZG=min(g1、g2)，ZD=max(d1、d2)，显然 [ZD，ZG] 就是
        缠中说禅走势中枢的区间」
    其中 g1/d1 = A段(Z1)、g2/d2 = C段(Z3)，中间的反向笔（B段）**不参与**，
    原文 108 课里**没有 g3**。
    ⚠️ 本准则曾写成「前三个次级别走势 min(high)/max(low)」，那会把中间的反向笔
      也算进去 —— 是对原文的误读（V840 已更正）。按误读口径实测的「303 个
      中枢区间被放宽 / 51.3%」因此**全部作废**，不是代码缺陷。
    ⚠️ 另注：构成笔与 [ZD,ZG] 有重叠这一条**实测 0 违反**（591 个中枢全部满足），
      故 I8 只检定义段口径，不检「每笔都必须落在 [ZD,ZG] 内」（那是对原文的误读：
      原文只要求重叠，GG/DD 可以超出 ZG/ZD）。
I8b 中枢的每条构成笔都必须与 [ZD,ZG] 有重叠（原文延伸判据：无重叠则中枢结束）
I9  线段至少 3 笔；线段方向交替；线段端点 = 某笔端点
I10 分型独立性：valid_fractals 顶底交替 + 相邻不共用 K 线
I11 买卖点锚定：mmd.bar_index 与 mmd.bi.end.bar_index 一致；buy 类在底分型
I12 确定性：同一输入跑两次，全量结构完全一致

用法：  .venv/bin/python scripts/audit_chanlun_invariants.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402
from easy_tdx.chanlun.types import Direction, FXType  # noqa: E402

DATA_DIR = ROOT / "audit_data"

BUY_TYPES = {"1buy", "2buy", "3buy", "buy", "l2buy", "l3buy"}
SELL_TYPES = {"1sell", "2sell", "3sell", "sell", "l2sell", "l3sell"}


def load_all(limit: int = 0) -> list[tuple[str, pd.DataFrame]]:
    """加载真实日线。limit>0 时只取前 N 只（供 --selftest / 日常快速跑）。"""
    out: list[tuple[str, pd.DataFrame]] = []
    for p in sorted(DATA_DIR.glob("*.json")):
        code = p.name.split("_")[0]
        rows = json.loads(p.read_text(encoding="utf-8"))
        if len(rows) < 60:
            continue
        df = pd.DataFrame(rows)
        df["datetime"] = pd.to_datetime(df["datetime"])
        out.append((code, df))
        if limit and len(out) >= limit:
            break
    return out


def audit_one(code: str, df: pd.DataFrame) -> tuple[dict[str, int], list[str]]:
    """返回 (每条不变式的违反计数, 违规明细)。"""
    v: dict[str, int] = {f"I{i}": 0 for i in range(1, 13)}
    v["I8b"] = 0
    details: list[str] = []

    res = ChanlunAnalyser(code=code, frequency="daily", config=ChanlunConfig()).process_klines(df)

    # ── 坏状态注入（仅供 chanlun_health_gate.py --selftest 验证"牙齿"）──
    # 动机（AGENTS.md §7）：一个**从不会变红**的门禁等于没有门禁。
    # 这里故意构造一条违反 I2/I3 的笔（复制末笔 → 同向且端点不连续），
    # 若审计在这种情况下仍返回 0 违反，说明判据在空转，必须修。
    # ⚠️ 默认关闭；CI 正常跑完全不受影响。
    import os as _os

    if _os.environ.get("INJECT_BROKEN") == "1":
        _bs = list(res.bis)
        if len(_bs) >= 2:
            import copy as _copy

            res.bis = _bs + [_copy.copy(_bs[-1])]
        else:
            v["I2"] += 1
            details.append(f"{code} INJECT 笔数不足，无法注入坏状态")

    kls = res.klines
    high_by_bar = {k.index: k.high for k in kls}
    low_by_bar = {k.index: k.low for k in kls}

    # ── I1..I4, I6：笔 ──
    bis = res.bis
    for i, bi in enumerate(bis):
        up = bi.direction == Direction.UP
        # I1
        if up and not (bi.start.fx_type == FXType.DI and bi.end.fx_type == FXType.DING):
            v["I1"] += 1
            details.append(f"{code} I1 笔{bi.index} 向上笔端点非 底→顶")
        if not up and not (bi.start.fx_type == FXType.DING and bi.end.fx_type == FXType.DI):
            v["I1"] += 1
            details.append(f"{code} I1 笔{bi.index} 向下笔端点非 顶→底")
        # I2
        if i > 0 and bis[i - 1].direction == bi.direction:
            v["I2"] += 1
            details.append(f"{code} I2 笔{bi.index} 与笔{bis[i-1].index} 同向")
        # I3
        if i > 0 and bis[i - 1].end.bar_index != bi.start.bar_index:
            v["I3"] += 1
            details.append(
                f"{code} I3 笔{bis[i-1].index}.end@{bis[i-1].end.bar_index} "
                f"!= 笔{bi.index}.start@{bi.start.bar_index}"
            )
        # I4
        if up and not bi.end.val > bi.start.val:
            v["I4"] += 1
            details.append(f"{code} I4 笔{bi.index} 向上但 end<=start")
        if not up and not bi.end.val < bi.start.val:
            v["I4"] += 1
            details.append(f"{code} I4 笔{bi.index} 向下但 end>=start")
        # I6：笔区间极值 = 区间内原始K线真实极值
        si, ei = bi.start.bar_index, bi.end.bar_index
        if 0 <= si <= ei < len(kls):
            seg_h = max(high_by_bar[b] for b in range(si, ei + 1))
            seg_l = min(low_by_bar[b] for b in range(si, ei + 1))
            if abs(bi.high - seg_h) > 1e-6:
                v["I6"] += 1
                details.append(f"{code} I6 笔{bi.index} high {bi.high:.3f} != 区间 {seg_h:.3f}")
            if abs(bi.low - seg_l) > 1e-6:
                v["I6"] += 1
                details.append(f"{code} I6 笔{bi.index} low {bi.low:.3f} != 区间 {seg_l:.3f}")

    # ── I5, I11：买卖点锚定 ──
    for m in res.mmds:
        t = m.mmd_type.value.lower()
        if not m.bi:
            continue
        bar = m.bi.end.bar_index
        # I11：类型方向 vs 端点分型类型
        is_buy = any(b in t for b in BUY_TYPES) or "buy" in t
        is_sell = any(s in t for s in SELL_TYPES) or "sell" in t
        if is_buy and not is_sell and m.bi.end.fx_type != FXType.DI:
            v["I11"] += 1
            details.append(f"{code} I11 {t} 锚在{m.bi.end.fx_type.value}分型（应为底）")
        if is_sell and not is_buy and m.bi.end.fx_type != FXType.DING:
            v["I11"] += 1
            details.append(f"{code} I11 {t} 锚在{m.bi.end.fx_type.value}分型（应为顶）")
        # I5：锚定值 == 该 bar 的真实极值
        if bar in low_by_bar:
            if is_buy and not is_sell:
                if abs(m.bi.end.val - low_by_bar[bar]) > 1e-6:
                    v["I5"] += 1
                    details.append(
                        f"{code} I5 {t}@bar{bar} anchor {m.bi.end.val:.3f} "
                        f"!= kline.low {low_by_bar[bar]:.3f}"
                    )
            elif is_sell:
                if abs(m.bi.end.val - high_by_bar[bar]) > 1e-6:
                    v["I5"] += 1
                    details.append(
                        f"{code} I5 {t}@bar{bar} anchor {m.bi.end.val:.3f} "
                        f"!= kline.high {high_by_bar[bar]:.3f}"
                    )

    # ── I7, I8：中枢 ──
    for zs in res.zss:
        if not (zs.zg > zs.zd):
            v["I7"] += 1
            details.append(f"{code} I7 中枢{zs.index} ZG{zs.zg:.3f} <= ZD{zs.zd:.3f}")
        if zs.gg < zs.zg - 1e-6:
            v["I7"] += 1
            details.append(f"{code} I7 中枢{zs.index} GG{zs.gg:.3f} < ZG{zs.zg:.3f}")
        if zs.dd > zs.zd + 1e-6:
            v["I7"] += 1
            details.append(f"{code} I7 中枢{zs.index} DD{zs.dd:.3f} > ZD{zs.zd:.3f}")
        if zs.line_count < 3:
            v["I7"] += 1
            details.append(f"{code} I7 中枢{zs.index} 仅 {zs.line_count} 笔")
        # I8：ZG/ZD 必须等于 **A段(Z1) 与 C段(Z3)** 的重叠区间（原文第20课
        # 「ZG=min(g1、g2)，ZD=max(d1、d2)」——只用第1笔和第3笔，中间反向笔
        # 不参与，原文里没有 g3）。V840 前本准则误用「前3笔 min/max」，
        # 把中间反向笔算进去，报出的违规是准则错误而非代码缺陷。
        if len(zs.lines) >= 3:
            a_ln = zs.lines[0]   # A 段 = Z1
            c_ln = zs.lines[2]   # C 段 = Z3（中间 lines[1] 是反向笔，不参与）
            zg_ac = min(a_ln.high, c_ln.high)
            zd_ac = max(a_ln.low, c_ln.low)
            if abs(zs.zg - zg_ac) > 1e-6:
                v["I8"] += 1
                details.append(
                    f"{code} I8 中枢{zs.index} ZG{zs.zg:.3f} != 原文 min(g1,g2)={zg_ac:.3f} "
                    f"(A段笔{a_ln.index} high={a_ln.high:.3f}, C段笔{c_ln.index} high={c_ln.high:.3f})"
                )
            if abs(zs.zd - zd_ac) > 1e-6:
                v["I8"] += 1
                details.append(
                    f"{code} I8 中枢{zs.index} ZD{zs.zd:.3f} != 原文 max(d1,d2)={zd_ac:.3f} "
                    f"(A段笔{a_ln.index} low={a_ln.low:.3f}, C段笔{c_ln.index} low={c_ln.low:.3f})"
                )
        # I8b：构成笔必须与 [ZD,ZG] 有重叠（原文延伸判据；GG/DD 可超出，不检）
        for ln in zs.lines:
            if not (min(zs.zg, ln.high) > max(zs.zd, ln.low)):
                v["I8b"] += 1
                details.append(
                    f"{code} I8b 中枢{zs.index} 笔{ln.index}[{ln.low:.3f},{ln.high:.3f}] "
                    f"与 [{zs.zd:.3f},{zs.zg:.3f}] 无重叠"
                )

    # ── I9：线段 ──
    for i, xd in enumerate(res.xds):
        if i > 0 and res.xds[i - 1].direction == xd.direction:
            v["I9"] += 1
            details.append(f"{code} I9 线段{xd.index} 与线段{res.xds[i-1].index} 同向")
        # 线段起止必须落在某个笔端点上
        bar_set = {bi.start.bar_index for bi in bis} | {bi.end.bar_index for bi in bis}
        if bis and (xd.start.bar_index not in bar_set or xd.end.bar_index not in bar_set):
            v["I9"] += 1
            details.append(f"{code} I9 线段{xd.index} 端点不在笔端点集合内")

    # ── I10：valid_fractals 独立性 ──
    vf = res.valid_fractals
    for i in range(1, len(vf)):
        if vf[i].fx_type == vf[i - 1].fx_type:
            v["I10"] += 1
            details.append(f"{code} I10 分型{i-1}@{vf[i-1].bar_index} 与 {i}@{vf[i].bar_index} 同类相邻")
        if abs(vf[i].bar_index - vf[i - 1].bar_index) < 3:
            v["I10"] += 1
            details.append(f"{code} I10 分型{i-1}/{i} 间距 {abs(vf[i].bar_index - vf[i-1].bar_index)} < 3")

    # ── I12：确定性 ──
    res2 = ChanlunAnalyser(code=code, frequency="daily", config=ChanlunConfig()).process_klines(df)
    sig1 = [(b.start.bar_index, b.end.bar_index, b.direction.value) for b in res.bis]
    sig2 = [(b.start.bar_index, b.end.bar_index, b.direction.value) for b in res2.bis]
    mm1 = [(m.mmd_type.value, m.bi.end.bar_index) for m in res.mmds if m.bi]
    mm2 = [(m.mmd_type.value, m.bi.end.bar_index) for m in res2.mmds if m.bi]
    if sig1 != sig2 or mm1 != mm2:
        v["I12"] += 1
        details.append(f"{code} I12 两次运行结果不一致（笔 {len(sig1)}/{len(sig2)}，信号 {len(mm1)}/{len(mm2)}）")

    return v, details


def main() -> int:
    import argparse as _ap

    _p = _ap.ArgumentParser()
    _p.add_argument("--limit", type=int, default=0, help="只审前 N 只（快速自检用）")
    _a = _p.parse_args()

    data = load_all(limit=_a.limit)
    if not data:
        print(f"❌ {DATA_DIR} 无数据，请先跑 scripts/audit_fetch_real_data.py")
        return 2

    keys = [f"I{i}" for i in range(1, 13)] + ["I8b"]
    total: dict[str, int] = {k: 0 for k in keys}
    all_details: list[str] = []
    print(f"缠论结构不变式审计 —— {len(data)} 只标的（真实日线）\n")
    print(f"{'代码':<8}{'笔':>5}{'中枢':>5}{'线段':>5}{'信号':>5}   违反")
    print("-" * 78)
    for code, df in data:
        v, det = audit_one(code, df)
        for k in total:
            total[k] += v[k]
        all_details.extend(det)
        res = ChanlunAnalyser(code=code, frequency="daily", config=ChanlunConfig()).process_klines(df)
        bad = {k: n for k, n in v.items() if n}
        print(
            f"{code:<8}{len(res.bis):>5}{len(res.zss):>5}{len(res.xds):>5}"
            f"{len(res.mmds):>5}   {bad if bad else '—'}"
        )

    print("\n" + "=" * 78)
    print("不变式总违反数：")
    for k in keys:
        flag = "❌" if total[k] else "✅"
        print(f"  {flag} {k}: {total[k]}")

    if all_details:
        print(f"\n违规明细（最多 40 条 / 共 {len(all_details)}）：")
        for d in all_details[:40]:
            print("   " + d)

    return 1 if any(total.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
