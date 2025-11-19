import numpy as np
import pandas as pd
from .utils import get_zigzag_pivots

def detect_vcp(window,
               vol_ma50_val, # Scalar
               price_ma50_val, # Scalar
               zigzag_threshold=0.04, # Tightened from 0.05
               min_up_ratio=0.5, # Increased from 0.4
               vol_dry_up_ratio=0.6):

    high = window['high'].values
    low = window['low'].values
    close = window['close'].values
    vol = window['volume'].values
    
    n = len(window)
    if n < 50: return False, np.nan, np.nan

    start_price = close[0]
    if start_price == 0: return False, np.nan, np.nan
    
    # 0. Trend Filter: Price > MA50 (if available)
    if not np.isnan(price_ma50_val) and close[-1] < price_ma50_val:
        return False, np.nan, np.nan
    window_high = high.max()
    window_high_idx = high.argmax()
    
    if window_high_idx < 10: return False, np.nan, np.nan
        
    up = window_high / start_price - 1.0
    if up < min_up_ratio:
        return False, np.nan, np.nan

    base_high = high[window_high_idx:]
    base_low = low[window_high_idx:]
    base_close = close[window_high_idx:]
    
    if len(base_close) < 10: return False, np.nan, np.nan
    
    pivots = get_zigzag_pivots(base_high, base_low, base_close, threshold_pct=zigzag_threshold)
    
    troughs = [p for p in pivots if p['type'] == 'trough']
    peaks = [p for p in pivots if p['type'] == 'peak']
    
    if len(troughs) < 2:
        return False, np.nan, np.nan
        
    valid_vcp = True
    
    # Check Lows (Increasing)
    for i in range(len(troughs) - 1):
        if troughs[i+1]['price'] < troughs[i]['price'] * 0.98:
             valid_vcp = False
             break
    if not valid_vcp: return False, np.nan, np.nan
    
    # Check Depth Contraction
    legs = []
    current_peak = pivots[0]['price']
    for p in pivots:
        if p['type'] == 'peak':
            current_peak = p['price']
        elif p['type'] == 'trough':
            if current_peak == 0: continue
            depth = (current_peak - p['price']) / current_peak
            legs.append(depth)
            
    for i in range(len(legs) - 1):
        if legs[i+1] >= legs[i]:
            valid_vcp = False
            break
    if not valid_vcp: return False, np.nan, np.nan
    
    # Volume Filter
    last_3_days_vol = vol[-3:].mean()
    if not np.isnan(vol_ma50_val) and vol_ma50_val > 0:
        if last_3_days_vol > vol_ma50_val * vol_dry_up_ratio:
            return False, np.nan, np.nan
            
    if len(peaks) > 0:
        buy_price = peaks[-1]['price']
    else:
        buy_price = window_high
        
    stop_price = troughs[-1]['price']
    if stop_price >= buy_price: return False, np.nan, np.nan

    return True, float(buy_price), float(stop_price)
