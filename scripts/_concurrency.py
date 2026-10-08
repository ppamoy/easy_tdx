"""后台审计/回测脚本共用的并行度约定。

为什么统一在 2：
    本机只有 4 核，且常态要同时负担 —— easy_tdx web 服务、pytest、
    以及正在跑的 agent 本身。审计/回测是 CPU 密集的纯 Python（GIL 内
    多线程无效，必须 ProcessPoolExecutor），worker 数一旦接近核数，
    就会和这些常驻负载正面抢核。

    实测后果（2026-10-07）：`--workers 4` + 4 个卡死未回收的 worker
    长期 100% 占核，导致同一个 session 里**每个后台任务都要等
    40~100 分钟** —— 而模型推理本身 p50 只有 0.7 秒，慢的全是"等"。

    详见 docs/BG_JOB_SLowness_POSTMORTEM.md。

可通过环境变量覆盖（仅在明确知道机器空闲时使用）：
    EASY_TDX_WORKERS=4 .venv/bin/python scripts/audit_xxx.py
"""

from __future__ import annotations

import os

DEFAULT_WORKERS = 2


def resolve_workers(explicit: int | None = None) -> int:
    """算出实际并行度。

    explicit  : 命令行显式传入的 --workers
    环境变量  : EASY_TDX_WORKERS
    默认      : DEFAULT_WORKERS
    """
    if explicit is not None:
        return max(1, explicit)
    env = os.environ.get("EASY_TDX_WORKERS")
    if env and env.strip().isdigit():
        return max(1, int(env.strip()))
    return DEFAULT_WORKERS
