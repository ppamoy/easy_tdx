"""离线本地数据读写命令 —— 读取本地通达信数据文件 & 从服务端同步写入。"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

if TYPE_CHECKING:
    import pandas as pd

    from ..client import TdxClient
    from ..models.bar import SecurityBar


@click.group()
def offline() -> None:
    """离线本地数据读写（读取本地通达信数据文件 & 从服务端同步写入）。

    读取需要本地已安装通达信并下载过对应数据。
    sync-daily 可从服务端获取最新日线并追加到本地 .day 文件。

    示例：

      easy-tdx offline home

      easy-tdx offline daily SZ 000001 --table

      easy-tdx offline min SH 600519 --type lc5 --table

      easy-tdx offline ex-files --table

      easy-tdx offline ex-daily 29#A1801 --table

      easy-tdx offline sync-daily SZ 000001

      easy-tdx offline sync-daily SH 600519 --vipdoc C:\\new_jyplug\\vipdoc
    """
    pass


@offline.command()
def home() -> None:
    """检测并显示通达信安装目录。"""
    from ..offline import detect_tdx_home

    tdx_home = detect_tdx_home()
    if tdx_home is None:
        click.echo("未检测到通达信安装目录，请设置 TDX_HOME 环境变量")
        raise SystemExit(1)
    click.echo(str(tdx_home))


@offline.command()
@click.argument("market")
@click.argument("code")
@click.option("--count", default=0, type=int, help="返回条数（0=全部）")
@click.option("--table", "use_table", is_flag=True, help="表格输出")
@click.option("--output", "output_fmt", type=click.Choice(["json", "table", "csv"]), default="json")
def daily(
    market: str,
    code: str,
    count: int,
    use_table: bool,
    output_fmt: str,
) -> None:
    """读取 A 股日线数据（.day 文件）。

    MARKET: 市场代码（SZ/SH）
    CODE: 6 位股票代码

    示例：

      easy-tdx offline daily SZ 000001 --table

      easy-tdx offline daily SH 600519 --count 30 --table
    """
    import pandas as pd

    from .output import print_error, print_output
    from .parsers import parse_market

    fmt = "table" if use_table else output_fmt

    try:
        from ..offline import find_daily_bar_file, read_daily_bars

        filepath = find_daily_bar_file(parse_market(market), code)
        bars = read_daily_bars(filepath)
    except Exception as e:
        print_error(str(e))
        raise SystemExit(1)

    if not bars:
        click.echo("未读取到数据，请确认通达信已下载该股票的日线数据")
        raise SystemExit(0)

    rows = [
        {
            "datetime": f"{b.year}-{b.month:02d}-{b.day:02d}",
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "vol": b.vol,
            "amount": b.amount,
        }
        for b in (bars[-count:] if count > 0 else bars)
    ]
    print_output(pd.DataFrame(rows), fmt)


@offline.command()
@click.argument("market")
@click.argument("code")
@click.option(
    "--type",
    "bar_type",
    type=click.Choice(["5min", "lc1", "lc5"]),
    default="5min",
    help="分钟线类型: 5min(.5) / lc1(.lc1) / lc5(.lc5)",
)
@click.option("--count", default=0, type=int, help="返回条数（0=全部）")
@click.option("--table", "use_table", is_flag=True, help="表格输出")
@click.option("--output", "output_fmt", type=click.Choice(["json", "table", "csv"]), default="json")
def min(
    market: str,
    code: str,
    bar_type: str,
    count: int,
    use_table: bool,
    output_fmt: str,
) -> None:
    """读取分钟线数据（.5 / .lc1 / .lc5 文件）。

    MARKET: 市场代码（SZ/SH）
    CODE: 6 位股票代码

    示例：

      easy-tdx offline min SZ 000001 --table

      easy-tdx offline min SH 600519 --type lc1 --count 100 --table
    """
    import pandas as pd

    from .output import print_error, print_output
    from .parsers import parse_market

    fmt = "table" if use_table else output_fmt

    try:
        from ..offline import read_5min_bars, read_lc_min_bars
        from ..offline.finders import find_5min_bar_file, find_lc1_bar_file, find_lc5_bar_file

        mkt = parse_market(market)
        if bar_type == "5min":
            filepath = find_5min_bar_file(mkt, code)
            bars = read_5min_bars(filepath)
        elif bar_type == "lc1":
            filepath = find_lc1_bar_file(mkt, code)
            bars = read_lc_min_bars(filepath)
        else:
            filepath = find_lc5_bar_file(mkt, code)
            bars = read_lc_min_bars(filepath)
    except Exception as e:
        print_error(str(e))
        raise SystemExit(1)

    if not bars:
        click.echo("未读取到数据，请确认通达信已下载该股票的分钟线数据")
        raise SystemExit(0)

    rows = [
        {
            "datetime": f"{b.year}-{b.month:02d}-{b.day:02d} {b.hour:02d}:{b.minute:02d}",
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "vol": b.vol,
            "amount": b.amount,
        }
        for b in (bars[-count:] if count > 0 else bars)
    ]
    print_output(pd.DataFrame(rows), fmt)


@offline.command("ex-files")
@click.option("--table", "use_table", is_flag=True, help="表格输出")
def ex_files(use_table: bool) -> None:
    """列出扩展市场可用的日线数据文件。

    文件位于 vipdoc/ds/lday/ 目录下。
    """
    import pandas as pd

    from ..offline.paths import detect_tdx_home
    from .output import print_error, print_output

    fmt = "table" if use_table else "json"

    tdx_home = detect_tdx_home()
    if tdx_home is None:
        print_error("未检测到通达信安装目录，请设置 TDX_HOME 环境变量")
        raise SystemExit(1)

    lday_dir = tdx_home / "vipdoc" / "ds" / "lday"
    if not lday_dir.is_dir():
        print_error(f"扩展市场目录不存在: {lday_dir}")
        raise SystemExit(1)

    files = sorted(lday_dir.glob("*.day"))
    if not files:
        click.echo("扩展市场目录为空，请在通达信中下载扩展市场数据")
        raise SystemExit(0)

    rows = [{"filename": f.name, "size_kb": round(f.stat().st_size / 1024, 1)} for f in files]
    print_output(pd.DataFrame(rows), fmt)


@offline.command("ex-daily")
@click.argument("filename")
@click.option("--count", default=0, type=int, help="返回条数（0=全部）")
@click.option("--table", "use_table", is_flag=True, help="表格输出")
@click.option("--output", "output_fmt", type=click.Choice(["json", "table", "csv"]), default="json")
def ex_daily(
    filename: str,
    count: int,
    use_table: bool,
    output_fmt: str,
) -> None:
    """读取扩展市场日线数据（期货/港股/外盘）。

    FILENAME: 文件名（如 29#A1801）或完整路径

    示例：

      easy-tdx offline ex-daily 29#A1801 --table

      easy-tdx offline ex-daily 12#A_IXIC --count 30 --table
    """
    from pathlib import Path

    import pandas as pd

    from ..offline import read_ex_daily_bars
    from ..offline.paths import detect_tdx_home
    from .output import print_error, print_output

    fmt = "table" if use_table else output_fmt

    filepath = Path(filename)
    if not filepath.is_file():
        # 路径穿越防护（审计 #16）：仅当 filename 是裸文件名（不含路径分隔符 / \ 与
        # 父目录引用 ..）时，才允许拼接到 vipdoc 目录下，防止 "../foo" 写出目录之外。
        # 允许通达信扩展行情文件名的常见字符（含 #，如 "29#A1801"、"12#A_IXIC"）。
        if re.search(r"[\\/]|(\.\.)", filename):
            raise click.BadParameter("filename 禁止包含路径分隔符(/ \\)或父目录引用(..)")
        tdx_home = detect_tdx_home()
        if tdx_home is not None:
            filepath = tdx_home / "vipdoc" / "ds" / "lday" / f"{filename}.day"

    try:
        bars = read_ex_daily_bars(filepath)
    except Exception as e:
        print_error(str(e))
        raise SystemExit(1)

    if not bars:
        click.echo("未读取到数据，请确认文件存在且已下载对应数据")
        raise SystemExit(0)

    rows = [
        {
            "datetime": f"{b.year}-{b.month:02d}-{b.day:02d}",
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "vol": b.vol,
            "settlement": b.settlement,
        }
        for b in (bars[-count:] if count > 0 else bars)
    ]
    print_output(pd.DataFrame(rows), fmt)


@offline.command()
@click.argument("filepath")
@click.option("--count", default=0, type=int, help="返回条数（0=全部）")
@click.option("--table", "use_table", is_flag=True, help="表格输出")
@click.option("--output", "output_fmt", type=click.Choice(["json", "table", "csv"]), default="json")
def gbbq(
    filepath: str,
    count: int,
    use_table: bool,
    output_fmt: str,
) -> None:
    """读取股本变迁数据（gbbq 文件）。

    FILEPATH: gbbq 文件路径

    示例：

      easy-tdx offline gbbq C:\\new_jyplug\\T0002\\hq_cache\\gbbq --table
    """
    import pandas as pd

    from ..offline import read_gbbq
    from .output import print_error, print_output

    fmt = "table" if use_table else output_fmt

    try:
        records = read_gbbq(filepath)
    except Exception as e:
        print_error(str(e))
        raise SystemExit(1)

    if not records:
        click.echo("未读取到数据")
        raise SystemExit(0)

    rows = [
        {
            "market": r.market,
            "code": r.code,
            "datetime": r.datetime,
            "category": r.category,
            "hongli_panqianliutong": r.hongli_panqianliutong,
            "peigujia_qianzongguben": r.peigujia_qianzongguben,
            "songgu_qianzongguben": r.songgu_qianzongguben,
            "peigu_houzongguben": r.peigu_houzongguben,
        }
        for r in (records[-count:] if count > 0 else records)
    ]
    print_output(pd.DataFrame(rows), fmt)


@offline.command()
@click.argument("filepath")
@click.option("--count", default=0, type=int, help="返回条数（0=全部）")
@click.option("--table", "use_table", is_flag=True, help="表格输出")
@click.option("--output", "output_fmt", type=click.Choice(["json", "table", "csv"]), default="json")
def financial(
    filepath: str,
    count: int,
    use_table: bool,
    output_fmt: str,
) -> None:
    """读取历史财务数据（gpcw*.dat / gpcw*.zip）。

    FILEPATH: 财务数据文件路径

    示例：

      easy-tdx offline financial C:\\new_jyplug\\vipdoc\\sz\\gpcw.zip --count 5 --table
    """
    import pandas as pd

    from ..offline import read_history_financial
    from .output import print_error, print_output

    fmt = "table" if use_table else output_fmt

    try:
        records = read_history_financial(filepath)
    except Exception as e:
        print_error(str(e))
        raise SystemExit(1)

    if not records:
        click.echo("未读取到数据")
        raise SystemExit(0)

    display = records[-count:] if count > 0 else records
    rows = [
        {
            "code": r.code,
            "market": r.market.value,
            "report_date": r.report_date,
        }
        for r in display
    ]
    print_output(pd.DataFrame(rows), fmt)


@offline.command()
@click.argument("block_dir")
@click.option("--table", "use_table", is_flag=True, help="表格输出")
@click.option("--output", "output_fmt", type=click.Choice(["json", "table", "csv"]), default="json")
def blocks(
    block_dir: str,
    use_table: bool,
    output_fmt: str,
) -> None:
    """读取自定义板块数据。

    BLOCK_DIR: 自定义板块目录路径（如 C:\\new_jyplug\\T0002\\blocknew）

    示例：

      easy-tdx offline blocks C:\\new_jyplug\\T0002\\blocknew --table
    """
    import pandas as pd

    from ..offline import read_customer_blocks
    from .output import print_error, print_output

    fmt = "table" if use_table else output_fmt

    try:
        result = read_customer_blocks(block_dir)
    except Exception as e:
        print_error(str(e))
        raise SystemExit(1)

    if not result:
        click.echo("未读取到板块数据")
        raise SystemExit(0)

    rows = [
        {
            "blockname": b.blockname,
            "type": b.block_type,
            "stock_count": len(b.codes),
            "codes": ",".join(b.codes[:10]) + ("..." if len(b.codes) > 10 else ""),
        }
        for b in result
    ]
    print_output(pd.DataFrame(rows), fmt)


# ---------------------------------------------------------------------------
# sync-daily：从服务端同步日线到本地 .day 文件
# ---------------------------------------------------------------------------


def _df_to_bars(df: pd.DataFrame) -> list[SecurityBar]:
    """将日线 DataFrame 转换为 SecurityBar 列表（按日期升序）。"""
    from ..models.bar import SecurityBar

    bars: list[SecurityBar] = []
    for _, row in df.iterrows():
        dt = row["date"]
        bars.append(
            SecurityBar(
                open=row["open"],
                close=row["close"],
                high=row["high"],
                low=row["low"],
                vol=row["vol"],
                amount=row["amount"],
                year=dt.year,
                month=dt.month,
                day=dt.day,
                hour=0,
                minute=0,
            )
        )
    bars.sort(key=lambda b: b.year * 10000 + b.month * 100 + b.day)
    return bars


def _is_index_code(exchange: str, code: str) -> bool:
    """根据市场和代码前缀判断是否为指数。

    指数需要调用 get_index_bars()（服务端响应每条记录多 4 字节），
    而非 get_security_bars()。
    """
    head = code[:2]
    if exchange == "sh":
        return head in ("00", "88", "99")
    if exchange == "sz":
        return head == "39"
    return False


def _fetch_all_daily_bars(
    client: TdxClient,
    market: int,
    code: str,
    need_full: bool = False,
    is_index: bool = False,
) -> list[SecurityBar]:
    """从服务端分页获取全部日线数据。

    Args:
        client: 已连接的 TdxClient。
        market: 市场代码（0=SZ, 1=SH）。
        code: 6 位股票代码。
        need_full: True 表示拉取全量历史（空文件场景），
                   False 表示只拉最近一页（增量更新）。
        is_index: True 表示指数，使用 get_index_bars()。

    Returns:
        SecurityBar 列表（按日期升序）。
    """
    from ..models.enums import KlineCategory, Market

    mkt = Market(market)
    fetch_fn = client.get_index_bars if is_index else client.get_security_bars

    all_bars: list[SecurityBar] = []
    start = 0
    page_size = 800
    max_pages = 50 if need_full else 1  # 50 页 = 40000 条，足够覆盖 A 股全部历史

    for _ in range(max_pages):
        df = fetch_fn(mkt, code, KlineCategory.DAY, start, page_size)
        if df.empty:
            break
        all_bars.extend(_df_to_bars(df))
        if len(df) < page_size:
            break  # 最后一页不满，已无更多数据
        start += page_size

    # 去重并按日期升序排列（跨页可能有重叠）
    seen: set[tuple[int, int, int]] = set()
    unique: list[SecurityBar] = []
    for b in all_bars:
        key = (b.year, b.month, b.day)
        if key not in seen:
            seen.add(key)
            unique.append(b)
    unique.sort(key=lambda b: b.year * 10000 + b.month * 100 + b.day)
    return unique


def _sync_one_daily(client: TdxClient, filepath: Path) -> tuple[int, str]:
    """同步单只股票日线，返回 (写入条数, 状态消息)。"""
    from ..offline import append_daily_bars, get_last_bar_date
    from ..offline.daily_bar import _SECURITY_COEFFICIENTS, _detect_security_type

    # 文件名 → 市场 + 代码
    name = filepath.name.lower()  # e.g. sh600000.day
    exchange = name[:2]  # "sh" or "sz"
    code = name[2:8]
    market = 1 if exchange == "sh" else 0  # Market.SH=1, Market.SZ=0

    # 判断是否需要全量拉取（空文件 → 全量，有数据 → 增量）
    last_date = get_last_bar_date(filepath)
    need_full = last_date is None

    # 判断是否为指数（指数需要 get_index_bars，响应格式不同）
    is_index = _is_index_code(exchange, code)

    # 从服务端分页获取日线
    bars = _fetch_all_daily_bars(client, market, code, need_full=need_full, is_index=is_index)
    if not bars:
        return 0, "服务端无数据"

    # 检测证券类型获取系数
    sec_type = _detect_security_type(filepath.name)
    price_coeff, vol_coeff = _SECURITY_COEFFICIENTS.get(sec_type, (0.01, 0.01))

    # 追加写入
    written = append_daily_bars(filepath, bars, price_coeff, vol_coeff)
    if written > 0:
        return written, f"+{written}"
    return 0, "已是最新"


@offline.command("sync-daily")
@click.argument("market")
@click.argument("code")
@click.option("--vipdoc", default=None, help="vipdoc 目录路径（默认自动检测）")
def sync_daily(market: str, code: str, vipdoc: str | None) -> None:
    """从服务端同步日线数据到本地 .day 文件。

    自动检测本地文件末尾日期，从服务端分页获取缺失的数据并追加写入。
    空文件自动全量下载，已有数据只做增量更新。
    建议在通达信关闭时执行，避免文件被锁定。

    MARKET: 市场代码（SZ/SH）
    CODE: 6 位股票代码

    示例：

      easy-tdx offline sync-daily SZ 000001

      easy-tdx offline sync-daily SH 000001 --vipdoc C:\\new_jyplug\\vipdoc
    """
    from ..client import TdxClient
    from ..offline import find_daily_bar_file
    from .output import print_error
    from .parsers import parse_market

    mkt = parse_market(market)

    try:
        filepath = find_daily_bar_file(mkt, code, vipdoc)
        click.echo(f"目标文件: {filepath}")

        click.echo("正在连接服务端获取日线数据...")
        with TdxClient.from_best_host() as client:
            written, msg = _sync_one_daily(client, filepath)

        if written > 0:
            click.echo(f"✓ 成功写入 {written} 条新记录")
        else:
            click.echo(f"本地已是最新，无需写入 ({msg})")

    except PermissionError:
        click.echo(f"✗ 文件被锁定，请关闭通达信后重试: {filepath}", err=True)
        raise SystemExit(1)
    except Exception as e:
        print_error(str(e))
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# sync-all：一键同步全部日线
# ---------------------------------------------------------------------------


@offline.command("sync-all")
@click.option("--vipdoc", default=None, help="vipdoc 目录路径（默认自动检测）")
def sync_all(vipdoc: str | None) -> None:
    """一键同步全部本地日线数据（沪深全市场）。

    扫描 vipdoc 下所有 .day 文件，自动连接服务端获取最新数据并追加写入。
    建议在通达信关闭时执行，避免文件被锁定。

    示例：

      easy-tdx offline sync-all

      easy-tdx offline sync-all --vipdoc C:\\new_jyplug\\vipdoc
    """
    import time

    from ..client import TdxClient
    from ..offline.paths import resolve_vipdoc

    try:
        vipdoc_path = resolve_vipdoc(vipdoc)
    except Exception as e:
        click.echo(f"✗ {e}", err=True)
        raise SystemExit(1)

    # 1. 扫描所有 .day 文件
    all_files: list[Path] = []
    for exchange in ("sh", "sz"):
        lday_dir = vipdoc_path / exchange / "lday"
        if lday_dir.is_dir():
            all_files.extend(sorted(lday_dir.glob("*.day")))

    if not all_files:
        click.echo("未找到任何 .day 文件，请确认 vipdoc 路径正确")
        raise SystemExit(0)

    total = len(all_files)
    click.echo(f"发现 {total} 个 .day 文件，开始同步...")

    # 2. 连接服务端，逐个同步
    success = 0
    skipped = 0
    failed = 0
    total_written = 0

    with TdxClient.from_best_host() as client:
        for idx, filepath in enumerate(all_files, 1):
            name = filepath.name
            try:
                written, msg = _sync_one_daily(client, filepath)
                total_written += written
                if written > 0:
                    success += 1
                else:
                    skipped += 1
                click.echo(f"  [{idx}/{total}] {name}: {msg}")
            except PermissionError:
                failed += 1
                click.echo(f"  [{idx}/{total}] {name}: ✗ 文件被锁定", err=True)
            except Exception as e:
                failed += 1
                click.echo(f"  [{idx}/{total}] {name}: ✗ {e}", err=True)

            # 每 100 只暂停一小段，避免请求过快被服务器断开
            if idx % 100 == 0:
                time.sleep(0.2)

    # 3. 汇总
    click.echo("")
    summary = (
        f"同步完成: {total} 只 | "
        f"更新 {success} | 已是最新 {skipped} | "
        f"失败 {failed} | 共写入 {total_written} 条"
    )
    click.echo(summary)


@offline.command()
@click.argument("market")
@click.argument("code")
@click.option(
    "--file",
    "file_path",
    default=None,
    help="直接指定 .day 文件路径（缺省自动检测通达信目录）",
)
@click.option("--count", default=0, type=int, help="读取K线条数（0=全部）")
@click.option("--max-hold", default=10, type=int, help="建议最大持有根数（1-60）")
@click.option(
    "--output",
    "output_fmt",
    type=click.Choice(["json", "table", "csv", "md"]),
    default="json",
)
def advice(
    market: str,
    code: str,
    file_path: str | None,
    count: int,
    max_hold: int,
    output_fmt: str,
) -> None:
    """用本地 .day 日线跑 V102 建议回放（无需网络/通达信连接）。

    MARKET: 市场代码（SZ/SH，作为上下文；--file 时仍须给出）
    CODE: 6 位股票代码

    读取本地日线 → 缠论分析 → 对 3买/3卖 信号生成 V102 建议
    → 用 advice_simulator 逐笔回放（止损/止盈/到期）→ 输出汇总与每笔明细。

    示例：

      easy-tdx offline advice SZ 000001 --output csv
      easy-tdx offline advice SZ 000001 --file /path/to/sh600000.day --output csv
    """
    import pandas as pd

    from .output import print_error, print_output
    from .parsers import parse_market

    try:
        from ..offline import find_daily_bar_file, read_daily_bars
    except Exception as e:
        print_error(f"离线模块不可用: {e}")
        raise SystemExit(1)

    try:
        if file_path is not None:
            bars = read_daily_bars(file_path)
        else:
            bars = read_daily_bars(find_daily_bar_file(parse_market(market), code))
    except Exception as e:
        print_error(str(e))
        raise SystemExit(1)

    if not bars:
        click.echo("未读取到数据，请确认通达信已下载该股票的日线数据")
        raise SystemExit(0)

    if count > 0:
        bars = bars[-count:]

    # ── 组装 DataFrame → 缠论分析 → V102 建议回放 ──
    from easy_tdx.backtest.advice_simulator import collect_signal_advices, simulate_advice_batch
    from easy_tdx.chanlun import ChanlunAnalyser

    df = pd.DataFrame(
        [
            {
                "datetime": f"{b.year}-{b.month:02d}-{b.day:02d}",
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "vol": b.vol,
                "amount": b.amount,
            }
            for b in bars
        ]
    )
    analyser = ChanlunAnalyser(code=code, frequency="daily")
    result = analyser.process_klines(df)

    closes = [float(k.close) for k in result.klines]
    highs = [float(k.high) for k in result.klines]
    lows = [float(k.low) for k in result.klines]

    advices = collect_signal_advices(result, closes, highs, lows, max_hold)
    report = simulate_advice_batch(highs, lows, closes, advices)
    report["symbol"] = f"{market.upper()}{code}"
    report["bars"] = len(closes)
    report["signals"] = len(result.mmds)
    report["advices"] = advices

    import json as _json

    if output_fmt == "md":
        _print_advice_md(report)
        return
    if output_fmt == "json":
        click.echo(_json.dumps(report, ensure_ascii=False, indent=2))
        return
    # table/csv：只输出标量列（嵌套的 advices/trades 不展开）
    scalar = {k: v for k, v in report.items() if not isinstance(v, (list, dict))}
    print_output(pd.DataFrame([scalar]), output_fmt)


def _print_advice_md(report: dict[str, object]) -> None:
    """V364: offline advice 单标 Markdown 报告（与 advice-batch --md 对齐）。"""
    from typing import Any, cast

    symbol = report.get("symbol", "")
    reason_cn = {"stop": "止损", "tp1": "止盈", "expire": "到期", "invalid": "无效"}
    trades = cast(list[dict[str, Any]], report.get("trades") or [])
    advices = cast(list[dict[str, Any]], report.get("advices") or [])
    click.echo(f"# 离线 V102 建议回放报告（{symbol}）")
    click.echo()
    click.echo(
        f"K线 **{report.get('bars', 0)}** 根 | 缠论信号 **{report.get('signals', 0)}** | "
        f"建议 **{report.get('count', 0)}** 笔"
    )
    click.echo()
    click.echo("| # | 入场 | 止损 | 止盈1 | 出场价 | 原因 | 收益% |")
    click.echo("|---|-----|-----|------|-------|------|-------|")
    for i, t in enumerate(trades):
        a = advices[i] if i < len(advices) else {}
        reason = reason_cn.get(str(t.get("exit_reason", "")), t.get("exit_reason", ""))
        click.echo(
            f"| {i + 1} | {a.get('entry_price', 0.0):.2f} | "
            f"{a.get('stop_loss', 0.0):.2f} | {a.get('take_profit_1', 0.0):.2f} | "
            f"{t.get('exit_price', 0.0):.2f} | {reason} | {t.get('return_pct', 0.0):+.2f} |"
        )
    click.echo()
    click.echo(
        f"**汇总**：胜率 {cast(float, report.get('win_rate', 0.0)) * 100:.0f}% | "
        f"平均收益 {cast(float, report.get('avg_return', 0.0)):+.2f}% | "
        f"累计 {cast(float, report.get('total_return', 0.0)):+.2f}%"
    )
    click.echo(
        f"**出场分布**：止损 {cast(float, report.get('stop_rate', 0.0)) * 100:.0f}% / "
        f"止盈 {cast(float, report.get('tp_rate', 0.0)) * 100:.0f}% / "
        f"到期 {cast(float, report.get('expire_rate', 0.0)) * 100:.0f}%"
    )


def _watch_signal_row(symbol: str, mmd: Any, date_str: str) -> dict[str, object]:
    """V368: 构造 watch 新信号行（含 V102 建议的入场/止损/止盈）。

    抽为纯函数便于单测（合成行情难以触发 3买/3卖，直接喂构造的 MMD）。
    """
    scorecard = getattr(mmd, "_signal_quality_scorecard", None) or {}
    decision = getattr(mmd, "_decision_support", None) or {}
    return {
        "symbol": symbol,
        "type": mmd.mmd_type.value,
        "date": date_str,
        "confidence": round(mmd.confidence, 2),
        "v102_grade": scorecard.get("overall_grade") or None,
        "advice": decision.get("action_recommendation") or None,
        "entry_price": decision.get("entry_price"),
        "stop_loss": decision.get("stop_loss"),
        "take_profit_1": decision.get("take_profit_1"),
    }


def _is_within_since_days(date_str: str, since_days: int) -> bool:
    """V373: watch 信号日期是否落在最近 N 天窗口内（0=不过滤）。

    日期解析失败时**保守跳过**（不报告），与 V372 运行时行为一致；
    抽为纯函数便于单测（原来内联在 watch 循环中，无直接测试覆盖）。
    """
    if since_days <= 0:
        return True
    try:
        sig_date = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except ValueError:
        return False  # 日期解析失败则保守跳过
    return sig_date >= date.today() - timedelta(days=since_days)


def _fmt_opt_price(value: object) -> str:
    """V377: 建议价格字段格式化（None → '-'，数字 → 两位小数）。"""
    if value is None:
        return "-"
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    return str(value)


def _render_watch_report(rows: list[dict[str, object]]) -> str:
    """V377: 将本轮 watch 新信号渲染为 Markdown 报告（含 V102 建议）。

    抽为纯函数便于单测（与 _watch_signal_row 同思路）；文件写入由 watch 负责。
    """
    lines: list[str] = []
    lines.append("# 离线 V102 信号监控报告")
    lines.append("")
    lines.append(f"- 扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 新信号: {len(rows)} 条")
    lines.append("")
    lines.append("| 标的 | 信号 | 日期 | 置信度 | 质量 | 建议 | 入场 | 止损 | 止盈1 |")
    lines.append("|------|------|------|--------|------|------|------|------|-------|")
    for r in rows:
        lines.append(
            f"| {r['symbol']} | {r['type']} | {r['date']} | {r['confidence']} | "
            f"{r['v102_grade'] or '-'} | {r['advice'] or '-'} | "
            f"{_fmt_opt_price(r['entry_price'])} | {_fmt_opt_price(r['stop_loss'])} | "
            f"{_fmt_opt_price(r['take_profit_1'])} |"
        )
    lines.append("")
    return "\n".join(lines)


def _advice_batch_one(
    filepath: Path, count: int, max_hold: int
) -> tuple[dict[str, object] | None, dict[str, object]]:
    """V378: 处理单个 .day 文件，返回 (report, row)（异常 → (None, error 行)）。

    抽为模块级纯函数：advice-batch 串行/并行统一调用，且便于单测与保持输出顺序。
    """
    import pandas as pd

    from easy_tdx.backtest.advice_simulator import (
        collect_signal_advices,
        simulate_advice_batch,
    )
    from easy_tdx.chanlun import ChanlunAnalyser

    from ..offline import read_daily_bars

    name = filepath.name.lower()  # e.g. sh600000.day
    mkt = name[:2].upper()  # SH / SZ
    code = name[2:8]
    symbol = f"{mkt}{code}"
    try:
        bars = read_daily_bars(filepath)
        if not bars:
            return None, {"symbol": symbol, "error": "无数据"}
        if count > 0:
            bars = bars[-count:]
        if len(bars) < 30:
            return None, {"symbol": symbol, "error": "K线不足(30)"}
        df = pd.DataFrame(
            [
                {
                    "datetime": f"{b.year}-{b.month:02d}-{b.day:02d}",
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "vol": b.vol,
                    "amount": b.amount,
                }
                for b in bars
            ]
        )
        analyser = ChanlunAnalyser(code=code, frequency="daily")
        result = analyser.process_klines(df)
        closes = [float(k.close) for k in result.klines]
        highs = [float(k.high) for k in result.klines]
        lows = [float(k.low) for k in result.klines]
        if len(closes) < 30:
            return None, {"symbol": symbol, "error": "K线不足(30)"}
        buy_hold = (closes[-1] / closes[0] - 1.0) * 100.0 if closes[0] > 0 else 0.0
        advices = collect_signal_advices(result, closes, highs, lows, max_hold)
        report = simulate_advice_batch(highs, lows, closes, advices)
        report["symbol"] = symbol
        row = {
            "symbol": symbol,
            "bars": len(closes),
            "signals": len(result.mmds),
            "advice_count": report["count"],
            "win_rate": round(float(report.get("win_rate", 0.0)) * 100, 1),
            "avg_return": round(float(report.get("avg_return", 0.0)), 2),
            "total_return": round(float(report.get("total_return", 0.0)), 2),
            "buy_hold": round(buy_hold, 2),
            "stop_rate": round(float(report.get("stop_rate", 0.0)) * 100, 1),
            "tp_rate": round(float(report.get("tp_rate", 0.0)) * 100, 1),
            "expire_rate": round(float(report.get("expire_rate", 0.0)) * 100, 1),
        }
        return report, row
    except Exception as e:  # noqa: BLE001
        return None, {"symbol": symbol, "error": str(e)}


@offline.command("advice-batch")
@click.option("--dir", "day_dir", default=None, help=".day 文件目录（缺省自动检测通达信 vipdoc）")
@click.option("--limit", default=0, type=int, help="最多处理的股票数（0=全部）")
@click.option("--count", default=0, type=int, help="每只读取K线条数（0=全部）")
@click.option("--max-hold", default=10, type=int, help="建议最大持有根数（1-60）")
@click.option("--workers", default=1, type=int, help="并行处理线程数（1=串行，2+ 批量实证加速）")
@click.option(
    "--output",
    "output_fmt",
    type=click.Choice(["json", "table", "csv", "md"]),
    default="json",
)
def advice_batch(
    day_dir: str | None,
    limit: int,
    count: int,
    max_hold: int,
    workers: int,
    output_fmt: str,
) -> None:
    """离线批量 V102 建议回放：扫描本地 .day 目录逐只跑建议实证并汇总。

    --dir 缺省时自动检测通达信 vipdoc 目录；每只从文件名推断市场/代码
    （sh600000.day → SH/600000）。输出每只汇总 + 全池聚合（json/table/csv/md）。
    --workers N 用多线程并行处理（默认 1=串行，行为不变；输出顺序按文件名稳定）。

    示例：

      easy-tdx offline advice-batch --dir /path/to/vipdoc/sz/lday --limit 10 --output md
      easy-tdx offline advice-batch --dir /path/to/vipdoc/sz/lday --workers 4 --output csv
    """
    import pandas as pd

    from .output import print_error, print_output

    try:
        from ..offline.paths import resolve_vipdoc
    except Exception as e:
        print_error(f"离线模块不可用: {e}")
        raise SystemExit(1)

    # 1. 定位 .day 目录
    try:
        if day_dir is not None:
            lday_dir = Path(day_dir)
        else:
            lday_dir = resolve_vipdoc(None) / "sz" / "lday"
        if not lday_dir.is_dir():
            print_error(f".day 目录不存在: {lday_dir}")
            raise SystemExit(1)
        files = sorted(lday_dir.glob("*.day"))
    except Exception as e:
        print_error(str(e))
        raise SystemExit(1)

    if not files:
        click.echo(f"目录 {lday_dir} 中没有 .day 文件")
        raise SystemExit(0)
    if limit > 0:
        files = files[:limit]

    # 2. 逐只跑 V102 建议回放（--workers 并行，默认 1 串行；输出按文件名顺序稳定）
    from easy_tdx.backtest.advice_simulator import summarize_batch

    if workers < 1:
        raise click.BadParameter("--workers 至少为 1")

    # 仅处理沪深 A 股 .day 文件（与串行版一致：跳过其他文件）
    valid_files = [
        f
        for f in files
        if f.name.lower().startswith(("sh", "sz")) and f.name.lower().endswith(".day")
    ]

    if workers > 1:
        from concurrent.futures import ThreadPoolExecutor

        def _run_one(fp: Path) -> tuple[dict[str, object] | None, dict[str, object]]:
            return _advice_batch_one(fp, count, max_hold)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(_run_one, valid_files))
    else:
        results = [_advice_batch_one(fp, count, max_hold) for fp in valid_files]

    reports: list[dict[str, object]] = []
    rows: list[dict[str, object]] = []
    for report, row in results:
        if report is not None:
            reports.append(report)
        rows.append(row)

    # 3. 聚合 + 输出
    summary = summarize_batch(reports)
    if output_fmt == "md":
        click.echo("# 离线 V102 批量建议实证报告")
        click.echo()
        click.echo(
            f"扫描 **{len(files)}** 只 | 有建议 **{summary['symbols']}** | "
            f"总建议 **{summary['advice_count']}** | 胜率 **{summary['win_rate'] * 100:.0f}%** | "
            f"平均 **{summary['avg_return']:+.2f}%** | "
            f"正收益 **{summary['positive_symbols']}/{summary['symbols']}**"
        )
        click.echo()
        click.echo("| 标的 | K线 | 信号 | 建议数 | 胜率% | 平均收益% | 累计% | 买入持有% |")
        click.echo("|------|-----|------|--------|-------|-----------|-------|-----------|")
        for r in rows:
            if "error" in r:
                click.echo(f"| {r['symbol']} | - | - | - | - | - | - | {r['error']} |")
            else:
                click.echo(
                    f"| {r['symbol']} | {r['bars']} | {r['signals']} | {r['advice_count']} | "
                    f"{r['win_rate']} | {r['avg_return']:+.2f} | {r['total_return']:+.2f} | "
                    f"{r['buy_hold']:+.2f} |"
                )
        return

    # json/table/csv：每只一行（含 summary 字段便于聚合查看）
    out_df = pd.DataFrame(rows)
    out_df["summary_symbols"] = summary["symbols"]
    out_df["summary_advice_count"] = summary["advice_count"]
    out_df["summary_win_rate"] = round(summary["win_rate"] * 100, 1)
    out_df["summary_avg_return"] = round(summary["avg_return"], 2)
    out_df["summary_positive_symbols"] = summary["positive_symbols"]
    print_output(out_df, output_fmt)


@offline.command("watch")
@click.option("--dir", "day_dir", default=None, help=".day 文件目录（缺省自动检测通达信 vipdoc）")
@click.option("--limit", default=0, type=int, help="最多扫描的股票数（0=全部）")
@click.option("--count", default=0, type=int, help="每只读取K线条数（0=全部）")
@click.option(
    "--state",
    "state_file",
    default=None,
    help="已见信号状态文件路径（缺省 ~/.easy_tdx/offline_watch_state.json）",
)
@click.option("--interval", default=0, type=int, help="连续轮询间隔秒数（0=单次扫描；Ctrl+C 退出）")
@click.option(
    "--since-days",
    "since_days",
    default=0,
    type=int,
    help="只看最近 N 天的新信号（0=不按时间过滤）",
)
@click.option("--reset", "do_reset", is_flag=True, help="清空已见信号状态，重新建立基线")
@click.option(
    "--info", "do_info", is_flag=True, help="显示状态文件信息（路径 + 已记录信号数）后退出"
)
@click.option("--output", "output_fmt", type=click.Choice(["json", "table", "csv"]), default="json")
@click.option(
    "--out",
    "out_file",
    default=None,
    help="将本轮新信号以 JSONL 追加写入文件（供脚本/定时任务消费）",
)
@click.option(
    "--report",
    "report_file",
    default=None,
    help="将本轮新信号以 Markdown 报告追加写入文件（供人阅读/定时任务存档）",
)
def watch(
    day_dir: str | None,
    limit: int,
    count: int,
    state_file: str | None,
    interval: int,
    since_days: int,
    do_reset: bool,
    do_info: bool,
    output_fmt: str,
    out_file: str | None,
    report_file: str | None,
) -> None:
    """离线信号监控：扫描本地 .day 目录，报告「新」发现的 3买/3卖 信号 + V102 建议摘要。

    用状态文件记录上次已见过的信号（symbol+type+date），本次只报告新增，
    实现无网络轮询监控（类比 Web 监控页「新信号」面板）。首次运行将当前全部
    信号记为基线并输出。--interval N 开启连续轮询（轻量离线监控守护，Ctrl+C 退出）；
    --reset 清空基线重新开始；--info 查看状态文件信息。

    示例：

      easy-tdx offline watch --dir /path/to/vipdoc/sz/lday --output csv
      easy-tdx offline watch --dir /path/to/vipdoc/sz/lday --state /tmp/watch.json --limit 5
      easy-tdx offline watch --dir /path/to/vipdoc/sz/lday --interval 60 --output csv
      easy-tdx offline watch --state /tmp/watch.json --info
      easy-tdx offline watch --state /tmp/watch.json --reset
      easy-tdx offline watch --dir /path/to/vipdoc/sz/lday --out /tmp/signals.jsonl
      easy-tdx offline watch --dir /path/to/vipdoc/sz/lday --report /tmp/signals.md
    """
    import json
    import os
    import time

    import pandas as pd

    from .output import print_error, print_output

    try:
        from ..offline import read_daily_bars
        from ..offline.paths import resolve_vipdoc
    except Exception as e:
        print_error(f"离线模块不可用: {e}")
        raise SystemExit(1)

    # 1. 状态文件路径（--info/--reset 不依赖 .day 目录）
    if state_file is None:
        state_file = str(Path.home() / ".easy_tdx" / "offline_watch_state.json")
    state_path = Path(state_file)

    # 1a. --reset 与 --info 互斥
    if do_reset and do_info:
        click.echo("--reset 与 --info 不能同时使用。")
        raise SystemExit(1)

    # 1b. --info：显示状态信息后退出（不需要 .day 目录）
    if do_info:
        count_seen = 0
        if state_path.is_file():
            try:
                count_seen = len(json.loads(state_path.read_text(encoding="utf-8")).get("seen", []))
            except Exception:  # noqa: BLE001
                count_seen = 0
        click.echo(f"状态文件: {state_path}")
        click.echo(f"已记录信号数: {count_seen}")
        return

    # 1c. --reset：单独清空基线并退出（下次运行时重新建立基线）
    if do_reset:
        if state_path.is_file():
            try:
                state_path.unlink()
                click.echo(f"已清空监控基线: {state_path}（下次 watch 将重新建立）")
            except Exception as e:  # noqa: BLE001
                click.echo(f"⚠ 清除状态文件失败: {e}", err=True)
                raise SystemExit(1)
        else:
            click.echo("无现有基线可清除（状态文件不存在）。")
        return

    # 2. 定位 .day 目录（实际扫描才需要）
    try:
        if day_dir is not None:
            lday_dir = Path(day_dir)
        else:
            lday_dir = resolve_vipdoc(None) / "sz" / "lday"
        if not lday_dir.is_dir():
            print_error(f".day 目录不存在: {lday_dir}")
            raise SystemExit(1)
        files = sorted(lday_dir.glob("*.day"))
    except Exception as e:
        print_error(str(e))
        raise SystemExit(1)

    if not files:
        click.echo(f"目录 {lday_dir} 中没有 .day 文件")
        raise SystemExit(0)

    # 3. 加载已见信号状态
    seen: set[str] = set()
    if state_path.is_file():
        try:
            seen = set(json.loads(state_path.read_text(encoding="utf-8")).get("seen", []))
        except Exception:  # noqa: BLE001
            seen = set()  # 状态文件损坏则视为首次运行

    # 3. 轮询循环：每轮扫描目录，报告新信号 + V102 建议摘要（--interval 连续或单次）
    from easy_tdx.chanlun import ChanlunAnalyser

    pass_no = 0
    while True:
        pass_no += 1
        # 每轮重新扫描目录（可能新增 .day 文件）
        files = sorted(lday_dir.glob("*.day"))
        if limit > 0:
            files = files[:limit]

        rows: list[dict[str, object]] = []
        for filepath in files:
            name = filepath.name.lower()
            if not (name.startswith(("sh", "sz")) and name.endswith(".day")):
                continue
            mkt = name[:2].upper()
            code = name[2:8]
            symbol = f"{mkt}{code}"
            try:
                bars = read_daily_bars(filepath)
                if not bars:
                    continue
                if count > 0:
                    bars = bars[-count:]
                if len(bars) < 30:
                    continue
                df = pd.DataFrame(
                    [
                        {
                            "datetime": f"{b.year}-{b.month:02d}-{b.day:02d}",
                            "open": b.open,
                            "high": b.high,
                            "low": b.low,
                            "close": b.close,
                            "vol": b.vol,
                            "amount": b.amount,
                        }
                        for b in bars
                    ]
                )
                analyser = ChanlunAnalyser(code=code, frequency="daily")
                result = analyser.process_klines(df)
                for mmd in result.mmds:
                    if mmd.mmd_type.value not in ("3buy", "3sell"):
                        continue  # 只监控 3买/3卖（有 V102 建议）
                    if not mmd.bi or not mmd.bi.end:
                        continue
                    date_str = result._fmt_dt(result._fx_anchor_datetime(mmd.bi.end))
                    if not _is_within_since_days(date_str, since_days):
                        # V372: 只看最近 N 天的新信号（避免首次运行报告陈旧基线）
                        continue
                    key = f"{symbol}:{mmd.mmd_type.value}:{date_str}"
                    if key in seen:
                        continue
                    rows.append(_watch_signal_row(symbol, mmd, date_str))
                    seen.add(key)
            except Exception as e:  # noqa: BLE001
                click.echo(f"⚠ {symbol}: {e}", err=True)
                continue

        # 每轮结束写回状态（全部信号记为已见基线）
        try:
            os.makedirs(state_path.parent, exist_ok=True)
            state_path.write_text(
                json.dumps({"seen": sorted(seen)}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:  # noqa: BLE001
            click.echo(f"⚠ 状态文件写入失败: {e}", err=True)

        if rows:
            print_output(pd.DataFrame(rows), output_fmt)
            # V365: --out 以 JSONL 追加落盘（供脚本/定时任务消费）
            if out_file:
                try:
                    os.makedirs(Path(out_file).parent, exist_ok=True)
                    with open(out_file, "a", encoding="utf-8") as fh:
                        for r in rows:
                            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                except Exception as e:  # noqa: BLE001
                    click.echo(f"⚠ JSONL 落盘失败: {e}", err=True)
            # V377: --report 以 Markdown 报告追加落盘（供人阅读/定时任务存档）
            if report_file:
                try:
                    os.makedirs(Path(report_file).parent, exist_ok=True)
                    with open(report_file, "a", encoding="utf-8") as fh:
                        fh.write(_render_watch_report(rows) + "\n")
                except Exception as e:  # noqa: BLE001
                    click.echo(f"⚠ Markdown 落盘失败: {e}", err=True)
            if interval > 0:
                click.echo(f"[第{pass_no}轮] 新信号 {len(rows)} 条（基线已更新）。", err=True)
            else:
                click.echo(f"新信号 {len(rows)} 条（基线已更新，下次仅报告新增）。", err=True)
        elif interval > 0:
            click.echo(f"[第{pass_no}轮] 无新信号。", err=True)
        else:
            click.echo("无新信号（状态已是最新）。")

        if interval <= 0:
            break
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            click.echo("\n已停止监控（Ctrl+C）。", err=True)
            break
