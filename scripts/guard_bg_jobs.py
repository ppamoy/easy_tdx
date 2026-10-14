#!/usr/bin/env python3
"""后台任务僵尸/超订守卫 —— 抓 easy_tdx 这类"任务越跑越慢"的根因。

要抓两类问题：
  1. ZOMBIE  : 进程还活着但 CPU 增量 = 0（逻辑卡死），且已存活 > --stall-min
  2. OVERSUBSCRIBE : 同类后台任务并发数 > 核数，导致每个都慢成"很久"

用法:
  python3 scripts/guard_bg_jobs.py                 # 只报告，不动手
  python3 scripts/guard_bg_jobs.py --kill-stalled # 报告 + 杀掉卡死的
  python3 scripts/guard_bg_jobs.py --json          # 机器可读

退出码: 0=健康  1=发现僵尸  2=超订
"""
from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
import time
from dataclasses import dataclass, field, asdict


def cpu_ticks(pid: int) -> int | None:
    """读 /proc/<pid>/stat 的 utime+stime（不含子进程）。"""
    try:
        with open(f"/proc/{pid}/stat") as f:
            data = f.read()
    except OSError:
        return None
    # comm 字段可能含空格/括号，从最后一个 ')' 之后切
    tail = data[data.rfind(")") + 1:].split()
    if len(tail) < 13:
        return None
    try:
        return int(tail[11]) + int(tail[12])  # utime, stime
    except ValueError:
        return None


def proc_state(pid: int) -> str | None:
    try:
        with open(f"/proc/{pid}/stat") as f:
            data = f.read()
    except OSError:
        return None
    return data[data.rfind(")") + 1:].split()[0]


def cmdline(pid: int) -> str:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
    except OSError:
        return ""


_STATE_PATH = os.path.join(
    os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"),
    "easy_tdx", "guard_bg_jobs_seen.json",
)


def _load_seen() -> dict:
    try:
        with open(_STATE_PATH) as f:
            return {int(k): float(v) for k, v in json.load(f).items()}
    except (OSError, ValueError):
        return {}


def _save_seen(seen: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_PATH), exist_ok=True)
        tmp = _STATE_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump({str(k): v for k, v in seen.items()}, f)
        os.replace(tmp, _STATE_PATH)
    except OSError:
        pass


def elapsed_min(pid: int, seen: dict, now: float) -> float:
    """进程已存在多少分钟。

    注意：本容器里 /proc/uptime 是 namespaced 的（约 1.8 天），
    而 /proc/<pid>/stat 的 starttime 来自宿主机（约 66 天），
    两者相减会得到负数甚至荒诞值（ps etimes 报 41 亿秒）。
    因此不依赖内核计时，改为记录"本守卫第一次见到它的时刻"。
    首次见到时返回 0.0（未知），第二次起即为真实存活时长。
    """
    if pid not in seen:
        seen[pid] = now
        return 0.0
    return max(0.0, (now - seen[pid]) / 60.0)


def pgid_of(pid: int) -> int:
    try:
        with open(f"/proc/{pid}/stat") as f:
            data = f.read()
    except OSError:
        return pid
    tail = data[data.rfind(")") + 1:].split()
    try:
        return int(tail[2])
    except (IndexError, ValueError):
        return pid


def has_live_worker(pid: int) -> bool:
    """该进程是否有正在消耗 CPU 的子进程（进程池的父进程在间隙会空闲）。"""
    try:
        with open(f"/proc/{pid}/task/{pid}/children") as f:
            kids = f.read().split()
    except OSError:
        return False
    for k in kids:
        if not k.isdigit():
            continue
        st = proc_state(int(k))
        if st in ("R", "S", "D"):
            return True
    return False


@dataclass
class Finding:
    kind: str                 # "stalled" | "oversubscribed"
    pid: int
    pgid: int
    elapsed_min: float
    cpu_ticks_delta: int
    state: str
    cmd: str
    detail: str = ""
    siblings: list = field(default_factory=list)


# 默认匹配：easy_tdx 的审计/e2e/pytest 后台任务
DEFAULT_PATTERN = re.compile(
    r"(easy_tdx|audit_.*\.py|e2e_.*\.py|pytest\s+tests|multiprocessing\.spawn_main)",
    re.I,
)

# ⚠️⚠️ **常驻服务**——绝不能被"卡死"误判杀掉（实测 2026-10-10 事故）。
#
# 背景：dev 后端（scripts/dev_backend.sh，8001 + --reload）被 cron 守卫
# 当卡死进程杀掉两次（22:00:01、23:00:02），连带 reload 期间的请求全部 502，
# 前端只看到 "Failed to load resource: 502 (Bad Gateway)"。
# 22:00:01 那次还顺手杀了 **Vite 前端**（pid=1427316）。
#
# 误判链条（三条同时成立）：
#   1. `resource_tracker` 是 uvicorn spawn 出来的守护子进程，职责是监听
#      pipe 回收共享资源 —— **天生 CPU 增量=0**，永远不可能有 CPU 消耗；
#   2. 它的命令行含 easy_tdx 路径 ⇒ 命中 DEFAULT_PATTERN；
#   3. kill_stalled 用 `os.killpg(f.pgid)` **按进程组杀** ⇒ 一次带走整个
#      dev 后端（reloader + server + tracker）。
# 同理 Vite dev server 空闲时 CPU 增量也是 0（22:00:01 已实测被杀）。
#
# 所以这里做的是**进程级豁免**，而不是放宽 CPU 判据：
#   - `--reload` / 常驻 web 服务（uvicorn）
#   - Vite dev server（vite / node vitepress 等）
#   - resource_tracker 自身
# ⚠️ 只匹配**自己**的命令行是不够的（实测踩过，牙齿测试复现）：
#   uvicorn --reload 会 spawn 出真正的 server 进程，其命令行是
#     `python -c from multiprocessing.spawn import spawn_main; ... --multiprocessing-fork`
#   **不含 "uvicorn" 字面量** ⇒ 只看自己会漏掉它，豁免形同虚设
#   （我用 --kill-stalled 实测：8001 直接被杀没）。
#   所以判据是**沿 ppid 链向上查祖先**，命中即豁免整组。
SERVICE_PATTERN = re.compile(
    r"("
    r"uvicorn"                      # dev/prod 后端（含 --reload）
    r"|multiprocessing\.resource_tracker"  # uvicorn 的守护子进程
    r"|multiprocessing\.spawn"      # --reload spawn 出的 server 本体
    r"|vite(/|\s|$)"                # 前端 dev server（HMR）
    r"| next-server"                # 其他常驻前端
    r")",
    re.I,
)

# 向上最多查几代（防 ppid 成环 / 异常）
_ANCESTOR_MAX_DEPTH = 8


def _ppid_of(pid: int) -> int | None:
    try:
        with open(f"/proc/{pid}/stat") as f:
            data = f.read()
    except OSError:
        return None
    tail = data[data.rfind(")") + 1:].split()
    try:
        return int(tail[1])
    except (IndexError, ValueError):
        return None


def is_service(cl: str, pid: int | None = None) -> bool:
    """命令行（或其任一祖先）属于常驻服务 → 豁免"卡死"清理。

    传 pid 时沿 ppid 链上溯：--reload 派生的 server 进程命令行里没有
    uvicorn 字样，只看自己必然漏（实测 2026-10-10 牙齿测试复现并修复）。
    """
    if SERVICE_PATTERN.search(cl):
        return True
    if pid is None:
        return False
    seen = {pid}
    cur = _ppid_of(pid)
    for _ in range(_ANCESTOR_MAX_DEPTH):
        if cur is None or cur <= 1 or cur in seen:
            return False
        seen.add(cur)
        if SERVICE_PATTERN.search(cmdline(cur)):
            return True
        cur = _ppid_of(cur)
    return False


def scan(pattern: re.Pattern, sample_s: float) -> tuple[list[Finding], dict]:
    """采样两次 CPU，判定卡死。返回 (findings, stats)。"""
    now = time.time()
    seen = _load_seen()
    pids = []
    for name in os.listdir("/proc"):
        if not name.isdigit():
            continue
        pid = int(name)
        cl = cmdline(pid)
        if not cl or "guard_bg_jobs" in cl:
            continue
        # ⚠️ 常驻服务豁免（uvicorn / vite / resource_tracker）：它们空闲时
        #    CPU 增量天然为 0，判"卡死"必误杀（实测 2026-10-10 两次事故）。
        #    必须传 pid：--reload 派生的 server 命令行不含 uvicorn 字样，
        #    只看自己会漏（牙齿测试实测复现过）。
        if is_service(cl, pid):
            continue
        if not pattern.search(cl):
            continue
        if proc_state(pid) == "Z":
            continue
        pids.append((pid, cl))

    t0 = {pid: cpu_ticks(pid) for pid, _ in pids}
    time.sleep(sample_s)
    t1 = {pid: cpu_ticks(pid) for pid, _ in pids}

    # ⚠️ 按"任务家族"归组：取脚本名作为家族。
    #
    # ⚠️⚠️ 只数**真正干活的叶子进程**，否则并发数会**虚高**：
    #   `scripts/run_bg.sh` → `timeout` → `python 主进程` → `worker×N`
    #   这一串的命令行**全都含同一个脚本名**，直接 len(members) 会把
    #   包装层也算进去。一个 `--workers 2` 的任务会被报成"并发 4"，
    #   让人误以为自己超订（我 2026-10-08 就被这个假警报带偏过）。
    #
    # 判据：命令以 python 解释器开头（不是 bash/timeout/tee），
    #       且**自己没有子 worker**（即不是进程池父进程）。
    all_pids = {pid for pid, _ in pids}
    children: dict[int, list[int]] = {}
    for pid in all_pids:
        try:
            with open(f"/proc/{pid}/task/{pid}/children") as f:
                kids = [int(x) for x in f.read().split()]
        except OSError:
            kids = []
        for k in kids:
            children.setdefault(pid, []).append(k)

    def _is_wrapper(cl: str) -> bool:
        head = cl.strip().split(" ", 1)[0]
        base = os.path.basename(head)
        return base in ("bash", "sh", "timeout", "tee", "setsid", "nohup")

    fam: dict[str, list[int]] = {}
    for pid, cl in pids:
        m = re.search(r"(audit_\w+\.py|e2e_\w+\.py|pytest)", cl)
        if not m:
            continue
        if _is_wrapper(cl):
            continue
        # 进程池父进程不占一个"并发位"，真正占核的是它的 worker
        if children.get(pid):
            continue
        fam.setdefault(m.group(1), []).append(pid)

    ncpu = os.cpu_count() or 1
    findings: list[Finding] = []
    stats = {"ncpu": ncpu, "scanned": len(pids), "families": {}}

    for pid, cl in pids:
        st = proc_state(pid)
        d = (t1[pid] or 0) - (t0[pid] or 0)
        el = elapsed_min(pid, seen, now)
        # ⚠️ 包装层（bash/timeout/tee/setsid）本来就不烧 CPU，
        #    判它"卡死"是**假警报**（tee 只是转发输出，永远等不到 CPU 增量）。
        if _is_wrapper(cl):
            continue
        # 进程池的"父"进程在派发间隙本来就空闲，不算卡死。
        # 判据：它自己没在算、但确实有 worker 子进程在跑。
        if d == 0 and st in ("S", "D", "R") and not has_live_worker(pid):
            findings.append(Finding(
                kind="stalled", pid=pid, pgid=pgid_of(pid), elapsed_min=round(el, 1),
                cpu_ticks_delta=d, state=st, cmd=cl[:200],
                detail="CPU 增量=0，进程存活但不推进（疑似逻辑卡死）",
            ))

    # 清理已消失的 pid，并落盘，供下次算出真实存活时长
    live = {pid for pid, _ in pids}
    _save_seen({k: v for k, v in seen.items() if k in live})

    for key, members in fam.items():
        stats["families"][key] = len(members)
        if len(members) > ncpu:
            findings.append(Finding(
                kind="oversubscribed", pid=members[0], pgid=pgid_of(members[0]),
                elapsed_min=0, cpu_ticks_delta=0, state="-",
                cmd=key,
                detail="并发 %d > 核数 %d，会让每个任务都变慢" % (len(members), ncpu),
                siblings=members,
            ))

    findings = [f for f in findings if f.kind == "oversubscribed" or f.elapsed_min >= 0]
    return findings, stats


def kill_stalled(findings: list[Finding], min_age_min: float) -> list[dict]:
    killed = []
    for f in findings:
        if f.kind != "stalled" or f.elapsed_min < min_age_min:
            continue
        # 🔒 兜底复核：即使 findings 是从别处（如旧版 state/外部脚本）传进来的，
        #    也不能让常驻服务被进程组杀掉。 os.killpg 会把整组带走，
        #    误杀代价太高（dev 后端 + Vite 一起没），这里必须再挡一次。
        #    同理传 f.pid 走祖先链判定（只看自己命令行会漏 spawn_main）。
        if is_service(f.cmd, f.pid):
            continue
        # 只杀进程组，避免留下孤儿 worker
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(f.pgid, sig)
            except (ProcessLookupError, PermissionError):
                try:
                    os.kill(f.pid, sig)
                except ProcessLookupError:
                    break
            time.sleep(2)
            if not os.path.exists(f"/proc/{f.pid}"):
                break
        killed.append({"pid": f.pid, "pgid": f.pgid, "gone": not os.path.exists(f"/proc/{f.pid}")})
    return killed


def loadavg() -> list:
    return [float(x) for x in open("/proc/loadavg").read().split()[:3]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pattern", default=None, help="匹配后台任务的正则（默认覆盖 easy_tdx 审计/e2e/pytest）")
    ap.add_argument("--sample", type=float, default=15.0, help="CPU 采样间隔秒（默认 15）")
    ap.add_argument("--kill-stalled", action="store_true", help="清理卡死进程（会杀进程组）")
    ap.add_argument("--min-age-min", type=float, default=10.0, help="最短存活时间，低于此值不杀（防误杀刚启动的）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    pattern = re.compile(args.pattern, re.I) if args.pattern else DEFAULT_PATTERN
    findings, stats = scan(pattern, args.sample)

    killed = kill_stalled(findings, args.min_age_min) if args.kill_stalled else []

    la = loadavg()
    out = {
        "loadavg": la,
        "load_per_cpu": round(la[0] / stats["ncpu"], 2),
        **stats,
        "findings": [asdict(f) for f in findings],
        "killed": killed,
    }

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print("== 后台任务守卫 ==")
        print("loadavg=%.2f (每核 %.2f)  核数=%d  扫描=%d 个进程"
              % (la[0], la[0] / stats["ncpu"], stats["ncpu"], stats["scanned"]))
        if stats["families"]:
            print("任务家族: " + ", ".join("%s×%d" % (k, v) for k, v in stats["families"].items()))
        stalled = [f for f in findings if f.kind == "stalled"]
        over = [f for f in findings if f.kind == "oversubscribed"]
        print("\n卡死(CPU增量=0): %d" % len(stalled))
        for f in stalled:
            print("  pid=%-8d 存活%6.1f分 state=%s  %s" % (f.pid, f.elapsed_min, f.state, f.cmd[:90]))
        print("\n超订(并发>核数): %d" % len(over))
        for f in over:
            print("  %s -> %s  pids=%s" % (f.cmd, f.detail, f.siblings))
        if killed:
            print("\n已清理: %d" % len(killed))
            for k in killed:
                print("  pid=%-8d pgid=%-8d gone=%s" % (k["pid"], k["pgid"], k["gone"]))
        else:
            print("\n(未执行清理，加 --kill-stalled 才会动手)")

    if killed:
        return 0
    if any(f.kind == "stalled" for f in findings):
        return 1
    if over:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())