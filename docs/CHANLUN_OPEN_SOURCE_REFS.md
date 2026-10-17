# 缠论开源项目参考清单

> 用途：审计/改进 easy_tdx 缠论模型时，参考其他开源实现的思路。
> **原则：以缠论 108 课原文为准**——这些项目不一定百分百符合原文，
> 仅作对照与启发，任何采纳须回到原文验证。

## 四个参考项目

| 项目 | 地址 | 语言 | 备注 |
|---|---|---|---|
| czsc | https://github.com/waditu/czsc | Python | 较工程化，分析框架完整，star 多（研究子代理进行中） |
| chan.py | https://github.com/Vespa314/chan.py | Python | 缠论纯实现，结构清晰，常被对照 |
| chanlun-pro | https://github.com/yijixiuxin/chanlun-pro | Python | 功能全，含量化策略集成；核心 cl_fast PyArmor 加密 |
| chanlun (tomcat) | https://github.com/tomcat123a/-chanlun | Python | 另一缠论实现，可供交叉对照（研究子代理进行中） |

## 研究结论（偏差A 修复对照，以原文 20课L22/30课L142 为准）

| 项目 | 中枢方向 | GG/DD | Z走势段(Zn) | 零件级别 | 与原文偏差 |
|---|---|---|---|---|---|
| **czsc** | ⚠️ 无 direction 字段，仅 `sdir`/`edir`=首/倒一笔方向透传；信号层靠"末笔方向"反推 | ❌ `bis.iter()`遍历**全部笔**无方向过滤，反向B段全额参与(`zs.rs:61-68`)；唯一方向过滤在`zdy.rs:533/540`但算DIF非GG/DD | ❌ 无Zn概念；按"反向突破中枢沿"断中枢，同向/反向笔全并入(`utils.rs:31-51`) | ❌ 笔构中枢(`ZS.bis:Vec<BI>`)；`FakeBI`存在但零引用 | GG/DD不符；方向部分符(奇数笔等价) |
| **chan.py** | ❌ 无 direction 字段（靠 seg.dir/bi_out 外部推） | ❌ 无 GG/DD 概念；peak_high/peak_low **遍历全笔含反向笔**（实测被反向笔抬高2.0） | ❌ 无 Zn 层；唯一方向过滤是"段方向取补笔"（语义相反） | ❌ 笔构中枢（+one_bi_zs 一笔中枢开关） | 4项全不符 |
| **chanlun-pro** | ✅ `ZS.type∈{up,down,zd}`（zd=震荡第三态）；进入/离开段方向一致性定 | ❌ 遍历**全部段含反向B段**；`zf()` 把 gg-dd 当"整个中枢区间"是铁证 | ❌ 全仓库 `Zn` 零命中；zsd/qsd 是线段层递归聚合非 Zn | ⚠️ 笔中枢是默认主干（每9笔升一级）；线段/走势段中枢近似 | GG/DD 不符（同 easy_tdx 偏差）；方向符合 |
| **tomcat chanlun** | ✅ `enter_d`=进入段方向(L488)，强制体形下上下/上下上与之匹配(L683-711) | ⚠️ **B段极值永不进入同界**(✅正确，靠共享顶点+朝向分支)；但**单侧缺口**：d=+1的`dd`/d=-1的`gg`只取第一段Zn(漏第2+Zn) | ⚠️ 无Zn对象，靠体形交替约束+段朝向分支隐式实现 | ❌ 线段(Seg)当中枢零件(笔→线段→中枢)，作者自认"粗略" | B段排除对✓；单侧遍历不全✗ |

**关键印证**：**4 个项目 GG/DD 处理分两类**：
- **3 个遍历全段含反向 B 段**(czsc / chan.py / chanlun-pro)——行业普遍偏差，非 easy_tdx 独有。
- **1 个(tomcat)正确排除 B 段**但**单侧只取第一段 Zn**(漏第2+Zn)——方向对但不完整。

⇒ **easy_tdx 本次偏差A 修复（显式同向段过滤 + 遍历所有 Zn）是 5 个实现中最原文完整的**：
  ① B段(反向段)不参与(✓ 与 tomcat 一致，优于 czsc/chan.py/chanlun-pro)
  ② 遍历中枢中所有同向段 Zn(✓ A/C/E… 全覆盖，优于 tomcat 的单侧只取第一段)

- czsc 子代理指出修复法：「在 `zs.rs:61-68` 处按 `self.sdir` 过滤 `bis`」——**正是 easy_tdx 本次所做**。
- czsc 全仓库唯一符合原文 ZG/ZD 口径的实现：`cxt.rs:950-952` `zs_zd=max(b1.low,b3.low)`/`zs_zg=min(b1.high,b3.high)`（取第1、3同向笔）——可作改造参照。
- chan.py 子代理提出「修正所需三项」(①direction字段 ②按中枢方向切Zn ③GG/DD只遍历Zn)，**正是本次所做**。
- tomcat 的「共享顶点+朝向分支」是另一种排除 B 段的机制，但单侧缺口证明：**显式按 direction 过滤遍历所有 Zn** 比「靠共享顶点间接带」更可靠（不会漏 Zn）。

原文方向（20课L22「n遍历中枢中所有Zn，Zn=与中枢方向一致的次级别走势类型」）得到 4 个独立项目的反向验证。
chanlun-pro 的 `ZS.type∈{up,down,zd}` 第三态(zd=震荡)比 easy_tdx 的 up/down 更细，但原文30课L142「中枢一样有方向」，
up/down 对 GG/DD 同向段过滤已足。

## 使用纪律

- 参考其**思路与结构**，不直接抄代码（license/风格不同）。
- 任何与原文冲突处以原文为准（参见 docs/缠论108课/）。
- 对照后把结论沉淀进 docs/CHANLUN_FULL_AUDIT_6SUBAGENT_2026.md 或专项审计文档。

## tdxrs（jiangtaovan/tdxrs）—— 不引入

**结论：不建议为提升 easy_tdx 性能而引入 tdxrs。**（子代理 a3af488e 只读实测，未改任何文件）

- **定位错层**：tdxrs 是 Rust 实现的 TDX 行情**数据解析层**（兼容 tdxpy API，PyO3/maturin）。
  easy_tdx 的性能瓶颈 100% 在**缠论计算**（CPU 密集，GIL 内多线程无效），不在取数。实测
  `fetch_qfq_klines`+30min/5min 联立：取数 ~0.04s（0.3%），`process_klines` 缠论计算 ~23~25s（99.7%）。
  tdxrs 优化的「本地 TDX 协议解析」与瓶颈不在同一层，端到端收益 ≈ 0.1%，用户无感。
- **不兼容 + 功能倒退**：tdxrs 不支持 MAC 扩展协议（`0x122E` K线/`0x1231` 板块/分时/逐笔/资金流等
  20+ 命令，全库 grep 无命中），而 MAC 是 easy_tdx 前复权 + 全部分时/逐笔/资金流/板块排名的**核心路径**。
  API 签名/输出（datetime 为字符串 vs Timestamp）/复权口径（客户端侧 vs 服务端）全不同，drop-in 替换
  等于功能倒退，且需 3~5 人日适配 + 全调用点回归。
- **easy_tdx 取数本就快**：MAC 路径冷取数 0.02~0.07s/次（含磁盘缓存 read-through），批量 10 只冷取数
  0.457s。标准协议路径慢在「逐台故障转移 ~6s×N 台」（服务器不提供该标的分钟线），非解析慢——
  该问题应加「首台返回空 body 即快速失败 + 短 TTL 黑名单」解决，与 tdxrs 无关。
- **真正值得做的性能优化**（同一份实测数据的自然延伸）：
  1. 多进程（`ProcessPoolExecutor`）绕 GIL——4 核批量场景理论 ~3.5×；
  2. `process_klines` 管道向量化（`analyser.py:35 _df_to_klines` 逐行 `itertuples` 构造对象是热点）；
  3. 按区间增量计算（`append_klines` 已有雏形 `analyser.py:1173`），只重算尾部。
- 如确有强需求（离线本地 .day/.lc5 文件解析），只作为**旁路可选组件**，不做 drop-in 替换。
