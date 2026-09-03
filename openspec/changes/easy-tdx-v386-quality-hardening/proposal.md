## Why

easy_tdx 已连续演进到 V385，后端 Python（缠论算法/回测/CLI）测试体系已经非常成熟：全量 pytest 2609 passed，ruff/mypy/format 归零，vue-tsc + vite build 通过。但本次全面审计发现四类结构性短板，它们不是功能缺陷，而是持续演进下的工程债，正在拖慢后续迭代速度并放大回归风险：

1. 前端几乎零自动化测试。web-ui 有 31 个组件、13 个视图，却只有 1 个测试文件（src/grading/__tests__/grade.test.ts，且用的是 node:test 而非 vitest）。V102DecisionCard、ChanlunChart、各视图页等核心 UI 全靠人工点击验证，历史上已经出现过「前端无回归守卫导致离谱数值 bug」的先例。
2. 后端测试覆盖严重不均衡。27 个注册策略里有 15 个在测试目录中零引用（atr_breakout/bbi/bias_reversal/dmi/donchian/ema_cross/emv/keltner/obv_breakout/rsi_divergence/rsi_macd_combo/supertrend/triple_ma/volume_breakout/wr_reversal），11 个 Web 路由模块零测试文件（announcement/block/board_mac/ex_market/finance/fundamental/indicator/mac_data/mac_quotes/realtime/server）。覆盖率长期贴着 60 门槛，缺少提升抓手。
3. chanlun/mmd.py 已膨胀到约 2.96 万行、299 个顶层函数，成为单文件 god-module，同时残留多个带版本号的旧实现（find_mmds_v39/v40/v41/v42/v76 等），其中若干已无任何生产调用点，属于死代码。
4. 工程卫生与 CI 门禁不完整：前端没有 eslint/prettier 与测试脚本，CI 只跑前端 build 不跑前端测试，覆盖率不产出可视化报告，根目录散落 6 个未跟踪的一次性脚手架脚本，.gitignore 缺 htmlcov 等运行时产物条目。

这些问题不解决，每新增一个 V102/缠论/回测特性，验证成本都在线性增长，且前端质量只能靠发布后用户反馈兜底。

## What Changes

本变更分四个能力域推进（只做需求与任务规划，不含具体实现）：

- 前端测试基础设施：引入 vitest + @vue/test-utils，为纯逻辑与关键组件建立自动化测试，并把前端测试接入 CI。
- 后端覆盖率提升：补齐 15 个零覆盖策略与 11 个零覆盖路由的边界/契约测试，把覆盖率门槛从 60 提升到可执行的 65，并向 70 靠拢。
- 缠论模块治理：拆分 mmd.py god-module，清理无调用点的版本化死代码，建立模块边界与回归基线。
- 工程卫生与门禁：前端 lint/format 落地，覆盖率报告与前端测试进 CI，根目录脚手架归档，.gitignore 补齐运行时产物。

## Capabilities

### New Capabilities
- frontend-testing: 前端 vitest 测试框架、纯函数与关键 Vue 组件的自动化测试能力
- backend-coverage: 策略与 Web 路由的边界/契约测试补全，以及可执行的覆盖率提升门禁
- chanlun-modularization: mmd.py 拆分与版本化死代码清理的模块治理能力
- engineering-hygiene: 前端 lint/format、CI 门禁扩展、仓库卫生与产物忽略规则

### Modified Capabilities

（无。本变更不修改既有能力的规格级行为，只新增质量保障能力。）

## Impact

- 代码：新增/拆分 chanlun 子模块；新增 web-ui 测试目录与配置；新增/调整测试文件；修改 .github/workflows/ci.yml、web-ui/package.json、pyproject.toml（覆盖率门槛）、.gitignore。
- 依赖：web-ui 新增 devDependencies（vitest、@vue/test-utils、@vitejs/plugin-vue 测试相关、eslint、prettier）。后端不新增运行时依赖。
- API/契约：不改变任何对外 API 行为；清理的 find_mmds_vNN 旧函数如被外部用户引用，采用弃用周期而非硬删除。
- 风险：god-module 拆分是最高风险项，需以「纯搬移 + 全量回归 + 逐步切换」方式降低风险。