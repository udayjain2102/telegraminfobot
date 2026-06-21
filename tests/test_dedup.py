from datetime import date
from marketbot.dedup import load_alerted, record_alerted


def test_record_and_load_roundtrip(tmp_path):
    p = tmp_path / "tv_alerts.json"
    day = date(2026, 6, 22)
    assert load_alerted(p, day) == set()       # nothing yet
    record_alerted(p, day, ["PARAS", "TARIL"])
    assert load_alerted(p, day) == {"PARAS", "TARIL"}


def test_record_merges_within_same_day(tmp_path):
    p = tmp_path / "tv_alerts.json"
    day = date(2026, 6, 22)
    record_alerted(p, day, ["PARAS"])
    record_alerted(p, day, ["TARIL"])
    assert load_alerted(p, day) == {"PARAS", "TARIL"}


def test_state_resets_on_a_new_day(tmp_path):
    p = tmp_path / "tv_alerts.json"
    record_alerted(p, date(2026, 6, 22), ["PARAS"])
    # a different day → yesterday's alerts must not carry over
    assert load_alerted(p, date(2026, 6, 23)) == set()
    record_alerted(p, date(2026, 6, 23), ["NEW"])
    assert load_alerted(p, date(2026, 6, 23)) == {"NEW"}
    assert load_alerted(p, date(2026, 6, 22)) == set()  # old day no longer current
