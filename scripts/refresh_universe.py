"""Weekly job: rebuild data/universe.csv from the NSE equity list + market caps."""
from marketbot.config import load_config
from marketbot.universe import (
    fetch_equity_list, build_universe, yf_market_cap, yf_sector,
)


def main() -> None:
    cfg = load_config()
    equity_csv = fetch_equity_list()
    df = build_universe(
        equity_csv,
        min_market_cap_inr=cfg.min_market_cap_inr,
        market_cap_fn=yf_market_cap,
        sector_fn=yf_sector,
        max_market_cap_inr=cfg.max_market_cap_inr,
    )
    ceil = f" .. INR {cfg.max_market_cap_inr:,}" if cfg.max_market_cap_inr else ""
    print(f"[refresh-universe] kept {len(df)} symbols >= INR {cfg.min_market_cap_inr:,}{ceil}")


if __name__ == "__main__":
    main()
