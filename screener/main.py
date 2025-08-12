# -*- coding: utf-8 -*-
"""
Main application logic for the Taiwan Stock Screener.
- Fetches data
- Applies screening rules
- Scores candidates
- Outputs results
"""
import argparse
import logging
import sys
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from . import config, fetch, indicators, rules

log = logging.getLogger(__name__)

def analyze_one(ticker: str, name: str, start_date: str, twii_df: pd.DataFrame) -> dict | None:
    """
    Analyzes a single stock against coarse screening criteria.
    """
    df = fetch.fetch_stock_data(ticker, start_date)
    if df is None or df.empty:
        return None

    df = indicators.compute_indicators(df)
    if df.empty or len(df) < 252:
        log.debug(f"Skipping {ticker}: not enough data ({len(df)} days) for analysis.")
        return None

    last = df.iloc[-1]
    price_ok = last["Close"] > config.MIN_PRICE
    sma50_slope_ok = indicators.slope_positive(df["SMA50"])
    sma200_slope_ok = indicators.slope_positive(df["SMA200"])
    slope_ok = sma50_slope_ok and sma200_slope_ok
    turnover_ok = last["Turnover50"] >= config.MIN_50D_TURNOVER
    hh_52w = last["HH_252"]
    dist_52w = (last["Close"] / hh_52w - 1.0) if hh_52w > 0 else -1.0
    dist_ok = (dist_52w >= -config.DIST_TO_52W_MAX)

    pass_coarse = price_ok and slope_ok and turnover_ok and dist_ok

    return {
        "ticker": ticker,
        "name": name,
        "pass_coarse": pass_coarse,
        "close": float(last["Close"]),
        "dist_52w": float(dist_52w),
        "ret_252": float(df["Close"].pct_change(config.RS_LOOKBACK).iloc[-1]),
        "raw_df": df if pass_coarse else None,
        "twii_df": twii_df if pass_coarse else None,
    }

def score_candidate(rec: dict) -> dict:
    """
    Applies fine-grained screening rules to a candidate that passed coarse screening.
    """
    df = rec.pop("raw_df", None)
    twii = rec.pop("twii_df", None)

    if df is None or twii is None:
        rec["score"] = 0
        rec["checks"] = ""
        return rec

    check_functions = {
        "VCP 最末縮口": rules.detect_vcp,
        "杯柄/平台突破在即": rules.detect_platform_breakout_imminent,
        "缺口後2–5天企穩AVWAP": rules.detect_breakaway_gap_avwap,
        "首次回測20EMA/10W反轉": rules.detect_first_pullback_ema20,
        "RS領先創新高": lambda d: rules.detect_rs_leads(d, twii),
    }

    passed_checks = []
    for name, func in check_functions.items():
        try:
            if func(df):
                passed_checks.append(name)
        except Exception as e:
            log.error(f"Error scoring {rec['ticker']} with rule '{name}': {e}")

    rec["score"] = len(passed_checks)
    rec["checks"] = ", ".join(passed_checks)
    return rec

def run():
    """
    Main execution function.
    """
    parser = argparse.ArgumentParser(description="Taiwan Stock Screener")
    parser.add_argument(
        "--since", type=str,
        default=(datetime.today() - timedelta(days=900)).strftime("%Y-%m-%d"),
        help="Start date for historical data download (YYYY-MM-DD)."
    )
    parser.add_argument("--threads", type=int, default=8, help="Number of threads for data download.")
    parser.add_argument("--out", type=str, default="tw_candidates.csv", help="Output CSV filename.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging.")
    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log.info("Fetching ticker list from TWSE...")
    code_df = fetch.fetch_tickers_from_twse()
    if code_df.empty:
        log.critical("Could not fetch ticker list. Exiting.")
        sys.exit(1)

    code_df = code_df[code_df["code"].str.match(r"^\d{4}$")]
    tickers = code_df["yahoo"].tolist()
    name_map = dict(zip(code_df["yahoo"], code_df["name"]))

    log.info("Fetching market index data (^TWII)...")
    twii_df = fetch.fetch_stock_data("^TWII", args.since)
    if twii_df is None:
        log.warning("Could not fetch market index data. RS-related scores will be affected.")
        twii_df = pd.DataFrame()

    log.info(f"Found {len(tickers)} stocks. Starting analysis (this may take a while)...")
    results = []
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        future_to_ticker = {
            executor.submit(analyze_one, t, name_map.get(t, ""), args.since, twii_df): t
            for t in tickers
        }
        for i, future in enumerate(as_completed(future_to_ticker)):
            if (i + 1) % 100 == 0:
                log.info(f"Analysis progress: {i+1}/{len(tickers)}")
            res = future.result()
            if res:
                results.append(res)
    log.info("Analysis complete.")

    if not results:
        log.error("No data could be analyzed.")
        sys.exit(1)

    df_all = pd.DataFrame(results)

    df_all["rs_pct"] = indicators.rs_percentile(df_all["ret_252"].fillna(0.0))
    coarse_pass_mask = (df_all["pass_coarse"]) & (df_all["rs_pct"] >= config.RS_PERCENTILE_MIN)
    coarse_pass_tickers = df_all[coarse_pass_mask]["ticker"].tolist()

    if not coarse_pass_tickers:
        log.info("No stocks passed the coarse screening criteria today.")
        coarse_results_path = args.out.replace(".csv", "_coarse_results.csv")
        df_all.to_csv(coarse_results_path, index=False, encoding="utf-8-sig")
        log.info(f"Coarse results saved to {coarse_results_path}")
        sys.exit(0)

    log.info(f"{len(coarse_pass_tickers)} stocks passed coarse screening. Now scoring them...")

    final_candidates = [
        score_candidate(r)
        for r in df_all[df_all["ticker"].isin(coarse_pass_tickers)].to_dict('records')
    ]

    if not final_candidates:
        log.warning("Scoring did not yield any candidates.")
        sys.exit(0)

    out_df = pd.DataFrame(final_candidates)
    out_df = out_df.merge(df_all[["ticker", "close", "rs_pct", "dist_52w"]], on="ticker")
    out_df = out_df.sort_values(
        by=["score", "rs_pct", "dist_52w"],
        ascending=[False, False, False]
    )
    cols_to_show = ["ticker", "name", "score", "checks", "close", "rs_pct", "dist_52w"]
    out_df = out_df[[c for c in cols_to_show if c in out_df.columns]]

    out_df.to_csv(args.out, index=False, encoding="utf-8-sig")

    log.info(f"Done! Results saved to {args.out}")
    print("\nTop 30 Candidates:")
    print(out_df.head(30).to_string(index=False))
