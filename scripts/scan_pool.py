#!/usr/bin/env python3
"""对股票池全量跑融合分析，筛出可操作信号，输出报告。

## 做什么
1. 从缓存读取每只股票的日线 + 30分K线
2. 运行缠论分析提取买卖点
3. 运行 HybridEngine 融合分析（方向过滤+技术评分+决策）
4. 筛出 execute 信号
5. 输出 JSON 报告到 audit_data/scan_result.json（前端可读）

## 数据源
全部从本地缓存读（audit_data/ + audit_data_min/），不连 TDX。

## 用法
    # 全量扫描
    .venv/bin/python scripts/scan_pool.py

    # 只扫前 5 只（冒烟）
    .venv/bin/python scripts/scan_pool.py --limit 5

    # 只输出 execute 信号
    .venv/bin/python scripts/scan_pool.py --execute-only

## 定时
    # refresh_data 之后跑
    0 17 * * 1-5  cd /home/skp/workspace/easy_tdx && .venv/bin/python scripts/scan_pool.py >> /tmp/scan_pool.log 2>&1
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import pandas as pd  # noqa: E402

from _concurrency import resolve_workers  # noqa: E402
from easy_tdx.chanlun import ChanlunAnalyser, ChanlunConfig  # noqa: E402
from easy_tdx.fusion import HybridEngine, ChanlunSignal  # noqa: E402
from easy_tdx.fusion.hybrid_engine import TREE, GRAIN, GRASS  # noqa: E402

DAILY_DIR = ROOT / "audit_data"
MIN_DIR = ROOT / "audit_data_min"
OUT_FILE = DAILY_DIR / "scan_result.json"

# 扫描时只取最近 N 根 K线（减少计算量；30min 500根≈10交易日，daily 300根≈1.5年）
SCAN_30MIN_BARS = 500
SCAN_DAILY_BARS = 300

# 股票名称（已知池子）
STOCK_NAMES = {
    "600000": "浦发银行", "600036": "招商银行", "601318": "中国平安",
    "600276": "恒瑞医药", "600030": "中信证券", "000333": "美的集团",
    "000651": "格力电器", "000725": "京东方A", "300750": "宁德时代",
    "002415": "海康威视",
}

# gpcw 财报数据（全局加载一次）
_GPCW_FRAME = None


def _get_gpcw_frame():
    """加载 gpcw 财报数据帧（首次调用时加载，之后缓存）。"""
    global _GPCW_FRAME
    if _GPCW_FRAME is not None:
        return _GPCW_FRAME
    from easy_tdx.fundamental.indicators import load_all_periods_frame
    from easy_tdx.fundamental.cache import cache_stats
    from easy_tdx.fundamental.pipeline import pick_report_zips
    zips = pick_report_zips(date.today())
    if not zips:
        zips = [z["filename"] for z in cache_stats().get("zips", [])]
    if zips:
        _GPCW_FRAME = load_all_periods_frame(zips)
        print(f"  gpcw 财报加载: {len(_GPCW_FRAME)} rows", flush=True)
    else:
        print("  ⚠️ 无 gpcw 财报数据", flush=True)
    return _GPCW_FRAME


def _load_json(path: Path) -> pd.DataFrame:
    """从 JSON 缓存加载 K线 DataFrame。"""
    if not path.exists():
        return pd.DataFrame()
    rows = json.loads(path.read_text("utf-8"))
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    return df


def _extract_signals(result, df: pd.DataFrame, level: str = "30min") -> list[ChanlunSignal]:
    """从缠论分析结果提取信号列表。"""
    type_map = {
        "1buy": "buy_1", "2buy": "buy_2", "2buy_s": "buy_2", "3buy": "buy_3",
        "1sell": "sell_1", "2sell": "sell_2", "2sell_s": "sell_2", "3sell": "sell_3",
    }
    signals = []
    for mmd in result.mmds:
        sig_type = type_map.get(mmd.mmd_type.value, mmd.mmd_type.value)
        price = float(mmd.bi.end.val) if mmd.bi else 0.0
        zs_range = [float(mmd.zs.zd), float(mmd.zs.zg)] if mmd.zs else []
        beichi = 0.0
        if hasattr(mmd, "beichi_force") and mmd.beichi_force:
            beichi = float(mmd.beichi_force)
        elif mmd.confidence:
            beichi = float(mmd.confidence) * 0.5
        signals.append(ChanlunSignal(
            signal_type=sig_type, level=level, price=price,
            confidence=float(mmd.confidence) if mmd.confidence else 0,
            beichi_force=beichi,
            zhongshu_range=zs_range,
        ))
    return signals


def _get_season() -> tuple[str, dict]:
    """用 PRD pipeline 判断当前季节（detect_season_for_date）。

    该函数内部有缓存（V713），重复调用不会重复取指数。
    """
    from easy_tdx.fundamental.pipeline import detect_season_for_date
    try:
        sr = detect_season_for_date(date.today())
        if sr:
            season = getattr(sr, "season", "unknown")
            signals = {}
            if hasattr(sr, "signals"):
                s = sr.signals
                if isinstance(s, dict):
                    signals = s
            return season, signals
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️ 季节判断失败: {e}", flush=True)
    return "unknown", {}


def _scan_one(code: str, market: str, season: str, season_signals: dict) -> dict | None:
    """扫描一只股票，返回分析结果 dict。

    注意：此函数在子进程中运行，HybridEngine 每次新建。
    """
    engine = HybridEngine()
    name = STOCK_NAMES.get(code, code)
    daily_path = DAILY_DIR / f"{market.lower()}{code}_daily.json"
    min30_path = MIN_DIR / f"{market.lower()}{code}_30min.json"

    df_daily = _load_json(daily_path)
    df_30min = _load_json(min30_path)
    if df_daily.empty or df_30min.empty:
        return None

    # 只取最近 N 根（扫描不需要全量历史）
    df_30min = df_30min.tail(SCAN_30MIN_BARS).reset_index(drop=True)
    df_daily = df_daily.tail(SCAN_DAILY_BARS).reset_index(drop=True)

    # 30min 缠论分析
    cfg = ChanlunConfig(zs_from_xd=False)
    analyser = ChanlunAnalyser(code=f"{market}{code}", frequency="30min", config=cfg)
    result = analyser.process_klines(df_30min)
    signals = _extract_signals(result, df_30min, "30min")

    # 日线缠论分析（趋势确认+日线信号）
    analyser_d = ChanlunAnalyser(code=f"{market}{code}", frequency="daily", config=cfg)
    result_d = analyser_d.process_klines(df_daily)
    daily_signals = _extract_signals(result_d, df_daily, "daily")

    # 树粮草分类（按 PRD F6：gpcw 财报 → pick_report → screen_stock）
    screen = None
    indicators = {}
    frame = _get_gpcw_frame()
    if frame is not None and not frame.empty:
        from easy_tdx.fundamental.indicators import pick_report
        from easy_tdx.fundamental.screener import screen_stock
        row = pick_report(frame, code, date.today(), market=market)
        if row is not None:
            row_dict = row.to_dict() if hasattr(row, "to_dict") else dict(row)
            indicators = {k: v for k, v in row_dict.items()
                         if k not in ("code", "market")}
            screen_row = {"code": code, "market": market, **row_dict}
            screen = screen_stock(screen_row)

    # 季节结果（构造简单对象）
    class SeasonObj:
        def __init__(self):
            self.season = season
            self.signals = season_signals
        def label(self):
            return {"spring": "春", "summer": "夏", "autumn": "秋",
                    "winter": "冬", "unknown": "未知"}.get(self.season, "未知")
        def info(self):
            return f"{self.label()}季"
    season_obj = SeasonObj()

    # 运行融合引擎
    hybrid = engine.analyze(
        code=code, market=market,
        klines_df=df_30min, signals=signals,
        screen_result=screen, season_result=season_obj,
        daily_df=df_daily, daily_signals=daily_signals,
    )

    d = hybrid.as_dict()
    d["name"] = name
    d["code"] = code
    d["market"] = market
    return d


def _scan_one_wrapper(args: tuple) -> dict | None:
    """ProcessPoolExecutor map 用的包装器。"""
    code, market, season, season_signals = args
    try:
        return _scan_one(code, market, season, season_signals)
    except Exception as e:  # noqa: BLE001
        print(f"  ❌ {code}: {type(e).__name__}: {e}", flush=True)
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="全池融合分析扫描")
    ap.add_argument("--limit", type=int, default=0, help="只扫前 N 只（0=全部）")
    ap.add_argument("--execute-only", action="store_true", help="只输出 execute 信号")
    a = ap.parse_args()

    # 加载季节判断（按 PRD F7）
    season, season_signals = _get_season()
    print(f"=== 全池扫描 ===")
    print(f"当前季节: {season}")
    print()

    # 股票池
    codes = []
    for p in sorted(DAILY_DIR.glob("*_daily.json")):
        name = p.stem.replace("_daily", "")
        if name in ("sh000001", "sh000300"):
            continue
        market = "SH" if name.startswith("sh") else "SZ"
        code = name[2:]
        codes.append((code, market, name))

    if a.limit:
        codes = codes[: a.limit]

    print(f"扫描 {len(codes)} 只...\n")

    results = []
    execute_signals = []
    t0 = time.time()

    from concurrent.futures import ProcessPoolExecutor
    workers = resolve_workers(None)
    jobs = [(code, market, season, season_signals) for code, market, _ in codes]

    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, d in enumerate(ex.map(_scan_one_wrapper, jobs, chunksize=1)):
            if d:
                results.append(d)
                if d.get("final_signal") == "execute":
                    execute_signals.append(d)
                    name = d.get("name", d.get("code"))
                    sig = d.get("latest_signal", {})
                    cat = d.get("category_label", "")
                    print(f"  ✅ {name}({d.get('code')}) {cat} | "
                          f"信号:{sig.get('signal_type','')} | "
                          f"决策:{d.get('final_signal')} | "
                          f"{(d.get('final_reason','') or '')[:60]}")

            if (i + 1) % 10 == 0 or i + 1 == len(codes):
                print(f"  进度 {i+1}/{len(codes)}  ({time.time()-t0:.0f}s)", flush=True)

    el = time.time() - t0

    # P2-8：板块优先排序——按行业板块涨跌幅强弱重排结果
    try:
        from easy_tdx.fundamental.sector_priority import enrich_results_with_sector
        results = enrich_results_with_sector(results)
        execute_signals = enrich_results_with_sector(execute_signals)
        print(f"  板块优先排序: 已应用 (前 5 强势板块)", flush=True)
    except Exception as exc:
        print(f"  板块优先排序: 跳过 ({exc})", flush=True)

    # 输出报告
    report = {
        "scan_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scan_date": str(date.today()),
        "elapsed_seconds": round(el, 1),
        "season": season,
        "season_signals": season_signals,
        "total_scanned": len(results),
        "execute_count": len(execute_signals),
        "results": results,
        "execute_signals": execute_signals if not a.execute_only else None,
    }

    OUT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== 扫描完成 ({el:.1f}s) ===")
    print(f"  总计: {len(results)} 只")
    print(f"  执行: {len(execute_signals)} 只")
    print(f"  报告: {OUT_FILE}")

    if execute_signals:
        print(f"\n{'='*80}")
        print(f"  可操作信号（{len(execute_signals)} 只）")
        print(f"{'='*80}")
        for d in execute_signals:
            name = d.get("name", d.get("code"))
            cat = d.get("category_label", "")
            sig = d.get("latest_signal", {})
            score = d.get("score", {}).get("total", "N/A")
            reason = (d.get("final_reason", "") or "")[:80]
            print(f"  {name:8s} | {cat:4s} | {sig.get('signal_type',''):8s} | "
                  f"评分{score} | {reason}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
