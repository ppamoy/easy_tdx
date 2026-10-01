"""区间套确认阈值的敏感性扫描（扩样本：20 票 × 3 周期）——不入库。

⚠️ V-22 已弃用：本脚本基于 B 伪区间套评分（v68_multi_level_score）做阈值扫描，
真区间套迁移后 nested 是布尔、无需阈值；保留仅供历史基线（V730 表格）对照。
现用脚本见 nesting_backtest.py（/chanlun/multi-level 跨周期口径）。

目的：检验「有区间套确认」的判定阈值取多少最合适，以及结论对阈值是否稳健。
样本为 20 只龙头 × DAY/MIN_30/MIN_60 共 60 个序列（约 495 个 3 类信号）。

实测基线（V730，n=495：3buy=211 / 3sell=284，10 根前瞻命中率）：

    阈值   3buy 有/无              3sell 有/无
    0.3    67%/20% n=196/15        73%/43% n=277/7
    0.4    67%/20% n=196/15        74%/44% n=266/18
    0.5    66%/29% n=194/17        74%/57% n=247/37   当前默认值
    0.6    65%/58% n=175/36        74%/64% n=218/66
    0.7    64%/63% n=144/67        75%/67% n=181/103
    0.8    65%/63% n=72/139        78%/69% n=90/194

结论：3buy 的区分度在 0.3-0.5 最强（+37%~+47%），0.7 以上消失；
3sell 在全区间保持正向。当前阈值 0.5 兼顾两方向，判定为无需调整。
（此前用 20 只日线小样本时看到 0.7 处区分度消失、担心高分档失真；
扩样本后确认为 3buy 单方向的真实特性，而非分档错误。）
"""

import json, urllib.request
POOL=[("SH","600519"),("SH","601318"),("SH","600036"),("SH","601166"),("SH","600900"),
      ("SH","601899"),("SH","600030"),("SH","601012"),("SH","600276"),("SH","601888"),
      ("SZ","000858"),("SZ","000333"),("SZ","000651"),("SZ","000001"),("SZ","000002"),
      ("SZ","002594"),("SH","600887"),("SH","601668"),("SZ","000725"),("SH","600309")]
CATS=("DAY","MIN_30","MIN_60")
rows=[]
for cat in CATS:
  for mk,code in POOL:
    try:
      d=json.loads(urllib.request.urlopen(urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/chanlun/analyze",
        data=json.dumps({"market":mk,"code":code,"category":cat,"start":0,"count":800}).encode(),
        headers={"Content-Type":"application/json"}),timeout=120).read())
      b=json.loads(urllib.request.urlopen(f"http://127.0.0.1:8000/api/v1/bars?market={mk}&code={code}&category={cat}&start=0&count=800",timeout=120).read())
    except Exception: continue
    closes=[float(x["close"]) for x in b["data"]]
    for m in d["mmds"]:
      if not m["type"].endswith(("3buy","3sell")): continue
      v=m.get("v68_range_set_multi_level")
      if not v: continue
      sc=v.get("multi_level_score"); bi=m.get("bar_index")
      if sc is None or bi is None or bi+10>=len(closes): continue
      buy="buy" in m["type"]; fwd=(closes[bi+10]-closes[bi])/closes[bi]*100
      rows.append({"sc":sc,"buy":buy,"hit":(fwd>0) if buy else (fwd<0),"ret":fwd*(1 if buy else -1)})
print(f"3类信号总样本={len(rows)} (3buy={sum(1 for r in rows if r['buy'])}, 3sell={sum(1 for r in rows if not r['buy'])})")
print("\n阈值扫描（10根命中率，按方向分层）：")
print(f"{'阈值':>5} {'3buy有/无':>18} {'3sell有/无':>18}")
for th in (0.3,0.4,0.5,0.6,0.7,0.8):
    out=[]
    for buy in (True,False):
        sub=[r for r in rows if r["buy"]==buy]
        A=[r for r in sub if r["sc"]>=th]; B=[r for r in sub if r["sc"]<th]
        if len(A)<5 or len(B)<5: out.append("样本不足"); continue
        ha=sum(1 for r in A if r["hit"])/len(A); hb=sum(1 for r in B if r["hit"])/len(B)
        out.append(f"{ha:.0%}/{hb:.0%} n={len(A)}/{len(B)}")
    print(f"{th:>5} {out[0]:>18} {out[1]:>18}")
