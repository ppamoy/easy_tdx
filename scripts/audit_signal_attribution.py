#!/usr/bin/env python3
"""V733：把**单笔盈亏**归因到具体信号类型（`tag` 字段）。

为什么要有这个脚本
------------------
`audit_strategy_vs_buyhold.py`（五之五十一）卡在一个地方：

> 回测 trades 只有 BUY/SELL，无信号类型字段 ⇒ 无法把单笔盈亏归因到具体信号

于是「信号层测出 3buy/3sell 为负」与「策略层测出关掉 3buy/3sell 更差」
这两件事**无法互相解释**，只能停在"证据不足，两个方向都不改"。

本脚本补上这一层：给成交打 `tag`（`1buy` / `3buy->1sell` / `3buy->stop_loss`
等），然后**按 tag 聚合单笔收益率**，回答两个问题：

  Q1 开仓信号：1buy 开的仓 vs 3buy 开的仓，扣成本后单笔收益率孰高？
  Q2 平仓信号：被 1sell 平掉的仓 vs 被 3sell 平掉的仓，孰高？

⚠️ 这**不是**"关掉 3sell 会不会更好"的答案 —— 关掉一个信号会改变整个
持仓序列（原本 3sell 平的仓会改由 1sell/止损平掉），是**反事实**问题。
本脚本只能测**条件差**（conditioning），不能测**干预差**（intervention）。
这一点不诚实说明就会变成又一条过度解读的结论。

用法：
    .venv/bin/python scripts/audit_signal_attribution.py
    .venv/bin/python scripts/audit_signal_attribution.py --limit 60

退出码：0 = 跑完（结论可能是"不显著"）；2 = 环境不可用/无数据。
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

# 并行度统一取项目约定（默认 2，本机 4 核），禁止硬编码 4/8
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _concurrency import resolve_workers  # noqa: E402

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from easy_tdx.backtest.engine import BacktestEngine  # noqa: E402
from easy_tdx.backtest.strategies.chanlun import ChanlunStrategy  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "audit_data"
EXCLUDE = {"sh000300", "sh000001"}  # 指数不做个股择时

# 归因口径：tag 形如 "<entry>" 或 "<entry>-><exit_reason>"
# 例：  "1buy"          = 1buy 开仓，尚未平仓（多头持仓中）
#       "1buy->1sell"   = 1buy 开、1sell 平（完整一来回）
#       "3buy->stop_loss" = 3buy 开、止损平
SEP = "->"


def files(limit: int) -> list[Path]:
    fs = [p for p in sorted(DATA.glob("*.json")) if p.stem.split("_")[0] not in EXCLUDE]
    return fs[:limit] if limit else fs


def t_stat(d: np.ndarray) -> float:
    """单样本 t 统计（均值 / 标准误）。"""
    if len(d) < 3 or d.std() == 0:
        return float("nan")
    return float(d.mean() / d.std() * np.sqrt(len(d)))


def _run_one(path_str: str, kw: dict) -> dict:
    """跑单只标的，返回可 pickle 的纯 dict（顶层函数，供 ProcessPoolExecutor）。

    ⚠️ 异常必须**向上抛**而不是吞掉：静默 continue 会让"全部失败"伪装成
    "样本少"，是本脚本最危险的失败模式（见下方 _parallel 的失败计数牙齿）。
    """
    p = Path(path_str)
    df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
    df["datetime"] = pd.to_datetime(df["datetime"])
    r = BacktestEngine(ChanlunStrategy(**kw), cash=100000.0).run(df)
    tr = r.trades
    if not isinstance(tr, pd.DataFrame) or tr.empty:
        return {
            "symbol": p.stem.split("_")[0],
            "rows": [],
            "total_ret": None,
            "n_trades": 0,
            "err": None,
        }
    if "tag" not in tr.columns:
        # 牙齿：tag 缺失说明跑在旧代码上，聚合会全空 ⇒ 不能静默通过
        raise RuntimeError("trades 缺少 tag 列 —— 请确认 backtest 代码已升级")
    closes = tr[(tr["direction"] == "SELL") & (~tr["rejected"]) & (tr["cost_basis"] > 0)]
    rows = [
        {
            "symbol": p.stem.split("_")[0],
            "tag": str(row["tag"]),
            # 单笔收益率 = 已实现盈亏 / 该笔持仓成本
            "ret": float(row["pnl"]) / float(row["cost_basis"]),
        }
        for _, row in closes.iterrows()
    ]
    return {
        "symbol": p.stem.split("_")[0],
        "rows": rows,
        "total_ret": float(closes["pnl"].sum()) / 100000.0 if not closes.empty else None,
        "n_trades": len(closes),
        "err": None,
    }


def _cache_key(symbol: str, kw: dict) -> str:
    """缓存键 = 标的 + 参数（参数不同必须分开存，否则消融两组会互相污染）。"""
    return json.dumps({"symbol": symbol, "kw": kw}, sort_keys=True)


def _parallel(
    fs: list[Path],
    kw: dict,
    workers: int,
    label: str,
    cache_path: Path | None = None,
) -> tuple[list[dict], int]:
    """并行跑一批标的，返回 (结果列表, 失败数)。

    牙齿：失败数 > 0 要**显式报告**。串行版用 `except: continue` 会把
    "全部标的都失败"伪装成"样本少"，跑到全 286 只时尤其危险。
    """
    # ── 缓存：已跑过的标的直接复用，支持超时后续跑 ──
    cache: dict[str, dict] = {}
    if cache_path is not None:
        try:
            if cache_path.exists():
                cache = json.loads(cache_path.read_text(encoding="utf-8"))
                print(f"  缓存：已载入 {len(cache)} 条（{cache_path}）", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ 缓存损坏，从头跑：{e}", flush=True)
            cache = {}

    todo: list[Path] = []
    out: list[dict] = []
    for p in fs:
        key = _cache_key(p.stem.split("_")[0], kw)
        if key in cache:
            out.append(cache[key])
        else:
            todo.append(p)
    if todo:
        print(f"  待跑 {len(todo)} 只（{len(fs) - len(todo)} 只命中缓存）", flush=True)

    nerr = 0

    def _save() -> None:
        if cache_path is None:
            return
        try:
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠️ 缓存写入失败：{e}", flush=True)

    if workers <= 1 or len(todo) <= 1:
        for p in todo:
            try:
                r = _run_one(str(p), kw)
                cache[_cache_key(p.stem.split("_")[0], kw)] = r
                out.append(r)
                _save()
            except Exception as e:  # noqa: BLE001
                nerr += 1
                print(f"  ⚠️ {p.stem} 失败：{type(e).__name__}: {e}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(_run_one, str(p), kw): p for p in todo}
            done = 0
            for fut, p in futs.items():
                try:
                    r = fut.result()
                    cache[_cache_key(p.stem.split("_")[0], kw)] = r
                    out.append(r)
                    done += 1
                    # 每 10 只落盘一次，超时也不丢进度
                    if done % 10 == 0:
                        _save()
                        print(f"    进度 {done}/{len(todo)}", flush=True)
                except Exception as e:  # noqa: BLE001
                    nerr += 1
                    print(f"  ⚠️ {p.stem} 失败：{type(e).__name__}: {e}", flush=True)
        _save()

    if nerr:
        print(f"  ❌【{label}】{nerr}/{len(fs)} 只失败 —— 结论样本已缺失，不可外推", flush=True)
    return out, nerr


def collect(fs: list[Path], workers: int = 0, cache_path: Path | None = None, **kw) -> pd.DataFrame:
    """跑一批回测，返回带 tag 的**已平仓**交易（SELL 且 pnl 有意义）。"""
    w = workers or resolve_workers(None)
    res, _ = _parallel(fs, kw, w, "collect", cache_path=cache_path)
    rows: list[dict] = []
    for r in res:
        rows.extend(r["rows"])
    return pd.DataFrame(rows)


def total_returns(
    fs: list[Path], workers: int = 0, cache_path: Path | None = None, **kw
) -> pd.DataFrame:
    """跑一批回测，返回每只标的的**策略总收益率**（用于消融实验）。

    注意：这里用总资产口径（与 `collect()` 的"单笔等权收益率"**不是同一个东西**），
    故分开采。并行度同 `collect()`。
    """
    w = workers or resolve_workers(None)
    res, _ = _parallel(fs, kw, w, "total_returns", cache_path=cache_path)
    rows: list[dict] = []
    for r in res:
        if r.get("total_ret") is None:
            continue
        rows.append(
            {
                "symbol": r["symbol"],
                # 逐笔收益率按 Symbol 合并成一条资金曲线（各标的独立、等权累加再取均值）
                "total_ret": r["total_ret"],
                "n_trades": r["n_trades"],
            }
        )
    return pd.DataFrame(rows)


def ablation(fs: list[Path], label: str, workers: int = 0, cache_path: Path | None = None) -> None:
    """真正的**干预差**：把某个信号关掉，端到端对比总收益。

    ⚠️ 这才回答"关掉 X 会更好吗"。上面的 `report()` 只能给条件差。
    """
    w = workers or resolve_workers(None)
    print(f"\n{'=' * 78}\n【干预实验｜{label}】每组 {len(fs)} 只，并行度 {w}")

    kw = {"use_3sell": False}
    base = total_returns(fs, workers=w, cache_path=cache_path)
    alt = total_returns(fs, workers=w, cache_path=cache_path, **kw)
    if base.empty or alt.empty:
        print("  ❌ 某组无结果，无法比较")
        return

    def _stat(d: pd.DataFrame, name: str) -> None:
        v = d["total_ret"].to_numpy()
        t = t_stat(v)
        print(
            f"  {name:<22} 均 {v.mean() * 100:+.2f}%  中位 {np.median(v) * 100:+.2f}%"
            f"  总笔数 {int(d['n_trades'].sum())}  t={t:+.2f}"
        )

    _stat(base, "默认(3sell 开)")
    _stat(alt, "关掉 3sell")
    v0, v1 = base["total_ret"].to_numpy(), alt["total_ret"].to_numpy()
    if len(v0) >= 5 and len(v1) >= 5:
        d = v1.mean() - v0.mean()
        se = np.sqrt(v0.var(ddof=1) / len(v0) + v1.var(ddof=1) / len(v1))
        t = d / se if se > 0 else float("nan")
        verdict = "更差" if d < 0 else ("更好" if d > 0 else "相同")
        print(
            f"  ⇒ 关掉后 {verdict} {d * 100:+.2f}pp  t={t:+.2f}"
            f"{'（不显著）' if abs(t) < 2 else '（显著）'}"
        )
    print("  ⚠️ 口径：总收益 = Σpnl / 初始资金（各标的独立、等权），**未做复利**")


def _entry(tag: str) -> str:
    return tag.split(SEP)[0] if SEP in tag else tag


def _exit(tag: str) -> str:
    return tag.split(SEP)[1] if SEP in tag else ""


def report(X: pd.DataFrame, label: str) -> None:
    if X.empty:
        print(f"【{label}】无已平仓交易")
        return
    X = X.copy()
    X["entry"] = X["tag"].map(_entry)
    X["exit"] = X["tag"].map(_exit)

    print(f"\n{'=' * 78}\n【{label}】已平仓 {len(X)} 笔，覆盖 {X['symbol'].nunique()} 只")

    def _grp(col: str, title: str) -> None:
        print(f"\n{title}")
        print(f"  {'标签':<12}{'n':>6}{'均值%':>9}{'中位%':>9}{'胜率':>8}{'t':>8}")
        print("  " + "-" * 52)
        g = X.groupby(col)["ret"]
        for k, v in sorted(g, key=lambda kv: -len(kv[1])):
            if len(v) < 5:
                continue
            a = v.to_numpy()
            t = t_stat(a)
            print(
                f"  {k:<12}{len(a):>6}{a.mean() * 100:>9.2f}{np.median(a) * 100:>9.2f}"
                f"{(a > 0).mean() * 100:>7.0f}%{t:>8.2f}"
            )

    _grp("entry", "Q1 按**开仓**信号分组（该信号开的仓，最终实现的单笔收益率）")
    _grp("exit", "Q2 按**平仓**信号分组（该信号平的仓，其单笔收益率）")

    # 关键对照：1buy vs 3buy 开仓（信号层说 3buy 有害）
    a = X[X["entry"] == "1buy"]["ret"].to_numpy()
    b = X[X["entry"] == "3buy"]["ret"].to_numpy()
    if len(a) >= 5 and len(b) >= 5:
        d = a.mean() - b.mean()
        # Welch 近似（两组独立、方差不等）
        se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        t = d / se if se > 0 else float("nan")
        print(
            f"\n  关键对照 1buy 开仓 vs 3buy 开仓："
            f"{a.mean() * 100:+.2f}% vs {b.mean() * 100:+.2f}%  "
            f"差 {d * 100:+.2f}pp  t={t:+.2f}"
            f"{'（|t|<2 不显著）' if abs(t) < 2 else '（|t|>=2 显著）'}"
        )

    a = X[X["exit"] == "1sell"]["ret"].to_numpy()
    b = X[X["exit"] == "3sell"]["ret"].to_numpy()
    if len(a) >= 5 and len(b) >= 5:
        d = a.mean() - b.mean()
        se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        t = d / se if se > 0 else float("nan")
        print(
            f"  关键对照 1sell 平仓 vs 3sell 平仓："
            f"{a.mean() * 100:+.2f}% vs {b.mean() * 100:+.2f}%  "
            f"差 {d * 100:+.2f}pp  t={t:+.2f}"
            f"{'（|t|<2 不显著）' if abs(t) < 2 else '（|t|>=2 显著）'}"
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40, help="标的数量上限，0=全部")
    ap.add_argument(
        "--cache",
        default="/tmp/attr_cache.json",
        help="逐标的缓存（可按 --limit 增量续跑，超时/中断后不丢已完成部分）",
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=0,
        help="并行度，0=取项目默认（_concurrency.resolve_workers，本机 2）",
    )
    ap.add_argument(
        "--ablation", action="store_true", help="跑真正的干预实验（关掉 3sell 端到端对比总收益）"
    )
    ap.add_argument(
        "--only-ablation",
        action="store_true",
        help="只跑干预实验，跳过单笔归因报告（后者要再跑一遍全样本回测，很慢）",
    )
    ap.add_argument(
        "--enable-2s",
        action="store_true",
        help=(
            "开 use_2s_signals=True 后再归因。⚠️ 必须显式开：该开关默认 False，"
            "默认参数下 2buy_s/2sell_s 一笔都不会出现（实测不是 n 小，是 n=0）"
        ),
    )
    a = ap.parse_args()
    fs = files(a.limit)
    if not fs:
        print("❌ 无 audit_data，先跑 audit_fetch_real_data.py")
        return 2

    print("单笔盈亏归因：把 trades 的 pnl 归因到具体信号类型")
    print("口径：单笔收益率 = pnl / cost_basis（已扣佣金+印花税+滑点）")
    print("样本：默认参数 ChanlunStrategy，cash=10 万，日线")

    # ⚠️ 单笔归因要跑一遍全样本回测；干预实验要再跑两遍（默认组 + 开关组）。
    #    本机 4 核，两者叠起来会顶到 run_bg 超时 ⇒ 支持 --only-ablation 只跑后者。
    cp = Path(a.cache)
    # ⚠️ 2buy_s/2sell_s 在默认参数下根本不触发（use_2s_signals 默认 False，n=0 而非 n 小）。
    #    要归因它们就必须显式开这个开关 —— 且开了之后 cnt=60 门槛要相应放宽。
    main_kw = {"use_2s_signals": True} if a.enable_2s else {}
    if main_kw:
        print(f"⚠️ 已开 {main_kw} —— 注意这与「默认参数」口径不同，不可直接对比默认组")
    X = (
        collect(fs, workers=a.workers, cache_path=cp, **main_kw)
        if not a.only_ablation
        else pd.DataFrame()
    )
    if not a.only_ablation:
        if X.empty:
            print("❌ 没有任何已平仓交易 —— 归因无法进行")
            return 2

        # ── 牙齿：tag 必须真的带上了信号类型，否则本脚本等于空转 ──
        tagged = X[X["tag"] != ""]
        if tagged.empty:
            print("\n❌ 牙齿不成立：所有交易的 tag 都是空 ⇒ 归因字段没生效，结果不可信")
            return 1
        known = {"1buy", "2buy", "3buy", "2buy_s"}
        entries = {_entry(t) for t in X["tag"].unique()}
        if not (entries & known):
            print(f"\n❌ 牙齿不成立：tag 里没有任何已知开仓信号类型（见到 {sorted(entries)}）")
            return 1
        print(
            f"\n✅ 牙齿：{len(tagged)}/{len(X)} 笔带 tag，含开仓类型 {sorted(entries & known)}"
            f" ⇒ 归因字段生效"
        )

        report(X, "默认(3buy/3sell 开)")

    if a.ablation or a.only_ablation:
        # ⚠️ 必须传 cache_path：消融两组（默认 / use_3sell=False）靠 kw 区分缓存键，
        #    不传就完全没有缓存，跑到全样本超时时进度全丢。
        ablation(fs, "3sell", workers=a.workers, cache_path=cp)

    print("\n" + "=" * 78)
    print("⚠️ 怎么读这个结果（别过度解读）")
    print("  0) take_profit 胜率 100% / stop_loss 胜率 0% 是**同义反复**（触发条件就是价格达标），")
    print("     不是预测能力，别拿它当证据。")
    print("  1) 这里是**条件差**（给定「这笔由 3sell 平掉」的平均收益），")
    print("     不是**干预差**（「关掉 3sell 会怎样」）。关掉信号会改变持仓序列，")
    print("     原本由它平的仓会改由其它信号/止损平掉 —— 本脚本测不到。")
    print("  2) 单笔收益率与「策略总收益」不同：前者等权于笔数，后者受仓位/复利影响。")
    print("  3) 样本为日线 A 股、默认参数、未 beta 中性化，n 只股票。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
