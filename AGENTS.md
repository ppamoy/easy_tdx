# 后台任务纪律（本机 4 核，必读）

> 背景：2026-10-07 一个 session 里"每个后台任务都非常久"，
> 实测 `job_output` 累计空等 **57.8 小时**（占工具时间 95.4%），
> 而模型推理 p50 只有 **0.7 秒** —— 慢的全是"等"，不是"算"。
> 完整复盘见 [docs/BG_JOB_SLowness_POSTMORTEM.md](docs/BG_JOB_SLowness_POSTMORTEM.md)。

本机只有 **4 核**，且常态要同时负担 web 服务、pytest、agent 本身。
所以下面四条是硬规矩，不是建议。

## 1. `--workers` 默认 2，不要在这台机器上开 4

CPU 密集的回测/审计必须用进程池（GIL 内多线程无效），
worker 数一旦接近核数就会和常驻负载正面抢核。

- 并行度统一取 `scripts/_concurrency.py` 的 `DEFAULT_WORKERS`（=2）
- 确需更高并行度时才显式 `--workers N`，或用 `EASY_TDX_WORKERS=N` 覆盖
- **禁止**在脚本里硬编码 `default=4` / `default=8`

## 2. 后台任务必须可回收：统一走 `timeout` + 退出即回收

卡死没人管是本次事故的直接原因。启动后台任务一律走包装脚本：

```bash
scripts/run_bg.sh <超时秒数> <任务名> <命令...>

# 例
scripts/run_bg.sh 1800 screen-usefulness \
    .venv/bin/python scripts/audit_chanlun_screen_usefulness.py --limit 60
```

它保证三件事：

- **强制超时**：到点必死（`timeout -k 10`）
- **按进程组回收**：`kill -TERM -$$` / `kill -KILL -$$`，
  不会出现"父死了 worker 还活着占核"
- **退出兜底**：`trap cleanup EXIT`，脚本被杀也不漏
- **退出码透传**：超时=124、失败=原码，不会被 `tee` 吞成 0

❌ **禁止** `setsid nohup ... & disown` 之后再 `disown`：
进程脱离会话后 `job_kill` 抓不到，只能靠 `pkill` 手动收尸。
（本次事故里那 4 个卡死 worker 就是这么变成孤儿的。）

## 3. 轮询用 `wait=false`，别用 `wait=true` 硬扛 600 秒

`job_output(wait=true)` 的上限约 600 秒。事故中 **248 次调用（43%）
硬扛满上限**，等到的还是 `status: running` —— 纯空转，累计 57.8 小时。

正确姿势：

```python
job_output(job_id="bash-123", wait=False)   # 非阻塞，立刻返回
# 还是 running？去干别的，别干等
```

只有当你**真的没别的事可做**时才 `wait=true`。

## 4. 全量 pytest 只在收尾跑一次，日常用 `-k` 选子集

`tests/unit` 共 **4593 个用例**，全量跑一次 **17~52 分钟**（视负载）。
事故 session 内观察到 **277 次全量跑，累计 19.3 小时** —— 大量重复。

实测对照：

```bash
# 全量（收尾才跑）
.venv/bin/python -m pytest tests/unit -q

# 日常：只跑受影响的（3 个重文件仅 4.76 秒）
.venv/bin/python -m pytest tests/unit -q -k "screen_usefulness or drawdown_parallel"
```

## 5. 怀疑卡住时先查机器，别急着调模型参数

模型不是瓶颈。先看：

```bash
nproc && uptime && .venv/bin/python scripts/guard_bg_jobs.py
```

- `load average` 接近/超过核数 → 先清僵尸
- 守卫报「卡死」→ `--kill-stalled` 清掉
- 守卫报「超订」→ 调低 `--workers`

已装 crontab（每 30 分钟自动清理，`MIN_AGE=15` 防误杀）：

```
*/30 * * * * /home/skp/workspace/easy_tdx/scripts/reap_stalled_bg.sh --auto
```

## 6. 别重复跑同一个任务

事故里 `e2e_chanlun_pixels.py` 被起了 **125 次**（51 次是同一条命令）。
起任务前先看一眼有没有现成结果：

```bash
ls -la ~/.local/state/easy_tdx/bg_jobs/    # run_bg.sh 的日志都在这
```
