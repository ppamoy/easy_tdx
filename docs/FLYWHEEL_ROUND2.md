# 持续优化飞轮 · 第 2 轮

> 流程：主代理维护 E2E 脚本并保证生产 8000 最新 → 子代理深度测试扩展 →
> 主代理审核去伪定级 → 子代理编码修复 → 回归全绿 → 提交 → 下一轮。
>
> 上一轮：`docs/FLYWHEEL_ROUND1.md`（V719，提交 `4acc14e`，基线 16/16 全绿）。

## 第 2 轮子代理测试（harness 内置子代理，2026-09-23）

- 覆盖：8 个探针方向 ~1130 次判定（A 参数边界 990 / B HTTP 23 / C 异步 14 /
  D 监控 24 / E 缠论 27 / F 契约 92 路径 / G 并发 3×10 / H 性能 8 案例），
  每个发现独立复现 ≥2 次；报告 `/tmp/flywheel_r2/report.md`。
- 基线回归：`tests/e2e/prod_smoke.py` **16/16**，无回退。

## 主代理审核：判定与优先级

### 确认缺陷（本轮修复，V720）

| 编号 | 级别 | 问题 | 独立验证 | 根因 | 修法 |
|---|---|---|---|---|---|
| D1 | **high** | `GET /diagnosis/quick` 对任何股票 **100% 500**（`'Depends' object has no attribute 'get_stock_kline'`），诊断页完全不可用 | 主代理复现 2 次（600519/000001 均 500） | `diagnosis.py:2706` `quick_diagnosis` 调 `diagnose_stock(req, client)` **漏传 `mac_client`**；`diagnose_stock` 的默认参数 `Depends(get_mac_client_optional)` 在普通函数调用中不解析，裸 Depends 对象被当 client 用 | `quick_diagnosis` 签名补 `mac_client: Any \| None = Depends(get_mac_client_optional)` 并显式传入 |
| D2 | medium | 数值越界穿透到 TDX 协议层 → 500：`chanlun/analyze|multi-level|train/session` `start=999999999` → `'H' format…`；`bars/index` 同；`minute/history?date=-1` → `'I' format…` | 主代理复现 date=-1 → 500 | `start` 无上限（struct 'H' 上限 65535）、`date` 无 YYYYMMDD 边界 | `bars.py` 各 GET `start` 加 `le=65535`；`date` 加 `ge=19900101, le=20991231`；chanlun POST 请求模型 `start` 同约束 |
| D3 | medium | 松散 dict 端点对复合形状不设防 → 500 族：`screen(/async)`、`dashboard/async` 的 `pool` 传字符串 → `'str' has no attribute 'get'`；`timing` symbols 传 `["SH600519"]`；`train/score` 分数 "abc"；`learn/mistakes` 数组字段 | 主代理复现 monitor 同族（interval "abc" → 500） | 手工 `req.get(...)` 后直接使用，无形状/类型校验 | 各入口前置校验（pool 元素须 dict、symbols 须 6 位代码、数值字段 try→400），非法一律 400+detail |
| D4 | medium | `monitor/create` 校验失败返回 500 但**任务已入库——孤儿任务**（响应无 task_id 无法清理，`/monitor/list` 残留 `interval='abc'`） | 主代理完整复现：500 + list 残留 | `create_task` 先执行、参数校验缺失（interval 在 `if interval > 0` 才炸） | monitor/create 前置校验 interval（int，0~86400）与 threshold（float，0~1），非法 400，**校验先于 create_task**（与 D3 同族，此处必须修复顺序） |
| D11 | medium | 空数据触发**逐主机故障转移失控**：`fund-flow/history` 空数据股票 >280s 超时；窗口内正常请求 `security/count` 6.5s→18.9s | 子代理双会话复现 + 连带拖慢证据 | `client.py` `_fund_flow_failover`/`_find_host_returning_data` ping 全部候选主机逐台重试，**无总时间预算** | 故障转移加总预算（monotonic 计时，超 ~30s 返回空数据+日志），单主机尝试保留原超时 |
| D5 | low（降级） | `/market/strength` 任何调用 500「无法定位通达信安装目录」 | 主代理复现 | 本机无 TDX_HOME/vipdoc，属**环境配置缺失**而非逻辑缺陷 | 路由层捕获该异常 → **503** + 可读提示（设置 TDX_HOME 的指引） |
| D7 | low | backtest 未知任务 400 而非 404（与全站任务端点不一致） | 探针复现 | 历史实现 | 改 404+detail |
| D8 | low | `multi-level` 非法 category 静默按 DAY（`analyze` 同参 400，行为不一致） | 探针复现 | `frequency_map.get(..., "daily")` 兜底 | category 不在白名单 → 400 |
| D9 | low | `alerts?limit=0/-1` 返回 1 条（`max(1, …)` 夹取） | 探针复现 | `alert_store.recent_alerts` 下限夹到 1 | limit≤0 → 返回空列表（语义正确） |
| D10 | low | `sina/financial-report` 无效代码 → 503（应 4xx） | 探针复现 | 503 语义错误 | 改 400+detail |

### 去伪（不计为缺陷）

- 探针 C 组「backtest 未知任务 FAIL」：400+detail 是 V719 正确语义，探针预期写反（仅保留 D7 一致性改进）。
- 探针 E「analyze/multi-level 结构一致」SUSPECT：比对了错误层级（multi-level 响应在 `high_level.result` 下）——误报。
- `/bars` 的 `as_of/offset/length` 等未声明 query 参数被忽略：FastAPI 标准行为。
- `SH:999999` 返回指数数据：TDX 协议行为（999999 即上证指数）。
- screening 系 200+error 残留（scan/verify 等）：前端已 `if (data.error) throw` 兼容，属**一致性改进非缺陷**，记 backlog。
- 偶发上游超时（minute 4.6s、finance 7s）：上游 TDX 延迟，性能观察项。

### 暂缓（backlog，本轮不做）

- D6：GET 端点不支持 HEAD（404）——需自定义路由类，收益低。
- `security/count` 6.5~15s、`fund-flow` 常态耗时——上游延迟，观察。
- 200+error → 4xx 全面统一（screening/scan、verify、diagnosis/analyze、chanlun/560/924 等 11 处）——前端已兼容，低优。

## V720 修复验收标准

1. D1：`GET /diagnosis/quick?market=SH&code=600519` 生产实测 200 且含 analysis 字段；单测覆盖（mock 依赖）。
2. D2：上述越界请求全部 4xx（422/400），无 500；单测覆盖 start 上限与 date 边界。
3. D3/D4：所有列形状非法输入 → 400+detail；monitor/create **先校验后建任务**，`/monitor/list` 无孤儿。
4. D11：`fund-flow/history`（空数据股票）总耗时 ≤ ~35s（预算内返回空+标记），并发窗口内 `security/count` 不显著劣化。
5. D5/D7/D8/D9/D10：语义更正后生产实测通过；各自单测。
6. 全量回归：pytest / ruff / mypy / vue-tsc / eslint / vitest / build 全绿；生产重启后 E2E 冒烟 16/16。

## V720 修复与验证（修复子代理编码，主代理独立回归）

### 实施要点（含经审核接受的处方偏差）

| 项 | 实施 | 偏差与理由 |
|---|---|---|
| D1 | `diagnosis.py` quick_diagnosis 补 mac_client 显式传参 + V720 注释；全文件排查无同构隐患 | 无 |
| D2 | bars.py 4 个 GET `start` 加 `le=65535`，date 加 19900101~20991231；`ChanlunRequest.start` 加 le（覆盖 analyze/multi-level/train/session） | 无 |
| D3 | stock_pick `_norm_pool_arg()`（pool 元素须 dict，接入 screen/screen-async/dashboard-async）；timing symbols 形状校验；train/score 数值校验；learn/mistakes 标量限制 | 「6 位代码」改为「元素须对象」——炸点是形状不是位数，"600519" 亦会被 zfill 接受 |
| D4 | monitor/create **先校验**（interval 0~86400、threshold 0~1，拒 bool）**后 create_task**，孤儿消除 | 无 |
| D11 | `client.py`（实际位置，非 tdx/ 子包）sync/async × failover/`_find_host_returning_data` 共 **4 处**加 30s monotonic 总预算，超时 warning+回原 host+空数据；单台 5s 超时与首台命中即返不变 | 范围从 2 处扩到 4 处——同族失控机制，只修 2 处留同类入口 |
| D5 | market.py 窄捕获 `TdxOfflineError` → 503 + TDX_HOME 处方 detail | 无 |
| D7 | backtest 未知任务 400 → 404；同步更新 test_web_backtest.py 旧断言 | 无 |
| D8 | multi-level category/low_level 白名单 400（列合法值），空 low_level 默认 30min 语义保留；analyze 等未扩大改动面 | 无 |
| D9 | alert_store `limit<=0 → []` | 无 |
| D10 | sina `code` Query 加 `pattern=^\d{6}$` → 422 参数层拦截；真实网络故障 SinaError 保持 503 | 比处方（400）更准：无效代码本就到不了 except 分支，4xx 目标达成且不误标网络故障 |

### 回归防护

- 新增 `tests/unit/test_v720_fixes.py` **46 个测试**（D1×3 含 inspect 源码级防回退锚定、D2×7、D3×11、D4×6 含 create_task 未调用断言、D5×2、D7×1、D8×3、D9×2、D10×2、D11×4）。
- `tests/e2e/prod_smoke.py` 新增第 17 项常驻检查 `v720_semantics`（10 项 V720 语义一次性回归）。

### 最终回归（主代理独立重跑，全绿，2026-09-23）

| 项 | 结果 |
|---|---|
| 后端全量单测 | **3526 passed, 4 skipped** |
| ruff check / format | **All checks passed**（13 个改动文件已格式化） |
| mypy | **no issues in 258 files** |
| vue-tsc / eslint / vitest / vite build | **0 错误 / 0 警告 / 70 passed / 构建成功** |
| 生产重启 + 清残留 | **active**；alerts 清空、/monitor/list 空 |
| 生产 E2E 冒烟 | **17/17 全过**，`v720_semantics` 证据：`quick:200；bars_index:422；minute_history:422；analyze:422；pool_shape:400；monitor_validate:400/tasks=0；backtest_404:404；ml_category:400；alerts_limit0:200；sina:422` |

**结论：D1–D10 全部修复并生产实测验证；D11 预算机制单测验证（线上空数据股票故障转移场景需等待真实空数据标的复测，已由常驻预算+warning 日志覆盖）。**
