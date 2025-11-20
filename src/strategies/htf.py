import numpy as np
import pandas as pd

def detect_htf(window,
               rs_rating=0.0, # New in Cycle 5
               min_up_ratio=0.6, # Relaxed from 0.8 (Cycle 7)
               max_pullback=0.25,
               min_flag_days=3,
               max_flag_days=12):

    high = window['high'].values.astype(float)
    low = window['low'].values.astype(float)
    close = window['close'].values.astype(float)
    vol = window['volume'].values.astype(float)

    n = len(window)
    if n < 20:
        return False, np.nan, np.nan, None

    # 0. RS Filter (Cycle 5)
    if rs_rating < 0:
        return False, np.nan, np.nan, None

    start_price = close[0]
    if start_price == 0: return False, np.nan, np.nan, None

    max_idx = high.argmax()
    max_price = high[max_idx]

    up = max_price / start_price - 1.0
    if up < min_up_ratio:
        return False, np.nan, np.nan, None

    flag = window.iloc[max_idx+1:]
    flag_len = len(flag)
    if not (min_flag_days <= flag_len <= max_flag_days):
        return False, np.nan, np.nan, None

    flag_high = flag['high'].max()
    flag_low = flag['low'].min()
    
    if max_price == 0: return False, np.nan, np.nan, None
        
    pullback = 1.0 - flag_low / max_price
    if pullback > max_pullback:
        return False, np.nan, np.nan, None

    up_vol_mean = vol[:max_idx+1].mean()
    flag_vol_mean = flag['volume'].mean()
    
    if np.isnan(up_vol_mean) or np.isnan(flag_vol_mean):
        return False, np.nan, np.nan, None
        
    if not (flag_vol_mean < up_vol_mean):
        return False, np.nan, np.nan, None

    buy_price = flag_high
    stop_price = flag_low

    if stop_price >= buy_price:    
        return False, np.nan, np.nan, None

    # Grading System (Cycle 10)
    # A: Pole > 90%, Pullback < 15%, Vol Drop > 50%
    # B: Pole > 90%, Pullback 15-20%
    # C: Pullback 20-25%
    
    vol_drop = 1.0 - flag_vol_mean / up_vol_mean
    grade = 'C' # Default
    
    if up > 0.90:
        if pullback < 0.15 and vol_drop > 0.50:
            grade = 'A'
        elif pullback < 0.20:
            grade = 'B'
            
    return True, float(buy_price), float(stop_price), grade
