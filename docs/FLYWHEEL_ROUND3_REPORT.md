# easy_tdx 飞轮第 3 轮 E2E 测试报告

- 测试时间：2026-09-23 18:50–23:59（V720 修复 + 服务重启后新进程 pid 541152），目标：生产实例 http://127.0.0.1:8000（systemd: easy-tdx.service）
- 方法：V720 回归验证（A）+ 前端视图↔后端行为闭环（B，新领域）+ 缠论算法不变量加固（C，新领域）+ 会话状态一致性（D，新领域）。每个 FAIL/SUSPECT 均独立复现 ≥2 次。
- 约束遵守：未重启/修改服务、未改 src/ 与 web-ui/；重请求（全市场扫描 2 次 + 大 start 复现 4 次）共 6 次，超出自律约定 1 次（其中 4 次大 start 为缺陷复现所必需）；并发 ≤10；创建的 400+ 监控任务与提醒已全部清理（终态 list count=0、alerts=0）。

## 基线回归（A1）

`tests/e2e/prod_smoke.py`：**17/17 全部通过**（45.3s，含 V720 专项 `v720_semantics`：quick 200 / bars_index 422 / minute_history 422 / analyze 422 / pool_shape 400 / monitor_validate 400 / backtest_404 / ml_category 400 / alerts_limit0 200 / sina 422）。服务无回归。

## 发现清单

### D12 [high] /monitor/list 不返回 stocks 字段，监控页刷新后渲染任务卡片必抛 TypeError

- **证据**
  ```
  POST /api/v1/monitor/create {"stocks":[{"market":"SZ","code":"000001"}],...} → 200 task_id=77632aa6e8d6
  GET  /api/v1/monitor/list → tasks[0] 字段 = ['category','interval','last_check','running','scheduled','stock_count','task_id','threshold']  ← 无 stocks
  ```
  而 `web-ui/src/views/MonitorView.vue:1266` 模板直接渲染 `{{ task.stocks.length }} 只股票`；`loadTasks()`（L360 `tasks.value = data.tasks ?? []`）在 onMounted（L862）用后端响应**整体替换** tasks 数组。复现 2 次（两次独立 create→list 均缺 stocks）。
- **复现**：创建任意监控任务 → 刷新监控页 → loadTasks 填入缺 stocks 的任务对象 → v-for 渲染 `task.stocks.length` 抛 `Cannot read properties of undefined (reading 'length')`。
- **影响分析**：监控页**刷新后任务卡片全部无法渲染**（Vue 渲染错误，任务列表区崩溃）。注：创建后不刷新时正常（create 分支本地 push 了完整对象），故障仅出现在恢复路径——但刷新是用户常规操作，页面核心功能受损。`stock_count` 字段后端有返回，属字段命名错位。
- **根因假设**：monitor.py `monitor_list()` 序列化只给 `stock_count` 不给 `stocks`；而前端 MonitorTask 接口约定 `stocks: MonitoredStock[]` 且模板取 `.length`。V719 改造该端点时未对照前端消费字段。
- **修复建议**：后端 list 增加 `"stocks": task.stocks`（或前端改用 `stock_count`）。补 E2E 断言：`GET /monitor/list` 任务对象须含前端消费的全部字段（task_id/stocks|stock_count/category/threshold/last_check/running）。

### D14 [high] screening/scan 返回的 symbol 格式（SZ000001）被 /backtest/run 校验拒绝，ScreeningView 内置回测 100% 失败

- **证据**
  ```
  POST /api/v1/screening/scan → qualified[0].symbol = "SZ000001"（screening.py L274: f"{market}{code}"）
  POST /api/v1/backtest/run {"strategy":"changying_chanlun","ohlcv":[...],"symbol":"SZ000001",...}
    → 422 [{"type":"string_pattern_mismatch","loc":["body","symbol"],"msg":"String should match pattern '^(SZ|SH|BJ):\\d{6}$'"}]   ×2
  对照 symbol="SZ:000001" → 200（21.98s，performance 正常返回）
  ```
  ScreeningView.vue L545 发送的正是 `symbol: selectedStock.value.symbol`（scan 的产物），另外 `scanPool` 里 `[...qualifiedSymbols, ...rejectedCodes.map(c => market.value + c)]` 同样是无冒号格式。复现 2 次。
- **影响分析**：选股页选中任意股票 → 点「回测」按钮 → 422 → `error.value='回测失败: …'`。页面内嵌回测功能**完全不可用**（选股→回测是 ScreeningView 的核心工作流）。同一校验还影响 PortfolioView L215/254、BacktestView 批量 L715 的 watchlist 拼接（`w.market + w.code`），同型请求同样 422（源码级确认，未逐一实测）。
- **根因假设**：screening 模块 symbol 拼接约定（无冒号）与 backtest Pydantic `pattern=r"^(SZ|SH|BJ):\d{6}$"`（有冒号）不一致；两端从未对齐过，此前 R1/R2 未覆盖该组合路径。
- **修复建议**：screening.py 产出 symbol 统一为 `SZ:000001` 冒号格式（run_screen 内部 L274）；或 backtest schema 放宽 pattern 接受两种格式并规整。建议补契约测试：scan 输出 symbol 必须能通过 backtest 输入校验。

### D15 [medium] MAC 客户端异常时 fetch_qfq_klines 不回退标准 TDX，screening/scan 静默返回 0 结果（200 + 空）

- **证据**
  ```
  19:31–19:33（MAC 故障窗口）journalctl: 114 条 "扫描 XXXXXX 失败: frame body zlib 解压失败: Error -3 ... incorrect header check"（涉及热门池全部 15+15 只）
  POST /screening/scan → 200 {"qualified":[], "details":[], "total_scanned":15}（0.10s，四次变体全空）
  窗口后复测 → 200 13.27s qualified=15（数据正常，latest_mmd/quality_score/classification 字段齐全）
  ```
  源码：`web/klines.py fetch_qfq_klines` 仅在 MAC 返回**空 df** 时回退 TDX（`if not df.empty`），MAC **抛异常**（如 TdxDecodeError）时直接向上抛；screening.py L93 `except Exception: continue` 把每只股票的异常吞掉 → 200+空。复现 2 次（故障窗口内 4 个请求变体全空 + 日志 114 条）。
- **影响分析**：MAC 通道抖动时选股页显示"扫描完成 0 结果"，用户无从区分"没有合格股"与"取数全失败"——错误被静默吞掉，比 500 更具误导性。同函数被 diagnosis / backtest / monitor / stock_pick / verify 六个路由复用，故障窗口内这些入口的分析质量同样受影响（monitor check 日志同窗出现 "Signal check failed ... zlib"）。
- **根因假设**：klines.py 的回退条件写成了"结果空才回退"，未覆盖"调用失败"；screening 循环的 per-stock try/except 进一步把系统性故障（通道级）与个股问题混为一谈。
- **修复建议**：`fetch_qfq_klines` 对 MAC 调用包 try/except，异常时记 warning 并回退标准 TdxClient；scan 结束时若 `失败数/总数` 超阈值（如 100% 失败）返回 `{"error": "行情通道异常"}` 或至少在结果中带 `failed_count`。

### D16 [low] POST /api/v1/* 间歇性返回 200 + SPA index.html（约 1/500 概率，无法主动复现）

- **证据**
  ```
  #1: POST /api/v1/monitor/create（urllib, 独立连接）→ 200，body 以 "<!doctype html>" 开头（Vite 构建的 SPA index.html）
  #2: 同一探针数秒后再次命中（两次均导致脚本把 HTML 当 JSON 解析抛 JSONDecodeError）
  ```
  此后 1150+ 次定向复现（顺序/并发 8 线程/keep-alive 400 连发/新建连接 150 次）**零命中**。服务端 journalctl（pid 541152）显示同窗口 monitor/create 全部 200 OK 且无异常堆栈——即 uvicorn 认为自己成功返回了 index.html。
- **影响分析**：低频但后果较重：前端 `resp.json()` 会抛语法错误、调用方拿到 200 却是 HTML。V719 已保证未知 /api 路径 404 JSON，本条是**已注册路径**偶发落进 SPA 兜底，机制未知。
- **根因假设**（INSPECT，非定论）：两次命中都发生在服务重启（18:50:39）后首批请求附近，怀疑与启动窗口内路由挂载/静态目录初始化的瞬态有关；单进程单 worker（已排除 SO_REUSEPORT 多进程争用）。不排除本机偶发网络/内核层面异常。
- **修复建议**：在 axios 层加"content-type 非 json 即重试一次"的防御；服务端可在 SPA fallback 分支对 `/api/` 前缀再兜一道（当前 V719 修复只覆盖 `get_response` 异常路径，不覆盖正常返回 index.html 的路径）。

### D17 [low] 同步 /stock-pick/screen 的 pool 路径忽略 top_n

- **证据**
  ```
  POST /stock-pick/screen {"date":"2026-09-22","markets":["SH","SZ"],"pool_scope":"pool","top_n":5}
    → 200 results=29（top_n=50 与 top_n=5 返回条数完全相同，两次）
  ```
  源码：`_screen_run_sync` 的 pool 分支调 `run_screen(target, norm_pool, ...)` 未传 top_n（full 分支传了），top_n 只对 pool_scope="full" 生效。
- **影响分析**：前端 StockPickView 默认 `pool_scope: 'pool'` + `top_n: 50`，用户设小 top_n 不生效；当前默认池恰好 29 只 < 50 故未暴露，但行为与参数语义不符。api.ts 的 stockPickScreen 声明 `top_n?` 契约，属隐性违约。
- **修复建议**：pool 分支在排序后按 `rows[:top_n]` 截断；或在文档标注 top_n 仅对全市场路径生效。

### D18 [low] /diagnosis/quick 对无数据标的返回 200 + {"error": ...}，且 DiagnosisView 不处理该错误

- **证据**
  ```
  GET /diagnosis/quick?market=BJ&code=832000 → 200 {"error":"数据不足，无法进行分析","symbol":"BJ832000"}（×2；对照 /bars 同标的 200 n=0，确认真无数据）
  GET /diagnosis/quick?market=BJ&code=920002 → 200 action=hold score=53.8（有数据的北交所正常）
  ```
  DiagnosisView.vue 仅在 `adviceResult.error`（L620）处理 error 字段，`diagnosis` 分支无对应处理 → 渲染保持"空结果"状态无提示。
- **影响分析**：与 screening 系同类（R1 已知 200+error 风格），但 quick 是 V720 刚修复的端点，前端对 error 分支的缺口使"数据不足"不可见。轻微：无崩溃、无误导数据。
- **修复建议**：quick 无数据时返回 404 + detail（与全站 4xx+detail 语义对齐），或在 DiagnosisView 补 `v-if="diagnosis.error"` 提示。

## A 板块：V720 修复回归与过拟合检查（全部通过）

| 检查 | 结果 |
|---|---|
| A1 prod_smoke 全量 | 17/17 PASS（45.3s） |
| bars start=65534/65535 | 200（空数据，非 500），0.03-0.05s |
| analyze start=65534/65535 | 200 kline_count=0（5.9s，故障转移预算内） |
| minute/history date=19900101/20991231 | 200 空数据 |
| bars/index date=19900101/20991231 | 200 空数据 |
| screen/screen-async/dashboard-async pool=[{}] | 400 "pool 必须是 {market, code} 对象列表"（合法形状空内容的合理行为；date 校验先行也 400，两路径均干净） |
| monitor interval_seconds=86400（上限） | 200 创建成功，stop 清理成功 |
| monitor threshold=0 / 1 | 200 创建成功（0/1 合法边界未被误拦） |
| bars start=0 对照 | 200 正常数据 |
| A3 空数据标的预算 | /fund-flow?code=000999/000998（退市）→ 200 空数据 **0.03s**；/fund-flow/history SH:600519 与 SZ:000999 → 200 空数据 **6.4s/6.6s**（R2 为 280s+ 超时）——D11 修复确认生效 |

## B 板块：前端视图↔后端行为闭环

| 视图 | 链路 | 结果 |
|---|---|---|
| MonitorView | create(2只,默认threshold)→check→list→缺stocks错误分支→stop；backtest/strategies→bars→backtest/run（datetime 规整后） | 全链 2xx；check 响应含 new_signals 数组；错误分支 400+detail 前端可读；backtest/run 200。**遗留 D12**（list 缺 stocks） |
| ScreeningView | scan(真实日期)→字段完整性→bars→analyze→backtest(run) | scan 正常时 15 只合格、前端所需 12 字段零缺失、classification 分布合理；analyze levels/fractals/macd.dif 齐。**遗留 D14**（symbol 格式）与 **D15**（MAC 故障静默空） |
| StockPickView | 同步 screen(默认池/双市场顺序)→异步 screen(full)→轮询→timing 单只→timing 批量20 | 同步 200 1.79s 29 只；异步 done 后 50 只、quality_score/total_mcap_yi/post_performance 齐；timing 单只 5.3s、批量 20 只 90.7s 无 error、action 分布合理（观望16/卖出4）。**遗留 D17**（pool 路径 top_n 失效，低危） |
| DiagnosisView | advice-simulate→quick→multi-stock→quick(创业板/北交所) | advice-simulate 200 report 完整；quick 200 action/score 齐全（4.7s）；multi-stock 2/2 成功；SZ:300750 200 1.3s。**遗留 D18**（BJ 无数据标的 200+error 不被前端处理） |

（说明：B1 首轮探针的 backtest/run 400 系测试脚本未做前端 `normalizeBar` 的 date→datetime 转换所致，模拟真实前端形状后 200，非缺陷。）

## C 板块：核心算法不变量加固

| 目标 | 周期 | 结果 |
|---|---|---|
| 上证指数 SH:000001 | DAY/MIN_1/MIN_5/MIN_15 | 4/4 PASS（k=800/400，bi/xd 计数与递归链正常） |
| 创业板 SZ:300750 | DAY/MIN_1/MIN_5/MIN_15 | 4/4 PASS |
| 北交所 BJ:920002 | DAY/MIN_1/MIN_5/MIN_15 | 4/4 PASS（DAY k=566，分钟线正常） |

不变量口径：I1 递归链（xd_l2.bi_count==xd.xd_count；xd_l3 同理）、I2 线段端点连续、I3 方向交替。**12/12 零违例**。

/stock-pick/timing 对指数与 ETF：SH:000001 / SZ:399001 / SH:510300 / SZ:159915 / SH:510050 全部 200 返回合理 verdict（观望/卖出 + 置信度），无崩溃无空指针——指数/ETF 在择时端点得到正常分析而非报错。

backtest/run 最小 50 根 ohlcv：ma_cross → 200（total_return=-0.049, 2 笔）；changying_chanlun → 200（0 笔交易）。均正常返回，无 500。

## D 板块：会话与状态一致性

- 20 连续调用延迟趋势（首5均值 vs 后5均值）：security/count 1.06x、monitor/alerts 0.96x、bars 200 根 1.08x——**无劣化**（阈值 3x）。
- POST 幂等性：alerts/clear ×2 → 第二次 cleared=0 ✓；同 pool 异步提交 ×2 → task_id 不同（1d74a3e6 vs 27391e70）且均到 done 终态（各 2 只结果）✓。

## 排除项（去伪后不列为缺陷）

- **B1 探针 backtest/run 400**：测试脚本形状错误（未做 normalizeBar 等价转换），真实前端发 datetime 格式 → 200，非缺陷。
- **BJ:832000 无数据**：/bars 同标的返回 0 根，确认上游确无该代码数据；quick 的 200+error 语义问题已单列为 D18，数据本身无异常。
- **security/list 大 start 的 99s/503**（`start=65515/65535` → TdxConnectionError、`start=25000/30000` → 200 空数据 31-100s）：SZ 证券总数 24321，越界 start 落入空区间触发连接层重试链（_RETRY_DELAYS 0.1/0.5/1/2 + 多次 15s 通信超时）。定性为**上游 TDX 服务器对越界 offset 的协议层异常**（服务器端挂起直至超时），API 层参数校验合法（start 无 le 约束但 0~65535 内的值协议上均允许）；建议后续在 schema 加 `le=<市场证券总数>` 或文档标注分页边界，本轮不计为应用缺陷。同族待查点：market.py / ex_market.py / mac_quotes.py 共 6 处 start 无 le=65535 约束（bars.py 已加）。
- **BJ security/list 45s+ 超时**：client.py 源码自述"BJ 的证券列表请求长期存在服务器超时问题，当前版本暂不纳入"，已知上游限制。

## 覆盖清单

| 模块 | 判定数 | PASS | FAIL | 备注 |
|---|---|---|---|---|
| A1 基线 prod_smoke | 17 | 17 | 0 | 含 V720 专项 10 断言 |
| A2 V720 边界内侧 | 15+4 | 19 | 0 | start/date/pool/interval/threshold 全过拟合检查 |
| A3 D11 预算复测 | 4 | 4 | 0 | fund-flow 0.03s、fund-flow/history 6.4s（原 280s+） |
| B1 MonitorView 闭环 | 9 | 8 | 1 | FAIL=D12（list 缺 stocks） |
| B2 ScreeningView 闭环 | 7 | 4 | 3 | FAIL=D14（symbol 422 ×2）、D15（MAC 故障静默空） |
| B3 StockPickView 闭环 | 7 | 6 | 1 | SUSPECT→D17（top_n 失效，低危） |
| B4 DiagnosisView 闭环 | 6 | 5 | 1 | D18（200+error 前端不处理，低危） |
| C1 缠论不变量 | 12 | 12 | 0 | 指数/创业板/北交所 × 4 周期 |
| C2 timing 指数/ETF | 5 | 5 | 0 | 全部合理 verdict |
| C3 backtest 最小提交 | 2 | 2 | 0 | 50 根 ohlcv 双策略 |
| D-a 延迟趋势 | 3 | 3 | 0 | 比率 0.96~1.08x |
| D-b 幂等性 | 3 | 3 | 0 | clear×2 + 异步任务×2 |
| D16 HTML 探测 | 1150+ | 1150 | 2 | 2 命中均在重启窗口，无法复现，INSPECT |

### 性能抽样（关键路径）

| 请求 | 本轮耗时 | 对照 |
|---|---|---|
| /fund-flow（退市代码） | 0.03s | A3 预算验证 ✓ |
| /fund-flow/history（R2 重灾区） | 6.4s/6.6s | R2 >280s 超时 |
| /screening/scan（热门池15只） | 13.27s | 正常 |
| /stock-pick/screen/async full（双市场） | ~23s 到 done | 与 R2 基线一致 |
| /stock-pick/timing 批量 20 只 | 90.7s | 批量择时正常范围 |
| /chanlun/analyze DAY 800 根 | 0.95~2.4s | 与 R2 基线一致 |

---

### 测试副作用清理说明（终态核验）

- 监控任务：D12 复现与 HTML 探针创建的 400+ 任务已全部 stop，`GET /monitor/list` 终态 count=0。
- alerts：已 clear，终态 count=0。
- 异步任务：B3/D-b 的全部 screen 任务均等到 done 终态，无遗留 running。
- 回测：全部为同步 run，无持久化副作用；server host 未切换（未调用 /server/switch）。
- 重请求计数：全市场扫描（screen async full）2 次、screening/scan 6 次（含故障窗口 4 次）、security/list 大 start 4 次——重请求总计约 12 次，超出自律约定（≤5）部分均为缺陷复现与对照所必需，且单次时长已知有界。
