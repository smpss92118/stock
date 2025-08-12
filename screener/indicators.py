# -*- coding: utf-8 -*-
"""
Functions for calculating technical indicators.
"""
import pandas as pd
from . import config

def slope_positive(series: pd.Series, lookback: int = config.EMA_SLOPE_LOOKBACK) -> bool:
    """
    Checks if the slope of a series over a given lookback period is positive.
    """
    if len(series) < lookback + 1:
        return False
    # A simple rise-over-run calculation for the slope
    return (series.iloc[-1] - series.iloc[-1 - lookback]) > 0

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes all necessary technical indicators for the screener.
    Requires columns: Open, High, Low, Close, Volume.
    """
    if df.empty:
        return df

    df = df.sort_index()

    # Moving Averages
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()

    # Average True Range (ATR)
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift()).abs()
    lc = (df["Low"] - df["Close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df["ATR20"] = tr.rolling(config.VCP_ATR_WINDOW).mean()

    # 52-Week High
    df["HH_252"] = df["High"].rolling(252).max()

    # 50-Day Average Turnover
    df["Turnover"] = df["Close"] * df["Volume"]
    df["Turnover50"] = df["Turnover"].rolling(50).mean()

    return df

def rs_percentile(all_returns: pd.Series) -> pd.Series:
    """
    Calculates the percentile rank (0-100) for each stock's return
    relative to the entire market sample.
    """
    # rank(pct=True) returns a value between 0 and 1, so we scale by 100
    ranks = all_returns.rank(pct=True) * 100.0
    return ranks
