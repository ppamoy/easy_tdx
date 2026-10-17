"""第38课「走势类型连接的同级别分解」。

原文（docs/缠论108课/38.走势类型连接的同级别分解.md，逐字核对）：

  1. 「所谓同级别分解，就是把所有走势按一固定级别的走势类型进行分解。
      根据『缠中说禅走势分解定理』，同级别分解具有唯一性。」

  2. 「对于这种同级别分解视角下的操作，永远只针对一个正在完成着的同级别中枢，
      一旦该中枢完成，就继续关注下一个同级别中枢。」

  3. 「注意，在这种同级别的分解中，是**不需要中枢延伸或扩展的概念**的，
      对30分钟来说，只要5分钟级别的三段上下上或下上下类型有价格区间的重合
      就构成中枢。**如果这5分钟次级别延伸出6段，那么就当成两个30分钟盘整类型
      的连接**，在这种分解中，是允许盘整+盘整情况的。」

  4. 「因此，完全合理、不违反任何理论原则的，可以制定出这样的同级别分解规则：
      在某级别中，**不定义中枢延伸，允许该级别上的盘整+盘整连接**；与此同时，
      规定该级别以下的所有级别，都允许中枢延伸，不允许盘整+盘整连接。」

本模块实现第 3、4 条的口径：把输入序列（笔或线段）切成一段段**同级别走势类型**
的连接，其中

  - 「走势类型」= 3 段同向连接且有价格区间重合 ⇒ 一个中枢（原文第 38 课）。
  - 少于 3 段 ⇒ 不构成中枢，原样作为一个独立走势类型段（趋势/盘整的未完成部分）。
  - **不定义中枢延伸**：第 4 段起若仍与中枢区间重合，按原文「当成两个盘整类型
    的连接」处理 —— 即**立刻关闭当前中枢并新起一个**，而不是无限延伸。
  - 因此「盘整 + 盘整」是合法连接（原文明确允许）。

与非同级别分解（``zs.find_zss``）的关键差异
---------------------------------------------
======================= ========================== ==========================
维度                    非同级别分解（默认）        同级别分解（本模块）
======================= ========================== ==========================
中枢延伸                 允许（上限 9 段后硬关闭）   **不允许**（原文不需要该概念）
超 3 段的重叠             继续延伸同一个中枢          关闭并新起 ⇒ 盘整+盘整
原文依据                 第33课 3+6=9 段            第38课「不需要延伸/扩展」
======================= ========================== ==========================

⚠️ 原文第 38 课同时规定「该级别以下的所有级别，都允许中枢延伸」—— 即**同级别
   分解只作用于被选定的那个级别**。本模块只做「把给定序列按同级别分解」这一层，
   不递归处理更低级别；更低级别仍走 ``find_zss`` 的延伸口径。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from easy_tdx.chanlun.config import ChanlunConfig
from easy_tdx.chanlun.types import BI, Direction, XD, ZS

# 原文第38课：「只要5分钟级别的**三段**上下上或下上下类型有价格区间的重合
# 就构成中枢」⇒ 构成一个中枢所需的最少段数 = 3（与 find_zss 的 zs_min_lines 同源）。
_MIN_CENTRAL_SEGMENTS = 3


@dataclass
class TrendSegment:
    """同级别分解后的一个「走势类型」段。

    原文口径下，一段走势类型只能是：

      - **趋势**：含 >= 2 个依次同向的中枢（原文第17课定义）；
      - **盘整**：只含 1 个中枢（原文第17课定义）；
      - **未完成/不足段**：不足 3 段、构不成中枢的零段。

    第38课允许「盘整 + 盘整」连接，所以相邻两段都是盘整是合法分解。
    """

    lines: list[BI | XD] = field(default_factory=list)
    zss: list[ZS] = field(default_factory=list)
    kind: str = "none"  # "up" / "down" / "none"
    index: int = 0

    # ── 派生属性 ────────────────────────────────────────────────────────
    @property
    def n_segments(self) -> int:
        return len(self.lines)

    @property
    def is_panzheng(self) -> bool:
        """原文第17课：只包含一个缠中说禅走势中枢 ⇒ 盘整。"""
        return len(self.zss) == 1

    @property
    def is_trend(self) -> bool:
        """原文第17课：至少包含两个以上依次同向的中枢 ⇒ 趋势。"""
        return len(self.zss) >= 2

    @property
    def has_zs(self) -> bool:
        return len(self.zss) > 0

    @property
    def start_val(self) -> float:
        return self.lines[0].start.val if self.lines else 0.0

    @property
    def end_val(self) -> float:
        return self.lines[-1].end.val if self.lines else 0.0

    def __str__(self) -> str:
        s = self.lines[0].start.k.date if self.lines else None
        e = self.lines[-1].end.k.date if self.lines else None
        return (
            f"TrendSegment(#{self.index} {self.kind} "
            f"{s:%Y-%m-%d}→{e:%Y-%m-%d} segs={self.n_segments} "
            f"zs={len(self.zss)})"
        )


def _overlap(a: BI | XD, b: BI | XD) -> float:
    """两段线的价格重叠长度（0 表示不重叠）。原文只要求「有价格区间的重合」。"""
    hi = min(a.high, b.high)
    lo = max(a.low, b.low)
    return hi - lo


def _zs_interval(lines: list[BI | XD]) -> tuple[float, float]:
    """中枢区间 [ZD, ZG]：第38课口径 = 前三段的重叠（等同第20课 ZG/ZD 定义）。

    原文第38课：「只要5分钟级别的三段上下上或下上下类型有价格区间的重合就构成
    中枢」⇒ 区间由**这三段**的重叠确定；第 4 段起在同级别分解里不再延伸，
    所以不需要继续更新 ZG/ZD。
    """
    hi = min(x.high for x in lines)
    lo = max(x.low for x in lines)
    return lo, hi  # (ZD, ZG)


def decompose_same_level(
    bis: list[BI] | list[XD],
    config: ChanlunConfig | None = None,
) -> list[TrendSegment]:
    """把笔/线段序列按第38课同级别分解成一段段走势类型的连接。

    算法（逐条对应原文）：

    1. **三段成中枢**：连续三段若有价格重合 ⇒ 形成一个中枢（原文第38课）。
    2. **不定义中枢延伸**：中枢形成后，第 4 段若仍与中枢区间重合 ——
       按原文「如果这5分钟次级别延伸出6段，那么就当成两个30分钟盘整类型的连接」
       ⇒ **关闭当前中枢并立即新起一个中枢**，不把第 4 段并入延伸。
       这就是「允许盘整+盘整」的机制来源。
    3. **中枢完成即换**：原文「永远只针对一个正在完成着的同级别中枢，一旦该
       中枢完成，就继续关注下一个同级别中枢」⇒ 每段走势类型最多含 1 个中枢
       （本实现口径：段内含多个中枢时按顺序切开，使每段只归一个中枢）。
    4. **不足三段**：构不成中枢的零散段，单独成为一个走势类型段（kind="none"），
       保持分解的连续性与唯一性（原文要求分解唯一）。

    Args:
        bis: 笔或线段列表（方向交替排列）。
        config: 缠论配置（用于读取 ``zs_min_lines``）。

    Returns:
        按时间顺序排列的 :class:`TrendSegment` 列表，其 ``lines`` 首尾相接、
        恰好覆盖整个输入序列（分解唯一性 ⇒ 不漏不重）。
    """
    if config is None:
        config = ChanlunConfig()

    min_lines = max(3, int(getattr(config, "zs_min_lines", _MIN_CENTRAL_SEGMENTS)))
    if len(bis) < min_lines:
        # 不足以构成任何中枢：整段作为一个「未完成走势类型」返回。
        if not bis:
            return []
        return [
            TrendSegment(lines=list(bis), zss=[], kind="none", index=0)
        ]

    segments: list[TrendSegment] = []
    i = 0
    n = len(bis)

    while i < n:
        # ── 尝试从 i 起形成一个中枢（需要 >= min_lines 段且有重合）──────────
        zs_lines: list[BI | XD] = []
        zs: ZS | None = None
        j = i
        while j < n and len(zs_lines) < min_lines:
            zs_lines.append(bis[j])
            j += 1

        if len(zs_lines) == min_lines:
            zd, zg = _zs_interval(zs_lines)
            if zg > zd:
                zs = _make_zs(zs_lines, zd, zg, len(segments))

        if zs is None:
            # 构不成中枢 ⇒ 单独成段（保持连续覆盖）
            segments.append(
                TrendSegment(
                    lines=[bis[i]], zss=[], kind="none", index=len(segments)
                )
            )
            i += 1
            continue

        # ── 中枢已成：不定义延伸，遇到下一段与中枢重合即「盘整+盘整」───────
        # 原文第38课：「如果这5分钟次级别延伸出6段，那么就当成两个30分钟盘整
        # 类型的连接」⇒ 这里**不并入**，直接收尾当前段，让下一轮循环
        # 从 j 起新起一个中枢 ⇒ 得到「盘整 + 盘整」连接。
        #
        # 但同时保留中枢的进入段/离开段信息（原文第20课「中枢由进入段 + 至少3段
        # 重叠 + 离开段构成」），让下游买卖点判定能用上。
        seg_lines = list(zs_lines)
        kind = _direction_of(seg_lines)
        seg = TrendSegment(lines=seg_lines, zss=[zs], kind=kind, index=len(segments))
        _attach_enter_leave(seg, bis, i, j)
        segments.append(seg)
        i = j

    return segments


def _make_zs(lines: list[BI | XD], zd: float, zg: float, index: int) -> ZS:
    """构造中枢对象（ZG/ZD 由前三段重叠确定后即冻结 —— 同级别分解不延伸）。

    20课L22：GG=max(gn)/DD=min(dn)，n遍历与中枢方向一致的 Z走势段(同向段)，
    反向段不参与。中枢方向=首段方向(30课L142)。
    """
    d = _direction_of(lines)
    # 只取与中枢方向一致的同向段(Zn)；方向缺失时回落全段（防御）
    same_dir = [x for x in lines if x.direction.value == d] or lines
    return ZS(
        lines=list(lines),
        zg=zg,
        zd=zd,
        gg=max(x.high for x in same_dir),
        dd=min(x.low for x in same_dir),
        direction=d,
        index=index,
        done=True,
        start=lines[0].start,
        end=lines[-1].end,
    )


def _direction_of(lines: list[BI | XD]) -> str:
    """段的方向：原文按构成中枢的走势方向，这里取首段方向（交替序列的代表方向）。"""
    if not lines:
        return ""
    return "up" if lines[0].direction == Direction.UP else "down"


def _attach_enter_leave(
    seg: TrendSegment,
    all_lines: list[BI | XD],
    start_idx: int,
    end_idx: int,
) -> None:
    """记录中枢的进入段与离开段（原文第20课：中枢 = 进入段 + 3段重叠 + 离开段）。"""
    zs = seg.zss[0]
    if start_idx > 0:
        zs.enter_bi = all_lines[start_idx - 1]
    if end_idx < len(all_lines):
        zs.exit_bi = all_lines[end_idx]


# ── 与既有非同级别分解的对照（供守门脚本/测试复用）───────────────────────


def decomposition_diff(
    bis: list[BI],
    config: ChanlunConfig | None = None,
) -> dict:
    """返回两种分解在同一序列上的差异指标，用于守门与文档对照。

    Returns:
        dict: ``same_level`` / ``non_same_level`` 两把钥匙，各含
        ``n_segments``（走势类型段数）、``n_zs``（中枢数）、
        ``max_zs_segments``（单中枢最多段数）。
    """
    from easy_tdx.chanlun.zs import find_zss

    cfg = config or ChanlunConfig()
    same = decompose_same_level(bis, cfg)
    other = find_zss(bis, cfg)
    return {
        "same_level": {
            "n_segments": len(same),
            "n_zs": sum(len(s.zss) for s in same),
            "max_zs_segments": max((len(z.lines) for s in same for z in s.zss), default=0),
            "panzheng_plus_panzheng": sum(
                1
                for a, b in zip(same, same[1:])
                if a.is_panzheng and b.is_panzheng
            ),
        },
        "non_same_level": {
            "n_segments": 0,  # 非同级别分解不产出「走势类型段」
            "n_zs": len(other),
            "max_zs_segments": max((len(z.lines) for z in other), default=0),
            "panzheng_plus_panzheng": 0,
        },
    }
