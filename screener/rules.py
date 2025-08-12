# -*- coding: utf-8 -*-
"""
Screening rules for identifying stock patterns and setups.
Each function returns a boolean value indicating if the pattern is detected.
"""
import numpy as np
import pandas as pd
from . import config

def detect_vcp(df: pd.DataFrame) -> bool:
    """ Heuristic VCP: Detects if range/ATR has contracted over 4 windows. """
    if len(df) < 130:
        return False
    ok_range, ok_atr = True, True
    prev_range = None
    prev_atr = None
    n = len(df)
    for (a, b) in config.VCP_WINDOWS:
        seg = df.iloc[n - a : n - b]
        if len(seg) < 10:
            return False
        r = (seg["High"].max() - seg["Low"].min()) / max(1e-9, seg["Low"].min())
        atr = seg["ATR20"].median()
        if prev_range is not None and not (r <= prev_range * config.VCP_RANGE_DECAY):
            ok_range = False
        if prev_atr is not None and not (atr <= prev_atr * config.VCP_ATR_DECAY):
            ok_atr = False
        prev_range, prev_atr = r, atr

    if not (ok_range and ok_atr):
        return False

    # Volume contraction (recent 30d median vs. prior 30d median)
    vol_recent = df["Volume"].tail(30).median()
    vol_prev = df["Volume"].tail(60).head(30).median()
    volume_contract = vol_recent < vol_prev * 0.8

    # Price near a pivot point (within 5% of 120d high)
    near_pivot = (df["Close"].iloc[-1] >= df["High"].tail(120).max() * 0.95)

    return volume_contract and near_pivot

def detect_platform_breakout_imminent(df: pd.DataFrame) -> bool:
    """ Platform/Cup-with-Handle: Detects a 30-150 day base with depth <= 33%. """
    if len(df) < config.PLATFORM_MAX_DAYS + 5:
        return False
    window = df.tail(config.PLATFORM_MAX_DAYS)
    H = window["High"].max()
    H_idx = window["High"].idxmax()
    base_window = window.loc[:H_idx]
    L = base_window["Low"].min()

    depth = (H - L) / H if H > 0 else 1.0
    base_len = len(base_window)

    if not (config.PLATFORM_MIN_DAYS <= base_len <= config.PLATFORM_MAX_DAYS and depth <= config.PLATFORM_MAX_DEPTH):
        return False

    # Price near pivot (within 5% of base high)
    near_pivot = df["Close"].iloc[-1] >= H * 0.95

    # Volume contraction (recent 20d median vs. prior 20d median)
    vol_recent = df["Volume"].tail(20).median()
    vol_prev = df["Volume"].tail(40).head(20).median()
    volume_contract = vol_recent < vol_prev * 0.85

    return near_pivot and volume_contract

def detect_breakaway_gap_avwap(df: pd.DataFrame) -> bool:
    """ Finds a recent breakaway gap and checks for stabilization above AVWAP. """
    if len(df) < 80:
        return False
    recent = df.tail(60)
    for i in range(1, len(recent)):
        today = recent.iloc[i]
        prev = recent.iloc[i - 1]
        gap_up = (today["Open"] > prev["High"] * (1 + config.GAP_PCT_MIN / 2)) and \
                 (today["Close"] > prev["Close"] * (1 + config.GAP_PCT_MIN))

        if gap_up:
            gap_top = max(today["Open"], prev["High"])
            anchor_loc = recent.index[i]
            sub = df.loc[anchor_loc:]

            # Calculate AVWAP from the gap day
            pv = (sub["Close"] * sub["Volume"]).cumsum()
            vv = sub["Volume"].cumsum().replace(0, np.nan)
            avwap = pv / vv

            # Check for stabilization in the next 2-5 days
            for k in range(i + 2, min(i + 6, len(recent))):
                row = recent.iloc[k]
                av = avwap.loc[recent.index[k]]
                if pd.notna(av) and (row["Close"] > gap_top) and (row["Close"] > av):
                    return True
    return False

def detect_first_pullback_ema20(df: pd.DataFrame) -> bool:
    """ Detects the first pullback to EMA20 after a recent breakout. """
    if len(df) < 150:
        return False

    # Find a recent breakout (new 120d high on high volume)
    hh120 = df["High"].rolling(120).max()
    vol50 = df["Volume"].rolling(50).mean()
    recent = df.tail(config.FIRST_PULLBACK_LOOKBACK)
    breakout_idx = None
    for i in range(len(recent)):
        row_idx = recent.index[i]
        if recent["High"].iloc[i] >= hh120.loc[row_idx] * 0.999 and \
           recent["Volume"].iloc[i] >= vol50.loc[row_idx] * config.VOLUME_BOOST:
            breakout_idx = row_idx
            break

    if breakout_idx is None:
        return False

    # Check if price touched EMA20 after the breakout
    after_breakout = df.loc[breakout_idx:].tail(20)
    if not (after_breakout["Low"] <= after_breakout["EMA20"]).any():
        return False

    # Simplified reversal signal: last day is a green bar, close above EMA20, volume increase
    last = df.iloc[-1]
    prev = df.iloc[-2]
    reversal = (last["Close"] > last["Open"]) and \
               (last["Close"] > last["EMA20"]) and \
               (last["Volume"] > prev["Volume"])
    return reversal

def detect_rs_leads(df: pd.DataFrame, twii: pd.DataFrame) -> bool:
    """ Detects if the RS line is making a new high before the price. """
    if df.empty or twii.empty:
        return False

    aligned = df.join(twii[["Close"]].rename(columns={"Close": "TWII"}), how="inner")
    if len(aligned) < config.RS_LEAD_WINDOW + 5:
        return False

    aligned["RS"] = aligned["Close"] / aligned["TWII"]
    rs_high = aligned["RS"].rolling(config.RS_LEAD_WINDOW).max()
    px_high = aligned["Close"].rolling(config.RS_LEAD_WINDOW).max()

    # RS made a new 60d high in the last 5 days
    rs_recent_high = (aligned["RS"].tail(5) >= rs_high.tail(5) * 0.999).any()

    # Price is close to its 60d high (within 2%)
    dist_px_high = aligned["Close"].iloc[-1] / px_high.iloc[-1] - 1.0

    return rs_recent_high and (dist_px_high >= -0.02)
