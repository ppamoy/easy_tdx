"""长赢基本面选股（P1）：gpcw 历史财报指标层 + 树粮菜量化选股 + 历史时点四季判断。"""

from .gpcw_fields import GPCW_FIELDS, F  # noqa: F401
from .indicators import (  # noqa: F401
    ReportRecord,
    build_indicator_frame,
    indicator_values,
    load_all_periods,
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

__all__ = [
    "F", "GPCW_FIELDS",
    "ReportRecord", "build_indicator_frame", "indicator_values",
    "load_all_periods", "pick_report", "pick_reports_bulk", "records_from_zip",
    "CATEGORY_LABELS", "ScreenResult", "ScoreDetail", "screen_stock",
    "score_grain", "score_tree", "score_vegetable",
    "SEASON_INFO", "SeasonResult", "detect_season",
]
