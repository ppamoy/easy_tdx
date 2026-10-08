#!/usr/bin/env python3
"""V733：缠论前端端到端验证 —— 用真实浏览器（Chromium + CDP）验证。

为什么不用单测代替
------------------
AGENTS.md 明确要求：不能用「DOM 里存在控件」冒充验证（历史教训：缠论图的
下拉框渲染出来了，但 `chanlun/analyze` 请求**根本没发**，图上是裸 K 线）。
所以本脚本断言的是**真实行为**：
  1. 打开真实页面（http://127.0.0.1:8000）
  2. 监听 CDP 的 Network 事件
  3. 断言缠论相关请求**真的发出且 HTTP 200**
  4. 断言返回体里含有真实结构（笔/中枢/信号），而不是空壳
  5. 截图留证（人工/视觉模型可复核）

用法：
    .venv/bin/python scripts/e2e_chanlun_browser.py [--base http://127.0.0.1:8000]
                                                    [--shot /tmp/chanlun.png]

退出码：0 = 断言全通过；1 = 有断言失败；2 = 环境不可用（无法下结论）。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import shutil
import subprocess
import time
from pathlib import Path

DEFAULT_BASE = "http://127.0.0.1:8000"
# 缠论分析页的真实路由（web-ui/src/router.ts:23：`/chanlun` 重定向到
# `/learn?tab=analysis`；ChanlunView.vue:909 在该页调用 /chanlun/analyze）。
# ⚠️ 只打开根路径是**不够的** —— 根路径是回测页，不会发 chanlun 请求。
# 这正是 AGENTS.md 案例 A 的翻版：必须走到真正触发请求的那个页面。
CHANLUN_PAGE = "/learn?tab=analysis"
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
    prof = Path("/tmp/e2e_chanlun_profile")
    if prof.exists():
        shutil.rmtree(prof)
    prof.mkdir(parents=True)

    proc = subprocess.Popen(
        [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
         "--window-size=1400,1000",
         f"--remote-debugging-port={port}", f"--user-data-dir={prof}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        # 等 DevTools 端口就绪
        ws_url = None
        import urllib.request
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

            events: list[dict] = []
            replies: list[dict] = events
            await send("Target.attachToTarget", {"targetId": (await _first_page(port)), "flatten": True})
            session = None
            for e in events:
                if e.get("method") == "Target.attachedToTarget":
                    session = e["params"]["sessionId"]
                    break
            events.clear()

            await send("Network.enable", {}, session)
            await send("Page.enable", {}, session)

            # 单一 recv 循环：既收事件、也收命令响应（已验证可行的模式）。
            # ⚠️ 第一版用「后台 pump + 同步 send 各自 recv」会互相抢消息，
            # 导致只捕获到 1 个请求而误判为"请求没发出"。
            reqs: dict[str, dict] = {}
            t0 = time.time()
            # ⚠️ 竞态：必须在 attach + Network.enable 之后才 navigate，
            # 且等 Page.loadEventFired，否则请求会漏捕（实测会时好时坏）。
            await send("Page.navigate", {"url": base + CHANLUN_PAGE}, session)
            # 等主文档 load
            t_load = time.time()
            loaded = False
            while time.time() - t_load < 20:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                d = json.loads(raw)
                if d.get("method") == "Page.loadEventFired":
                    loaded = True
                    break
                if d.get("method") == "Network.requestWillBeSent":
                    r = d["params"]["request"]
                    reqs[d["params"]["requestId"]] = {"url": r["url"], "method": r["method"]}
            print(f"  主文档 load: {'是' if loaded else '超时'}")
            while time.time() - t0 < wait_s:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                d = json.loads(raw)
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
                else:
                    events.append(d)

            # 汇总请求

            # ⚠️ 只认**接口**请求。ChanlunChart.js/css 这些静态资源名字里也含
            # "chanlun"，若一并计入会让断言被资源加载"喂饱"而失去意义
            # （即使 analyze 没发也能 PASS —— 正是 AGENTS.md 要防的假验证）。
            chanlun = [r for r in reqs.values()
                       if "/api/v1/chanlun/" in r["url"]]
            print(f"\n页面加载完成，共捕获 {len(reqs)} 个请求")
            print(f"其中 chanlun **接口**请求：{len(chanlun)}")
            for r in chanlun:
                print(f"  {r.get('status', 'FAIL')}  {r['method']}  {r['url'][:110]}")

            # 断言 1：缠论请求真的发出
            ok_fired = len(chanlun) > 0
            print(f"\n[{'PASS' if ok_fired else 'FAIL'}] 缠论请求真的发出（不是只有空壳 UI）")

            # 断言 2：全部 200
            bad = [r for r in chanlun if r.get("status") != 200 or r.get("failed")]
            ok_status = not bad and ok_fired
            print(f"[{'PASS' if ok_status else 'FAIL'}] 缠论请求全部 HTTP 200"
                  + (f"（异常：{[r['url'][:70] for r in bad][:3]}）" if bad else ""))

            # 断言 3：直接打接口，确认返回真实结构（不是空壳）
            # ⚠️ /api/v1/chanlun/analyze 是 **POST**（第一版用 GET 必然 404）
            import urllib.request
            probe_ok, probe_detail = False, "未尝试"
            # 正确 schema（web/schemas.py ChanlunRequest）：market/code，不是 symbol
            payload = {"market": "SH", "code": "600519", "category": "DAY", "count": 500}
            try:
                req = urllib.request.Request(
                    base + "/api/v1/chanlun/analyze",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=40) as r:
                    body = json.loads(r.read().decode())
                src = body if "bis" in body else body.get("result", body.get("data", {}))
                bis = src.get("bis") or []
                zss = src.get("zss") or []
                mmds = src.get("mmds") or []
                if len(bis) > 0:
                    probe_ok = True
                probe_detail = f"POST chanlun/analyze → bis={len(bis)} zss={len(zss)} mmds={len(mmds)}"
            except Exception as e:
                probe_detail = f"POST chanlun/analyze → {e}"
            print(f"[{'PASS' if probe_ok else 'FAIL'}] 缠论接口返回真实结构（{probe_detail}）")

            # 截图
            # ============ 渲染验证（真实像素，不是存在性断言）============
            # AGENTS.md 案例 A 的教训：canvas 存在 ≠ 图真的画出来了。
            # 这里读 canvas 的**实际像素**：非背景像素占比 + 出现红/绿蜡烛色。
            # 我自己踩过的坑（都记在注释里，别再犯）：
            #  - 只判断 canvas.width>0 → 画布空也能 PASS；
            #  - 不看像素直接截图 → 图表在 y=1352（视口 1000 之外），
            #    拍到的是视口外黑块，被视觉模型判为"空白"，差点误报缺陷；
            #  - 引导遮罩「新手第一课」挡住图，必须先点 × 关掉。
            await send("Runtime.evaluate", {"expression": (
                "(()=>{const b=[...document.querySelectorAll('button')]"
                ".find(x=>(x.innerText||'').trim()==='×');if(b){b.click();return 1}return 0})()"
            ), "returnByValue": True}, session)
            await asyncio.sleep(1.5)
            await send("Runtime.evaluate", {"expression": (
                "(()=>{const b=[...document.querySelectorAll('button')]"
                ".find(x=>(x.innerText||'').includes('开始分析'));if(b){b.click();return 1}return 0})()"
            ), "returnByValue": True}, session)
            await asyncio.sleep(8.0)
            # 滚动进视口，保证截图落在可视区
            await send("Runtime.evaluate", {"expression": (
                "(()=>{const c=document.querySelector('canvas');"
                "if(c){c.scrollIntoView({block:'center'});return 1}return 0})()"
            ), "returnByValue": True}, session)
            await asyncio.sleep(2.0)

            r = await send("Runtime.evaluate", {"expression": (
                "(()=>{const c=document.querySelector('canvas');if(!c)return '{}';"
                "const g=c.getContext('2d');if(!g)return '{}';"
                "const d=g.getImageData(0,0,c.width,c.height).data;"
                "let nb=0,t=0,red=0,green=0;"
                "for(let k=0;k<d.length;k+=4*37){t++;const r0=d[k],g0=d[k+1],b0=d[k+2];"
                "if(r0>25||g0>25||b0>25)nb++;"
                "if(r0>150&&g0<120&&b0<120)red++;"
                "if(g0>110&&r0<120&&b0<120)green++;}"
                "const rc=c.getBoundingClientRect();"
                "return JSON.stringify({cw:c.width,ch:c.height,pct:+(100*nb/t).toFixed(2),"
                "red,green,y:Math.round(rc.y)});})()"
            ), "returnByValue": True}, session)
            try:
                px = json.loads((r.get("result") or {}).get("result", {}).get("value", "{}"))
            except Exception:
                px = {}
            pct = px.get("pct", 0.0)
            has_candles = px.get("red", 0) > 0 and px.get("green", 0) > 0
            rendered = pct >= 5.0 and has_candles  # 空画布实测 <1%
            print(f"[{'PASS' if rendered else 'FAIL'}] 缠论图真的画出来了"
                  f"（canvas={px.get('cw')}x{px.get('ch')}，非背景像素 {pct}%，"
                  f"红柱采样 {px.get('red')}、绿柱采样 {px.get('green')}）")

            if shot:
                # ⚠️ 第一次截图只拍到「新手第一课」引导遮罩 —— 图被它挡住了，
                # 但请求早已发出，所以请求断言仍 PASS。这正是"请求通过 ≠ 画出来了"。
                # 必须先关掉遮罩（点 × / 调 dismiss 逻辑），再截图。
                dismissed = False
                for sel in ('button[aria-label="Close"]', '.close', '[class*="close"]'):
                    r = await send("Runtime.evaluate", {
                        "expression": (
                            "(()=>{const e=document.querySelector('" + sel + "');"
                            "if(e){e.click();return 'clicked';}return 'none';})()"
                        ), "returnByValue": True}, session)
                    v = (r.get("result") or {}).get("result", {}).get("value")
                    if v == "clicked":
                        dismissed = True
                        break
                # 兜底：直接移除所有疑似遮罩的浮层
                await send("Runtime.evaluate", {"expression": (
                    "(()=>{document.querySelectorAll('div').forEach(d=>{"
                    "const t=(d.innerText||'').slice(0,20);"
                    "if(t.includes('新手第一课')){d.remove();}});return 1;})()"
                ), "returnByValue": True}, session)
                await asyncio.sleep(2.0)
                print(f"  引导遮罩已关闭: {'是' if dismissed else '否（用移除兜底）'}")
                rr = await send("Runtime.evaluate", {"expression": (
                    "(()=>{const c=document.querySelector('canvas');"
                    "const r=c.getBoundingClientRect();"
                    "return JSON.stringify({x:r.x,y:r.y,w:r.width,h:r.height});})()"
                ), "returnByValue": True}, session)
                try:
                    rc = json.loads((rr.get("result") or {}).get("result", {}).get("value", "{}"))
                except Exception:
                    rc = {}
                clip = None
                if rc.get("w"):
                    clip = {"x": max(0, rc["x"]), "y": max(0, rc["y"]),
                            "width": min(rc["w"], 1400 - max(0, rc["x"])),
                            "height": min(rc["h"], 1000 - max(0, rc["y"])), "scale": 1}
                resp = await send("Page.captureScreenshot",
                                  {"format": "png", **({"clip": clip} if clip else {})}, session)
                data = (resp.get("result") or {}).get("data")
                if data:
                    Path(shot).write_bytes(base64.b64decode(data))
                    print(f"\n截图已保存：{shot}")

            all_ok = ok_fired and ok_status and probe_ok and rendered
            print(f"\n== 结果: {'全部通过' if all_ok else '存在失败'} ==")
            return 0 if all_ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


async def _first_page(port: int) -> str:
    """取第一个 page 目标的 targetId（用 http://127.0.0.1:port/json/list）。"""
    import urllib.request
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as r:
        pages = json.loads(r.read().decode())
    for p in pages:
        if p.get("type") == "page":
            return p["id"]
    raise RuntimeError("无 page 目标")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--shot", default=None)
    ap.add_argument("--wait", type=float, default=40.0,
                    help="等待秒数；缠论页会先分页拉 ~10 次 /bars 才发 analyze")
    ap.add_argument("--retries", type=int, default=2,
                    help="CDP 连接/捕获失败时的重试次数（浏览器启动是竞态的）")
    a = ap.parse_args()

    last = 2
    for attempt in range(a.retries + 1):
        try:
            last = asyncio.run(main_async(a.base, a.shot, a.wait))
        except Exception as e:  # noqa: BLE001
            print(f"第 {attempt + 1} 次运行异常：{e}")
            last = 2
        if last == 0:
            return 0
        if attempt < a.retries:
            print(f"—— 第 {attempt + 1} 次未通过，重试 ——")
    return last


if __name__ == "__main__":
    raise SystemExit(main())
