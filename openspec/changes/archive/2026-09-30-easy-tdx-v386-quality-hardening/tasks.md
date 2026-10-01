## 1. 前端测试基础设施（frontend-testing）

- [x] 1.1 web-ui 安装 vitest、@vue/test-utils、jsdom 等测试依赖并新增 test 脚本
- [x] 1.2 将 grading/__tests__/grade.test.ts 从 node:test 迁移到 vitest 并确认全绿
- [x] 1.3 为 V102DecisionCard 编写三类数据形态（完整/缺字段/无建议）组件测试
- [x] 1.4 为 13 个视图页各补一个挂载冒烟测试
- [x] 1.5 为 format.ts、market.ts、grading 纯函数补充 vitest 用例
- [x] 1.6 CI frontend job 增加前端测试步骤（vitest run）
  - V-33：frontend job 已有 vitest+lint+format；test 矩阵 job（含 Windows）已补
    `npm test` 步骤（本地 vitest run 129 passed 等价验证；CI 实跑待下次 push）。

## 2. 后端覆盖率提升（backend-coverage）

- [x] 2.1 建立零覆盖策略参数化测试模板并跑通 1 个策略作为样板
- [x] 2.2 补齐 15 个零覆盖策略的参数校验/信号产生/边界测试
- [x] 2.3 为 11 个零覆盖 Web 路由模块建立契约测试模板
- [x] 2.4 补齐路由成功/错误分支契约测试
- [x] 2.5 本地测量覆盖率，定位剩余低覆盖模块并列出差距
  - V-33 实测：总覆盖率 78.7%（门槛 70，达标）。低覆盖集中在 ex/ 命令簇与
    CLI 入口（__main__/tray/dsl 0%，ex/commands 24-27%），已沉淀
    scripts/coverage_gaps.py 可复跑定位。
- [x] 2.6 pyproject.toml 与 CI 的覆盖率门槛 60 → 65，CI 产出覆盖率摘要

## 3. 缠论模块治理（chanlun-modularization）

- [x] 3.1 审计 mmd.py 全部 299 个顶层函数的调用关系，生成死函数清单
  - V-33 复核：mmd.py 现存 6323 行 / 25 顶层函数（含 5 个 _calc_*），
    V76-V82/V49-V65/V41-V51 条件簇已拆至 mmd_conditions.py + 惰性再导出 shim（V393/V397/V399）。
- [x] 3.2 删除确认无生产调用点的版本化死函数并全量回归
  - V-33 实测：v40/v41 为带 deprecated::V390 标注的兼容别名（存在性测试锁定），
    v42（1 处）/v44（recursive.py 递归主路径在用）有生产调用点，
    _check_pullback_volume_v2 有 4 处调用——**无真正死代码可删**，任务以审计结论关闭。
- [x] 3.3 设计 mmd/ 子包边界与顶层再导出 shim
  - V-33 实测：采用等价的「条件簇拆至 mmd_conditions.py + mmd.py 惰性再导出」
    方案（V393/V397/V399 落地），mmd.py 2.96万行→6323 行；未建 mmd/ 子包目录，
    边界目标已由 mmd_conditions.py/mmd_v102.py 实现且 3810 测试全绿。
- [x] 3.4 分步搬移指标计算簇（每步全量 pytest + ruff + mypy 通过）
  - V-33 实测：大簇搬移已由 V393/V397/V399 完成；mmd.py 仅余 5 个
    _calc_*（position_sizing/avg_volume×2/zs_avg_volume/breakout_retest），
    各 1-2 处调用且与 find_mmds 主链强耦合，属合理保留边界，非待搬项。
- [x] 3.5 验证 find_mmds 与核心类型导入兼容性并固化回归

## 4. 工程卫生与门禁（engineering-hygiene）

- [x] 4.1 web-ui 引入 eslint + prettier 与 format/lint 脚本
- [x] 4.2 CI frontend job 增加 lint/format 步骤
- [x] 4.3 归档/清理根目录 6 个未跟踪脚手架脚本
- [x] 4.4 .gitignore 补齐 htmlcov 等运行时产物条目
- [x] 4.5 全量门禁复跑（pytest/ruff/mypy/format/vue-tsc/vite build/vitest）并更新 DEV_STATUS 质量行
  - V-33 复跑实测：pytest 3810 passed/4 skipped；ruff check+format 双绿；
    vue-tsc 0 error；vitest 129 passed(16 文件)；mypy src/ 20 处遗留告警（8 个为
    untracked 新文件的 strict 项，非本轮回归）；uvicorn 8000 重启后 /analyze 真实链路
    返回 bis/zss 正常。