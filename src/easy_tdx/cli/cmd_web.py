"""easy-tdx serve — 启动 Web API 服务器。"""

from __future__ import annotations

import threading
import time
import webbrowser
from datetime import date, datetime, timedelta

import click


@click.command("serve")
@click.option("--host", default="0.0.0.0", help="监听地址")
@click.option("--port", default=8000, type=int, help="监听端口")
@click.option("--tdx-host", default=None, help="TDX 服务器地址（默认自动选择最优）")
@click.option("--tdx-port", default=None, type=int, help="TDX 服务器端口")
@click.option("--reload", is_flag=True, help="开发模式（自动重载）")
@click.option(
    "--open-browser/--no-open-browser",
    default=True,
    help="启动后自动打开浏览器（默认开启，PyInstaller 打包后老人双击即用）",
)
@click.option(
    "--changying-scheduler/--no-changying-scheduler",
    default=True,
    help="凌晨调度全市场树/粮/菜标记（半年主跑 + 季报兜底，默认开启）",
)
def serve(
    host: str,
    port: int,
    tdx_host: str | None,
    tdx_port: int | None,
    reload: bool,
    open_browser: bool,
    changying_scheduler: bool,
) -> None:
    """启动 Web API 服务器（需要安装 easy-tdx[web]）。"""
    try:
        import uvicorn
    except ImportError:
        click.echo(
            "错误：缺少 web 依赖。请运行: pip install easy-tdx[web]",
            err=True,
        )
        raise SystemExit(1) from None

    # 启动后延迟打开浏览器：uvicorn 需要约 1-2 秒绑定端口，过早打开会
    # 命中 connection refused。用后台 Timer 而非阻塞主线程。
    if open_browser and not reload:
        # 0.0.0.0 / 127.0.0.1 在浏览器里用 localhost 打开（更友好）。
        display_host = "localhost" if host in ("0.0.0.0", "127.0.0.1") else host
        url = f"http://{display_host}:{port}"
        # 1.5 秒通常足够本地端口就绪；uvicorn 启动慢的机器可适当延长。
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    if changying_scheduler and not reload:
        threading.Thread(
            target=_changying_scheduler_loop,
            daemon=True,
            name="changying-scheduler",
        ).start()

    if reload:
        uvicorn.run(
            "easy_tdx.web:app_factory",
            host=host,
            port=port,
            reload=True,
            factory=True,
        )
    else:
        from easy_tdx.web import create_app

        app = create_app(host=tdx_host, port=tdx_port)
        uvicorn.run(app, host=host, port=port)


# 半年主跑窗口：1 月 / 7 月的首个周六（财报披露季 4/8/10 月结束后，
# 树/粮/菜 point-in-time 输入在 1/7 月已包含完整中报/年报口径）。
_MARK_MAIN_MONTHS = (1, 7)
_MARK_MAIN_HOUR = 0
_MARK_MAIN_MINUTE = 5

# 进程内互斥：防止调度线程与手动 changying-mark 同时跑（SQLite 全量替换
# 非原子，并发写会互相踩踏）。
_marks_refresh_lock = threading.Lock()


def _is_first_saturday(dt: datetime) -> bool:
    """是否 1/7 月的首个周六（半年主跑窗口）。"""
    return dt.month in _MARK_MAIN_MONTHS and 1 <= dt.day <= 7 and dt.weekday() == 5


def _changying_scheduler_loop() -> None:
    """凌晨调度（守护线程，失败仅打印告警）。

    - 半年主跑：1/7 月首个周六 00:05 全市场重算树/粮/菜标记；
    - 季报兜底：其余周六 00:05 检查 gpcw 缓存是否出现新报告期，出现才重跑；
    - 自检：每天 00:05 记录 marks 快照元信息（标的数/更新时间），
      超过 35 天未更新则告警。
    """
    import logging

    logger = logging.getLogger("changying-scheduler")
    from easy_tdx.fundamental.marks import (
        derive_pool_from_marks,
        detect_new_report_period,
        marks_selfcheck,
        refresh_changying_marks,
    )

    while True:
        now = datetime.now()
        next_run = now.replace(
            hour=_MARK_MAIN_HOUR, minute=_MARK_MAIN_MINUTE, second=0, microsecond=0
        )
        if next_run <= now:
            next_run += timedelta(days=1)
        time.sleep(max(1.0, (next_run - now).total_seconds()))
        wake = datetime.now()
        try:
            # 自检：每天记录快照状态，超过 35 天未更新告警
            meta = marks_selfcheck()
            if meta.get("updated_at"):
                age_days = (wake - datetime.fromisoformat(meta["updated_at"])).days
                if age_days > 35:
                    logger.warning(
                        "长盈全市场标记已 %s 天未更新（上次 %s，%s 只），树/粮/菜覆盖可能过期",
                        age_days,
                        meta.get("trade_date"),
                        meta.get("count"),
                    )
                else:
                    logger.info(
                        "marks 自检：count=%s date=%s updated_at=%s",
                        meta.get("count"),
                        meta.get("trade_date"),
                        meta.get("updated_at"),
                    )
            # 周六才考虑重算（半年主跑或季报兜底）
            if wake.weekday() != 5:
                continue
            is_main = _is_first_saturday(wake)
            has_new_period = detect_new_report_period()
            if not (is_main or has_new_period):
                logger.info("非主跑窗口且无新报告期，跳过全市场标记刷新")
                continue
            if not _marks_refresh_lock.acquire(blocking=False):
                logger.warning("另有 marks 刷新在进行，本次跳过")
                continue
            try:
                out = refresh_changying_marks(date.today())
                logger.info(
                    "长盈全市场标记刷新完成 count=%s by_category=%s date=%s",
                    out.get("count"),
                    out.get("by_category"),
                    out.get("trade_date"),
                )
                pool = derive_pool_from_marks()
                if pool:
                    logger.info(
                        "精选池已从 marks 派生：count=%s date=%s",
                        pool.get("count"),
                        pool.get("trade_date"),
                    )
            finally:
                _marks_refresh_lock.release()
        except Exception as e:  # noqa: BLE001
            logger.warning("长盈全市场标记刷新失败: %s", e)
