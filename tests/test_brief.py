from datetime import date
from marketbot.brief import render_brief, render_unavailable
from marketbot.screen import Report, StockRow
from marketbot.market_overview import MarketOverview
from marketbot.volume_profile import LevelHit


def _row(sym, chg=1.0, rv=3.0, poc=True):
    hits = [LevelHit("POC", 385.0, "support", 1.0)] if poc else []
    return StockRow(symbol=sym, name=sym, close=389.0, chg_pct=chg, rel_vol=rv,
                    turnover=1e9, sector="IT", chandelier_dir=1,
                    buy_flip=True, sell_flip=False, level_hits=hits, rsi=25.0)


def test_render_includes_all_section_headers():
    report = Report(as_of=date(2026, 6, 12))
    report.unusual_volume = [_row("MTARTECH")]
    report.turnover_leaders = [_row("HDFCBANK")]
    report.high_conviction = [_row("APOLLO")]
    report.chandelier_buys = [_row("APOLLO")]
    report.rsi_oversold = [_row("XYZ")]
    ov = MarketOverview(nifty=(24310.0, 0.8), sensex=(79850.0, 0.7), top_sectors=[("IT", 1.9)])
    text = render_brief(report, ov)
    for marker in ["Market Brief", "Unusual activity", "Most-traded",
                   "Momentum BUY", "Chandelier", "12 Jun"]:
        assert marker in text


def test_render_unavailable_message():
    text = render_unavailable(date(2026, 6, 12), "data not ready")
    assert "12 Jun" in text
    assert "not ready" in text.lower()


def test_empty_report_still_renders_without_error():
    report = Report(as_of=date(2026, 6, 12))
    ov = MarketOverview(nifty=None, sensex=None, top_sectors=[])
    text = render_brief(report, ov)
    assert "Market Brief" in text
