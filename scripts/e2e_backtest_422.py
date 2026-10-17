#!/usr/bin/env python3
"""V724：回测页「选择缠论 → 422」的真实浏览器端到端验证。

为什么需要这个脚本
------------------
2026-10-13 用户报：easy_tdx 回测选择缠论，控制台
  `:3012/api/v1/backtest/run:1 Failed to load resource: 422 (Unprocessable Entity)`

根因（已用真实请求复现，不是猜）：
  回测页默认区间 2020-01-06 起 → SymbolPicker.loadBars() 带 startDate 调
  fetchBars → fetchBarsDirect 的翻页循环发 start=0,800,1600... 共 10 页；
  但后端 /bars?start_date= 走 fetch_bars_range（klines.py:259），它自己翻页
  并按区间切片，**忽略 start**，于是每页都返回整个区间（1500 根）。前端把
  10 页全 concat ⇒ 15000 根，POST /backtest/run 撞上
  `BacktestRequest.ohlcv max_length=2000` ⇒ 422 too_long。

  与策略无关（chanlun / changying_chanlun / ma_cross 全复现），
  只是缠论页默认区间最长，所以用户以为「选缠论才报错」。

AGENTS.md §1：不能拿「DOM 里有下拉框」冒充验证，必须断言**真实行为**——
所以本脚本真的在浏览器里点「开始回测」，并监听 CDP Network 事件，断言：
  1. /api/v1/bars 请求次数不再是无脑 10 页（修前 10 次 / 修后 ≤2 次）；
  2. POST /api/v1/backtest/run 真的发出且 **HTTP 200**（修前 422）；
  3. 页面上真的出现回测结果（绩效区域有内容，不是空白）。

用法：
    .venv/bin/python scripts/e2e_backtest_422.py [--base http://127.0.0.1:3012]
                                                  [--shot /tmp/backtest_422.png]
退出码：0 = 全通过；1 = 有断言失败；2 = 环境不可用。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

# 回测页是 SPA 根路由；标的选择器 + 策略下拉 + 「开始回测」按钮都在这一页。
PAGE = "/"
CHROME_CANDIDATES = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")


def find_chrome() -> str | None:
    for c in CHROME_CANDIDATES:
        p = shutil.which(c)
        if p:
            return p
    return None


async def main_async(base: str, shot: str | None, wait_s: float) -> int:
    try:
        import websockets
    except ImportError:
        print("❌ 未安装 websockets，无法驱动浏览器")
        return 2

    chrome = find_chrome()
    if not chrome:
        print("❌ 未找到 chromium/chrome")
        return 2

    port = 9222
    prof = Path("/tmp/e2e_backtest_422_profile")
    if prof.exists():
        shutil.rmtree(prof)
    prof.mkdir(parents=True)

    proc = subprocess.Popen(
        [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
         "--window-size=1500,1100",
         f"--remote-debugging-port={port}", f"--user-data-dir={prof}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        ws_url = None
        for _ in range(60):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as r:
                    info = json.loads(r.read().decode())
                ws_url = info.get("webSocketDebuggerUrl")
                if ws_url:
                    break
            except Exception:
                await asyncio.sleep(0.5)
        if not ws_url:
            print("❌ DevTools 端口未就绪")
            return 2

        async with websockets.connect(ws_url, max_size=None) as ws:
            msg_id = 0
            events: list[dict] = []

            async def send(method: str, params: dict | None = None, session: str | None = None):
                nonlocal msg_id
                msg_id += 1
                payload = {"id": msg_id, "method": method, "params": params or {}}
                if session:
                    payload["sessionId"] = session
                await ws.send(json.dumps(payload))
                while True:
                    raw = await ws.recv()
                    d = json.loads(raw)
                    if d.get("id") == msg_id:
                        return d
                    events.append(d)

            # attach 到第一个 page。⚠️ /json/list 的字段名是 **id** 不是 targetId
            # （用 targetId 会 KeyError；Target.attachToTarget 才要 targetId）。
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as r:
                targets = json.loads(r.read().decode())
            page_target = next((t for t in targets if t.get("type") == "page"), None)
            if not page_target:
                print("❌ 没有 page target")
                return 2
            tid = page_target.get("targetId") or page_target.get("id")
            if not tid:
                print(f"❌ page target 无 id 字段：{page_target}")
                return 2
            await send("Target.attachToTarget", {"targetId": tid, "flatten": True})
            session = None
            for e in events:
                if e.get("method") == "Target.attachedToTarget":
                    session = e["params"]["sessionId"]
                    break
            events.clear()
            if not session:
                print("❌ 未拿到 sessionId")
                return 2

            await send("Network.enable", {}, session)
            await send("Page.enable", {}, session)

            reqs: dict[str, dict] = {}
            # 记录 POST /backtest/run 的响应体（用来证明回测真的出了结果）
            bodies: dict[str, str] = {}

            async def eval_js(expr: str, sid: str):
                d = await send("Runtime.evaluate",
                               {"expression": expr, "returnByValue": True, "awaitPromise": True},
                               sid)
                res = d.get("result", {}).get("result", {})
                return res.get("value")

            await send("Page.navigate", {"url": base + PAGE}, session)
            t_load = time.time()
            loaded = False
            while time.time() - t_load < 25:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                d = json.loads(raw)
                if d.get("method") == "Page.loadEventFired":
                    loaded = True
                    break
                _collect(d, reqs)
            print(f"  主文档 load: {'是' if loaded else '超时'}")

            # 等策略列表拉取完（/backtest/strategies 200）——下拉框有选项才选得到缠论
            t0 = time.time()
            while time.time() - t0 < 20:
                if any("/backtest/strategies" in r["url"] for r in reqs.values()):
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                _collect(json.loads(raw), reqs)

            # 选「缠论买卖点」策略（真实用户操作：改 select 的 value 并触发 change）
            await eval_js(
                "(() => {"
                "  const sel = [...document.querySelectorAll('select')]"
                "    .find(s => [...s.options].some(o => o.value === 'chanlun'));"
                "  if (!sel) return 'no-select';"
                "  sel.value = 'chanlun';"
                "  sel.dispatchEvent(new Event('change', {bubbles: true}));"
                "  return sel.value;"
                "})()",
                session,
            )
            await asyncio.sleep(1.0)  # 等 Vue 响应式把参数表单/默认参数刷完

            # 清掉之前导航阶段攒的 /bars 请求，只统计本次回测产生的
            reqs.clear()
            bodies.clear()

            # 点「开始回测」（真实点击，不是直接调 API）
            clicked = await eval_js(
                "(() => {"
                "  const btn = [...document.querySelectorAll('button')]"
                "    .find(b => (b.textContent || '').includes('开始回测'));"
                "  if (!btn) return false;"
                "  btn.click();"
                "  return true;"
                "})()",
                session,
            )
            print(f"  点击「开始回测」: {'是' if clicked else '否'}")

            # 等回测请求落地并拿到响应（最多 wait_s）
            # ⚠️ 不能一看到 /backtest/run 就 break —— 响应要几百毫秒后才到，
            # 提前 break 会让 status 一直是 None（假失败）。必须等到
            # responseReceived/loadingFailed 真的出现。
            t0 = time.time()
            while time.time() - t0 < wait_s:
                if _run_settled(reqs):
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                d = json.loads(raw)
                _collect(d, reqs)
                if d.get("method") == "Network.responseReceived":
                    rid = d["params"]["requestId"]
                    if rid in reqs and reqs[rid].get("url", "").endswith("/backtest/run"):
                        # 拿到响应头时立刻取体（此时体已完整，dataReceived 时机太早
                        # 常读到空串，导致「真结果」断言假失败）
                        try:
                            chunk = await send(
                                "Network.getResponseBody", {"requestId": rid}, session
                            )
                            b = chunk.get("result", {}).get("body", "")
                            if b:
                                bodies[rid] = b
                        except Exception:
                            pass

            # ── 汇总断言 ────────────────────────────────────────────────
            bars_reqs = [r for r in reqs.values() if "/api/v1/bars" in r["url"]]
            run_reqs = [r for r in reqs.values() if r["url"].endswith("/backtest/run")]
            print(f"\n本次回测捕获 /api/v1/bars 请求：{len(bars_reqs)} 次")
            for r in bars_reqs:
                print(f"    {r.get('status', 'FAIL')}  {r['url'][:120]}")
            print(f"POST /api/v1/backtest/run：{len(run_reqs)} 次")
            for r in run_reqs:
                print(f"    {r.get('status', 'FAIL')}  {r['method']} {r['url'][:120]}")

            ok = True

            # 断言 1：backtest/run 真的发出
            fired = len(run_reqs) > 0
            print(f"\n[{'PASS' if fired else 'FAIL'}] POST /backtest/run 真的发出")
            ok &= fired

            # 断言 2：HTTP 200（修前是 422）
            bad = [r for r in run_reqs if r.get("status") != 200 or r.get("failed")]
            ok_status = fired and not bad
            print(f"[{'PASS' if ok_status else 'FAIL'}] /backtest/run 返回 HTTP 200"
                  + (f"（异常：{[(r['url'][:60], r.get('status')) for r in bad][:3]}）" if bad else ""))
            ok &= ok_status

            # 断言 3：响应体是真回测结果（含 performance.total_trades），不是空壳
            has_result = False
            for rid, b in bodies.items():
                try:
                    j = json.loads(b)
                except Exception:
                    continue
                if isinstance(j, dict) and "performance" in j:
                    has_result = True
                    perf = j.get("performance", {})
                    print(f"    回测结果：total_trades={perf.get('total_trades')} "
                          f"total_return={perf.get('total_return')}")
                    break
            print(f"[{'PASS' if has_result else 'FAIL'}] 响应体含 performance（真结果，非空壳）")
            ok &= has_result

            # 断言 4：/bars 请求次数不再是无脑 10 页（修前 10 次）
            ok_bars = 0 < len(bars_reqs) <= 2
            print(f"[{'PASS' if ok_bars else 'FAIL'}] /bars 请求 ≤2 次"
                  f"（实际 {len(bars_reqs)}；修前固定 10 次并把重复数据 concat 成 15000 根）")
            ok &= ok_bars

            # 断言 5：页面真的渲染出回测结果（绩效卡片有数字，不是空白）
            rendered = await eval_js(
                "(() => {"
                "  const t = document.body.innerText || '';"
                "  return /总收益率|年化收益|交易次数|夏普/.test(t);"
                "})()",
                session,
            )
            print(f"[{'PASS' if rendered else 'FAIL'}] 页面渲染出绩效指标文本")
            ok &= bool(rendered)

            if shot:
                try:
                    d = await send("Page.captureScreenshot", {"format": "png"}, session)
                    data = d.get("result", {}).get("data")
                    if data:
                        Path(shot).write_bytes(__import__("base64").b64decode(data))
                        print(f"\n截图已存：{shot}")
                except Exception as e:
                    print(f"截图失败：{e}")

            return 0 if ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def _run_settled(reqs: dict) -> bool:
    """/backtest/run 是否已拿到响应（有 status 或 failed），而不是刚发出。"""
    for r in reqs.values():
        if r["url"].endswith("/backtest/run"):
            if "status" in r or "failed" in r:
                return True
    return False


def _collect(d: dict, reqs: dict) -> None:
    m = d.get("method", "")
    if m == "Network.requestWillBeSent":
        r = d["params"]["request"]
        reqs[d["params"]["requestId"]] = {"url": r["url"], "method": r["method"]}
    elif m == "Network.responseReceived":
        rid = d["params"]["requestId"]
        if rid in reqs:
            reqs[rid]["status"] = d["params"]["response"]["status"]
    elif m == "Network.loadingFailed":
        rid = d["params"]["requestId"]
        if rid in reqs:
            reqs[rid]["failed"] = d["params"].get("errorText", "?")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:3012")
    ap.add_argument("--shot", default="/tmp/backtest_422.png")
    ap.add_argument("--wait", type=float, default=90.0)
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main_async(a.base, a.shot, a.wait)))
