"""缠论内置因子的「有牙」回归测试。

背景（本次修复的 bug，务必看）
------------------------------
`src/easy_tdx/factor/builtin/chanlun.py` 里两个因子原本读的是**不存在的属性**：

- ``ChanlunMMD`` 读 ``mmd.type`` / ``mmd.index``（真实路径是 ``mmd.mmd_type``
  与 ``mmd.bi.end.k.k_index``）
- ``ChanlunBiDir`` 读 ``bi.start_index`` / ``bi.end_index``（真实路径是
  ``bi.start.k.k_index`` / ``bi.end.k.k_index``）

两者外面都裹着 ``except Exception: pass``，于是 AttributeError 被无声吞掉，表现为：

- ``ChanlunMMD`` → 恒定全 0（引擎明明算出了 3 个买卖点，实际一个都没落到序列上）
- ``ChanlunBiDir`` → 恒定全 1.0（循环体里每次写整帧，最后一笔方向赢者通吃）

本文件所有断言都打在**真实计算出来的数值**上（不是源码文本），因此把修复
回退（改回 ``.type`` / ``.start_index``）时，这些用例**必须失败**。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.factor.builtin.chanlun import ChanlunBiDir, ChanlunMMD
from easy_tdx.factor.base import FACTORY_REGISTRY

FIXTURE = Path(__file__).parent.parent / "fixtures" / "chanlun_000333_daily.json"


@pytest.fixture(scope="module")
def fixture_df() -> pd.DataFrame:
    rows = json.loads(FIXTURE.read_text())
    df = pd.DataFrame(rows)
    if "datetime" in df.columns and "date" not in df.columns:
        df["date"] = df["datetime"]
    df["date"] = pd.to_datetime(df["date"])
    return df


@pytest.fixture(scope="module")
def chanlun_result(fixture_df: pd.DataFrame):
    return ChanlunAnalyser(code="SZ000333", frequency="daily").process_klines(fixture_df)


@pytest.fixture(scope="module")
def fixture_expected_date_index(fixture_df: pd.DataFrame) -> bool:
    """fixture 未被整成 DatetimeIndex —— 本文件数据量级足够脏，直接位置索引。"""
    return isinstance(fixture_df.index, pd.DatetimeIndex)


# ── 前置：fixture 本身确实带着真信号（否则下面的断言毫无意义）──────────────


def test_fixture_has_real_signals(fixture_df: pd.DataFrame, chanlun_result) -> None:
    """护栏：确认 fixture 上引擎算得出笔与买卖点，且样本够大。

    若这条挂了，说明是 fixture/引擎变了，而不是因子 bug —— 需要人工复核。
    """
    assert len(fixture_df) >= 100
    assert len(chanlun_result.bis) >= 3, "fixture 上应有 3 笔以上，否则本文件失去意义"
    assert len(chanlun_result.mmds) >= 1, "fixture 上应有买卖点，否则 MMD 测试失去意义"


# ── ChanlunMMD ────────────────────────────────────────────────────────────


def test_mmd_nonzero_count_equals_engine_mmd_count(fixture_df: pd.DataFrame, chanlun_result) -> None:
    """核心断言：非零格数 == 引擎算出的买卖点数。

    bug 版本在这里必挂：预期 3，实际 0。
    """
    out = ChanlunMMD().compute(fixture_df)

    assert len(out) == len(fixture_df), "MMD 因子必须与输入等长"
    n_nonzero = int((out != 0).sum())
    assert n_nonzero == len(chanlun_result.mmds), (
        f"MMD 非零格数 {n_nonzero} != 引擎买卖点数 {len(chanlun_result.mmds)}"
    )
    # 更强的锚：非零必须 > 0（引擎已确认有信号，写死而非跟随 len(mmds) 兜底成 0==0）
    assert n_nonzero > 0


def test_mmd_lands_on_correct_bar_and_value(fixture_df: pd.DataFrame, chanlun_result) -> None:
    """每个买卖点必须落在 mmd.bi.end.k.k_index 那一行，且值取自 _MMD_MAP。"""
    out = ChanlunMMD().compute(fixture_df)
    dates = list(fixture_df["date"])

    got = {i: float(v) for i, v in enumerate(out) if v != 0}
    expected: dict[int, float] = {}
    for mmd in chanlun_result.mmds:
        idx = mmd.bi.end.k.k_index
        val = ChanlunMMD._MMD_MAP.get(mmd.mmd_type.value)
        if val is not None:
            expected[idx] = val

    assert set(got) == set(expected), f"落点集合不符: got={sorted(got)} expected={sorted(expected)}"
    assert got == expected, f"落点取值不符: got={got} expected={expected}"

    # 日期一致性：非零格所在的原始 K 行日期必须与买卖点日期吻合
    date_keyed = {i: v for i, v in got.items()}
    for i, _v in date_keyed.items():
        mmd_dates = {pd.Timestamp(m.bi.end.k.date) for m in chanlun_result.mmds}
        assert pd.Timestamp(dates[i]) in mmd_dates, f"第 {i} 行日期 {dates[i]} 不是任何买卖点日期"


def test_mmd_result_is_not_all_zero(fixture_df: pd.DataFrame) -> None:
    """一行护栏：明确禁止「静默全 0」——这是 bug 的表现形式。"""
    out = ChanlunMMD().compute(fixture_df)
    assert out.abs().sum() > 0, "MMD 全 0：属性路径多半又写错了（历史 bug：mmd.type 不存在）"


# ── ChanlunBiDir ──────────────────────────────────────────────────────────


def test_bi_dir_has_more_than_one_distinct_value(fixture_df: pd.DataFrame) -> None:
    """核心断言：序列不能恒定（bug 版本全 1.0，只有 1 个 distinct 值）。"""
    out = ChanlunBiDir().compute(fixture_df)

    assert len(out) == len(fixture_df)
    distinct = set(out.unique().tolist())
    assert len(distinct) > 1, f"笔方向序列恒定/退化: distinct={distinct}"


def test_bi_dir_last_value_equals_last_bi_direction(fixture_df: pd.DataFrame, chanlun_result) -> None:
    """最后一个值必须等于最后一笔方向（+1 / -1），不能是兜底的 0 或常量。"""
    out = ChanlunBiDir().compute(fixture_df)
    last_bi = chanlun_result.bis[-1]
    expected = 1.0 if last_bi.direction.value == "up" else -1.0

    assert out.iloc[-1] == pytest.approx(expected), (
        f"末值 {out.iloc[-1]} != 最后一笔方向 {last_bi.direction.value} -> {expected}"
    )


def test_bi_dir_paints_each_bi_over_its_own_span(fixture_df: pd.DataFrame, chanlun_result) -> None:
    """每笔把自己的方向刷在自己的 [start.k_index, end.k_index) 区间上。

    相邻笔共用分界 K 线（bi[n].end == bi[n+1].start），所以半开区间右侧让给后一笔。
    bug 版本每轮写满整帧 → 最后一笔赢者通吃 → 这里必挂。
    """
    out = ChanlunBiDir().compute(fixture_df)

    for bi in chanlun_result.bis:
        lo, hi = bi.start.k.k_index, bi.end.k.k_index
        expected = 1.0 if bi.direction.value == "up" else -1.0
        seg = out.iloc[lo:hi]
        assert len(seg) > 0, f"bi[{bi.index}] 区间 [{lo},{hi}) 为空"
        assert set(seg.unique().tolist()) == {expected}, (
            f"bi[{bi.index}] ({bi.direction.value}) 区间 [{lo},{hi}) "
            f"应为常量 {expected}，实际 {set(seg.unique().tolist())}"
        )


def test_bi_dir_covers_bi_extension_not_just_last_bar(fixture_df: pd.DataFrame, chanlun_result) -> None:
    """最后一笔结束后到帧尾（无新已完成笔）应延续末笔方向，而不是只值最后一根。"""
    out = ChanlunBiDir().compute(fixture_df)
    tail_start = chanlun_result.bis[-1].end.k.k_index
    expected = 1.0 if chanlun_result.bis[-1].direction.value == "up" else -1.0

    tail = out.iloc[tail_start:]
    assert len(tail) >= 1
    assert set(tail.unique().tolist()) == {expected}, (
        f"帧尾 [{tail_start}:] 应延续末笔方向 {expected}，实际 {set(tail.unique().tolist())}"
    )


def test_bi_dir_before_first_bi_is_zero(fixture_df: pd.DataFrame, chanlun_result) -> None:
    """第一笔起点之前没有笔，必须是 0（验证区间是半开而非贪心写整帧）。"""
    out = ChanlunBiDir().compute(fixture_df)
    head_end = chanlun_result.bis[0].start.k.k_index

    if head_end > 0:
        assert set(out.iloc[:head_end].unique().tolist()) == {0.0}


# ── 错误路径：不允许用 blanket except 假装「没信号」──────────────────────


def test_bi_dir_does_not_swallow_attribute_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """构造 BI 缺少 k.k_index 路径的情形 → 必须冒泡 AttributeError，不能静默返回常数。"""
    from easy_tdx.chanlun.analyser import ChanlunAnalyser  # 因子内部是延迟导入，patch 类方法即可

    class _Bad:
        index = 0
        direction = "up"

        def __getattr__(self, item: str):
            # 除了 index/direction，其余一律 AttributeError —— 模拟属性名写错
            raise AttributeError(f"'BadBI' object has no attribute '{item}'")

    class _BadResult:
        bis = [_Bad()]
        mmds: list = []

    monkeypatch.setattr(ChanlunAnalyser, "process_klines", lambda self, df: _BadResult())

    df = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]})

    with pytest.raises(AttributeError):
        ChanlunBiDir().compute(df)


def test_mmd_does_not_swallow_attribute_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """MMD 缺少 mmd_type / bi 路径 → 必须冒泡 AttributeError，不能返回全 0。"""
    from easy_tdx.chanlun.analyser import ChanlunAnalyser

    class _BadMMD:
        def __getattr__(self, item: str):
            raise AttributeError(f"'BadMMD' object has no attribute '{item}'")

    class _BadResult:
        bis: list = []
        mmds = [_BadMMD()]

    monkeypatch.setattr(ChanlunAnalyser, "process_klines", lambda self, df: _BadResult())

    df = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]})

    with pytest.raises(AttributeError):
        ChanlunMMD().compute(df)


# ── 退化输入：数据算不出结构时应返回全 0（正常路径，不是 bug）───────────


def test_no_structures_yields_zeros() -> None:
    """样本太少时引擎一笔都算不出 → 两个因子都返回全 0，且不抛异常。"""
    df = pd.DataFrame(
        {
            "datetime": pd.date_range("2025-01-01", periods=3),
            "date": pd.date_range("2025-01-01", periods=3),
            "open": [1.0, 2.0, 3.0],
            "high": [1.5, 2.5, 3.5],
            "low": [0.5, 1.5, 2.5],
            "close": [1.2, 2.2, 3.2],
            "vol": [1.0, 1.0, 1.0],
            "amount": [1.0, 2.0, 3.0],
        }
    )
    bi = ChanlunBiDir().compute(df)
    mmd = ChanlunMMD().compute(df)

    assert len(bi) == 3 and len(mmd) == 3
    assert set(bi.unique().tolist()) == {0.0}
    assert set(mmd.unique().tolist()) == {0.0}


# ── 注册契约（与既有 test_factor_builtin.py 保持一致，此处再确认一次）──────


def test_chanlun_factors_registered() -> None:
    assert "chanlun_bi_dir" in FACTORY_REGISTRY
    assert "chanlun_mmd" in FACTORY_REGISTRY
    assert FACTORY_REGISTRY["chanlun_bi_dir"] is ChanlunBiDir
    assert FACTORY_REGISTRY["chanlun_mmd"] is ChanlunMMD
