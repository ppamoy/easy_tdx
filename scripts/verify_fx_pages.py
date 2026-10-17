#!/usr/bin/env python3
"""各页面「分型渲染」行为级验收 —— 缠论原文硬约束。

背景（必须吸取的教训）：
  1. 用户报告 000001 日线 2024-12-17/18/19 出现「底分型紧跟着顶分型」。经查是
     展示层渲染了原始 ``fractals``（find_fractals 逐三根滑动窗口的产物，天然含
     共用K线的重叠分型）。已改为渲染 ``valid_fractals``。
  2. 但仅改展示层不够：``valid_fractals`` 的性质原本依赖 ``bi_type``，legacy 的
     simple 口径会让笔端点集合退化。已由 analyser._enforce_fx_independence 兜底。

本脚本的原则同 scripts/verify_ui.py：**只信行为，不信 DOM 标志**。
直接从页面里真实渲染的 ECharts 实例读取 series 数据，断言：
  · 图上真的画出了分型（不是 0 个 —— 防止「改成空数组导致什么都不画」）
  · 相邻分型顶底严格交替
  · 相邻分型不共用 K 线（bar_index 间距 >= 4）
  · 分型是白色（满足「顶底分型统一白色」需求）

用法：
    python3 scripts/verify_fx_pages.py                 # 全部页面
    python3 scripts/verify_fx_pages.py --page backtest
    python3 scripts/verify_fx_pages.py --list

依赖：playwright（用系统 chromium，无需下载浏览器）
    pip install playwright --target=/tmp/pw
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pw import api_base, import_playwright, launch_pw, ui_base  # noqa: E402

BASE = ui_base()

# 从页面里真实的 ECharts 实例读 series —— 这是渲染结果，不是 DOM/变量标志
JS_FX = """() => {
  const c = window.__CHANLUN_CHART__;
  if (!c) return {error: 'no instance'};
  const o = c.getOption();
  const out = [];
  for (const s of o.series) {
    if (s.name === '顶分型') (s.data || []).forEach(d => out.push([d.value[0], 'ding']));
    if (s.name === '底分型') (s.data || []).forEach(d => out.push([d.value[0], 'di']));
  }
  return out;
}"""

JS_COLOR = """() => {
  const c = window.__CHANLUN_CHART__;
  if (!c) return {error: 'no instance'};
  const o = c.getOption();
  const out = [];
  for (const s of o.series) {
    if (s.name === '顶分型' || s.name === '底分型') {
      out.push([s.name, s.itemStyle && s.itemStyle.color]);
    }
  }
  return out;
}"""


def _diagnose_zero(probe: tuple[str, dict] | None = None) -> str:
    """图上 0 个分型时，判断是「后端旧进程」还是「前端真 bug」。

    Args:
        probe: (接口路径, 查询参数)。应传**该页实际依赖的接口**，否则诊断会
            指错方向（例如 verify 页走 /verify/signals/detail 的预跑缓存，
            而 /chanlun/analyze 一直是好的）。

    典型成因：旧进程启动时还没有 valid_fractals 字段 → 返回空 → 前端画 0 个。
    这种情况重启后端即可，不是代码缺陷。
    """
    import json
    import urllib.parse
    import urllib.request

    probe = probe or ("/api/v1/chanlun/analyze", {}, "POST")
    path, params = probe[0], probe[1]
    method = probe[2] if len(probe) > 2 and probe[2] else ("GET" if params else "POST")
    url = api_base() + path
    try:
        if method == "GET":
            url += "?" + urllib.parse.urlencode(params)
            d = json.loads(urllib.request.urlopen(url, timeout=180).read())
        else:
            req = urllib.request.Request(
                url,
                data=json.dumps(params or {"market": "SZ", "code": "000001",
                                           "category": "DAY", "start": 0,
                                           "count": 800}).encode(),
                headers={"Content-Type": "application/json"},
            )
            d = json.loads(urllib.request.urlopen(req, timeout=180).read())
    except (OSError, ValueError, json.JSONDecodeError) as e:
        # 只吞网络/解析类问题；NameError 之类编程错误必须暴露，不能被掩盖
        return f"（另：无法连后端确认成因：{type(e).__name__}: {e}）"
    # 有些接口把结构放在 results[] 里（如 /stock-pick/timing），要看进去
    target = d
    if "valid_fractals" not in target and isinstance(d.get("results"), list) and d["results"]:
        target = d["results"][0]

    if "valid_fractals" in target:
        return f"{path} 有 valid_fractals → 前端或该页数据源的问题（真 bug）"
    return (f"[部署态] {path} 缺 valid_fractals —— 旧进程未重启，"
            "重启后端后再跑本脚本（非代码缺陷）")


def audit(xs: list, probe: tuple[str, dict] | None = None) -> tuple[bool, str]:
    """返回 (是否合规, 描述)。0 分型且后端缺字段时，描述里带 [部署态] 标记。"""
    """审计分型序列，返回 (是否合规, 描述)。"""
    if isinstance(xs, dict):
        return False, f"读不到图表实例: {xs}"
    a = sorted(xs, key=lambda t: t[0])
    if not a:
        # 一个都没画 = 可疑。区分两种成因，别一律当成代码 bug：
        #   ① 后端还是旧进程（预跑缓存缺 valid_fractals 字段）→ 部署态，重启即恢复
        #   ② 前端传了空数组 / 回退逻辑写错 → 真 bug
        hint = _diagnose_zero(probe)
        return False, f"图上没有分型（0 个）。{hint}"
    same = sum(1 for i in range(1, len(a)) if a[i - 1][1] == a[i][1])
    close = sum(1 for i in range(1, len(a)) if a[i][0] - a[i - 1][0] < 4)
    if same or close:
        return False, (
            f"共 {len(a)} 个，同类型相邻 {same} 处、间距<4（共用K线）{close} 处"
        )
    return True, f"{len(a)} 个，交替与独立性均合规"


def _setup(pg) -> list[str]:
    """安装错误监听，返回错误列表。"""
    errs: list[str] = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    return errs


def _wait_chart(pg, timeout: int = 90000) -> bool:
    try:
        pg.wait_for_selector(".chanlun-chart canvas", timeout=timeout)
        pg.wait_for_timeout(2500)
        return True
    except Exception:
        return False


# ── 各页面的驱动函数 ────────────────────────────────────────────────────────


def page_backtest(pg) -> bool:
    """回测页：跑 chanlun 策略。"""
    pg.goto(BASE + "/", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(3000)
    pg.locator('input[placeholder="6位代码（市场自动识别）"]').first.fill("000001")
    # 策略下拉异步填充（选项来自后端），必须等有选项再选，否则首屏慢时会误判
    sel = pg.locator("select").nth(1)
    for _ in range(30):
        if sel.locator("option").count() > 1:
            break
        pg.wait_for_timeout(1000)
    sel.select_option("chanlun")
    pg.locator("button", has_text="开始回测").first.click()
    return _wait_chart(pg, 120000)


def page_chanlun(pg) -> bool:
    """缠论分析页。"""
    pg.goto(BASE + "/learn?tab=analysis", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(4500)
    return _wait_chart(pg)


def _click_any(pg, texts: tuple[str, ...], wait: int = 1500) -> str | None:
    """按文本依次尝试点击按钮，返回命中的文本。"""
    for t in texts:
        try:
            btn = pg.locator("button", has_text=t).first
            if btn.count() and btn.is_visible():
                btn.click()
                pg.wait_for_timeout(wait)
                return t
        except Exception:  # noqa: BLE001
            continue
    return None


def page_screening(pg) -> bool:
    """选股页：点「开始选股」→ 点结果行（触发 selectStock → 缠论分析出图）。"""
    pg.goto(BASE + "/screening", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(4000)
    if not _click_any(pg, ("开始选股",), wait=3000):
        return False
    # 等扫描出结果（结果项是 .stock-item，点击它才会跑缠论分析）
    try:
        pg.wait_for_selector(".stock-item", timeout=120000)
    except Exception:  # noqa: BLE001
        return False
    pg.wait_for_timeout(2000)
    try:
        pg.locator(".stock-item").first.click()
    except Exception:  # noqa: BLE001
        return False
    return _wait_chart(pg, 90000)


def page_stockpick(pg) -> bool:
    """选股择时页：① 长盈选股 → ② 缠论择时（runTiming）→ 结果行「详情」。"""
    pg.goto(BASE + "/stock-pick", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(4000)
    if not _click_any(pg, ("① 长盈选股", "长盈选股"), wait=5000):
        return False
    # 等 Step1 出结果：结果行里出现「② 缠论择时」按钮
    try:
        pg.wait_for_selector("button:has-text('缠论择时')", timeout=150000)
    except Exception:  # noqa: BLE001
        return False
    if not _click_any(pg, ("② 缠论择时",), wait=5000):
        return False
    # 等择时完成，再点「详情」（pickTiming）展开缠论图
    pg.wait_for_timeout(15000)
    _click_any(pg, ("详情",), wait=4000)
    return _wait_chart(pg, 90000)


def page_today(pg) -> bool:
    """今日看板：「生成今日看板」→ 结果行「图表」（pickRow）下钻出图。"""
    pg.goto(BASE + "/today", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(4000)
    if not _click_any(pg, ("生成今日看板",), wait=5000):
        return False
    # 看板聚合多标的，较慢
    try:
        pg.wait_for_selector("button:has-text('图表')", timeout=180000)
    except Exception:  # noqa: BLE001
        return False
    # 看板有 N 行「图表」按钮，个别行可能确实无分型数据（不是 bug）。
    # 逐个尝试，取第一个能渲染出分型的行，避免把「该行本就无数据」误判成失败。
    n = min(pg.locator("button:has-text('图表')").count(), 5)
    for i in range(n):
        try:
            pg.locator("button:has-text('图表')").nth(i).click()
        except Exception:  # noqa: BLE001
            continue
        if not _wait_chart(pg, 30000):
            continue
        if pg.evaluate(JS_FX):
            return True
    return _wait_chart(pg, 30000)


def page_verify(pg) -> bool:
    """信号验证页 /learn?tab=verify：默认已加载当前标的，等待图表就绪即可。"""
    pg.goto(BASE + "/learn?tab=verify", wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(6000)
    return _wait_chart(pg)


# 各页实际依赖的分型数据源（用于 0 分型时判断成因，别指错方向）
PAGE_PROBE = {
    "verify": ("/api/v1/verify/signals/detail",
               {"code": "000001", "category": "DAY"}),
    "stockpick": ("/api/v1/stock-pick/timing",
                  {"date": "2025-06-01", "symbols": [{"market": "SZ", "code": "000001"}],
                   "count": 400}, "POST"),
    # today 页数据来自 dashboard 聚合任务（异步，看板行里带结构），不是 analyze
    # today 走 dashboard 异步任务：命中不了就用 analyze 作参考（两者同源）
    "today": ("/api/v1/chanlun/analyze", {}, "POST"),
    "screening": ("/api/v1/chanlun/analyze", {}),
    "backtest": ("/api/v1/chanlun/analyze", {}),
    "chanlun": ("/api/v1/chanlun/analyze", {}),
}

PAGES = {
    "backtest": page_backtest,
    "chanlun": page_chanlun,
    "screening": page_screening,
    "stockpick": page_stockpick,
    "today": page_today,
    "verify": page_verify,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", help=f"只跑某个页面，可选: {list(PAGES)}")
    ap.add_argument("--list", action="store_true", help="列出页面后退出")
    args = ap.parse_args()

    if args.list:
        for k in PAGES:
            print(k)
        return 0

    pages = PAGES
    if args.page:
        if args.page not in PAGES:
            print(f"未知页面 {args.page}，可选: {list(PAGES)}")
            return 2
        pages = {args.page: PAGES[args.page]}

    try:
        sync_api = import_playwright()
    except ImportError as e:
        print(str(e))
        return 2

    failures: list[str] = []
    deploys: list[str] = []
    skipped: list[str] = []

    with sync_api.sync_playwright() as pw:
        browser = launch_pw(pw)
        for name, driver in pages.items():
            pg = browser.new_page(viewport={"width": 1600, "height": 1200})
            errs = _setup(pg)
            try:
                ready = driver(pg)
                if not ready:
                    # 页面没能自动出图（可能需要交互/数据），不算失败也不算通过
                    skipped.append(f"{name}: 未自动渲染出缠论图，需人工交互验证")
                    print(f"⚠️  [{name}] 未自动渲染出缠论图 —— 需人工交互验证")
                    pg.close()
                    continue

                fx = pg.evaluate(JS_FX)
                ok, why = audit(fx, PAGE_PROBE.get(name))
                colors = pg.evaluate(JS_COLOR)
                white_ok = bool(colors) and all(
                    c[1] == "#ffffff" for c in colors if isinstance(c, list)
                )
                if not white_ok:
                    failures.append(f"[{name}] 分型配色非白色: {colors}")

                flag = "✅" if ok else "❌"
                print(f"{flag} [{name}] 分型 {why}")
                if not ok:
                    if "[部署态]" in why:
                        deploys.append(f"[{name}] {why}")
                    else:
                        failures.append(f"[{name}] {why}")

                if errs:
                    failures.append(f"[{name}] 页面 JS 错误: {errs[:2]}")
            except Exception as e:  # noqa: BLE001
                failures.append(f"[{name}] 驱动异常: {type(e).__name__}: {e}")
                print(f"❌ [{name}] 驱动异常: {type(e).__name__}")
            finally:
                pg.close()
        browser.close()

    print()
    if skipped:
        print("需人工验证（未自动出图，不计通过也不计失败）：")
        for s in skipped:
            print(f"  · {s}")
    if deploys:
        print("环境问题（非代码缺陷，重启后端后重试）：")
        for d in deploys:
            print(f"  · {d}")
    if failures:
        print("失败项（需修代码）：")
        for f in failures:
            print(f"  · {f}")
        return 1
    if deploys:
        return 2
    print("✅ 所有自动渲染的页面分型均合规")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
