from pathlib import Path
from marketbot.config import load_config


def test_load_config_reads_yaml(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        "min_market_cap_inr: 10000000000\n"
        "top_n_unusual: 5\n"
        "chandelier_length: 22\n"
        "chandelier_mult: 3.0\n"
        "sma_periods: [20, 50, 200]\n"
    )
    cfg = load_config(p)
    assert cfg.min_market_cap_inr == 10_000_000_000
    assert cfg.top_n_unusual == 5
    assert cfg.chandelier_length == 22
    assert cfg.chandelier_mult == 3.0
    assert cfg.sma_periods == [20, 50, 200]


def test_load_config_applies_defaults_for_missing_keys(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("min_market_cap_inr: 5\n")
    cfg = load_config(p)
    assert cfg.rsi_period == 14          # default fills in
    assert cfg.avp_value_area_pct == 0.70
