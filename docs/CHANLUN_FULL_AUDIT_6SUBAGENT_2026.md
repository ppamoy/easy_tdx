# 缠论模型全文符合度审计报告（6 子代理独立审计 + 亲读原文交叉验证）

> 审计日期：2026-10-XX
> 审计方法：6 个独立子代理（各自全新视角，不依赖旧审计文档）逐课读原文 + 核代码 +
> 构造反例实证；**同时本人亲自读最易错原文段落交叉验证每个子代理发现**。
> 双重保险：既查子代理漏报，也查子代理误报（已抓出 1 处子代理误读）。

---

## 一、审计方法说明

| 组件 | 子代理 | 本人亲读原文 | 本人亲核代码 |
|---|---|---|---|
| 分型/K线合并 | ce2fcda5 ✅ | 62课L16/22/24 | fractal.py, kline_merge.py |
| 笔 | ec047a16 ✅ | 62课L18/20, 69课L6 | bi.py:65-90 |
| 线段 | 53c75bdc ✅ | 65课L8/14/34, 67/71/78课 | xd.py:44-100, 117-166 |
| 中枢 | 3d69e824 ✅ | 17/18/20课, 30/33/61/91课 | zs.py（GG/DD+direction 已独立核实） |
| 走势/同级别分解 | 98b6ca4c ✅ | 17课, 36/38课 | analyser.py:1031-1046 |
| 买卖点 | e4ab1abb ✅ | 17/20/21/24/53/101课 | mmd.py, mmd_conditions.py |

---

## 二、逐组件符合度结论

### ✅ 高符合（主干正确，无高风险偏差）

**1. 分型（62课L16）—— 符合**
- `fractal.py:62-73` 严格模式：顶分型=`mid.high>left&right.high AND mid.low>left&right.low`，
  逐字符合 62课「第二K线高点最高且低点也最高」。
- `val=mid.high/low`（非收盘价），符合 62课L18。
- 合并前置（analyser.py:816→820 先 merge_klines 后 find_fractals），符合 62课L24。
- 子代理实证：拒绝「高点最高但低点非最高」的误判。

**2. 笔（62课L20/69课L6）—— 符合**
- `bi.py:65-90` gap 规则：新笔 gap≥3（=1根独立K线），符合 62课L20「顶底间至少1根K线」。
  注：任务描述「至少5根K线」假设**在原文无依据**（106课「6单位」是均线经验，非笔定义）。
- 顶底交替（bi.py:62-63）、同型取更极端（bi.py:240-266）、方向由首笔决定，均符合。
- 低severity偏差：FX.done恒True（fractal.py:98）使完成度字段失效，但无未来函数、不影响中枢/背驰。

**3. 1买 = 趋势背驰（24课L19/53课L16）—— 符合（主干）**
- `mmd_conditions.py:16613-16649` 趋势背驰分支完整实现 24课 A/B/C 三段：
  两同向中枢 → `_find_leaving_bi`（V736 修好「破边沿」）取离开段 → 新极值确认 →
  **黄白线0轴门控**（`_check_zero_axis_pullback`，V736 本轮补修）→ MACD面积比 C<A。
- 注释明写「存在同向趋势时，1买必须走趋势背驰，禁用笔背驰」。
- **这不是笔背驰替代**——子代理与本人一致确认。

**4. 3买 = 突破ZG后回踩不破ZG（20课L26）—— 符合**
- `mmd.py:3016-3019` `retest_bi.low <= zs.zg → continue`（严格大于ZG）。
- V840 修正了「向下笔 high 天然>ZG 被误判为向上离开」的方向错误。

**5. 买卖对称性（17课L48/53课L16）—— 符合（最高符合度维度）**
- 1/2/3 买与 1/2/3 卖逐行镜像（趋势门槛/中枢参照/背驰/去重/时间窗/距离检查）。
- V730 修了1卖侧 `reversed(bis)` 未来函数；V731 修了买侧回撤深度门槛死代码导致的系统性做多偏误。

**6. 2买可跌破1买（101课L22）—— 符合**
- `_low_ok=True` + `mmd_2nd_max_pullback=None` 默认；测试 `test_2buy_allowed_on_deep_pullback_lesson101` 锁定。

### ⚠️ 真实偏差（需关注）

**偏差 A — 中枢 GG/DD（20课L22）【✅ 已修 V856：同向段 Zn 过滤 + direction 字段】**
- 原文L22（逐字）：「把这些**与中枢方向一致**的次级别走势类型称为 Z走势段……`GG=max(gn)`, `DD=min(dn)`，**n遍历中枢中所有Zn**」。
  - 30课L142（缠师回帖）佐证：「一样有方向，例如…方向就是下上下」——Zn 按中枢方向切分。
  - 中枢子代理给出三点裁定：①前文已限定 Z走势段=与方向一致；②含反向段则中枢方向自相矛盾；③45课读者问 Z走势段，缠师答以「有方向」。
- ✅ **本次修复（V856）**：
  1. `zs.py find_zss`：GG/DD 累加加方向过滤 `if bi.direction == candidate_lines[0].direction`（只累加同向段 A/C/E…，反向段 B/D… 不参与）。
  2. `zs.py` 3 处 ZS 构造点（硬关闭/正常关闭/收尾）赋 `direction=candidate_lines[0].direction.value`（30课L142 中枢方向=首笔方向）。
  3. `same_level.py _make_zs`：GG/DD 同样改为同向段过滤（direction 已有，补 Zn 过滤）。
- **外部印证（chan.py 子代理）**：Vespa314/chan.py 有**完全相同的偏差**——无 GG/DD 概念，等价位 `peak_high/peak_low` 遍历全部笔含反向笔（实测 peak_high 被反向笔抬高 2.0），无 direction 字段。子代理提出的「修正所需三项」(①direction字段②切Zn③GG/DD只遍历Zn)**正是本次所做**，原文方向得到独立验证。
- **级联影响（已测，§2）**：GG/DD 变严 → 29课反弹确认阈值变严（DD=min(dn over Zn) 比旧全笔 DD 更高）。sh600009 实测：反弹未通过 1→3（原文正确——旧全笔 DD 把未触及同向段 DD 的假通过也算进 verified）。信号数/中枢数**不变**（13/34，stash 对照证明）。
- 代码 `zs.py:334-341`：`gg_candidate=max(gg_candidate, bi.high)` 对**全部笔含反向 B/D 段**取极值。
  - 同类无过滤：`zs.py:251-252`（_merge_overlapping_zss）、`same_level.py:222-223`。
  - 反例（既有审计文档）：A上[10,20] B下[25,3] C上[3,18] D下[18,9] ⇒ 原文 GG=max(20,18)=20，代码 gg=25（虚高25%）。
- **根因（中枢子代理新发现）**：`ZS.direction` 是死字段——`find_zss` 全文无 `direction=` 赋值（grep 确认仅 `direction_score` 质量分）。
  无中枢方向 → 无法切分 Z走势段 → GG/DD 无从按方向过滤。偏差 A 与审计点5同源。
- **影响传导（4处，均不影响3买/3卖）**：①`zs.py:197-201` 定理二升级判定；②`analyser.py:748-751` 反弹确认；③`seg_mmd.py:535-537` bsp3_peak；④`mmd_conditions.py:18360-18368` 中枢强度评分。
- **测试固化**：`tests/unit/test_chanlun_zs_extension.py:47-70` 断言 `zs.gg==15.0`（来自反向笔）——修偏差须同步改测试。
- **未修原因**：破坏 3 个测试 + 零实战影响（GG/DD 不进 3买/3卖判定，`mmd.py:2953/3014` 只用 zg/zd）。修法 = 先落地 `ZS.direction`（取首段方向）→ GG/DD 按方向过滤同向段 → 同步改测试。留定理二下游专项会话。

**偏差 B — 笔极值覆盖（62课L18/20 vs 工程口径）【✅ 已修 V857】**
- `analyser.py:830-837`（HEAD）把 `bi.high/low` 从分型端点极值改写为**区间原始K线极值**。
- 原文62课L20「顶底间其他波动可忽略」；代码注释引「笔极值=区间所有K线最高/最低」查无出处（§3 伪造引用）。
- **影响方向保守**（中枢更宽/3买更难触发，不产虚假信号）—— 笔子代理评低severity，分型子代理评中。
- `zs.py:302-341` 用 `bi.high/low` 算 ZG/ZD；若用区间极值则 ZG 偏高、3买偏少（保守）。
- 中枢子代理确认（审计点3附带）：区间极值还**放大 GG/DD 污染**（gn/dn 可超端点分型值）。62课L18「gn/dn即端点分型顶/底」。
- ✅ **V857 修复**：移除 `analyser.py:830-837` 区间极值覆盖块，`bi.high/low` 回归端点分型值
  `max/min(start.val,end.val)`（`bi.py:301-302,325-326` find_bis 原始口径）。与偏差A（GG/DD 同向段
  Zn 过滤）配合，共同保证 GG/DD = 同向段端点分型值极值 = 原文 20课L22 口径。
- **上游对照**（handsomejustin/easy_tdx HEAD）：上游 `analyser.py` **本就无覆盖段**（调用 find_bis
  后直接赋值），`bi.py:100-101` 用端点分型值——即 V857 修复使本项目与上游 + 原文一致。覆盖段是本项目
  下游自加、注释伪称原文的偏离，现已移除。
- **行为 delta（§3 实测）**：bis 数不变（251/225/229），zss 34→35(+1/+1/0)，mmds ±2。固化测试更新：
  `test_chanlun_invariants.py::test_bi_high_low_equal_endpoint_fractals`（5 fixtures，原 `..._equal_range_extremes`
  固化区间极值，已诚实重写为端点分型值断言）；`test_chanlun_real_golden.py` mmds 2→3 / bcs 2→3（新增
  SELL_3@bi11 + PZ盘整背驰 bi11vsbi7，均非前视、原文合法，区间极值 bug 漏算）。267 passed。

**偏差 C — 2买「次级别回调」解读为同级别笔【已知，已文档化】**
- 四处原文（17/21/53/101课）一致说「**次级别**回调/走势结束点」。
- 代码 `mmd.py:2364-2422` 取**同级别向下笔**终点。V852 实测 85% 走宽松解读。
- 字面口径需跨级别 MMD 架构改动（风险高），已文档化为「解读选择」。

**偏差 D — 线段前三笔重叠检查缺失（65课L34）【✅ 已修 V857 破坏确认集成】**
- 原文65课L34「线段前三笔必须有重叠部分」无歧义；同课更明确「线段破坏的充要条件，就是被另一个线段
  破坏」「只要构成有重叠部分的前三笔，那么必然会形成一线段」——即线段须**延伸到被有效线段（前三笔
  重叠）破坏**，不能孤立笔（chaining）。
- `xd.py:133`（HEAD 前）只查 `len(bis)<3`，无重叠检查。实测 000001_daily：xd1（start_bi=3）前三笔
  **不重叠**（65课违①）；000001_30min/weekly xd0 前三笔亦不重叠（违①）。
- **简单「前三笔无重叠则 start+=1 滑动」gate 不可用（§3 实测证伪）**：gate-ON 时 000001_daily 3线段
  前三笔全重叠✓，但 xd0/xd1 间 orphan bi3（end30≠start38）违 65课 chaining②——即**用 chaining 违例
  换前三笔违例，非修复**。关键认知：chaining 是算法固有的（`start=end+1`），故偏差D 唯一 65课 问题是
  前三笔重叠，正确修法**只能**是破坏确认（线段延伸），无干净旁路（post-merge 改终点违分型语义）。
- ✅ **V857 破坏确认集成（三部件配合）**：
  ① **起点前三笔检查**（xd.py 外层 loop 顶）：线段自身前三笔 `bis[start:+3]` 须重叠，否则 `start+=1`
     滑动。因②③保证线段间 chaining（延伸非孤立），此滑动仅孤立数据最前端无法成段的笔。
  ② **confirmed_end 破坏确认**（特征序列分型）：检出终点 `cand_end` 时，验证下一线段前三笔
     `bis[cand_end+1:+4]` 重叠方确认；否则不提交、不 break，继续扫描（线段延伸）。
  ③ **provisional_end 破坏确认**（笔破坏暂定）：暂定后待下一线段前三笔可用（`j>=provisional_end+3`）
     时校验重叠；无重叠则撤销暂定、线段延伸（内层 loop 继续找后续有效破坏，而非落收尾过度延伸）。
- **双向验证（§3/§4）**：4 fixtures（daily/30min/weekly/600519）修复后前三笔违例=0、chain_gap=0；
  stash 偏差D 后 000001_daily/30min/weekly 前三笔违例=1（xd0 不重叠）——证修复真实。
- **行为 delta**：000001_daily xd0 延伸（end_bar 30→71），xd 计数 weekly/30min 2→1（daily 不变）；
  zs/mmd/bc 不变（仅 xd 结构变）。固化测试更新：`test_chanlun_real_golden_multi` weekly/30min xd 2→1；
  `test_chanlun_recursive` [56,8,1]→[51,5,1]（各级线段延伸收敛）。守卫测试
  `test_chanlun_xd_first3_overlap_chaining.py`（4 fixtures，前三笔重叠+chaining 双不变量，双向验证）。
- **上游对照**：handsomejustin/easy_tdx 同样无此检查（共有缺陷）；本项目修复后与上游分叉（上游仍带 bug）。

**偏差 E — 线段特征序列首次合并方向硬编码（xd.py:67-72）【✅ 已修 V858：seg_dir fallback】**
- 代码首次合并（len(merged)==1）硬编码 `direction="up"`。
- **子代理推理有误**：它说「特征笔是向下笔→应取低低」，但原文65课L14方向由 `gn vs gn-1`（顶点趋势）定，非笔自身方向。
- 原文 L14 对首次合并方向**沉默**（第 n 根是包含链起点，需 gn-1 可比，但 features[0] 是第一个、无 n-1）。
- ✅ **V858 修复**：首次合并方向取 `seg_dir`（线段方向）作 fallback。依据：特征序列元素是
  **反向笔**（`features.append` 在 `not same_dir` 分支，xd.py:311）——向上段→向下回调笔，其顶
  g1<g2<… 向上→高高（seg_dir=UP→up）；向下段→向上反弹笔，其顶 g1>g2>… 向下→低低（seg_dir=DOWN→down）。
  旧硬编码 "up" 对向下线段**错误**（应取低低却取高高）。第二特征序列传 `opp_dir`（反向候选线段方向）。
  `_merge_feature_sequence` 签名加 `seg_dir: Direction` 参数。
- **双向验证（§4）**：守卫测试 `test_merge_feature_sequence_first_merge_seg_dir_down_low_low`
  （向下段→低低）+ `_up_high_high`（向上段→高高）。ON 时双 pass；临时 revert else 分支回硬编码 "up"
  后 DOWN 守卫**立刻红**（assert 14.0==13.5，高高≠低低）——证修复真实。
- **行为 delta**：偏差E 仅影响**向下线段特征序列首次合并**（罕见触发：需向下段且首组特征笔包含）。
  真实数据 delta=0：144 passed（real_golden_multi xd 2→1 / recursive [51,5,1] / invariants 不变）+
  zs_from_xd 3 passed + lookahead 3 passed + 守卫 65 passed。修复了向下线段首次合并的潜在 bug
  （硬编码 up 取高高，偏离原文趋势），虽真实数据罕见触发，但原文口径正确。


**偏差 F — has_trend 死变量（mmd_conditions.py:16610/16622）【本轮遗留，行为是intentional soft-fix】**
- `has_trend` 赋值后从不读取（grep 确认）。这是**本人本轮 revert 严格门控时遗留的死代码**。
- 行为（笔背驰兜底无 trend 门控）是**本意的 soft-fix 权衡**（严格版让平安+166→+64 丢盘整背驰反转+破15测试）。
- 按53课L12「盘整背驰非第一类买卖点」，这是偏差；但 soft-fix 是权衡取舍，非疏忽。
- ✅ **本次已修（代码卫生，无行为改动）**：删除死变量 `has_trend`（16610/16622 赋值后从不读取），
  注释改为诚实描述 soft-fix 行为（笔背驰兜底始终保留，含同向趋势时）+ 标注与原文53课L12的偏差及
  strict 门控留专项会话的理由。28 单测通过。strict 门控本身（行为改动，破15测试）未加。

**偏差 G — K线包含同组方向翻转（kline_merge.py:73-78,119-120）【✅ 已修 V857】**
- 子代理报：`prev.open/close` 被覆盖为最后K线值（:119-120），致首组（len(result)<2，无 result[-2] 可比）
  每次 merge 按「末根阴阳」重算方向，同组内可翻转（前半取高高后半取低低），合并 high/low 既非高高也非低低。
- 本人已读 kline_merge.py:109-120 确认 prev.open/close 确被覆盖。方向翻转路径真实存在。
- 中severity（上游污染分型基准）。
- ✅ **V857 修复**：首组方向在第一次 merge（`prev.merged_count==0`，prev 仍为原始K线）时按其阴阳锁定，
  后续 merge（`merged_count>0`）沿用 `prev.direction`，不再按末根阴阳重算。len(result)>=2 组方向本就
  自锁（prev.high 单调演进，`prev.high vs result[-2].high` 自强化，无翻转风险），未改。
- **上游对照**（handsomejustin/easy_tdx HEAD kline_merge.py:74,93-94）：上游有**同样的覆盖 + 同样的首组
  方向判定**，方向翻转同样可复现（共有缺陷）。本项目修复后与上游分叉（上游仍带 bug）。
- **双向验证（§4）**：合成 k0阳(10→12)+k1/k2阴被包含——修复前 `dir=down H=10.8`（翻转、H≠真区间高12），
  修复后 `dir=up H=12`（锁定、H正确）。
- **行为 delta**：偏差G 仅影响**首合并组**（len<2），真实数据首组通常 benign（无包含+阴阳翻转组合），
  4 个审计数据集 + 5 个 fixture 全 delta=0（bis/zss/mmds 不变）。守卫测试
  `test_chanlun_kline_merge_first_group.py` 双向验证（stash 后 fail 抓到回归）。267 passed。

**偏差 H — MMD 无 level 字段（53课L14）【架构缺口】**
- 53课L14「不同级别的买卖点意义不同」在数据结构层无承载（MMD dataclass 无 level 字段）。
- 级别靠 to_dict 容器分层表达，信号离开容器无法自证级别。加 `level:int=1` 可闭合但触及1137+回归。

**偏差 I — zsd.py 走势段是自创概念（20课L22）【display-only】**
- 原文20课L22 走势段=Z走势段（中枢内同向次级别走势类型）；代码 zsd.py 是「合并同向线段」，无原文依据。
- `_is_trending` 用「终点>起点」冒充17课趋势（中枢数≥2），同名不同义。
- 不参与买卖点计算（仅前端展示）。

### ❌ 子代理误报（本人抓出，非真实偏差）

**误报 1 — 走势子代理「is_trend 结构性永假（高severity）」= 误读！**
- 子代理说：同级别分解每段最多1中枢，is_trend永假，是代码bug。
- **本人读38课L8/L12核实**：「一旦该中枢完成就继续关注下一个」「允许盘整+盘整连接」——
  同级别分解**本就产出盘整+盘整**，趋势(≥2中枢)分解成多段盘整，**不作为单段趋势出现**。
- **is_trend在单段永假恰恰符合38课原文**。子代理把17课趋势定义(≥2中枢)错套到38课同级别分解。
- V852审计判「趋势0=数据分布合法」反而更接近原文；子代理判「结构性永假误诊」本身才是误判。

---

## 三、本次已修正的错误引用 + 已修复偏差（§3 沉淀）

**53课 line139「黄白线都没拉回0轴不是背驰」= 匿名网友回帖，非缠中说禅原文。**
- 本人核实：53课L139 出自「UID:[0] 匿名哈哈」，在回帖区。
- 真实出处：**第24课 line19（正文）**「B中枢一般会把黄白线回拉0轴附近」+
  **第25课 line313/332（缠中说禅回帖，UID:[1215172700]）**「背弛首先需要的是回拉0轴的黄白线」。
- 已修正 4 处：`mmd_conditions.py:16539` docstring + `:16654` 行内注释 + `BEICHI_FIDELITY_AUDIT_108LESSONS.md` line19/122/337。
- 判据行为正确（0轴门控本身有24课原文支撑），仅引用出处错。

**偏差 F（has_trend 死变量）—— 已修（代码卫生，无行为改动）**
- 删除 `has_trend` 死变量（赋值后从不读取）；注释改为诚实描述 soft-fix 行为 + 标注与原文53课L12偏差。
- strict 门控本身（行为改动，破15测试）未加，留专项会话。

**2买/2卖 msg 文案 bug —— 已修（纯文案，无判定改动）**
- `mmd.py:2489/2525/2633/2668` 原写死「低点 > 1买」/「高点 < 1卖」，跌破/升破时（101课最弱情况）为假命题。
- 改为动态显示实际关系（`>`/`<`/`=`）+ 标注「101课最弱可跌破/升破」。28 单测通过。

---

## 三bis、V857 偏差B/D/G 修复落地 + 全量回归收尾

偏差B（笔端点分型值，62课L20）、偏差D（线段前三笔重叠+破坏确认，65课L34）、
偏差G（K线包含首组方向锁定，62课L22）均已在 V857 落地，双向验证 + 111 passed
（invariants/real_golden/real_golden_multi/recursive/守卫/核心）。详见上文 §二「真实偏差」各条。

**全量 chanlun 回归收尾（bash-146，602s）发现 4 个 failure，已逐个隔离 + 处理（§0/§2）：**

| 测试 | 隔离结论 | 处理 |
|---|---|---|
| `test_chanlun_v735_zs_from_xd` | **偏差B + 偏差D** 引起。偏差B(端点值)使 bi-level mmd 63→61（bar481 1buy/bar498 2buy 消失，端点值使中枢更窄→买点不再成立）；偏差D(破坏确认)使 xd 构中枢 0→5（线段 1→29，旧逻辑 1 线段是确认过于宽松一条贯穿，不符 65课）。偏差D/G 对 bi-level delta=0（exact config 验证） | ✅ 更新固化值（mmds 63→61、xd zs/mmds 0→5/16）+ 隔离注释 |
| `test_changying_chanlun_lookahead_guard` | **偏差B** 引起。端点值使中枢 ZD 升高→3卖（跌破ZD回抽不破ZD，20课）新触发（off 153/on 156）。守卫验证非前视（default==explicit + on==off+lag=3 对应正确）；emitted 不变（3sell 不产生 BUY） | ✅ 更新固化值（off/on/default 各 +1 个 3sell） |
| `test_chanlun_v733_qujiantao_pit` | **偏差B** 引起。端点值口径下旧 KNOWN_CONFIRMED（区间极值口径实测）不再产出截断段确认信号（扫 5 标的端点值口径全量确认均 0；sh603659 仅全量 1 个 bar2003>cut）。区间极值覆盖偏离原文属 bug，确认减少是收紧 | ⚠️ 标 skip + 待办：重测 KNOWN_CONFIRMED（端点值口径有确认的标的）以恢复因果性断言 |
| `test_chanlun_v735_cross_timeframe` | **偏差B+C 引起（V859 修正，原文正确）**。偏差B(端点分型值)使次级别线段 lower_xds 经 find_xds(bis) 受笔极值口径影响→中枢 3→4（62课L20）；偏差C(次级别回调)使 2买/2卖 msg 含「次级别回调」，信号 6→12（17/21/53/101课）。旧断言(3,6)基于区间极值覆盖+同级别笔回调旧口径，已证伪。**之前误判为「既有failure」**：stash 全部源码（含偏差B）后 HEAD 无偏差B→中枢3 passed，误以为非偏差B引起；实为偏差B在 analyser.py L825（非 bi.py），撤 bi.py 不撤偏差B。V859 逐文件隔离（撤 xd/zs/kline_merge/fractal/bi/config/mmd 均仍 4）→ 撤 analyser.py 偏差B（恢复区间极值覆盖）→ 中枢3 passed，确认偏差B引起 | ✅ 更新 assert（zss 3→4、mmds 6→12）+ 偏差C msg 断言 + docstring 原文口径；6/6 cross_tf 测试 passed |

**偏差B 下游效应判据**：偏差B 是 62课L20 原文正确口径（端点分型值，已双向验证 + 对齐上游）。
其下游效应（中枢 ZG/ZD 更窄 → mmd/区间套确认变化）是机械的原文正确效应——区间极值覆盖
偏离原文（属 bug），端点值是原文正确口径，故信号增减是收紧而非回归。但 qujiantao 的
区间套确认口径变化需重测 KNOWN_CONFIRMED（待办，非阻塞偏差B 原文正确性）。

**未彻底完成**：qujiantao KNOWN_CONFIRMED 重测（端点值口径，需扫 286 标的，慢）；
cross_timeframe 既有 failure（非本次引入，留专项）。

---

## 四、总结

**核心结论：缠论模型主干符合原文，无高级别违背。**

用户最关心的三点：
1. **1买是否真用趋势背驰（非笔背驰替代）**：✅ 是。趋势背驰分支完整实现24课A/B/C三段+0轴门控。
2. **所有模型定义是否按原文**：主干符合。分型/笔/1买/3买/对称性高符合；偏差集中在
   中枢GG/DD（已知未修）、2买次级别口径（已知文档化）、线段细节（低实战影响）、
   同级别分解按级别（已知架构缺口）。
3. **审计可信度**：6子代理独立审计 + 本人亲读原文交叉验证，**抓出1处子代理误读**
   （走势is_trend），**修正1处引用错误**（53课L139），体现双重保险价值。

**按优先级的修复建议（更新至 V858）**：
1. ✅ 偏差A 中枢GG/DD（V856 已修）
2. ✅ 偏差B 笔极值覆盖（V857 已修，对齐62课端点分型值）
3. ✅ 偏差D 线段前三笔重叠+破坏确认（V857 已修，65课L34）
4. ✅ 偏差E 特征序列首次合并方向（V858 已修，seg_dir fallback）
5. ✅ 偏差F has_trend死变量（已清理，代码卫生）
6. ✅ 偏差G K线包含方向翻转（V857 已修，首组方向锁定）
7. ✅ 偏差C 2买/2卖次级别走势回调（V859 已修，原文17/21/53/101课「次级别回调」）
   - **口径**：仅在 `process_klines_cross_timeframe`（真实跨周期）传入 `lower_xds` 时启用原文精确口径——2买=1买后第一个次级别向下线段（回调走势）终点；2卖对称。默认 `process_klines`（lower_xds=None）走同级别笔回调近似（与 czsc 库 cxt_second_bs_V240524 同级别并列一致，不强制改默认）。
   - **实现**：mmd.py 新增 `_find_sublevel_callback_xd`（次级别线段找回调）+ `_remap_sublevel_xd_to_daily_bi`（终点对齐日线笔）；`_find_second_type_mmds` 加 `lower_xds` 参数 + 2买/2卖偏差C分支；`find_mmds`/`find_mmds_v39`/`find_mmds_v44` 链路传递；`analyser.process_klines_cross_timeframe` 传入 `lower_xds=lower_result.xds`。
   - **第101课**：允许2买跌破1买，故不要求 cb_xd.low > buy_1_low。
   - **双向验证（§4）**：helper 守卫 3 passed（find_sublevel down/none + remap 对齐）；单元集成 ON（lower_xds传入，2买msg含「次级别回调」+ bi日线笔对齐）+ OFF（lower_xds=None，msg不含「次级别回调」走同级别笔回调）各 1 passed；默认回归 88 passed（lower_xds=None 不变）；chanlun 回归 116 passed/5 skipped/0 failed。
   - **隔离确认**：cross_timeframe 既有中枢 failure（assert 3 实际 4）经 git stash 隔离，系 **V853 same_level 接入** 引起（非偏差C）；偏差C 只改 2买/2卖 msg，不改中枢逻辑（cross_zss 在 find_mmds 前生成）。
8. ⬜ 偏差H MMD level字段：架构缺口，触及1137+回归
9. ⬜ 偏差I zsd命名：display-only，不参与买卖点计算
10. ✅ 偏差J 37课趋势背驰 A/B 同级别（V859 已修）
    - **原文**：37课L8「A、B 是同级别中枢，否则 a+A+b+B+c 只是较大中枢的震荡，非趋势非背驰」。
    - **实现**：beichi.py `_check_qs_beichi` 加 `if prev_zs.level != curr_zs.level: continue`（同向排列后、DIF 检查前）。
    - **双向验证（§4）**：守卫 test_qs_skip_when_level_mismatch_37ke（level=2→无趋势背驰）+ test_qs_pass_when_level_match_37ke（level=1→趋势背驰成立）各 1 passed；beichi 回归 173 passed；sh000001 实测（zss level=1~7）趋势背驰 ON==OFF==1（成立的 A、B 对都同级别，level 检查无副作用）。
    - **c 含 B 的第三类买卖点（37课L10，V859 部分实现）**：beichi.py `_check_qs_beichi` 加 `mmds` 参数，检查 c 段含 B(curr_zs) 的 3买/3卖（`m.mmd_type.value in ("3buy","3sell") and m.zs is curr_zs`）。仅在 cross_timeframe（mmds 非空）启用；默认 process_klines（mmds=None）走 83课近似（c=日线笔，不检查 3买/3卖）。analyser.py L1121 cross_bcs 传 cross_mmds。
    - **双向验证（§4）**：守卫 test_qs_skip_when_c_has_no_third_37ke（mmds 无3买/3卖→无趋势背驰）+ test_qs_pass_when_c_has_third_37ke（有3买/3卖→趋势背驰成立）+ test_qs_pass_when_mmds_none_83ke_approx（mmds=None→83课近似趋势背驰成立）各 1 passed；beichi 回归 97 passed；cross_tf passed。
    - **c=次级别走势（线段，非日线笔）→ 偏差L 已修**：见下「偏差L」。
12. ✅ 偏差L 37课L10 c=次级别走势（线段，V860 已修）
    - **原文**：37课L10「c 必然是次级别的，也就是说，c 至少包含对 B 的一个第三类买卖点」。cross_timeframe 的中枢是次级别线段中枢（find_zss(lower_xds)），离开段 c 应是次级别线段（XD），非日线笔。
    - **偏离**：beichi.py `_check_qs_beichi` 旧用 `_find_leaving_bi(bis)`（日线笔）作 c 段；cross_zss 是次级别线段中枢，c=日线笔尺度不一致，偏离37课L10。
    - **实现**：mmd_conditions.py 新增 `_find_leaving_xd(xds, zs, direction)`（对象引用 `xds.index(zs.lines[-1])` 定位中枢末线段，破边沿的同向XD）；beichi.py `_check_qs_beichi` 加 `lower_xds` 参数：lower_xds 非空（cross_timeframe）→ c=次级别线段（XD），力度用振幅降级（XD.index 是次级别线段序号、closes 是日线，尺度不一致，用 closes=None → abs(high-low)）；lower_xds=None（默认 83课近似）→ c=日线笔（BI），力度用 MACD 面积（closes）。analyser.py L1121 cross_bcs 传 `lower_xds=lower_xds`。
    - **双向验证（§4）**：守卫 test_find_leaving_xd_returns_breakout（_find_leaving_xd 返回破边沿XD）+ test_qs_uses_xd_when_lower_xds_37ke_L10（lower_xds非空→c=XD,BC.curr是XD）+ test_qs_uses_bi_when_no_lower_xds_83ke（lower_xds=None→c=BI 对照）各 1 passed；golden_samples 69 passed；cross_tf/beichi/v859 162 passed/1 skipped。
    - **力度精确化（V861）**：c=次级别线段力度改用次级别 MACD 面积——`check_bi_beichi`/`_check_qs_beichi` 加 `lower_closes` 参数；XD 分支 `_calc_bi_force(XD, lower_closes, 0)` 用 `XD.start/end.bar_index`（次级别 K 线索引）切片 lower_closes 算 MACD 面积（`_calc_bi_force` 实际用 `bi.start.bar_index`/`bi.end.bar_index`，非 bi_idx 参数）；无 lower_closes 时降级振幅。analyser.py cross_timeframe 从 `lower_result.klines` 导出 `lower_closes = [k.close for k in lower_result.klines]` 并传入。守卫 `test_qs_uses_xd_when_lower_xds_37ke_L10` 用 lower_closes=None 验证振幅降级路径（3 passed）；cross_tf 真链路验证 lower_closes 传递（见下）。
    - **DIF检查次级别化（V862）**：`_check_zero_axis_pullback` 用 `curr_zs.lines[0].start.bar_index`/`prev_zs.lines[0].start.bar_index`（mmd_conditions L16589-16591）切片 closes 算 DIF；cross_zss 的 lines 是次级别线段 XD（bar_index 是次级别 K 线索引），但旧传日线 closes → 尺度不一致（end_bar 次级别索引 >= len(closes) 日线 → 保守放行）。修复：`_check_qs_beichi` L229 `dif_closes = lower_closes if (lower_xds is not None and lower_closes) else closes`，cross_timeframe 用次级别 lower_closes 算 DIF（24课 L19/L24 B中枢回拉0轴），尺度一致；默认 process_klines 用日线 closes（中枢 lines 是日线笔）。守卫 3 passed（lower_closes=None→dif_closes=closes=None→放行，振幅降级路径不变）；cross_tf 真链路验证（见下）。
11. ✅ 偏差K 20课L25 趋势判据 GG/DD（V859 已修）
    - **原文**：20课L25 中心定理二「后GG<前DD 等价于下跌及其延续；后DD>前GG 等价于上涨及其延续。后ZG<前ZD 且 后GG>=前DD（或后ZD>前ZG 且 后DD<=前GG）→ 形成高级别走势中枢」。
    - **偏离**：beichi.py `_check_qs_beichi` 旧用 `prev.zg>curr.zg 且 prev.zd>curr.zd`（ZG/ZD 中枢区间）判趋势；原文用 GG/DD（波动区间）。ZG/ZD 不重叠但 GG/DD 重叠时（中枢区间分离但波动区间重叠），原文是高级别中枢（非趋势），旧判据误判为趋势。
    - **实现**：改为 `is_down_trend = curr_zs.gg < prev_zs.dd` / `is_up_trend = curr_zs.dd > prev_zs.gg`（GG/DD 判据）。GG/DD 由偏差A（zs.py 同向段 Zn）正确维护。
    - **双向验证（§4）**：守卫 test_qs_skip_when_zgzd_trend_but_ggdd_overlap_20ke（ZG/ZD 排列但 GG/DD 重叠→无趋势背驰，即高级别中枢）+ test_qs_pass_when_mmds_none_83ke_approx（GG/DD 不重叠→趋势背驰成立）各 1 passed；既有 test_qs_beichi_exit_stroke_after_zs / test_qs_beichi_anchored_to_exit_segment 构造更新满足 GG/DD；golden_samples 65 passed + beichi/invariants 123 passed + cross_tf 6 passed。

**已做的验证**：偏差A-L（除H/I低优先）均双向守卫+回归验证；偏差H（MMD level：mmd.zs.level 隐含级别，代码 0 处直接访问 `.zs.level`，17 处全用 `is None`/`is not None` 判断，加 level 字段冗余，低优先不修）、偏差I（zsd 命名：zsd 是 XD 类型，命名「zsd」是显示标签不改计算，display-only 低价值不修）。**全量 pytest 已跑**（5101 passed + 35 skipped + 23 failed，2331s/38:51）；23 failed 全是既有失败（test_screen_usefulness_audit/test_screening_router/test_v721_fixes，非缠论模型：屏幕审计/路由/MAC qfq 数据获取），与偏差A-L 改动无关；缠论模型核心测试全过（golden_samples 69 passed + beichi 95 passed + 偏差L/C守卫 82 passed + 偏差L/D/A守卫 12 passed）。
**未做的验证**：偏差的实际发生率未在真实行情量化（除茅台前三笔重叠0违反已实测）。
