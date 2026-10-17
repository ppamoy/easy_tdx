#!/usr/bin/env python3
"""独立验证：easy_tdx 缠论模型到底能不能指导买股票、能不能赚钱。

与已有脚本（audit_predictive_power / audit_strategy_vs_buyhold）的区别：
此前结论散落多个脚本、口径不一。本脚本做**一次独立的端到端复算**，
并刻意站在最不利于缠论的立场：

  1. 信号层：缠论买卖点出现后持有固定时长的收益，与「同标的、同窗口、
     同数量」的随机入场对比，重抽样得到经验 p 值。
     关键：随机基准必须与信号**同样数量**，否则"信号集中在上涨段"
     会造成假显著。
  2. 策略层：用项目自带回测引擎跑真实交易（佣金 0.03% + 印花税 0.1%
     + 滑点），与买入持有对比，报告胜率/超额/配对 t。
  3. 稳健性：前后半段是否符号翻转；换随机种子是否翻转。

刻意不做的（避免自欺）：
  * 不调参，全部用默认参数。调参后的结果无法外推。
  * 不用"准确率"口径（未来价优于买入价即算盈利）——该口径掩盖盈亏比
    且不含成本。本脚本只用**实际持有期收益率**。

前提：信号层允许"全量算一次再回看"，这依赖「历史信号不随后续数据改变」
（PIT），已由 scripts/audit_future_leak_real.py 独立验证（0 违反）。
若该前提被破坏，本层结论作废。

用法：
    .venv/bin/python scripts/audit_can_chanlun_make_money.py --limit 5 --signal-only
    .venv/bin/python scripts/audit_can_chanlun_make_money.py --limit 60

退出码 0 = 跑完（结论可能是"不能赚钱"）；2 = 环境/数据不可用。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from math import sqrt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from _concurrency import resolve_workers  # noqa: E402

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402
from easy_tdx.backtest.engine import BacktestEngine  # noqa: E402
from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy  # noqa: E402

DATA_DIR = ROOT / "audit_data"

HORIZONS = (5, 10, 20, 60)
BUY = {"1buy", "2buy", "2buy_s", "3buy"}
SELL = {"1sell", "2sell", "2sell_s", "3sell"}
MIN_N = 30          # 单类单窗口最低样本量
BOOT = 500          # 随机基准重抽样次数
SEED = 20241002
EXCLUDE = {"sh000300", "sh000001"}   # 指数不做个股择时


def load_universe(limit: int) -> list[Path]:
    # 只选 K 线文件（_daily/_30min/_60min），排除 scan_result.json 等元数据
    _kline_tags = ("_daily", "_30min", "_60min", "_15min", "_5min", "_week", "_month")
    fs = [p for p in sorted(DATA_DIR.glob("*.json"))
          if p.stem.split("_")[0] not in EXCLUDE
          and any(tag in p.stem for tag in _kline_tags)]
    return fs[:limit] if limit else fs


def load_symbol(p: Path) -> tuple[str, pd.DataFrame]:
    code = p.stem.split("_")[0]
    df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
    df["datetime"] = pd.to_datetime(df["datetime"])
    return code, df


# ────────────────────────────── 第一层：信号层 ──────────────────────────────

def _analyze_one(p: Path) -> tuple[str, np.ndarray, list[dict]]:
    """子进程用：算一只标的的缠论信号。返回 (code, closes, rows)。

    ⚠️ 必须定义在模块顶层（ProcessPoolExecutor 需要 pickle），
    不能写成闭包。
    """
    code = p.stem.split("_")[0]
    df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
    df["datetime"] = pd.to_datetime(df["datetime"])
    c = df["close"].to_numpy(dtype=float)
    n = len(c)
    try:
        res = ChanlunAnalyser(
            code=code, frequency="daily", config=ChanlunConfig()
        ).process_klines(df)
    except Exception as e:  # noqa: BLE001
        return code, c, [{"__error__": f"{type(e).__name__}: {e}"}]

    rows = []
    for m in res.mmds:
        if not m.bi:
            continue
        st = m.mmd_type.value.lower()
        if st not in BUY and st not in SELL:
            continue
        idx = int(m.bi.end.bar_index)
        if idx >= n - 1:
            continue
        rows.append({"symbol": code, "type": st, "idx": idx,
                     "conf": float(getattr(m, "confidence", 0.0) or 0.0)})
    return code, c, rows


def collect_signals(files: list[Path], workers: int = 1, verbose: bool = True):
    """并行算缠论，收集 (标的, 类型, bar_index)。

    workers=1 时串行（等价旧行为，用于小样本/对照）；>1 走进程池。
    并行只改速度不改结果：每只标的独立计算，无共享状态。
    """
    rows: list[dict] = []
    closes: dict[str, np.ndarray] = {}

    if workers <= 1:
        results = [_analyze_one(p) for p in files]
    else:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(max_workers=workers) as ex:
            results = list(ex.map(_analyze_one, files, chunksize=1))

    for code, c, rs in results:
        closes[code] = c
        for r in rs:
            if "__error__" in r:
                print(f"  ⚠️ {code} 分析失败: {r['__error__']}")
                continue
            rows.append(r)
    if verbose:
        kinds = Counter(r["type"] for r in rows)
        print(f"  并行度 workers={workers}，成功标的 {len(closes)}/{len(files)}")
    return pd.DataFrame(rows), closes


def _collect_signals_serial(files: list[Path], verbose: bool = True):
    """旧串行实现（保留：作为并行版的等价性对照，见 --check-parallel）。"""
    rows: list[dict] = []
    closes: dict[str, np.ndarray] = {}

    for p in files:
        code, df = load_symbol(p)
        c = df["close"].to_numpy(dtype=float)
        closes[code] = c
        n = len(c)
        try:
            res = ChanlunAnalyser(
                code=code, frequency="daily", config=ChanlunConfig()
            ).process_klines(df)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ {code} 分析失败: {type(e).__name__}: {e}")
            continue
        if verbose:
            kinds = Counter(m.mmd_type.value.lower() for m in res.mmds if m.bi)
            print(f"  {code}: mmds={len(res.mmds)} {dict(kinds)}")
        for m in res.mmds:
            if not m.bi:
                continue
            st = m.mmd_type.value.lower()
            if st not in BUY and st not in SELL:
                continue
            idx = int(m.bi.end.bar_index)
            if idx >= n - 1:
                continue
            rows.append({"symbol": code, "type": st, "idx": idx,
                         "conf": float(getattr(m, "confidence", 0.0) or 0.0)})

    return pd.DataFrame(rows), closes


def fwd_returns(closes: np.ndarray, starts: np.ndarray, horizon: int) -> np.ndarray:
    """从 starts 各点持有 horizon 根的收益率（越界返回 nan）。"""
    n = len(closes)
    valid = starts <= n - 1 - horizon
    out = np.full(len(starts), np.nan)
    if valid.any():
        s = starts[valid]
        out[valid] = closes[s + horizon] / closes[s] - 1.0
    return out


def signal_layer(sig: pd.DataFrame, closes: dict[str, np.ndarray],
                 rng: np.random.Generator) -> dict:
    """缠论信号 vs 同时期同数量随机入场（配对重抽样，向量化）。"""
    out: dict[str, dict] = {}

    for horizon in HORIZONS:
        for st in sorted(BUY | SELL):
            sub = sig[sig["type"] == st]
            if len(sub) < MIN_N:
                continue

            sign = 1.0 if st in BUY else -1.0
            syms = sub["symbol"].to_numpy()
            idxs = sub["idx"].to_numpy()

            real_parts: list[np.ndarray] = []
            rand_draws: list[np.ndarray] = []   # 每个标的的可随机区间上界
            for code in np.unique(syms):
                c = closes[code]
                sel = idxs[syms == code]
                r = fwd_returns(c, sel, horizon) * sign
                real_parts.append(r)
                # 随机基准可从 [0, hi] 抽，hi 与真实信号在同一"可比区间"
                hi = np.minimum(sel, len(c) - 1 - horizon)
                rand_draws.append(np.column_stack([np.full(len(sel), code), hi]))

            real = np.concatenate(real_parts)
            real = real[~np.isnan(real)]
            if len(real) < MIN_N:
                continue

            # 随机基准：每次重抽样，对每个信号在其标的上独立随机取一点
            boot_means = np.empty(BOOT)
            for b in range(BOOT):
                tot, cnt = 0.0, 0
                for part in rand_draws:
                    code = part[0, 0]
                    c = closes[code]
                    hi = part[:, 1].astype(int)
                    ok = hi > 0
                    if not ok.any():
                        continue
                    k = rng.integers(0, hi[ok] + 1)
                    r = c[k + horizon] / c[k] - 1.0
                    tot += float(np.sum(r * sign))
                    cnt += int(ok.sum())
                boot_means[b] = tot / cnt if cnt else np.nan

            boot_means = boot_means[~np.isnan(boot_means)]
            if len(boot_means) < 100:
                continue

            mu = float(real.mean())
            base_mu = float(boot_means.mean())
            base_sd = float(boot_means.std())
            z = (mu - base_mu) / base_sd if base_sd > 0 else float("nan")
            p_emp = float((boot_means >= mu).mean())

            out[f"{st}@{horizon}"] = {
                "n": len(real), "mean": mu, "base_mean": base_mu,
                "excess": mu - base_mu, "z": z, "p_emp": p_emp,
                "win_rate": float((real > 0).mean()),
            }
    return out


# ────────────────────────────── 第二层：策略层 ──────────────────────────────

def strategy_layer(files: list[Path], slippage: float) -> pd.DataFrame:
    """真实回测（含成本）vs 买入持有，逐标的。"""
    rows = []
    for p in files:
        code, df = load_symbol(p)
        try:
            r = BacktestEngine(
                ChanlunStrategy(), cash=100000.0, slippage=slippage
            ).run(df)
            strat = float(r.performance["total_return"])
            bh = float(df["close"].iloc[-1] / df["close"].iloc[0] - 1)
            tr = r.trades
            n_trades = int((tr["direction"] == "SELL").sum()) \
                if isinstance(tr, pd.DataFrame) and not tr.empty else 0
            rows.append({"symbol": code, "strat": strat, "buyhold": bh,
                         "excess": strat - bh, "n_trades": n_trades})
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ {code} 回测失败: {type(e).__name__}: {e}")
    return pd.DataFrame(rows)


def paired_t(d: np.ndarray) -> float:
    if len(d) < 3 or float(np.std(d, ddof=1)) == 0:
        return float("nan")
    return float(np.mean(d) / np.std(d, ddof=1) * sqrt(len(d)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--slippage", type=float, default=0.002)
    ap.add_argument("--signal-only", action="store_true")
    ap.add_argument("--strategy-only", action="store_true")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--workers", type=int, default=None,
                    help="并行度（默认取 _concurrency.DEFAULT_WORKERS=2）")
    ap.add_argument("--check-parallel", action="store_true",
                    help="自检：并行版与串行版信号是否逐位一致")
    a = ap.parse_args()
    workers = resolve_workers(a.workers)

    files = load_universe(a.limit)
    if not files:
        print("❌ 无 audit_data，先跑 scripts/audit_fetch_real_data.py")
        return 2

    rng = np.random.default_rng(a.seed)
    print(f"样本：{len(files)} 只 A股日线（1500 根/只）")
    print(f"种子 {a.seed}  重抽样 {BOOT} 次  滑点 {a.slippage:.2%}  并行度 {workers}")
    print("前提：历史信号不随后续数据改变（PIT）→ 由 audit_future_leak_real.py 验证\n")

    # 并行版必须产出与串行版**逐位一致**的信号，否则加速就是错的。
    if a.check_parallel:
        small = files[:3]
        s_ser, _ = _collect_signals_serial(small, verbose=False)
        s_par, _ = collect_signals(small, workers=workers, verbose=False)
        same = (len(s_ser) == len(s_par)
                and s_ser.sort_values(["symbol", "type", "idx"]).reset_index(drop=True).equals(
                    s_par.sort_values(["symbol", "type", "idx"]).reset_index(drop=True)))
        print(f"[自检] 并行 vs 串行：串行 {len(s_ser)} 条 / 并行 {len(s_par)} 条 → "
              f"{'一致 ✅' if same else '不一致 ❌（并行有 bug，禁止用）'}")
        if not same:
            return 2
        print()

    res: dict = {}
    if not a.strategy_only:
        print("=" * 84)
        print("【第一层】信号层：缠论买卖点 vs 随机入场（配对重抽样）")
        print("=" * 84)
        print("口径：信号后持有 N 根的收益率（卖点取负=押跌），")
        print("      对比「同标的、同窗口、同数量」的随机入场均值。\n")

        sig, closes = collect_signals(files, workers=workers)
        if sig.empty:
            print("❌ 无信号")
            return 2
        print(f"\n信号总数 {len(sig)}，类型分布：")
        for k, v in sig["type"].value_counts().items():
            print(f"  {k:8s} {v}")

        res = signal_layer(sig, closes, rng)
        print("\n%-12s %6s %10s %10s %10s %8s %9s" %
              ("信号@窗口", "样本", "信号均值", "随机基准", "超额", "z", "经验p"))
        print("-" * 84)
        for k in sorted(res, key=lambda x: (res[x].get("type", x), x)):
            v = res[k]
            flag = ""
            if v["p_emp"] < 0.05 and v["excess"] > 0:
                flag = " ✅显著优于随机"
            elif v["p_emp"] < 0.05 and v["excess"] < 0:
                flag = " ❌显著劣于随机"
            print("%-12s %6d %9.2f%% %9.2f%% %9.2f%% %8.2f %9.3f%s" % (
                k, v["n"], v["mean"] * 100, v["base_mean"] * 100,
                v["excess"] * 100, v["z"], v["p_emp"], flag))
        print("-" * 84)
        n_pos = sum(1 for v in res.values() if v["excess"] > 0)
        n_better = sum(1 for v in res.values() if v["excess"] > 0 and v["p_emp"] < 0.05)
        n_worse = sum(1 for v in res.values() if v["excess"] < 0 and v["p_emp"] < 0.05)
        print(f"参与判定 {len(res)} 组：超额为正 {n_pos}，其中显著 {n_better}；显著为负 {n_worse}")

    if a.signal_only:
        return 0

    print("\n" + "=" * 84)
    print("【第二层】策略层：真实回测（佣金0.03%+印花税0.1%+滑点）vs 买入持有")
    print("=" * 84)
    df = strategy_layer(files, a.slippage)
    if len(df) < 3:
        print("❌ 回测样本不足")
        return 2

    d = df["excess"].to_numpy()
    t = paired_t(d)
    print(f"\n标的数            {len(df)}")
    print(f"策略平均收益      {df['strat'].mean()*100:+8.2f}%")
    print(f"买入持有平均      {df['buyhold'].mean()*100:+8.2f}%")
    print(f"平均超额          {df['excess'].mean()*100:+8.2f}%")
    print(f"超额中位数        {np.median(d)*100:+8.2f}%")
    print(f"配对 t            {t:+.2f}")
    print(f"跑赢买入持有比例  {(df['excess'] > 0).mean()*100:.1f}%")
    print(f"平均平仓单数      {df['n_trades'].mean():.1f}")

    half = len(df) // 2
    for name, part in (("前半段", df.iloc[:half]), ("后半段", df.iloc[half:])):
        dd = part["excess"].to_numpy()
        print(f"  {name} n={len(part)} 超额 {dd.mean()*100:+7.2f}%  t={paired_t(dd):+.2f}")

    print("\n" + "=" * 84)
    print("结论判定")
    print("=" * 84)
    sig_ok = bool(res) and n_better > 0 and n_better >= n_worse if res else None
    strat_ok = (not np.isnan(t)) and t > 2 and df["excess"].mean() > 0
    if res:
        if sig_ok and strat_ok:
            print("信号层与策略层**都**支持缠论有效。")
        elif sig_ok and not strat_ok:
            print("信号层有微弱正向，但**传导不到策略层**（扣完成本后不显著）。")
            print("  ⇒ 可做参考，不足以单独作为买卖依据。")
        elif not sig_ok and strat_ok:
            print("信号层不显著、策略层显著 —— 警惕：多半是 beta/暴露差异，")
            print("  而非选股择时能力。")
        else:
            print("两层都不支持「缠论能稳定赚钱」。")
    else:
        print(f"策略层：超额 {df['excess'].mean()*100:+.2f}%，t={t:+.2f}"
              f"（|t|<2 即无法与噪声区分）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
