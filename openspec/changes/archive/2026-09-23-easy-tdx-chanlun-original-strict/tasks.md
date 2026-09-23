# 任务（Tasks）— 缠论原文口径收敛

## Phase 1: OpenSpec 建模（本文档）
- [x] 1.1 proposal.md
- [x] 1.2 specs/line-segment-original-fidelity/spec.md
- [x] 1.3 specs/bi-pohuai-default-on/spec.md
- [x] 1.4 specs/bi-type-convergence/spec.md
- [x] 1.5 tasks.md

## Phase 2: 编码与金标
- [x] 2.0 现有全量测试回归基线（记录当前 pass 数）——基线 3605 passed / 6 skipped（V723 后复跑）
- [x] 2.1 line-segment：多义性「最早确认」已落地（XD_TIEBREAK_EARLIEST，V602）；V725 补齐「收尾不换取端点」——收尾终点取最后已完成同向笔端点，取消 max/min 换点（金标同步受控更新，mypy/ruff 通过）
- [x] 2.2 bi-pohuai：config.xd_bi_pohuai 已默认 True（历史轮次完成）；test_chanlun_xd_pohuai 锁定开/关差异
- [x] 2.3 bi-type：默认 new，simple 标注 legacy（config.py docstring + find_bis 告警 + test_chanlun_config 锁定默认值）
- [x] 2.4 金标回归：test_chanlun_golden_samples 收尾端点 15.0→13.0（受控更新，理由见测试注释）
- [x] 2.5 门禁：ruff 0 / mypy 0 / pytest 全量 3606 passed + 6 skipped / 前端 vue-tsc -b + vite build + vitest 87 passed（+1 simple legacy 告警测试，AuditView TS7053 build 错误一并修复）

## Phase 3: 提交
- [x] 3.1 提交本 change（V726 归档）
