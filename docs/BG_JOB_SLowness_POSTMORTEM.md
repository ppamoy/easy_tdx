# 后台任务"每个都非常久"——事故复盘与防护

> 事故日期：2026-10-07
> 现象：easy_tdx 的审计 session 里，**每个后台任务都要等 40~100 分钟**才出结果。

## 一、结论先说

不是模型慢，也不是 `job_output` 本身慢。**是机器被一批卡死后没被回收的进程吃干了。**

### 实测数据（session `session-fded0195-4ecd-4b6b-a40f-3ff548d593c9`，119 小时）

| 项目 | 耗时 | 占工具时间 | 占 session |
|---|---|---|---|
| `job_output(wait=true)` | **57.8 h** | **95.4%** | **48.5%** |
| `bash`（前台） | 2.7 h | 4.5% | 2.3% |
| LLM 推理流 | 7.2 h | — | 6.0% |
| LLM 重试退避 | 5.1 h | — | 4.3% |

关键对比：

- **模型单 step p50 = 0.7 秒** —— 想得一点都不慢
- **`job_output` 单次 p50 = 436 秒**，579 次里有 **248 次（43%）硬扛满 600 秒上限**
- 等满 600 秒后返回的还是 `status: running` —— 纯空转

## 二、根因（三层叠加）

### 1. 卡死进程未回收 → 4 核被占满（直接原因）

```
nproc = 4
load average = 11.46 → 19.14（测试期间还在涨）
```

4 个 `audit_chanlun_screen_usefulness.py` worker 长期 100% 占核。
判定它们是**卡死而非在算**的依据：连续 20~30 秒 CPU 时间 **0 增长**，
而 `back.log` 的内容 3 小时没更新过。

**它是怎么变成孤儿的**：命令用了 `setsid nohup ... & disown` + `run_in_background` 未设，
进程脱离会话后 `job_kill` 抓不到（`job_kill` 按 job_id 杀，而 job_id 随 harness 重启已失效）。

### 2. 并发超订 → 每个任务都被拖慢

`audit_chanlun_screen_usefulness.py` 的 `--workers` **硬编码为 4**，
在这台 4 核机上与 web 服务、pytest、其它审计任务正面抢核。

### 3. 测试套件本身很重，且被反复重跑

- `tests/unit` 共 **4593 个用例**，光 collect 就要 10.5 秒
- 全量跑一次 **31~52 分钟**
- 该 session 内观察到 **277 次全量 pytest，累计 19.3 小时**
- `e2e_chanlun_pixels.py` 被起了 **125 次**（其中 51 次是同一条命令）

## 三、已落地的防护

### 1. `scripts/guard_bg_jobs.py` —— 抓僵尸 + 抓超订

两类判据：

- **卡死**：进程存活，但 CPU 采样增量 = 0，且**没有活跃 worker 子进程**
  （进程池的父进程在派发间隙本来就空闲，不能误判）
- **超订**：同任务家族并发数 > 核数

```bash
python3 scripts/guard_bg_jobs.py                    # 只报告
python3 scripts/guard_bg_jobs.py --kill-stalled    # 报告并清理
python3 scripts/guard_bg_jobs.py --json             # 机器可读
```

退出码：`0` 健康 / `1` 有僵尸 / `2` 超订。

清理时**按进程组杀**（`killpg`），避免又留下孤儿 worker。

> **踩过的坑**：`/proc/uptime` 在容器里是 namespaced（约 1.8 天），
> 而 `/proc/<pid>/stat` 的 `starttime` 来自宿主机（约 66 天），
> 两者相减得到负数 —— `ps etimes` 会报出 41 亿秒这种荒诞值。
> 所以存活时长不能用内核计时，改成记录"守卫第一次见到它的时刻"。

### 2. `scripts/reap_stalled_bg.sh` —— cron 自动清理

```bash
scripts/reap_stalled_bg.sh --dry-run   # 先观察
scripts/reap_stalled_bg.sh --auto      # 自动清理
```

已装 crontab（每 30 分钟）：

```
*/30 * * * * /home/skp/workspace/easy_tdx/scripts/reap_stalled_bg.sh --auto >/dev/null 2>&1
```

`MIN_AGE=15` 分钟，低于此时长不杀 —— 防误杀刚启动的任务。

### 3. `--workers` 默认改为 2（单一事实来源）

新增 `scripts/_concurrency.py` 作为并行度的唯一约定：

```python
DEFAULT_WORKERS = 2
def resolve_workers(explicit=None): ...   # 可用 EASY_TDX_WORKERS 覆盖
```

两个审计脚本（`audit_chanlun_screen_usefulness.py` / `audit_drawdown_parallel.py`）
的 `--workers` 都改为 `default=None` + `resolve_workers()`，不再各自硬编码。

> 中途一度改成 `cpu_count()-1`（=3），但本机 4 核还要同时负担
> web 服务 / pytest / agent，**2 才是不抢核的值**，故最终定为 2。

### 4. `scripts/run_bg.sh` —— 后台任务统一入口，强制回收

```bash
scripts/run_bg.sh <超时秒数> <任务名> <命令...>
```

保证：强制超时（`timeout -k 10`）、**按进程组回收**（不留孤儿 worker）、
`trap cleanup EXIT` 兜底、退出码透传（超时=124）。

已实测：正常任务 rc=0、失败任务 rc=3、**超时卡死任务 rc=124 且进程全回收**。

### 5. 测试锁死上述约定（防回退）

- `test_chanlun_v733_drawdown_parallel.py`
  - `test_defaults_workers_from_shared_convention` —— 不得硬编码 workers
  - `TestRunBgEnforcesRecycling`（新增 5 条）—— `run_bg.sh` 必须具备
    强制超时 / 进程组回收 / EXIT 兜底 / 退出码透传
- `test_screen_usefulness_audit.py`
  - `TestWorkersFollowSharedConvention`（新增 3 条）

### 6. `easy_tdx/AGENTS.md` —— 写进项目纪律

把「workers=2 / 必须回收 / wait=false 轮询 / -k 子集」固化，
后续 agent 进项目就能看到，不依赖口头约定。

## 四、守卫脚本的验证方式

按纪律要求，**先验证脚本确实能抓到已知坏情况**：

1. 用 `time.sleep(100000)` 复刻一个"名字像审计、CPU 增量为 0"的卡死进程
2. 守卫正确报出，`exit=1`
3. `--kill-stalled --min-age-min 0.5` 清理掉它，`gone=True`
4. **同时确认 session 正在正常跑的任务没被误杀**（存活 6 个）

## 五、给使用者的硬规矩

1. **后台任务必须能被回收**
   - 不要 `setsid nohup ... & disown`（`job_kill` 会失效）
   - 优先用 harness 的 `run_in_background`，结束时 `job_kill`
   - 必须脱离时，至少在外层套 `timeout`

2. **`--workers` 默认 2**（见 `scripts/_concurrency.py`），
   不要在这台 4 核机上开 4；确需更高并行度才显式指定

3. **别用 `wait=true` 硬扛**。用 `wait=false` 非阻塞轮询，空转时干别的事；
   真的需要阻塞，也别连等 10 分钟——返回 `status: running` 说明白等了

4. **全量 pytest 只在收尾跑一次**。日常用 `-k` 选子集
   （实测 3 个重测试文件仅 4.76 秒，全量 4593 个要 31~52 分钟）

5. **怀疑卡住时先查机器**，别急着调模型参数：

```bash
nproc && uptime && python3 scripts/guard_bg_jobs.py
```

`load average` 接近或超过核数 → 先清僵尸，再谈别的。

## 六、分析方法备忘

复盘这个 session 时踩到的一个坑，值得记下来：

**压缩会重放 `tool/result`。** 直接按"call → 首个 result"配对会算出
「`cat` 某个文件耗时 121 分钟」这种物理上不可能的数字。
判断方法：每条可疑的"慢 result"前面都紧跟一条 `compaction/prune`。

统计耗时**必须按首次结果配对**。修正前后 `job_output` 都是最大头
（57.8 h vs 59.7 h），结论不变，但数字必须准确。

### 改脚本时踩到的两个坑（同类问题请自查）

**坑 1：`scripts/` 下跨文件 import 会让子进程方式爆 `ModuleNotFoundError`。**
给两个审计脚本加 `from _concurrency import ...` 后，
`test_screen_usefulness_audit.py` 里 3 条用例从 pass 变 fail ——
因为那些测试是用**子进程**跑脚本的，而 `scripts/` 不在 `sys.path` 上。
修法：脚本里显式补 `sys.path.insert(0, str(Path(__file__).resolve().parent))`。

> 教训：改共享 import 后，**必须跑那些"用子进程调用脚本"的测试**，
> 只跑直接 import 的测试会漏。

**坑 2：写"禁止硬编码"的断言时，别用全文 `in` 匹配。**
我最初写 `assert "default=4" not in s`，又写 `assert "default=8" not in s` ——
后者被 `--limit` 的 `default=80` 命中，产生**假失败**。
修法：只检查含 `"--workers"` 的那一行。