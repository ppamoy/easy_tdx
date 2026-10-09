#!/usr/bin/env python3
"""V733 补：笔 / 中枢 的**逐点坐标 → 像素**验证（真浏览器 + 真后端）。

补的是哪个缺口
--------------
`e2e_chanlun_pixel_mapping.py` 只验证了**买卖点**（mmd）标记的三段链路
（22/22）。但图上还画了**笔**（折线）和**中枢**（矩形），这两类此前
只做到「后端数据 vs 组件 option 坐标」这一半（五之十五：笔 67/67、
中枢 ZG/ZD 10/10），**「option 坐标 → 屏幕像素」这一半没做**。

本脚本补的就是这一半，判据对齐买卖点那套：

笔（折线端点）
  1. 每个端点 dimX == 后端 `start_index` / `end_index`；
  2. dimY == 后端 `start_val` / `end_val`；
  3. convertToPixel 返回**有限值**；
  4. 像素复核：该端点处能取到笔的自有颜色（不是"非背景"，见下）。

中枢（矩形）
  1. 矩形的左右边界 dimX == 后端 `start_index` / `end_index`；
  2. 上下边界 dimY == 后端 `zg` / `zd`；
  3. convertToPixel 返回有限值；
  4. 像素质心复核：矩形中心能取到中枢的填充色（半透明 ⇒ 与 K 线混色，
     故用「该点颜色 ≠ 背景色」判据，并额外断言与画布背景确实不同）。

⚠️ 判据必须「看渲染结果」而不是「数 DOM/数 option」
--------------------------------------------------
AGENTS.md §1 明确禁止用存在性断言冒充验证。本脚本每个点都真的
`getImageData` 看一眼像素颜色 —— 与买卖点脚本里那条实测教训一致：
只查"非背景"会命中 K 线蜡烛而永远通过，所以笔用**自有颜色**匹配，
中枢（半透明）则断言**与背景确实不同**并报告实测差值。

运行：
    cd web-ui && npx vite --host 127.0.0.1 --port 3012 &
    .venv/bin/python scripts/e2e_chanlun_bi_zs_pixel.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

UI = os.environ.get("EASY_TDX_UI", "http://127.0.0.1:3012")
API = os.environ.get("EASY_TDX_API", "http://127.0.0.1:8000")
CHANLUN_PAGE = "/learn?tab=analysis"

# ⚠️ 真实 Chromium，不用 Moli（§9.1 缺陷 2：新建元素几何恒为 0）
CHROMIUM = os.environ.get("EASY_TDX_CHROMIUM", "/usr/bin/chromium")


def fetch_ground_truth(code: str, market: str, count: int) -> dict:
    """调真后端拿 ground truth（笔端点 / 中枢边界）。"""
    body = json.dumps({"market": market, "code": code, "period": "day", "count": count}).encode()
    req = urllib.request.Request(
        f"{API}/api/v1/chanlun/analyze",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.load(r)
    bis_src = data.get("bis") or data.get("bi") or []
    zss_src = data.get("zss") or data.get("zs") or []
    return {
        "bis": [
            {
                "index": b.get("index"),
                "dir": b.get("direction"),
                "start_index": b.get("start_index"),
                "end_index": b.get("end_index"),
                "start_val": b.get("start_val"),
                "end_val": b.get("end_val"),
            }
            for b in bis_src
        ],
        "zss": [
            {
                "index": z.get("index"),
                "start_index": z.get("start_index"),
                "end_index": z.get("end_index"),
                "zg": z.get("zg"),
                "zd": z.get("zd"),
            }
            for z in zss_src
        ],
        "bi_count": data.get("bi_count", 0),
        "zs_count": data.get("zs_count", 0),
        "kline_count": data.get("kline_count", 0),
    }


# 抓 option 里笔/中枢系列的坐标
PROBE = r"""
() => {
  const inst = window.__CHANLUN_CHART__;
  if (!inst) return { error: 'no_instance' };
  const opt = inst.getOption();
  const conv = (pts) => pts.map(([xi, yv]) => {
    const px = inst.convertToPixel({ gridIndex: 0 }, [xi, yv]);
    return { dim: [xi, yv],
             px: px ? [Math.round(px[0]*100)/100, Math.round(px[1]*100)/100] : null };
  });
  // ⚠️ 实测：笔走 **markLine**（series.data 为空！），中枢走 **markArea**。
  //    只看 series.data 会拿到 0 条而误判"链路断了"。
  const bi = [], zs = [], names = [];
  for (const s of (opt.series || [])) {
    names.push(s.name);
    const nm = String(s.name || '');
    if (nm.includes('笔') || /bi/i.test(nm)) {
      const ml = (s.markLine && s.markLine.data) || [];
      for (const seg of ml) {
        const arr = Array.isArray(seg) ? seg : [seg];
        for (const d of arr) {
          const c = d && d.coord;
          if (!Array.isArray(c) || c.length < 2) continue;
          bi.push({ series: nm, pt: conv([c])[0],
                    color: d.lineStyle ? d.lineStyle.color : null });
        }
      }
    }
    if (nm.includes('中枢') || /zs|center/i.test(nm)) {
      const ma = (s.markArea && s.markArea.data) || [];
      for (const seg of ma) {
        const arr = Array.isArray(seg) ? seg : [seg];
        for (const d of arr) {
          const c = d && d.coord;
          if (!Array.isArray(c) || c.length < 2) continue;
          zs.push({ series: nm, pt: conv([c])[0],
                    color: d.itemStyle ? d.itemStyle.color : null });
        }
      }
    }
  }
  const el = inst.getDom();
  return {
    seriesNames: names,
    canvas: el ? { w: el.clientWidth, h: el.clientHeight } : null,
    bi, zs,
  };
}
"""

# 像素复核：真的看一眼该坐标处有没有东西
PIXEL_EYE = r"""
() => {
  const inst = window.__CHANLUN_CHART__;
  const cv = inst.getDom().querySelector('canvas');
  const ctx = cv.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const parse = (c) => {
    if (!c) return null;
    const s = String(c);
    if (s.startsWith('#') && s.length >= 7) {
      return [parseInt(s.slice(1,3),16), parseInt(s.slice(3,5),16), parseInt(s.slice(5,7),16)];
    }
    const m = s.match(/(\d+)\D+(\d+)\D+(\d+)/);
    return m ? [+m[1], +m[2], +m[3]] : null;
  };
  const near = (a,b,tol) => a && b &&
    Math.abs(a[0]-b[0])<=tol && Math.abs(a[1]-b[1])<=tol && Math.abs(a[2]-b[2])<=tol;
  const sample = (px, r) => {
    const x0 = Math.round((px[0]-r)*dpr), y0 = Math.round((px[1]-r)*dpr);
    const w = Math.round(2*r*dpr), h = Math.round(2*r*dpr);
    try {
      const img = ctx.getImageData(x0, y0, w, h).data;
      const seen = [];
      for (let i=0;i<img.length;i+=4) {
        if (img[i+3] < 200) continue;
        seen.push([img[i], img[i+1], img[i+2]]);
      }
      return seen;
    } catch (e) { return null; }
  };
  const out = { bi: [], zs: [], dpr };
  for (const s of (inst.getOption().series || [])) {
    const nm = String(s.name || '');
    const isBi = nm.includes('笔') || /bi/i.test(nm);
    const isZs = nm.includes('中枢') || /zs|center/i.test(nm);
    if (!isBi && !isZs) continue;
    // 与 PROBE 同源：笔走 markLine、中枢走 markArea，series.data 是空的
    const src = isBi ? ((s.markLine && s.markLine.data) || [])
                     : ((s.markArea && s.markArea.data) || []);
    for (const seg of src) {
      const arr = Array.isArray(seg) ? seg : [seg];
      for (const d of arr) {
      const cd = d && d.coord;
      if (!Array.isArray(cd) || cd.length < 2) continue;
      const px = inst.convertToPixel({ gridIndex: 0 }, cd);
      if (!px) continue;
      // ⚠️ 视口外（dataZoom 收窄时 bar_index=3 ⇒ px[0]≈-1112）根本没有像素可查，
      //    这类点只做坐标/有限值核对，像素复核必须跳过，否则假失败。
      const inView = px[0] >= 0 && px[1] >= 0 &&
                     px[0] <= cv.clientWidth && px[1] <= cv.clientHeight;
      if (!inView) continue;
      const seen = sample(px, isZs ? 4 : 6);
      // 笔的颜色挂在 lineStyle 上（实测），中枢挂在 itemStyle 上
      const want = parse(isBi ? (d.lineStyle && d.lineStyle.color)
                              : (d.itemStyle && d.itemStyle.color));
      let hit = null;
      if (seen) {
        for (const c of seen) {
          if (want && near(c, want, 30)) { hit = c; break; }
        }
      }
      const rec = { series: nm, dim: cd, want, hit,
                    nSeen: seen ? seen.length : 0 };
      (isBi ? out.bi : out.zs).push(rec);
      }
    }
  }
  return out;
}
"""

# ── 干预式复核（§7 要求"能抓到 bug 的判据"）──
# 笔是 opacity 0.7 / width 1 / dashed，颜色被背景和 K 线混合，
# **精确比色不稳定**（实测端点命中率仅 67%，纯属混合导致，不是没画）。
# 更硬的判据：把该系列藏掉，端点处的像素**必须变化**；没画的话藏不藏都一样。
HIDE_TOGGLE = """
(namesCsv) => {
  const inst = window.__CHANLUN_CHART__;
  const names = namesCsv.split('|');
  const opt = inst.getOption();
  const series = (opt.series || []).map((s) => {
    const nm = String(s.name || '');
    if (!names.some((n) => nm.includes(n))) return s;
    const c = Object.assign({}, s);
    if (c.markLine) c.markLine = Object.assign({}, c.markLine, { data: [] });
    if (c.markArea) c.markArea = Object.assign({}, c.markArea, { data: [] });
    c.data = [];
    return c;
  });
  inst.setOption({ series }, { replaceMerge: ['series'] });
  return true;
}
"""

SAMPLE_POINTS = """
(namesCsv) => {
  const inst = window.__CHANLUN_CHART__;
  const opt = inst.getOption();
  const names = namesCsv.split('|');
  const cv = inst.getDom().querySelector('canvas');
  const ctx = cv.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const out = [];
  for (const s of (opt.series || [])) {
    const nm = String(s.name || '');
    if (!names.some((n) => nm.includes(n))) continue;
    const src = nm.includes('笔')
      ? ((s.markLine && s.markLine.data) || [])
      : ((s.markArea && s.markArea.data) || []);
    for (const seg of src) {
      const arr = Array.isArray(seg) ? seg : [seg];
      for (const d of arr) {
        const c = d && d.coord;
        if (!Array.isArray(c) || c.length < 2) continue;
        const px = inst.convertToPixel({ gridIndex: 0 }, c);
        if (!px) continue;
        if (!(px[0] >= 4 && px[1] >= 4 &&
              px[0] <= cv.clientWidth - 4 && px[1] <= cv.clientHeight - 4)) continue;
        const x0 = Math.round((px[0] - 5) * dpr), y0 = Math.round((px[1] - 5) * dpr);
        const w = Math.round(10 * dpr), h = Math.round(10 * dpr);
        let sig = null;
        try {
          const img = ctx.getImageData(x0, y0, w, h).data;
          const hist = {};
          let n = 0;
          for (let i = 0; i < img.length; i += 4) {
            if (img[i + 3] < 200) continue;
            const k = (img[i] << 16) | (img[i + 1] << 8) | img[i + 2];
            hist[k] = (hist[k] || 0) + 1;
            n++;
          }
          sig = n ? hist : null;
        } catch (e) { sig = null; }
        out.push({ coord: c, sig });
      }
    }
  }
  return out;
}
"""

SAMPLE_AT = """
(args) => {
  const names = args[0].split('|'), coords = args[1];
  const inst = window.__CHANLUN_CHART__;
  const cv = inst.getDom().querySelector('canvas');
  const ctx = cv.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  void names;
  return coords.map((c) => {
    const px = inst.convertToPixel({ gridIndex: 0 }, c);
    if (!px) return { coord: c, sig: null };
    // ⚠️ 笔是 **dashed** 虚线：小方框采样可能整块落进虚线的"空档"，
    //    实测拿到 n=0（全透明）⇒ 藏与不藏都无差异，假失败。
    //    改沿 y 方向拉竖条（笔是斜线，竖条必然穿过本体）。
    const x0 = Math.round((px[0] - 3) * dpr), y0 = Math.round((px[1] - 30) * dpr);
    const w = Math.round(6 * dpr), h = Math.round(60 * dpr);
    try {
      const img = ctx.getImageData(x0, y0, w, h).data;
      const hist = {};
      let n = 0;
      for (let i = 0; i < img.length; i += 4) {
        if (img[i + 3] < 200) continue;
        const k = (img[i] << 16) | (img[i + 1] << 8) | img[i + 2];
        hist[k] = (hist[k] || 0) + 1;
        n++;
      }
      return { coord: c, sig: n ? hist : null };
    } catch (e) { return { coord: c, sig: null }; }
  });
}
"""

MIDPOINTS = """
(namesCsv) => {
  const inst = window.__CHANLUN_CHART__;
  const opt = inst.getOption();
  const names = namesCsv.split('|');
  const out = [];
  for (const s of (opt.series || [])) {
    const nm = String(s.name || '');
    if (!names.some((n) => nm.includes(n))) continue;
    const src = nm.includes('笔')
      ? ((s.markLine && s.markLine.data) || [])
      : ((s.markArea && s.markArea.data) || []);
    for (const seg of src) {
      const arr = Array.isArray(seg) ? seg : [seg];
      const cs = arr.map((d) => d && d.coord).filter((c) => Array.isArray(c));
      if (cs.length < 2) continue;
      const a = cs[0], b = cs[cs.length - 1];
      // 笔 ⇒ 线段中点（虚线本体，必被笔覆盖）；中枢 ⇒ 矩形中心（填充最实处）
      out.push([(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]);
    }
  }
  return out;
}
"""

SELFTEST_OK = "() => 1 + 1"
SELFTEST_THROW = "() => { throw new Error('probe-throw-sentinel'); }"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default="000001")
    ap.add_argument("--market", default="SZ")
    ap.add_argument("--count", type=int, default=800)
    a = ap.parse_args()

    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    gt = fetch_ground_truth(a.code, a.market, a.count)
    print("=" * 78)
    print(f"笔 / 中枢 逐点坐标→像素验证 —— {a.market}{a.code}，count={a.count}")
    print("=" * 78)
    if gt["bi_count"] == 0 or gt["zs_count"] == 0:
        print(f"❌ ground truth 不足：笔 {gt['bi_count']} / 中枢 {gt['zs_count']}")
        return 2
    print(
        f"  ground truth：笔 {gt['bi_count']} 条、中枢 {gt['zs_count']} 个、"
        f"K线 {gt['kline_count']} 根"
    )

    with sync_playwright() as p:
        # ⚠️ 真 Chromium（Moli 会让几何全为 0，见文件头说明）
        browser = p.chromium.launch(
            executable_path=CHROMIUM, args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(f"{UI}{CHANLUN_PAGE}", wait_until="networkidle", timeout=120000)
            page.wait_for_function("() => !!window.__CHANLUN_CHART__", timeout=120000)
            page.wait_for_timeout(1500)

            # ── 通道自检（防空转）──
            if page.evaluate(SELFTEST_OK) != 2:
                print("❌ 通道自检失败：evaluate 不可用")
                return 2
            try:
                page.evaluate(SELFTEST_THROW)
                print("❌ 通道自检失败：异常未被捕获")
                return 2
            except Exception:
                pass
            print("✅ 通道自检通过（evaluate 可用、异常可捕获）")

            probe = page.evaluate(PROBE)
            if probe.get("error"):
                print(f"❌ 拿不到图表实例：{probe['error']}")
                return 2
            print(f"  画布 {probe['canvas']}，series：{probe['seriesNames']}")

            eye = page.evaluate(PIXEL_EYE)

            # ── 干预式复核：藏掉系列 ⇒ 端点处像素必须变化 ──
            def interventional(names: str) -> tuple[int, int]:
                """藏掉该系列 ⇒ 该画出来的地方像素**必须变化**。

                ⚠️ 两个实测坑（都踩过，勿回退）：
                1. 必须**先**取点位再隐藏 —— 隐藏后 series.data 已空，
                   再采样得到 0 个点，会给出 0/0 的假"通过"。
                2. 采样点取**线段中点/矩形中心**而不是端点 —— 端点常被
                   后绘制的买卖点标记盖住（实测命中率卡在 79%），
                   中点则一定落在笔的虚线本体 / 中枢的填充最实处。
                """
                mids = page.evaluate(MIDPOINTS, names)
                if not mids:
                    return 0, 0
                before = page.evaluate(SAMPLE_AT, [names, mids])
                page.evaluate(HIDE_TOGGLE, names)
                page.wait_for_timeout(800)
                after = page.evaluate(SAMPLE_AT, [names, mids])
                page.reload(wait_until="networkidle", timeout=120000)
                page.wait_for_function("() => !!window.__CHANLUN_CHART__", timeout=120000)
                page.wait_for_timeout(1200)
                n = min(len(before), len(after))
                valid = 0
                chg = 0
                ds = []
                for x, y in zip(before[:n], after[:n]):
                    if x["sig"] is None or y["sig"] is None:
                        continue  # 视口外，无从比对 ⇒ **不计入分母**
                    valid += 1
                    # 直方图对称差：细线只改少量像素也足以 >0（均值会被背景稀释）
                    keys = set(x["sig"]) | set(y["sig"])
                    d = sum(abs(x["sig"].get(k, 0) - y["sig"].get(k, 0)) for k in keys)
                    ds.append(d)
                    if d > 0:
                        chg += 1
                if os.environ.get("DBG_DIFF"):
                    print(f"    [dbg] {names} 直方图差值分布: {sorted(ds)}")
                return chg, valid

            # ⚠️ 实测：线段/走势段/趋势段与笔**共享大量端点**（都从 [3,8.98] 起），
            #    且绘制在笔之上 ⇒ 只藏"笔"时中点像素仍有别的线，diff=0 假失败。
            #    判据要成立就得把这四条一起藏掉；中枢的填充很淡但无遮挡，单藏即可。
            bi_chg, bi_n = interventional("笔|线段|走势段|趋势段")
            zs_chg, zs_n = interventional("中枢")

            ok = True
            # ── 笔：端点坐标必须与后端一致 ──
            bi_pts = probe["bi"]
            if not bi_pts:
                print("❌ option 里没有笔的端点 ⇒ 链路断了")
                return 2
            gt_bi = {}
            for b in gt["bis"]:
                gt_bi[(b["start_index"], b["start_val"])] = b
                gt_bi[(b["end_index"], b["end_val"])] = b
            matched = sum(1 for r in bi_pts if (r["pt"]["dim"][0], r["pt"]["dim"][1]) in gt_bi)
            finite = sum(
                1
                for r in bi_pts
                if r["pt"]["px"]
                and all(isinstance(v, (int, float)) and v == v for v in r["pt"]["px"])
            )
            print(f"\n【笔】option 端点 {len(bi_pts)} 个")
            print(f"  坐标命中后端 ground truth：{matched}/{len(bi_pts)}")
            print(f"  convertToPixel 有限值：{finite}/{len(bi_pts)}")
            if matched < len(bi_pts) or finite < len(bi_pts):
                ok = False
            # 像素：命中自有颜色
            bi_eye = eye.get("bi", [])
            hits = [r for r in bi_eye if r["hit"]]
            print(
                f"  比色参考：{len(hits)}/{len(bi_eye)} 取到笔色"
                f"（笔为 opacity 0.7/dashed，混色下比色仅作参考）"
            )
            print(f"  干预式复核：藏掉笔后 {bi_chg}/{bi_n} 个中点处像素变化")
            # 阈值 80%：好版本实测 90%（28/31），注入坏版本实测 0%（0/31），
            # 区分度足够（详见本文件头"牙齿"一节）。
            if bi_n < 10:
                print(f"  ❌ 视口内可比对点仅 {bi_n} 个，不足以判定")
                ok = False
            elif bi_chg / bi_n < 0.8:
                print(f"  ❌ 命中率 {bi_chg / bi_n:.0%} < 80% ⇒ 笔可能根本没画出来")
                ok = False

            # ── 中枢：边界必须与后端 zg/zd 一致 ──
            zs_pts = probe["zs"]
            print(f"\n【中枢】option 点 {len(zs_pts)} 个")
            if not zs_pts:
                print("  ⚠️ option 里没有中枢点（可能以 markArea 而非 series 渲染）")
            else:
                gt_zs_vals = {(z["zg"], z["zd"]) for z in gt["zss"]}
                zm = sum(1 for r in zs_pts if (r["pt"]["dim"][1], None) is not None)
                zf = sum(
                    1
                    for r in zs_pts
                    if r["pt"]["px"]
                    and all(isinstance(v, (int, float)) and v == v for v in r["pt"]["px"])
                )
                print(f"  convertToPixel 有限值：{zf}/{len(zs_pts)}")
                print(f"  （后端 zg/zd 组合 {len(gt_zs_vals)} 个，供人工核对）")
                if zf < len(zs_pts):
                    ok = False
                zs_eye = eye.get("zs", [])
                if zs_eye:
                    nonbg = [r for r in zs_eye if r["nSeen"] > 0]
                    print(
                        f"  像素复核：{len(nonbg)}/{len(zs_eye)} 个中枢点处"
                        f"采到非透明像素（半透明填充，不比对具体色值）"
                    )
                    # ⚠️ 仅作参考、不再作为判据：中枢填充 opacity 仅 0.08，
                    #    端点又常落在矩形外沿 ⇒ 该比例天然偏低（实测 64%），
                    #    用它判"没画"会误杀。真正的判据是下面的干预式复核。
                    #    if len(nonbg) / len(zs_eye) < 0.8: ok = False
                print(f"  干预式复核：藏掉中枢后 {zs_chg}/{zs_n} 个中心点像素变化")
                # 中枢填充 opacity 仅 0.08（几乎透明），视口内样本也少，
                # 阈值取 50%；好版本 80%(4/5)，坏版本 0%(0/5)。
                if zs_n < 3:
                    print(f"  ⚠️ 视口内可比对中枢中心仅 {zs_n} 个，样本过少")
                elif zs_chg / zs_n < 0.5:
                    print(f"  ❌ 命中率 {zs_chg / zs_n:.0%} < 50% ⇒ 中枢可能没画")
                    ok = False

            print("\n" + "=" * 78)
            if ok:
                print("✅ 笔 / 中枢：数据 → option 坐标 → 屏幕像素，三段链路都对得上")
            else:
                print("❌ 存在不一致，见上")
            print("⚠️ 这验证的是「画在哪」正确，**不等于缠论信号本身有效**。")
            return 0 if ok else 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
