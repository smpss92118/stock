import numpy as np
import pandas as pd

def detect_cup(window,
               ma_info, # Dict with last values of MAs: {'ma50':, 'ma150':, 'ma200':, 'low52':}
               rs_rating=0.0, # New in Cycle 6
               min_depth=0.12,
               max_depth=0.33,
               handle_max_depth=0.15):

    high = window['high'].values
    low = window['low'].values
    close = window['close'].values
    
    n = len(window)
    if n < 40: return False, np.nan, np.nan
    
    # 0. RS Filter (Cycle 6)
    if rs_rating < 0:
        return False, np.nan, np.nan

    current_price = close[-1]

    # 1. Trend Template Check (Minervini)
    # Price > MA50 > MA150 > MA200
    # Price > 52-week low * 1.25
    # MA200 slope > 0 (Approx by current > 1 month ago)
    
    # We need historical MA200 to check slope.
    # ma_info contains current values.
    # We can check basic ordering first.
    
    try:
        if not (current_price > ma_info['ma50'] > ma_info['ma150'] > ma_info['ma200']):
            return False, np.nan, np.nan
        if current_price < ma_info['low52'] * 1.25:
            return False, np.nan, np.nan
    except:
        return False, np.nan, np.nan # Missing MAs

    # 2. Cup Shape
    first_half = high[:n//2]
    if len(first_half) == 0: return False, np.nan, np.nan
    left_high_idx = first_half.argmax()
    left_high_price = first_half.max()

    mid_end = int(n*0.75)
    mid = close[left_high_idx:mid_end]
    if len(mid) == 0: return False, np.nan, np.nan

    bottom_rel = mid.argmin()
    bottom_idx = left_high_idx + bottom_rel
    bottom_price = close[bottom_idx]

    if left_high_price == 0: return False, np.nan, np.nan
    depth = 1.0 - bottom_price / left_high_price
    if not (min_depth <= depth <= max_depth):
        return False, np.nan, np.nan

    # 3. Handle Logic
    right = close[bottom_idx:]
    if len(right) < 10: return False, np.nan, np.nan
    right_high = right.max()
    
    handle_len = max(int(n * 0.2), 5)
    handle = window.iloc[-handle_len:]
    handle_high = handle['high'].max()
    handle_low = handle['low'].min()
    
    # Handle Position: Low > Cup Low + 0.5 * Cup Depth
    # Cup High is Left High or Right High? Usually Right High (Pivot).
    cup_range = right_high - bottom_price
    min_handle_low = bottom_price + 0.5 * cup_range
    
    if handle_low < min_handle_low:
        return False, np.nan, np.nan
        
    # Handle Drift (Price down, Vol down)
    # Simple check: Handle Close < Handle Open (Net down) AND Vol < Avg Vol?
    # User: "Price down, Vol down".
    # Let's check if Handle is a pullback (High > Close)
    # And Handle Vol < Avg Vol
    handle_vol_mean = handle['volume'].mean()
    window_vol_mean = window['volume'].mean()
    
    if handle_vol_mean > window_vol_mean: # Vol expansion in handle is bad
        return False, np.nan, np.nan

    buy_price = handle_high
    stop_price = handle_low
    if stop_price >= buy_price: return False, np.nan, np.nan

    return True, float(buy_price), float(stop_price)
