#!/usr/bin/env python3
"""背驰标记的「后端数据 → option 坐标 → 屏幕像素」三段逐点验证。

为什么单独写这个脚本
--------------------
五之十一（买卖点）与本轮的笔/中枢都已逐点验证，但**背驰是第三个独立通道**
（后端 `bcs` 字段 → 前端 mapBcs → series「背驰」/「背驰(主图)」）。
此前只在教程文案里见过"背驰"两个字，图上到底画没画、画在哪，**没验证过**。

判据（必须能抓到 bug，见 --selftest / INJECT_BROKEN）
----------------------------------------------------
1. 数量：图上背驰点数 == 后端 bcs 数（不等就直接失败，不做"部分通过"）
2. 坐标：每个点的 option 坐标 == 后端 `anchor_bar_index` / `anchor_val`
3. 像素：在该坐标处**真的能取到该标记自己的颜色**
   ⚠️ 不能用"非背景"判据 —— 标记后面就是 K 线蜡烛，只查非背景会命中蜡烛
      而永远通过（实测把标记设成全透明，依然"通过" ⇒ 该判据形同虚设）。

⚠️ 已实测的两个坑（都是从买卖点脚本那儿带过来的教训，别再踩）：
   - 代码输入框**没有 keyup.enter**，且 ChanlunView 的 watch 不监听 code
     ⇒ 必须点「开始分析」按钮，fill + Enter 不触发。
   - 采样窗口必须**随 symbolSize 自适应**：小标记用固定窗口采不到实心像素。
   - 视口外的点没有像素可查 ⇒ 必须跳过而不是算失败（否则命中率假性暴跌）。

用法：
    python3 scripts/e2e_chanlun_bcs_pixel.py
    python3 scripts/e2e_chanlun_bcs_pixel.py --code 600519 --market SH
    INJECT_BROKEN=1 python3 scripts/e2e_chanlun_bcs_pixel.py   # 牙齿：应失败

退出码：0 = 三段全对；1 = 有不一致；2 = 取数失败/环境不可用。
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
CHROMIUM = os.environ.get("EASY_TDX_CHROMIUM", "/usr/bin/chromium")

# 图上两个背驰系列：主图散点 + 副图（MACD 上）散点
BCS_NAMES = ("背驰", "背驰(主图)")


def fetch_ground_truth(code: str, market: str, count: int) -> dict:
    """调真后端拿 ground truth（anchor_bar_index / anchor_val）。"""
    body = json.dumps({"market": market, "code": code, "period": "day", "count": count}).encode()
    req = urllib.request.Request(
        f"{API}/api/v1/chanlun/analyze",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.load(r)
    return {
        "bcs": [
            {
                "type": b.get("type"),
                "bc": b.get("bc"),
                "date": b.get("date"),
                "anchor_bar_index": b.get("anchor_bar_index"),
                "anchor_val": b.get("anchor_val"),
                "msg": b.get("msg", ""),
            }
            for b in data.get("bcs", [])
        ],
        "bcs_count": len(data.get("bcs", [])),
        "kline_count": data.get("kline_count", 0),
    }


PROBE = r"""
() => {
  const inst = window.__CHANLUN_CHART__;
  if (!inst) return { error: 'no_instance' };
  let opt = null;
  try { opt = inst.getOption(); } catch (e) { return { error: 'getOption_threw: ' + e.message }; }
  if (!opt || !opt.series) return { error: 'no_series' };
  const NAMES = window.__BCS_NAMES__ || [];
  const out = [];
  for (const s of opt.series) {
    if (!NAMES.includes(String(s.name || ''))) continue;
    for (const d of (s.data || [])) {
      const v = Array.isArray(d.value) ? d.value : null;
      out.push({
        name: d.name,
        series: s.name,
        dim: v,
        color: d.itemStyle && d.itemStyle.color,
        symbolSize: d.symbolSize,
      });
    }
  }
  return {
    seriesCount: opt.series.length,
    canvas: (() => {
      const cv = inst.getDom().querySelector('canvas');
      return cv ? { w: cv.clientWidth, h: cv.clientHeight } : null;
    })(),
    marks: out,
  };
}
"""

PIXEL_EYE = r"""
() => {
  const inst = window.__CHANLUN_CHART__;
  if (!inst) return { error: 'no_instance' };
  const opt = inst.getOption();
  if (!opt || !opt.series) return { error: 'no_series' };
  const cv = inst.getDom().querySelector('canvas');
  const ctx = cv.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const NAMES = window.__BCS_NAMES__ || [];
  const parse = (c) => {
    if (!c) return null;
    const s = String(c);
    if (s.startsWith('#') && s.length >= 7) {
      return [parseInt(s.slice(1, 3), 16), parseInt(s.slice(3, 5), 16),
              parseInt(s.slice(5, 7), 16)];
    }
    const m = s.match(/(\d+)\D+(\d+)\D+(\d+)/);
    return m ? [+m[1], +m[2], +m[3]] : null;
  };
  const near = (a, b, t) => a && b &&
    Math.abs(a[0] - b[0]) <= t && Math.abs(a[1] - b[1]) <= t && Math.abs(a[2] - b[2]) <= t;
  const res = [];
  let offView = 0;
  for (const s of (opt.series || [])) {
    if (!NAMES.includes(String(s.name || ''))) continue;
    for (const d of (s.data || [])) {
      if (!Array.isArray(d.value) || d.value.length < 2) continue;
      const px = inst.convertToPixel({ gridIndex: 0 }, d.value);
      if (!px) continue;
      // ⚠️ 采样窗口随 symbolSize 自适应（买卖点脚本上的实测教训）
      const sz = Math.max(10, Number(d.symbolSize) || 12);
      const r = Math.max(7, Math.round(sz * 0.9));
      // ⚠️ 视口外的点没有像素可查 ⇒ 跳过，不算失败
      if (!(px[0] >= r && px[1] >= r &&
            px[0] <= cv.clientWidth - r && px[1] <= cv.clientHeight - r)) {
        offView++;
        continue;
      }
      const want = parse(d.itemStyle && d.itemStyle.color);
      const img = ctx.getImageData(
        Math.round((px[0] - r) * dpr), Math.round((px[1] - r) * dpr),
        Math.round(2 * r * dpr), Math.round(2 * r * dpr)).data;
      let got = null;
      for (let i = 0; i < img.length; i += 4) {
        if (img[i + 3] < 200) continue;
        const c = [img[i], img[i + 1], img[i + 2]];
        if (near(c, want, 26)) { got = c; break; }
      }
      res.push({ name: d.name, series: s.name, dimX: d.value[0], want, got });
    }
  }
  return { dpr, res, offView };
}
"""

HIDE_TOGGLE = r"""
(names) => {
  const inst = window.__CHANLUN_CHART__;
  const opt = inst.getOption();
  const series = (opt.series || []).map((s) => {
    if (!names.includes(String(s.name || ''))) return s;
    const c = Object.assign({}, s);
    c.data = [];
    return c;
  });
  inst.setOption({ series }, { replaceMerge: ['series'] });
  return true;
}
"""

SELFTEST_OK = "() => 1 + 1"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default="000001")
    ap.add_argument("--market", default="SZ")
    ap.add_argument("--count", type=int, default=800)
    a = ap.parse_args()

    try:
        truth = fetch_ground_truth(a.code, a.market, a.count)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ 后端取数失败：{exc}")
        return 2
    if not truth["bcs"]:
        print("❌ 后端未返回背驰 ⇒ 无法逐点验证（退出）")
        return 2
    print(f"✅ ground truth：{truth['bcs_count']} 个背驰 / {truth['kline_count']} 根 K 线")

    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    failures: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=CHROMIUM,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1000})

        if page.evaluate(SELFTEST_OK) != 2:
            print("❌ evaluate 通道不可用")
            return 2

        page.goto(f"{UI}{CHANLUN_PAGE}", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        # ⚠️ 必须真的切票：fill + Enter **不触发**分析（没有 keyup.enter，
        #    且 watch 不监听 code）⇒ 必须点按钮。
        inp = page.locator('input[placeholder="如 000001"]').first
        inp.fill(a.code)
        page.locator("button.analyze-btn").first.click()

        # 等图上背驰数量 == 后端，光看输入框不够（值对了 ≠ 数据换了）
        page.evaluate(f"() => {{ window.__BCS_NAMES__ = {json.dumps(list(BCS_NAMES))}; }}")
        page.wait_for_timeout(3000)
        got_n = -1
        for _ in range(15):
            r = page.evaluate(PROBE)
            if not isinstance(r, dict) or r.get("error"):
                page.wait_for_timeout(2000)
                continue
            got_n = len(r["marks"])
            if got_n:
                break
            page.wait_for_timeout(2000)
        if not got_n:
            print(f"❌ 等待超时：图上背驰 {got_n} 个（后端 {truth['bcs_count']}）")
            return 2

        print(f"✅ 取到 {got_n} 个背驰标记")

        # ── 牙齿 1：数量必须与后端一致 ──
        # 两个系列各画一遍同样的背驰 ⇒ 期望是后端数的 2 倍
        expect = truth["bcs_count"] * 2
        if got_n != expect:
            failures.append(f"背驰数 {got_n} != 后端×2 {expect}")
            print(f"❌ 背驰数 {got_n} != 后端 {truth['bcs_count']} × 2 = {expect}")
        else:
            print(f"✅ 背驰数 == 后端 {truth['bcs_count']} × 2 个系列 == {got_n}")

        # ── 判据 2：逐点坐标对齐后端 ──
        r = page.evaluate(PROBE)
        marks = r["marks"]
        by_dim = {(m["dim"][0], round(m["dim"][1], 6)) for m in marks if m.get("dim")}
        want = {
            (b["anchor_bar_index"], round(float(b["anchor_val"]), 6))
            for b in truth["bcs"]
            if b.get("anchor_bar_index") is not None
        }
        aligned = sum(1 for w in want if w in by_dim)
        print(f"\n坐标对齐 {aligned}/{len(want)}")
        if aligned != len(want):
            failures.append(f"坐标对齐 {aligned}/{len(want)}")

        # ── 判据 3：像素处确有该标记自己的颜色 ──
        page.evaluate(
            "() => window.__CHANLUN_CHART__.dispatchAction({type:'dataZoom', start:0, end:100})"
        )
        page.wait_for_timeout(3000)
        # ── 牙齿开关（§7：判据必须能抓到 bug）──
        # ⚠️ 注入必须用真的清空 data：实测 ECharts 对 opacity:0 与
        #    symbolSize:0 **完全无视**（买卖点脚本上验证过）⇒ 那种注入
        #    会让人误以为判据有牙。
        if os.environ.get("INJECT_BROKEN"):
            page.evaluate(HIDE_TOGGLE, list(BCS_NAMES))
            page.wait_for_timeout(800)
        eye = page.evaluate(PIXEL_EYE)
        if not isinstance(eye, dict) or eye.get("error"):
            failures.append(f"像素复核失败：{eye}")
            print(f"❌ 像素复核失败：{eye}")
        else:
            colored = [e for e in eye["res"] if isinstance(e.get("got"), list)]
            if eye.get("offView"):
                print(f"  （{eye['offView']} 个在视口外，不计入分母）")
            print(
                f"\n像素复核：{len(colored)}/{len(eye['res'])} 个背驰在其坐标处"
                f"确有自身颜色（dpr={eye['dpr']}）"
            )
            if not eye["res"]:
                failures.append("像素复核：取不到任何背驰坐标")
            else:
                miss = [e for e in eye["res"] if not isinstance(e.get("got"), list)]
                ratio = len(miss) / max(len(eye["res"]), 1)
                # ⚠️ 允许 ≤15%：背驰标记较小且可能与分型/买卖点重叠互相遮挡
                if ratio > 0.15:
                    failures.append(f"{len(miss)}/{len(eye['res'])} 个背驰处无自身颜色")
                    print(f"❌ {len(miss)}/{len(eye['res'])} 个背驰处找不到自身颜色（{ratio:.0%}）")

        browser.close()

    if failures:
        print("\n❌ 存在不一致：")
        for f in failures:
            print(f"   - {f}")
        return 1
    print("\n✅ 背驰：数据 → option 坐标 → 屏幕像素，三段链路都对得上")
    print("⚠️ 这验证的是「画在哪」正确，**不等于背驰信号本身有效**。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
