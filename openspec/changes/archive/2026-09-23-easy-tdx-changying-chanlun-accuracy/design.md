# 设计：长盈全市场标记 + 准确性审计 + 图表全历史回溯

## 架构（现状 → 目标）

```
                     ┌──────────────────────────────────────────────┐
                     │                凌晨调度（cmd_web 守护线程）    │
                     │  0:05 changying-mark（半年窗口锁）            │
                     │  0:40 audit-accuracy（周窗口锁，可选）         │
                     └──────────────┬───────────────────────────────┘
                                    │
  TDX/MAC 行情 ──► pipeline.scan_market ──► fundamental/marks.py ──► ~/.easy_tdx/changying_marks.db
  gpcw 财报 zip ──► point-in-time 裁剪 ──┘        （全量 ≥100 亿，无 top_n 截断）
                                    │
  Web /stock-pick ──► 读 marks 全量表 ──► 缠论择时 ──► 图表
  Web /audit/accuracy ──► audit/accuracy.json + accuracy.md
  Web /bars?lookback=N ──► klines.fetch_paged_bars（循环翻页）──► 前端图表「加载更早」
```

## 关键决策（D1–D6）

### D1 全量标记独立于 top-N 池，不推翻现有 `changying_pool`
现状 `changying_pool.db`（top 20）被 `/stock-pick` 白天路径与看板消费。
保留它作为「精选层」，新增 `changying_marks.db` 存全量标记（≥100 亿），
`/stock-pick` 本地路径改为读 marks 表。理由：一次迁移同时改存储与消费方
风险大；marks 表落地后 pool 退化为「marks 按 score 排序取 20」的视图，
后续可无缝切换。

### D2 调度频次：财报对齐半年频 + 兜底周自检
树/粮/菜输入是季报/半年报/年报的 point-in-time 快照，财报披露季
（4 月/8 月/10 月）结束后标记才会变化。凌晨任务带「窗口锁」：
- 1/7 月首个周六 00:05 全量重算（半年频主跑）；
- 其余周六仅当 gpcw 缓存出现新报告期 zip 时重算（季报兜底）；
- 手动 `easy-tdx changying-mark --force` 随时可跑。
满足用户「半年还是季度更新一次就可以」的要求，且避免每天几千只全量
打分的无意义开销。

### D3 市值门槛硬过滤在候选窗口，标记不分页截断
`scan_market(min_mcap_yi=100)` 已支持市值过滤但候选窗口受 `top_n*5`
限制；marks 管道调用时传 `top_n=全部合格数`（不截断）。市值取价仍走
8 线程并行（V714 已实现），全市场 ~5000 只候选压到 ~1200 只后逐只打分，
预计 10–20 分钟，凌晨窗口可承受。

### D4 审计管道只算真账，禁止任何合成指标
审计输出三类数字，全部可追溯到逐笔明细：
1. **长盈分层前瞻收益**：对 marks 表每类（树/粮/菜）抽样 ≥30 只，
   从标记日起算 +20/+60/+250 日收益（复权价），输出分位数与胜率；
2. **缠论买卖点信号质量**：复用 `backtest/chanlun_validator.py` 的
   信号→N 根超额收益口径，按买卖点类型汇总命中率；
3. **图表对账**：对同一 (market, code, category) 比对 `/bars` 返回的
   最后一根 bar 与缠论分析输入 df 的最后一根，时间戳不一致即报错。
报告 JSON 落 `~/.easy_tdx/audit/accuracy.json`，同时渲染 Markdown；
禁止 hash/随机数伪造（沿用 2026-07-05 chanlun-v3 审计教训）。

### D5 图表全历史：服务端循环翻页 + 前端增量拼接
TDX 协议单次 `start` 为 uint16、`count` ≤800；MAC `get_stock_kline`
单次上限相同。新增 `web/klines.py :: fetch_paged_bars()`：按 800 根一页
向前循环拉取直至凑满 `lookback`（默认 3000，上限 20000），去重拼接。
前端图表组件新增 `loadMore(direction)`：向左（更早）请求
`start=当前最早偏移-800`，向右请求最新页；拼接后保持 dataZoom 视口
不变。缠论/买卖点标注只对已加载窗口内数据重算，不跨窗口拼接结构。

### D6 信号口径统一：一处计算，两处消费
`SignalAccuracyPanel`（模型视角）与回测 TradeTable（账本视角）共用
新增 `web/signal_ledger.py :: signal_returns()`：输入信号列表 + 复权
bars，输出每信号的 N 根收益明细。面板与审计报告都从它取数，口径漂移
在单测层被拦截（同一输入两处输出必须逐字节一致）。

## 风险与对策

| 风险 | 对策 |
| --- | --- |
| 全市场打分凌晨跑不完 | D3 并行取价已有；marks 管道支持 `--markets` 分市场跑，失败下次窗口锁重试 |
| MAC 主机抖动导致 marks 半成品 | 落库前校验标的数 ≥ 上期 80%，否则拒写并告警（防半量数据覆盖全量） |
| 前端拼接重复 bar | fetch_paged_bars 按 (datetime) 去重 + 单测覆盖跨页重叠 |
| 审计跑在旧 marks 上 | audit 管道显式校验 marks.updated_at 距今 ≤35 天，过期在报告头标红 |
