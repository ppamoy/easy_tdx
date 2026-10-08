"""train 页 e2e：沉淀本轮手工验证为可复用脚本（可加进 verify_fx_pages 家族）。

验证点：
1. 开始训练后图上出现分型（此前因 valid_fractals 漏传恒为 0）
2. MACD 副图有数据（此前因 macd 漏传恒缺）
3. 切线段级别有笔、切回笔级别恢复（此前因 levels 漏传空图）
用法：python3 scripts/verify_train_e2e.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pw import chromium_path, import_playwright, launch_pw, ui_base

JS = """() => {
  const c=window.__CHANLUN_CHART__;
  const o=c&&c.getOption&&c.getOption();
  if(!o) return null;
  const cnt=n=>{const s=(o.series||[]).find(x=>x.name===n);return s?(s.data||[]).length:0;};
  const ml=n=>{const s=(o.series||[]).find(x=>x.name===n);
    return (s&&s.markLine)?(s.markLine.data||[]).length:0;};
  const macd=(o.series||[]).filter(
    x=>['MACD','DIF','DEA'].includes(x.name)&&((x.data||[]).length>0)).length;
  return {笔:ml('笔(虚线)'), 顶:cnt('顶分型'), 底:cnt('底分型'), macd系列数:macd};
}"""

def main() -> int:
    api = import_playwright()
    with api.sync_playwright() as pw:
        b = launch_pw(pw)
        pg = b.new_page(viewport={"width": 1600, "height": 1200})
        pg.goto(ui_base() + "/learn?tab=train", wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_timeout(5000)
        pg.locator("button", has_text="开始训练").first.click()
        pg.wait_for_timeout(15000)
        r0 = pg.evaluate(JS)
        print("笔级别:", r0)
        errs = []
        if not r0 or r0["顶"] + r0["底"] == 0:
            errs.append("图上 0 分型 —— valid_fractals 疑似漏传")
        if not r0 or r0["macd系列数"] < 3:
            errs.append("MACD 副图缺失 —— macd 疑似漏传")
        sel = pg.locator("select").filter(has=pg.locator("option[value='xd']")).first
        sel.select_option("xd")
        pg.wait_for_timeout(4000)
        r1 = pg.evaluate(JS)
        print("线段级别:", r1)
        # 揭示窗口可能还没到第一根 xd 笔的位置——推进到底再判定
        if r1 and r1["笔"] == 0:
            for _ in range(85):
                try:
                    pg.locator("button", has_text="揭示 +5 根").first.click(timeout=1200)
                except Exception:
                    break
            pg.wait_for_timeout(5000)
            r1 = pg.evaluate(JS)
            print("线段级别(全揭示):", r1)
        sel.select_option("bi")
        pg.wait_for_timeout(4000)
        r2 = pg.evaluate(JS)
        print("切回笔:", r2)
        if r1 and r1["笔"] == 0:
            errs.append("线段级别全揭示后仍 0 笔 —— levels 疑似漏传")
        # 恢复判定：切回后分型数应等于 bi 全量（props.validFxs），
        # 而非初始揭示窗口内的个数（r0 只画前几根）。
        full = pg.evaluate(
            "() => document.querySelector('.chanlun-chart')"
            "?.__vueParentComponent?.props?.validFxs?.length ?? -1"
        )
        if r2 and full >= 0 and (r2["顶"] + r2["底"]) != full:
            errs.append(f"切回笔级别后分型 {(r2['顶'] + r2['底'])} != props {full} —— 恢复不完整")
        b.close()
    if errs:
        print("❌ train 页契约破坏：")
        for e in errs:
            print("  ·", e)
        return 1
    print("✅ train 页数据契约完整（分型/MACD/级别切换）")
    return 0

if __name__ == "__main__":
    sys.exit(main())
