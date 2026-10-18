# easy_tdx 背驰（beichi/divergence）实现对照缠论108课原文 符合性审计报告

**审计方式**：只读不改（read-only）。所有仓库文件均未修改；验证脚本全部写在 `/tmp/` 下。
**审计对象**：`src/easy_tdx/chanlun/` 下 `mmd.py`、`mmd_conditions.py`、`beichi.py`、`macd.py`、`seg_mmd.py`、`config.py`、`analyser.py`
**原文依据**：`docs/缠论108课/` 第 15、24、25、27、37、43、44 课（+第 21、29、53 课作辅助判据）
**实测数据**：`audit_data/*_daily.json` 真实日线，取 6~12 只 × 最近 1200 根 K 线；所有比率均来自可复跑脚本（见附录 A）。

---

## 一、原文定义提炼（审计基准）

| 概念 | 原文定义（逐字/精炼） | 出处 |
|---|---|---|
| **没有趋势，没有背驰** | 「必须注意：**没有趋势，没有背驰**。在盘整中是无所谓"背驰"的」 | 第15课 line 32 |
| **趋势的前提** | 「当说`a+A+b+B+c`中有背驰时，**首先要`a+A+b+B+c`是一个趋势**。而一个趋势，就意味着**A、B是同级别的中枢**，否则就只能看成是其中较大中枢的一个震荡」 | 第37课 line 8 |
| **c 段的级别要求** | 「`c`必然是**次级别的**，也就是说，`c`**至少包含对`B`的一个第三类买卖点**，否则就可以看成是`B`中枢的小级别波动，完全可以用盘整背驰来处理」 | 第37课 line 10 |
| **c 段必须创新极值** | 「如果`a+A+b+B+c`是上涨，`c`**一定要创出新高**；是下跌，`c`**一定要创出新低**」 | 第37课 line 12 |
| **MACD 判背驰的前提** | 「用MACD判断背驰的前提是，A、B、C段在一个大的趋势里，其中**A之前已经有一个中枢**，而**B是这个大趋势的另一个中枢**，这个中枢**一般会把MACD的黄白线（DIFF和DEA）回拉到0轴附近**。而C段的走势类型完成时对应的**MACD柱子面积**（向上的看红柱子，向下看绿柱子）**比A段对应的面积要小**」 | 第24课 line 19 |
| **黄白线回拉0轴是必要条件** | **正文（第24课 line 19，权威出处）**：「B 是这个大趋势的另一个中枢，这个中枢**一般会把 MACD 的黄白线（DIFF 和 DEA）回拉到 0 轴附近**」；**缠中说禅回帖（第25课 line 313/332，UID:[1215172700]）**：「背驰需要多少个条件？光柱子缩短就背驰？**前面的黄白线有回拉0轴吗？**」「背弛首先需要的是**回拉0轴的黄白线**」 | 第24课 line 19（正文）、第25课 line 313/332（缠师回帖）。注：曾误引「第53课 line 139」，经核该句出自回帖区**匿名网友**（UID:[0]，非缠中说禅），已剔除 |
| **趋势背驰 vs 盘整背驰的判据** | 「如果在**第一个中枢**就出现背驰，那不会是真正意义上的背驰，**只能算是盘整背驰**……而**第一类买点，多数由趋势的背驰构成**」「**第一类买点肯定是趋势背驰构成的**」 | 第27课 line 8 / line 34 |
| **盘整背驰的段结构** | 「第二、三类的买点，都有一个**三段的走势**，第三段往往都**破点第一段的极限位置**，从而形成盘整背驰，注意，这里是**把第一、三段看成两个走势类型之间的比较**」 | 第27课 line 8 |
| **背驰级别≥转折级别** | 「背驰-转折定理：某背驰的下跌意味着反向走势至少回到背驰段的中枢里」；「背驰的级别等于/小于当下走势级别」 | 第43课 |
| **小背驰-大转折（必要条件）** | 「小背驰引发大转折的必要条件是**最后一个次级别中枢的第三类买卖点**」 | 第44课 |

---

## 二、代码路径定位（从入口到背驰判定）

```
analyser.py:981  bcs = check_bi_beichi(bis, zss, closes, config)     ← 独立的背驰列表
analyser.py:931  use_seg_mmd=True 时走 seg_mmd.find_mmds_seg（默认 False）

find_mmds (mmd.py:1000)
  ├─ _find_first_type_mmds (mmd.py:2081)         ← 1买/1卖
  │    ├─ 门槛1: bi.low < ref_zs.zd             (mmd.py:2162)
  │    ├─ 门槛2: _downtrend_established (mmd.py:2169 → 2002/2028)
  │    ├─ 门槛3: trend_strength > 0             (mmd.py:2112-2113)
  │    └─ 判定:   _is_strong_beichi (mmd_conditions.py:16524)
  │              ├─ 【笔背驰分支】 16542-16580   ← 先跑，命中即 return True
  │              └─ 【趋势背驰分支】 16598-16655  ← 后跑
  ├─ _find_second_type_mmds (mmd.py:2300)        ← 2买/2卖（不用背驰）
  └─ _find_third_type_mmds  (mmd.py:3060)        ← 3买/3卖（用结构，不用背驰）
```

---

## 三、偏差清单（按严重程度排序）

### 偏差 1【高】1买/1卖 的背驰判定**先走"笔背驰"分支，且完全不要求任何中枢**

- **原文定义**：第15课 line 32：「没有趋势，没有背驰。在盘整中是无所谓'背驰'的」。第27课 line 34：「**第一类买点肯定是趋势背驰构成的**」；「如果在第一个中枢就出现背驰，那不会是真正意义上的背驰，只能算是盘整背驰」。第37课 line 8：「当说`a+A+b+B+c`中有背驰时，首先要`a+A+b+B+c`是一个趋势」。
- **代码实现**：`mmd_conditions.py:16542-16580`
  ```python
  # 1. 笔背驰检查（要求新极值：向下背驰须创新低，向上背驰须创新高）
  for j in range(bi_idx - 1, -1, -1):
      prev_bi = bis[j]
      if prev_bi.direction.value == direction:
          ...
          if curr_force < prev_force * threshold:
              return True          # ← 命中即返回，不看 zss
          break
  ```
  该分支只比较「当前笔」与「**前一同向笔**」的单笔 MACD 面积，**`zss`（中枢列表）参数在此分支内完全未被读取**。
- **偏差**：笔背驰 = 单笔对单笔的力度比较，与「中枢/趋势」无关。原文明确「在盘整中是无所谓背驰的」，而此处**零中枢、单中枢、多中枢都会输出**。
- **实测证据**（`/tmp/probe_v734_verify.py`，12 只日线 × 1200 根）：
  1buy/1sell 共 74 个，按实际生效分支归因：
  - `bi`（仅笔背驰分支命中）：**65 个 = 87.8%**
  - `trend`（仅趋势背驰分支命中）：**5 个 = 6.8%**
  - `bi+trend`（两分支都成立）：4 个 = 5.4%

  即 **近九成的 1买/1卖 来自与中枢无关的笔背驰**。
- **部分缓解（须计入结论）**：`_find_first_type_mmds` 有三道结构性门槛挡住了「无趋势」情形：
  1. `mmd.py:2112-2113` `if trend_strength <= 0: return mmds`（`_calc_trend_strength` 要求 `len(zss) >= 2` 且有同向排列，`mmd_conditions.py:16691-16706`）
  2. `mmd.py:2169` `if not _downtrend_established(zss, bi): continue`（`mmd.py:2002-2025`：要求**最近两个**中枢依次同向向下，V736 已从「任意历史对」收紧为「末尾对」）
  3. `mmd.py:2162` `if bi.low >= ref_zs.zd: continue`

  实测（`/tmp/probe_no_trend3.py`，合成单中枢形态）：`_downtrend_established` 返回 `False`，最终买卖点为空 —— 这条门槛**确实挡住了单中枢盘整**。所以「零中枢出1买」在实践中被门槛2/1 挡住。
- **但残余问题仍然严重**：门槛2只保证「此前有两个同向中枢」，**不保证候选笔本身处在该趋势的末端**，也不保证比较对象是趋势段。实测（`/tmp/probe_cmp_pair2.py`，57 个 1buy/1sell）其笔背驰比较对象的落点：
  - 落在**最后一个中枢内部**：23 个 = **40.4%**（原文：中枢内部震荡的笔不是趋势段）
  - 落在两中枢之间（b 段）：34 个 = **59.6%**
  - 落在**趋势第一个中枢之前**（原文 A 段位置）：**0 个 = 0.0%**

  即 1买 从未按第24课「A段（第一个中枢之前那一段）vs C段」来比，而是在拿中枢内/中枢间的短笔当基准。
- **严重程度**：**高**。门槛2/1 让「无趋势」情形不产出，但**候选笔与比较对象的结构位置仍系统性偏离原文**；且 87.8% 的信号走的是与趋势结构无关的分支。

---

### 偏差 2【高】`bcs` 背驰列表里的「笔背驰」没有任何趋势/中枢要求，且被直接对外暴露

- **原文定义**：同偏差 1。第15课「在盘整中是无所谓'背驰'的」。
- **代码实现**：`beichi.py:65-106`（`_check_bi_level_beichi`），由 `analyser.py:981` 的 `check_bi_beichi(bis, zss, closes)` 产出并挂在 `result.bcs` 上：
  ```python
  def _check_bi_level_beichi(bis: list[BI], closes: list[float] | None) -> list[BC]:
      # 比较相邻同向笔，后笔力度 < 前笔80% = 背驰
      for i in range(1, len(bis)):
          curr = bis[i]
          for j in range(i - 1, -1, -1):
              prev = bis[j]
              if prev.direction == curr.direction:
                  ...  # 只要求创新极值 + 力度 < 80%
                  bcs.append(BC(bc_type=BCType.BI, ...))
                  break  # 只比较最近一个同向笔
  ```
  注意函数签名**根本没有 `zss` 参数** —— 中枢信息在类型层面就被排除了。
- **偏差**：`_check_bi_level_beichi` 输出的 `BCType.BI` 背驰不满足「两段同向趋势」这一前提，但会被 GUI/API 当作"缠论背驰"直接展示。
- **实测证据**（`/tmp/probe_final_stats.py`，12 只日线）：
  - `bc_bi`（笔背驰）**142 条**
  - `bc_pz`（盘整背驰）**51 条**
  - `bc_qs`（趋势背驰）**0 条** ← 见偏差 4
  - 总计 193 条背驰中，**73.6% 是无趋势要求的笔背驰**。
- **严重程度**：**高**。这是**唯一直接以「背驰」名义对外输出的路径**，其 73.6% 的条目不满足原文的背驰前提。

---

### 偏差 3【高】背驰判定路径中**完全没有使用黄白线（DIF/DEA）回拉 0 轴**这一必要条件 — ✅ 已修（2026 二轮审计）

> **修复状态**：已实现 `_check_zero_axis_pullback(closes, prev_zs, curr_zs)`（`mmd_conditions.py:16534`），并集成进决策侧 `_is_strong_beichi` 趋势背驰分支（`16640`）与显示侧 `_check_qs_beichi`（`beichi.py:205`）。
> **判据**：中枢2（B段=curr_zs）期间 DIF 穿越 0 轴（相邻异号）或 `min|DIF| < 0.2 × 趋势|DIF|峰值`。
> **§7 证伪**：`tests/unit/test_chanlun_zero_axis_beichi.py` 4 用例；no-op（恒 True）时 `test_no_pullback_when_dif_stays_far_from_zero` FAIL（`assert True is False`），含检查时 4 PASS。合成数据验证：有回拉(反弹中枢)→True，无回拉(持续强跌)→False。
> **实测**：茅台 30min 3 个真趋势背驰 case 全过 0 轴（B 段反弹天然拉 DIF）；non-0 轴 case 被正确过滤。

- **原文定义**：第24课 line 19（正文，权威出处）：「这个中枢**一般会把MACD的黄白线（也就是DIFF和DEA）回拉到0轴附近**」；第25课 line 313/332（缠中说禅回帖，UID:[1215172700]）：「背驰需要多少个条件？光柱子缩短就背驰？**前面的黄白线有回拉0轴吗？**」「背弛首先需要的是**回拉0轴的黄白线**」。注：早期曾误引「第53课 line 139 逐字：黄白线都没拉回0轴不是背驰」，经核该句出自53课回帖区**匿名网友**（UID:[0]，非缠中说禅），此处已更正剔除。
- **代码实现（修复前）**：整条背驰判定路径只用 `calc_macd_force` 返回的三个标量：`hist_sum` / `hist_up_sum` / `hist_down_sum`（`macd.py:71`）。
  用 `inspect.getsource` 逐函数检查（`/tmp/probe_dif_zero.py`）：
  | 函数 | 是否引用 `dif` | 是否引用 `dea` |
  |---|---|---|
  | `_is_strong_beichi` (mmd_conditions.py:16524) | 否 | 否 |
  | `_get_beichi_strength` (mmd_conditions.py:16660) | 否 | 否 |
  | `_calc_bi_force` (mmd_conditions.py:16709) | 否 | 否 |
  | `_check_bi_level_beichi` (beichi.py:65) | 否 | — |
  | `_check_pz_beichi` (beichi.py:109) | 否 | — |
  | `_check_qs_beichi` (beichi.py:156) | 否 | — |
  `calc_macd_force` 返回 keys = `['hist_sum','hist_up_sum','hist_down_sum']`，**不含 dif/dea**。
- **偏差（修复前）**：原文把「黄白线回拉0轴」当作背驰的**前提性判据**（第53课给的是强判断：「黄白线都没拉回0轴**不是背驰**」）。代码只比较 MACD 柱面积/峰值，**这一条必要条件整体缺失**。
- **实测证据**（`/tmp/probe_zero_axis.py`，10 只日线的 88 个 1buy/1sell）：
  - 在候选笔起点前 60 根窗口内，DIF 确实穿越过 0 轴：79 个 = **89.8%**
  - 未穿越：9 个 = **10.2%**
  - 窗口内 DIF 距 0 轴最近值 < 0.05 的：65/88 = **73.9%**

  ⇒ 这不是「代码算出不同结论」，而是**代码根本没做这个判断**，只是日线数据恰好大部分满足。一旦换到小周期/强趋势延续段，第53课的类型错误会直接发生（因为没有判据拦它）。
- **严重程度**：**高**（判据缺失型偏差，原文给的是否定式硬条件）。
- **修复说明（诚实边界）**：0 轴检查当前只作用于**趋势背驰分支**（`_is_strong_beichi` + `_check_qs_beichi`）。笔背驰兜底分支（相邻同向笔 MACD 衰竭）未加 0 轴检查——因笔背驰是原文盘整背驰的**简化近似**（相邻笔而非 a+B+c 单中枢结构），0 轴检查对象「中枢2/B段」在笔背驰路径中无清晰对应。要彻底解决需把笔背驰重构为标准盘整背驰（a+B+c，B=单中枢），留后续会话。

---

### 偏差 4【高】趋势背驰分支的比较对象是 **b 段（中枢间连接段）**，原文要求的是 **a 段（第一个中枢之前）**；且 `_check_qs_beichi` 在真实数据上恒不产出 — ❌ 已证伪（误判，2026-10-17）

> **状态更新（2026-10-17）**：本偏差**已证伪**，代码实际**符合原文**。
> 证伪依据——原文第24课 line 24 给出具体例子：「11日11点30分到15日10点35分构成一个中枢。
> **15日10点35分到16日10点25分构成A段**。16日10点25分到17日10点10分构成新的中枢，也
> 相应构成B段…其后就是C段」。⇒ **A段 = 中枢1之后、中枢2之前的连接段**（不在中枢之前）。
> 代码 `prev_exit = _find_leaving_bi(prev_zs)` = 中枢1之后的离开段 = **A段** ✓；
> `curr_exit = _find_leaving_bi(curr_zs)` = 中枢2之后的离开段 = **C段** ✓；
> 比较 curr vs prev = **C vs A** ✓。原审计把 A 段误读为「中枢之前」（与 line24 实例矛盾），
> 进而误判代码「比 b 而非 A」。另：「恒0产出」子问题已在 0 轴检查（偏差3）修复后消除：
> 实测 sh600519 日线产出 1 条 qs 背驰（旧代码取 bis[lines[-1].index+1] 方向恒反→0），
> 现 `_find_leaving_bi` 取真正破边沿的同向离开段，不再恒0。

- **原文定义**：第24课 line 19：「用MACD判断背驰的前提是，**A、B、C段**在一个大的趋势里，其中**A之前已经有一个中枢**，而B是这个大趋势的另一个中枢……C段对应的MACD柱子面积比**A段**对应的面积要小」。⇒ A 段 = **第一个中枢之前**那一段；B = 两中枢之间；C = 第二个中枢之后。比较的是 **C vs A**。

- **代码实现**：
  - `mmd_conditions.py:16651-16654`（`_is_strong_beichi` 趋势分支）：
    ```python
    prev_exit = bis[prev_exit_idx]   # _find_leaving_bi(prev_zs) = 第一个中枢之后的离开段
    curr_exit = bis[curr_exit_idx]   # 第二个中枢之后的离开段
    ...
    if new_extreme and curr_force < prev_force * threshold and curr_force > 0:
    ```
    ⇒ 比的是 **b 段 vs c 段**。
  - `beichi.py:182-206`（`_check_qs_beichi`）同样取 `bis[prev_zs.lines[-1].index + 1]`：
    ```python
    prev_exit = bis[prev_zs.lines[-1].index + 1]   # 第一个中枢之后那一笔
    curr_exit = bis[curr_zs.lines[-1].index + 1]   # 第二个中枢之后那一笔
    ```
    同样缺 **a 段**。
- **偏差**：原文的 A 段在第一个中枢**之前**；代码的 `prev_exit` 在第一个中枢**之后**。少了 a 段这一参照，等于把「趋势背驰」降级成「b/c 两段比较」。
- **实测证据 1（漏斗，`/tmp/probe_qs_funnel.py` + `/tmp/probe_qs_recheck.py`，10 只日线）**：
  `_check_qs_beichi` 的逐门槛流失：
  | 门槛 | 通过数 |
  |---|---|
  | 相邻中枢对 | 114 |
  | 依次同向 | 106 |
  | 两个「离开笔」可定位 | 98 |
  | **两离开笔方向都与趋势一致** | **2** |
  | 创新极值 | 0 |
  | 力度 < 80% | 0 |

  根因：`bis[zs.lines[-1].index + 1]` 取的是中枢末笔的**下一笔**，而笔方向天然交替 —— 实测 116 个中枢中 **116 个**的 `exit_bi.index == lines[-1].index + 1`（`/tmp/probe_exit_bi.py`），且中枢末笔方向 → 下一笔方向 100% 反向（`/tmp/probe_last_line_dir.py`：`down→up` 66 个、`up→down` 50 个，**同向 0 个**）。所以只要 `is_down_trend` 时末笔是 up（即离开段该是 down），`prev_exit.direction != Direction.DOWN` 恒真 → `continue`。
- **实测证据 2（产出为零）**：`/tmp/probe_bc_types.py`，10 只日线：
  - `bcs` 类型统计：`{'bi': 117, 'pz': 42, 'qs': 0}`
  - 直接调用 `beichi._check_qs_beichi(bis, zss, closes)`：产出 **0 条**

  ⇒ **趋势背驰这条路径在真实数据上一次都没成功过**，对外背驰列表里的"趋势背驰"是空的。
- **对比**：`mmd_conditions.py:16598-16655` 的趋势分支用了 `_find_leaving_bi`（`mmd_conditions.py:16496`）修正了取法，实测 `_find_leaving_bi` 返回笔方向 == direction 的比例是 **231/231 = 100%**（`/tmp/probe_zs_dir.py`）。所以 `mmd_conditions` 侧的分支是可触发的（漏斗：`same 106 → leaving_ok 98 → dir_ok 98 → new_ext 45 → force<80% 9`，`/tmp/probe_trend_loose.py`），其中 6/9 真的锚定到了 1buy/1sell（`/tmp/probe_trend_anchor.py`）。**但 `beichi.py` 的对应函数没有同步这个修正** —— 同一套语义在两处不一致。
- **严重程度**：**高**。一是比较对象错位（b vs a），二是 `beichi.py` 的趋势背驰路径**完全失效**（0 产出），而它正是对外展示"趋势背驰"的唯一来源。

---

### 偏差 5【中】「趋势背驰」要求 `c` 是**次级别走势类型**，代码用的是**单根笔**

- **原文定义**：第37课 line 10：「`c`必然是**次级别的**，也就是说，`c`**至少包含对`B`的一个第三类买卖点**，否则就可以看成是`B`中枢的小级别波动，完全可以用盘整背驰来处理。」
- **代码实现**：`mmd_conditions.py:16645-16654` 与 `beichi.py:195-206`，`curr_exit` / `curr_force` 都是**单根 `BI` 对象**（`_calc_bi_force(bi, ...)` 只算一根笔的 MACD 面积）。
- **偏差**：单根笔 ≠ 次级别走势类型。原文明确说「`c` 至少包含对 B 的一个第三类买卖点」，单笔不可能包含任何买卖点。
- **实测证据**：
  1. 尺度（`/tmp/probe_1buy_scale.py`，10 只日线）：1buy/1sell 笔跨度 median **13 根**（min 5 / max 32）；同期中枢跨度 median **81 根**（min 25 / max 179）。1buy 笔 / 最后中枢跨度比值 median **0.16**（`/tmp/probe_1buy_bi_pos.py`，60 个样本，min 0.05 / max 0.48）⇒ 背驰"段"平均只有中枢的 1/6，不可能是含中枢的次级别走势类型。
  2. 含三买/三卖比例（`/tmp/probe_37_c_contains_b3.py`）：60 个 1buy/1sell 中，其背驰笔内**同时含 3买/3卖的数量 = 0 = 0.0%**。
- **严重程度**：**中**。级别不匹配会系统性低估背驰段力度（小段的 MACD 面积天然小于大段），是偏差 1 中「笔背驰」容易触发的物理原因之一。

---

### 偏差 6【中】盘整背驰的「进入段/离开段」被取成**单笔**，且不要求「第三段破第一段极限位置」

- **原文定义**：第27课 line 8：「第二、三类的买点，都有一个**三段的走势**，第三段往往都**破点第一段的极限位置**，从而形成盘整背驰，注意，这里是**把第一、三段看成两个走势类型之间的比较**」。
- **代码实现**：`beichi.py:123-137`
  ```python
  first = zs.lines[0]
  last  = zs.lines[-1]
  enter  = bis[first.index - 1]   # 进入笔（单笔）
  exit_  = bis[last.index + 1]    # 离开笔（单笔）
  if enter.direction != exit_.direction:
      continue
  ...
  if enter_force > 0 and exit_force < enter_force * 0.8 and exit_force > 0:
      bcs.append(BC(bc_type=BCType.PZ, ...))
  ```
- **偏差**：
  1. 把「走势类型」降成「单笔」（结构近似，同偏差 5）；
  2. **不要求 `exit_` 突破 `enter` 的极限位置**（原文「第三段往往都破点第一段的极限位置」）。
- **实测证据**（`/tmp/probe_pz_extreme.py`，10 只日线的 42 个盘整背驰命中）：
  - 其中 C 段（离开笔）真的破了 A 段（进入笔）极限位置的：**8 个 = 19.0%**
  - 未破极限位置却仍判为盘整背驰：**34 个 = 81.0%**

  即八成盘整背驰不满足原文的形态描述。
- **附带实测（无差异，不计入偏差）**：`enter` 取 `first.index-1`（单笔）与「first 之前所有连续同向笔合并」的力度差异极小（0/75 超过 1.5 倍，`/tmp/probe_pz_std.py`）⇒ 这一条**单笔 vs 走势段**的简化在实测中无害，不必单独报。
- **严重程度**：**中**（81% 的命中缺原文形态要件）。

---

### 偏差 7【中】`_calc_bi_force` 的 MACD 面积口径只取单侧柱子，实测 76.2% 的笔被系统性削减；10.7% 的笔力度为 0

- **原文定义**：第24课 line 19：「C段的走势类型完成时对应的 **MACD柱子面积**（**向上的看红柱子，向下看绿柱子**）比A段对应的面积要小」。原文口径确实是单侧（向上看红柱、向下看绿柱），代码方向一致。
- **代码实现**：`macd.py:71`（`calc_macd_force`）→ `hist_up_sum = sum(h for h>0)`、`hist_down_sum = abs(sum(h for h<0))`；由 `mmd_conditions.py:16746-16750` 按笔方向取其中一侧。
- **偏差**：原文「向下看绿柱子」指的是**该下跌段整体对应绿柱**；代码在**任意单根笔的窗口内**只累绿柱、丢弃红柱。当一根下跌笔内部 MACD 已翻红（震荡/衰竭末段常见），力度被大幅削减，制造出虚假的"力度衰减"。
- **实测证据**：
  1. `_calc_bi_force` 的降级路径与正常路径（MACD 面积 vs 振幅）不同量纲，代码注释自证「实测两路径数值比中位 3.2 倍（范围 1.0~12.0）」（`mmd_conditions.py:16727-16733`）。实测（`/tmp/probe_force_degrade.py`，825 笔）正常链路全部走 MACD 路径（`out_of_range=0`、`macd_err=0`）⇒ **当前不混用，风险可控**。
  2. 笔内红绿混合比例（`/tmp/probe_macd_hist_sign.py`，512 笔）：**390 笔 = 76.2%** 的笔内 MACD 柱红绿混合 ⇒ 单侧口径在这些笔上丢弃了另一侧的全部面积。
     典型（`/tmp/probe_hist_abs_sum.py`）：
     - `sh000001 bi2 up 20根`：红柱 152.15 / 绿柱 -114.34 / 绝对值和 266.49 ⇒ 代码力度 152.15（丢弃 43%）
     - `sh300 bi7 down 19根`：红柱 114.21 / 绿柱 -448.55 ⇒ 代码力度 448.55
     - `sh300 bi1 down 6根`：红柱 165.39 / 绿柱 -8.42 ⇒ 代码力度 **8.42**（笔实际振幅对应的动能几乎全被判为 0）
  3. 力度为 0 的笔（`/tmp/probe_zero_force.py`，825 笔）：**88 笔 = 10.7%** 力度 ≤ 0（up 40 / down 48）。这类笔在 `_is_strong_beichi` 中会 `break`/`continue`（16564-16576），在 `_check_bi_level_beichi` 中因 `curr_force > 0` 被排除。
- **严重程度**：**中**。方向与原文一致（单侧），但**窗口粒度错**（笔内 vs 走势段内）导致系统性低估，是偏差 1 的助推因素。

---

### 偏差 8【中】`_calc_macd_histogram_divergence_v61` / `_calc_zhongshu_divergence_strength_v67` 用固定 K 线根数窗口，与笔/段/中枢结构无关

- **原文定义**：第24课要求 A/B/C 是**走势段**（由中枢结构界定），不是固定根数的窗口。
- **代码实现**：
  - `mmd_conditions.py:6933`（`_calc_macd_histogram_divergence_v61`）：固定 20 根窗口
  - `mmd_conditions.py:8747`（`_calc_zhongshu_divergence_strength_v67`）：固定 last-10 / last-20 根
  - 二者只在 `_calc_confidence_v47` / `_calc_confidence` 中用于 **3买/3卖置信度加权**，不影响信号有无。
- **偏差**：用「最近 N 根 K 线」近似「中枢前后的走势段」，窗口边界与结构边界无对应关系；且只作用于 3买/3卖置信度（3买/3卖原文本就是结构定义、不用背驰）。
- **实测证据**：未单独量化（不改变信号集合，仅改 confidence 小数）。经 `find_mmds` → `_calc_confidence_v47`（`mmd.py:1076-1078`）确认只写 `mmd.confidence`。
- **严重程度**：**低~中**（只影响排序/展示数值，不影响背驰判定本身；但会误导用户对"MACD 确认度"的理解）。

---

### 偏差 9【低】`seg_mmd.py` 读的配置键 `divergence_rate` 不存在，`seg_divergence_rate=1.5` 形同虚设

- **原文定义**：无直接对应（工程阈值）。但与背驰判定相关，因为 1.5 若生效则**完全不要求力度衰减**。
- **代码实现**：
  - `seg_mmd.py:179`：`divergence_rate = getattr(config, "divergence_rate", 0.8)`
  - `config.py:274`：`seg_divergence_rate: float = 1.5`（键名带 `seg_` 前缀）
- **偏差**：`ChanlunConfig` 无 `divergence_rate` 字段 ⇒ `getattr` 恒取默认 **0.8**，用户配的 1.5 被静默忽略。
- **实测证据**（`/tmp/probe_seg_rate.py`）：
  ```
  config.seg_divergence_rate = 1.5
  config 有 divergence_rate 属性?  False
  getattr(c,'divergence_rate', 0.8) = 0.8
  'divergence_rate' in config fields: False
  'seg_divergence_rate' in config fields: True
  ```
  另有 8 处脚本/策略显式传 `seg_divergence_rate=1.5`（`scripts/final_verification.py`、`scripts/optimize_round2.py` 等）—— 全部无效。
- **影响面**：仅 `use_seg_mmd=True` 时生效，而 `config.py:270` `use_seg_mmd: bool = False`（默认关闭），默认路径不受影响。
- **严重程度**：**低**（默认关闭 + 默认值 0.8 恰好更接近原文的"力度衰减"，但属"配置项形同虚设"类欺骗性问题，与 V734 §3 修掉的同类问题同型）。

---

### 偏差 10【低】`seg_mmd._detect_t1` 的 T1「趋势背驰」只比较**最后一个中枢**的 enter/exit，且默认用 MACD 峰值而非面积

- **原文定义**：第24课要求 A/B/C 三段 + B 中枢把黄白线回拉 0 轴 + C 的**柱子面积** < A 的面积。趋势 = 至少两个同向中枢（第17课）。
- **代码实现**：`seg_mmd.py:216-238`
  ```python
  last_zs = multi_bi_zss[-1]         # 只取最后一个中枢
  enter_bi = last_zs.enter_bi
  exit_bi  = last_zs.exit_bi
  if macd_algo == "area":
      in_metric  = _macd_area(macd_data, enter_ks, enter_ke)
      out_metric = _macd_area(macd_data, exit_ks, exit_ke)
  else:  # peak
      in_metric  = _macd_peak(...)
      out_metric = _macd_peak(...)
  is_diver = out_metric <= divergence_rate * (in_metric + 1e-7)
  ```
  配合 `config.py:276` `seg_min_zs_cnt: int = 1`（**允许只有 1 个中枢**就算"趋势背驰"）与 `config.py:296` `seg_macd_algo: str = "peak"`（默认峰值）。
- **偏差**：
  1. 单中枢即触发"T1 趋势背驰"（原文：第一个中枢的背驰只能是盘整背驰，第27课 line 8）；
     **✅ V857 已修**：seg_mmd.py `_detect_t1` 改为要求 `len(multi_bi_zss) >= 2`（第28课 L587 趋势=≥2中枢）；
     1 中枢走 T1P 盘整背驰分支（enter/exit 比较，与 T1 同口径区别仅中枢数=1）。
  2. 默认 `peak`（峰值）而非原文的「柱子面积」（第24课 line 19）；
  3. 无黄白线 0 轴检查（同偏差 3）。
- **实测证据**：`config.py:270` `use_seg_mmd: bool = False` ⇒ 默认路径不触发，仅用户显式开启后才生效。
- **严重程度**：**低**（默认关闭；开启后为高，因为同时踩中"单中枢算趋势"与"峰值代替面积"两条）。

---

## 四、实测数据总表

| 指标 | 数值 | 脚本 |
|---|---|---|
| 1buy/1sell 分支归因（12 只日线） | 笔背驰 65 / 趋势背驰 5 / 两者 4（共 74） | `/tmp/probe_v734_verify.py` |
| 1buy/1sell 比较对象落点（57 个） | 最后中枢内 40.4% / 中枢间 59.6% / **A 段位置 0.0%** | `/tmp/probe_cmp_pair2.py` |
| `bcs` 类型分布（12 只日线） | bi 142 / pz 51 / **qs 0** | `/tmp/probe_final_stats.py` |
| `_check_qs_beichi` 直接调用产出（10 只） | **0 条** | `/tmp/probe_bc_types.py` |
| `_check_qs_beichi` 方向门槛流失 | 106 → 98 → **2** → 0 → 0 | `/tmp/probe_qs_funnel.py` |
| 中枢末笔 → 下一笔方向 | `down→up` 66 / `up→down` 50 / **同向 0** | `/tmp/probe_last_line_dir.py` |
| `exit_bi.index == lines[-1].index+1` | 116/116 = 100% | `/tmp/probe_exit_bi.py` |
| `_find_leaving_bi` 方向正确率 | 231/231 = 100% | `/tmp/probe_zs_dir.py` |
| 趋势分支漏斗（106 个同向中枢对） | new_ext 45 → force<80% **9** → 锚定到 1buy/1sell **6** | `/tmp/probe_trend_loose.py`、`probe_trend_anchor.py` |
| 合成单中枢（盘整）形态 | `_downtrend_established=False`，买卖点为空 | `/tmp/probe_no_trend3.py` |
| 合成教科书 a+A+b+B+c | 1buy 未在 c 段产生（在 bi6 误发） | `/tmp/probe_no_trend4.py` |
| 1buy 笔跨度 / 中枢跨度 | median 13 / 81 根，比值 median 0.16 | `/tmp/probe_1buy_scale.py`、`probe_1buy_bi_pos.py` |
| 1buy 笔内含 3买/3卖 | **0/60 = 0.0%** | `/tmp/probe_37_c_contains_b3.py` |
| 盘整背驰缺「破极限位置」 | 34/42 = **81.0%** 未破 | `/tmp/probe_pz_extreme.py` |
| 笔内 MACD 红绿混合 | 390/512 = **76.2%** | `/tmp/probe_macd_hist_sign.py` |
| 力度为 0 的笔 | 88/825 = **10.7%** | `/tmp/probe_zero_force.py` |
| DIF 窗口内穿越 0 轴（88 个 1buy/1sell） | 79 = 89.8%（代码**未做此判断**） | `/tmp/probe_zero_axis.py` |
| 背驰函数引用 dif/dea | **全部为否**（6/6） | `/tmp/probe_dif_zero.py` |
| `seg_divergence_rate` 是否被读 | **否**（恒取 0.8） | `/tmp/probe_seg_rate.py` |
| 默认配置 `use_seg_mmd` | **False** | `/tmp/probe_seg_active.py` |
| 严格口径（短路笔背驰分支）信号量（6 只） | 1buy 共 4 个（vs 当前口径 30 个量级） | `/tmp/probe_strict_trend.py` |

---

## 五、对已有审计文档的修正与补充

1. **`mmd_conditions.py:16582-16593` 的注释已过期**。该注释称「当前的 1buy/1卖 **100% 来自笔背驰**」并引用 V734 的收益对照。V734 已在 `docs/CHANLUN_FIDELITY_AUDIT_V734.md` 顶部自我作废（判据来自代码注释转述、无原文；用收益否决原文硬性要求属逻辑倒置）。实测现状也不是 100%：12 只日线下笔背驰占 87.8%（65/74），趋势分支占 6.8%（5/74），另有 4 个两分支都成立。**结论应更新为"近九成"而非"100%"**。
2. **V735 逐条符合性总表中「第27课 1买=趋势背驰 ✅」需要降级**。该行只验证了「趋势门槛存在」（`_downtrend_established`），未验证「背驰比较本身是趋势段 vs 趋势段」。实测比较对象 0% 落在 A 段位置（见偏差 1），因此该条应标 ⚠ 而非 ✅。
3. **V735 表中「第53课 2买=不创新低或盘整背驰 ✅(非问题)」只覆盖了 2买**。0 轴回拉判据（权威出处**第24课 line 19 正文**「B 中枢一般会把黄白线回拉 0 轴附近」+ 缠师回帖第25课 line 313/332「背弛首先需要的是回拉0轴的黄白线」）是**对背驰本身**的否定式判据，在 1买/1卖/bcs 三条路径上原均未实现（见偏差 3），V735 未覆盖。注：此处不再引用「第53课 line 139」——经核该句出自53课回帖区匿名网友（UID:[0]），非缠中说禅原文。
4. **V734 §4 的"收益持平 ⇒ 不改 1买"结论不应作为本次审计的既定事实**。V734 已自认逻辑倒置（"符合原文是判据，收益是结果，不能反过来"），且 V735 §2 修掉 `_find_leaving_bi` 后，1买 结构已变（趋势分支从"恒不触发"变为可触发）。**收益对照需要在当前代码上重跑**（本次未跑，见第六节）。

---

## 六、读过的函数 / 跳过的内容

### 已读（核心决策路径）
| 文件 | 函数 | 行号 |
|---|---|---|
| `mmd.py` | `find_mmds` | 1000 |
| `mmd.py` | `_find_first_type_mmds` | 2081 |
| `mmd.py` | `_downtrend_established` / `_uptrend_established` | 2002 / 2028 |
| `mmd.py` | `_reference_zs_for_bi` | 2042 |
| `mmd_conditions.py` | `_is_strong_beichi` | 16524 |
| `mmd_conditions.py` | `_get_beichi_strength` | 16660 |
| `mmd_conditions.py` | `_calc_bi_force` | 16709 |
| `mmd_conditions.py` | `_find_leaving_bi` | 16496 |
| `mmd_conditions.py` | `_calc_trend_strength` | 16691 |
| `beichi.py` | `check_bi_beichi` | 18 |
| `beichi.py` | `_check_bi_level_beichi` | 65 |
| `beichi.py` | `_check_pz_beichi` | 109 |
| `beichi.py` | `_check_qs_beichi` | 156 |
| `macd.py` | `calc_macd` / `calc_macd_force` | 12 / 71 |
| `seg_mmd.py` | `_detect_t1`（T1/T1P） | 160 |
| `seg_mmd.py` | `_map_zs_to_seg` / `find_mmds_seg` | 82 / 589 |
| `config.py` | 相关开关与阈值字段 | 160/214/267-296/323-345 |
| `analyser.py` | `check_bi_beichi` 调用点 / seg_mmd 分支 | 981 / 931-950 |

### 已读（次要，用于排除嫌疑）
`_calc_macd_histogram_divergence_v61`(6933)、`_calc_zhongshu_divergence_strength_v67`(8747)、`_calc_confidence_v47`(15718)、`_calc_confidence`(14288)、`_calc_macd_histogram_area`(21180)、`_check_macd_confirmation`(16419)、`_calc_trend_strength_weighting_v48`(13493)、`_calc_trend_strength_composite_v51`(13849)、`_calc_mmd_quality`(16820)、`_calc_breakout_force_ratio`(16802)。

### 已跳过（不影响背驰判定结论）
| 内容 | 跳过理由 |
|---|---|
| `_find_second_type_mmds` 内部（mmd.py:2300） | 2买/2卖原文由结构定义（1买后回调不创新低），不经背驰；V735 已单独审过其窗口口径 |
| `_find_third_type_mmds` / `_find_third_type_mmds_original` 内部（3060/2814） | 3买/3卖原文是纯结构定义，MACD 仅作置信度加权（已由偏差 8 覆盖其影响面） |
| `mmd_conditions.py` 中约 250 个 `_calc_*_vNN` 条件函数 | 只调 `mmd.confidence` 小数，不改变信号有无/背驰真值 |
| `find_zss` / `same_level.py` 中枢构造细节 | 已有独立审计（`docs/CHANLUN_FIDELITY_AUDIT_108LESSONS.md` 偏差 1/2 覆盖 GG/DD 与笔极值）；本报告只在 `zs.exit_bi`/`zs.enter_bi` 语义层面使用它们 |
| `zs.py` 的 `zs_no_hard_close`（9 段升级） | 属中枢延伸规则，非背驰路径；V735 已审 |
| 收益/PnL 回测对照 | **本次未跑**。V734/V735 的收益数字均已过期，重跑需要 `scripts/audit_chanlun_beichi_pnl.py` 在 288 只上跑（本机 4 核，`--workers 2`，约需数十分钟），且用户要求只读审计 —— 是否重跑由用户决定 |

---

## 七、结论速览

| # | 项 | 是否符合原文 | 严重程度 |
|---|---|---|---|
| 1 | 1买/1卖 背驰判定先走"笔背驰"分支（无中枢要求），实测占 87.8% | ❌ 不符合（有趋势门槛部分缓解） | **高** |
| 2 | `bcs` 的 `BCType.BI` 笔背驰无趋势要求，占对外背驰列表 73.6% | ❌ 不符合 | **高** |
| 3 | 背驰路径完全不用黄白线（DIF/DEA）回拉 0 轴 | ❌ 不符合（第53课否定式硬条件缺失） | **高** |
| 4 | 趋势背驰比较对象是 b 段而非 a 段；`beichi._check_qs_beichi` 真实数据 0 产出 | ❌ 不符合 | **高** |
| 5 | 趋势背驰的 `c` 用单笔，不满足"次级别走势类型"（0/60 含三买卖点） | ❌ 不符合 | **中** |
| 6 | 盘整背驰用单笔比较，且 81% 不要求"第三段破第一段极限" | ⚠ 部分符合 | **中** |
| 7 | MACD 面积口径单侧正确但窗口粒度错（76.2% 笔红绿混合；10.7% 力度为 0） | ⚠ 近似 | **中** |
| 8 | v61/v67 用固定根数窗口近似走势段，只影响 3买/3卖置信度 | ⚠ 近似 | **低~中** |
| 9 | `seg_divergence_rate=1.5` 配置项形同虚设（键名不匹配，恒取 0.8） | ⚠ 工程缺陷 | **低** |
| 10 | `seg_mmd` T1 默认单中枢即算趋势背驰、默认峰值代替面积 | ⚠ 默认关闭 | **低** |

**一句话总结**：背驰判定的**必要条件链条在代码中是不完整的** —— "两段同向趋势"在 `_find_first_type_mmds` 有趋势门槛（应计入），但**背驰比较本身**（`_is_strong_beichi` 笔分支 / `beichi.py` 三个 check）几乎不用中枢结构；"黄白线回拉 0 轴"在全部 6 个背驰相关函数中一次都没实现；趋势背驰与盘整背驰虽有 `BCType` 区分，但趋势背驰路径在真实数据上产出为 0，比较对象也取错了段。

---

## 附录 A：验证脚本清单（均在 `/tmp/`，未写入仓库）

| 脚本 | 用途 |
|---|---|
| `probe_v734_verify.py` | 1buy/1sell 分支归因（bi/trend/bi+trend） |
| `probe_beichi_attr.py` | 同上，10 只样本版本 |
| `probe_cmp_pair2.py` | 比较对象在趋势中的落点分类 |
| `probe_ref_zs_mismatch.py` | ref_zs 与比较对象所在中枢一致性 |
| `probe_bc_types.py` | `bcs` 类型分布 + `_check_qs_beichi` 直接产出 |
| `probe_qs_funnel.py` / `probe_qs_recheck.py` | `_check_qs_beichi` 逐门槛漏斗 |
| `probe_zs_dir.py` | `_find_leaving_bi` 方向正确率 |
| `probe_exit_bi.py` | `exit_bi.index == lines[-1].index+1` 验证 |
| `probe_last_line_dir.py` | 中枢末笔 → 下一笔方向 |
| `probe_trend_loose.py` / `probe_trend_anchor.py` | 趋势分支漏斗 + 锚定命中 |
| `probe_no_trend2.py` / `probe_no_trend3.py` / `probe_no_trend4.py` | 合成形态（单中枢 / 双中枢 / 教科书 a+A+b+B+c） |
| `probe_std_fail.py` | 教科书标准形态下 c 段背驰 |
| `probe_1buy_scale.py` / `probe_1buy_bi_pos.py` | 1buy 笔跨度 vs 中枢跨度 |
| `probe_37_c_contains_b3.py` | c 段是否含 B 的三买卖点 |
| `probe_pz_leaving.py` / `probe_pz_std.py` / `probe_pz_extreme.py` | 盘整背驰结构三探针 |
| `probe_a_seg.py` / `probe_a_seg2.py` | a 段 vs b 段比较口径差异 |
| `probe_macd_hist_sign.py` / `probe_hist_abs_sum.py` | MACD 柱红绿混合与力度削减 |
| `probe_zero_force.py` / `probe_force_degrade.py` | 零力度笔比例 / 降级路径触发 |
| `probe_zero_axis.py` / `probe_dif_zero.py` | 黄白线 0 轴：代码未判 + 数据侧现状 |
| `probe_seg_rate.py` / `probe_seg_active.py` | seg_mmd 配置键与默认开关 |
| `probe_strict_trend.py` / `probe_strict_pnl.py` | 严格口径（短路笔背驰）信号量对照 |
| `probe_final_stats.py` | 12 只日线汇总统计 |
| `probe_bc_vs_mmd.py` / `probe_1buy_bc_kind.py` | 背驰与买卖点一致性 |
