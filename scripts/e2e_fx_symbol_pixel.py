#!/usr/bin/env python3
"""验证**笔端点（分型）在图上真的画成了小圆点**，不是三角形。

背景（用户要求 2026-10-10）
---------------------------
> 笔的端点不要用三角形，用小圆点标识吧。所有的缠论图都这样。

为什么需要这个脚本
------------------
`symbols/check_fx_symbol.py` 是**静态扫描**（看源码字符串），能防住
「把 circle 改回 triangle」，但防不住「option 写对了、渲染出来不是那样」。
AGENTS.md §1 要求这类渲染结论必须**看真实像素**，不能停在源码层。

判据（几何，不是颜色）
----------------------
对同一个分型点，分别截取**该点上/下半区**的像素，统计前景（白色标记）像素数：

- **三角形**：宽度随高度线性变化 —— 靠近尖端宽、另一侧窄。
  向上三角 row 越靠上越窄（上窄下宽），向下三角相反。
  ⇒ 上半宽 / 下半宽 差异显著（ratio 明显 ≠ 1）。
- **圆点**：上下大致对称（圆是垂直轴对称图形）
  ⇒ 上半宽 / 下半宽 ≈ 1（允许抗锯齿误差）。

所以断言：** |上半宽 − 下半宽| / max ≤ TOL ** 即为圆点；
超过则说明又画成了三角形（不对称）。

为什么不能「只断言有白色像素」
------------------------------
和 `e2e_chanlun_bi_zs_pixel.py` 里那条教训同源：K 线、影线、标签文字都是白的，
只判「有前景像素」会永远通过、抓不到形状。必须做**形状区分**（上/下半宽比）。

运行：
    # 需要：8012 dev 后端 + 3012 vite + Moli(9222)
    .venv/bin/python scripts/e2e_fx_symbol_pixel.py [--code 600519] [--market sh]

退出码：0=确实是小圆点，1=画成了三角形/取不到数据。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

NODE_MODULES = "/home/skp/coder/ansheng5/node_modules"
CDP = "http://127.0.0.1:9222"
# 兜底用绝对路径：run_bg.sh 的 env 里 PATH 不一定含 ~/.local/bin
MOLI_STOP = str(Path.home() / ".local/bin/moli-serve-stop")
MOLI_START = str(Path.home() / ".local/bin/moli-serve-start")
PAGE_URL = "http://127.0.0.1:3012/learn?tab=analysis"  # 缠论分析页：唯一会传 fxs/validFxs 的入口

# 上/下半宽差异容忍度。圆的离散化会让两侧不完全相等（尤其 symbolSize 只有 7~10px），
# 但三角形的一侧宽度会趋近 0，ratio 差异远大于此。
TOL = 0.34


async def fetch_fx_true_values(code: str, market: str, count: int) -> list[dict]:
    """取后端的分型真值（用作图上点的 ground truth）。"""
    import httpx

    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(
            "http://127.0.0.1:8001/api/v1/chanlun/analyze",
            json={
                "market": market.upper(),
                "code": code,
                "category": "DAY",
                "count": count,
            },
        )
        r.raise_for_status()
        data = r.json()
    # valid_fractals = 笔端点（顶底交替、不共用K线），正是图上画的那批
    return data.get("valid_fractals") or data.get("fractals") or []


MEASURE_JS = r"""
() => {
  const inst = window.__CHANLUN_CHART__;
  if (!inst) return { err: 'window.__CHANLUN_CHART__ 不存在（图表未初始化）' };
  const cv = inst.getDom().querySelector('canvas');
  if (!cv || !cv.width) return { err: 'canvas 宽度为 0 —— Moli 布局缺陷，请重启 Moli' };
  const ctx = cv.getContext('2d');
  const dpr = window.devicePixelRatio || 1;

  // 前景判据：分型点是白色 FX_COLOR(#ffffff) + 深色描边。
  // 只认「接近纯白」的像素 —— 若放宽成「非背景」会把影线/文字算进来，
  // 形状判定会失真（这条教训来自 e2e_chanlun_bi_zs_pixel.py）。
  const isFx = (r,g,b,a) => a >= 200 && r > 225 && g > 225 && b > 225;

  function rowWidths(px, half) {
    const x0 = Math.round((px[0]-half)*dpr), y0 = Math.round((px[1]-half)*dpr);
    const w = Math.round(2*half*dpr), h = Math.round(2*half*dpr);
    if (x0 < 0 || y0 < 0 || x0+w > cv.width || y0+h > cv.height) return null;
    let img;
    try { img = ctx.getImageData(x0, y0, w, h).data; }
    catch (e) { return null; }
    const rows = [];
    for (let y = 0; y < h; y++) {
      let cnt = 0;
      for (let x = 0; x < w; x++) {
        const i = (y*w + x)*4;
        if (isFx(img[i], img[i+1], img[i+2], img[i+3])) cnt++;
      }
      rows.push(cnt);
    }
    return rows;
  }

  const out = { series: [], dpr, canvas: [cv.width, cv.height] };
  const opt = inst.getOption();
  for (const s of (opt.series || [])) {
    const nm = String(s.name || '');
    if (nm !== '顶分型' && nm !== '底分型') continue;
    const data = s.data || [];
    if (!data.length) { out.series.push({ name: nm, n: 0, measured: 0 }); continue; }
    const HALF = 9;  // symbolSize 7~10px，±9 的窗口足够覆盖又不吃太多相邻 K 线
    const measured = [];
    for (const d of data.slice(0, 14)) {
      const v = Array.isArray(d) ? d : d.value;
      if (!Array.isArray(v) || v.length < 2) continue;
      const px = inst.convertToPixel({ gridIndex: 0 }, v);
      if (!px) continue;
      const rows = rowWidths(px, HALF);
      if (!rows || rows.length < 6) continue;
      const mid = Math.floor(rows.length/2);
      // 用「整半区的像素总量」而不是单行宽度：单行在圆点边缘会因抗锯齿抖动
      const upper = rows.slice(0, mid).reduce((a,b)=>a+b, 0);
      const lower = rows.slice(mid).reduce((a,b)=>a+b, 0);
      measured.push({ upper, lower });
    }
    out.series.push({ name: nm, n: data.length, measured: measured.length, pts: measured });
  }
  return out;
}
"""


def measure_via_browser() -> dict:
    """在真实浏览器里量每个分型点的「上半 vs 下半」前景像素分布。"""
    probe = f"""
    const {{ chromium }} = require('playwright');
    (async () => {{
      const b = await chromium.connectOverCDP('{CDP}');
      const p = await (await b.newContext()).newPage();
      await p.setViewportSize({{width:1400, height:1000}});
      await p.goto('{PAGE_URL}', {{waitUntil:'domcontentloaded', timeout:120000}});
      await p.waitForFunction(()=>document.querySelectorAll('canvas').length>0, {{timeout:120000}}).catch(()=>{{}});
      await p.waitForFunction(()=>{{
        const c=document.querySelector('canvas'); return c && c.width>0;
      }}, {{timeout:120000}}).catch(()=>{{}});
      await p.waitForTimeout(4000);
      const r = await p.evaluate({MEASURE_JS});
      console.log('RESULT' + JSON.stringify(r));
      await b.close();
    }})();
    """
    # Moli 随会话退化：connectOverCDP 会超时挂住（AGENTS.md §9.2）。
    # 所以每次失败先重启 Moli 再重试，最多 2 轮 —— 不这么做的话，
    # 脚本会以「看起来像像素判据失败」的方式假阴性。
    last = ""
    for attempt in range(3):
        out = subprocess.run(
            ["env", f"NODE_PATH={NODE_MODULES}", "node", "-e", probe],
            capture_output=True, text=True, timeout=400,
        )
        for line in (out.stdout or "").splitlines():
            if line.startswith("RESULT"):
                try:
                    return json.loads(line[len("RESULT") :])
                except json.JSONDecodeError:
                    return {"err": "结果 JSON 解析失败"}
        last = (out.stderr or out.stdout or "无输出").strip()[:200]
        if attempt < 2:
            print(f"   (第 {attempt + 1} 次连接失败，重启 Moli 后重试) {last[:80]}")
            subprocess.run([MOLI_STOP], capture_output=True, timeout=60, shell=True)
            import time as _t

            _t.sleep(4)
            subprocess.run([MOLI_START, "--restart"], capture_output=True, timeout=120, shell=True)
            _t.sleep(10)
    return {"err": last}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default="600519")
    ap.add_argument("--market", default="sh")
    ap.add_argument("--count", type=int, default=800)
    args = ap.parse_args()

    print(f"标的 {args.market}:{args.code}  取分型真值…")
    try:
        fx = asyncio.run(fetch_fx_true_values(args.code, args.market, args.count))
    except Exception as e:  # noqa: BLE001
        print(f"❌ 取后端真值失败：{type(e).__name__} {e}")
        return 1
    if not fx:
        print("❌ 后端没返回任何分型 —— 无法验证")
        return 1
    print(f"   后端分型 {len(fx)} 个")

    probe = f"""
    const {{ chromium }} = require('playwright');
    (async () => {{
      const b = await chromium.connectOverCDP('{CDP}');
      const p = await (await b.newContext()).newPage();
      await p.setViewportSize({{width:1400, height:1000}});
      await p.goto('{PAGE_URL}', {{waitUntil:'domcontentloaded', timeout:120000}});
      await p.waitForFunction(()=>document.querySelectorAll('canvas').length>0, {{timeout:120000}}).catch(()=>{{}});
      await p.waitForTimeout(20000);
      const r = await p.evaluate(() => {{
        const c = document.querySelector('canvas');
        if (!c) return {{err:'无 canvas'}};
        return {{ w: c.width, h: c.height }};
      }});
      console.log(JSON.stringify(r));
      await b.close();
    }})();
    """
    out = subprocess.run(
        ["env", f"NODE_PATH={NODE_MODULES}", "node", "-e", probe],
        capture_output=True, text=True, timeout=300,
    )
    r = measure_via_browser()
    if "err" in r:
        print(f"❌ {r['err']}")
        return 1

    print(f"   canvas {r.get('canvas')}  dpr={r.get('dpr')}")
    series = [s for s in r.get("series", []) if s.get("measured")]
    if not series:
        print("❌ 分型 series 没量到任何点（可能被 showFractals 关掉，或取像素失败）")
        for s in r.get("series", []):
            print(f"   - {s.get('name')}: 数据 {s.get('n')} 条，量到 {s.get('measured')} 个")
        return 1

    bad: list[str] = []
    for s in series:
        pts = s["pts"]
        ratios = [
            abs(pt["upper"] - pt["lower"]) / (max(pt["upper"], pt["lower"]) or 1)
            for pt in pts
        ]
        worst, avg = max(ratios), sum(ratios) / len(ratios)
        # 三角形一侧趋近 0 ⇒ ratio 趋近 1；圆点上下对称 ⇒ ratio 远小于 TOL
        verdict = "圆点 ✅" if worst <= TOL else "三角形 ❌"
        print(
            f"   {s['name']}: {len(pts)} 点  上下不对称度 avg={avg:.2f} "
            f"worst={worst:.2f} (阈值 {TOL}) → {verdict}"
        )
        if worst > TOL:
            bad.append(s["name"])

    if bad:
        print(f"❌ 以下 series 仍画成三角形（上下不对称）：{bad}")
        return 1
    worst_all = max(
        abs(pt["upper"] - pt["lower"]) / (max(pt["upper"], pt["lower"]) or 1)
        for s in series
        for pt in s["pts"]
    )
    print(f"✅ 笔端点确认为小圆点（上下不对称度最差 {worst_all:.2f} ≤ 阈值 {TOL}）")
    return 0


⚠️ 已知限制（2026-10-11 实测）
-----------------------------
在 Moli 浏览器底座上跑本脚本会撞到：
`timer callback dispatch failed: Window Web IDL callback exceeded 8s and was terminated`
—— Moli 的 layout pump 会掐掉超过 8s 的回调，导致 ECharts 初始化/重绘被打断
（`window.__CHANLUN_CHART__` 迟迟不出现）。这是**浏览器底座的限制，不是应用代码问题**
（AGENTS.md §9.1 缺陷2 同源）。

已实测到的状态：canvas 确实渲染（1171×760）、ChanlunChart 容器存在、
dev server 下 `import.meta.env.DEV` 为真，但全局实例被上述超时打断拿不到。
所以本脚本的像素测量**尚未跑通**，目前不能作为验收依据。

if __name__ == "__main__":
    sys.exit(main())
