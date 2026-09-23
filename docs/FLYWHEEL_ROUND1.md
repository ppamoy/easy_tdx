# 持续优化飞轮 · 第 1 轮

> 流程：我（主代理）写测试脚本 → agnes-3.0-flash 子代理深度测试 → 我审核并写修改意见
> → agnes-3.0-flash 子代理编码修复 → 回归测试 → 提交 → 下一轮。
>
> 生产环境：http://127.0.0.1:8000 （systemd `easy-tdx.service`，工作目录 = 仓库根，
> 用 `.venv/bin/python -m uvicorn easy_tdx.web:create_app --factory`，代码改动需
> `sudo -n systemctl restart easy-tdx.service` 后生效；前端需 `npx vite build`）。
>
> 核心测试脚本：`tests/e2e/prod_smoke.py`（14 项检查，含不变量断言，基线 14/14 全过）。

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

## 待补充（等待子代理测试报告）

子代理测试中（agnes-3.0-flash，5 个领域：缠论递归 / 选股择时看板 / 提醒流与监控 /
前后端契约 / 健壮性负向）。其发现经我审核（去伪、定级）后并入本文件，再统一派发修复。

主代理已独立交叉验证的两点（降低误报风险）：
- 前端 `api.ts` 全部 **26 个请求路径**与后端 92 条路由**完全匹配**（无路径拼写类契约缺陷）。
- 缠论递归不变量：2 标的 × 3 周期（DAY/MIN_30/WEEK）共 6 组，递归链一致 / 端点连续 /
  方向交替 / 中枢区间 **零违例**。
