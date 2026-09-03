## 1. 前端测试基础设施（frontend-testing）

- [ ] 1.1 web-ui 安装 vitest、@vue/test-utils、jsdom 等测试依赖并新增 test 脚本
- [ ] 1.2 将 grading/__tests__/grade.test.ts 从 node:test 迁移到 vitest 并确认全绿
- [ ] 1.3 为 V102DecisionCard 编写三类数据形态（完整/缺字段/无建议）组件测试
- [ ] 1.4 为 13 个视图页各补一个挂载冒烟测试
- [ ] 1.5 为 format.ts、market.ts、grading 纯函数补充 vitest 用例
- [ ] 1.6 CI frontend job 增加前端测试步骤（vitest run）

## 2. 后端覆盖率提升（backend-coverage）

- [ ] 2.1 建立零覆盖策略参数化测试模板并跑通 1 个策略作为样板
- [ ] 2.2 补齐 15 个零覆盖策略的参数校验/信号产生/边界测试
- [ ] 2.3 为 11 个零覆盖 Web 路由模块建立契约测试模板
- [ ] 2.4 补齐路由成功/错误分支契约测试
- [ ] 2.5 本地测量覆盖率，定位剩余低覆盖模块并列出差距
- [ ] 2.6 pyproject.toml 与 CI 的覆盖率门槛 60 → 65，CI 产出覆盖率摘要

## 3. 缠论模块治理（chanlun-modularization）

- [ ] 3.1 审计 mmd.py 全部 299 个顶层函数的调用关系，生成死函数清单
- [ ] 3.2 删除确认无生产调用点的版本化死函数并全量回归
- [ ] 3.3 设计 mmd/ 子包边界与顶层再导出 shim
- [ ] 3.4 分步搬移指标计算簇（每步全量 pytest + ruff + mypy 通过）
- [ ] 3.5 验证 find_mmds 与核心类型导入兼容性并固化回归

## 4. 工程卫生与门禁（engineering-hygiene）

- [ ] 4.1 web-ui 引入 eslint + prettier 与 format/lint 脚本
- [ ] 4.2 CI frontend job 增加 lint/format 步骤
- [ ] 4.3 归档/清理根目录 6 个未跟踪脚手架脚本
- [ ] 4.4 .gitignore 补齐 htmlcov 等运行时产物条目
- [ ] 4.5 全量门禁复跑（pytest/ruff/mypy/format/vue-tsc/vite build/vitest）并更新 DEV_STATUS 质量行