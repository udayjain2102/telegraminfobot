from marketbot.market_overview import sector_movers, MarketOverview, build_overview
from marketbot.screen import StockRow


def _row(sym, sector, chg):
    return StockRow(symbol=sym, name=sym, close=100, chg_pct=chg, rel_vol=1.0,
                    turnover=1.0, sector=sector, chandelier_dir=1,
                    buy_flip=False, sell_flip=False)


def test_sector_movers_average_and_sort():
    rows = [_row("A", "IT", 2.0), _row("B", "IT", 0.0), _row("C", "Auto", 5.0)]
    movers = sector_movers(rows, top=2)
    assert movers[0][0] == "Auto" and movers[0][1] == 5.0
    assert movers[1][0] == "IT" and abs(movers[1][1] - 1.0) < 1e-9


def test_build_overview_uses_injected_index_fn():
    def fake_index(_ticker):
        return (24310.0, 0.8)  # (last_close, pct_change)
    ov = build_overview(rows=[_row("A", "IT", 2.0)], index_fn=fake_index)
    assert isinstance(ov, MarketOverview)
    assert ov.nifty == (24310.0, 0.8)
    assert ov.sensex == (24310.0, 0.8)
    assert ov.top_sectors[0][0] == "IT"
