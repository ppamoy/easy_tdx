#!/usr/bin/env python3
"""原文买卖点回测 V3 — 修复信号映射（用k.k_index精确匹配）。

关键修复：
  • 旧方法: str(bi.end.k.date)[:10] → 日期截断 → 匹配到当天第一根K线（可能差4小时）
  • 新方法: bi.end.k.k_index → 精确匹配到bi端点那根K线
"""
import json, sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, "/home/skp/workspace/easy_tdx/src")
from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig

CACHE_D = Path("/home/skp/workspace/easy_tdx/audit_data")
CACHE_M = Path("/home/skp/workspace/easy_tdx/audit_data_min")
COMMISSION, STAMP, SLIP = 0.0003, 0.001, 0.002
LAG = 3  # 确认延迟
SL_PCT, TP_PCT = 0.08, 0.25

STOCKS = [
    ("SH","600000","浦发银行"), ("SH","600036","招商银行"), ("SH","601318","中国平安"),
    ("SH","600276","恒瑞医药"), ("SH","600030","中信证券"), ("SZ","000333","美的集团"),
    ("SZ","000651","格力电器"), ("SZ","000725","京东方A"), ("SZ","300750","宁德时代"),
    ("SZ","002415","海康威视"),
]

def load(m, c, cat):
    d = CACHE_M if "min" in cat else CACHE_D
    slug = {"daily":"daily","30min":"30min","60min":"60min"}[cat]
    fp = d / f"{m.lower()}{c}_{slug}.json"
    if not fp.is_file(): return None
    rows = json.loads(fp.read_text("utf-8"))
    if not rows: return None
    df = pd.DataFrame(rows)
    for col in ("datetime","date"):
        if col in df.columns: df["datetime"]=pd.to_datetime(df[col]); break
    return df.sort_values("datetime").reset_index(drop=True)

def analyze(df, code):
    cfg = ChanlunConfig(zs_from_xd=True)
    r = ChanlunAnalyser(code=code, frequency="auto", config=cfg).process_klines(df)
    sigs = []
    for mmd in r.mmds:
        if mmd.bi is None: continue
        # ★ 关键修复：用 k.k_index 精确匹配
        bar_idx = mmd.bi.end.k.k_index
        if bar_idx < 0 or bar_idx >= len(df): continue
        t = mmd.mmd_type.value
        if "buy" in t: sigs.append({"b":bar_idx,"buy":True,"sell":False,"conf":mmd.confidence,"type":t})
        elif "sell" in t: sigs.append({"b":bar_idx,"buy":False,"sell":True,"conf":mmd.confidence,"type":t})
    sigs.sort(key=lambda s: s["b"])
    # 线段方向
    xds = []
    for xd in r.xds:
        if xd.start is None or xd.end is None: continue
        sd = str(xd.start.k.date)[:10]
        ed = str(xd.end.k.date)[:10]
        sp = float(getattr(xd.start.k, 'close', 0))
        ep = float(getattr(xd.end.k, 'close', 0))
        xds.append({"sd":sd,"ed":ed,"dir":"up" if ep>=sp else "down"})
    return sigs, xds, len(r.bis), len(r.zss)

def trend_at(daily_xds, date_str):
    d = None
    for x in daily_xds:
        if x["ed"] <= date_str: d = x["dir"]
        else: break
    return d

def sim(df, sigs, daily_xds=None, sl=False, tp=False, tf=False):
    cash, pos, ep = 1e6, 0, 0.0
    sells, wins = 0, 0
    sp = 0
    for bi in range(len(df)):
        if pos > 0:
            c = float(df.iloc[bi]["close"])
            if sl and c <= ep*(1-SL_PCT):
                p = c*(1-SLIP); cash += pos*p*(1-COMMISSION-STAMP)
                sells+=1; wins+=(1 if p>ep else 0); pos=0; ep=0; continue
            if tp and c >= ep*(1+TP_PCT):
                p = c*(1-SLIP); cash += pos*p*(1-COMMISSION-STAMP)
                sells+=1; wins+=(1 if p>ep else 0); pos=0; ep=0; continue
        while sp < len(sigs):
            s = sigs[sp]
            eb = s["b"] + LAG
            if eb > bi: break
            if eb < bi or eb >= len(df): sp+=1; continue
            c = float(df.iloc[eb]["close"])
            if c <= 0: sp+=1; continue
            if tf and daily_xds:
                ds = str(df.iloc[eb]["datetime"])[:10]
                tr = trend_at(daily_xds, ds)
                if tr == "up" and s["sell"]: sp+=1; continue
                if tr == "down" and s["buy"]: sp+=1; continue
            if s["buy"] and pos == 0:
                p = c*(1+SLIP); sh = int(cash*(1-COMMISSION)/(p*100))*100
                if sh <= 0: sp+=1; continue
                cash -= sh*p*(1-COMMISSION); pos=sh; ep=p
            elif s["sell"] and pos > 0:
                p = c*(1-SLIP); cash += pos*p*(1-COMMISSION-STAMP)
                sells+=1; wins+=(1 if p>ep else 0); pos=0; ep=0
            sp += 1
    fc = float(df.iloc[-1]["close"])
    if pos > 0:
        p = fc*(1-SLIP); cash += pos*p*(1-COMMISSION-STAMP)
        sells+=1; wins+=(1 if p>ep else 0)
    yr = (df.iloc[-1]["datetime"]-df.iloc[0]["datetime"]).days/365.25
    ann = ((cash/1e6)**(1/yr)-1)*100 if yr>0 else 0
    bh = ((fc/float(df.iloc[0]["close"]))**(1/yr)-1)*100 if yr>0 else 0
    wr = wins/sells*100 if sells>0 else 0
    return {"ann":round(ann,2),"bh":round(bh,2),"exc":round(ann-bh,2),
            "sig":len(sigs),"trd":sells,"wr":round(wr,1)}

# 测试: 日线 + 30min, 原文(zs_from_xd=True), 精确信号映射
CONFIGS = [
    ("日线原文",    "daily", False, False, False),
    ("30min原文",   "30min", False, False, False),
    ("30min+止损止盈","30min", True,  True,  False),
    ("30min+多级别", "30min", False, False, True),
    ("30min+全部",  "30min", True,  True,  True),
]

print("="*140)
print("原文买卖点回测 V3（修复信号映射: k.k_index精确匹配）")
print(f"模型: zs_from_xd=True  确认延迟: {LAG}根  止损{SL_PCT*100}% 止盈{TP_PCT*100}%")
print("="*140)
hdr = f"{'股票':10s}"
for n,_,_,_,_ in CONFIGS: hdr += f" | {n:>16s}"
hdr += f" | {'买入持有':>8s}"
print(hdr)
print("-"*len(hdr))

S = {n:{"ann":0,"exc":0,"sig":0,"trd":0,"wr":0,"n":0} for n,_,_,_,_ in CONFIGS}
BH = {"daily": {"ann":0,"n":0}, "30min": {"ann":0,"n":0}}

for mkt, code, name in STOCKS:
    # 预加载日线线段
    dfd = load(mkt, code, "daily")
    daily_xds = None
    if dfd is not None and len(dfd) >= 100:
        _, daily_xds, _, _ = analyze(dfd, code)

    row = f"{name:10s}"
    for cn, tf_cat, sl, tp, use_tf in CONFIGS:
        df = load(mkt, code, tf_cat)
        if df is None or len(df) < 100:
            row += f" | {'—':>16s}"
            continue
        sigs, _, bis, zs = analyze(df, code)
        r = sim(df, sigs, daily_xds if use_tf else None, sl, tp, use_tf)
        row += f" | {r['ann']:6.1f}%/{r['sig']:2d}sig"
        S[cn]["ann"]+=r["ann"]; S[cn]["exc"]+=r["exc"]
        S[cn]["sig"]+=r["sig"]; S[cn]["trd"]+=r["trd"]
        S[cn]["wr"]+=r["wr"]; S[cn]["n"]+=1
        # 买入持有
        if cn not in BH: continue
    # BH
    yr_d = (dfd.iloc[-1]["datetime"]-dfd.iloc[0]["datetime"]).days/365.25 if dfd is not None else 0
    bh_d = ((float(dfd.iloc[-1]["close"])/float(dfd.iloc[0]["close"]))**(1/yr_d)-1)*100 if yr_d>0 else 0
    BH["daily"]["ann"]+=bh_d; BH["daily"]["n"]+=1
    df30 = load(mkt, code, "30min")
    if df30 is not None:
        yr_30 = (df30.iloc[-1]["datetime"]-df30.iloc[0]["datetime"]).days/365.25
        bh_30 = ((float(df30.iloc[-1]["close"])/float(df30.iloc[0]["close"]))**(1/yr_30)-1)*100 if yr_30>0 else 0
        BH["30min"]["ann"]+=bh_30; BH["30min"]["n"]+=1
    row += f" | {bh_d:6.1f}%"
    print(row)

print("-"*len(hdr))
row = f"{'平均':10s}"
for cn, tf_cat, _,_,_ in CONFIGS:
    n = S[cn]["n"]
    if n==0: row += f" | {'—':>16s}"; continue
    a=S[cn]["ann"]/n; s=S[cn]["sig"]/n
    row += f" | {a:5.1f}%/{s:4.1f}sig"
row += f" | {BH['daily']['ann']/BH['daily']['n']:6.1f}%"
print(row)

print(f"\n详细汇总:")
print(f"{'方案':20s} | {'年化':>8s} | {'超额(vs同级别BH)':>16s} | {'信号/股':>8s} | {'交易/股':>8s} | {'胜率':>6s}")
print("-"*85)
for cn, tf_cat, _,_,_ in CONFIGS:
    n=S[cn]["n"]
    if n==0: continue
    bh_key = tf_cat
    bh_avg = BH[bh_key]["ann"]/BH[bh_key]["n"] if BH[bh_key]["n"]>0 else 0
    exc = S[cn]["ann"]/n - bh_avg
    print(f"{cn:20s} | {S[cn]['ann']/n:7.2f}% | {exc:+15.2f}% | "
          f"{S[cn]['sig']/n:7.1f} | {S[cn]['trd']/n:7.1f} | {S[cn]['wr']/n:5.1f}%")
for k in ("daily","30min"):
    if BH[k]["n"]>0:
        print(f"{'买入持有('+k+')':20s} | {BH[k]['ann']/BH[k]['n']:7.2f}% | {'—':>16s} | {'—':>8s} | {'—':>8s} | {'—':>6s}")
print("="*140)
