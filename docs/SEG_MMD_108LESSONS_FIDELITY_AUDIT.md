# seg_mmd.py（线段级别买卖点）缠论108课原文保真审计报告

**审计对象**：`src/easy_tdx/chanlun/seg_mmd.py`（689 行，`find_mmds_seg` 及 `_detect_t1` / `_detect_t2` / `_detect_t2s` / `_detect_t3`）
**原文基准**：`docs/缠论108课/`（115 篇），重点第 15/17/20/21/24/27/28/29/53/61/91/101 课
**审计方式**：原文逐条摘引 + 代码逐行核对 + 自建合成走势受控探针（13 组，`/tmp/audit/probe_*.py`）+ 500 例随机游走统计对照

**激活前提**：`use_seg_mmd` 默认为 `False`（`config.py:266`），本模块仅在显式开启后才参与选点；因此下文各项偏差的严重度均以此为前提标注。但定义性偏差与默认值无关，一旦开启即如实发生。

---

## 偏差 1：三类买卖点（T3A）参照的中枢对象错误 —— 用「下一线段自身的中枢」替代「被离开的中枢」

**原文定义**（第20课，`20.缠中说禅走势中枢级别扩张及第三类买卖点.md:26`）：

> 由定理一，可以得到第三类买卖点定理：一个**次级别走势类型向上离开缠中说禅走势中枢**，然后以一个次级别走势类型回试，其**低点不跌破 ZG**，则构成第三类买点。

即：回试笔的比较基准必须是**被离开的那个中枢**的 ZG/ZD。第21课进一步限定「第三类买点是中枢扩张或新生产生的」（`21.缠中说禅买卖点分析的完备性.md:10`）。

**代码实现**（`seg_mmd.py:557-598`）：

```python
# ── T3A: 下一线段首个中枢突破后不回 ──
next_si = si + 1
if next_si < len(xds):
    next_zss = [z for z in seg_zss.get(next_si, []) if len(z.lines) >= 2]
    ...
        for zs_idx, zs in enumerate(next_zss):      # ← 取「下一线段」的中枢
            ...
            bsp3_bi = bis[exit_pos + 1]
            if is_buy:
                if bsp3_bi.low < zs.zg:             # ← 与「下一线段中枢」的 ZG 比较
                    continue
```

**偏差说明**：
1. `zs` 来自 `seg_zss.get(next_si)`，即**当前线段之后那条反向线段自己内部的中枢**，而不是「被次级别走势离开的那个中枢」。
2. 方向性后果：下跌线段末端出 1buy 后，进入的是**上涨线段**，其首个中枢必然位于**原下跌中枢之上**（价格已上行才可能构中枢）。用这个更高的 ZG 作门槛，等价于要求回试笔「不进入上涨趋势自身的中枢」——那不是第三类买点，而是上涨中枢之上的延续。
3. 实证（受控探针 `probe_t3a_ctrl.py`，下跌两中枢 [90,96]/[78,86]→1buy@60→bi9 离开 high=105→bi10 回试 low=90）：原文口径 `low(90) > ZG(86)` ⇒ **标准 3buy 成立**；代码 T3A 参照上涨线段中枢 `ZG=105`，`90 < 105` ⇒ `continue`，**漏判**。
4. 实证（`probe_t3_final.py`，400 例随机游走）：原文口径应触发 136 例，代码仅 T3A 20 例 + T3B 104 例，且差集方向以假阴为主。
5. 统计（`probe_t3_overlap.py`，500 例）：原文出而代码不出（假阴）**37 例**，代码出而原文不出（假阳）**21 例**。

**严重度**：高。这是三类买卖点的核心定义对象错误，直接改变信号集合；且偏差方向不对称（同时存在假阴与假阳）。

---

## 偏差 2：T3A 未执行第20课「必须是第一次」的约束

**原文定义**（第20课:36）：

> 但一定要注意，并不是任何回调回抽都是第三类买卖点，**必须是第一次**。

**代码实现**（`seg_mmd.py:562-598`）：循环 `for zs_idx, zs in enumerate(next_zss)` 内逐个中枢判定，唯一约束是 `if zs_idx >= bsp3a_max_zs_cnt: break`（L563），即只按「扫描前 N 个中枢」截断，**没有任何「第一次离开/回试」的计数或去重**。同一次级别离开后的多次回抽，只要各自满足 `low >= zs.zg`，会被重复判为第三类买点。

**偏差说明**：
1. 「第一次」的含义是：对该中枢的**首次次级别离开 + 首次次级别回试**才算；后续同一中枢上方的震荡回抽都不算。代码无此状态。
2. `bsp3a_max_zs_cnt=1` 只是「最多看几个中枢」的工程扫描上限，与「第一次回抽」是两回事，不能互相替代。
3. 该偏差与偏差 1 叠加：T3A 参照的中枢本就是错的，「第一次」又未校验，导致 3 类信号在原文不成立时也频繁触发（见偏差 1 的 21 例假阳）。

**严重度**：高。第20课用「必须」明确否定了非首次回抽；无此约束会系统性多发 3 类信号。

---

## 偏差 3：一类买卖点（T1）的趋势门槛形同虚设 ——「趋势背驰」在默认配置下不会触发

**原文定义**：
- 第17课:30：「缠中说禅趋势：在任何级别的任何走势中，某完成的走势类型**至少包含两个以上**依次同向的缠中说禅走势中枢，就称为该级别的缠中说禅趋势。」
- 第27课:4：「对于背驰来说，肯定不会发生在第一个中枢之后，**肯定是至少是第二个中枢之后**」；「如果在第一个中枢就出现背驰，那不会是真正意义上的背驰，只能算是盘整背驰」。
- 第15课:32：「没有趋势，没有背驰。**在盘整中是无所谓'背驰'的**」。

即：T1（第一类买点）必须以**趋势**（≥2 个同向中枢）为前提。

**代码实现**（`seg_mmd.py:180, 194-198, 220`）：

```python
min_zs_cnt = getattr(config, "seg_min_zs_cnt", 1)          # L180
...
multi_bi_zss = [z for z in zs_lst if len(z.lines) >= 2]
zs_cnt = len(multi_bi_zss) if bsp1_only_multibi else len(zs_lst)
is_target = min_zs_cnt <= 0 or zs_cnt >= min_zs_cnt       # L198
...
if len(multi_bi_zss) >= 2 and multi_bi_zss[-1].exit_bi is not None:   # L220 → T1 趋势背驰
```

**偏差说明**：
1. L198 的 `is_target` 初值由 `seg_min_zs_cnt` 决定，默认 `=1` ⇒ 只要线段含 **1 个**多笔中枢即 `is_target=True`；再经 L220 判断 `>=2` 才走 T1 分支，**1 个中枢时落入 L271 的 T1P 分支**。表面上「趋势背驰需 ≥2 中枢」已由 L220 保证。
2. 但 **T1P 分支（L265-306）与 T1 分支（L220-264）使用完全相同的判定式**（同样比较 `enter_bi`/`exit_bi` 的 MACD、同样要求创新极值 `bs1_peak`），且**产出同一个 `MMDType.BUY_1/SELL_1`**（L297 `mmd_type = MMDType.BUY_1 if is_down else MMDType.SELL_1`）。二者唯一差别只有 `msg` 文案 `"T1P 盘整背驰 ..."` vs `"T1 趋势背驰 ..."`。
3. 因此下游（`analyser.py:925-944`）与任何消费者看到的都是**同一类 MMD 类型**，无法区分「趋势背驰 1 买」与「盘整背驰 1 买」。第27课:34 明确「第一类买点肯定是趋势背驰构成的」，盘整背驰只是「类第一类买点」且「这个级别，至少应该是周线以上」；代码把盘整背驰按第一类买卖点同型发出。
4. **0 中枢兜底分支（L308-353）在默认配置下是死代码**：`zs_cnt=0` 时 `is_target` 初值为 `False`（`seg_min_zs_cnt=1`），而该分支只会把 `is_target` 改 `False`，永不可能产出。实证（`probe_dead.py`：MACD 明显背驰，bi2 面积 0.10×11 < bi0 0.25×11，产出 0 例）。该分支的注释自称「原文无此概念，保留最后两根同向笔比较」，实为不可达代码。
5. 进一步：即便 T1 分支被走到，它比较的是 `enter_bi` 与 `exit_bi` 两根**笔**的 MACD，而非第24课的 A/B/C 三段走势类型（见偏差 4）。

**严重度**：中。T1/T1P 分流在「判定式」上正确，但**输出类型未区分**，使「趋势背驰才构成第一类买点」这条原文约束在消费端失效；附带一段死代码。

---

## 偏差 4：背驰度量默认用「MACD 柱峰值」而非原文的「柱子面积」，且无黄白线回拉 0 轴检验

**原文定义**（第24课，`24.MACD对背弛的辅助判断.md`）：

> 用MACD判断背驰，首先要有两段同向的趋势……把这三段分别称为A、B、C段。显然，**B的中枢级别比A、C里的中枢级别都要大**……这个中枢**一般会把MACD的黄白线（也就是DIFF和DEA）回拉到0轴附近**。而**C段的走势类型完成时对应的MACD柱子面积**（向上的看红柱子，向下看绿柱子）**比A段对应的面积要小**，这时候就构成标准的背弛。

**代码实现**（`seg_mmd.py:130-154, 183, 233-238`）：

```python
def _macd_area(...):   # 面积口径（存在但非默认）
def _macd_peak(...):   # 峰值口径
...
macd_algo = getattr(config, "seg_macd_algo", "peak")      # L183，默认 peak
...
if macd_algo == "area":
    in_metric  = _macd_area(...)
    out_metric = _macd_area(...)
else:  # peak
    in_metric  = _macd_peak(macd_data, enter_ks, enter_ke, not is_down)   # L237
    out_metric = _macd_peak(macd_data, exit_ks, exit_ke, not is_down)     # L238
```

配置默认：`seg_macd_algo: str = "peak"`（`config.py:294`）。

**偏差说明**：
1. 原文口径是**面积**（「柱子面积……比A段对应的面积要小」），第27课:12 再次以万科季线为例确认「柱子的面积是明显小于第1段的」。默认 `peak` 取区间极值，与面积不是同一量：一段「矮而长」的面积可以大于「高而短」的峰值，峰值口径会把前者误判为不背驰；反之亦然。
2. 原文要求 A/B/C **三段**且 B 为更大级别中枢；代码只取 `enter_bi`（进入中枢前最后一段）与 `exit_bi`（离开段）**两根笔**作 A/C，既无 B 段概念，也无「B 的中枢级别更大」检验。
3. 原文的「黄白线回拉 0 轴附近」在代码中**完全没有实现**（`_macd_peak`/`_macd_area` 只读 `macd_data["hist"]`，从不读 `dif`/`dea`）。`find_mmds_seg` 的 docstring 虽声明 `macd_data` 含 `dif/dea/hist`，实际未使用前两者。
4. 该偏差在**买卖两侧同构**（`not is_down` 只是切换取 `max` 还是 `abs(min)`），故不构成方向不对称，但两侧同时偏离原文。

**严重度**：中。默认值即偏离原文口径，且缺失 0 轴回拉这一关键前置条件，会显著改变背驰成立与否。

---

## 偏差 5：二类买卖点回踩阈值 `max_bs2_rate=0.8` 为无原文依据的工程魔数（且在默认路径上是死变量）

**原文定义**（第101课，`101.答疑1.md:22`）：

> 第二类买点跌破第一类买点，也就是第二类买点比第一类买点低，**这是完全可以的**。

第101课:12：「所谓第二类买点，就是第一类买点的次级别回抽结束后再次探底或回试的那个次级别走势的结束点。」——全文**没有任何幅度/比例门槛**。

**代码实现**（`seg_mmd.py:379, 401-418`）：

```python
max_bs2_rate = getattr(config, "max_bs2_rate", 0.8)      # L379
...
break_amp = _bi_amp(break_bi)
if break_amp <= 0:
    continue
retrace_rate = _bi_amp(bsp2_bi) / break_amp              # L405
# 101课原文：None=无门槛（总出2buy）；有门槛时 retrace<=门槛才出
if mmd_2nd_max_pullback is None or retrace_rate <= mmd_2nd_max_pullback:   # L408
    ... mmds.append(mmd)
```

**偏差说明**：
1. `max_bs2_rate` 被读取（L379）但**在比较中从未使用**——L408 的门槛取自 `mmd_2nd_max_pullback`（默认 `None`），`max_bs2_rate` 是纯死变量。`config.py:274` 对它的注释也自认「仅当 `mmd_2nd_max_pullback` 非空时作为 fallback」，而代码里连这个 fallback 都没接。`_detect_t2s` 的 L440 同理死读一次。
2. 从原文保真看这是「好事」：默认 `None` ⇒ 无门槛，符合第101课。实证（`probe_t2_rate.py`）：retrace_rate=3.00（远超 0.8）时默认配置仍产出 T2（1 例），与原文一致；`mmd_2nd_max_pullback=0.5` 时才抑制。
3. 但**该魔数仍以配置项形式暴露**（`max_bs2_rate: float = 0.8`，`config.py:274`），docstring L371 仍写「回踩幅度 ≤ max_bs2_rate」——**注释与代码不符**，且诱导使用者以为存在 0.8 门槛。这是「文档声明的能力实际不存在」的反向失真：若有人按注释依赖 0.8 抑制，实际不会发生。

**严重度**：低。默认行为符合原文；但死变量 + 失实 docstring 是可维护性缺陷，且 `max_bs2_rate` 一旦被误接进比较就会立刻变成无原文依据的魔数。

---

## 偏差 6：二类买卖点在「笔」上判定，而非原文的「次级别走势类型结束点」

**原文定义**：
- 第101课:12：「第二类买点，就是第一类买点的**次级别回抽**结束后再次探底或回试的那个**次级别走势的结束点**。」
- 第17课:53：「任何级别的第二类买卖点都**由次级别相应走势的第一类买点构成**。」

**代码实现**（`seg_mmd.py:394-418`）：

```python
break_bi  = bis[bsp1_pos + 1]        # L394：1买后第一根反向笔
bsp2_bi   = bis[bsp1_pos + 2]        # L395：第二根同向笔
retrace_rate = _bi_amp(bsp2_bi) / break_amp
if mmd_2nd_max_pullback is None or ...:
    mmds.append(MMD(mmd_type=..., bi=bsp2_bi, ...))
```

**偏差说明**：
1. 原文的 2 买是「次级别**走势类型**的结束点」；代码是「第一根反向笔之后的第二根同向笔」——**用笔替代了次级别走势类型**。
2. 一根笔连一个次级别中枢都不构成（第91课:16「笔是不能构成中枢的」），更不是「次级别走势的第一类买点」。
3. 该偏差与 `zs_from_xd=False`（`config.py:72`，全项目多处显式传 False，如 `analyser.py:856`、`web/routers/chanlun.py:2304`）叠加：`seg_mmd` 的注释 L15 自述「中枢用笔构（zs_from_xd=False 口径），但买卖点在线段末端判定」。即**用笔构中枢来支撑线段级别买卖点**，而第91课明确笔不能构中枢。这是已文档化的工程近似，但与原文「线段级别走势中枢」仍差一级。
4. 实证旁证（`probe_sym.py`、`probe_peak_sym.py`）：T1/T2 判定对 `bis` 的索引推进（`bsp1_pos+1`、`+2`）完全基于笔，买卖两侧对称——偏差是**同构**的，不构成方向不对称，但两侧同时低于原文的级别要求。

**严重度**：中。模块自身定位是「线段级别买卖点」，却以笔为基本单位实现 2 买，级别口径与原文定义差一级；且这是该模块结构性（非配置可调）的偏差。

---

## 偏差 7：`divergence_rate` 读取了不存在的配置键，`seg_divergence_rate` 被静默忽略

**原文定义**：无直接对应（背驰比例阈值为工程参数），但**键名不一致导致用户配置失效**属保真审计中的「配置不可达」缺陷。

**代码实现**（`seg_mmd.py:179`）：

```python
divergence_rate = getattr(config, "divergence_rate", 0.8)
```

**配置定义**（`config.py:268`）：

```python
# 背驰率阈值：exit 笔 MACD 指标 ≤ divergence_rate × enter 笔 MACD 指标
seg_divergence_rate: float = 1.5
```

**偏差说明**：
1. 运行时实证：`hasattr(ChanlunConfig(), 'divergence_rate')` = **False**；`getattr(c, 'divergence_rate', 0.8)` = **0.8**。`dataclasses.fields(ChanlunConfig)` 中不存在 `divergence_rate` 字段。
2. 因此 `seg_mmd.py` 永远使用硬编码 **0.8**，用户在 `config.py` 里设的 `seg_divergence_rate=1.5`（乃至任何自定义值）**完全不生效**，且不报错、不告警。
3. 0.8 与 1.5 差异巨大（1.5 意味着 `out <= 1.5*in` 几乎恒真 ⇒ 几乎总判背驰）。这是一条静默的错误配置通道。
4. 该偏差影响 T1 三个分支（L240/L287/L340 三处 `is_diver` 判定）——`use_seg_mmd=True` 时一类买卖点的背驰阈值实际由 L179 的魔数决定。

**严重度**：中。不影响默认语义（0.8 仍是常用工程值），但使用户唯一可调的对应配置项失效，且失效方式不可观测。

---

## 偏差 8：`strict_bsp3` / `bsp3_peak` / `bsp3a_max_zs_cnt` 是无原文依据的工程魔数，且 `strict_bsp3` 为死变量

**原文定义**：第20课:26 的三类买卖点定理只要求「次级别离开 + 次级别回试 + 低点不跌破 ZG」；第61课:26 补充结构下限：

> 一个第三类买卖点，**至少需要有5段次级别的，前三段构成中枢，第四段离开中枢，第5段构成第三类买卖点**。

**代码实现**（`seg_mmd.py:525-527, 563-564, 583-588`）：

```python
strict_bsp3 = getattr(config, "strict_bsp3", False)     # L525 —— 读取后从未使用
bsp3_peak   = getattr(config, "bsp3_peak", False)       # L526
bsp3a_max_zs_cnt = getattr(config, "bsp3a_max_zs_cnt", 1)  # L527
...
if zs_idx >= bsp3a_max_zs_cnt:      # L563：只扫描前 N 个中枢
    break
...
if bsp3_peak:                       # L584：要求回试笔不破中枢极值 DD/GG
    if is_buy and bsp3_bi.low > zs.dd:
        continue
    if not is_buy and bsp3_bi.high < zs.gg:
        continue
```

**偏差说明**：
1. **`strict_bsp3` 是死变量**：全文件仅 L525 一次赋值，无任何使用点（`grep -n strict_bsp3` 仅 1 处命中）。配置项 `strict_bsp3: bool = False`（`config.py:283`）对行为零影响。
2. `bsp3a_max_zs_cnt=1`：原文无「只扫描下一线段第一个中枢」的说法；这是用工程扫描上限替代了原文对「被离开中枢」的定位（与偏差 1 叠加）。
3. `bsp3_peak` 要求 `low > zs.dd` / `high < zs.gg`，即回试笔不进入中枢的**极值区间**（比 ZG/ZD 更严）。原文第20课的门槛是 ZG/ZD，第29课:11 反而说「该反弹**一定触及**最后一个中枢的 `DD=min(dn)`」——原文允许（且必然）触及 DD，`bsp3_peak=True` 会把触及 DD 的标准 3 类买点判为不合格。默认 `False` 故不触发，但开关语义与原文相反。
4. **第61课「至少 5 段次级别」的结构下限在代码中完全没有实现**：`_detect_t3` 既不校验前三段构成中枢、第四段离开、第五段构成 3 类，也不统计段数。T3A 仅用 `bis[exit_pos+1]` 一根笔、T3B 仅用 `range(bsp1_pos+2, len(bis), 2)` 逐根笔扫描，与「5 段次级别」无对应关系。

**严重度**：中。默认配置下 `strict_bsp3`/`bsp3_peak` 不触发，但「≥5 段次级别」这条原文结构约束缺失是定义性的；死变量与反向语义的开关构成维护陷阱。

---

## 偏差 9：三类买卖点（T3B）在笔索引上机械推进，且重复计数、缺少「第一次」与「不回中枢」的严格判定

**原文定义**：第20课:26（离开 + 回试不破 ZG/ZD）；第20课:36（必须是第一次）；第53课:18：

> 而在第二、三买卖点之间，都是中枢震荡，这时候，**是不会有该级别的买卖点的**。

**代码实现**（`seg_mmd.py:600-631`）：

```python
last_zs = zs_lst[-1]
if last_zs.exit_bi is not None:
    exit_pos = bi_idx_map.get(last_zs.exit_bi.index, -1)
    if exit_pos >= 0 and exit_pos + 2 < len(bis):
        for bsp3_pos in range(bsp1_pos + 2, len(bis), 2):   # L607：按 +2 逐根笔
            if bsp3_pos > exit_pos + 2:
                break
            bsp3_bi = bis[bsp3_pos]
            is_buy = is_down
            if is_buy:
                if bsp3_bi.low < last_zs.zg:    # L616
                    continue
            else:
                if bsp3_bi.high > last_zs.zd:
                    continue
            mmds.append(MMD(mmd_type=..., bi=bsp3_bi, msg="T3B 突破前中枢", ...))
            break                                    # L631：命中即停
```

**偏差说明**：
1. `range(bsp1_pos + 2, len(bis), 2)` 是按**笔索引奇偶步进**的机械扫描，不构成「次级别走势类型离开 + 次级别走势类型回试」的两段式结构（第61课的 5 段式更无从体现）。
2. `continue`（L617/L620）与 `break`（L631）混用：循环遇到「回到中枢内」的笔就 `continue` 跳过、继续往后找，直到遇到一根满足 `low >= zg` 的笔才 `break`。这意味着**允许中间任意多根笔跌回中枢**，与「次级别回试不跌破 ZG」的单次回试语义不符；且「必须是第一次」（第20课:36）同样未校验。
3. `if bsp3_pos > exit_pos + 2: break` 用**笔索引差**粗截扫描窗口，无原文依据。
4. 实证（`probe_t4.py`）：构造 1buy 后 bi2/bi4/bi6 均 `low < zg`、bi8 `low > zg`，代码因 `continue` 一直扫到 bi8 才出 T3B——即把「第三次回试」当成了 3 类买点，正是第20课「并不是任何回调回抽都是第三类买卖点」所否定的情形。
5. 实证（`probe_t3_final.py` / `probe_t3_overlap.py`）：T3B 是代码 3 类信号的主要来源（104/124 例），也是假阳（21 例）与假阴（37 例）的主要来源。

**严重度**：高。T3B 是 `use_seg_mmd=True` 时 3 类买卖点的主力通道，其结构、首次性、回试语义三项同时偏离原文。

---

## 偏差 10：类二买卖点（T2S）在 108 课原文中无对应定义，属于自创概念

**原文定义**：108 课中检索「类二」**零命中**（精确词）；仅有两处近似表述，且均非定义：
- 第27课:38：「……可以构成**类似第二类买点**的买点……构成一个典型的**类第二类买点**」（指大级别周线以上不创新低的买点）。
- 第86课:66：「……那第三类买卖点，就有点**新走势的类第二类买卖点**的样子了。（**注意，这只是比喻**，不是说这就是大级别的第一、二买卖点。）」

**代码实现**（`seg_mmd.py:423-501`）：

```python
def _detect_t2s(...):
    """检测类二买卖点（T2S）。
    chan.py 逻辑：
    - 二类后，连续同向笔与二类笔重叠
    - 每根重叠的同向笔都是类二
    """
    ...
        bias = 2
        while bsp2_pos + bias < len(bis):
            bsp2s_bi = bis[bsp2_pos + bias]
            if max_bsp2s_lv is not None and bias // 2 > max_bsp2s_lv:   # L464
                break
            if bias == 2:
                if not _has_overlap(...): break
                _low = max(...); _high = min(...)
            elif not _has_overlap(_low, _high, ...):
                break
            # 类二不能突破一类
            if is_buy and bsp2s_bi.low < break_bi.low: break     # L480
            ...
            retrace_rate = abs(_bi_end_val(bsp2s_bi) - _bi_end_val(break_bi)) / _bi_amp(break_bi)  # L485
            if mmd_2nd_max_pullback is not None and retrace_rate > mmd_2nd_max_pullback: break      # L487
            mmds.append(MMD(mmd_type=MMDType.BUY_2S if is_buy else MMDType.SELL_2S, ...))           # L490
            bias += 2
```

**偏差说明**：
1. 原文中「类第二类买点」是第27课对**大级别（周线以上）盘整背驰型买点**的比喻性称呼，且第86课明确「这只是比喻，不是说这就是大级别的第一、二买卖点」。代码的 T2S 定义为「2 买之后与 2 买笔区间重叠的连续同向笔」，与该比喻**完全不是一回事**。
2. 代码用一个独立枚举 `MMDType.BUY_2S/SELL_2S` 承载这个概念，使其在输出中与第101课定义的第二类买卖点（`MMDType.BUY_2/SELL_2`）平级，**虚增了买卖点种类**。
3. 「每根重叠的同向笔都是类二」（`bias += 2` 循环、`max_bsp2s_lv` 不限）会在一段中枢震荡中连发多个 T2S，与第53课:18「在第二、三买卖点之间，都是中枢震荡，这时候，是不会有该级别的买卖点的」直接冲突——原文说该区间**没有**该级别买卖点，代码却在其中批量产出。
4. L485 的 `retrace_rate` 分母用 `_bi_amp(break_bi)`，`break_bi = bis[bsp2_pos - 1]`（L454）是 2 买**之前**的那根笔，与 L405 的 T2 回踩率口径（分母为 1 买后的反弹笔）不同源，属自设量纲。

**严重度**：中。概念本身无原文依据；且在第二/三类买卖点之间的中枢震荡区批量发信号，与第53课明确冲突。

---

## 偏差 11：`_map_zs_to_seg` 用「中枢第一根笔的 start k_index」归属线段，会跨线段错配中枢

**原文定义**：第91课:16「笔是不能构成中枢的」；线段（次级别走势类型）才是中枢的合法构件。原文中「某级别的走势中枢」归属应由构成它的次级别走势整体决定。

**代码实现**（`seg_mmd.py:96-127`）：

```python
for bi_i, bi in enumerate(bis):
    bi_s = bi_start[bi_i]
    for si, (seg_s, seg_e) in enumerate(seg_ranges):
        if seg_s <= bi_s <= seg_e:      # ← 笔的 start k_index 落在线段范围内即归属该线段
            bi_to_seg[bi.index] = si
            break
...
for zs in zss:
    first_line = zs.lines[0] if zs.lines else None
    ...
    seg_idx = bi_to_seg.get(first_line.index)     # ← 用中枢第一根笔归属
    if seg_idx is None:
        if zs.enter_bi is not None:
            seg_idx = bi_to_seg.get(zs.enter_bi.index)   # fallback
```

**偏差说明**：
1. 归属依据是「中枢**第一根笔**的起始 k_index 落在哪个线段的 [start, end] 区间」。一个中枢通常跨 3~5 根笔，可能横跨相邻两条线段；此时它被整体归给「第一根笔所在的那条线段」，另一条线段则完全看不到这个中枢。
2. 后果直接影响买卖点：`seg_zss` 是 `_detect_t1`（`zs_cnt`、T1/T1P 分支）、`_detect_t3`（`zs_lst`、T3B 参照中枢）的唯一数据源。实证（`probe_dir.py`）：下跌线段末端 1buy 后，其**最后一个中枢**被 `_map_zs_to_seg` 判给了线段 1（`lines=[5,6,7,8,9]` 归到线段 1，而 1buy 在 bi8、属于线段 0），导致线段 0 的 `zs_lst` 最后一个中枢变成 `[0,1,2,3,4]`（ZG=96 而非 86），T3B 参照的 ZG 随之错高 10 个点，教科书式 3buy（回试 low=88 > 86）被判不合格。
3. fallback 用 `enter_bi` 归属，而 `enter_bi = bis[first.index-1]`（`zs.py:489-497`）在中枢位于线段首部时为 `None`，此时 `seg_idx is None`，中枢被**静默丢弃**（`result[seg_idx]` 无赋值）。实证（`probe_t2.py`）：ZS#0 的 `enter_bi=None`。
4. 这是结构性偏差：`_map_zs_to_seg` 的映射口径没有原文依据（原文不存在「按第一根笔归属」），且直接造成 T1/T3 的中枢集合错误。

**严重度**：高。它同时污染 T1 的中枢计数（决定 T1/T1P 分流）与 T3 的参照中枢，是偏差 1/3/9 的共同上游成因之一。

---

## 附：已核对但**不构成偏差**的项（按任务要求不列入偏差计数）

- T1/T2/T2S/T3 的**买卖两侧符号对称**：`_macd_peak(..., not is_down)` 正确切换 `max`/`abs(min)`；`is_buy`/`is_down` 分支在 L245-253、L480-483、L574-581、L615-620 均成对出现。实证（`probe_peak_sym.py`）两侧判定等价。
- T2 的 `mmd_2nd_max_pullback=None` 默认 ⇒ 无回踩门槛，符合第101课（实证 `probe_t2_rate.py`：retrace=3.0 仍出 T2）。
- `bsp2_follow_1`/`bsp3_follow_1` 要求买卖点跟随一类，符合第101课「第二类买点就是第一类买点的次级别回抽……」与第21课「第一类与第三类不可能重合」。
- `find_mmds_seg` 的流水线顺序（T1→T2→T2S→T3）与 `analyser.py:925-944` 的派发逻辑自洽；`seg_mmd_hybrid` 混合模式保留笔级 T2/T3 是显式工程选择。

---

## 实证清单（自建探针，均在 `easy_tdx/.venv` 下实跑）

| 探针 | 验证内容 | 结果 |
|---|---|---|
| `probe_t1.py` / `probe_t2.py` | `find_zss` 产出的 `enter_bi`/`exit_bi` 方向与归属 | ZS#0 `enter_bi=None`（证实偏差 11） |
| `probe_t3.py` / `probe_t4.py` | T3A/T3B 分支可触发性 | T3A 因 `exit_bi` 条件极少触发；T3B 经 `continue` 跳过中枢内笔 |
| `probe_t5.py` / `probe_t6.py` | T3A 参照中枢对象 | 确认取「下一线段中枢」而非「被离开中枢」 |
| `probe_t3_final.py` | 400 例随机游走，T3A/T3B vs 第20课 | 原文应触发 136，代码 20+104；差集以假阴为主 |
| `probe_t3_overlap.py` | 500 例随机游走，假阳/假阴计数 | 假阳 21、假阴 37 |
| `probe_t3a_ctrl.py` | 受控：回试 low 落在两中枢 ZG 之间 | 原文出 3buy，代码不出（假阴实锤） |
| `probe_dir.py` | 教科书式 3buy + `_map_zs_to_seg` 错配 | 末中枢被错归线段 1，ZG 由 86 变 96，漏判 |
| `probe_dead.py` | 0 中枢兜底分支可达性 | 默认配置下死代码（产出 0） |
| `probe_t2_rate.py` | `max_bs2_rate` 死变量 / `mmd_2nd_max_pullback` 生效 | `max_bs2_rate` 未参与比较；None 时无门槛（合原文） |
| `probe_sym.py` / `probe_peak_sym.py` | 买卖对称性 | 两侧对称，非不对称偏差 |
| `verify_report_facts.py` | 报告引用的 24 个行号逐一实读核对 | 23/24 精确匹配（1 处为行号笔误，已修正） |

---

审计结论：发现 11 个偏差点。
