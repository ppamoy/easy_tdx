# 缠论原文口径收敛（easy-tdx-chanlun-original-strict）

## 动机（Motivation）
审计结论（docs/CAPABILITY_AUDIT.md）指出：当前缠论结构判定仍是简化版，未达到「严格原文、非简化」的口径。具体差距：
1. 线段划分未实现缠论原文的多义性确定性选择（第一特征/第二特征序列）。
2. 笔破坏（xd_bi_pohuai）存在但默认关闭，需默认开启并校准既有金标。
3. 笔类型含 simple 简化口径，需收敛/显式标注，保证模型口径唯一且贴近原文。

本 change 按「先建模（OpenSpec）再编码」推进，逐项带金标与门禁。

## 现状盘点（Audit）
- src/easy_tdx/chanlun/xd.py — 特征序列+包含处理，自述为简化实现；未覆盖笔破坏与多义性全部情形；笔破坏为可选开关（默认 False）。
- src/easy_tdx/chanlun/config.py — 已有 xd_bi_pohuai、bi_type（new/old/simple）。
- 既有金标：tests/unit/test_chanlun_real_golden_multi.py、test_chanlun_geometry.py、test_chanlun_xd_pohuai.py、test_chanlun_golden_samples.py 等。

## 目标形态（Target）
- 线段划分：实现「确定性、严格原文」的结束判定（含第一/第二特征序列与笔破坏统一取舍），默认采用原文口径。
- 笔破坏：xd_bi_pohuai 默认 True，并校准既有金标（允许在受控前提下更新快照）。
- 笔类型：bi_type 收敛为 new（原文新笔）/old 二态，simple 标记为 legacy，仅显式开启，不作为默认。

## 能力域概述（Spec Overview）
1. line-segment-original-fidelity — 线段多义性确定性选择（第一/第二特征序列）。
2. bi-pohuai-default-on — 笔破坏默认开启并按金标校准。
3. bi-type-convergence — 笔类型口径收敛（simple 显式 legacy）。

## 成功标准（Success Criteria）
- 三张 spec 全部 Requirement 的 Scenario 由金标覆盖并通过。
- 全量门禁（pytest/ruff/mypy/前端 build+vitest）通过。
- 既有历史快照在受控更新后仍保持确定性（同输入同输出）。
