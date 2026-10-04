#!/usr/bin/env python3
"""V733：并行版回撤审计 —— 把"下行保护"从 n=8/12 扩到**大样本**复核。

为什么做
----------
五之十四~十六得出整份审计里最关键的结论："缠论的价值是下行保护，
中位最大回撤 28.5% vs 买持 54.1%，97% 样本回撤更小"。但那个数字
**样本太小**（分区脚本 n=30、低暴露基线 n=8、参数扫描 n=12）。

单次回测约 26s/只 ⇒ 串行跑 200 只需 ~1.5 小时。本脚本用**进程池**在
4 核上并行，把样本扩到可下结论的规模。

⚠️ 并行化本身要小心（我踩过）：
- 必须用 `ProcessPoolExecutor`（回测是 CPU 密集的纯 Python，GIL 内多线程无效）；
- 子进程里必须能 import 到项目源码 ⇒ 显式传 `sys.path` 或设环境变量，
  不能依赖父进程的 sys.path（fork 会继承，spawn 不会）；
- 结果必须**按标的索引对齐**（和之前的 broadcast bug 同类风险）。

用法：
    .venv/bin/python scripts/audit_drawdown_parallel.py --limit 60 --workers 4

退出码：0 = 跑完；2 = 环境不可用。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "audit_data"
EXCLUDE = {"sh000300", "sh000001"}


def _one(args: tuple[int, str, str]) -> tuple:
    """单标的回测，返回 (idx, 策略收益, 策略回撤, 买持收益, 买持回撤, 交易数)。

    ⚠️ 买持回撤必须在子进程里就地算：它只是收盘价序列的前向最大值回撤，
    几乎零成本；而把它推回主进程重算需要重新读 288 个 JSON（更慢）。
    第一版只返回买持**收益**、把回撤对比留给别的脚本，等于这个脚本
    回答不了"缠论回撤是否低于买持"——那正是要验证的问题。
    """
    idx, path, position_pct = args
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    from easy_tdx.backtest.engine import BacktestEngine
    from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy
    try:
        df = pd.DataFrame(json.loads(Path(path).read_text(encoding="utf-8")))
        df["datetime"] = pd.to_datetime(df["datetime"])
        if "vol" in df.columns:
            df = df.rename(columns={"vol": "volume"})
        if "volume" in df.columns:
            df["amount"] = df["close"] * df["volume"]
        if len(df) < 300:
            return (idx,) + (float("nan"),) * 5 + (f"数据过短 {len(df)}",)
        s = ChanlunStrategy()
        if position_pct != 1.0:
            s.p["position_pct"] = position_pct
        r = BacktestEngine(s, cash=100000.0).run(df)
        px = df["close"].to_numpy(float)
        peak = np.maximum.accumulate(px)
        bh_dd = float((peak - px).max() / peak.max())
        tr = r.trades
        ntr = (int((tr["direction"] == "SELL").sum())
               if isinstance(tr, pd.DataFrame) and not tr.empty else 0)
        return (idx, float(r.performance["total_return"]),
                float(r.performance["max_drawdown"]),
                float(px[-1] / px[0] - 1.0), bh_dd, ntr)
    except Exception as e:  # ⚠️ 之前是裸 except，会把真错误静默成 nan，
        # 表现为"有效样本不足"——排查方向完全被带偏。必须让错误可见。
        return (idx,) + (float("nan"),) * 5 + (f"{type(e).__name__}: {e}",)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--position-pct", type=float, default=1.0,
                    help="仓位；默认 1.0（满仓），此时不传显式 size")
    a = ap.parse_args()

    fs = [p for p in sorted(DATA.glob("*.json"))
          if p.stem.split("_")[0] not in EXCLUDE]
    if a.limit:
        fs = fs[: a.limit]
    if not fs:
        print("❌ 无 audit_data，先跑 scripts/audit_fetch_real_data.py")
        return 2

    jobs = [(i, str(p), a.position_pct) for i, p in enumerate(fs)]
    print(f"并行回撤审计 —— {len(jobs)} 只 A 股，{a.workers} 进程，"
          f"position_pct={a.position_pct}")
    print("（单次回测≈26s，串行需 "
          f"{len(jobs)*26/60:.0f} 分钟，并行约 {len(jobs)*26/a.workers/60:.0f} 分钟）")
    print("=" * 72, flush=True)

    out: dict[int, tuple] = {}
    done = 0
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(_one, j): j[0] for j in jobs}
        for f in as_completed(futs):
            r = f.result()
            out[r[0]] = r
            done += 1
            if done % 10 == 0 or done == len(jobs):
                print(f"  已完成 {done}/{len(jobs)}", flush=True)

    # ⚠️ 必须按 idx 对齐，不能靠完成顺序（否则和曾经的 broadcast bug 同类）
    arr = np.array([out[i][:6] for i in range(len(jobs)) if i in out], dtype=float)
    ok = ~np.isnan(arr[:, 1])
    bad = [out[i][6] for i in sorted(out) if i in out and not ok[list(arr[:, 0]).index(i)]
           if len(out[i]) > 6]
    arr = arr[ok]
    if len(arr) < 10:
        print(f"❌ 有效样本仅 {len(arr)}，不足")
        if bad:
            print("失败原因（前 5 条）：")
            for b in bad[:5]:
                print(f"   - {b}")
        return 2
    if bad:
        print(f"⚠️ {len(bad)} 只标的回测失败（已跳过），前 3 条：")
        for b in bad[:3]:
            print(f"   - {b}")

    ret, dd, bh_ret, bh_dd, ntr = arr[:, 1], arr[:, 2], arr[:, 3], arr[:, 4], arr[:, 5]
    # arr[:,0] 是原始 idx，仅用于对齐，不参与统计
    n = len(arr)
    print(f"\n有效样本 n={n}")
    print(f"  缠论策略   收益中位 {np.median(ret)*100:+6.1f}%   "
          f"最大回撤中位 {np.median(dd)*100:5.1f}%")
    print(f"  买入持有   收益中位 {np.median(bh_ret)*100:+6.1f}%   "
          f"最大回撤中位 {np.median(bh_dd)*100:5.1f}%")
    print(f"  交易数中位 {np.median(ntr):.0f}")

    win = int((dd < bh_dd).sum())
    print(f"\n  缠论回撤 < 买持回撤：{win}/{n} = {win/n*100:.0f}%")
    d = ret - bh_ret
    t = float(d.mean() / d.std() * np.sqrt(len(d))) if d.std() > 0 else float("nan")
    print(f"  收益超额：中位 {np.median(d)*100:+.1f}%  均值 {d.mean()*100:+.1f}%  t={t:+.2f}")
    print(f"  收益跑赢买持：{int((d>0).sum())}/{n} = {(d>0).mean()*100:.0f}%")
    if win / n >= 0.9:
        print("\n✅ 判定：回撤优势在**大样本**下依然成立（≥90% 标的）。")
    else:
        print("\n⚠️ 判定：大样本下回撤优势未达 90%，需重新审视五之十四的结论。")
    print("\n⚠️ 局限：单市场日线、默认参数（除 position_pct 外）、"
          "未 beta/市值中性化、")
    print("   未做样本外切分；本轮为横截面统计，不是策略建议。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
