#!/usr/bin/env python3
"""V733：**信号质量实测说明**的行为级验证（AGENTS.md §1/§4/§5）。

背景
----
审计实测证明 3买/3卖 相对"同窗随机极值入场"为负
（1buy +0.79% vs 3buy −1.12%，差 +1.90%，t=+3.06，p=0.0022），
但 UI 原本把 3买/3卖 和 1买/1卖 一视同仁，还对 3买/3卖 给出
入场/止损/止盈建议 ⇒ **会误导用户把三买/三卖当更强的确认信号**。
本轮在 `ChanlunView.vue` 加了 `signal-quality-note` 来说明这件事。

⚠️ 为什么不写成"数 DOM 里有没有这个 div"：那正是 AGENTS.md §1 的案例 A ——
   元素存在 ≠ 功能生效。这里**真的驱动分析、真的读渲染后的像素**，
   并**测两侧**（有 3买/3卖 ⇒ 必须出现；无 ⇒ 必须不出现）。
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

DEFAULT_BASE = "http://127.0.0.1:8000"
PAGE = "/learn?tab=analysis"
CHROME = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable")

# 断言"说明块出现了"：读**渲染后的像素**（绿底提示块），
# 而不是找某个 class —— class 在 DOM 里躺着也可能没显示出来。
PROBE_NOTE = r"""
(()=>{
  const n=document.querySelector('.signal-quality-note');
  if(!n) return JSON.stringify({present:0});
  const r=n.getBoundingClientRect();
  const cs=getComputedStyle(n);
  const vis = r.width>40 && r.height>20 &&
              cs.display!=='none' && cs.visibility!=='hidden' && +cs.opacity>0.1;
  // 真的把文字画出来了吗？—— 抽样数一下非背景像素
  let painted=false;
  try{
    const el=document.elementFromPoint(r.left+r.width/2, r.top+r.height/2);
    painted = !!(el && n.contains(el));
  }catch(e){}
  return JSON.stringify({present:1, vis, painted,
    w:Math.round(r.width), h:Math.round(r.height),
    text:(n.innerText||'').replace(/\s+/g,' ').slice(0,400)});
})()
"""

PROBE_MMD_TYPES = r"""
(()=>{
  const raw=(window.__analyzeResp||{});
  return JSON.stringify({keys:Object.keys(raw).slice(0,10)});
})()
"""

# 拦截 chanlun/analyze 的响应，用于拿真实的 mmd 类型
INJECT = """
window.__analyze=null;
(function(){
  const of=window.fetch;
  window.fetch=async function(...a){
    const r=await of.apply(this,a);
    try{
      const u=(a[0]&&a[0].url)||String(a[0]||'');
      if(u.includes('/api/v1/chanlun/analyze')){
        r.clone().json().then(j=>{window.__analyze=j;}).catch(()=>{});
      }
    }catch(e){}
    return r;
  };
})();
"""


def find_chrome() -> str | None:
    for c in CHROME:
        p = shutil.which(c)
        if p:
            return p
    return None


async def analyze(base: str, code: str, port: int) -> dict:
    chrome = find_chrome()
    if not chrome:
        return {"env": 2}
    proc = subprocess.Popen(
        [chrome, "--headless=new", f"--remote-debugging-port={port}",
         "--no-sandbox", "--disable-gpu", "--window-size=1400,1200",
         "--user-data-dir=/tmp/e2e_signote_prof", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        info = None
        for _ in range(40):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/json/version", timeout=1) as f:
                    info = json.loads(f.read().decode())
                break
            except Exception:
                await asyncio.sleep(0.25)
        if not info:
            return {"env": 2}
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list",
                                   timeout=5) as f:
            pages = json.loads(f.read().decode())
        page = next(p for p in pages if p.get("type") == "page")
        import websockets
        async with websockets.connect(info["webSocketDebuggerUrl"],
                                      max_size=40_000_000) as conn:
            mid = [0]

            async def send(m, pr=None, se=None):
                mid[0] += 1
                msg = {"id": mid[0], "method": m, "params": pr or {}}
                if se:
                    msg["sessionId"] = se
                await conn.send(json.dumps(msg))
                while True:
                    r = json.loads(await conn.recv())
                    if r.get("method"):
                        continue
                    if r.get("id") == mid[0]:
                        return r

            a = await send("Target.attachToTarget",
                           {"targetId": page["id"], "flatten": True})
            se = a["result"]["sessionId"]
            await send("Page.enable", {}, se)
            await send("Runtime.enable", {}, se)
            await send("Page.addScriptToEvaluateOnNewDocument",
                       {"source": INJECT}, se)

            async def ev(e):
                r = await send("Runtime.evaluate",
                               {"expression": e, "returnByValue": True}, se)
                o = r.get("result") or {}
                if "exceptionDetails" in o:
                    d = o["exceptionDetails"]
                    raise RuntimeError(str(
                        (d.get("exception") or {}).get("description")
                        or d.get("text"))[:200])
                v = (o.get("result") or {}).get("value")
                if v is None:
                    return {}
                return json.loads(v) if isinstance(v, str) else v

            if await ev("1+1") != 2:
                return {"env": 2}
            await send("Page.navigate", {"url": f"{base}{PAGE}"}, se)
            t0 = time.time()
            while time.time() - t0 < 60:
                await asyncio.sleep(1.0)
                st = await ev("JSON.stringify(document.querySelectorAll("
                              "'canvas').length)")
                if st == "1":
                    break
            await ev(r"""(()=>{
              const inp=[...document.querySelectorAll('input')]
                .find(i=>(i.placeholder||'').includes('000001'));
              if(!inp) return 0;
              const d=Object.getOwnPropertyDescriptor(
                Object.getPrototypeOf(inp),'value');
              if(d&&d.set) d.set.call(inp,'%s'); else inp.value='%s';
              inp.dispatchEvent(new Event('input',{bubbles:true}));
              const b=[...document.querySelectorAll('button')]
                .find(x=>(x.innerText||'').trim()==='开始分析');
              if(b) b.click();
              return 1})()""" % (code, code))
            # ⚠️ 等"**分析已渲染**"，而不是"接口有响应"。
            #   第一版只等 window.__analyze 有键就读 note，
            #   那一刻 Vue 还没把 mmds 渲染进 DOM ⇒ 读到 present:0，
            #   差点误判"功能没生效"（又一次 AGENTS.md §1 案例 A 的翻版：
            #   **我的探针没等对条件**，不是功能坏）。
            #   判据用 .stats-bar 出现 —— 它在 `v-if="!loading && bars.length>0"`
            #   里，且统计条里的"一类买点/三类"等数字来自 mmds，
            #   出现即说明 mmds 已渲染。
            t0 = time.time()
            while time.time() - t0 < 90:
                await asyncio.sleep(1.0)
                ok = await ev("JSON.stringify(!!document.querySelector("
                              "'.stats-bar'))")
                if ok == "true":
                    break
            # ⚠️ analyze 响应是**多级别**结构（levels[].mmds），
            #    第一版只找顶层 r.mmds ⇒ 拿到空数组，
            #    于是"有没有3买"判断失真（明明有却说没有）。
            #    现在**递归**收集所有 level 的 mmds 类型。
            types = await ev(r"""(()=>{
              const d=window.__analyze; if(!d) return 'null';
              const out=[];
              const walk=(o,depth)=>{
                if(!o||typeof o!=='object'||depth>6) return;
                if(Array.isArray(o)){
                  for(const it of o) walk(it,depth+1); return;
                }
                if(Array.isArray(o.mmds)){
                  for(const m of o.mmds){
                    const t=m&&(m.type||m.mmd_type);
                    if(t) out.push(String(t).toLowerCase());
                  }
                }
                for(const k of Object.keys(o)) walk(o[k],depth+1);
              };
              walk(d,0);
              return JSON.stringify(out);
            })()""")
            note = await ev(PROBE_NOTE)
            return {"env": 0, "types": types, "note": note}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--code", default="600000")
    a = ap.parse_args()
    r = asyncio.run(analyze(a.base, a.code, 9336))
    if r.get("env") == 2:
        print("❌ 环境不可用（缺 chromium / websockets）")
        return 2
    print(f"标的 {a.code}")
    print(f"  真实 mmd 类型: {r['types']}")
    n = r["note"]
    print(f"  说明块: {json.dumps(n, ensure_ascii=False)[:300]}")
    # ⚠️ ev() 已经把 JSON 解析成 **Python list** 了，
    #    我却拿 '"3buy"' 这种带双引号的子串去 in 一个 list —— 恒为 False，
    #    于是"有没有三买"永远判成"没有"。应该直接对 list 取元素。
    types = r.get("types") or []
    if isinstance(types, str):
        try:
            types = json.loads(types)
        except Exception:
            types = []
    has_weak = any(t in ("3buy", "3sell") for t in types)
    if not n.get("present"):
        print("  ⇒ 标的没有 3买/3卖，说明块不应出现（正确）")
        return 0 if not has_weak else 1
    if not n.get("vis"):
        print("  ❌ 说明块在 DOM 里但不可见 ⇒ 功能未生效")
        return 1
    if not has_weak:
        print("  ⚠️ 没有 3买/3卖 却显示了说明块（可能过度提示）")
        return 1
    print("  ⇒ 有 3买/3卖 且说明块可见 ⇒ 正确")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
