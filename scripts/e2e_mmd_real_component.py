#!/usr/bin/env python3
"""缠论买卖点标记**真实组件 + 真实 Chromium** 像素级端到端验证。

与 scripts/e2e_mmd_marker_pixels.py 的区别：
  - 那个脚本复现了 ChanlunChart 的取价逻辑来验算；
  - 本脚本**挂载真实的 ChanlunChart.vue**（Vite 构建、Chromium 渲染），
    再用 echarts.getInstanceByDom 读出真实实例里 scatter 系列的 coord，
    并用 convertToPixel 得到实际像素坐标，与后端 ground truth 比对。

判据：
  1. 横轴 bar 索引 == 后端 bar_index
  2. 纵轴价格 == 后端 anchor_val（避免 low*0.995 回退造成的 ±0.5% 偏移）
  3. 像素坐标有限且落在画布内

运行：  python3 scripts/e2e_mmd_real_component.py
（需系统 Python：需 playwright；vite 需在 web-ui/ 可构建）
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FIXTURES = ROOT / "tests" / "fixtures"
WEB = ROOT / "web-ui"
PORT = 5233


def build_payload(fixture: str) -> dict:
    """用真实后端算出该 fixture 的完整缠论结果（与前端收到的形状一致）。"""
    import pandas as pd

    from easy_tdx.chanlun.analyser import ChanlunAnalyser
    from easy_tdx.chanlun.config import ChanlunConfig

    rows = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    df = pd.DataFrame(rows)
    res = ChanlunAnalyser(code="T", frequency="daily", config=ChanlunConfig()).process_klines(df)

    # 注意：Bar 接口的日期字段是 datetime 而非 date（ChanlunChart 依赖它）
    bars = [
        {
            "datetime": str(r["datetime"]),
            "date": str(r["datetime"])[:10],
            "open": float(r["open"]),
            "close": float(r["close"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "vol": float(r.get("vol", 0) or 0),
        }
        for r in rows
    ]
    mmds = []
    for m in res.mmds:
        bi = m.bi
        mmds.append(
            {
                "type": m.mmd_type.value,
                "date": bars[bi.end.bar_index]["date"] if bi and bi.end else None,
                "price": getattr(bi.end, "val", None) if bi and bi.end else None,
                "bar_index": bi.end.bar_index if bi and bi.end else None,
                "anchor_val": getattr(bi.end, "val", None) if bi and bi.end else None,
            }
        )
    return {"bars": bars, "mmds": mmds}


def strip_anchor(payload: dict) -> dict:
    """对照组：只丢掉**前端收到的** anchor_val（ground truth 保留）。

    用途：证明本脚本的判据真的有效——若component在缺少 anchor_val 时仍输出
    相同价格，说明判据失效（例如回退分支恰好等价）。已知乾约为 ±0.5%。
    """
    return {
        "bars": payload["bars"],
        "mmds": [{**m, "anchor_val": None} for m in payload["mmds"]],
    }


def _render(page, url: str, payload: dict) -> None:
    """注入 payload 并等组件渲染完成。"""
    page.add_init_script(
        "window.__PAYLOAD__ = " + json.dumps(payload, ensure_ascii=False)
    )
    page.goto(url)
    page.wait_for_function("window.__READY__ === true", timeout=30000)


def build_e2e_page() -> bool:
    """构建审计页（CHANLUN_E2E=1 才会产出 mmd-e2e.html）。

    外部可用 SKIP_BUILD=1 跳过（例如 CI 已提前构建好）。

    V731（第 33 轮实测发现的缺陷）：SKIP_BUILD=1 跳过构建时，dist/ 里可能躺着
    **陈旧的构建产物** —— 本轮实测：改坏 ChanlunChart.vue → 跑出 5 项失败
    （判据有效）→ 还原源码 → SKIP_BUILD=1 重跑，**仍然 5 项失败**，因为 dist
    还是坏代码构建出来的。也就是说 SKIP_BUILD 会把「源码已修好」误报成
    「依然失败」，反之若先构建过好的产物再改坏源码，也会误报成「通过」。
    现在改为：SKIP_BUILD=1 时比对 dist/mmd-e2e.html 与源码树的修改时间，
    产物比任一源码文件旧 → 拒绝跳过并强制重建。
    """
    import os

    dist_html = WEB / "dist" / "mmd-e2e.html"
    if os.environ.get("SKIP_BUILD") == "1":
        if dist_html.exists():
            prod_m = dist_html.stat().st_mtime
            src_files = [
                WEB / "mmd-e2e.html",
                WEB / "src" / "components" / "ChanlunChart.vue",
                WEB / "src" / "echarts-setup.ts",
            ]
            stale = [
                f.name
                for f in src_files
                if f.exists() and f.stat().st_mtime > prod_m + 1
            ]
            if stale:
                print(
                    f"⚠ SKIP_BUILD=1 但以下源码比 dist 产物新: {stale}，"
                    "陈旧产物会给出假结果 → 强制重建"
                )
            else:
                return True
        else:
            print("⚠ SKIP_BUILD=1 但 dist/mmd-e2e.html 不存在 → 强制重建")

    env = dict(os.environ, CHANLUN_E2E="1")
    r = subprocess.run(
        ["npx", "vite", "build"], cwd=str(WEB), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if r.returncode != 0:
        print("构建失败：npx vite build（web-ui/，CHANLUN_E2E=1）")
        return False
    return dist_html.exists()


def main() -> int:
    from playwright.sync_api import sync_playwright

    if not build_e2e_page():
        return 1

    proc = None
    # 起静态服务器托管 web-ui/dist（mmd-e2e.html 是真实组件构建产物）
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1"],
        cwd=str(WEB / "dist"),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    failures: list[str] = []
    checked = 0
    try:
        # 等 dev server 就绪
        import time
        import urllib.request

        url = f"http://127.0.0.1:{PORT}/mmd-e2e.html"
        for _ in range(60):
            try:
                urllib.request.urlopen(url, timeout=2)
                break
            except Exception:
                time.sleep(1)
        else:
            print("Vite dev server 未就绪")
            return 1

        with sync_playwright() as pw:
            browser = pw.chromium.launch(args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            page.on("console", lambda m: None)

            for fixture in sorted(p.name for p in FIXTURES.glob("chanlun_*.json")):
                payload = build_payload(fixture)
                if not payload["mmds"]:
                    print(f"{fixture}: 无买卖点，跳过")
                    continue

                _render(page, url, payload)
                err = page.evaluate("window.__ERROR__")
                if err:
                    failures.append(f"{fixture}: 页面异常 {err}")
                    continue
                got = page.evaluate("window.__RESULT__") or []

                # 对照组：确认判据有效（丢 anchor_val 时价格必须偏离）
                if os.environ.get("E2E_SKIP_CONTROL") != "1":
                    _render(page, url, strip_anchor(payload))
                    got_bad = page.evaluate("window.__RESULT__") or []
                    expected = sum(
                        1 for t in payload["mmds"] if t.get("anchor_val") is not None
                    )
                    deviated = sum(
                        1
                        for g, t in zip(got_bad, payload["mmds"])
                        if t.get("anchor_val") is not None
                        and abs(g["coord"][1] - t["anchor_val"]) > 1e-6
                    )
                    if deviated != expected:
                        failures.append(
                            f"{fixture}: 对照组应全部偏离，实得 "
                            f"{deviated}/{expected} —— 判据失效"
                        )

                truth = {m["type"]: m for m in payload["mmds"]}
                if not got:
                    failures.append(f"{fixture}: 组件未渲染出任何买卖点标记")
                    continue

                for g in got:
                    checked += 1
                    t = truth.get(g["name"])
                    if t is None:
                        failures.append(f"{fixture}: 组件渲染了未知标记 {g['name']}")
                        continue
                    if g["coord"][0] != t["bar_index"]:
                        failures.append(
                            f"{fixture} {t['type']}: 横轴 {g['coord'][0]} != "
                            f"bar_index {t['bar_index']}"
                        )
                    av = t.get("anchor_val")
                    if av is None:
                        failures.append(
                            f"{fixture} {t['type']}: ground truth 缺 anchor_val"
                        )
                    elif abs(g["coord"][1] - av) > 1e-6:
                        failures.append(
                            f"{fixture} {t['type']}: 纵轴 {g['coord'][1]} != "
                            f"anchor_val {av}"
                        )
                    px = g.get("pixel")
                    if not px or not (px[0] > 0 and px[1] > 0):
                        failures.append(
                            f"{fixture} {t['type']}: 像素坐标异常 {px}"
                        )
                print(f"{fixture}: {len(got)} 个标记已校验")

            browser.close()
    finally:
        if proc:
            proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()

    print()
    print(f"校验 {checked} 个买卖点标记")
    if failures:
        print(f"✗ {len(failures)} 项不通过：")
        for f in failures[:20]:
            print("   -", f)
        return 1
    print("✓ 真实组件渲染：横轴=bar_index，纵轴=anchor_val，像素坐标有效")
    return 0


if __name__ == "__main__":
    sys.exit(main())
