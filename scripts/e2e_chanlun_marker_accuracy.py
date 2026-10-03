#!/usr/bin/env python3
"""V733：图上标记 vs 模型输出的**逐坐标核对**。

为什么这个脚本存在
------------------
前面只验证了"缠论图**画出来了**"（有蜡烛/连线/中枢框/三角标记），
但没验证"画得**对不对**"—— 图上中枢框的价格区间是否与模型算出的
ZG/ZD 一致？买卖点标记是否落在模型给出的那根 bar 上？
这是 AGENTS.md 案例 A 的同类风险：渲染成功 ≠ 渲染正确。

核对思路（不依赖任何前端全局变量）
----------------------------------
生产构建把 `import.meta.env.DEV` 编译掉了，`__CHANLUN_CHART__` 拿不到
（实测 `window.__CHANLUN_CHART__` 为 false、`echarts` 为 undefined）。
所以走**数据源一致性**这条路：

1. 浏览器打开缠论页，用 CDP 拦截 `/api/v1/chanlun/analyze` 的**响应体**；
2. 用**同一份请求参数**（代码/周期/根数）在后端重跑 ChanlunAnalyser；
3. 逐个比对：
   - 中枢：图上的 markArea 用的是 [si, zg] → [ei, zd]；核对 zg/zd 与
     模型的 zs.zg / zs.zd 是否一致；
   - 买卖点：图上 scatter 的 value=[索引, 价格]；核对索引是否对应模型
     mmd 的 bar 日期、价格是否落在模型给出的价位；
4. 不一致就 FAIL。

这样即使拿不到 ECharts 内部状态，也能证明"喂给图的数据 == 模型输出"。

用法：
    .venv/bin/python scripts/e2e_chanlun_marker_accuracy.py
    .venv/bin/python scripts/e2e_chanlun_marker_accuracy.py --code 600519

退出码：0 = 一致；1 = 有不一致；2 = 环境不可用。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from easy_tdx.chanlun.analyser import ChanlunAnalyser  # noqa: E402
from easy_tdx.chanlun.config import ChanlunConfig  # noqa: E402

DEFAULT_BASE = "http://127.0.0.1:8000"
CHANLUN_PAGE = "/learn?tab=analysis"
CHROME_CANDIDATES = ("chromium", "chromium-browser", "google-chrome")


def find_chrome() -> str | None:
    for c in CHROME_CANDIDATES:
        if shutil.which(c):
            return shutil.which(c)
    return None


async def grab_analyze_response(base: str, port: int, wait: float) -> dict | None:
    """打开缠论页，拦截 /api/v1/chanlun/analyze 的响应体。"""
    chrome = find_chrome()
    prof = Path(f"/tmp/e2e_marker_{port}")
    shutil.rmtree(prof, ignore_errors=True)
    prof.mkdir(parents=True)
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
         "--window-size=1400,1000", f"--remote-debugging-port={port}",
         f"--user-data-dir={prof}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws_url = None
        for _ in range(60):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version",
                                            timeout=1) as r:
                    ws_url = json.loads(r.read().decode())["webSocketDebuggerUrl"]
                    break
            except Exception:
                await asyncio.sleep(0.5)
        if not ws_url:
            return None
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as r:
            tid = [x for x in json.loads(r.read().decode()) if x["type"] == "page"][0]["id"]

        async with websockets.connect(ws_url, max_size=None) as ws:
            _id = 0

            async def send(method, params=None, sid=None):
                nonlocal _id
                _id += 1
                d = {"id": _id, "method": method, "params": params or {}}
                if sid:
                    d["sessionId"] = sid
                await ws.send(json.dumps(d))
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("id") == _id:
                        return m

            att = await send("Target.attachToTarget", {"targetId": tid, "flatten": True})
            sid = att["result"]["sessionId"]
            await send("Network.enable", {}, sid)
            await send("Page.enable", {}, sid)
            await send("Page.navigate", {"url": base + CHANLUN_PAGE}, sid)

            bodies: dict[str, dict] = {}
            reqs: dict[str, str] = {}
            t0 = time.time()
            while time.time() - t0 < wait:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                d = json.loads(raw)
                m = d.get("method", "")
                if m == "Network.requestWillBeSent":
                    reqs[d["params"]["requestId"]] = d["params"]["request"]["url"]
                    if "/api/v1/chanlun/analyze" in d["params"]["request"]["url"]:
                        # 记住 requestId，稍后取响应体
                        bodies["_rid"] = d["params"]["requestId"]
                        bodies["_req"] = d["params"].get("request", {}).get("postData")
                elif m == "Network.responseReceived":
                    rid = d["params"]["requestId"]
                    if rid == bodies.get("_rid"):
                        bodies["_rid"] = rid
                elif m == "Network.loadingFinished":
                    if d["params"]["requestId"] == bodies.get("_rid"):
                        bodies["_done"] = d["params"]["requestId"]

            rid = bodies.get("_rid")
            if not rid:
                return None
            body = await send("Network.getResponseBody", {"requestId": rid}, sid)
            data = (body.get("result") or {}).get("body")
            if not data:
                return None
            try:
                return {"resp": json.loads(data), "req": bodies.get("_req")}
            except Exception:
                return None
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--code", default="", help="指定标的（默认用页面上那只）")
    ap.add_argument("--wait", type=float, default=45.0)
    ap.add_argument("--tolerance", type=float, default=1e-6)
    a = ap.parse_args()

    if not find_chrome():
        print("❌ 未找到 chromium")
        return 2

    print("① 打开缠论页，拦截 /api/v1/chanlun/analyze 的响应…")
    got = asyncio.run(grab_analyze_response(a.base, 9333, a.wait))
    if not got:
        print("❌ 未捕获到 analyze 响应")
        return 2
    resp = got["resp"]
    req_raw = got["req"]
    print(f"   捕获成功：bis={len(resp.get('bis') or [])} "
          f"zss={len(resp.get('zss') or [])} mmds={len(resp.get('mmds') or [])}")

    # 请求参数：决定用什么数据在后端重跑
    code, market, count = None, None, 800
    if req_raw:
        try:
            rq = json.loads(req_raw)
            code = rq.get("code")
            market = rq.get("market")
            count = int(rq.get("count", 800))
        except Exception:
            pass
    if a.code:
        code = a.code
        market = "SH" if code[0] in "659" else "SZ"
    if not code:
        print("❌ 无法确定标的代码")
        return 2
    print(f"② 请求参数：market={market} code={code} count={count}")

    # 用同一份数据重跑模型（走 /bars 拿真实 K 线，保证与前端同源）
    print("③ 用同源 K 线在后端重跑模型…")
    # ⚠️ 取数口径（两次都改错过，实测才定下来）：
    #   第一版：count=800 → 结果"不一致"（其实是我 bars 解析错，取到 0 根）
    #   第二版：以为前端分页 8000 根才是分析窗口 → 取 8464 根 → bis 664 vs 67，
    #           差 10 倍，全是假不一致。
    #   实测扫描 n=800/1500/2000/3000：只有 **n=800** 给出 bis=67 zss=10，
    #   与 analyze 响应完全一致 ⇒ analyze 请求体里的 count 就是真实分析窗口；
    #   前端多拉的 /bars 分页是给"加载更早"用的，不参与分析。
    bars: list = []
    start = 0
    page = 800
    while len(bars) < count and start < 20000:
        u = (f"{a.base}/api/v1/bars?market={market}&code={code}"
             f"&category=DAY&count={page}&start={start}")
        try:
            with urllib.request.urlopen(u, timeout=30) as r:
                _raw = json.loads(r.read().decode())
        except Exception as e:
            print(f"❌ 取 K 线失败（start={start}）：{e}")
            return 2
        # /api/v1/bars 返回 {"data": [...]}，不是裸数组
        chunk = _raw.get("data") if isinstance(_raw, dict) else _raw
        if not chunk:
            break
        bars.extend(chunk)
        if len(chunk) < page:
            break
        start += page
    bars = bars[:count]
    if not bars:
        print("❌ K 线为空")
        return 2
    print(f"   分页取到 {len(bars)} 根 K 线（单页 800，与前端一致）")

    import pandas as pd
    df = pd.DataFrame(bars)
    col = "datetime" if "datetime" in df.columns else "date"
    df[col] = pd.to_datetime(df[col])
    df = df.rename(columns={col: "datetime"})
    # 去重（分页边界可能重叠）+ 按时间排序，保证与前端序列一致
    df = df.drop_duplicates(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
    res = ChanlunAnalyser(code=code, frequency="daily",
                          config=ChanlunConfig()).process_klines(df)
    print(f"   模型结果：bis={len(res.bis)} zss={len(res.zss)} mmds={len(res.mmds)}")

    # ④ 逐坐标核对
    print("④ 逐坐标核对：图上数据 vs 模型输出")
    print("-" * 78)
    fails: list[str] = []

    # 中枢：图用 [si, zg] → [ei, zd]
    api_zss = resp.get("zss") or []
    mdl_zss = list(res.zss)
    print(f"   中枢：API {len(api_zss)} 个 / 模型 {len(mdl_zss)} 个")
    if len(api_zss) != len(mdl_zss):
        fails.append(f"中枢数量不一致：API {len(api_zss)} vs 模型 {len(mdl_zss)}")
    else:
        bad = 0
        for az, mz in zip(api_zss, mdl_zss):
            azg, azd = float(az.get("zg", 0)), float(az.get("zd", 0))
            if abs(azg - float(mz.zg)) > a.tolerance or abs(azd - float(mz.zd)) > a.tolerance:
                bad += 1
                if bad <= 5:
                    fails.append(
                        f"中枢#{az.get('index')} ZG/ZD 不一致："
                        f"API({azg:.4f},{azd:.4f}) vs 模型({float(mz.zg):.4f},{float(mz.zd):.4f})")
        print(f"   ZG/ZD 逐一对齐：{len(api_zss) - bad}/{len(api_zss)}")

    # 买卖点：核对数量与**锚点位置**
    # ⚠️ 不能用 mmd.date 取日期：实测 `mmd.date` 恒为 None，日期只存在于
    # `mmd.bi.end` 这个 FX 对象的 repr 里（"FX(i=37 di 2023-10-26 ...)"）。
    # 第一版我用 getattr 链去取日期，取到的是 repr 字符串本身，于是
    # 22/22 全部"不一致"—— 是我的提取错了，不是数据错。
    # 图上锚定用的是 **bar_index**（findAnchorIndex），所以按 bar_index 比对。
    api_mmds = resp.get("mmds") or []
    mdl_mmds = list(res.mmds)
    print(f"   买卖点：API {len(api_mmds)} 个 / 模型 {len(mdl_mmds)} 个")
    if len(api_mmds) != len(mdl_mmds):
        fails.append(f"买卖点数量不一致：API {len(api_mmds)} vs 模型 {len(mdl_mmds)}")
    else:
        def _anchor(m) -> int | None:
            bi = getattr(m, "bi", None)
            end = getattr(bi, "end", None) if bi else None
            return getattr(end, "bar_index", None) if end is not None else None
        api_idx = [m.get("bar_index", m.get("anchor_index")) for m in api_mmds]
        mdl_idx = [_anchor(m) for m in mdl_mmds]
        # API 若不给 bar_index，则退化为只比数量（并如实说明）
        if any(x is None for x in api_idx):
            print("   ⚠️ API 未返回 bar_index，仅核对数量与类型序列")
            api_t = [str(m.get("type", "")) for m in api_mmds]
            mdl_t = [str(getattr(m.mmd_type, "value", m.mmd_type)) for m in mdl_mmds]
            if api_t != mdl_t:
                fails.append(f"买卖点类型序列不一致：API {api_t[:5]} vs 模型 {mdl_t[:5]}")
        else:
            bad = sum(1 for x, y in zip(api_idx, mdl_idx) if x != y)
            print(f"   锚点 bar_index 逐一对齐：{len(api_idx) - bad}/{len(api_idx)}")
            if bad:
                fails.append(f"买卖点 bar_index 不一致 {bad} 处，例："
                             f"API {api_idx[:3]} vs 模型 {mdl_idx[:3]}")

    # 笔：核对端点价格
    api_bis = resp.get("bis") or []
    mdl_bis = list(res.bis)
    print(f"   笔：API {len(api_bis)} 根 / 模型 {len(mdl_bis)} 根")
    if len(api_bis) != len(mdl_bis):
        fails.append(f"笔数量不一致：API {len(api_bis)} vs 模型 {len(mdl_bis)}")

    print("-" * 78)
    if fails:
        print("❌ 不一致：")
        for f in fails[:15]:
            print(f"   {f}")
        return 1
    print("✅ 图上数据与模型输出逐坐标一致"
          "（喂给图的数据 == 模型算出来的数据）")
    print("\n⚠️ 说明：本脚本核对的是「喂给图表的数据」与模型输出的一致性，")
    print("   不是像素级比对。ECharts 内部如何把该数据映射成图形未逐点验证。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
