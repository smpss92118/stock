# -*- coding: utf-8 -*-
"""
Data fetching utilities for the Taiwan Stock Screener.
- Fetches ticker list from TWSE.
- Downloads historical data from Yahoo Finance with caching.
"""
import logging
import time
from pathlib import Path
from datetime import datetime
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import yfinance as yf

log = logging.getLogger(__name__)

# --- Caching Setup ---
CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)


def requests_retry_session(
    retries=3,
    backoff_factor=0.3,
    status_forcelist=(500, 502, 504),
    session=None,
):
    session = session or requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def fetch_tickers_from_twse() -> pd.DataFrame:
    """
    Fetches the list of stock tickers from the TWSE ISIN page.
    Retries on transient HTTP errors.
    """
    urls = [
        ("TW", "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"),
        ("TWO", "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"),
        ("TWO", "https://isin.twse.com.tw/isin/C_public.jsp?strMode=5"),
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    session = requests_retry_session()
    rows = []
    for suffix, url in urls:
        try:
            r = session.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            r.encoding = "big5"
            df_list = pd.read_html(r.text)
            if not df_list:
                log.warning(f"No tables found at {url}")
                continue

            df = df_list[0]
            df.columns = df.iloc[0]
            df = df[1:]

            def split_code_name(x):
                try:
                    parts = str(x).split("\u3000")
                    code = parts[0].strip()
                    name = parts[1].strip() if len(parts) > 1 else ""
                    return code, name
                except Exception:
                    return None, None

            codes, names = zip(*df[df.columns[0]].map(split_code_name))
            tmp = pd.DataFrame({"code": codes, "name": names})
            tmp = tmp[tmp["code"].str.match(r"^\d{4}$", na=False)]
            tmp["yahoo"] = tmp["code"].astype(str) + f".{suffix}"
            rows.append(tmp[["code", "name", "yahoo"]])
        except Exception as e:
            log.error(f"Failed to fetch from {url}: {e}")

    if not rows:
        return pd.DataFrame(columns=["code", "name", "yahoo"])

    return pd.concat(rows, ignore_index=True).drop_duplicates(subset=["yahoo"])

def fetch_stock_data(
    ticker: str, start_date: str, retries=3, delay=5
) -> pd.DataFrame | None:
    """
    Downloads historical stock data from Yahoo Finance with a retry and caching mechanism.
    """
    # Sanitize ticker for use as a filename
    safe_ticker = ticker.replace("^", "INDEX_")
    cache_path = CACHE_DIR / f"{safe_ticker}.pkl"

    # Check for a valid cache from today
    if cache_path.exists():
        mod_time = datetime.fromtimestamp(cache_path.stat().st_mtime).date()
        if mod_time == datetime.today().date():
            log.debug(f"Loading {ticker} from cache.")
            return pd.read_pickle(cache_path)

    # If no valid cache, download the data
    log.debug(f"Fetching {ticker} from yfinance (no valid cache).")
    for attempt in range(retries):
        try:
            df = yf.download(
                ticker,
                start=start_date,
                progress=False,
                auto_adjust=False,
                threads=False
            )
            if df.empty:
                log.warning(f"No data for {ticker}, it might be delisted or invalid.")
                return None

            df = df.rename(columns=str.title)

            # Save to cache upon successful download
            df.to_pickle(cache_path)
            log.debug(f"Saved {ticker} data to cache.")
            return df
        except Exception as e:
            log.warning(f"Attempt {attempt + 1}/{retries} failed for {ticker}: {e}. Retrying in {delay}s...")
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                log.error(f"All {retries} attempts failed for {ticker}.")
                return None
