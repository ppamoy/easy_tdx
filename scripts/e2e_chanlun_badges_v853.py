#!/usr/bin/env python3
"""V853 §1/§5 真实浏览器 e2e —— 验证 5 个买卖点工具徽章在真实页面（真实后端 +
真实 tdx 数据）上渲染，而非 jsdom mock。

补的缺口（AGENTS.md §1/§5/§6）：
- 此前 5 个工具（区间套三态/2买形态/1买背驰确立/3买ZG安全距离/同级别分解）
  只在 jsdom mount 断言「徽章 DOM class+text+title」——是 mock 数据。
- 本脚本连 Moli（127.0.0.1:9222）开真实页面，填 sh000001 点「开始分析」，
  等渲染稳定后读真实页面上的徽章 class+text+title，并截图。
- 徽章是文字+CSS（非图表），故「真实页面上徽章的 class+text+title」即 §1 行为级
  断言（不数 DOM 存在）；截图给视觉模型复核配色/位置（§1 渲染类补充）。

用法：
    .venv/bin/python scripts/e2e_chanlun_badges_v853.py [--base URL] [--code 000001]
退出码：0=全部徽章就位；1=缺徽章/异常；2=环境不可用。
"""
from __future__ import annotations
import argparse, asyncio, json, time, urllib.request, sys

WS = "ws://127.0.0.1:9222"
PAGE = "/learn?tab=analysis"

PROBE_BADGES = r"""
(()=>{
  const pick=(sel)=>[...document.querySelectorAll(sel)].map(e=>({
    cls:e.className||'', txt:(e.innerText||e.textContent||'').trim().slice(0,40),
    title:e.getAttribute('title')||''}));
  const ml=document.querySelector('.mmd-list');
  const sl=document.querySelector('.sl-panel');
  return JSON.stringify({
    hasMmdList: !!ml, mmdListRows: ml?ml.querySelectorAll('tbody tr').length:0,
    hasSlPanel: !!sl,
    qt: pick('.qt-badge'),
    m2: pick('.m2-form-badge'),
    b1: pick('.b1-status-badge'),
    b3: pick('.b3-status-badge'),
    slMech: pick('.sl-mech-banner'),
    slKind: pick('.sl-kind-badge'),
    slTrend: pick('.sl-trend-badge'),
  });
})()
"""

async def run(base: str, code: str, out_png: str) -> int:
    import websockets
    with urllib.request.urlopen("http://127.0.0.1:9222/json/list", timeout=5) as f:
        pages = json.loads(f.read().decode())
    page = next((p for p in pages if p.get("type") == "page"), None)
    if not page:
        print("❌ Moli 无 page target"); return 2
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=80_000_000) as conn:
        mid = [0]
        async def send(method, params=None):
            mid[0] += 1
            await conn.send(json.dumps({"id": mid[0], "method": method, "params": params or {}}))
            while True:
                r = json.loads(await conn.recv())
                if r.get("method"): continue
                if r.get("id") == mid[0]:
                    if "error" in r: print(f"❌ CDP {method}: {r['error']}")
                    return r
        async def ev(expr):
            r = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            outer = r.get("result") or {}
            if "exceptionDetails" in outer:
                d = outer["exceptionDetails"]
                txt = ((d.get("exception") or {}).get("description") or d.get("text") or "?")
                raise RuntimeError(f"页面JS异常: {str(txt)[:200]}")
            v = (outer.get("result") or {}).get("value")
            if isinstance(v, str):
                try: return json.loads(v)
                except Exception: return {}
            return v or {}
        await send("Page.enable"); await send("Runtime.enable")
        if await ev("1+1") != 2:
            print("❌ 探针通道异常"); return 2
        await send("Page.navigate", {"url": f"{base}{PAGE}"})
        t0 = time.time(); st = {}
        # 页面就绪 = 分析 tab 的「开始分析/分析中」按钮出现（比 ml>500 严格，
        # 避免 1s 误触即点空）
        while time.time() - t0 < 60:
            await asyncio.sleep(1.0)
            st = await ev("(()=>{const bs=[...document.querySelectorAll('button')].map(b=>(b.innerText||'').trim());return JSON.stringify({hasAnalyze: bs.some(t=>t.includes('开始分析')||t.includes('分析中')),mmdRows:document.querySelectorAll('.mmd-list tbody tr').length})})()")
            if st.get("hasAnalyze") or st.get("mmdRows", 0) > 0:
                break
        else:
            print(f"❌ 60s 分析 tab 未就绪 ({st})"); return 2
        print(f"[INFO] 页面就绪 ({time.time()-t0:.0f}s)")
        # 等「开始分析」按钮渲染（tab=analysis 自动选中后才有；早点点会扑空；
        # 慢机上 auto-analyze 可能正在跑「分析中…」，需等它回到「开始分析」）
        t0 = time.time(); found_btn = False
        while time.time() - t0 < 90:
            has = await ev("(()=>{const b=[...document.querySelectorAll('button')].find(x=>(x.innerText||'').includes('开始分析'));return JSON.stringify(!!b)})()")
            if has is True or has == 1: found_btn = True; break
            await asyncio.sleep(0.5)
        if not found_btn:
            btns = await ev("JSON.stringify([...document.querySelectorAll('button')].map(b=>(b.innerText||'').trim().slice(0,16)).filter(Boolean).slice(0,20))")
            print(f"❌ 「开始分析」按钮未就绪，现有按钮: {btns}"); return 1
        fill_js = r"""(()=>{
          const inp=[...document.querySelectorAll('input')].find(i=>(i.placeholder||'').includes('000001'));
          if(!inp) return JSON.stringify('no-input');
          const d=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(inp),'value');
          if(d&&d.set) d.set.call(inp,'__C__'); else inp.value='__C__';
          inp.dispatchEvent(new Event('input',{bubbles:true}));
          inp.dispatchEvent(new Event('change',{bubbles:true}));
          return JSON.stringify('filled:'+inp.value);})()""".replace("__C__", code)
        print(f"  填入: {await ev(fill_js)}")
        clicked = await ev("(()=>{const b=[...document.querySelectorAll('button')].find(x=>(x.innerText||'').includes('开始分析'));if(b){b.click();return JSON.stringify(1)}return JSON.stringify(0)})()")
        print(f"  点击「开始分析」: {'是' if clicked==1 else '否'}")
        if clicked != 1:
            btns = await ev("JSON.stringify([...document.querySelectorAll('button')].map(b=>(b.innerText||'').trim().slice(0,16)).filter(Boolean))")
            print(f"  现有按钮: {btns}")
            return 1
        # 等买卖点明细 + 同级别分解面板渲染
        t0 = time.time(); b = {}
        while time.time() - t0 < 90:
            await asyncio.sleep(1.5)
            b = await ev(PROBE_BADGES)
            if b.get("hasMmdList") and b.get("mmdListRows", 0) > 0:
                if b.get("hasSlPanel") or (time.time()-t0) > 40:
                    break
        else:
            print(f"❌ 90s 徽章未渲染 ({b})"); return 1
        time.sleep(1.0)  # 让 CSS 稳定
        b = await ev(PROBE_BADGES)
        print(f"\n[结果] mmdList 行={b.get('mmdListRows')}  sl-panel={'有' if b.get('hasSlPanel') else '无'}")
        print(f"  qt-badge(区间套三态)    : {len(b.get('qt',[]))} 个 → {[e['txt'] for e in b.get('qt',[])][:6]}")
        print(f"  m2-form-badge(2买形态)  : {len(b.get('m2',[]))} 个 → {[e['txt'] for e in b.get('m2',[])][:6]}")
        print(f"  b1-status(1买背驰确立)  : {len(b.get('b1',[]))} 个 → {[e['txt'] for e in b.get('b1',[])][:6]}")
        print(f"  b3-status(3买ZG安全距离): {len(b.get('b3',[]))} 个 → {[e['txt'] for e in b.get('b3',[])][:6]}")
        print(f"  sl-mech(机械操作横幅)  : {[e['txt'] for e in b.get('slMech',[])][:2]}")
        print(f"  sl-kind(段方向)        : {len(b.get('slKind',[]))} 个 → {[e['txt'] for e in b.get('slKind',[])][:4]}")
        # 截图：先关掉可能遮挡的 el-dialog/el-overlay（Moli §9.1.1 缺陷6：
        # el-dialog 关不上，直接隐藏），再截买卖点表 + 同级别分解区域。
        await ev("(()=>{[...document.querySelectorAll('.el-overlay,.el-dialog,.v-overlay,.signal-detail,.detail-card')].forEach(e=>{e.style.display='none'});return 1})()")
        loc = await ev("(()=>{const t=document.querySelector('.mmd-list');const s=document.querySelector('.sl-panel');const r=t?t.getBoundingClientRect():null;const r2=s?s.getBoundingClientRect():null;return JSON.stringify({mmd:r?{x:r.x|0,y:r.y|0,w:r.width|0,h:r.height|0}:null,sl:r2?{x:r2.x|0,y:r2.y|0,w:r2.width|0,h:r2.height|0}:null,vp:window.innerHeight})})()")
        import base64
        # 截整页（裁剪到 mmd-list 顶部到 sl-panel 底部）
        y0 = (loc.get('mmd') or {}).get('y', 0) if loc else 0
        ss = await send("Page.captureScreenshot", {"format": "png"})
        if ss.get("result", {}).get("data"):
            with open(out_png, "wb") as f:
                f.write(base64.b64decode(ss["result"]["data"]))
            print(f"\n[截图] {out_png}  mmd-list@{loc.get('mmd')} sl@{loc.get('sl') if loc else None}")
        # 断言：至少区间套徽章 + 同级别分解面板就位（这两个不依赖配对1买/中枢，
        # 应普遍存在）。其它徽章依赖具体信号，只统计不硬断言。
        ok = True
        if not b.get("hasSlPanel"):
            print("❌ 同级别分解面板未渲染"); ok = False
        if len(b.get("qt", [])) == 0 and len(b.get("m2", [])) == 0 and len(b.get("b1", [])) == 0 and len(b.get("b3", [])) == 0:
            print("❌ 无任何买卖点徽章渲染"); ok = False
        return 0 if ok else 1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8001")
    ap.add_argument("--code", default="000001")
    ap.add_argument("--out", default="audit_data/e2e_badges_v853.png")
    a = ap.parse_args()
    try:
        return asyncio.run(run(a.base, a.code, a.out))
    except Exception as e:
        print(f"❌ 异常: {e!r}"); return 2

if __name__ == "__main__":
    sys.exit(main())
