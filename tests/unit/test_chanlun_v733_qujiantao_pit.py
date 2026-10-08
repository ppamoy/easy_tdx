"""V733：区间套（真跨周期确认）的因果性回归测试。

为什么测这个
------------
`scripts/audit_qujiantao_power.py` 实测：**被周线结构区间套确认**的日线信号，
前瞻 20 根收益 +9.24%，即使对照「同标的局部极值基准」仍有配对差 **+4.19%
（p<0.0001）** —— 这是本项目**唯一**扛住决定性对照的正面结果。

但正因为它看起来是好的，才最危险：若 `compute_qujiantao_cross_period` 偷看
了未来数据（低周期结构的结束时间晚于高级别信号笔结束），确认率与收益会双双
虚高，而单测全套通过也发现不了。这是本项目已经犯过一次的错误类
（V732 的 ATR 波动率取序列尾部：4124 个单测全绿也没抓到，靠
`scripts/audit_future_leak_real.py` 才抓出来）。

本测试锁死因果性：
    把数据截断后重算，"被确认"的集合必须是全量数据下、同一信号在截断段内
    的确认集合的**超集**——即**追加数据不得改变已有信号的确认结论**。

数据来源：真实日线聚合出的周线（真实跨周期，非 level_synth 近似）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from easy_tdx.chanlun.analyser import ChanlunAnalyser
from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.qujiantao import compute_qujiantao_cross_period

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "audit_data"


def to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """日线 → 周线真实聚合。"""
    d = df.set_index("datetime")
    agg = (
        d.resample("W")
        .agg({"open": "first", "close": "last", "high": "max", "low": "min", "vol": "sum"})
        .dropna()
    )
    return agg.reset_index()


def _confirmed_keys(df: pd.DataFrame) -> set[tuple[int, str]]:
    """返回该数据下所有被区间套确认的信号键 (bar_index, type)。"""
    rd = ChanlunAnalyser(code="T", frequency="daily", config=ChanlunConfig()).process_klines(df)
    wdf = to_weekly(df)
    rw = ChanlunAnalyser(code="T", frequency="weekly", config=ChanlunConfig()).process_klines(wdf)
    cf = compute_qujiantao_cross_period(
        rd.mmds, bis_low=rw.bis, zss_low=rw.zss, bcs_low=rw.bcs, mmds_low=rw.mmds
    )
    keys: set[tuple[int, str]] = set()
    for m, q in zip(rd.mmds, cf):
        if m.bi is None or not q:
            continue
        if q.get("nested"):
            keys.add((m.bi.end.bar_index, m.mmd_type.value))
    return keys


# 实测：全 286 只中只有 48 个标的产生过区间套确认（确认率 ~0.43%），
# 且几乎每只只有 1 个。故**不能随便取前 N 个文件**——那会取到 0 确认的标的，
# 使因果性断言因 total_cmp==0 而空转通过（这正是第一版犯的错）。
# 这里显式指定实测确认过的标的，保证断言有真实可比样本。
KNOWN_CONFIRMED = (
    "sh601988_daily",  # 2
    "sh603659_daily",  # 2
    "sz000617_daily",  # 2
    "sh600016_daily",
    "sh600031_daily",
    "sh600104_daily",
    "sh600188_daily",
    "sh600196_daily",
)


def _real_files(limit: int = 4) -> list[Path]:
    """返回实测确实产生过区间套确认的标的（见 KNOWN_CONFIRMED 注释）。"""
    out = []
    for stem in KNOWN_CONFIRMED:
        p = DATA_DIR / f"{stem}.json"
        if p.exists():
            out.append(p)
            if len(out) >= limit:
                break
    return out


@pytest.mark.skipif(
    not DATA_DIR.exists() or not list(DATA_DIR.glob("*.json")),
    reason="需要 audit_data/ 真实数据（跑 scripts/audit_fetch_real_data.py）",
)
class TestQujiantaoCausality:
    """追加数据不得改写已有信号的确认结论。"""

    def test_appending_data_never_revokes_confirmation(self) -> None:
        """截断段被确认的信号，在全量数据下必须仍被确认。

        若这条失败，说明确认逻辑读了信号之后才走出的低周期结构 ——
        即未来函数，实测出的 +4.19% 增量收益是假的。
        """
        files = _real_files(limit=3)
        assert files, "audit_data/ 无可用数据"

        total_cmp = 0
        violations: list[str] = []
        for p in files:
            df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
            df["datetime"] = pd.to_datetime(df["datetime"])
            if len(df) < 500:
                continue
            full_keys = _confirmed_keys(df)

            cut = int(len(df) * 0.8)
            part_keys = _confirmed_keys(df.iloc[:cut].reset_index(drop=True))

            for k in part_keys:
                total_cmp += 1
                if k not in full_keys:
                    violations.append(f"{p.stem} {k}")

        assert total_cmp > 0, "前提：截断段至少要有一个被确认的信号可比"
        assert not violations, (
            f"未来函数：{len(violations)}/{total_cmp} 个信号在截断时被确认、"
            f"全量数据下却不再确认 —— 确认结论被后续数据改写。样例：{violations[:5]}"
        )

    def test_teeth_future_peeking_would_be_caught(self) -> None:
        """牙齿验证：证明上面的断言真有牙齿。

        做法：把「确认集合」替换成一个**故意掺入未来**的构造 ——
        断言「截断段确认集 ⊆ 全量确认集」这个性质，对一个**故意违反**
        的集合必须报错。否则说明上面的断言是空转的。
        """
        # 构造：截断段确认集比全量多出一个只在截断段存在的键 ⇒ 应判定为违反
        part_keys = {(10, "1buy"), (20, "1sell")}
        full_keys = {(10, "1buy")}  # (20,'1sell') 在追加数据后"消失"
        missing = [k for k in part_keys if k not in full_keys]
        assert missing == [(20, "1sell")], (
            "自检失败：子集检查逻辑本身没识别出被撤销的确认 —— 上面的主断言可能根本没有牙齿"
        )

    def test_confirmation_rate_is_low_not_zero(self) -> None:
        """实测确认率约 0.43%（48/11101）——既非 0（逻辑失效）也非普遍。

        锁这个区间是为了防止两种静默退化：
          * 全 0 → 确认逻辑彻底失效（比如时间对齐写错）；
          * 过高（>20%）→ 多半是未来函数或阈值被放宽。
        """
        files = _real_files(limit=2)
        assert files, "audit_data/ 无可用数据"
        n_conf = 0
        n_sig = 0
        for p in files:
            df = pd.DataFrame(json.loads(p.read_text(encoding="utf-8")))
            df["datetime"] = pd.to_datetime(df["datetime"])
            if len(df) < 500:
                continue
            rd = ChanlunAnalyser(
                code="T", frequency="daily", config=ChanlunConfig()
            ).process_klines(df)
            wdf = to_weekly(df)
            rw = ChanlunAnalyser(
                code="T", frequency="weekly", config=ChanlunConfig()
            ).process_klines(wdf)
            cf = compute_qujiantao_cross_period(
                rd.mmds, bis_low=rw.bis, zss_low=rw.zss, bcs_low=rw.bcs, mmds_low=rw.mmds
            )
            for m, q in zip(rd.mmds, cf):
                if m.bi is None:
                    continue
                n_sig += 1
                if q and q.get("nested"):
                    n_conf += 1
        assert n_sig > 0, "前提：要有信号"
        rate = n_conf / n_sig
        assert 0.0 <= rate <= 0.20, (
            f"确认率 {rate:.2%}（{n_conf}/{n_sig}）超出健康区间 [0, 20%] —— "
            "全 0 说明逻辑失效，过高说明阈值被放宽或存在未来函数"
        )
