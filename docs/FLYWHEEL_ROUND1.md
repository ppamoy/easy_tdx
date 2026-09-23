# 持续优化飞轮 · 第 1 轮

> 流程：我（主代理）写测试脚本 → agnes-3.0-flash 子代理深度测试 → 我审核并写修改意见
> → agnes-3.0-flash 子代理编码修复 → 回归测试 → 提交 → 下一轮。
>
> 生产环境：http://127.0.0.1:8000 （systemd `easy-tdx.service`，工作目录 = 仓库根，
> 用 `.venv/bin/python -m uvicorn easy_tdx.web:create_app --factory`，代码改动需
> `sudo -n systemctl restart easy-tdx.service` 后生效；前端需 `npx vite build`）。
>
> 核心测试脚本：`tests/e2e/prod_smoke.py`（16 项检查，含不变量断言，基线 16/16 全过）。

## 生产代码新鲜度核查（2026-09-22）

| 项 | 值 | 结论 |
|---|---|---|
| 服务进程启动 | 16:26:51 | — |
| `web/routers/monitor.py` 最后修改（V718b） | 16:25:52 | 早于启动 ✅ |
| 最新提交 | `15f465d` V718b | 已加载 |
| 前端 `dist/index.html` | 15:56:27 | 晚于最后前端源码改动 15:42 ✅ |
| 最新端点在线 | `/monitor/alerts` 200、dashboard/screen async 均在 OpenAPI | ✅ |

**结论：8000 端口运行的是最新代码**（含 V718b 与最新前端构建）。后续每轮修复后需重启并复验。

## 已确认问题（主代理独立复现）

### F1 [high] `/api/v1/*` 未知路径返回 200 + SPA HTML，而非 JSON 404

- **证据**：
  ```
  curl -s -o /tmp/x -w "http=%{http_code} type=%{content_type}\n" http://127.0.0.1:8000/api/v1/does-not-exist
  → http=200 type=text/html; charset=utf-8   （返回前端 index.html）
  curl ... http://127.0.0.1:8000/api/v1/monitor/nope/nope → 同样 200 + HTML
  ```
- **影响**：API 客户端/前端把「端点不存在」当成功，随后解析 HTML → 报错信息误导；
  排障时把错误路径误判为可用（我自己在写 E2E 脚本时就被误导过一次）。
- **根因**：`src/easy_tdx/web/app.py` 的 `SPAStaticFiles.get_response`（约 336-346 行）
  捕获一切 404 返回 `index.html`；注释假设「API 路径已在前面注册不会走到这里」，
  但该假设只对**已注册**路由成立，未注册的 `/api/*` 会落到兜底。
- **修改意见**：在 `get_response` 中读取 `scope.get("path", "")`，若以 `/api` 开头则
  `raise`（交回 Starlette 的 JSON 404），不做 SPA 兜底。附带单测：`/api/v1/does-not-exist`
  与 `/api/v1/monitor/nope` 必须返回 404 且 `content-type: application/json`。

### F2 [medium] 自选池路径的异步选股 `progress` 恒为 null（进度条不显示）

- **证据**：
  ```
  POST /api/v1/stock-pick/screen/async {"date":..., "pool":[...2 只...], "top_n":5}
  GET  /api/v1/stock-pick/screen/task/{id} → status=done progress=None note=''
  ```
  （对比 `pool_scope=full` → progress 10→20→…→100 正常）
- **影响**：前端 `StockPickView` 的进度条仅在 `progress !== null` 时渲染，
  自选池扫描全程无进度反馈（默认热门池 30 只是 17.5s 的等待，体验差）。
- **根因**：进度上报只加在 `scan_market`（全市场）；`_screen_run_sync` 的 pool 分支走
  `fundamental/pipeline.py::run_screen`，其循环（约 456-480 行）无 `report_progress`。
- **修改意见**：在 `run_screen` 的逐只循环内按 ~10% 粒度 `report_progress(...)`，
  并在 `_screen_run_sync` 的 pool 分支首尾各报一次；保持 `report_progress` 在
  非任务线程静默（已实现）。

### F3 [medium/perf] 自选池路径 30 只耗时 17.5s（市值取价串行）

- **证据**：`pool_scope=pool` + 默认热门池(30 只) 实测 `real 0m17.47s`；
  3 只小池 2.42s → 每只约 0.6s，与 MAC 服务器单次取数延迟一致。
- **根因**：`run_screen` 在循环内**串行**调用 `_market_quote`（`pipeline.py` 约 468 行）；
  V714 只把 `scan_market`（全市场）的同一段改成 8 线程并行，池路径漏改。
- **修改意见**：把 `run_screen` 的市值门槛取价改为 `ThreadPoolExecutor(max_workers=8)`
  并行（每线程各自建 MAC 连接，与 `scan_market` 的实现保持一致），预期 17.5s → ~4s。

## 第 1 轮修复与验证（V719，主代理自测自修）

> 原计划的 agnes-3.0-flash 子代理测试因**速度过慢**由用户叫停，改为主代理自行完成
> 「深度测试 → 定位 → 修复 → 回归」全流程。

### 我做的深度测试

1. **生产 E2E 冒烟**（`tests/e2e/prod_smoke.py`）：14 项 + 不变量断言，基线全过。
2. **负向/边界/并发探针**（`/tmp/probe/deep_probe.py`）：17 个非法/越界请求、5 条未知路径、
   3 组 10 并发、健康复查。
3. **契约交叉审计**：`api.ts` 全部 26 个请求路径 ↔ 后端 92 条路由，**完全匹配**。
4. **递归不变量独立验证**：2 标的 × 3 周期 6 组，**零违例**。
5. **性能实测**：`_market_quote` 逐只新建 MAC 连接 = 1.30s/只（复用连接 0.58s/只）。

### 修复清单（均已线上验证）

| 编号 | 问题 | 修复 | 线上验证 |
|---|---|---|---|
| F1 [high] | `/api/*` 未知路径被 SPA 兜底成 **200 + HTML** | `web/app.py` `SPAStaticFiles.get_response` 对 `/api`、`/api/*` **不兜底**（raise → JSON 404）；前端路由不受影响 | 3 条未知路径 → `404 application/json`；`/optimize` → 200 ✅ |
| F2 [medium] | 自选池异步选股 `progress` 恒 `null` | `run_screen` 各阶段 + `_screen_run_sync` 池分支补 `report_progress` | 池路径进度 `3.0 → 100.0` ✅ |
| F3 [medium/perf] | 自选池 30 只 **62s**（`run_screen` 逐只新建 MAC 连接 + 串行） | 改为「打分/盈利过滤 → **8 线程并行市值校验（每线程复用一条 MAC 连接）** → 组装」三段式 | **62s → 2.17s（28×）**，结果数不变（29 只）✅ |
| F4 [medium] | 部分端点用 **200 + `{"error":...}`** 报客户端错误（monitor/create 空池、monitor check 未知任务、screening/evaluate 缺参/坏日期），客户端会把失败当成功 | 统一改 **4xx + `detail`**（`HTTPException`） | 400/404/400/400 ✅ |
| F5 [low] | `top_n="abc"` → 400 且泄漏 `invalid literal for int()` 内部报错 | 新增 `_int_arg()` 统一解析（非法 → `400 {"detail": "top_n 必须是整数"}`，越界夹取） | `{"detail":"top_n 必须是整数"}` ✅ |

### 回归防护

- 新增 `tests/unit/test_v719_fixes.py`（**12 项**）：F1 未知路径 JSON 404 + 前端路由不误伤、
  F2 池路径进度单调到 100、F4 三处 4xx 语义、F5 干净报错与 `_int_arg` 边界。
- `tests/e2e/prod_smoke.py` 新增 2 项常驻检查：`api_unknown_path_404`、`error_semantics`
  （修复一旦回退立即报警）。
- 同步更新 `tests/unit/test_screening_router.py` 两处旧断言（200+error → 400+detail）。

### 审核要点（去伪）

- 子代理与探针里出现的「`/api/v1/server/test` has_data=false」「观望且无入场价」等，
  经核实均为**已知环境事实/设计行为**，不计为缺陷（已在测试脚本注释中固化，避免后续误报）。

### 提交前基线审计补遗（主代理，2026-09-23）

| 编号 | 问题 | 处理 |
|---|---|---|
| F6 [low] | `monitor/create` 中残留 200+error 死代码（306-307 行，400 分支之后不可达） | 删除 |
| F7 [medium] | F4 修复不彻底：`GET /monitor/{task_id}` 未知任务仍返回 **200+error**（其余端点已改 4xx），且 `test_market_monitor_sina.py` 三处旧断言（200+error）未同步 → 全量单测 2 failed | 路由补 404（含注释），3 处断言改 4xx+detail；前端无调用方（已核实 MonitorView 只用 check/stop/create） |
| — | `chanlun/bi.py` 1 处 + `tests/e2e/prod_smoke.py` 14 处 E501 长行（ruff 15 errors） | 全部折行，ruff 全绿 |
| — | `web-ui/src/stores/backtest.ts` 4 个 unused eslint-disable 指令 | eslint --fix 清除 |

### 最终回归（全绿，2026-09-23）

| 项 | 结果 |
|---|---|
| 后端全量单测 `pytest tests/unit` | **3480 passed, 4 skipped** |
| ruff `check src tests` | **All checks passed**（15 → 0） |
| mypy `src/easy_tdx` | **no issues in 258 files** |
| vue-tsc `-b` | **0 错误** |
| eslint `src/` | **0 错误 0 警告** |
| vitest `run` | **全过** |
| vite build | **成功**（chunk>500kB 提示为已知非缺陷） |
| 生产重启 `systemctl restart easy-tdx` | **active** |
| 生产 E2E 冒烟 | **16/16 全过**（含 api_unknown_path_404、error_semantics） |
