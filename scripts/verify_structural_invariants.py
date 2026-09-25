"""跨周期结构不变量扫描 —— 一次性巡检脚本（不入库）。

缠论结构的硬约束，任何一项被违反即模型/画图可能出错：
1) 中枢区间合法：zd <= zg，且 gg/dd 覆盖 zg/zd
2) 笔方向严格交替，且相邻笔首尾同值相连（同一转折点）
3) K线索引单调不回退
4) 线段端点必须是笔端点（级别递归的共享转折点要求）
5) 买卖点 bar_index 落在数据范围内

用法：.venv/bin/python scripts/verify_structural_invariants.py
"""
import json, urllib.request
API="http://127.0.0.1:8000/api/v1/chanlun/analyze"
CASES=[("SZ","000001","DAY"),("SZ","000001","MIN_30"),("SZ","000001","WEEK"),
       ("SH","600519","DAY"),("SH","600519","MIN_30"),("SH","600519","WEEK"),
       ("SZ","000333","MIN_30"),("SZ","000333","WEEK"),("SH","601318","MIN_30")]
def post(u,p):
    r=urllib.request.Request(u,data=json.dumps(p).encode(),headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(r,timeout=120).read())
bad=0
for mk,code,cat in CASES:
    d=post(API,{"market":mk,"code":code,"category":cat,"start":0,"count":800})
    errs=[]
    # 1) 中枢 zd <= zg
    for z in d.get("zss",[]):
        if z["zd"] > z["zg"]: errs.append(f"中枢[{z['index']}] zd({z['zd']})>zg({z['zg']})")
        if z["gg"] < z["zg"] or z["dd"] > z["zd"]: errs.append(f"中枢[{z['index']}] gg/dd 越界")
    # 2) 笔方向交替 & 首尾相连
    bis=d.get("bis",[])
    for i in range(1,len(bis)):
        if bis[i]["direction"]==bis[i-1]["direction"]: errs.append(f"笔[{i}] 与前一笔同向")
        if bis[i]["start_val"] != bis[i-1]["end_val"]: errs.append(f"笔[{i}] 起点({bis[i]['start_val']})≠前笔终点({bis[i-1]['end_val']})")
    # 3) 索引单调
    for i in range(1,len(bis)):
        if bis[i]["start_index"] < bis[i-1]["end_index"]: errs.append(f"笔[{i}] 索引回退")
    # 4) 线段端点共享笔端点
    bi_pts={(round(b["start_val"],4),b["start_index"]) for b in bis}|{(round(b["end_val"],4),b["end_index"]) for b in bis}
    for x in d.get("xds",[]):
        for p in ((round(x["start_val"],4),x["start_index"]),(round(x["end_val"],4),x["end_index"])):
            if p not in bi_pts: errs.append(f"线段端点{p}不在笔端点集合")
    # 5) mmd bar_index 在范围内
    n=d.get("kline_count",0)
    for m in d.get("mmds",[]):
        if m.get("bar_index") is not None and not (0<=m["bar_index"]<n): errs.append(f"mmd {m['type']} bar_index={m['bar_index']} 越界(n={n})")
    print(f"  {mk}{code} {cat:7s}: bi={len(bis)} xd={len(d.get('xds',[]))} zs={len(d.get('zss',[]))} mmd={len(d.get('mmds',[]))} → {'⚠️ '+str(len(errs))+' 项: '+errs[0] if errs else '✅ 无异常'}")
    if errs:
        bad+=1
        for e in errs[:4]: print(f"        - {e}")
print(f"\n不变量扫描：异常标的={bad}/{len(CASES)}")
