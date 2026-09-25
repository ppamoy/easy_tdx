"""检验 V68 区间套的 confidence_adjust 分档是否与真实表现一致（不入库）。

分档（mmd_conditions._calc_range_set_multi_level_v68）：
    score >= 0.7 → +5%   0.5-0.7 → +3%   0.3-0.5 → 0    < 0.3 → -3%

本脚本在 20 只龙头 × 800 根日线的全部 3 类信号上，按评分区间统计实际的
10 根前瞻命中率与收益，验证「高分档确实更好」。若出现高分档不优于低分档，
说明分档需要调整。

实测基线（V730，n=206）：
    <0.3   n=12  hit=33.3%  ret=-1.40%   → -3% 合理
    0.3-0.5 n=16 hit=56.2%  ret=+1.42%   → 0
    0.5-0.7 n=42 hit=66.7%  ret=+1.37%   → +3%
    >=0.7  n=136 hit=64.0%  ret=+2.80%   → +5%（收益最高，故合理）

注意：曾观察到 3买 单独在阈值 0.7 处区分度消失（n=50 vs 20），系单方向
小样本噪声，大样本下不成立 —— 不可用小样本结论改动分档。

"""

import json, urllib.request
POOL=[("SH","600519"),("SH","601318"),("SH","600036"),("SH","601166"),("SH","600900"),
      ("SH","601899"),("SH","600030"),("SH","601012"),("SH","600276"),("SH","601888"),
      ("SZ","000858"),("SZ","000333"),("SZ","000651"),("SZ","000001"),("SZ","000002"),
      ("SZ","002594"),("SH","600887"),("SH","601668"),("SZ","000725"),("SH","600309")]
rows=[]
for mk,code in POOL:
    d=json.loads(urllib.request.urlopen(urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/chanlun/analyze",
        data=json.dumps({"market":mk,"code":code,"category":"DAY","start":0,"count":800}).encode(),
        headers={"Content-Type":"application/json"}),timeout=120).read())
    b=json.loads(urllib.request.urlopen(f"http://127.0.0.1:8000/api/v1/bars?market={mk}&code={code}&category=DAY&start=0&count=800",timeout=120).read())
    closes=[float(x["close"]) for x in b["data"]]
    for m in d["mmds"]:
        if not m["type"].endswith(("3buy","3sell")): continue
        v=m.get("v68_range_set_multi_level")
        if not v: continue
        sc=v.get("multi_level_score"); bi=m.get("bar_index")
        if sc is None or bi is None or bi+10>=len(closes): continue
        buy="buy" in m["type"]
        fwd=(closes[bi+10]-closes[bi])/closes[bi]*100
        hit=(fwd>0) if buy else (fwd<0)
        rows.append({"sc":sc,"adj":v.get("confidence_adjust"),"hit":hit,"ret":abs(fwd)*(1 if hit else -1),"buy":buy})
print(f"3类信号样本={len(rows)}")
def band(lo,hi): 
    g=[r for r in rows if lo<=r["sc"]<hi]
    return g
print("\n评分区间 → 实际 10根命中率/收益（分档是否与表现单调一致？）：")
for lo,hi,lab in ((0.0,0.3,"<0.3 (adj -3%)"),(0.3,0.5,"0.3-0.5 (adj 0)"),(0.5,0.7,"0.5-0.7 (adj +3%)"),(0.7,1.01,">=0.7 (adj +5%)")):
    g=band(lo,hi)
    if not g: print(f"  {lab}: n=0"); continue
    h=sum(1 for r in g if r["hit"])/len(g); rt=sum(r["ret"] for r in g)/len(g)
    print(f"  {lab}: n={len(g):>3}  hit={h:.1%}  avg_ret={rt:+.2f}%")
