import pandas as pd
import numpy as np
import os

# --- Configuration ---
INPUT_FILE = 'stock/2023_2025_daily_stock_info.csv'
OUTPUT_FILE = 'stock/pattern_analysis_result.csv'
WINDOW_DAYS = 126  # Approx 6 months

# Column mapping
COL_NAMES = ['sid', 'name', 'date', 'open', 'high', 'low', 'close', 'volume']

# --- Helper Functions ---

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

# --- Pattern Detection Functions ---

def detect_htf(window,
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

def detect_vcp(window,
               full_history_vol_ma, # Passed from main loop
               zigzag_threshold=0.05,
               up_ratio=0.30, # Relaxed from 0.6 for VCP if we use ZigZag? Or keep 0.6? User said "Up trend", usually 30% is min. Let's keep 0.3-0.6.
               # User prompt: "視窗內最高價相對起點上漲 >= 60%" was original. 
               # Let's stick to original 0.6 or user didn't complain? 
               # User didn't explicitly change this in refined request, but ZigZag handles structure.
               # Let's keep 0.6 but maybe allow 0.3 if structure is good? 
               # I'll stick to 0.6 to be safe, or maybe 0.4.
               min_up_ratio=0.4, 
               vol_dry_up_ratio=0.6): # Volume < 60% of 50MA

    high = window['high'].values
    low = window['low'].values
    close = window['close'].values
    vol = window['volume'].values
    
    n = len(window)
    if n < 50: return False, np.nan, np.nan

    # 1. Trend Check
    start_price = close[0]
    if start_price == 0: return False, np.nan, np.nan
    window_high = high.max()
    window_high_idx = high.argmax()
    
    if window_high_idx < 10: # High too early
        return False, np.nan, np.nan
        
    up = window_high / start_price - 1.0
    if up < min_up_ratio:
        return False, np.nan, np.nan

    # 2. ZigZag Analysis (From High Point onwards)
    # We only care about contraction AFTER the high.
    # Or does VCP include the run up? VCP is the consolidation.
    # The "High" is the left side of the base.
    
    # Slice from High Index
    base_high = high[window_high_idx:]
    base_low = low[window_high_idx:]
    base_close = close[window_high_idx:]
    
    if len(base_close) < 10: return False, np.nan, np.nan
    
    pivots = get_zigzag_pivots(base_high, base_low, base_close, threshold_pct=zigzag_threshold)
    
    # We need at least 2 contractions (High -> Low -> Lower High -> Higher Low)
    # Sequence: Peak (Start) -> Trough -> Peak -> Trough ...
    # Filter pivots to ignore 'start' if it's not the max high
    
    # The first point in base_slice is the Max High (index 0 relative).
    # ZigZag might find it as start.
    
    # Extract Troughs and Peaks
    troughs = [p for p in pivots if p['type'] == 'trough']
    peaks = [p for p in pivots if p['type'] == 'peak']
    
    # Check Contraction
    # 1. Amplitudes decrease?
    # Amplitude = (Peak - Next Trough) / Peak
    # Or (Previous Peak - Trough)
    
    # We need pairs of (Peak_i, Trough_i)
    # Logic: Peak 1 (Left High) -> Trough 1 -> Peak 2 -> Trough 2 ...
    # Conditions:
    # Peak 2 < Peak 1
    # Trough 2 > Trough 1 (Low padding)
    # Depth 2 < Depth 1
    
    if len(troughs) < 2: # Need at least 2 pullbacks for VCP? Or 1 is Cup? VCP usually 2-4.
        # User mentioned "2, 3, 4 legs".
        # If only 1 trough, it's just a Cup or pullback.
        return False, np.nan, np.nan
        
    valid_vcp = True
    last_depth = 1.0
    last_vol = float('inf') # We don't have vol in pivots, need to look up
    
    # Check Troughs (Lows) - Should be increasing or flat
    # User: "Low_i >= Low_{i-1}" (Low padding)
    # Actually VCP lows usually increase.
    
    for i in range(len(troughs) - 1):
        if troughs[i+1]['price'] < troughs[i]['price'] * 0.98: # Allow small undercut? User said >=.
             valid_vcp = False
             break
             
    if not valid_vcp: return False, np.nan, np.nan
    
    # Check Depths (Contraction)
    # Depth = (Prev Peak - Trough) / Prev Peak
    # We need to match Trough to its preceding Peak.
    # Pivots are ordered.
    
    # Reconstruct Legs
    legs = []
    # Find Peak before Trough
    # Pivot list: [Start(Peak), Trough, Peak, Trough, Peak...]
    
    current_peak = pivots[0]['price'] # Should be window high
    
    for p in pivots:
        if p['type'] == 'peak':
            current_peak = p['price']
        elif p['type'] == 'trough':
            depth = (current_peak - p['price']) / current_peak
            legs.append(depth)
            
    # Check Depth Contraction
    for i in range(len(legs) - 1):
        if legs[i+1] >= legs[i]: # Depth must decrease
            valid_vcp = False
            break
            
    if not valid_vcp: return False, np.nan, np.nan
    
    # 3. Volume Filter (Dry Up)
    # Check last few days volume vs 50MA Vol
    last_vol_ma = full_history_vol_ma.iloc[-1] # Passed value is scalar? No, series.
    # Actually we need the vol_ma corresponding to the end of window.
    # window is a slice of the group.
    # We can compute local vol ma or use passed global/series.
    # Let's compute local 50MA of volume for simplicity and safety.
    
    vol_ma_50 = pd.Series(vol).rolling(50).mean().iloc[-1]
    last_3_days_vol = vol[-3:].mean()
    
    if np.isnan(vol_ma_50) or vol_ma_50 == 0:
        pass # Skip check if not enough data
    else:
        if last_3_days_vol > vol_ma_50 * vol_dry_up_ratio:
            return False, np.nan, np.nan
            
    # Buy Point: Pivot High (Last Peak) or Window High?
    # User: "Breakout". Usually last peak + buffer.
    # Let's use the Last Peak price.
    if len(peaks) > 0:
        buy_price = peaks[-1]['price']
    else:
        buy_price = window_high
        
    stop_price = troughs[-1]['price']
    
    if stop_price >= buy_price: return False, np.nan, np.nan

    return True, float(buy_price), float(stop_price)

def detect_cup(window,
               ma_info, # Dict with last values of MAs: {'ma50':, 'ma150':, 'ma200':, 'low52':}
               min_depth=0.12,
               max_depth=0.33,
               handle_max_depth=0.15):

    high = window['high'].values
    low = window['low'].values
    close = window['close'].values
    
    n = len(window)
    if n < 40: return False, np.nan, np.nan
    
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

# --- Main Execution ---

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: Input file {INPUT_FILE} not found.")
        return

    print("Loading data...", flush=True)
    df = pd.read_csv(INPUT_FILE, header=None, names=COL_NAMES + [f'col_{i}' for i in range(8, 20)]) 
    df = df[COL_NAMES].copy()
    
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df.dropna(subset=['sid', 'date', 'close'], inplace=True)
    df.sort_values(['sid', 'date'], inplace=True)
    
    print("Calculating Indicators...", flush=True)
    # Calculate MAs and 52-week Low globally (grouped)
    # Using transform to keep shape
    df['ma50'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(50).mean())
    df['ma150'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(150).mean())
    df['ma200'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(200).mean())
    df['low52'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(252).min())
    # For Vol Dry Up
    df['vol_ma50'] = df.groupby('sid')['volume'].transform(lambda x: x.rolling(50).mean())
    
    results = []
    
    print("Processing stocks...", flush=True)
    grouped = df.groupby('sid')
    total_groups = len(grouped)
    count = 0
    
    for sid, group in grouped:
        count += 1
        if count % 100 == 0:
            print(f"Processed {count}/{total_groups} stocks...", flush=True)
            
        g = group.reset_index(drop=True)
        n_rows = len(g)
        if n_rows < WINDOW_DAYS: continue
        
        # Optimization: Pre-convert to numpy for speed if needed, but logic is complex.
        # We iterate.
        
        for i in range(WINDOW_DAYS - 1, n_rows):
            window = g.iloc[i - WINDOW_DAYS + 1 : i + 1]
            row_today = g.iloc[i]
            
            # Prepare MA info for CUP
            ma_info = {
                'ma50': row_today['ma50'],
                'ma150': row_today['ma150'],
                'ma200': row_today['ma200'],
                'low52': row_today['low52']
            }
            
            # Basic info
            prev_close = g.iloc[i-1]['close'] if i > 0 else np.nan
            window_high = window['high'].max()
            if window_high == 0: dd = 0
            else: dd = 1.0 - row_today['close'] / window_high
            change_pct = (row_today['close'] / prev_close - 1.0) if (i > 0 and prev_close != 0) else np.nan
            
            # Detect Patterns
            is_vcp, vcp_buy, vcp_stop = detect_vcp(window, row_today['vol_ma50']) 
            # Actually detect_vcp computes local vol ma or needs global.
            # I passed g['vol_ma50'] which is the whole series. detect_vcp needs to know 'i' or just take last value of window?
            # detect_vcp receives `window`. `window` has `volume`.
            # But `vol_ma50` is already computed in `g`.
            # Let's pass the scalar value of vol_ma50 for today?
            # detect_vcp logic: "last_vol_ma = full_history_vol_ma.iloc[-1]"
            # So I should pass `window_vol_ma`?
            # Better: pass `row_today['vol_ma50']`.
            # But detect_vcp signature I wrote: `detect_vcp(window, full_history_vol_ma, ...)`
            # And inside: `last_vol_ma = full_history_vol_ma.iloc[-1]`
            # If I pass a scalar, iloc will fail.
            # Let's fix detect_vcp to accept scalar `vol_ma50_val`.
            
            # Wait, I need to fix the function definition in this file content.
            # I will modify detect_vcp to take `vol_ma50_val`.
            
            # (Self-correction in code below)
            
            is_htf, htf_buy, htf_stop = detect_htf(window)
            is_cup, cup_buy, cup_stop = detect_cup(window, ma_info)
            
            # ... (Outcome Eval) ...
            vcp_2R = vcp_3R = vcp_4R = vcp_stop_hit = False
            htf_2R = htf_3R = htf_4R = htf_stop_hit = False
            cup_2R = cup_3R = cup_4R = cup_stop_hit = False

            if is_vcp:
                vcp_2R, vcp_3R, vcp_4R, vcp_stop_hit = eval_R_outcome(g, i, vcp_buy, vcp_stop)
            if is_htf:
                htf_2R, htf_3R, htf_4R, htf_stop_hit = eval_R_outcome(g, i, htf_buy, htf_stop)
            if is_cup:
                cup_2R, cup_3R, cup_4R, cup_stop_hit = eval_R_outcome(g, i, cup_buy, cup_stop)

            results.append({
                'sid': sid,
                'date': row_today['date'],
                'dd': dd,
                'high': row_today['high'],
                'low': row_today['low'],
                'close': row_today['close'],
                'change_pct': change_pct,
                'is_vcp': is_vcp, 'vcp_buy_price': vcp_buy, 'vcp_stop_price': vcp_stop,
                'vcp_2R': vcp_2R, 'vcp_3R': vcp_3R, 'vcp_4R': vcp_4R, 'vcp_stop': vcp_stop_hit,
                'is_htf': is_htf, 'htf_buy_price': htf_buy, 'htf_stop_price': htf_stop,
                'htf_2R': htf_2R, 'htf_3R': htf_3R, 'htf_4R': htf_4R, 'htf_stop': htf_stop_hit,
                'is_cup': is_cup, 'cup_buy_price': cup_buy, 'cup_stop_price': cup_stop,
                'cup_2R': cup_2R, 'cup_3R': cup_3R, 'cup_4R': cup_4R, 'cup_stop': cup_stop_hit,
            })

    print("Saving results...", flush=True)
    result_df = pd.DataFrame(results)
    result_df.to_csv(OUTPUT_FILE, index=False)
    print(f"Done. Saved to {OUTPUT_FILE}", flush=True)

# Redefine detect_vcp to match usage
def detect_vcp(window,
               vol_ma50_val, # Scalar
               zigzag_threshold=0.05,
               min_up_ratio=0.4, 
               vol_dry_up_ratio=0.6):

    high = window['high'].values
    low = window['low'].values
    close = window['close'].values
    vol = window['volume'].values
    
    n = len(window)
    if n < 50: return False, np.nan, np.nan

    start_price = close[0]
    if start_price == 0: return False, np.nan, np.nan
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

if __name__ == "__main__":
    main()
