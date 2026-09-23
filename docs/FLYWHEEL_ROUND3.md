# 飞轮第 3 轮 — 审核意见与修复处方（V721）

- 测试子代理报告：`docs/FLYWHEEL_ROUND3_REPORT.md`（原始归档，探针脚本 `/tmp/flywheel_r3/`）
- 主代理独立验证：D12 源码+接口证实；D14 部分证实（**定性下调**，见下）；D17 源码证实；D15 日志+代码路径证实；D16 复现机制未明，转为防御性修复。
- 基线：V720 全部修复复核通过（smoke 17/17、边界内侧 19/19 无过拟合、D11 预算 280s→6.4s），算法不变量 12/12、状态一致性全 PASS。

## 审核定级与处方

| # | 级别 | 判定 | 根因 | 处方 |
|---|---|---|---|---|
| D12 | **高** | ✅ 证实 | `monitor.py` list 端点每项只给 `stock_count`（L335）不给 `stocks`；`MonitorView.vue:1266` 模板 `task.stocks.length` 在 loadTasks()（刷新/重进页面）后对后端数据直接渲染 → TypeError，监控页任务区崩溃 | ① `monitor.py` list 每项补 `"stocks": task.stocks`（载荷小，无性能顾虑）；② 前端 1266 行改 `task.stocks?.length ?? task.stock_count ?? 0` 双重防御 |
| D14 | **高**（定性收敛） | ⚠️ 部分证实 | `screening.py:274` scan 产出 `symbol="SZ000001"`，而 backtest 系列 schema 一律 `^(SZ|SH|BJ):\d{6}$`（4 处）→ 同类 API 两套口径。**「选股页回测 100% 失败」不成立**：ScreeningView 批量回测走 `fetchBars`+`ohlcv`（symbol 可空，不触发 pattern），PortfolioView 保存用 `market+':'+code` 规范格式；真正触雷的是任何把 scan 产出 symbol 直传 symbol 字段的集成路径（现前端恰好绕开，属契约地雷） | ① `backtest_schemas.py` symbol 字段加共享 `field_validator`：接受 `SZ000001`/`sz:000001` 变体并归一为 `SZ:000001`（宽进严处），彻底非法仍 422；② `screening.py` scan 产出改规范 `f"{market}:{code}"`（与全站口径统一），修复代理须 grep `web-ui` 全部 `s.symbol` 消费点（CSV 导出 L175/310、verify symbols、表格展示）确认兼容并跑 vitest |
| D15 | 中 | ✅ 证实 | `klines.py fetch_qfq_klines` 只对「MAC 返回空 df」回退 TDX，对「MAC 客户端抛异常」不回退 → MAC 故障窗口内 screening/scan 静默 200+0 结果（journalctl 114 条 zlib 错误），窗口后自愈 | MAC 客户端调用包 `try/except Exception` → warning 日志 + 走与空 df 相同的 TDX 回退路径；该函数被 6 个路由复用，一处修复全域受益 |
| D16 | 低→本轮修复 | ⚠️ 机制未明 | 重启窗口内 POST /api/v1/* 间歇返回 200+SPA index.html（2/1150+，定向复现 0 命中，服务端 200 无堆栈） | 放弃服务端追凶，转前端防御：`api.ts` fetch 封装统一校验 `content-type` 含 `application/json`，否则抛「服务正在重启，请稍候」友好错误（防 HTML 进 JSON.parse 产生难懂报错） |
| D17 | 低 | ✅ 源码证实 | 同步 `/stock-pick/screen` pool 路径忽略 top_n：`pipeline.run_screen` 无 top_n 参数，路由未做输出截断（top_n=5 与 50 同返 29 条） | 路由层对 run_screen 结果的标的列表按 top_n 截断（修复代理先读 run_screen 返回结构再切片），并在 docstring 标注「top_n 在同步池路径为输出上限」 |
| D18 | 低 | ✅ 证实 | `/diagnosis/quick` 对无数据标的 200+`{"error"}`，`DiagnosisView` 不处理 error 分支 | 前端 DiagnosisView 解析响应后 `if (data.error)` 走错误展示分支（对齐 ScreeningView 现有模式）；后端 200+error 属既有 backlog（全站清理），本轮不扩大 |

## V721 修复与验证（修复子代理编码，主代理独立回归）

### 实施要点（含经审核接受的偏差）

| 项 | 实施 | 偏差与理由 |
|---|---|---|
| D12 | monitor_list 每项补 `stocks`；MonitorView `stocks?.length ?? stock_count ?? 0` 双重防御 + 接口补 `stock_count?` | 无 |
| D14 | `_normalize_symbol` 共享归一（SZ000001/sz:000001→SZ:000001；不推断市场，裸 6 位/ABC123 仍 422），5 个 schema 接入 field_validator，pattern 移除；PortfolioBacktestRequest.stocks 逐元素归一；scan 产出改 `市场:代码`；前端消费点核验（CSV 转义冒号安全、verify `_norm` 兼容、vitest 全绿） | **偏差②（超出处方，审核接受）**：同步 `/backtest/run` 补 symbol 取行情路径（复用 async 同一 `_fetch_bars`，MAC 优先 TDX 兜底；取不到→400）——处方验收 #2 要求同步 SZ000001→200，原实现 symbol 必 400，验收项为假，故补齐；**偏差③（审核接受）**：`test_web_backtest.py` 旧「symbol→400」用例为 V721 锚定（断言的正是本次要修复的行为），拆为 3 条新语义用例（mock 取行情→200 / 失败→400 / 无数据源→422） |
| D15 | klines.py MAC 调用段 `try/except Exception` → warning + 空 df 走既有 TDX 回退；空 df 回退语义不变；6 个复用路由受益 | 无 |
| D16 | api.ts `parseJson()`（content-type 非 JSON → 友好报错）+ `throwError` 同守卫，28 处成功路径全量替换 | **偏差①（审核接受）**：处方允许收窄但全量替换成本低且防御一致 |
| D17 | 路由层 `_apply_top_n()`：results 按 top_n 截断、total 同步；同步端点 + 本地沉淀池路径接入；docstring 注明语义 | 异步路径未动（处方仅要求同步端点） |
| D18 | DiagnosisView `if (data.error)` → error 展示（对齐 ScreeningView 模式） | **偏差④（审核接受）**：补了 2 条视图用例（处方不强造，实际可行）；偏差⑤：动态 import 移 beforeAll + 20s 超时（大组件冷 import 撞 5s 默认时钟） |

另有偏差⑥（审核接受）：`ruff format --check` 本就报 9 个文件将重排，顺带格式化 pipeline.py / test_chanlun_strategy.py 等非本次文件——主代理逐 hunk 复核，全部纯换行调整、零逻辑改动。

### 回归防护

- 新增 `tests/unit/test_v721_fixes.py` **31 条**（D12×2、D14×13、D15×5、D17×5+1）；`test_web_backtest.py` 拆改 3 条（D14 同步语义）。
- 前端新增 `web-ui/src/views/__tests__/v721-fixes.test.ts` **6 条**（D16×4、D18×2）。
- `tests/e2e/prod_smoke.py` 新增第 18 项常驻检查 `v721_semantics`（D12 建任务→list 含 stocks→stop 清理；D14 归一 200 / 非法 422 / 裸代码 422 / scan symbol 规范形态）。

### 最终回归（主代理独立重跑，全绿，2026-09-23）

| 项 | 结果 |
|---|---|
| 后端全量单测 | **3559 passed, 4 skipped**（V720 基线 3526 + 新增 33） |
| ruff check / format | **All checks passed / 486 files already formatted** |
| mypy | **no issues in 258 files** |
| vue-tsc / eslint / vitest / vite build | **通过 / 通过 / 76 passed / built 8.49s** |
| 生产重启 | **active**；探针任务清理后 /monitor/list 空、alerts 空 |
| 生产 E2E 冒烟 | **18/18 全过**，`v721_semantics` 证据：`list_stocks:yes；sym_nonorm:200；sym_bad:422；sym_bare:422；scan_sym:['SZ:000001']` |

**结论：D12/D14 两个高优先级缺陷 + D15/D16/D17/D18 四个中低缺陷全部修复并生产实测验证；两个高优先级清零。**
