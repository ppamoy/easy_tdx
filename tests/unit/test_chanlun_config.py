"""ChanlunConfig 序列化金标测试（V658）。

锁定 to_dict 输出所有影响缠论模型行为的配置项，避免新增配置字段后
只在默认构造器里生效、序列化却漏掉。
"""

from __future__ import annotations

from easy_tdx.chanlun.config import ChanlunConfig


def test_default_config_to_dict_includes_model_switches() -> None:
    d = ChanlunConfig().to_dict()

    assert d["multi_level"] is True
    assert d["mmd_1st_dedup"] is True
    assert d["mmd_3rd_type_technical"] is False
    assert d["bi_type"] == "new"
    assert d["zs_min_lines"] == 3


def test_custom_config_to_dict_roundtrip_switches() -> None:
    config = ChanlunConfig(
        multi_level=False,
        mmd_1st_dedup=False,
        mmd_3rd_type_technical=True,
        bi_type="old",
        zs_min_lines=4,
    )
    d = config.to_dict()

    assert d["multi_level"] is False
    assert d["mmd_1st_dedup"] is False
    assert d["mmd_3rd_type_technical"] is True
    assert d["bi_type"] == "old"
    assert d["zs_min_lines"] == 4
