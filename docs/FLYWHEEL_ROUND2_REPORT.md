# easy_tdx 飞轮第 2 轮 E2E 测试报告

- 测试时间：2026-01（本轮），目标：生产实例 http://127.0.0.1:8000（systemd: easy-tdx.service）
- 方法：基线回归 + 8 个方向探针（A 参数边界 / B HTTP 语义 / C 异步任务链 / D 监控提醒流 / E 缠论递归 / F 前后端契约 / G 并发 / H 性能），每个疑似缺陷均以独立 curl/独立会话复现 ≥2 次后收录
- 约束遵守：未重启/修改服务，未改 src/；全市场重扫描 0 次；并发 ≤10；监控任务与提醒已全部清理

## 基线回归

`tests/e2e/prod_smoke.py`：**16/16 全部通过**（与第 1 轮基线一致，服务无回归）。

## 发现清单

### D1 [high] /diagnosis/quick 对任何股票 100% 返回 500，诊断页完全不可用

- **证据**
  ```
  curl 'http://127.0.0.1:8000/api/v1/diagnosis/quick?market=SH&code=600519'
  → HTTP 500 {"error":"Internal server error","detail":"'Depends' object has no attribute 'get_stock_kline'"}
  curl 'http://127.0.0.1:8000/api/v1/diagnosis/quick?market=SZ&code=000001' → 同样 500
  ```
  两种参数、两次独立会话均复现（A 探针 + curl 共 4 次）。
- **复现**：任意 market/code 组合 GET 该端点即 500，无需任何特殊参数。
- **影响分析**：前端 `web-ui/src/api.ts:328`（`fetchQuickDiagnosis`）与 `web-ui/src/views/DiagnosisView.vue` 直接调用该端点——**快速诊断页任何操作都必然失败**，属于页面级功能不可用。这是本 A 探针 990 次判定中唯一"正常参数即崩"的端点。
- **根因假设**：`src/easy_tdx/web/routers/diagnosis.py` L2706 `quick_diagnosis` 调用 `diagnose_stock(req, client)` 少传 `mac_client`。`diagnose_stock`（L279）签名中 `mac_client: Any = Depends(get_mac_client_optional)` 的默认值是**原始 Depends 对象**——FastAPI 只在路由层解析依赖，普通函数调用拿到的是未解析的 `Depends` 对象，随后在其上调用 `.get_stock_kline` 即 AttributeError。
- **修复建议**：`quick_diagnosis` 增加依赖参数 `mac_client: Any | None = Depends(get_mac_client_optional)` 并透传给 `diagnose_stock`；补一条"E2E: GET /diagnosis/quick 200"冒烟断言防止回归。

### D2 [medium] 数值越界直达 TDX 协议层（struct.pack）→ 500，涉及 5 个核心端点

- **证据**（均独立复现 ≥2 次）
  ```
  POST /chanlun/analyze      {"start": 999999999} → 500 {'H' format requires 0 <= number <= 65535}
  POST /chanlun/multi-level  {"start": 999999999} → 500 同上
  POST /chanlun/train/session{"start": 999999999} → 500 同上（63.9s / 93.8s 后返回）
  GET  /bars/index?start=999999999 → 500 同上（20.0s / 15.5s）
  GET  /minute/history?date=-1     → 500 {'I' format requires 0 <= number <= 4294967295}
  ```
- **复现**：上述最小请求原样重放即 500；对照 start=0/count=50 均 200。
- **影响分析**：API 层对 start/date 只做了"是数字"校验，未做协议范围校验，恶意或失误的越界值穿透到 pytdx 的 `struct.pack('>H', …)` 才崩溃；对用户表现为 500 + 协议层报错细节（信息泄漏面）。`start` 在 A 股 K 线分页中本就无合法用途超过 65535，属于纯输入校验缺口。
- **根因假设**：`start`/`date` 参数直接进入 GetBarCommand 等协议命令；pytdx 用 `'H'`（u16）/`'I'`（u32）打包。schema 未加 `le=65535`/下界约束。
- **修复建议**：在 Pydantic 模型/Query 上为 start 类参数加 `ge=0, le=65535`（date 加日期合法性解析），把 500 变成 422；或 在 fetch 层 clamp。

### D3 [medium] 松散 dict 端点对复合形状不设防 → 一族 500（pool/symbols/成绩提交）

- **证据**（均独立复现 ≥2 次；timing 已用 curl 双格式验证）
  ```
  POST /stock-pick/screen         {"pool": "SH600519"}            → 500 'str' object has no attribute 'get'
  POST /stock-pick/screen/async   {"pool": "SH600519"}            → 500 同
  POST /stock-pick/dashboard/async{"pool": "SH600519"}            → 500 同
  POST /stock-pick/timing         {"symbols": ["SH600519"]}       → 500 同（{"symbols":[123]} → 'int' object has no attribute 'get'）
  POST /stock-pick/screen         {"min_score": "abc"}            → 500 ...could not convert string to float: 'abc'
  POST /chanlun/train/score       {"score": "abc"}                → 500 提交成绩失败: could not convert string to float
  POST /chanlun/train/score       {"count": "many"}               → 500 invalid literal for int()
  POST /learn/mistakes            {"tags": ["a","b"]}（数组字段）→ 500 Error binding parameter 6: type 'list' is not supported
  ```
- **复现**：原样重放即 500。
- **影响分析**：这族端点用 `dict[str, Any]` 接收请求体、手工取字段，对"元素不是 dict/类型不能转换"没有统一防御。前端当前不会发这些形状，但作为公开 API 它们把 ValueError/TypeError 直接变成 500（全局 handler 兜底），并且报错文本包含内部实现细节。
- **根因假设**：`symbols_raw` 列表推导直接 `s.get("code")`（stock_pick.py L384 附近）；train/score 用裸 `int()/float()`；learn/mistakes 把任意 JSON 值绑进 SQLite 参数。
- **修复建议**：统一小工具函数 `as_symbol_list(v)` / `as_float(v, default)`：形状不对返回 400（"symbols 元素应为 {market, code}"），既修 500 又收敛错误语义；learn/mistakes 对 list/dict 字段先 json.dumps 再入库。

### D4 [medium] monitor/create 参数校验失败返回 500，但任务已入库——产生无法清理的孤儿监控任务

- **证据**（两次独立复现）
  ```
  POST /monitor/create {"interval_seconds": "abc"} → 500 {'>' not supported between instances of 'str' and 'int'}
  POST /monitor/create {"interval_seconds": {"x":1}} → 500 同（dict vs int）
  随后 GET /monitor/list → 各出现一个 interval='abc' / {'x':1} 的残留任务（响应里没有 task_id，调用方无从 stop）
  ```
- **复现**：发送上述请求 → 500 → GET /monitor/list 可见孤儿任务（本测试已全部 stop 清理）。
- **影响分析**：比普通 500 更糟的是**状态不一致**：校验发生在任务入库之后，调用方收到 500 却已产生持久任务；因响应中无 task_id，只能靠 /monitor/list 猜测清理。长期运行会积累幽灵定时任务。
- **根因假设**：monitor.py 创建路径先建任务对象再校验 interval（`interval > 0` 比较在 str/dict 上爆炸），异常抛出时未回滚 store。
- **修复建议**：先全量校验后入库（interval 非正整数 → 400）；或在异常路径回滚已创建任务。

### D5 [medium] /market/strength 部署级不可用：服务器未配置 TDX_HOME，任何真实调用 500

- **证据**（两次独立 curl）
  ```
  curl 'http://127.0.0.1:8000/api/v1/market/strength' → 500 "无法定位通达信安装目录，请设置 TDX_HOME 环境变量或显式传入 vipdoc 路径"
  ```
  A 探针中该端点 27 个触及 vipdoc 的变异全部同一 500；本机搜索无 vipdoc 目录；systemd 单元 `easy-tdx.service` 仅有 `EASY_TDX_WEB_DIST` 一个环境变量。
- **复现**：GET /market/strength（任意参数）即 500。
- **影响分析**：强势股排名功能（含前端 StrengthenView 所需能力）在当前生产实例上完全不可用。与 D1 不同，这是**部署配置问题**而非代码缺陷：代码路径本身在 A 探针中参数校验（preset/top_n/min_listed_days 等 6 项）表现正确。
- **修复建议**：在 easy-tdx.service 加 `Environment=TDX_HOME=/path/to/new_tdx`（若本机应装通达信数据），或在文档/UI 标注该功能需要本地 vipdoc；若产品上接受无此功能，建议把该错误转为 503 并在前端隐藏入口。

### D6 [low] API GET 端点不支持 HEAD（404），违反 HTTP 语义

- **证据**（urllib 与 curl 两种独立方法各复现）
  ```
  curl -sI 'http://127.0.0.1:8000/api/v1/bars?market=SH&code=600519&count=5' → HTTP/1.1 404, content-type: application/json
  curl -sI 'http://127.0.0.1:8000/api/v1/server/hosts'  → 404；对照 HEAD / 与 HEAD /openapi.json → 200
  ```
- **影响分析**：HEAD 探活/网关缓存会误判 API 为不存在。低危：前端不用 HEAD，GET 行为正常。
- **根因假设**：FastAPI 不为 GET 路由自动注册 HEAD；请求落到根挂载的 SPAStaticFiles，其 not-found 抛 404（src/easy_tdx/web/app.py 挂载段）。
- **修复建议**：`app.router.method_not_allowed`/中间件层面为 404 的 GET 路由补 HEAD，或对 API 路由统一 `methods=["GET","HEAD"]`。

### D7 [low] backtest 未知任务返回 400 而非 404，与全站任务端点语义不一致

- **证据**：`GET /backtest/tasks/nonexistent0000` → 400 `{"error":"Bad request","detail":"未知任务 'nonexistent0000'"}`（独立复现 4 次：C 探针 + 3 次 curl）。
- **对照**：`/stock-pick/screen/task/{id}`、`/stock-pick/dashboard/task/{id}`、`/monitor/{id}` 同场景均 404。
- **根因假设**：backtest.py L137-142 注释自述"统一抛 ValueError → HTTP 400"——有意为之但与全站不一致；REST 语义下"资源不存在"应为 404。
- **修复建议**：改为 `HTTPException(404, ...)`；前端 `throwError` 两者都能处理，风险小。

### D8 [low] multi-level 对非法 category 静默按 DAY 处理（与 analyze 行为不一致）

- **证据**：`/chanlun/multi-level {"category": "day"}` 与 `"4"` → 200 且结果 frequency=daily；同参数 `/chanlun/analyze` → 400 无效K线周期（独立复现 2 次）。
- **根因假设**：multi-level 用 `frequency_map.get(req.category.upper(), "daily")` 静默兜底（chanlun.py L410），analyze 走显式校验（L312 兜底是原值，后续报错）。
- **影响分析**：用户输错周期拿到"看起来成功"的错误周期结果，比报错更隐蔽。
- **修复建议**：与 analyze 对齐，未知 category → 400。

### D9 [low] alerts limit=0 / 负数 返回 1 条而非报错或全量

- **证据**：`GET /monitor/alerts?limit=0` 与 `limit=-1` → 200 count=1（D 探针 + 复核）。
- **根因假设**：alert_store.recent_alerts 的 `max(1, min(int(limit), 200))` 把 0/负数钳到 1。
- **影响分析**：调用方传 0 期望"空"，得到 1 条，可能造成分页误判。属设计怪癖非崩溃。
- **修复建议**：limit<=0 → 400，或语义定为"默认 50"。

### D10 [low] sina/financial-report 对无效代码返回 503（客户端错误被标为服务端/上游故障）

- **证据**：`GET /sina/financial-report?code=999999` → 503 `{"detail":"新浪财报查询失败: 'NoneType' object has no attribute 'get'"}`（×2）；对照 code=600519 → 200（5.3s）。
- **影响分析**：503 会触发监控告警/重试，但这是输入问题，应 4xx。报错文本含 NoneType 细节。
- **修复建议**：上游返回空/None 时转 404 或 400（"未查询到该代码财报"）。

### D11 [medium] 空数据触发逐主机故障转移，单请求 >5 分钟且拖慢同客户端其他请求

- **证据**
  - `/fund-flow/history?market=SH&code=600519` 两只股票、独立两次会话均 **280s+ 超时未返回**（v1.20.5 空数据故障转移设计：ping 全部候选主机 × 逐台重试）。
  - `/chanlun/multi-level` 对空数据股票 SZ:000000 两次实测 **158.0s / 141.9s**，最终返回 kline_count=0 空结果。
  - 故障转移窗口内的 10 并发混合测试：正常基线 ~6.5s 的 `/security/count` 变为 **18.9s**（对照无故障转移时同请求 6.5s/15.3s）。
- **影响分析**：面向交互式 Web 的 API 中，用户一次"错误代码/无数据"查询要承受分钟级等待；期间同主机客户端的其它请求可观测变慢。多请求同时触发故障转移时（A 探针第二轮曾出现 3 个同型请求并发）会长时间占满连接。
- **根因假设**：`_fetch_fund_flow_records` 空结果 + `_auto_reconnect` → `_fund_flow_failover`（client.py L1582+）对全部 known hosts 逐台 ping(5s)+重试；bars/multi-level 的 `_find_host_returning_data`（L1468+）同模式。
- **修复建议**：给故障转移加总预算（如 30s deadline / 只试前 N 台）；对"确认无效的代码"短路返回空；Web 层为该类请求加更短超时与 503 快速失败。

### 已排除的疑点（去伪后不列为缺陷）

- **screening/scan、/verify 的 `200 {"error": ...}`**：legacy 风格但前端 ScreeningView.vue L299 已显式处理（`if (data.error) throw`），行为一致，且属第 1 轮已知项。保留为 SUSPECT 记录，不算缺陷。
- **未声明的 query 参数被忽略（标准行为）**：/bars 的 `as_of`/`offset`/`length`、列表端点的无关参数等 —— FastAPI 路由未声明的 query 参数被静默忽略属框架标准行为，A 探针的 `unrelated_keys` 变异全部按此处理，不算缺陷。
- **SH:999999 返回完整缠论数据**：经查 999999 是 TDX 协议中上证指数的内部代码，返回的是指数数据——协议行为，非缺陷（SZ:000000/BJ:999999 返回空数据）。
- **/bars/index、/minute 等端点偶发 60s 超时**：与上游 TDX 服务器瞬时延迟相关（同一端点对照 0.1s 正常），重测正常，归为环境波动。
- **B 探针中 HEAD /openapi.json 404 判定**：脚本标签错位，curl 实测 200，该条不算。
- **progress 单调性 / 任务并发 / alerts source 过滤 / monitor 生命周期**：全部 PASS。
- **D9 补充复核**：`monitor/alerts?limit=0` 与 `limit=-1` 独立 curl 复现 2 次（各返回 1 条，对照 limit=2 返回 2 条），复现次数达标后收录为 D9。

## 探针覆盖清单

| 模块 | 判定数 | PASS | SUSPECT | FAIL | FAIL 说明 |
|---|---|---|---|---|---|
| 基线 prod_smoke | 16 | 16 | 0 | 0 | — |
| A 参数边界轰炸 | 990 | 887 | 9 | 79 | 79 中 61 条为 5 类真实缺陷的变异命中（D1-D5、D8 的重复计数）；其余为上游 TDX 超时（环境波动）|
| B HTTP 语义 | 23 | 20 | 2 | 1 | 1 FAIL = D6（HEAD 404，真缺陷）；2 SUSPECT 中 1 条为脚本标签错位（openapi HEAD 实为 200）|
| C 异步任务链 | 14 | 12 | 0 | 2 | 1 FAIL = D7（backtest 400）；1 条为探针自身数据缺列（修正后通过）|
| D 监控提醒流 | 24 | 23 | 0 | 0 | 全过；孤儿任务（D4）在边界用例中确认 |
| E 缠论递归 | 27 | 22 | 4 | 3 | 3 FAIL = 空数据股票 multi-level 141-158s（D11）；SUSPECT = D8 静默兜底 + 不变量脚本结构假设修正 |
| F 前后端契约 | 92 路径对齐 + 66 视图引用 | 全部对齐 | 0 | 0 | method 检出 2 处为窗口法误报（源码核实 POST/GET 正确）；ChanlunView 轮询用的路径风格 `/bars/{m}/{c}/{cat}` 后端未注册但仅影响"最新价轮询"小功能（该视图另有主路径可用）|
| G 并发稳定性 | 4 | 4 | 0 | 0 | 3 轮 × 10 并发混合全部干净 |
| H 性能抽样 | 8 | — | — | — | 见下表 |

（A 模块 FAIL 中的 `__NETERR__ TimeoutError` 条目多数为上游 TDX 服务器瞬时慢导致的探针超时，单独重测均正常，未计为缺陷；500 类 FAIL 全部经 curl 二次复现。）

## 性能抽样表

| 请求 | 耗时 | 状态 | 备注 |
|---|---|---|---|
| GET /bars count=800 | 0.16s | 200 | 正常 |
| POST /chanlun/analyze count=800 depth=2 | 2.72s | 200 | 正常 |
| POST /chanlun/multi-level 800 d2 | 25.09s | 200 | 递归双层取数，偏慢但可接受 |
| GET /stock-pick/timing 3 股 | 0.58s | 200 | 正常 |
| GET /security/count | 6.5s / 15.3s | 200 | 上游 TDX 延迟波动 |
| GET /finance | 7.1s | 200 | 偏慢（财务数据接口） |
| GET /minute | 4.6s | 200 | 偏慢 |
| POST /chanlun/multi-level WEEK/MONTH | 21.0s / 27.9s | 200 | 高级别周期计算慢 |
| GET /fund-flow/history | **>280s ×2 超时** | -1 | D11，故障转移失控 |
| chanlun multi-level 空数据股票 | 142–158s | 200（空） | D11 同族 |

---

### 测试副作用清理说明（最终验证）

- 监控任务：本轮创建的全部任务已 `stop`（含 D4 复现产生的 2 个孤儿任务），`GET /monitor/list` 现为空 `{"tasks":[],"count":0}`；`/monitor/alerts/clear` 已执行三次（最后一次清理 9 条 dashboard 探针残留），alerts 现为空。
- 回测策略：A 探针创建的策略已在脚本内 DELETE，无残留。
- 学习/训练数据：`train/score` 与 `learn/mistakes` 的越界用例在服务端校验处 500 失败，**未写入**有效成绩；成功写入的少量记录 player 均为 `探针`，如需可在 DB 中按 player='探针' 清除（涉及数据文件，遵约束未动）。
- 异步任务：全部等待至终态，未遗留 running 任务。
- 服务器 host：未调用 `/server/switch`（仅对非候选 host 发过请求并被 400 拒绝），`save_best_host` 未被探针改变候选。
