#!/usr/bin/env python3
"""原文买卖点低级别回测 V2 — 修正置信度阈值，测试多级别+止损止盈组合。"""
import json, sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, "/home/skp/workspace/easy_tdx/src")
from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig

CACHE_D = Path("/home/skp/workspace/easy_tdx/audit_data")
CACHE_M = Path("/home/skp/workspace/easy_tdx/audit_data_min")
COMMISSION, STAMP, SLIP, LAG = 0.0003, 0.001, 0.002, 3
SL_PCT, TP_PCT = 0.08, 0.25
MIN_CONF = 0.4  # 修正：从0.7降到0.4（实际置信度max=0.56, mean=0.37）

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
        ds = str(mmd.bi.end.k.date)[:10]
        mask = df["datetime"].dt.strftime("%Y-%m-%d") == ds
        idx = df.index[mask]
        if len(idx)==0: continue
        t = mmd.mmd_type.value
        if "buy" in t: sigs.append({"b":idx[0],"date":df.iloc[idx[0]]["datetime"],"buy":True,"sell":False,"conf":mmd.confidence,"type":t})
        elif "sell" in t: sigs.append({"b":idx[0],"date":df.iloc[idx[0]]["datetime"],"buy":False,"sell":True,"conf":mmd.confidence,"type":t})
    sigs.sort(key=lambda s: s["b"])
    xds = []
    for xd in r.xds:
        if xd.start is None or xd.end is None: continue
        sd = str(xd.start.k.date)[:10]
        ed = str(xd.end.k.date)[:10]
        sp = float(getattr(xd.start.k, 'close', getattr(xd.start.k, 'high', 0)))
        ep = float(getattr(xd.end.k, 'close', getattr(xd.end.k, 'high', 0)))
        xds.append({"sd":sd,"ed":ed,"dir":"up" if ep>=sp else "down"})
    return sigs, xds, len(r.bis), len(r.zss)

def trend_at(daily_xds, date_str):
    d = None
    for x in daily_xds:
        if x["ed"] <= date_str: d = x["dir"]
        else: break
    return d

def sim(df, sigs, daily_xds=None, sl=False, tp=False, conf=False, tf=False):
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
            if eb < bi: sp+=1; continue
            c = float(df.iloc[eb]["close"])
            if c <= 0: sp+=1; continue
            if conf and s["conf"] < MIN_CONF: sp+=1; continue
            if tf and daily_xds:
                ds = s["date"].strftime("%Y-%m-%d")
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

CONFIGS = [
    ("30min原文",        False,False,False,False),
    ("+止损止盈",         True, True, False,False),
    ("+多级别",           False,False,False,True),
    ("+止损止盈+多级别",   True, True, False,True),
    ("+止损+多级别+置信度", True, True, True, True),
]

print("="*145)
print(f"原文买卖点30min回测 V2（zs_from_xd=True）  置信度阈值={MIN_CONF}  止损{SL_PCT*100}% 止盈{TP_PCT*100}%")
print("="*145)
hdr = f"{'股票':10s}"
for n,_,_,_,_ in CONFIGS: hdr += f" | {n:>18s}"
hdr += f" | {'买入持有':>8s}"
print(hdr)
print("-"*len(hdr))

S = {n:{"ann":0,"exc":0,"sig":0,"trd":0,"wr":0,"n":0} for n,_,_,_,_ in CONFIGS}
BHN, BHA = 0, 0

for mkt, code, name in STOCKS:
    df30 = load(mkt, code, "30min")
    dfd = load(mkt, code, "daily")
    if df30 is None or len(df30) < 100:
        print(f"{name:10s} | 跳过")
        continue

    sigs30, _, bis30, zs30 = analyze(df30, code)
    daily_xds = None
    if dfd is not None and len(dfd) >= 100:
        _, daily_xds, _, _ = analyze(dfd, code)

    row = f"{name:10s}"
    for cn, sl, tp, conf, tf in CONFIGS:
        r = sim(df30, sigs30, daily_xds, sl, tp, conf, tf)
        row += f" | {r['ann']:6.1f}%/{r['sig']:2d}sig/{r['trd']}tr"
        S[cn]["ann"] += r["ann"]; S[cn]["exc"] += r["exc"]
        S[cn]["sig"] += r["sig"]; S[cn]["trd"] += r["trd"]
        S[cn]["wr"] += r["wr"]; S[cn]["n"] += 1
    yr = (df30.iloc[-1]["datetime"]-df30.iloc[0]["datetime"]).days/365.25
    bh = ((float(df30.iloc[-1]["close"])/float(df30.iloc[0]["close"]))**(1/yr)-1)*100 if yr>0 else 0
    row += f" | {bh:6.1f}%"
    BHN += 1; BHA += bh
    print(f"{row}  (笔={bis30} 中枢={zs30})")

print("-"*len(hdr))
row = f"{'平均':10s}"
for cn,_,_,_,_ in CONFIGS:
    n = S[cn]["n"]
    if n == 0: row += f" | {'—':>18s}"; continue
    a = S[cn]["ann"]/n; s = S[cn]["sig"]/n; t = S[cn]["trd"]/n
    row += f" | {a:5.1f}%/{s:4.1f}sig/{t:3.1f}tr"
row += f" | {BHA/BHN:6.1f}%" if BHN > 0 else f" | {'—':>8s}"
print(row)

print(f"\n详细汇总（{BHN}只股票，30min数据，约2年）:")
print(f"{'方案':25s} | {'年化':>8s} | {'超额':>8s} | {'信号/股':>8s} | {'交易/股':>8s} | {'胜率':>6s}")
print("-"*80)
for cn,_,_,_,_ in CONFIGS:
    n = S[cn]["n"]
    if n == 0: continue
    print(f"{cn:25s} | {S[cn]['ann']/n:7.2f}% | {S[cn]['exc']/n:+7.2f}% | "
          f"{S[cn]['sig']/n:7.1f} | {S[cn]['trd']/n:7.1f} | {S[cn]['wr']/n:5.1f}%")
print(f"{'买入持有':25s} | {BHA/BHN:7.2f}% | {'—':>8s} | {'—':>8s} | {'—':>8s} | {'—':>6s}")

# 与日线原文对比
print(f"\n对比（日线原文 vs 30min原文+全部优化）:")
print(f"  日线原文(6年):   年化 -0.43%, 超额 +0.85%, 信号/股 ~8.9, 胜率 ~30%")
print(f"  30min原文+全部:  年化 {S['+止损+多级别+置信度']['ann']/S['+止损+多级别+置信度']['n']:.2f}%, "
      f"超额 {S['+止损+多级别+置信度']['exc']/S['+止损+多级别+置信度']['n']:+.2f}%, "
      f"信号/股 {S['+止损+多级别+置信度']['sig']/S['+止损+多级别+置信度']['n']:.1f}, "
      f"胜率 {S['+止损+多级别+置信度']['wr']/S['+止损+多级别+置信度']['n']:.1f}%")
print("="*145)
