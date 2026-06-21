import pandas as pd
from datetime import date, datetime, timezone, timedelta
from marketbot.config import Config
from marketbot.tradingview import scan_momentum, TvRow, TvScan, compute_risk_reward
from marketbot.brief import render_tv_scan
from marketbot import main as m


def _fake_query(rows):
    """Return a query_fn that ignores filters and yields a fixed scanner frame."""
    df = pd.DataFrame(rows)

    def query_fn(min_cap, max_cap, limit):
        return df

    return query_fn


def _no_history(_symbol):
    """history_fn that supplies no daily data → forces the TV 1-month-high fallback."""
    return None


# columns mirror the real tradingview-screener scanner output we depend on
def _row(ticker, close, vol, month_high, rel_vol, cap=5e10, change=1.0, atr=None,
         first_bar_time=None, open=None, high=None, low=None):
    return {
        "ticker": ticker, "name": ticker.split(":")[-1],
        "open": open if open is not None else close,
        "high": high if high is not None else close,
        "low": low if low is not None else close,
        "close": close, "change": change, "volume": vol, "market_cap_basic": cap,
        "High.1M": month_high, "relative_volume_10d_calc": rel_vol,
        "ATR": atr if atr is not None else close * 0.03,
        "first_bar_time": first_bar_time,
    }


def test_only_one_month_new_highs_included():
    cfg = Config()
    rows = [
        _row("NSE:UP", close=105, vol=1000, month_high=100, rel_vol=2.0),   # at new high
        _row("NSE:DOWN", close=90, vol=5000, month_high=100, rel_vol=2.0),  # below 1M high
    ]
    scan = scan_momentum(cfg, query_fn=_fake_query(rows), history_fn=_no_history)
    syms = [r.symbol for r in scan.universe]
    assert "UP" in syms
    assert "DOWN" not in syms


def test_universe_capped_and_ranked_by_turnover():
    cfg = Config(top_n_turnover=2)
    rows = [
        _row("NSE:A", close=100, vol=100, month_high=100, rel_vol=1.0),   # turn 10k
        _row("NSE:B", close=100, vol=300, month_high=100, rel_vol=1.0),   # turn 30k
        _row("NSE:C", close=100, vol=200, month_high=100, rel_vol=1.0),   # turn 20k
    ]
    scan = scan_momentum(cfg, query_fn=_fake_query(rows), history_fn=_no_history)
    assert [r.symbol for r in scan.universe] == ["B", "C"]   # top-2 by turnover


def test_buy_flag_requires_volume_confirmation():
    cfg = Config(top_n_turnover=10, buy_volume_mult=1.5)
    rows = [
        _row("NSE:HOT", close=100, vol=1000, month_high=100, rel_vol=2.0),  # >=1.5x
        _row("NSE:MEH", close=100, vol=1000, month_high=100, rel_vol=1.0),  # <1.5x
    ]
    scan = scan_momentum(cfg, query_fn=_fake_query(rows), history_fn=_no_history)
    buys = {r.symbol for r in scan.buys}
    assert "HOT" in buys
    assert "MEH" not in buys
    # both are still in the screener universe (new high + turnover)
    assert {r.symbol for r in scan.universe} == {"HOT", "MEH"}


def test_rows_are_tvrow_with_turnover_computed():
    cfg = Config()
    rows = [_row("NSE:X", close=50, vol=400, month_high=40, rel_vol=3.0)]
    scan = scan_momentum(cfg, query_fn=_fake_query(rows), history_fn=_no_history)
    r = scan.universe[0]
    assert isinstance(r, TvRow)
    assert r.turnover == 50 * 400
    assert r.new_high is True


def _ts(y, mo, d):
    return datetime(y, mo, d, tzinfo=timezone.utc).timestamp()


def test_excludes_stocks_listed_within_12_months():
    cfg = Config(top_n_turnover=10)
    now = datetime(2026, 6, 21, tzinfo=timezone.utc)
    rows = [
        _row("NSE:OLD", close=105, vol=1000, month_high=100, rel_vol=2.0,
             first_bar_time=_ts(2019, 1, 1)),   # listed long ago → eligible
        _row("NSE:IPO", close=105, vol=9000, month_high=100, rel_vol=2.0,
             first_bar_time=_ts(2026, 1, 15)),  # listed 5 months ago → excluded
    ]
    scan = scan_momentum(cfg, query_fn=_fake_query(rows), history_fn=_no_history, now=now)
    syms = {r.symbol for r in scan.universe}
    assert "OLD" in syms
    assert "IPO" not in syms


def _level_history(levels, n=25):
    """history_fn whose flat daily level depends on the symbol."""
    def fn(symbol):
        lvl = levels[symbol]
        return pd.DataFrame({"open": [lvl] * n, "high": [lvl] * n,
                             "low": [lvl] * n, "close": [lvl] * n})
    return fn


def test_heikin_ashi_new_high_uses_ha_close():
    cfg = Config(top_n_turnover=10, new_high_lookback_days=20)
    # Both names are near their 1-month high (pass the pre-filter); the HA-close
    # confirmation against prior HA closes is what differentiates them.
    rows = [
        _row("NSE:BREAK", close=110, vol=1000, month_high=110, rel_vol=2.0,
             open=110, high=110, low=110),     # HA close 110 vs prior 100 → new HA high
        _row("NSE:STALL", close=105, vol=2000, month_high=110, rel_vol=2.0,
             open=105, high=105, low=105),     # HA close 105 vs prior 110 → not a new high
    ]
    hist = _level_history({"BREAK": 100.0, "STALL": 110.0})
    scan = scan_momentum(cfg, query_fn=_fake_query(rows), history_fn=hist)
    syms = {r.symbol for r in scan.universe}
    assert "BREAK" in syms
    assert "STALL" not in syms
    assert scan.universe[0].new_high_basis == "HA"


def test_risk_reward_uses_atr_stop_when_within_cap():
    cfg = Config(atr_stop_mult=1.0, max_risk_pct=0.07, rr_multiples=[1.0, 2.0, 3.0])
    # ATR = 3 on a ₹100 entry → 3% risk, under the 7% cap → ATR governs the stop
    rr = compute_risk_reward(entry=100.0, atr=3.0, cfg=cfg)
    assert rr.stop == 97.0
    assert round(rr.risk_per_share, 4) == 3.0
    assert round(rr.risk_pct, 4) == 0.03
    # targets at 1R/2R/3R = +3 / +6 / +9
    assert [round(t.price, 2) for t in rr.targets] == [103.0, 106.0, 109.0]
    assert [t.r_multiple for t in rr.targets] == [1.0, 2.0, 3.0]


def test_risk_reward_caps_stop_at_max_risk_pct():
    cfg = Config(atr_stop_mult=1.0, max_risk_pct=0.07)
    # ATR = 12 on ₹100 → 12% > 7% cap → risk capped at 7
    rr = compute_risk_reward(entry=100.0, atr=12.0, cfg=cfg)
    assert round(rr.risk_per_share, 6) == 7.0   # capped, not 12
    assert round(rr.stop, 6) == 93.0
    assert rr.capped is True


def test_risk_reward_position_size_per_lakh():
    cfg = Config(position_risk_pct=0.02)
    rr = compute_risk_reward(entry=100.0, atr=4.0, cfg=cfg)   # risk ₹4/sh
    # 2% of ₹1,00,000 = ₹2,000 risk budget; ₹2,000 / ₹4 = 500 shares
    assert rr.shares_per_lakh == 500


def _tvrow(sym, close=100.0, rel_vol=2.1, atr=3.0, buy=True):
    return TvRow(sym, sym, close, 7.5, 1000, close * 1000, 5e10, close * 0.95,
                 rel_vol, True, buy=buy, atr=atr)


def test_render_tv_scan_has_headers_and_symbols():
    scan = TvScan(as_of=date(2026, 6, 21))
    scan.universe = [_tvrow("PARAS")]
    scan.buys = [scan.universe[0]]
    text = render_tv_scan(scan)
    assert "TradingView Momentum Scan" in text
    assert "BUY" in text and "PARAS" in text
    assert "21 Jun" in text


def test_render_tv_scan_includes_risk_reward_and_horizon():
    scan = TvScan(as_of=date(2026, 6, 21))
    scan.universe = [_tvrow("PARAS", close=100.0, atr=3.0)]
    scan.buys = list(scan.universe)
    text = render_tv_scan(scan)
    assert "Entry" in text and "Stop" in text       # risk side
    assert "1R" in text and "2R" in text            # reward matrix
    assert "Horizon" in text and "3-8 weeks" in text  # time horizon


def _fresh_scan(sym="X"):
    s = TvScan()
    s.universe = [TvRow(sym, sym, 10.0, 1.0, 100, 1000, 5e10, 9.0, 2.0, True, buy=True)]
    s.buys = list(s.universe)
    return s


def test_run_tv_scan_sends_and_reports_status(tmp_path):
    sent = {}
    status = m.run_tv_scan(
        run_date=date(2026, 6, 22),   # a Monday → trading day
        cfg=Config(),
        send_fn=lambda t: sent.setdefault("text", t),
        dry_run=False,
        scan_fn=lambda c: _fresh_scan(),
        dedup_path=tmp_path / "tv_alerts.json",
    )
    assert status == "sent"
    assert "TradingView Momentum Scan" in sent["text"]


def test_run_tv_scan_degrades_on_tv_failure(tmp_path):
    sent = {}
    def boom(_cfg):
        raise RuntimeError("scanner 503")
    status = m.run_tv_scan(
        run_date=date(2026, 6, 22), cfg=Config(),
        send_fn=lambda t: sent.setdefault("text", t),
        dry_run=False, scan_fn=boom, dedup_path=tmp_path / "tv_alerts.json",
    )
    assert status == "unavailable"
    assert "TradingView scan failed" in sent["text"]


def test_run_tv_scan_suppresses_repeat_buys_same_day(tmp_path):
    """Second run of the day must not re-alert a symbol already sent."""
    p = tmp_path / "tv_alerts.json"
    sent = []
    common = dict(run_date=date(2026, 6, 22), cfg=Config(),
                  scan_fn=lambda c: _fresh_scan("PARAS"), dedup_path=p)

    m.run_tv_scan(send_fn=lambda t: sent.append(t), dry_run=False, **common)
    assert "PARAS" in sent[0]                       # first run alerts it

    m.run_tv_scan(send_fn=lambda t: sent.append(t), dry_run=False, **common)
    assert "BUY — none" in sent[1]                  # no fresh BUY in the 2nd run
    assert "✅" not in sent[1]                       # not re-flagged as a fresh buy
    assert "·sent" in sent[1]                        # shown as already-alerted instead


def test_run_tv_scan_dry_run_does_not_persist(tmp_path):
    p = tmp_path / "tv_alerts.json"
    m.run_tv_scan(run_date=date(2026, 6, 22), cfg=Config(),
                  send_fn=lambda t: None, dry_run=True,
                  scan_fn=lambda c: _fresh_scan("PARAS"), dedup_path=p)
    assert not p.exists()                           # dry run writes no state
