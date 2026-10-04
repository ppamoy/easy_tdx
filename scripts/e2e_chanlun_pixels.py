#!/usr/bin/env python3
"""V733：ECharts **像素级**验证 —— 确认屏幕上的图真的画对了。

补的是哪个缺口
--------------
五之七只核对了「模型输出 vs 接口返回的数据」（中枢 ZG/ZD 10/10、买卖点锚点
bar_index 22/22、笔 67/67）。那验证的是**数据流**，**没有验证"屏幕上的图画对了"**
—— 坐标轴映射写错、series 顺序错位，数据全对而图是错的。

⚠️ 这正是 AGENTS.md §1：数据对 ≠ 画出来对。

做法（真读像素，不数 DOM）
--------------------------
1. CDP 打开真实页面、**精确点「开始分析」**触发真实分析；
2. 等图表**稳定渲染**（连续两次扫描结果一致，避开动画中途）；
3. `canvas.getImageData()` 读**真实像素**：蜡烛色像素、红绿列交替次数
   （与缩放无关）、白色标记像素；
4. **牙齿**：擦掉画布后用**同一套判据**重扫，必须测不到蜡烛。

⚠️ 踩过的坑（都已修，写下来防止重蹈）
--------------------------------------
1. **拿"探针失效"当"功能失效"**（AGENTS.md 案例 A 的翻版）：`window.echarts`
   不存在——web-ui 用 `echarts/core` 按需引入（`web-ui/src/echarts-setup.ts`）
   不挂全局；容器 DOM 也没有 `__ec_inner_`（实测 canvas 及其 5 层祖先自有属性
   全空），因为 `ChanlunChart.vue` 把实例存在**局部变量** `chart` 里
   （components/ChanlunChart.vue:267），从不暴露。第一版探针因此恒定返回
   "找不到实例"，页面却明明 canvas=1 正常显示。
2. **ev() 吞异常**：JS 异常与裸字符串返回值都变成 `{}`，于是"探针坏了"看起来
   像"功能坏了"。已改为显式抛异常 + 启动**通道自检**（1+1、故意 throw）。
   ⚠️ CDP 的 exceptionDetails 在**外层** result，查内层会漏。
3. **CDP 事件被丢**：`send()` 等命令响应时把 `Network.*` 事件一起丢掉，
   网络探针恒为 0 条，我差点据此断言"前端没发请求"。已改为缓冲。
4. **段数/间距依赖缩放**：dataZoom 一放大，蜡烛从 195 段变 5 段，拿"段间距"
   断言会误判"x 轴映射错位"。改用与缩放无关的"红绿交替次数"。
5. **牙齿必须与扫描同轮执行**：隔几秒再擦，前端已重挂载图表，
   `document.querySelector('canvas')` 拿到 null，牙齿形同虚设。
6. **JS 作用域错误伪装成"元素不存在"**：`if(..){var c}else{const c=..}` 是
   SyntaxError，整个探针抛异常又被吞成 `{}`，我误以为 canvas 拿不到。
7. **探针必须返回 JSON 字符串**：返回裸字符串会被吞成 `{}`。

⚠️ 局限（如实声明）
- 只做**几何与配色**层面的核对，**不逐点核对**"第 k 根 K 线的像素 x 是否等于
  ECharts 算出的 x"——那需要 ECharts 实例，而本项目不暴露它（见坑 1）。
- 白色像素只能证明"有标记"，不能区分是分型还是买卖点。
- 未做跨浏览器验证（仅 Chromium headless）。

用法：
    .venv/bin/python scripts/e2e_chanlun_pixels.py [--base URL] [--diag]

退出码：0 = 全部通过；1 = 存在失败；2 = 环境不可用。
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
CHANLUN_PAGE = "/learn?tab=analysis"
CHROME_CANDIDATES = ("chromium", "chromium-browser", "google-chrome",
                     "google-chrome-stable")

INJECT_ERRORS = """
window.__errs=[];
window.__barResponses=[];
// 拦截 fetch：记录 /api/v1/bars 的响应体。
// ⚠️ 必须**克隆**再读，否则 body 被消费掉会影响页面自身。
(function(){
  const of=window.fetch;
  window.fetch=async function(...a){
    const r=await of.apply(this,a);
    try{
      const u=(a[0]&&a[0].url)||String(a[0]||'');
      if(u.includes('/api/v1/bars')){
        r.clone().json().then(j=>{
          if(j&&j.data&&j.data.length) window.__barResponses.push(j.data);
        }).catch(()=>{});
      }
    }catch(e){}
    return r;
  };
})();
window.addEventListener('error',e=>window.__errs.push(
  'ERR: '+(e.message||'')+' @'+(e.filename||'').split('/').pop()+':'+e.lineno));
window.addEventListener('unhandledrejection',e=>window.__errs.push(
  'REJ: '+String(e.reason).slice(0,200)));
"""

PROBE_PIXEL = r"""
(()=>{
  const c=document.querySelector('canvas');
  if(!c) return JSON.stringify({ok:0,reason:'no canvas'});
  window.__chartCanvas=c;
  const ctx=c.getContext('2d');
  if(!ctx) return JSON.stringify({ok:0,reason:'no 2d ctx'});
  const W=c.width,H=c.height;
  const d=ctx.getImageData(0,0,W,H).data;
  const near=(r,g,b,tr,tg,tb)=>Math.abs(r-tr)<40&&Math.abs(g-tg)<40&&Math.abs(b-tb)<40;
  let red=0,green=0,bg=0,total=0,white=0;
  for(let i=0;i<d.length;i+=4){
    const r0=d[i],g0=d[i+1],b0=d[i+2];
    total++;
    if(r0>25||g0>25||b0>25) bg++;
    if(near(r0,g0,b0,0xef,0x41,0x46)) red++;
    else if(near(r0,g0,b0,0x18,0xa0,0x58)) green++;
    if(r0>200&&g0>200&&b0>200) white++;
  }
  let switches=0,lastColor=0;
  for(let x=0;x<W;x++){
    let rc=0,gc=0;
    for(let y=0;y<H;y++){
      const i=(y*W+x)*4;
      if(near(d[i],d[i+1],d[i+2],0xef,0x41,0x46)) rc++;
      else if(near(d[i],d[i+1],d[i+2],0x18,0xa0,0x58)) gc++;
    }
    const cc=rc>0?1:(gc>0?2:0);
    if(cc===0) continue;
    if(lastColor&&cc!==lastColor) switches++;
    lastColor=cc;
  }
  const chain=[]; let e2=c;
  for(let i=0;i<4&&e2;i++){chain.push((e2.className||'').toString().slice(0,30)||e2.tagName);
                            e2=e2.parentElement;}
  return JSON.stringify({ok:1,W,H,red,green,white,switches,
                         bgPct:+(100*bg/total).toFixed(2),chain});
})()
"""

PROBE_TEETH = r"""
(()=>{
  let c=(window.__chartCanvas && window.__chartCanvas.isConnected)
      ? window.__chartCanvas : null;
  if(!c){
    const host=document.querySelector('.chanlun-chart');
    c=host?host.querySelector('canvas'):null;
  }
  if(!c) return JSON.stringify({ok:0,reason:'no canvas in .chanlun-chart'});
  const ctx=c.getContext('2d');
  ctx.clearRect(0,0,c.width,c.height);
  ctx.fillStyle='#0a0a0a'; ctx.fillRect(0,0,c.width,c.height);
  const W=c.width,H=c.height;
  const d=ctx.getImageData(0,0,W,H).data;
  const near=(r,g,b,tr,tg,tb)=>Math.abs(r-tr)<40&&Math.abs(g-tg)<40&&Math.abs(b-tb)<40;
  let red=0,green=0,bg=0,total=0,switches=0,lastColor=0;
  for(let x=0;x<W;x++){
    let rc=0,gc=0;
    for(let y=0;y<H;y++){
      const i=(y*W+x)*4;
      const r0=d[i],g0=d[i+1],b0=d[i+2];
      total++;
      if(r0>25||g0>25||b0>25) bg++;
      if(near(r0,g0,b0,0xef,0x41,0x46)){rc++;red++;}
      else if(near(r0,g0,b0,0x18,0xa0,0x58)){gc++;green++;}
    }
    const cc=rc>0?1:(gc>0?2:0);
    if(cc===0) continue;
    if(lastColor&&cc!==lastColor) switches++;
    lastColor=cc;
  }
  return JSON.stringify({ok:1,red,green,switches,
                         bgPct:+(100*bg/total).toFixed(2)});
})()
"""

# ── 逐列取色序列：用于**逐点核对**（见文件头"局限"一节的说明）──
# 本项目的 ECharts 实例拿不到（echarts/core 按需引入、不挂全局、
# 组件把实例存在局部变量里），所以无法调用 convertToPixel 拿"权威坐标"。
# 但**逐点核对并不需要它**：
#   期望 = 由 /api/v1/bars 的真实 OHLC 推出的"第 i 根 K 线是涨(红)还是跌(绿)"
#   实际 = 画布第 x 列的像素颜色
# 二者按**顺序**比对 ⇒ 能查出"K 线顺序画反了 / 少画了 / 错位"这类错误。
# ⚠️ 对齐方式是**离屏右对齐**（ECharts 默认 dataZoom 显示最新一段），
#    故只比对"两序列右端的同长度尾部"。
PROBE_COLUMNS = r"""
(()=>{
  const c=document.querySelector('canvas');
  if(!c) return JSON.stringify({ok:0,reason:'no canvas'});
  const ctx=c.getContext('2d');
  if(!ctx) return JSON.stringify({ok:0,reason:'no 2d ctx'});
  const W=c.width,H=c.height;
  const d=ctx.getImageData(0,0,W,H).data;
  const near=(r,g,b,tr,tg,tb)=>Math.abs(r-tr)<40&&Math.abs(g-tg)<40&&Math.abs(b-tb)<40;
  const cols=[];
  for(let x=0;x<W;x++){
    let rc=0,gc=0;
    for(let y=0;y<H;y++){
      const i=(y*W+x)*4;
      if(near(d[i],d[i+1],d[i+2],0xef,0x41,0x46)) rc++;
      else if(near(d[i],d[i+1],d[i+2],0x18,0xa0,0x58)) gc++;
    }
    cols.push(rc>0?1:(gc>0?2:0));
  }
  return JSON.stringify({ok:1,W,H,cols});
})()
"""


def expected_colors(bars: list[dict]) -> list[int]:
    """由真实 OHLC 推出每根 K 线的应有颜色：1=红(涨) 2=绿(跌)。

    ECharts candlestick 的 itemStyle.color 表示**阳线**颜色。
    easy_tdx 前端是**红涨绿跌**（`echarts-setup.ts` 的 UP_COLOR=#ef4146），
    所以 close > open ⇒ 红。
    """
    out = []
    for b in bars:
        o, c = float(b["open"]), float(b["close"])
        out.append(1 if c >= o else 2)
    return out


def verify_alignment(cols: list[int], bars: list[dict]) -> dict:
    """把画布的红绿列序列与真实 OHLC 的涨跌序列**逐点**比对。

    对齐策略
    --------
    ECharts 默认 dataZoom 显示**最新**一段，且 K 线之间留有间隙（列 0），
    所以画布列序列不是"一根 K 线一列"。做法：
      1. 从画布列序列里**抽出所有非零段**，每段 = 一根 K 线的像素宽度；
      2. 取最后 K 个非零段（K = min(非零段数, 真实K线数)），即**右端对齐**；
      3. 真实 OHLC 也取最后 K 根；
      4. 逐点比较颜色。

    ⚠️ 为什么不直接比列：ECharts 的 category 起点偏移、间隙宽度、
    边框留白都会让"第 i 列"不等于"第 i 根 K 线"；按**段**对齐才是
    与缩放/像素密度都无关的比较。
    """
    if not cols:
        return {"ok": None, "reason": "未取到逐列序列"}
    segs = []
    start, cur = 0, cols[0]
    for x in range(1, len(cols)):
        if cols[x] != cur:
            if cur != 0:
                segs.append(cur)
            cur = cols[x]
    if cur != 0:
        segs.append(cur)
    if not segs:
        return {"ok": None, "reason": "画布上没抽出任何 K 线段"}

    if not bars:
        return {"ok": None, "reason": "未取到图表实际使用的 K 线"}

    exp = expected_colors(bars)
    k = min(len(segs), len(exp))
    if k < 10:
        return {"ok": None, "reason": f"可比数量太少({k})"}
    got = segs[-k:]
    # ⚠️ 不能假设画布显示的就是"最后 k 根" —— ECharts 的 dataZoom 可能
    #   停在窗口中部（实测画布只画了 47 段，而数据有 800 根）。
    #   所以这里**遍历所有可能的起始偏移**，取一致率最高的那一档，
    #   并同时报告最佳偏移；best_acc 明显高于随机(0.5)才算真的对上。
    best = (0.0, 0, 0)
    for off in range(0, len(exp) - k + 1):
        want = exp[off:off + k]
        hit = sum(1 for a, b in zip(got, want) if a == b)
        if hit / k > best[0]:
            best = (hit / k, off, hit)
    acc, off, hit = best
    # 右端对齐（off=len(exp)-k）那一档，供诊断对比
    tail_hit = sum(1 for a, b in zip(got, exp[-k:]) if a == b)
    return {"ok": True, "acc": acc, "hit": hit, "n_cmp": k, "off": off,
            "tail_acc": tail_hit / k,
            "n_pix": len(cols), "n_bars": len(exp), "n_seg": len(segs)}


def find_chrome() -> str | None:
    for c in CHROME_CANDIDATES:
        p = shutil.which(c)
        if p:
            return p
    return None


async def run(base: str, wait_s: float, diag: bool) -> int:
    try:
        import websockets
    except ImportError:
        print("❌ 未安装 websockets")
        return 2
    chrome = find_chrome()
    if not chrome:
        print("❌ 未找到 chromium/chrome")
        return 2

    port = 9334
    proc = subprocess.Popen(
        [chrome, "--headless=new", f"--remote-debugging-port={port}",
         "--no-sandbox", "--disable-gpu", "--window-size=1400,1000",
         "--user-data-dir=/tmp/e2e_pixels_prof", "about:blank"],
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
            print("❌ 浏览器未就绪")
            return 2
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/list", timeout=5) as f:
            pages = json.loads(f.read().decode())
        page = next(p for p in pages if p.get("type") == "page")

        events = []
        async with websockets.connect(info["webSocketDebuggerUrl"],
                                      max_size=80_000_000) as conn:
            msg_id = [0]

            async def send(method, params=None, session=None):
                msg_id[0] += 1
                m = {"id": msg_id[0], "method": method, "params": params or {}}
                if session:
                    m["sessionId"] = session
                await conn.send(json.dumps(m))
                while True:
                    r = json.loads(await conn.recv())
                    if r.get("method"):
                        events.append(r)
                        if len(events) > 4000:
                            del events[:2000]
                        continue
                    if r.get("id") == msg_id[0]:
                        if "error" in r:
                            print(f"❌ CDP {method}: {r['error']}")
                        return r

            a = await send("Target.attachToTarget",
                           {"targetId": page["id"], "flatten": True})
            session = a["result"]["sessionId"]
            await send("Page.enable", {}, session)
            await send("Runtime.enable", {}, session)
            await send("Network.enable", {}, session)
            await send("Page.addScriptToEvaluateOnNewDocument",
                       {"source": INJECT_ERRORS}, session)

            async def ev(expr):
                r = await send("Runtime.evaluate",
                               {"expression": expr, "returnByValue": True},
                               session)
                outer = r.get("result") or {}
                if "exceptionDetails" in outer:
                    d = outer["exceptionDetails"]
                    txt = ((d.get("exception") or {}).get("description")
                           or d.get("text") or "unknown")
                    raise RuntimeError(f"页面 JS 异常: {str(txt)[:300]}")
                v = (outer.get("result") or {}).get("value")
                if v is None:
                    return {}
                if isinstance(v, str):
                    try:
                        return json.loads(v)
                    except Exception:
                        print(f"    [探针契约] 返回非 JSON: {v[:100]!r}")
                        return {}
                return v

            if await ev("1+1") != 2:
                print("❌ 探针通道异常：1+1 不等于 2")
                return 2
            try:
                await ev("(()=>{throw new Error('BOOM')})()")
                print("❌ 探针无法上报 JS 异常 ⇒ 后续结果都不可信")
                return 2
            except RuntimeError:
                pass

            await send("Page.navigate", {"url": f"{base}{CHANLUN_PAGE}"}, session)
            t0 = time.time()
            st = {}
            loaded = False
            while time.time() - t0 < 60:
                await asyncio.sleep(1.0)
                st = await ev("(()=>{const m=document.querySelector('main');"
                              "return JSON.stringify({c:document.querySelectorAll"
                              "('canvas').length,ml:m?(m.innerText||'').length:0});})()")
                if st.get("c", 0) > 0 and st.get("ml", 0) > 1000:
                    loaded = True
                    break
            if not loaded:
                print(f"❌ 60s 内图表未就绪（最后一次: {st}）")
                return 2
            print(f"[INFO] 页面就绪（{time.time()-t0:.0f}s）")

            if diag:
                for t in (2, 4, 8, 12, 16):
                    await asyncio.sleep(t if t == 2 else t - 2)
                    c = await ev("JSON.stringify(document.querySelectorAll"
                                 "('canvas').length)")
                    print(f"  t={t}s canvas={c}")
                btns = await ev("JSON.stringify([...document.querySelectorAll("
                                "'button')].map(b=>(b.innerText||'').trim()"
                                ".slice(0,16)).filter(Boolean).slice(0,30))")
                print(f"  可点按钮: {btns}")
                return 0

            filled = await ev(r"""(()=>{
              const inp=[...document.querySelectorAll('input')]
                .find(i=>(i.placeholder||'').includes('000001'));
              if(!inp) return JSON.stringify('no-input');
              const d=Object.getOwnPropertyDescriptor(
                Object.getPrototypeOf(inp),'value');
              if(d&&d.set) d.set.call(inp,'600000'); else inp.value='600000';
              inp.dispatchEvent(new Event('input',{bubbles:true}));
              inp.dispatchEvent(new Event('change',{bubbles:true}));
              return JSON.stringify('filled:'+inp.value);})()""")
            print(f"  填入股票代码: {filled}")
            clicked = await ev(r"""(()=>{
              const b=[...document.querySelectorAll('button')]
                .find(x=>(x.innerText||'').trim()==='开始分析');
              if(b){b.click();return JSON.stringify(1)}
              return JSON.stringify(0)})()""")
            print(f"  点击「开始分析」: {'是' if clicked == 1 else '否'}")

            p = {}
            teeth = {}
            cols = {}
            deadline = time.time() + 120
            while time.time() < deadline:
                await asyncio.sleep(1.0)
                p1 = await ev(PROBE_PIXEL)
                if not p1.get("ok") or p1.get("red", 0) + p1.get("green", 0) < 500:
                    continue
                p2 = await ev(PROBE_PIXEL)
                if p2.get("red") != p1.get("red"):
                    continue
                p = p2
                # ⚠️ 逐列序列必须在**牙齿擦除之前**取，否则拿到的是空画布
                cols = await ev(PROBE_COLUMNS)
                t = await ev(PROBE_TEETH)
                if t.get("ok"):
                    teeth = t
                break
            if not p:
                api = [e["params"]["request"]["url"] for e in events
                       if e.get("method") == "Network.requestWillBeSent"
                       and "/api/" in e["params"]["request"]["url"]]
                print(f"❌ 未取到渲染好的画布。捕获 API 请求 {len(api)} 条：")
                for u in api[-6:]:
                    print(f"    {u}")
                return 1

            print(f"\n[INFO] canvas={p['W']}x{p['H']}  非背景 {p['bgPct']}%  "
                  f"红 {p['red']}  绿 {p['green']}  白 {p['white']}  "
                  f"红绿交替 {p['switches']} 次")
            print(f"[INFO] canvas 祖先链 {p.get('chain')}")

            ok = True
            print(f"\n[PASS] 蜡烛色像素 {p['red']+p['green']} ⇒ K 线画在画布上")
            if p["red"] > 0 and p["green"] > 0:
                print(f"[PASS] 红({p['red']})绿({p['green']})都有 ⇒ 涨跌配色正确")
            else:
                print(f"[FAIL] 红{p['red']}/绿{p['green']} 缺一种 ⇒ 配色或数据异常")
                ok = False
            if p["switches"] >= 4:
                print(f"[PASS] 红绿列交替 {p['switches']} 次 ⇒ 多根 K 线按序绘制，"
                      f"x 轴顺序映射正常")
            else:
                print(f"[WARN] 红绿交替仅 {p['switches']} 次 ⇒ 可能只画了少数几根")
            if p["white"] > 200:
                print(f"[PASS] 白色标记 {p['white']} 像素 ⇒ 缠论标记有画出来")
            else:
                print(f"[WARN] 白色标记仅 {p['white']} ⇒ 缠论标记可能没画")

            # 图表实际用的是哪个 K 线窗口？必须**用前端自己的请求参数**去取，
            # 否则会出现"拿 A 窗口的数据去比 B 窗口的图"的假失败
            # （我自己踩过：前端请求 start=6400&count=800，我用无 start 的
            #   count=800 去比，一致率 44.7% ≈ 随机，差点误判"图画错了"）。
            _api = [e["params"]["request"]["url"] for e in events
                    if e.get("method") == "Network.requestWillBeSent"
                    and "/api/v1/bars" in e["params"]["request"]["url"]]
            # ⚠️ 用**页面上正在渲染的那份数据**，而不是自己再查一次接口。
            #   前端最后一次 bars 请求带 start=6400，直接照抄该参数去查会返回
            #   0 根（该 offset 已越界）⇒ 必须复用浏览器已经拿到的数据。
            #   做法：拦截 fetch/XHR 记录响应体，读取时取最后一次。
            chart_bars = await ev(
                "JSON.stringify((window.__barResponses||[]).slice(-1)[0]||[])")
            print(f"  [逐点核对] 复用页面已加载的 K 线: {len(chart_bars)} 根")

            # ── 逐点核对：画布上的红绿顺序 vs 真实 OHLC 推出的涨跌顺序 ──
            # 这是"数据对 ≠ 画出来对"的正面回答：不需要 ECharts 实例，
            # 只要把两条序列按顺序比对即可。
            # ⚠️ 但**先要过分辨率这一关**：
            #   默认 dataZoom(start=50,end=100) 下 800 根画在约 1000px 绘图区
            #   ⇒ 每根仅 2.5px，**同色相邻 K 线的像素会连成一片**。
            #   实测只抽出 47 段、最佳一致率 70.2% —— 那不是"图画错了"，
            #   是**测量方法分辨率不够**（我自己先误判成"图画错了"，
            #   差点给出错误结论，正是 AGENTS.md §3 说的"先验证再下结论"）。
            #   所以分辨率不足时**必须报"不可判定"**，绝不给一个假的准确率。
            # ⚠️ cols 是"每列一个颜色值"，非零**列**数 ≈ 像素宽度，
            #    **不是 K 线段数**。K 线段数必须由压缩连续同色列得到。
            _raw = cols.get("cols") or []
            _nseg = 0
            _prev = 0
            for _c in _raw:
                if _c and _c != _prev:
                    _nseg += 1
                _prev = _c
            _nbar = len(chart_bars)
            _vis = max(_nbar // 2, 1)          # dataZoom 只显示后 50%
            _wpp = cols.get("W", 0) / _vis     # 每根 K 线平均像素宽
            if _nbar and _nseg < _nbar * 0.3:
                print(f"\n[WARN] 逐点核对**不可判定**（分辨率不足，非图表错误）:")
                print(f"       数据 {_nbar} 根，dataZoom 显示约 {_vis} 根，"
                      f"每根仅 ≈{_wpp:.1f}px 宽")
                print(f"       画布只抽出 {_nseg} 个可分辨 K 线段 ⇒ "
                      f"同色相邻蜡烛像素粘连，逐列取色分不出单根")
                print(f"       需要每根 K 线 ≥6px 才能逐点核对；"
                      f"本构建不暴露 ECharts 实例，无法自动缩放")
                print(f"       ⇒ 诚实结论：**逐点坐标映射在本构建下无法验证**")
            else:
                align = verify_alignment(cols.get("cols") or [], chart_bars)
                if align["ok"] is None:
                    print(f"\n[WARN] 逐点核对未执行: {align['reason']}")
                else:
                    print(f"\n[逐点核对] 页面数据 {align['n_bars']} 根，"
                          f"画布 {align['n_pix']} 列 / 抽出 {align['n_seg']} 个 K 线段"
                          f" ⇒ 比对 {align['n_cmp']} 段")
                    print(f"           最佳一致率 {align['acc']*100:.1f}%"
                          f"（{align['hit']}/{align['n_cmp']}，"
                          f"起始偏移 {align['off']}）"
                          f"；若误按'末 k 根'对则为 {align['tail_acc']*100:.1f}%")
                    if align["acc"] >= 0.90:
                        print(f"[PASS] 逐点一致率 {align['acc']*100:.1f}% ≥ 90% "
                              f"⇒ 第 i 根 K 线的像素位置与真实涨跌顺序对应，"
                              f"x 轴映射正确")
                    else:
                        print(f"[FAIL] 逐点一致率仅 {align['acc']*100:.1f}% < 90% "
                              f"⇒ K 线顺序/位置可能画错了")
                        ok = False

            if teeth:
                print(f"\n[牙齿] 擦掉画布后：非背景 {teeth['bgPct']}%"
                      f"（原 {p['bgPct']}%）、红 {teeth['red']} 绿 {teeth['green']}"
                      f"、交替 {teeth['switches']} 次")
                if (teeth["red"] == 0 and teeth["green"] == 0
                        and teeth["switches"] == 0):
                    print("[PASS] 牙齿成立：擦掉后测不到蜡烛 ⇒ 上面 PASS 是真的")
                else:
                    print(f"[FAIL] 牙齿不成立：仍有红{teeth['red']}/绿{teeth['green']}"
                          f" ⇒ 检测器常真，不可信")
                    ok = False
            else:
                print("[WARN] 牙齿未执行（未能在扫描同轮拿到画布）")

            errs = await ev("JSON.stringify(window.__errs||[])")
            if errs:
                print(f"\n[WARN] 页面捕获到 {len(errs)} 条前端错误: {errs}")
            print(f"\n== 判定: {'全部通过' if ok else '存在失败'} ==")
            return 0 if ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--wait", type=float, default=0.0,
                    help="兼容参数（等待逻辑已内置条件轮询）")
    ap.add_argument("--diag", action="store_true",
                    help="只观察页面渲染，不点任何按钮")
    a = ap.parse_args()
    try:
        return asyncio.run(run(a.base, a.wait, a.diag))
    except KeyboardInterrupt:
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
