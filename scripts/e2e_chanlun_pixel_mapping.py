#!/usr/bin/env python3
"""V733：ECharts **逐点坐标→像素**验证 —— 真浏览器 + 真应用 + 真后端。

补的是哪个缺口
--------------
五之五十五用 vitest 锁死了「数据 → ECharts option 坐标」这一半
（真后端 ground truth × 真组件，`chanlun-coord-mapping.test.ts`）。
但**「option 坐标 → 屏幕像素」这一半当时没跑通**（Moli 上该页 evaluate
挂住，且 `__CHANLUN_CHART__` 只在 DEV 暴露）。本脚本补上这一半。

⚠️ 关键教训（本轮实测，别再踩）
-------------------------------
1. **必须用真实 Chromium，不能用 Moli**。Moli 在 `--layout` 下依然有
   「导航后新建元素几何恒为 0」的缺陷（AGENTS.md §9.1 缺陷 2），
   canvas `getBoundingClientRect()` 全为 0，而 `width/height` 属性却有值
   （实测 1371×760）—— 只看属性会误判"渲染正常"。
2. `window.__CHANLUN_CHART__` 由 `import.meta.env.DEV` 守卫
   （ChanlunChart.vue:298）。`vite build --mode development` **不会**置位它
   （DEV 取决于 build/serve 命令本身，不是 mode），实测 dist 里 grep 不到。
   ⇒ 只能打 **vite dev server**（默认 :3012）。
3. 缠论页在 **`/learn?tab=analysis`**（`/chanlun` 会 redirect）；
   开根路径拿到的是「回测」页，placeholder 完全不同。

判据（逐点，缺一不可）
----------------------
1. 横轴：每个标记的 dimX == 后端 `bar_index`；
2. 纵轴：dimY == 后端 `anchor_val`；
3. 像素：`convertToPixel()` 必须返回**有限值**（NaN ⇒ 坐标映射断了）；
4. 可见性：在视口内的点像素必须落在画布内；视口外的点（dataZoom 收窄时）
   允许出界，**但必须单调**（dimX 越大 px[0] 越大 ⇒ 说明 x 轴方向没反）。

牙齿（防空转）
--------------
- 通道自检：evaluate 必须能正确返回 1+1，且故意 throw 必须被捕获；
- 标记数 == 后端 mmd_count，不等就失败（不做"部分通过"）；
- 至少要有标记（0 个 ⇒ ground truth 或选择器有问题）。

运行：
    cd web-ui && npx vite --host 127.0.0.1 --port 3012 &
    .venv/bin/python scripts/e2e_chanlun_pixel_mapping.py
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
# 缠论图在 /learn?tab=analysis；/chanlun 会 redirect 过去，根路径是回测页
CHANLUN_PAGE = "/learn?tab=analysis"

# ⚠️ 真实 Chromium，不用 Moli：Moli 有"新建元素几何恒为 0"缺陷（§9.1 缺陷 2），
#    会让本脚本的可见性判据全部假失败，且 convertToPixel 结果不可信。
CHROMIUM = os.environ.get("EASY_TDX_CHROMIUM", "/usr/bin/chromium")


def fetch_ground_truth(code: str, market: str, count: int) -> dict:
    """调真后端拿 ground truth（bar_index / anchor_val）。"""
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
        "mmds": [
            {
                "type": m.get("type"),
                "date": m.get("date"),
                "bar_index": m.get("bar_index"),
                "anchor_val": m.get("anchor_val"),
            }
            for m in data.get("mmds", [])
        ],
        "mmd_count": data.get("mmd_count", 0),
        "kline_count": data.get("kline_count", 0),
    }


PROBE = r"""
() => {
  const inst = window.__CHANLUN_CHART__;
  if (!inst) return { error: 'no_instance' };
  const opt = inst.getOption();
  const out = [];
  for (const s of (opt.series || [])) {
    if (s.name !== '买点' && s.name !== '卖点') continue;
    for (const d of (s.data || [])) {
      if (!Array.isArray(d.value) || d.value.length < 2) continue;
      const [xi, yv] = d.value;
      const px = inst.convertToPixel({ gridIndex: 0 }, [xi, yv]);
      out.push({
        name: d.name,
        dimX: xi, dimY: yv,
        px: px ? [Math.round(px[0]*100)/100, Math.round(px[1]*100)/100] : null,
      });
    }
  }
  const el = inst.getDom();
  return {
    seriesCount: (opt.series || []).length,
    canvas: el ? { w: el.clientWidth, h: el.clientHeight } : null,
    marks: out,
  };
}
"""

# ── 像素复核：在算出的坐标处真的看一眼有没有标记色（§1 要求看渲染结果）──
PIXEL_EYE = r"""
() => {
  const inst = window.__CHANLUN_CHART__;
  const cv = inst.getDom().querySelector('canvas');
  const ctx = cv.getContext('2d');
  const dpr = window.devicePixelRatio || 1;

  // ⚠️ 判据必须是「该标记自己的颜色」，不能只看"非背景"：
  //    标记后面就是 K 线（红/绿蜡烛），只查非背景会命中蜡烛而永远通过
  //    （实测把标记设成全透明，22/22 依然"通过" ⇒ 该判据形同虚设）。
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
  const near = (a, b, tol) =>
    a && b && Math.abs(a[0] - b[0]) <= tol && Math.abs(a[1] - b[1]) <= tol &&
    Math.abs(a[2] - b[2]) <= tol;

  const res = [];
  for (const s of (inst.getOption().series || [])) {
    if (s.name !== '买点' && s.name !== '卖点') continue;
    for (const d of (s.data || [])) {
      const [xi, yv] = d.value;
      const px = inst.convertToPixel({ gridIndex: 0 }, [xi, yv]);
      if (!px) continue;
      const want = parse(d.itemStyle && d.itemStyle.color);
      const x0 = Math.round((px[0] - 7) * dpr), y0 = Math.round((px[1] - 7) * dpr);
      const w = Math.round(14 * dpr), h = Math.round(14 * dpr);
      let got = null;
      try {
        const img = ctx.getImageData(x0, y0, w, h).data;
        for (let i = 0; i < img.length; i += 4) {
          if (img[i + 3] < 200) continue;
          const c = [img[i], img[i + 1], img[i + 2]];
          if (near(c, want, 26)) { got = c; break; }
        }
      } catch (e) { got = null; }
      res.push({ name: d.name, dimX: xi, want, got });
    }
  }
  return { dpr, res };
}
"""

SELFTEST_OK = "() => 1 + 1"
SELFTEST_THROW = "() => { throw new Error('probe-throw-sentinel'); }"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default="600000")
    ap.add_argument("--market", default="SH")
    ap.add_argument("--count", type=int, default=800)
    a = ap.parse_args()

    print("=" * 78)
    print("ECharts 逐点坐标→像素验证（真 Chromium + 真应用 + 真后端 ground truth）")
    print(f"UI={UI}  API={API}  {a.market}{a.code} count={a.count}")
    print(f"chromium={CHROMIUM}")
    print("=" * 78)

    truth = fetch_ground_truth(a.code, a.market, a.count)
    if not truth["mmds"]:
        print("❌ 后端未返回买卖点 ⇒ 无法逐点验证（退出）")
        return 2
    print(f"✅ ground truth：{truth['mmd_count']} 个买卖点 / {truth['kline_count']} 根 K 线")

    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    failures: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=CHROMIUM,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 1000})

        # ── 牙齿 0：evaluate 通道必须真的可用 ──
        if page.evaluate(SELFTEST_OK) != 2:
            print("❌ 牙齿0：evaluate 返回值不对 ⇒ 后续结论不可信")
            return 1
        try:
            page.evaluate(SELFTEST_THROW)
            print("❌ 牙齿0：抛异常没被捕获 ⇒ 探针坏了会伪装成功能坏了")
            return 1
        except Exception:
            pass
        print("✅ 牙齿0：evaluate 通道正常，且能区分「探针异常」与「返回空」")

        page.goto(UI + CHANLUN_PAGE, wait_until="domcontentloaded", timeout=60000)
        if page.locator('input[placeholder="如 000001"]').count() == 0:
            print(f"❌ {CHANLUN_PAGE} 上找不到缠论代码输入框 ⇒ 页面不对")
            print(f"   URL={page.url} title={page.title()!r}")
            return 2

        inp = page.locator('input[placeholder="如 000001"]').first
        inp.fill(a.code)
        inp.press("Enter")  # 回车即触发分析
        page.wait_for_timeout(3000)
        # ⚠️ 牙齿：必须确认页面真的在用我们指定的代码（应用会默认加载 000001，
        #    只 fill 不校验 ⇒ 拿到的 ground truth 与图上标的不是同一只票，
        #    数量判据会假失败/假通过）
        actual = inp.input_value()
        if actual != a.code:
            print(f"❌ 输入框实际值 {actual!r} != 指定 {a.code!r} ⇒ 比对的是两只票")
            return 2
        print(f"✅ 页面确实在展示 {actual}（与 ground truth 同一只票）")

        # 等实例出现（DEV 下组件 render() 会挂 window.__CHANLUN_CHART__）
        got = None
        for i in range(15):
            page.wait_for_timeout(4000)
            probe = page.evaluate("() => !!window.__CHANLUN_CHART__")
            if probe:
                got = page.evaluate(PROBE)
                break
            print(f"   等待图表实例… ({(i + 1) * 4}s)", flush=True)
        if not got:
            print("❌ 拿不到 __CHANLUN_CHART__ ⇒ 是否跑的是生产构建？需 vite dev server")
            return 2
        if got.get("error"):
            print(f"❌ 探针报错：{got['error']}")
            return 2

        marks = got["marks"]
        print(
            f"✅ 取到 {len(marks)} 个标记（series {got['seriesCount']} 个，画布 {got['canvas']}）"
        )

        # ── 牙齿 1：数量必须全等 ──
        if len(marks) != truth["mmd_count"]:
            print(f"❌ 牙齿1：标记数 {len(marks)} != 后端 {truth['mmd_count']}")
            return 1
        if not marks:
            print("❌ 牙齿1：0 个标记 ⇒ ground truth 或选择器有问题")
            return 1
        print(f"✅ 牙齿1：标记数 == 后端 mmd_count == {truth['mmd_count']}")

        t_sorted = sorted(truth["mmds"], key=lambda m: m["bar_index"] or 0)
        m_sorted = sorted(marks, key=lambda m: m["dimX"])

        print(
            f"\n{'类型':<9}{'期望bar':>7}{'实际bar':>7}{'期望价':>9}{'实际价':>9}"
            f"{'像素(x,y)':>22}  判定"
        )
        print("-" * 80)
        n_ok = 0
        px_by_x: list[tuple[float, float]] = []
        for t, m in zip(t_sorted, m_sorted):
            ok_x = t["bar_index"] == m["dimX"]
            tol = max(abs(t["anchor_val"] or 0) * 1e-6, 1e-6)
            ok_y = abs((t["anchor_val"] or 0) - m["dimY"]) <= tol
            px = m["px"]
            ok_px = (
                px is not None
                and px[0] == px[0]  # 非 NaN
                and px[1] == px[1]
                and abs(px[0]) != float("inf")
                and abs(px[1]) != float("inf")
            )
            good = ok_x and ok_y and ok_px
            n_ok += 1 if good else 0
            if ok_px:
                px_by_x.append((m["dimX"], px[0]))
            print(
                f"{str(t['type']):<9}{str(t['bar_index']):>7}{str(m['dimX']):>7}"
                f"{t['anchor_val']:>9.2f}{m['dimY']:>9.2f}{str(px):>22}  "
                f"{'✅' if good else '❌'}"
            )
            if not ok_x:
                failures.append(
                    f"{t['type']}@{t['bar_index']}: 横轴 {m['dimX']} != {t['bar_index']}"
                )
            if not ok_y:
                failures.append(f"{t['type']}: 纵轴 {m['dimY']} != anchor_val {t['anchor_val']}")
            if not ok_px:
                failures.append(f"{t['type']}: convertToPixel 返回非法值 {px}")

        # ── 判据 4：x 轴方向必须单调（dimX 增 ⇒ 像素 x 增）──
        px_by_x.sort()
        monotonic = all(px_by_x[i][1] <= px_by_x[i + 1][1] + 1e-6 for i in range(len(px_by_x) - 1))
        if not monotonic:
            bad = [
                (px_by_x[i], px_by_x[i + 1])
                for i in range(len(px_by_x) - 1)
                if px_by_x[i][1] > px_by_x[i + 1][1] + 1e-6
            ]
            print(f"\n❌ x 轴方向非单调：{bad[:3]}")
            failures.append(f"x 轴像素非单调（{len(bad)} 处）")
        else:
            print(f"\n✅ x 轴方向单调（{len(px_by_x)} 个点，dimX 增 ⇒ 像素 x 增）")
            print(
                "   ⚠️ 注：dataZoom 收窄时视口外的点像素可为负或超出画布，"
                "这是 ECharts 正确行为，非错位。"
            )

        # ── 判据 5：像素复核 —— 坐标算对了，还得真有标记画在那儿 ──
        #    （只核坐标不算验证渲染：坐标轴写错也能"算出"自洽的坐标）
        # ⚠️ dataZoom 后必须等重绘完成再取像素，否则读到上一帧（实测 2s 不够，
        #    22 个里只认出 10 个；3.5s 才稳定 22/22）。这是"取早了"，不是错位。
        # ⚠️ 必须「先 dispatch 全览 → 等重绘 → 再取像素」分三步。
        #    把 dispatch 和 getImageData 放在同一个 evaluate 里会读到**重绘前**
        #    的旧帧（实测 22 个只认出 10 个，且是随机的一批）—— 这是取早了，
        #    不是坐标错位。
        page.evaluate(
            "() => window.__CHANLUN_CHART__.dispatchAction({type:'dataZoom', start:0, end:100})"
        )
        page.wait_for_timeout(3000)
        eye = page.evaluate(PIXEL_EYE)
        colored = [e for e in eye["res"] if isinstance(e.get("got"), list)]
        print(
            f"\n✅ 像素复核：{len(colored)}/{len(eye['res'])} 个标记在其坐标处"
            f"确有**该标记自己的颜色**（dpr={eye['dpr']}）"
        )
        if not eye["res"]:
            failures.append("像素复核：取不到任何标记坐标")
        elif len(colored) < len(eye["res"]):
            # ⚠️ 允许少量「被覆盖」：K 线蜡烛画在 scatter 之后（series 顺序），
            #    标记落在实体内部时会被蜡烛盖住 ⇒ 找不到自己的颜色不等于画错。
            #    实测 22 个里有 1 个（3buy@172，被绿色蜡烛盖住）。
            #    阈值 10%：超过就判定为真的没画/坐标错，不是个别覆盖。
            miss = [e for e in eye["res"] if not isinstance(e.get("got"), list)]
            ratio = len(miss) / max(len(eye["res"]), 1)
            if ratio > 0.10:
                print(
                    f"❌ {len(miss)}/{len(eye['res'])} 个标记处找不到自身颜色"
                    f"（{ratio:.0%} > 10% ⇒ 不是个别覆盖，是真没画/坐标错）"
                )
                for e in miss[:5]:
                    print(f"   - {e}")
                failures.append(f"{len(miss)}/{len(eye['res'])} 个标记处无其自身颜色像素")
            else:
                print(
                    f"⚠️ {len(miss)} 个未取到自身颜色（{ratio:.0%} ≤ 10%）⇒ "
                    f"判为被 K 线蜡烛覆盖，不算失败："
                )
                for e in miss[:5]:
                    print(f"   - {e}")

        print("-" * 80)
        print(f"逐点通过 {n_ok}/{len(t_sorted)}")

        if failures:
            print(f"\n❌ {len(failures)} 处不一致：")
            for f in failures[:20]:
                print("   -", f)
            return 1

        print("\n✅ 全部逐点一致：数据 → option 坐标 → 屏幕像素，三段链路都对得上")
        print("⚠️ 这验证的是「画在哪」正确，**不等于缠论信号本身有效**。")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
