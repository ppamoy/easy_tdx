# 任务（Tasks）— 缠论原文口径收敛

## Phase 1: OpenSpec 建模（本文档）
- [x] 1.1 proposal.md
- [x] 1.2 specs/line-segment-original-fidelity/spec.md
- [x] 1.3 specs/bi-pohuai-default-on/spec.md
- [x] 1.4 specs/bi-type-convergence/spec.md
- [x] 1.5 tasks.md

## Phase 2: 编码与金标
- [ ] 2.0 现有全量测试回归基线（记录当前 pass 数）
- [ ] 2.1 line-segment：find_xds 收尾/多义性统一为「最早确认」确定性规则，端点共享、方向一致；新增原文金标
- [ ] 2.2 bi-pohuai：config.xd_bi_pohuai 改为默认 True，逐项校准受影响金标（记录 affected files）
- [ ] 2.3 bi-type：默认 new，simple 标注 legacy（config.to_dict / docstring / find_bis 注明）；默认规则测试不依赖 simple
- [ ] 2.4 金标回归：更新既有快照（受控），确保 tests/unit 全绿
- [ ] 2.5 门禁：ruff/mypy/pytest（全量）/前端 build+vitest 通过

## Phase 3: 提交
- [ ] 3.1 提交本 change
