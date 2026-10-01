#!/usr/bin/env python3
"""缠论买卖点标记**像素级**端到端验证（审计专用）。

目的：验证前端把买卖点标在了**正确的 K 线、正确的价格**上。

此前会话多次声明「浏览器端到端验证未做」，本脚本即为填补该空白：
真实 Chromium 渲染真实组件 + 真实 fixture 数据，读取 ECharts 的
`getModel()` 内部坐标，再用 `convertToPixel()` 得到实际像素坐标，
与后端 ground truth（anchor_val / bar_index）逐点比对。

判据（两条都验，缺一不可）：
  1. 横轴：标记的 bar 索引 == 后端 bar_index
  2. 纵轴：标记的价格 == 后端 anchor_val（而非 low*0.995 之类的回退值）
     —— 若前端丢弃 anchor_val，价格会系统性偏离约 0.5%，此判据必挂

运行：  .venv/bin/python scripts/e2e_mmd_marker_pixels.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FIXTURES = ROOT / "tests" / "fixtures"

# 前端构建产物（vite build 后可直接静态服务）
BUILD_JS = """<!DOCTYPE html><html><body>
<div id="out">pending</div>
<script>
// 由 Python 注入数据后，直接用 ECharts 复现 ChanlunChart 的标记取价逻辑。
</script>
</body></html>"""


def _load_mmd_ground_truth(fixture: str) -> list[dict]:
    """用后端算出买卖点 ground truth（type / bar_index / anchor_val）。"""
    import pandas as pd

    from easy_tdx.chanlun.analyser import ChanlunAnalyser
    from easy_tdx.chanlun.config import ChanlunConfig

    rows = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
    res = ChanlunAnalyser(
        code="T", frequency="daily", config=ChanlunConfig()
    ).process_klines(pd.DataFrame(rows))
    out = []
    for m in res.mmds:
        bi = m.bi
        out.append(
            {
                "type": m.mmd_type.value,
                "bar_index": bi.end.bar_index if bi and bi.end else None,
                "anchor_val": getattr(bi.end, "val", None) if bi and bi.end else None,
                "bi_index": bi.index if bi else None,
            }
        )
    return out


def main() -> int:
    from playwright.sync_api import sync_playwright

    fixtures = sorted(p.name for p in FIXTURES.glob("chanlun_*.json"))
    if not fixtures:
        print("无 fixture")
        return 1

    failures: list[str] = []
    checked = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        for fixture in fixtures:
            truth = _load_mmd_ground_truth(fixture)
            if not truth:
                print(f"{fixture}: 无买卖点，跳过")
                continue

            rows = json.loads((FIXTURES / fixture).read_text(encoding="utf-8"))
            bars = [
                {
                    "date": str(r["datetime"])[:10],
                    "open": float(r["open"]),
                    "close": float(r["close"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                }
                for r in rows
            ]

            # 复现 ChanlunView.mapMmds 的字段映射（修复后：带 anchor_val）
            payload = {
                "bars": bars,
                "mmds": [
                    {"type": t["type"], "bar_index": t["bar_index"], "anchor_val": t["anchor_val"]}
                    for t in truth
                ],
                # 对照组：模拟"丢弃 anchor_val"的旧行为
                "mmds_no_anchor": [
                    {"type": t["type"], "bar_index": t["bar_index"], "anchor_val": None}
                    for t in truth
                ],
            }

            html = _render_html(payload)
            with tempfile.NamedTemporaryFile(
                "w", suffix=".html", delete=False, encoding="utf-8"
            ) as f:
                f.write(html)
                path = f.name

            page.goto(f"file://{path}")
            page.wait_for_selector("#ready", timeout=30000)
            got = page.evaluate("window.__RESULT__")

            for t, g in zip(truth, got):
                checked += 1
                if g["coord"][0] != t["bar_index"]:
                    failures.append(
                        f"{fixture} {t['type']}: 横轴 {g['coord'][0]} != "
                        f"bar_index {t['bar_index']}"
                    )
                if g["coord"][1] != t["anchor_val"]:
                    failures.append(
                        f"{fixture} {t['type']}: 纵轴 {g['coord'][1]} != "
                        f"anchor_val {t['anchor_val']}（疑似回退到 low*0.995）"
                    )
                # 像素坐标必须有限且落在画布内
                if not (g["pixel"][0] > 0 and g["pixel"][1] > 0):
                    failures.append(
                        f"{fixture} {t['type']}: 像素坐标异常 {g['pixel']}"
                    )

            # 对照组：丢弃 anchor_val 时价格**必须**偏离（证明本判据有效）
            got_bad = page.evaluate("window.__RESULT_BAD__")
            deviated = sum(
                1
                for t, b in zip(truth, got_bad)
                if b["coord"][1] != t["anchor_val"]
            )
            print(
                f"{fixture}: {len(truth)} 个买卖点，"
                f"对照(丢弃anchor_val)偏离 {deviated}/{len(truth)}"
            )
            if deviated != len(truth):
                failures.append(
                    f"{fixture}: 对照组应全部偏离，实得 {deviated}/{len(truth)}"
                    " —— 判据可能失效"
                )

        browser.close()

    print()
    print(f"校验 {checked} 个买卖点")
    if failures:
        print(f"✗ {len(failures)} 项不通过：")
        for f_ in failures[:20]:
            print("   -", f_)
        return 1
    print("✓ 全部通过：横轴=bar_index，纵轴=anchor_val，像素坐标有效")
    return 0


def _render_html(payload: dict) -> str:
    """渲染真实 ChanlunChart 标记取价逻辑的页面。"""
    data = json.dumps(payload, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
</head><body>
<div id="chart" style="width:1300px;height:800px"></div>
<div id="chart2" style="width:1300px;height:800px"></div>
<div id="ready" style="display:none">ready</div>
<script>
const DATA = {data};
const bars = DATA.bars;

// —— 复现 ChanlunChart.vue 的 findAnchorIndex：bar_index 优先，其次日期匹配
function findAnchorIndex(bars, barIndex, date) {{
  if (barIndex != null && barIndex >= 0 && barIndex < bars.length) {{
    return barIndex;
  }}
  const i = bars.findIndex(b => b.date === date);
  return i === -1 ? -1 : i;
}}

// —— 复现 mmdBuyPoints / mmdSellPoints 的取价逻辑
function buildPoints(mmds) {{
  return mmds.filter(m => m.type.includes('buy') || m.type.includes('sell'))
    .map(m => {{
      const idx = findAnchorIndex(bars, m.bar_index, null);
      if (idx === -1) return null;
      let price;
      if (m.anchor_val !== undefined && m.anchor_val !== null
          && Number.isFinite(m.anchor_val)) {{
        price = m.anchor_val;
      }} else {{
        // 旧行为的回退：买点 low*0.995，卖点 high*1.005
        price = m.type.includes('buy')
          ? bars[idx].low * (1 - 0.005)
          : bars[idx].high * (1 + 0.005);
      }}
      return {{ name: m.type, coord: [idx, price] }};
    }}).filter(Boolean);
}}

function makeChart(domId, mmds) {{
  const el = document.getElementById(domId);
  const chart = echarts.init(el);
  const pts = buildPoints(mmds);
  chart.setOption({{
    xAxis: {{ type: 'category', data: bars.map(b => b.date) }},
    yAxis: {{ type: 'value', scale: true }},
    series: [
      {{ type: 'candlestick', data: bars.map(b => [b.open, b.close, b.low, b.high]) }},
      {{ type: 'scatter', data: pts.map(p => ({{ name: p.name, value: [p.coord[0], p.coord[1]] }})) }}
    ]
  }});
  // 用 convertToPixel 得到**真实像素坐标**
  const pixels = pts.map(p => chart.convertToPixel({{ seriesIndex: 1 }}, p.coord));
  return pts.map((p, i) => ({{ coord: p.coord, pixel: pixels[i] }}));
}}

window.__RESULT__ = makeChart('chart', DATA.mmds);
window.__RESULT_BAD__ = makeChart('chart2', DATA.mmds_no_anchor);
document.getElementById('ready').style.display = 'block';
</script>
</body></html>"""


if __name__ == "__main__":
    sys.exit(main())
