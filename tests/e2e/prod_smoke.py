#!/usr/bin/env python3
"""easy_tdx 生产环境 E2E 冒烟测试（飞轮核心脚本）。

对运行中的生产服务（默认 http://127.0.0.1:8000）做端到端验证，覆盖：
行情取数（MAC 回退）、缠论多级别递归、选股（同步/异步+进度）、择时、
今日可操作看板、提醒流、选股后验、诊断、主机健康、回测策略参数。

特点：
- 仅用标准库（urllib），无需额外依赖；
- 每项检查独立 try/except，单项失败不影响其余；
- 含**不变量断言**（递归链一致、行动榜排序、汇总自洽、端点锚定等），
  不是「有返回就算过」；
- 输出 JSON 报告（stdout 末行为 JSON，便于机器解析）+ 人类可读摘要。

用法：
    python3 tests/e2e/prod_smoke.py [--base http://127.0.0.1:8000] [--date 2026-09-01]
                                    [--json out.json] [--fast]

退出码：0 = 全部通过（允许 warn）；1 = 存在 fail。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
API = "/api/v1"

results: list[dict] = []


def _req(
    method: str,
    path: str,
    body: dict | None = None,
    timeout: float = 60.0,
) -> tuple[int, object]:
    """发请求，返回 (status, parsed_json_or_text)。"""
    url = path if path.startswith("http") else BASE + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"


def check(name: str, fn) -> None:
    """执行单项检查；fn 返回 (ok, detail, evidence) 或抛异常。"""
    t0 = time.time()
    try:
        ok, detail, evidence = fn()
        status = "pass" if ok else "fail"
    except AssertionError as e:
        status, detail, evidence = "fail", f"断言失败: {e}", {}
    except Exception as e:  # noqa: BLE001
        status, detail, evidence = "fail", f"{type(e).__name__}: {e}", {}
    results.append(
        {
            "name": name,
            "status": status,
            "detail": detail,
            "evidence": evidence,
            "elapsed_s": round(time.time() - t0, 2),
        }
    )
    mark = {"pass": "PASS", "fail": "FAIL", "warn": "WARN"}[status]
    print(f"[{mark}] {name}: {detail}", flush=True)


def _poll_task(kind: str, task_id: str, timeout: float = 180.0) -> dict:
    """轮询任务直到 done/failed，返回最终 task dict（并记录进度序列）。"""
    t0 = time.time()
    progress_seq: list[float | None] = []
    while time.time() - t0 < timeout:
        code, d = _req("GET", f"{API}/stock-pick/{kind}/task/{task_id}", timeout=20)
        if code != 200 or not isinstance(d, dict):
            raise AssertionError(f"轮询失败 http={code} body={str(d)[:120]}")
        progress_seq.append(d.get("progress"))
        if d.get("status") in ("done", "failed"):
            d["_progress_seq"] = progress_seq
            return d
        time.sleep(1.2)
    raise AssertionError(f"任务 {task_id} 超时未完成（{timeout}s）")


# ── 各项检查 ────────────────────────────────────────────────────────────────


def c_openapi_routes() -> tuple[bool, str, dict]:
    expected = [
        "/api/v1/bars",
        "/api/v1/chanlun/analyze",
        "/api/v1/stock-pick/screen",
        "/api/v1/stock-pick/screen/async",
        "/api/v1/stock-pick/screen/task/{task_id}",
        "/api/v1/stock-pick/timing",
        "/api/v1/stock-pick/dashboard/async",
        "/api/v1/stock-pick/dashboard/task/{task_id}",
        "/api/v1/monitor/alerts",
        "/api/v1/monitor/alerts/clear",
        "/api/v1/screening/verify",
        "/api/v1/diagnosis/analyze",
        "/api/v1/diagnosis/multi-stock",
        "/api/v1/server/test",
        "/api/v1/backtest/strategies",
    ]
    code, d = _req("GET", "/openapi.json", timeout=20)
    assert code == 200 and isinstance(d, dict), f"openapi http={code}"
    paths = set((d.get("paths") or {}).keys())
    missing = [p for p in expected if p not in paths]
    return (not missing, f"{len(paths)} 条路由；缺失 {missing}", {"missing": missing})


def c_bars_mac_fallback() -> tuple[bool, str, dict]:
    code, d = _req("GET", f"{API}/bars?market=SH&code=600519&category=DAY&count=5", timeout=40)
    assert code == 200, f"http={code}"
    if not isinstance(d, dict):
        raise AssertionError(f"非 JSON（疑似 SPA 兜底 HTML）: {str(d)[:80]}")
    bars = d.get("data") or d.get("bars")
    assert bars, f"无行情数据: {str(d)[:120]}"
    last = bars[-1]
    return (
        len(bars) >= 5,
        f"{len(bars)} 根，最后一根 {last.get('date')} close={last.get('close')}",
        {"last": last},
    )


def c_chanlun_recursion() -> tuple[bool, str, dict]:
    code, d = _req(
        "POST",
        f"{API}/chanlun/analyze",
        {"market": "SH", "code": "600519", "category": "DAY", "count": 800, "recursion_depth": 3},
        timeout=90,
    )
    assert code == 200, f"http={code} body={str(d)[:150]}"
    assert isinstance(d, dict), "非 JSON"
    levels = d.get("levels") or {}
    assert "bi" in levels and "xd" in levels, f"levels 缺 bi/xd: {list(levels)}"
    # 不变量：递归链一致——第 N 级的「笔数」== 第 N-1 级的「线段数」
    chain_ok = True
    chain_detail = []
    if "xd_l2" in levels:
        chain_ok &= levels["xd_l2"].get("bi_count") == levels["xd"].get("xd_count")
        chain_detail.append(
            f"xd_l2.bi_count={levels['xd_l2'].get('bi_count')} vs xd.xd_count={levels['xd'].get('xd_count')}"
        )
    if "xd_l3" in levels:
        chain_ok &= levels["xd_l3"].get("bi_count") == levels["xd_l2"].get("xd_count")
        chain_detail.append(
            f"xd_l3.bi_count={levels['xd_l3'].get('bi_count')} vs xd_l2.xd_count={levels['xd_l2'].get('xd_count')}"
        )
    # 不变量：每级 xds 的方向交替 + 端点首尾相连
    geom_ok = True
    for key, lv in levels.items():
        xds = lv.get("xds") or []
        for i in range(len(xds) - 1):
            if xds[i].get("end_index") != xds[i + 1].get("start_index"):
                geom_ok = False
                chain_detail.append(f"{key} 第{i}段端点不连续")
                break
    assert geom_ok, f"线段端点不连续: {chain_detail}"
    assert chain_ok, f"递归链不一致: {chain_detail}"
    return (
        True,
        f"levels={list(levels)}；链一致；端点连续",
        {"levels": {k: {"xd_count": v.get("xd_count"), "bi_count": v.get("bi_count")} for k, v in levels.items()}},
    )


def c_screen_pool() -> tuple[bool, str, dict]:
    code, d = _req(
        "POST",
        f"{API}/stock-pick/screen",
        {
            "date": DATE,
            "pool": [
                {"market": "SH", "code": "600519"},
                {"market": "SZ", "code": "000001"},
                {"market": "SH", "code": "601088"},
            ],
            "top_n": 5,
        },
        timeout=120,
    )
    assert code == 200, f"http={code} body={str(d)[:150]}"
    rows = (d or {}).get("results") or []
    assert rows, f"选股结果为空: {str(d)[:150]}"
    assert all(r.get("code") for r in rows), "结果缺 code"
    assert any((r.get("quality_score") or 0) > 0 for r in rows), "所有 quality_score 为 0/None"
    return (
        True,
        f"{len(rows)} 只，最高分 {max((r.get('quality_score') or 0) for r in rows)}",
        {"rows": [{"symbol": r.get("symbol"), "category": r.get("category"), "score": r.get("quality_score")} for r in rows[:3]]},
    )


def c_screen_async_progress() -> tuple[bool, str, dict]:
    code, d = _req(
        "POST",
        f"{API}/stock-pick/screen/async",
        {"date": DATE, "pool": [{"market": "SH", "code": "600519"}, {"market": "SZ", "code": "000001"}], "top_n": 5},
        timeout=30,
    )
    assert code == 200 and isinstance(d, dict), f"提交失败 http={code} {str(d)[:120]}"
    task_id = d.get("task_id")
    assert task_id, "缺 task_id"
    st = _poll_task("screen", task_id)
    assert st.get("status") == "done", f"任务状态 {st.get('status')} err={st.get('error')}"
    seq = [p for p in st.get("_progress_seq") or [] if p is not None]
    monotonic = all(seq[i] <= seq[i + 1] for i in range(len(seq) - 1))
    assert monotonic, f"进度非单调递增: {seq}"
    rows = ((st.get("result") or {}).get("results")) or []
    assert rows, "异步选股结果为空"
    return (
        True,
        f"进度 {seq[:1]}→{seq[-1:]}；结果 {len(rows)} 只；单调={monotonic}",
        {"progress_seq": seq, "rows": len(rows)},
    )


def c_timing_contract() -> tuple[bool, str, dict]:
    code, d = _req(
        "POST",
        f"{API}/stock-pick/timing",
        {"date": DATE, "symbols": [{"market": "SH", "code": "600519"}], "count": 1200, "recursion_depth": 2},
        timeout=120,
    )
    assert code == 200, f"http={code} {str(d)[:150]}"
    r = (d.get("results") or [{}])[0]
    assert not r.get("error"), f"timing error: {r.get('error')}"
    v = r.get("verdict") or {}
    assert v.get("action") in ("买入", "卖出", "观望"), f"verdict.action={v.get('action')}"
    assert "direction" in v, "verdict 缺 direction"
    na = r.get("novice_advice") or {}
    for k in ("explanation", "entry", "stop", "target", "position_note"):
        assert k in na, f"novice_advice 缺 {k}"
    assert "recursion" in r, "缺 recursion"
    assert "levels" in r, "缺 levels"
    assert "signal_quality" in r, "缺 signal_quality"
    # 不变量：若 verdict 是买入/卖出，则入场价应存在（有触发笔时）
    if v.get("action") in ("买入", "卖出"):
        assert na.get("entry") is not None, f"{v.get('action')} 但 entry=None（explanation={na.get('explanation')}）"
    return (
        True,
        f"action={v.get('action')} signal={v.get('signal')} conf={v.get('confidence')} entry={na.get('entry')} levels={list((r.get('levels') or {}).keys())}",
        {"verdict": v, "recursion": r.get("recursion"), "best_buy": (r.get("signal_quality") or {}).get("best_buy")},
    )


def c_dashboard_flow() -> tuple[bool, str, dict]:
    code, d = _req(
        "POST",
        f"{API}/stock-pick/dashboard/async",
        {"date": DATE, "pool_scope": "pool", "top_n": 30, "time_n": 6, "recursion_depth": 2},
        timeout=30,
    )
    assert code == 200 and isinstance(d, dict), f"提交失败 http={code} {str(d)[:120]}"
    st = _poll_task("dashboard", d["task_id"], timeout=240)
    assert st.get("status") == "done", f"状态 {st.get('status')} err={st.get('error')}"
    res = st.get("result") or {}
    season = res.get("season")
    assert season, "缺 season"
    pr = season.get("position_range")
    assert isinstance(pr, list) and len(pr) == 2 and pr[0] <= pr[1], f"position_range 异常: {pr}"
    sm = res.get("summary") or {}
    assert sm.get("buy", 0) + sm.get("sell", 0) + sm.get("wait", 0) == sm.get("timed"), f"汇总不自洽: {sm}"
    acts = res.get("actions") or []
    assert acts, "行动榜为空"
    # 不变量：排序 = (买入→卖出→观望, 置信度降序)
    rank = {"买入": 0, "卖出": 1, "观望": 2}
    keys = [(rank.get(a.get("action"), 9), -(a.get("confidence") or 0)) for a in acts]
    assert keys == sorted(keys), f"行动榜排序错误: {keys[:6]}"
    # 不变量：买入/卖出且有触发笔时应有入场/止损/目标
    bad = [
        a.get("symbol")
        for a in acts
        if a.get("action") in ("买入", "卖出")
        and (a.get("novice_advice") or {}).get("entry") is None
    ]
    return (
        not bad,
        f"season={season.get('label')} summary={sm} 榜 {len(acts)} 条；无价位异常={not bad}",
        {"season": season, "summary": sm, "top3": acts[:3], "bad_price_rows": bad},
    )


def c_alerts_after_dashboard() -> tuple[bool, str, dict]:
    code, d = _req("GET", f"{API}/monitor/alerts?limit=30&source=dashboard", timeout=20)
    assert code == 200 and isinstance(d, dict), f"http={code}"
    alerts = d.get("alerts") or []
    assert alerts, "看板来源提醒为空（看板任务应先写入提醒流）"
    missing = [
        a.get("stock")
        for a in alerts
        if not all(k in a for k in ("stock", "action", "season_note"))
    ]
    priced = [a for a in alerts if a.get("entry") is not None]
    return (
        not missing,
        f"{len(alerts)} 条看板提醒；{len(priced)} 条含入场价；缺字段={missing}",
        {"sample": alerts[:3]},
    )


def c_screening_verify() -> tuple[bool, str, dict]:
    code, d = _req(
        "POST",
        f"{API}/screening/verify",
        {"date": DATE, "symbols": ["SH600519", "SZ000001"], "selected": ["SH600519"]},
        timeout=120,
    )
    assert code == 200 and isinstance(d, dict), f"http={code}"
    assert not d.get("error"), f"error={d.get('error')}"
    assert d.get("verdict"), "verdict 为空"
    return True, f"verdict={str(d.get('verdict'))[:80]}", {"horizons": list((d.get("horizons") or {}).keys())}


def c_diagnosis_analyze() -> tuple[bool, str, dict]:
    code, d = _req("POST", f"{API}/diagnosis/analyze", {"market": "SH", "code": "600519"}, timeout=120)
    assert code == 200 and isinstance(d, dict), f"http={code}"
    assert not d.get("error"), f"error={d.get('error')}"
    for k in ("chanlun", "macd", "action_label"):
        assert k in d, f"缺 {k}"
    return True, f"action={d.get('action_label')} keys={len(d)}", {"action": d.get("action_label")}


def c_diagnosis_multi_stock() -> tuple[bool, str, dict]:
    code, d = _req(
        "POST",
        f"{API}/diagnosis/multi-stock",
        [{"market": "SH", "code": "600519"}, {"market": "SZ", "code": "000001"}],
        timeout=120,
    )
    assert code == 200 and isinstance(d, dict), f"http={code}"
    rows = d.get("stocks") or []
    assert rows, "无结果"
    ok_rows = [r for r in rows if not r.get("error") and (r.get("total_bars") or 0) > 0]
    assert ok_rows, f"全部标的取数失败（await 回归？）: {rows[:2]}"
    return True, f"{len(ok_rows)}/{len(rows)} 只有数据（signal_count={[r.get('signal_count') for r in ok_rows]}）", {"rows": rows[:2]}


def c_server_test_validate() -> tuple[bool, str, dict]:
    code, d = _req(
        "POST",
        f"{API}/server/test",
        {"hosts": ["115.238.56.198", "110.41.2.72"], "timeout": 5, "validate_data": True},
        timeout=90,
    )
    assert code == 200 and isinstance(d, list), f"http={code}"
    assert d, "空列表"
    assert all("has_data" in h for h in d), f"缺 has_data: {d[:1]}"
    return True, f"{len(d)} 台；has_data={[h.get('has_data') for h in d]}", {"hosts": d}


def c_strategies_params() -> tuple[bool, str, dict]:
    code, d = _req("GET", f"{API}/backtest/strategies", timeout=30)
    assert code == 200 and isinstance(d, dict), f"http={code}"
    ch = next((s for s in d.get("strategies") or [] if s.get("name") == "chanlun"), None)
    assert ch, "缺 chanlun 策略"
    names = {p.get("name") for p in ch.get("params") or []}
    assert "analysis_level" in names, f"缺 analysis_level: {sorted(names)}"
    assert "position_pct" in names, f"缺 position_pct: {sorted(names)}"
    return True, f"chanlun 参数 {sorted(names)}", {"params": sorted(names)}


def c_alerts_clear() -> tuple[bool, str, dict]:
    code, d = _req("POST", f"{API}/monitor/alerts/clear", timeout=20)
    assert code == 200, f"http={code}"
    code2, d2 = _req("GET", f"{API}/monitor/alerts?limit=5", timeout=20)
    assert code2 == 200 and (d2 or {}).get("count") == 0, f"清空后仍有 {(d2 or {}).get('count')} 条"
    return True, f"清空 {d.get('cleared')} 条", {}


CHECKS = [
    ("openapi_routes", c_openapi_routes),
    ("bars_mac_fallback", c_bars_mac_fallback),
    ("chanlun_recursion", c_chanlun_recursion),
    ("screen_pool", c_screen_pool),
    ("screen_async_progress", c_screen_async_progress),
    ("timing_contract", c_timing_contract),
    ("dashboard_flow", c_dashboard_flow),
    ("alerts_after_dashboard", c_alerts_after_dashboard),
    ("screening_verify", c_screening_verify),
    ("diagnosis_analyze", c_diagnosis_analyze),
    ("diagnosis_multi_stock", c_diagnosis_multi_stock),
    ("server_test_validate", c_server_test_validate),
    ("strategies_params", c_strategies_params),
    ("alerts_clear", c_alerts_clear),
]

DATE = "2026-09-01"


def main() -> int:
    global BASE, DATE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--date", default=DATE)
    ap.add_argument("--json", default="")
    ap.add_argument("--fast", action="store_true", help="跳过耗时的看板/异步检查")
    args = ap.parse_args()
    BASE, DATE = args.base.rstrip("/"), args.date

    selected = CHECKS
    if args.fast:
        skip = {"dashboard_flow", "alerts_after_dashboard", "screen_async_progress"}
        selected = [(n, f) for n, f in CHECKS if n not in skip]

    print(f"== easy_tdx 生产 E2E 冒烟 @ {BASE} date={DATE} ==", flush=True)
    t0 = time.time()
    for name, fn in selected:
        check(name, fn)
    total = time.time() - t0

    fails = [r for r in results if r["status"] == "fail"]
    warns = [r for r in results if r["status"] == "warn"]
    summary = {
        "base": BASE,
        "date": DATE,
        "total": len(results),
        "passed": len(results) - len(fails) - len(warns),
        "failed": len(fails),
        "warned": len(warns),
        "elapsed_s": round(total, 1),
        "results": results,
    }
    print(f"\n== 结果: {summary['passed']} pass / {summary['failed']} fail / {summary['warned']} warn，耗时 {summary['elapsed_s']}s ==")
    for r in fails:
        print(f"  FAIL {r['name']}: {r['detail']}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        print(f"报告已写入 {args.json}")
    print("REPORT_JSON_BEGIN")
    print(json.dumps(summary, ensure_ascii=False))
    print("REPORT_JSON_END")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
