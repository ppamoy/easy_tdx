"""长赢基本面选股（P1）：gpcw 历史财报指标层 + 树粮菜量化选股 + 历史时点四季判断。"""

from .cache import cache_stats, has_frame  # noqa: F401
from .cache import clear_cache as clear_gpcw_cache
from .cache import warm as warm_gpcw_cache
from .gpcw_fields import GPCW_FIELDS, F  # noqa: F401
from .indicators import (  # noqa: F401
    ReportRecord,
    build_indicator_frame,
    frame_for_zip,
    indicator_values,
    load_all_periods,
    load_all_periods_frame,
    pick_report,
    pick_reports_bulk,
    records_from_zip,
)
from .screener import (  # noqa: F401
    CATEGORY_LABELS,
    ScoreDetail,
    ScreenResult,
    score_grain,
    score_tree,
    score_vegetable,
    screen_stock,
)
from .season import SEASON_INFO, SeasonResult, detect_season  # noqa: F401
from .sina_cache import cache_stats as sina_cache_stats  # noqa: F401
from .sina_cache import clear_cache as clear_sina_cache  # noqa: F401
from .sina_cache import has_rows as sina_has_rows  # noqa: F401

__all__ = [
    "F", "GPCW_FIELDS",
    "ReportRecord", "build_indicator_frame", "frame_for_zip", "indicator_values",
    "load_all_periods", "load_all_periods_frame", "pick_report", "pick_reports_bulk",
    "records_from_zip",
    "cache_stats", "clear_gpcw_cache", "has_frame", "warm_gpcw_cache",
    "sina_cache_stats", "clear_sina_cache", "sina_has_rows",
    "CATEGORY_LABELS", "ScreenResult", "ScoreDetail", "screen_stock",
    "score_grain", "score_tree", "score_vegetable",
    "SEASON_INFO", "SeasonResult", "detect_season",
]
