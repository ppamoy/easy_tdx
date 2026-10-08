"""前端↔后端 API 契约测试：前端调用的每个 /api/v1 路径，后端必须真实注册。

背景（本项目反复出现的 bug 形态）：**「UI 渲染出来了，请求却从未落到后端」**。
典型病例——``ScreeningView.vue:351`` 的「验证选股效果」按钮渲染正常，但
``POST /api/v1/screening/verify`` 的 ``@router.post`` 装饰器在 v386 质量加固
提交（aba4b9f）中被误删：函数体还在、前端照常调用，路由表里却根本没有这个
路径，用户点下去只拿到 405。单测全绿也抓不到——因为此前没有任何测试比对过
「前端实际调用的 URL」与「后端实际注册的路由」。

本文件用两层网堵死这类漏网：

1. **静态抽取**：把 ``web-ui/src/**/*.{vue,ts}`` 当纯文本读（不装 node、不构建），
   正则抓出所有 ``/api/v1/...`` 字面量，含 ``${BASE}`` 与模板字符串里的
   ``${xxx}`` 插值。插值段归一化成 ``{p0}``/``{p1}``… 后**逐段**匹配后端路由
   模板——动态路径**不静默跳过**（见 :func:`test_dynamic_paths_are_matched`）。
2. **运行时核对**：实例化真实 ``create_app()``，从 ``app.openapi()["paths"]``
   取全部已注册路由，断言每个前端调用都能命中（路径 + 方法）。

任一侧漂移（前端改了 URL / 后端删了或改了路由名）都会让 CI 变红。

离线运行：只做路由表比对 + mock 注入的真实请求，不连 TDX。
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pandas as pd
import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

# ── 路径定位 ─────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[2]  # tests/unit -> tests -> 仓库根
_WEB_UI_SRC = _REPO_ROOT / "web-ui" / "src"

API_PREFIX = "/api/v1"

# api.ts 里的 ``const BASE = '/api/v1'``：模板字面量 `${BASE}/xxx` 展开后再比对
_BASE_LITERAL = "${BASE}"

# ── 静态抽取：前端到底调用了哪些路径 ─────────────────────────────────────────

# 抓 `/api/v1/...` 或 `${BASE}/...` 起始的字面量。终止于引号/反引号/空白/右括号等，
# 避免把紧随其后的 `body: JSON.stringify(...)` 之类代码吞进来。
_PATH_LITERAL_RE = re.compile(
    r"(?:/api/v1|" + re.escape(_BASE_LITERAL) + r")/[A-Za-z0-9_\-/{}$.]*"
)

# 模板插值段：${taskId} / ${market} / ${code.value} / ${encodeURIComponent(x)}
_INTERP_RE = re.compile(r"\$\{[^}]*\}")

# `?a=1&b=2` 及其后的 query/fragment：路径比对时剥掉
_QUERY_RE = re.compile(r"[?#].*$")

_METHOD_RE = re.compile(r"method:\s*['\"]([A-Z]+)['\"]")

_SCAN_SUFFIXES = (".vue", ".ts")

# 已确认待修、由其他 worker 并行处理的调用点：``file:line`` -> 说明。
# 这些条目**只豁免主断言**，不会让检查静默消失：
# :func:`test_known_missing_allowlist_is_not_stale` 会在条目过期（已修好、或
# 源码里已找不到该调用）时报错/告警，提醒把它删掉，避免白名单变成永久藏污点。
#
# 当前为空：本次修复期间唯一在列的 ``ChanlunView.vue:1257``
# （``/api/v1/bars/${market}/...`` path 版 404 + 误读 ``data.bars``）已由另一
# worker 改为 query 参数形式，过期检测立刻刷出了它，条目随即移除。
KNOWN_MISSING: dict[str, str] = {}


class FrontendCall:
    """一次前端 API 调用的静态抽取结果。"""

    __slots__ = ("file", "line", "raw", "path", "method", "explicit_method", "n_interp")

    def __init__(
        self,
        file: Path,
        line: int,
        raw: str,
        path: str,
        method: str,
        explicit_method: bool,
        n_interp: int,
    ) -> None:
        self.file = file
        self.line = line
        self.raw = raw
        self.path = path
        self.method = method
        self.explicit_method = explicit_method
        self.n_interp = n_interp

    @property
    def loc(self) -> str:
        return f"{self.file.relative_to(_REPO_ROOT)}:{self.line}"

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"<FrontendCall {self.loc} {self.method} {self.path}>"


def _iter_frontend_files() -> list[Path]:
    """前端源码文件（.vue/.ts），排除 node_modules / dist 构建产物。"""
    if not _WEB_UI_SRC.is_dir():
        return []
    return sorted(
        p
        for p in _WEB_UI_SRC.rglob("*")
        if p.is_file()
        and p.suffix in _SCAN_SUFFIXES
        and "node_modules" not in p.parts
        and "dist" not in p.parts
    )


def _normalize_path(raw: str) -> tuple[str, int]:
    """把抓到的 URL 片段归一化成可比对的路径模板。

    - 剥掉 query/fragment（先剥，避免 ``?code=${x}`` 被当成路径插值段）；
    - 展开 ``${BASE}`` → ``/api/v1``；
    - 每个 ``${...}`` 插值替换为 ``{pN}``（N 为出现序号）。如此
      ``/monitor/${taskId}/check`` 能与后端 ``/monitor/{task_id}/check``
      逐段匹配：同一段两侧都是占位符即算匹配，不比较占位符名字
      （参数名差异属 payload 契约，不是本文件的职责）。

    返回 ``(归一化路径, 插值个数)``。
    """
    path = _QUERY_RE.sub("", raw)
    path = path.replace(_BASE_LITERAL, API_PREFIX)
    if not path.startswith(API_PREFIX):
        path = API_PREFIX + path

    n_interp = len(_INTERP_RE.findall(path))
    counter = [0]

    def _sub(_m: re.Match[str]) -> str:
        idx = counter[0]
        counter[0] += 1
        return f"{{p{idx}}}"

    path = _INTERP_RE.sub(_sub, path)
    path = re.sub(r"/+", "/", path).rstrip("/")
    return path, n_interp


def _is_placeholder(seg: str) -> bool:
    return seg.startswith("{") and seg.endswith("}")


def _match_backend_path(norm_path: str, backend_paths: list[str]) -> str | None:
    """在后端路径表里找能匹配 ``norm_path`` 的路由，命中则返回该后端路径。

    段数必须相等；字面量段全等；占位符段与占位符段通配。
    优先返回**非占位符**匹配（更精确）。
    """
    fe_segs = [s for s in norm_path.split("/") if s]
    best: str | None = None
    best_used_ph = True
    for bp in backend_paths:
        be_segs = [s for s in bp.split("/") if s]
        if len(be_segs) != len(fe_segs):
            continue
        used_ph = False
        ok = True
        for f, b in zip(fe_segs, be_segs):
            f_ph = _is_placeholder(f)
            b_ph = _is_placeholder(b)
            if f_ph and b_ph:
                used_ph = True
                continue
            if f_ph != b_ph or f != b:
                ok = False
                break
        if ok and (best is None or (not used_ph and best_used_ph)):
            best = bp
            best_used_ph = used_ph
    return best


def _infer_method(lines: list[str], idx: int) -> tuple[str, bool]:
    """推断该次 fetch 的 HTTP 方法。

    从字面量所在行向下最多看 6 行，找 ``method: 'POST'`` 这样的显式声明
    （Vue 里普遍把 fetch 选项换行写）；遇到下一个 URL 字面量即停止，
    防止读到相邻调用的方法。找不到显式声明则按 GET（fetch 默认），
    并标记 ``explicit=False``——方法断言只对显式声明的调用生效。
    """
    for offset in range(0, 7):
        if idx + offset >= len(lines):
            break
        line = lines[idx + offset]
        if offset > 0 and _PATH_LITERAL_RE.search(line):
            break
        m = _METHOD_RE.search(line)
        if m:
            return m.group(1).upper(), True
    return "GET", False


def _collect_frontend_calls() -> list[FrontendCall]:
    """扫描前端源码，返回所有 /api/v1 调用点（按文件、行号排序）。"""
    calls: list[FrontendCall] = []
    seen: set[tuple[str, int, str]] = set()
    for f in _iter_frontend_files():
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):  # pragma: no cover - 极端情况
            continue
        lines = text.splitlines()
        for idx, line in enumerate(lines):
            for m in _PATH_LITERAL_RE.finditer(line):
                raw = m.group(0)
                path, n_interp = _normalize_path(raw)
                key = (str(f), idx + 1, path)
                if key in seen:
                    continue
                seen.add(key)
                method, explicit = _infer_method(lines, idx)
                calls.append(
                    FrontendCall(
                        file=f,
                        line=idx + 1,
                        raw=raw,
                        path=path,
                        method=method,
                        explicit_method=explicit,
                        n_interp=n_interp,
                    )
                )
    return calls


# ── 夹具 ─────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def openapi_paths() -> dict[str, dict[str, Any]]:
    """真实 app 的路由表：路径 -> {方法: 操作定义}。"""
    from easy_tdx.web import create_app

    app = create_app()
    with TestClient(app) as _c:  # noqa: F841 - 只为进入 lifespan 后取路由表
        return app.openapi()["paths"]


@pytest.fixture(scope="module")
def frontend_calls() -> list[FrontendCall]:
    return _collect_frontend_calls()


@pytest.fixture(scope="module")
def backend_path_list(openapi_paths: dict[str, dict[str, Any]]) -> list[str]:
    return list(openapi_paths)


# ── 契约断言 ─────────────────────────────────────────────────────────────────


def test_frontend_source_is_scanned(frontend_calls: list[FrontendCall]) -> None:
    """前端源码必须能被扫到——扫不到说明路径/正则失效，本文件在空转。"""
    assert _WEB_UI_SRC.is_dir(), f"前端源码目录不存在: {_WEB_UI_SRC}"
    assert len(frontend_calls) >= 25, (
        f"只扫到 {len(frontend_calls)} 处 /api/v1 调用，远少于预期；"
        "前端源码位置或 _PATH_LITERAL_RE 正则可能已失效"
    )


def test_every_frontend_path_exists_as_route(
    frontend_calls: list[FrontendCall],
    backend_path_list: list[str],
) -> None:
    """每个前端调用的路径都必须能在后端路由表里找到（KNOWN_MISSING 除外）。"""
    missing: list[str] = []
    for call in frontend_calls:
        if call.loc in KNOWN_MISSING:
            continue
        if _match_backend_path(call.path, backend_path_list) is None:
            missing.append(
                f"  ✗ {call.loc}\n"
                f"      源码: {call.raw}\n"
                f"      归一化: {call.path}  →  后端无此路径"
            )

    assert not missing, (
        f"前端调用了 {len(missing)} 个后端未注册的路径"
        "（典型病因：后端 @router 装饰器被误删/改名，而前端按钮照常渲染，"
        "用户点下去拿到 404/405）：\n" + "\n".join(missing)
    )


def test_every_frontend_method_matches(
    frontend_calls: list[FrontendCall],
    openapi_paths: dict[str, dict[str, Any]],
    backend_path_list: list[str],
) -> None:
    """显式写出 method 的调用，后端对应路径必须支持同名方法。"""
    bad: list[str] = []
    for call in frontend_calls:
        if call.loc in KNOWN_MISSING or not call.explicit_method:
            continue
        matched = _match_backend_path(call.path, backend_path_list)
        if matched is None:
            continue  # 路径缺失由上一个测试负责报错，这里不重复
        allowed = {m.upper() for m in openapi_paths[matched]}
        if call.method not in allowed:
            bad.append(
                f"  ✗ {call.loc}: {call.method} {call.path}\n"
                f"      后端 {matched} 仅支持 {sorted(allowed)}"
            )

    assert not bad, "前端调用的 HTTP 方法与后端路由不匹配：\n" + "\n".join(bad)


def test_dynamic_paths_are_matched(
    frontend_calls: list[FrontendCall], backend_path_list: list[str]
) -> None:
    """含模板插值（${...}）的动态路径必须**真的参与匹配**，不许静默跳过。

    这是本文件的防作弊闸门：如果抽取器把动态路径全丢掉，上面两个测试就会
    变成「只查静态 URL」的软柿子，"monitor/${taskId}/check" 这类真实调用
    永远查不到。这里断言抽取到的动态路径数量与匹配结果。
    """
    dynamic = [c for c in frontend_calls if c.n_interp > 0]
    assert dynamic, "未抽取到任何含 ${...} 插值的动态路径——正则可能已失效"

    unmatched = [
        c for c in dynamic if _match_backend_path(c.path, backend_path_list) is None
    ]
    unexpected = [c for c in unmatched if c.loc not in KNOWN_MISSING]

    assert not unexpected, (
        f"抽取到 {len(dynamic)} 处动态路径，其中 {len(unexpected)} 处"
        "在后端匹配不上（动态路径没有被跳过，是真的在查）：\n"
        + "\n".join(f"  ✗ {c.loc}: {c.raw} → {c.path}" for c in unexpected)
    )


def test_known_missing_allowlist_is_not_stale(
    frontend_calls: list[FrontendCall], backend_path_list: list[str]
) -> None:
    """KNOWN_MISSING 里的条目若已被修好，提醒删除白名单。

    不直接 fail（避免并行修复的 worker 被本文件卡住），但会用 UserWarning
    在 pytest 汇总里显式刷出来，防止白名单变成永久藏污点。
    """
    by_loc = {c.loc: c for c in frontend_calls}
    stale: list[str] = []
    for loc in KNOWN_MISSING:
        call = by_loc.get(loc)
        if call is None:
            stale.append(f"{loc}（源码里已找不到该调用）")
        elif _match_backend_path(call.path, backend_path_list) is not None:
            stale.append(f"{loc}（{call.path} 现已能匹配后端路由）")

    if stale:
        warnings.warn(
            "KNOWN_MISSING 白名单已过期，请删除这些条目让断言重新生效: "
            + "; ".join(stale),
            UserWarning,
            stacklevel=2,
        )

    # 白名单必须指向真实存在的源码位置，否则等于写错了豁免
    ghosts = [loc for loc in KNOWN_MISSING if loc not in by_loc]
    assert not ghosts, (
        "KNOWN_MISSING 里的位置在前端源码中不存在，豁免写错了: " + ", ".join(ghosts)
    )


# ── 本次修复的具体端点：路由存在且真的进到处理函数 ───────────────────────────


def test_screening_verify_route_is_registered(
    openapi_paths: dict[str, dict[str, Any]],
) -> None:
    """POST /api/v1/screening/verify 必须出现在路由表里（装饰器被误删的回归）。"""
    path = "/api/v1/screening/verify"
    assert path in openapi_paths, (
        f"{path} 未注册——@router.post 装饰器是不是又被删了？"
        f"（当前 screening 路由: {sorted(p for p in openapi_paths if 'screening' in p)}）"
    )
    assert "POST" in {m.upper() for m in openapi_paths[path]}, (
        f"{path} 注册了但不含 POST: {sorted(m.upper() for m in openapi_paths[path])}"
    )


def _synthetic_df(n: int = 260) -> pd.DataFrame:
    """合成日线（覆盖 2023-06-15 前后，供前瞻收益计算）。"""
    dates = pd.date_range("2023-01-02", periods=n, freq="B")
    close = [10.0 + 0.02 * i for i in range(n)]
    return pd.DataFrame(
        {
            "datetime": dates,
            "open": close,
            "high": [c * 1.01 for c in close],
            "low": [c * 0.99 for c in close],
            "close": close,
            "vol": [1000] * n,
        }
    )


def _mock_app_client() -> TestClient:
    """注入 mock 行情客户端的 TestClient（离线）。

    不走 lifespan（不用 ``with``）：一是避免真实连 TDX，二是 lifespan 会用真实
    客户端覆盖注入的 mock。路由在 ``_create_app`` 里已挂载完毕，无需 lifespan。
    """
    from easy_tdx.web.app import _create_app

    app = _create_app()
    tdx = AsyncMock()
    tdx.get_security_bars = AsyncMock(return_value=_synthetic_df())
    app.state.tdx_client = tdx
    app.state.mac_client = None  # 强制走标准 TDX 分支，返回可控 DataFrame
    return TestClient(app)


def test_screening_verify_reaches_handler() -> None:
    """真发一次请求：必须**进到处理函数**（不是 405），并按契约返回错误体。

    405 = 路由不存在（装饰器被删）；200 + 业务 error = 路由通了、参数不对，
    两者必须区分开——本测试断言的是后者。
    """
    client = _mock_app_client()
    resp = client.post(
        "/api/v1/screening/verify",
        json={"date": "2023-06-15", "market": "SZ", "symbols": [], "selected": []},
    )
    assert resp.status_code == 200, (
        f"期望 200（路由通了、参数校验失败），实际 {resp.status_code}——"
        "若是 405/404 说明 @router.post 装饰器又没了"
    )
    body = resp.json()
    assert body["error"] == "请提供选股日期和扫描池股票列表"
    assert body["horizons"] == {}
    assert body["verdict"] == ""


def test_screening_verify_bad_date_reaches_handler() -> None:
    """日期格式错误也必须进到处理函数并返回业务错误（不是 405/422）。"""
    client = _mock_app_client()
    resp = client.post(
        "/api/v1/screening/verify",
        json={
            "date": "not-a-date",
            "market": "SZ",
            "symbols": ["SZ:000001"],
            "selected": ["SZ:000001"],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["error"] == "日期格式错误，请使用 YYYY-MM-DD"


def test_screening_verify_success_shape() -> None:
    """正常入参：返回前端消费的完整结构（date/pool_size/selected_size/horizons）。"""
    client = _mock_app_client()
    resp = client.post(
        "/api/v1/screening/verify",
        json={
            "date": "2023-06-15",
            "market": "SZ",
            "symbols": ["SZ:000001", "SZ:000002", "000004"],
            "selected": ["SZ:000001"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "error" not in body, f"取数失败: {body}"
    assert body["date"] == "2023-06-15"
    assert body["pool_size"] == 3
    assert body["selected_size"] == 1
    assert set(body["horizons"]) >= {"5", "10", "20", "60"}
    assert isinstance(body["verdict"], str) and body["verdict"]
    # 前端 exportVerifyCsv 逐行读 horizons 的这些键
    for h in ("5", "10", "20", "60"):
        entry = body["horizons"][h]
        for key in (
            "selected_avg_return",
            "selected_hit_rate",
            "pool_avg_return",
            "pool_hit_rate",
            "excess_return",
            "excess_hit_rate",
        ):
            assert key in entry, f"horizons[{h}] 缺字段 {key}"
