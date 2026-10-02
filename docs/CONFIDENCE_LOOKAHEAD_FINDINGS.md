# 买卖点置信度的前视（point-in-time）问题

> 结论基于**实测**，不是代码阅读推断。发现于 V731 审计第 15–16 轮。

## 1. 现象

历史买卖点的**置信度会随着"后面又来新数据"而变化**。同一个位置的信号，
今天算出来是一个分，明天数据多了变成另一个分。

实测（确定性波动序列，无随机，两次运行可比）：

    signalsample: 1buy idx=52
      截断到 400 根 → confidence = 0.3350
      全长 500 根   → confidence = 0.3330

固定 mmd 对象后逐个信号的偏差：

    1buy  idx= 52   Δ-0.0020
    1buy  idx=126   Δ-0.0030
    1sell idx=230   Δ+0.0000
    2buy  idx= 91   Δ-0.0030
    3buy  idx=220   Δ-0.0070

## 2. 为什么这是缺陷

POINT-IN-TIME 是 F8/F9（历史时点选股与回测）可信度的生命线，也影响 F3
（训练数据）的可复现性：

- **回测**：策略按 `min_confidence` 过滤信号。若历史信号的置信度里掺了它
  之后的信息，等于用未来数据选股 → **回测收益被高估**。
- **训练数据 F3**：同一份数据今天导出和明天导出不一致 → 不可复现。
- **UI**：用户看历史信号，评分会随时间漂移，难以解释。

## 3. 已修：最大单一来源

`_check_post_signal_price_follow_through`（V47 条件131「后确认」）原实现：

    latest_close = closes[-1]                        # 序列最后一根 = "现在"
    actual_lookback = min(lookback_bars, signal_idx) # 信号**之前**的索引

对历史信号而言 `closes[-1]` 包含它之后直到"现在"的全部数据。实测同一信号：

    到 55 根 → adjust=+0.04「后确认通过」
    到 80 根 → adjust=-0.05「后确认失败」
    到 200 根 → adjust=-0.05

同一个信号"今天看好、明天看差"。另外 `actual_lookback` 取的是信号之前的索引，
msg 却写"信号后 N 根 K 线"（msg 撒谎），且成功路径漏写 `looked_bars`（恒为 0）。

**修复**：窗口固定为信号之后最多 `lookback_bars` 根并截断；数据不足返回
neutral；`looked_bars` 给真实根数。回归测试见
`tests/unit/test_mmd_conditions_post_signal_lookahead.py`（16 条，旧代码 8 条失败）。

## 4. 未修：系统性残留（诚实标注）

上述修复只处理了**一个**函数。扫描发现这不是孤例。

由 `scripts/verify_confidence_lookahead_candidates.py` 实测：
`mmd_conditions.py` 里有 **101 个**「形参含 mmd 且函数体内引用最新 bar
（`closes[-1]` / `len(closes)-1`）」的函数，其中 **81 个**在「截断序列 vs
加长序列」上返回值不同。

不过要注意区分（这是本问题的难点）：

- 其中大部分**没有接进** `_calc_confidence` / `_calc_mmd_quality`，是未接线的
  助手函数（这也是"数量多"却影响有限的原因）；
- 真正接线的（14 个左右）里，实测仍有残留偏差 ~0.007。

残留源头尚未逐个定位（候选与若干引用最新 bar 的助手函数、以及
expanding-window 指标有关）。

## 5. 已建立的守卫（防止回潮）

- `scripts/verify_confidence_pit_stability.py`
  全 pipeline 探针：截断 vs 全长，比较深历史信号置信度。**注意它的局限**——
  它会把"新数据导致 笔/中枢 结构本身重算"的合法效应与前视混在一起，
  所以它报警不代表一定是前视。
- `scripts/verify_confidence_lookahead_candidates.py`
  逐个函数调用，定位哪些助手对数据长度敏感。
- `tests/unit/test_chanlun_confidence_pit_stability.py`（推荐）
  **固定同一个 mmd 对象**分别喂截断/全长数组，隔离掉结构重算的影响，
  只允许 ≤ `MAX_DRIFT`(0.01) 的已知残留。已验证：在 round-15 修复前的代码上
  **会失败**（drift 0.0870 > 0.01），修复后通过 —— 守卫有效。

> ⚠️ 排查教训：第一次验证守卫有效性时，我用 `git stash push <path>` 想回到旧
> 代码，但那个文件当时已提交干净、没有本地改动，stash 什么也没存，测试实际跑
> 在**已修复的代码上，于是"通过"给了我假信心。后来改用
> `git show <commit>:<path>` 取出确凿的旧版本才测出真结果。**stash 无效时一定
> 要先确认文件内容真的变了。**

## 6. 建议后续

若要彻底消除残留，应逐个检查接线的 14 个助手，把"当前状态"类输入（MA/RSI/ADX/
BOLL 等）改为**截至信号 bar** 计算，而不是用整段序列。这是较大改动，应单独排期。
