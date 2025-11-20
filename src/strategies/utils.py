import numpy as np
import pandas as pd

def get_zigzag_pivots(high, low, close, threshold_pct=0.05):
    """
    Identify ZigZag pivots (Highs and Lows).
    Returns a list of dicts: {'index': i, 'price': p, 'type': 'peak'|'trough'}
    """
    pivots = []
    # Initial state
    trend = 0 # 1 for Up, -1 for Down
    last_pivot_price = close[0]
    last_pivot_idx = 0
    
    # We need to find the first move to establish trend
    # Simple approach: Start from index 0.
    pivots.append({'index': 0, 'price': close[0], 'type': 'start'})
    
    for i in range(1, len(close)):
        curr_high = high[i]
        curr_low = low[i]
        
        if trend == 0:
            if curr_high > last_pivot_price * (1 + threshold_pct):
                trend = 1
                last_pivot_idx = i
                last_pivot_price = curr_high
            elif curr_low < last_pivot_price * (1 - threshold_pct):
                trend = -1
                last_pivot_idx = i
                last_pivot_price = curr_low
        elif trend == 1: # Up trend, looking for higher high or reversal
            if curr_high > last_pivot_price:
                last_pivot_idx = i
                last_pivot_price = curr_high
            elif curr_low < last_pivot_price * (1 - threshold_pct):
                # Reversal found. The previous high was a peak.
                pivots.append({'index': last_pivot_idx, 'price': last_pivot_price, 'type': 'peak'})
                trend = -1
                last_pivot_idx = i
                last_pivot_price = curr_low
        elif trend == -1: # Down trend, looking for lower low or reversal
            if curr_low < last_pivot_price:
                last_pivot_idx = i
                last_pivot_price = curr_low
            elif curr_high > last_pivot_price * (1 + threshold_pct):
                # Reversal found. The previous low was a trough.
                pivots.append({'index': last_pivot_idx, 'price': last_pivot_price, 'type': 'trough'})
                trend = 1
                last_pivot_idx = i
                last_pivot_price = curr_high
                
    # Add the last point as tentative
    pivots.append({'index': last_pivot_idx, 'price': last_pivot_price, 'type': 'peak' if trend == 1 else 'trough'})
    
    return pivots

def eval_R_outcome(stock_df, i, buy_price, stop_price, lookahead=30):
    n = len(stock_df)
    if i >= n - 1 or np.isnan(buy_price) or np.isnan(stop_price):
        return False, False, False, False

    risk = buy_price - stop_price
    if risk <= 0: return False, False, False, False

    j_end = min(n, i + 1 + lookahead)
    future = stock_df.iloc[i+1 : j_end]
    if future.empty: return False, False, False, False

    f_high = future['high'].values
    hit_indices = np.where(f_high >= buy_price)[0]
    
    if len(hit_indices) == 0:
        return False, False, False, False
        
    first_hit_rel_idx = hit_indices[0]
    entry_abs_idx = (i + 1) + first_hit_rel_idx
    
    future_after_entry = stock_df.iloc[entry_abs_idx : j_end]
    if future_after_entry.empty:
         return False, False, False, False

    max_high = future_after_entry['high'].max()
    min_low  = future_after_entry['low'].min()

    max_R = (max_high - buy_price) / risk
    min_R = (min_low  - buy_price) / risk

    hit_2R = hit_3R = hit_4R = hit_stop = False

    if max_R >= 4: hit_4R = True
    elif max_R >= 3: hit_3R = True
    elif max_R >= 2: hit_2R = True
    elif min_R <= -1: hit_stop = True

    return hit_2R, hit_3R, hit_4R, hit_stop
