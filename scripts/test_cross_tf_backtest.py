#!/usr/bin/env python3
"""跨级别(次级别线段构中枢)回测 — 真正的原文第17课方法。

用 process_klines_cross_timeframe：30min线段构中枢 + 日线笔检测买卖点。
带前视守卫：每个信号在前缀上复现验证。
"""
import json, sys, time
from pathlib import Path
import pandas as pd

sys.path.insert(0, "/home/skp/workspace/easy_tdx/src")
from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig

CACHE_D = Path("/home/skp/workspace/easy_tdx/audit_data")
CACHE_M = Path("/home/skp/workspace/easy_tdx/audit_data_min")
COMMISSION, STAMP, SLIP = 0.0003, 0.001, 0.002
LAG = 3

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
    df = pd.DataFrame(rows)
    for col in ("datetime","date"):
        if col in df.columns: df["datetime"]=pd.to_datetime(df[col]); break
    return df.sort_values("datetime").reset_index(drop=True)

def get_signals(dfd, df30, code, guard=False):
    """获取跨级别信号。guard=True时对每个信号做前缀复现验证。"""
    start_30 = df30.iloc[0]["datetime"]
    dfd_c = dfd[dfd["datetime"] >= start_30 - pd.Timedelta(days=7)].reset_index(drop=True)
    
    cfg = ChanlunConfig(zs_from_xd=True)
    analyser = ChanlunAnalyser(code=code, frequency="daily", config=cfg)
    r = analyser.process_klines_cross_timeframe(dfd_c, df30)
    
    sigs = []
    for mmd in r.mmds:
        if mmd.bi is None: continue
        bar_idx = mmd.bi.end.k.k_index
        if bar_idx < 0 or bar_idx >= len(dfd_c): continue
        t = mmd.mmd_type.value
        if "buy" in t: sigs.append({"b":bar_idx,"buy":True,"sell":False,"type":t,"conf":mmd.confidence})
        elif "sell" in t: sigs.append({"b":bar_idx,"buy":False,"sell":True,"type":t,"conf":mmd.confidence})
    sigs.sort(key=lambda s: s["b"])
    
    if not guard:
        # 偏移回原dfd的索引
        offset = dfd.index[dfd["datetime"] >= start_30 - pd.Timedelta(days=7)][0]
        for s in sigs: s["b"] += offset
        return sigs, dfd_c, r
    
    # 前视守卫：对每个信号在前缀上复现
    kept = []
    for s in sigs:
        k = s["b"] + LAG + 1
        if k <= 0 or k >= len(dfd_c): continue
        # 前缀
        sub_daily = dfd_c.iloc[:k].reset_index(drop=True)
        # 找对应的30min截止时间
        daily_end_dt = sub_daily.iloc[-1]["datetime"]
        sub_30 = df30[df30["datetime"] <= daily_end_dt + pd.Timedelta(hours=24)].reset_index(drop=True)
        if len(sub_30) < 50: continue
        
        try:
            sub_r = analyser.process_klines_cross_timeframe(sub_daily, sub_30)
            # 检查是否同一个信号(bar_idx, type)在前缀上也出现
            found = False
            for mmd in sub_r.mmds:
                if mmd.bi is None: continue
                sub_idx = mmd.bi.end.k.k_index
                if sub_idx == s["b"] and mmd.mmd_type.value == s["type"]:
                    found = True
                    break
            if found:
                s2 = dict(s)
                offset = dfd.index[dfd["datetime"] >= start_30 - pd.Timedelta(days=7)][0]
                s2["b"] = s["b"] + offset
                s2["exec_b"] = s["b"] + LAG + offset
                kept.append(s2)
        except Exception:
            continue
    
    return kept, dfd_c, r

def sim(df, sigs):
    """简单买卖模拟：买入点全仓买，卖出点全仓卖。"""
    cash, pos, ep = 1e6, 0, 0.0
    sells, wins = 0, 0
    sp = 0
    for bi in range(len(df)):
        while sp < len(sigs):
            s = sigs[sp]
            eb = s.get("exec_b", s["b"]) if "exec_b" in s else s["b"] + LAG
            if eb > bi: break
            if eb < bi or eb >= len(df): sp+=1; continue
            c = float(df.iloc[eb]["close"])
            if c <= 0: sp+=1; continue
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
            "sig":len(sigs),"trd":sells,"wr":round(wr,1),"end":round(cash,0)}

# === 测试 ===
for guard_name, guard in [("无守卫", False), ("有守卫", True)]:
    print(f"\n{'='*100}")
    print(f"跨级别(次级别线段构中枢) — {guard_name} — 原文第17课精确口径")
    print(f"{'='*100}")
    print(f"{'股票':10s} | {'年化':>8s} | {'超额':>8s} | {'信号':>6s} | {'交易':>6s} | {'胜率':>6s} | {'买入持有':>8s} | {'耗时':>6s}")
    print("-"*80)
    
    tot = {"ann":0,"exc":0,"sig":0,"trd":0,"wr":0,"bh":0,"n":0}
    for mkt, code, name in STOCKS:
        dfd = load(mkt, code, "daily")
        df30 = load(mkt, code, "30min")
        if dfd is None or df30 is None:
            print(f"{name:10s} | 跳过")
            continue
        t0 = time.time()
        sigs, dfd_c, r = get_signals(dfd, df30, code, guard=guard)
        res = sim(dfd, sigs)
        elapsed = time.time() - t0
        print(f"{name:10s} | {res['ann']:7.2f}% | {res['exc']:+7.2f}% | {res['sig']:5d} | {res['trd']:5d} | {res['wr']:5.1f}% | {res['bh']:7.2f}% | {elapsed:5.1f}s")
        for k in ("ann","exc","sig","trd","wr","bh"): tot[k]+=res[k]
        tot["n"]+=1
    print("-"*80)
    n = tot["n"]
    print(f"{'平均':10s} | {tot['ann']/n:7.2f}% | {tot['exc']/n:+7.2f}% | {tot['sig']/n:5.1f} | {tot['trd']/n:5.1f} | {tot['wr']/n:5.1f}% | {tot['bh']/n:7.2f}% |")
