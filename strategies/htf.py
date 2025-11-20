import numpy as np
import pandas as pd

def detect_htf(window,
               rs_rating=0.0, # New in Cycle 5
               min_up_ratio=0.8,
               max_pullback=0.25,
               min_flag_days=3,
               max_flag_days=12):

    high = window['high'].values.astype(float)
    low = window['low'].values.astype(float)
    close = window['close'].values.astype(float)
    vol = window['volume'].values.astype(float)

    n = len(window)
    if n < 20:
        return False, np.nan, np.nan

    # 0. RS Filter (Cycle 5)
    if rs_rating < 0:
        return False, np.nan, np.nan

    start_price = close[0]
    if start_price == 0: return False, np.nan, np.nan

    max_idx = high.argmax()
    max_price = high[max_idx]

    up = max_price / start_price - 1.0
    if up < min_up_ratio:
        return False, np.nan, np.nan

    flag = window.iloc[max_idx+1:]
    flag_len = len(flag)
    if not (min_flag_days <= flag_len <= max_flag_days):
        return False, np.nan, np.nan

    flag_high = flag['high'].max()
    flag_low = flag['low'].min()
    
    if max_price == 0: return False, np.nan, np.nan
        
    pullback = 1.0 - flag_low / max_price
    if pullback > max_pullback:
        return False, np.nan, np.nan

    up_vol_mean = vol[:max_idx+1].mean()
    flag_vol_mean = flag['volume'].mean()
    
    if np.isnan(up_vol_mean) or np.isnan(flag_vol_mean):
        return False, np.nan, np.nan
        
    if not (flag_vol_mean < up_vol_mean):
        return False, np.nan, np.nan

    buy_price = flag_high
    stop_price = flag_low

    if stop_price >= buy_price:    
        return False, np.nan, np.nan

    return True, float(buy_price), float(stop_price)
