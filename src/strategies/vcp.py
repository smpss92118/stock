import numpy as np
import pandas as pd
from .utils import get_zigzag_pivots

def detect_vcp(window,
               vol_ma50_val, # Scalar
               price_ma50_val, # Scalar
               rs_rating=0.0, # RS Rating (Percentile 0-100)
               high_52w=np.nan, # 52-week High
               zigzag_threshold=0.07, # Optimized: 0.07 (was 0.05)
               min_up_ratio=0.5, # Optimized: 0.5
               vol_dry_up_ratio=0.45): # Optimized: 0.45 (was 0.5)

    high = window['high'].values
    low = window['low'].values
    close = window['close'].values
    vol = window['volume'].values
    
    n = len(window)
    if n < 50: return False, np.nan, np.nan, 0

    # 0. RS Filter (Cycle 4 - Relaxed from Cycle 8)
    # Require Stock to outperform Market (RS > 0)
    if rs_rating < 0:
        return False, np.nan, np.nan, 0

    start_price = close[0]
    if start_price == 0: return False, np.nan, np.nan, 0
    
    # 0. Trend Filter: Price > MA50 (if available)
    if not np.isnan(price_ma50_val) and close[-1] < price_ma50_val:
        return False, np.nan, np.nan, 0
    window_high = high.max()
    window_high_idx = high.argmax()
    
    if window_high_idx < 10: return False, np.nan, np.nan, 0
        
    up = window_high / start_price - 1.0
    if up < min_up_ratio:
        return False, np.nan, np.nan, 0
        
    # 1. ZigZag for Pivots
    pivots = get_zigzag_pivots(high, low, close, zigzag_threshold)
    if len(pivots) < 4: # Need at least 2 legs (High-Low-High-Low) -> 4 points
        return False, np.nan, np.nan, 0

    # 2. Analyze Contractions (High -> Low)
    # Pivots: [{'index':, 'price':, 'type':}]
    # We need pairs of High -> Low
    contractions = []
    for i in range(len(pivots)-1):
        if pivots[i]['type'] == 'peak' and pivots[i+1]['type'] == 'trough':
            high_p = pivots[i]['price']
            low_p = pivots[i+1]['price']
            depth = 1.0 - low_p / high_p
            contractions.append(depth)
            
    if len(contractions) < 2: # Need at least 2 contractions for VCP
        return False, np.nan, np.nan, 0
        
    # 2.1 Check Decreasing Volatility (Basic Damping)
    # Depths should generally decrease.
    if contractions[-1] > contractions[0]: # Simple check: Last shouldn't be larger than First
        return False, np.nan, np.nan, 0

    # 4. Dry Up Check (Existing)
    # Last few days volume < 50% of MA50
    # We already have vol_dry_up_ratio=0.5
    recent_vol_mean = vol[-5:].mean()
    if recent_vol_mean > vol_ma50_val * vol_dry_up_ratio:
        return False, np.nan, np.nan, 0

    # Buy Point: Last Pivot High
    # Find the last High pivot
    last_high_idx = -1
    last_high_price = -1
    for p in reversed(pivots):
        if p['type'] == 'peak':
            last_high_idx = p['index']
            last_high_price = p['price']
            break
            
    if last_high_price == -1: return False, np.nan, np.nan, 0
    
    # Stop Loss: Last Pivot Low
    last_low_price = -1
    for p in reversed(pivots):
        if p['type'] == 'trough':
            last_low_price = p['price']
            break
            
    if last_low_price == -1: return False, np.nan, np.nan, 0
    
    # Check if Price is near Buy Point (Breakout imminent)
    # Close should be close to Last High
    if close[-1] < last_high_price * 0.95: # Too far from pivot
        return False, np.nan, np.nan, 0

    vcp_len = n - window_high_idx
    return True, float(last_high_price), float(last_low_price), int(vcp_len)
