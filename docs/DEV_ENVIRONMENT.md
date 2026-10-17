# easy_tdx 开发环境（热修改即时可见）

## 一句话

```bash
bash scripts/dev_backend.sh --detach   # dev 后端 8001（--reload，绝不动生产 8000）
cd web-ui && npx vite                  # dev 前端 3012（HMR，/api 代理到 8001）
```

- 打开 **http://localhost:3012** —— 改 `web-ui/src/**` 保存即生效，**不用 `npm run build`**
- dev 后端 API 文档：http://localhost:8001/docs
- 停止 dev 后端：`bash scripts/dev_backend.sh --stop`

## ⚠️ 端口职责（别串台）

| 端口 | 谁 | 用途 | 改代码 |
|---|---|---|---|
| **8000** | 用户 user systemd 服务 `easy-tdx.service`（`Restart=always`） | **生产**，托管 `web-ui/dist` | 必须先 `npm run build` |
| **8001** | `scripts/dev_backend.sh` | **开发**，带 `--reload`，`EASY_TDX_WEB_DIST=""` | 改 `.py` 自动重启 |
| **3012** | `npx vite` | **开发前端**，HMR | 改 `.vue` 保存即生效 |

**8000 是生产，开发别碰它。** 它是 `~/.config/systemd/user/easy-tdx.service`
（`Restart=always`）—— 杀掉会被自动拉起，硬叠进程会抢端口。而且它
`EASY_TDX_WEB_DIST=web-ui/dist`，托管的是**构建产物**：改了 `.vue` 源码却只看
8000，看到的永远是旧代码。

Vite 的 `/api` 代理默认指向 **8001**（`web-ui/vite.config.ts` 的
`VITE_API_PORT`，默认 `8001`）。要打到生产后端：`VITE_API_PORT=8000 npm run dev`。

## 两个入口的区别（别搞混）

| 入口 | 端口 | 用途 | 改前端代码 |
|---|---|---|---|
| **3012**（Vite dev） | 3012 | **开发**，热更新 | 保存即生效 ✅ |
| **8000**（生产 dist） | 8000 | 看**构建后**产物 | 必须先 `npm run build` ❌ |

⚠️ 8000 端口托管的 `web-ui/dist` 是**构建产物**。改了 `.vue` 源码却只看 8000，
看到的一定是旧代码 —— 这是最容易踩的坑。

## 分别启动

```bash
bash scripts/dev.sh backend     # 只起 dev 后端（**8001**，--reload，不动生产 8000）
bash scripts/dev.sh frontend    # 只起前端（3012，HMR）
bash scripts/dev.sh stop        # 停掉 8001 与 3012（**不会**碰 8000）
```

⚠️ 2026-10-10 修正：`dev.sh backend` 原先会起在 **8000**，那是生产 systemd
服务在用的端口，实测必报 `[Errno 98] address already in use`。
现已改为委托 `scripts/dev_backend.sh`（8001）。`dev.sh stop` 也**不会**再
误杀 8000 的生产服务。

## 实测验证（2026-10-10）

| 项 | 结果 |
|---|---|
| Vite dev 起在 3012 | ✅ HTTP 200 |
| `/api` 代理到后端 | ✅ 页面内 `fetch('/api/v1/chanlun/analyze')` → 200 |
| 前端热更新 | ✅ 改 `.vue` → vite 日志 `hmr update /src/views/SignalCheckView.vue`，页面立刻显示新内容 |
| 后端 `--reload` | ✅ 改 `.py` → 自动重启，服务仍 200 |
| `dev.sh backend` 能起来 | ✅（**修好前起不来**，见下） |

## 修掉的两个启动脚本 bug（实测，2026-10-10）

两个脚本的**后端启动命令都是坏的**，照原样执行后端根本起不来：

1. **`scripts/dev.sh`** 用 `easy_tdx.cli.cmd_web:create_app`
   → 实测 `AttributeError: Attribute not found`（该模块没有 `create_app`）。
   → 已改为 `easy_tdx.web:create_app`（factory 模式）。

2. **`scripts/dev_server.py`** 用 `python -m easy_tdx.cli serve`
   → 实测 `No module named easy_tdx.cli.__main__`（`easy_tdx.cli` 是**包**不是模块）。
   → 已改为 `python -m uvicorn easy_tdx.web:create_app --factory --reload`。

## 完整实测（dev 模式跑通全流程，2026-10-10）

在 **3012**（Vite dev）上实跑：选 600519 → 预设切「自定义」→ 填
`2024-09-02 ~ 2026-10-09` → 次级别选 `MIN_30` → 等待：

```
切到 custom 后日期输入框数: 2
区间套: ["✅ 方向对且显著","✅ 3/3","✅ 方向对且显著","✅ 3/3","0/1 未确认","0/1 未确认","✅ 1/1","✅ 1/1"]
```

与生产 build 结果一致 ⇒ dev 与生产同源，所见即所得。

## 已知注意事项

- **首屏较慢**：Vite dev 首次访问要按需编译模块，可能 10~30s；之后是秒开。
- **Moli 浏览器 30s fetch 上限**：dev 模式下首个复杂请求（如区间套）可能触发。
  生产已加低级别截断护栏（`LOW_MAX_BARS=3000`），dev 同理。
- 若 3012 打不开，先看 `web-ui` 下 `npx vite` 的日志是否报端口占用。
- **Moli 会退化**：Playwright 过 CDP 连久了会莫名超时（实测重启后同样脚本
  立刻通过）。排查顺序：**先 `moli-serve-start --restart`，再怀疑应用代码**。

---

## 🔴 dev 服务被 cron 守卫误杀（502 的真正原因，2026-10-10 实测定位）

**症状**：dev 前端偶发 `Failed to load resource: 502 (Bad Gateway)`，
后端日志里找不到对应的异常，服务"过一会儿自己又好了"。

**根因**：cron 每 30 分钟跑 `scripts/reap_stalled_bg.sh --auto`
（见仓库 `AGENTS.md` §5 的僵尸清理），它把 **dev 后端当卡死进程杀掉**了：

1. `uvicorn --reload` 会 spawn 出 `resource_tracker` 与 `spawn_main` 子进程，
   它们只监听 pipe 回收资源 —— **CPU 增量天然为 0**，永远符合"卡死"判据；
2. 这些进程命令行含 easy_tdx 路径 ⇒ 命中守卫的 `DEFAULT_PATTERN`；
3. `kill_stalled()` 用 `os.killpg()` **按进程组杀** ⇒ reloader + server + tracker
   整组带走，Vite dev server 同理（实测 22:00:01 那次前端也被杀）。

日志铁证（`logs/dev-backend.log` + `~/.local/state/easy_tdx/reap.log` 时间戳比对）：

```
[reap 23:00:02] 已清理: 1  pid=1477488  pgid=1477477   ← 杀掉 dev 后端进程组
[uvicorn 23:00:55] Started reloader process [1558559]   ← 重启
     期间的请求 → 502 Bad Gateway
```

**修法**：`scripts/guard_bg_jobs.py` 增加**常驻服务豁免**（`is_service()`），
覆盖 `uvicorn` / `multiprocessing.resource_tracker` / `multiprocessing.spawn` /
`vite`。关键是**沿 ppid 链向上查祖先** —— 只看自己命令行会漏掉
`spawn_main`（它不含 `uvicorn` 字面量，我第一版修复就漏了，被牙齿测试抓到：
8001 直接被杀没）。

**牙齿（防回归，已固化）**：

- `scripts/guard_teeth_test.sh` —— 跑 `--kill-stalled` 前后比对 8001/3012 端口存活。
  实测：修复版 2→2 PASS；坏版本（去掉豁免）2→0 FAIL。
- `tests/unit/test_dev_scripts_startup.py::test_guard_exempts_long_running_dev_services`
  —— 断言服务被豁免、且**真任务不被豁免**（对照组）。

**dev 后端另加了 `--reload-dir`**（`dev_backend.sh`）：默认 uvicorn 监听
整个工作目录，含 `audit_*/`、`logs/`、`tmp/`，写缓存就会触发无谓重启。
收窄到 `src/` 与 `web-ui/src/`。

## 附：422 的两个来源（实测 2026-10-10）

控制台报 `POST /api/v1/backtest/run 422 (Unprocessable Entity)`。
422 = **参数校验失败**，不是代码崩。定位到两个独立来源：

### 1. `strategy` 字段缺失

后端 `backtest_schemas.py:69` `strategy: str = Field(...)` 是**必填**。
响应体：`{"detail":[{"type":"missing","loc":["body","strategy"],"msg":"Field required"}]}`

来源是「已保存策略 → 一键重验」路径（`StrategiesView.onReverify`）：
localStorage 里的**旧版本保存记录可能没有 strategy 字段**，直传就 422，
用户只看到一个裸 422，不知道发生了什么。

**修法（两层）**：
- `api.ts` 的 `runBacktest` 加预校验：空 strategy **根本不发请求**，
  直接抛「回测请求缺少 strategy（策略名）——该记录可能来自旧版本保存，请重新保存策略后再回测」
- `StrategiesView.onReverify` 入口拦下：「该保存记录缺少 strategy，请删除后重新保存」

### 2. `/bars` 的 `count` 超过 800

后端 `bars.py:74` `count: int = Query(800, ge=1, le=800)`（**TDX 协议单页上限**）。
日志里出现过 `GET /bars?...count=4000` / `count=2000` →
`422 less_than_equal(le=800)`。

**修法**：`fetchBarsDirect` 把单页 count 钳到 `MAX_BARS_PER_PAGE=800`，
宁可多翻一页也不要 422。

### 验证

| 项 | 结果 |
|---|---|
| 7 个页面全量扫 4xx/5xx | ✅ `/`、`/chanlun`、`/backtest`、`/signal-check`、`/strategies`、`/optimize`、`/portfolio` **均无** |
| 前端 vitest | **175 passed**（24 files，新增 4 例 422 guard） |
| 牙齿验证 | ✅ 去掉 strategy guard → 2 例立即变红 |

---

## 附：策略下拉的缠论分组（2026-10-10，2026-10 修订）

> ⚠️ **2026-10 修订**：`chanlun_pair`（缠论买卖点配对）已**废弃删除**。
> 原因：它的区间套过滤（`require_qujiantao`）用 `level_synth` **合成**低级别
> K 线，是**伪区间套**、不符合缠论原文。缠论策略收敛为单一 `chanlun`
> （`stop_loss_pct`/`take_profit_pct` 设为 0 即得原文口径）。
> **真区间套将放前端页面用真实双周期数据实现**，不再走后端合成数据。

回测页策略下拉里现有 **2 个**缠论策略（历史上有 3 个）：

| name | label | 出场规则 |
|---|---|---|
| `chanlun` | 缠论买卖点 | 默认**开启**百分比止损止盈（8% / 25%），可能在同级别卖点前被截断 |
| ~~`chanlun_pair`~~ | ~~缠论买卖点配对~~ | **已废弃删除**（区间套用合成数据，伪区间套） |
| `changying_chanlun` | 长赢缠论综合 | 叠加吴伟志四季周期（播种/成长/收获/储藏） |

### 实测对比（日线 2000 根，4 只票）

| 股票 | chanlun（交易/收益/回撤） | ~~chanlun_pair~~（交易/收益/回撤） |
|---|---|---|
| 600519 | 20 / 54.92% / 40.68% | ~~13 / 62.29% / 63.69%~~ |
| 000651 | 16 / −17.27% / 47.25% | ~~14 / −41.37% / 59.18%~~ |
| 600036 | 17 / 138.90% / 37.04% | ~~11 / 119.68% / 39.15%~~ |
| 000858 | 19 / 64.64% / 47.63% | ~~13 / 133.28% / 59.89%~~ |
| **平均** | **18.0 / 60.30% / 43.15%** | ~~**12.8 / 68.47% / 55.48%**~~ |

**当时结论：不足以判定优劣** —— chanlun_pair 平均收益高 8 个点，但回撤也大 12 个点，
个股互有胜负（4 只里 2:2）。样本太小，当时不做合并/删除决策。

> **后续（已废弃删除）**：用户最终决策删除 `chanlun_pair`，理由是它的
> 区间套用 `level_synth` 合成数据、属伪区间套，而非性能比较问题。

### 当前处理：只分组，不删

用户选择「先不合并，用 optgroup 分组」。于是 `StrategyPicker.vue`：
- 下拉改 `<optgroup>`：**缠论类** / **技术指标类** 两组
- 判定口径：`name` 含 `chanlun` 或 `label` 含「缠」→ 新增缠论策略自动归入
- 选中任一缠论策略时，显示差异说明（原来只对 `chanlun` 生效，
  选非 `chanlun` 缠论策略时不显示 —— 一并修了）

改动零风险：不删任何策略、不改后端、不改历史保存记录。

### 浏览器实测（2026-10-10，localhost:3012）

optgroup 与差异说明均经过**真实浏览器 + 截图确认**（不只是单测）：

```
optgroup数: 2
缠论类(3条): 长赢缠论综合（changying_chanlun）| 缠论买卖点（chanlun）| 缠论买卖点配对（chanlun_pair）
技术指标类(25条): 双均线交叉（ma_cross）| ... （共 25 条）
选中 chanlun_pair 时：差异说明存在=true、V102 提示存在=true

> ⚠️ 以上为 **2026-10-10 当时**的实测快照；`chanlun_pair` 现已废弃删除，
> 当前缠论类仅 2 条（chanlun / changying_chanlun）。
```

截图经视觉模型确认：排版清晰、无溢出/重叠/截断。

### ⚠️ 排障笔记：`/backtest` 不是路由

我一开始用 Playwright 打开 `http://127.0.0.1:3012/backtest`，看到**整页空白**
（app-main 长度为 0，且无 pageerror / console.error），一度以为是自己改挂了组件。
真实原因：

```
[Vue Router warn]: No match found for location with path "/backtest"
```

**回测页的路由是 `/`（根），不是 `/backtest`。** `router.ts:23`
`{ path: '/', name: 'backtest', component: BacktestView }`，
`App.vue:37` `<RouterLink to="/">回测</RouterLink>`。

教训（与 AGENTS.md §1 同源）：SPA 的客户端路由 miss 会**静默白屏** ——
HTTP 仍是 200（Vite/host fallback 返回 index.html），没有 4xx，没有 JS 异常。
用「页面无 4xx」或「无 JS 错误」断言白屏，会把**路由写错**误判成「没问题」。
排查先看 Vue Router 的 warn，再去怀疑组件。

---

## 附：笔端点（分型）改用小圆点（2026-10-10）

> 用户要求：「笔的端点不要用三角形，用小圆点标识吧。所有的缠论图都这样。」

### 改了什么

所有缠论图都复用同一个 `ChanlunChart.vue`（回测页 / 选股 / 今日可操作 / 买卖点核对 /
训练 / 筛查），所以**改一处即覆盖全部**。符号定义收口在 `echarts-setup.ts` 的
`FX_SYMBOL = 'circle'`，组件一律引用它，不允许在 series 里另写死。

**关键取舍：圆点是旋转对称的，`symbolRotate` 对它完全无效。**
原来顶▼/底▲靠 series 级 `symbolRotate: 180` 翻向，改圆点后这条路走不通了，
所以顶/底改由 `symbolOffset` 的 y 方向区分 —— **顶在最高价上方（负 y）、底在最低价下方（正 y）**，
偏移量对称（`props.compact ? -4 : -6` / `+4 / +6`）。

买卖点（1buy/2buy/3buy/…）**仍保留三角形** ▲▼ —— 那是有意的：
三角形能表达方向，用户只要求改笔端点。

### 门禁（两层，都验证过有牙齿）

1. `scripts/check_fx_symbol.py`（已接 CI）：
   - 分型 series 不得出现 triangle
   - 必须引用 `FX_SYMBOL`（保证全站统一）
   - 顶/底 offset 必须反向、非 0、对称
   - 不得用 symbolRotate 标记分型
   - **测试 mock 漏导出 FX_\* 会被拦** —— 我加 `FX_SYMBOL` 时只改了 1 个 mock，
     另外 2 个测试文件没改，结果 **8 个用例**以
     `No "FX_SYMBOL" export is defined on the mock` 崩掉。已按「测试实际 import 的 .vue」
     判定（不能靠文件名 == 组件名，`mmd-chart-contract.test.ts` 这种契约命名会漏检）。
2. `web-ui/src/components/__tests__/ChanlunChart.test.ts`：断言 symbol=circle、
   offset 反向且对称。
   - 牙齿实测：把 symbol 改回 `triangle` → **1 个用例变红**。

### 验证

| 项 | 结果 |
|---|---|
| 前端 vitest | **179 passed**（25 files） |
| vite build | ✅ 已入 dist |
| `check_fx_symbol.py` | ✅ 通过 |
| 牙齿：symbol 退化成 triangle | ✅ exit 1 + 1 用例失败 |
| 牙齿：mock 漏导出 | ✅ exit 1 |

### ⚠️ 没做到的验证：像素级确认

`scripts/e2e_fx_symbol_pixel.py` 写了（用 `getImageData` 量每个分型点的
「上半 vs 下半」前景像素分布：三角形一侧宽度趋近 0 ⇒ ratio→1，圆点上下对称 ⇒ ratio 小），
但**在 Moli 底座上没跑通** —— 撞到

```
timer callback dispatch failed: Window Web IDL callback exceeded 8s and was terminated
```

Moli 的 layout pump 会掐掉 >8s 的回调，ECharts 初始化被打断，
`window.__CHANLUN_CHART__` 拿不到。已实测 canvas 确实渲染（1171×760）、
容器存在、DEV 标志为真，**是底座限制不是应用问题**（AGENTS.md §9.1 缺陷2 同源）。

⇒ **目前最硬的证据是单测 + 静态扫描，不是真实像素。** 请你在浏览器里
   （http://localhost:8000 或 3012 → 缠论测试学习 → 看图分析 → 开始分析）
   肉眼看一眼确认圆点效果。
