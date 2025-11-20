import pandas as pd
import numpy as np
import os
from strategies import detect_htf, detect_vcp, detect_cup, eval_R_outcome

# --- Configuration ---
INPUT_FILE = './2023_2025_daily_stock_info.csv'
OUTPUT_FILE = './pattern_analysis_result.csv'
MARKET_FILE = './market_data.csv'
WINDOW_DAYS = 126  # Approx 6 months

# Column mapping
COL_NAMES = ['sid', 'name', 'date', 'open', 'high', 'low', 'close', 'volume']

def load_market_data():
    if not os.path.exists(MARKET_FILE):
        return None
    df = pd.read_csv(MARKET_FILE)
    # Ensure date is string YYYY-MM-DD
    return df.set_index('date')

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: Input file {INPUT_FILE} not found.")
        return

    market_df = load_market_data()
    if market_df is None:
        print("Warning: Market data not found. Proceeding without market filter.")
    else:
        print("Market data loaded.")

    print("Loading data...", flush=True)
    df = pd.read_csv(INPUT_FILE, header=None, names=COL_NAMES + [f'col_{i}' for i in range(8, 20)]) 
    df = df[COL_NAMES].copy()
    
    # Pre-calculate 52-week RS Rating
    # 1. Calculate 52-week return for each stock
    # 2. Group by date and calculate percentile rank
    print("Calculating RS Ratings...", flush=True)
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df['date'] = pd.to_datetime(df['date'])
    df.sort_values(['sid', 'date'], inplace=True)
    
    # 252 trading days approx 52 weeks
    df['return_52w'] = df.groupby('sid')['close'].pct_change(periods=252)
    
    # Calculate Percentile Rank per Date
    # We need to handle NaN values (first 252 days will be NaN)
    # Use transform to keep original index
    df['rs_rating'] = df.groupby('date')['return_52w'].transform(
        lambda x: x.rank(pct=True) * 100
    )
    
    # Pre-calculate 52-week High
    df['high_52w'] = df.groupby('sid')['high'].transform(
        lambda x: x.rolling(window=252, min_periods=1).max()
    )
    
    # Convert date back to string for compatibility
    df['date'] = df['date'].dt.strftime('%Y-%m-%d')

    print("Calculating Indicators...", flush=True)
    for col in ['open', 'high', 'low', 'volume']: # 'close' is already converted
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df.dropna(subset=['sid', 'date', 'close'], inplace=True)
    df.sort_values(['sid', 'date'], inplace=True)
    
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
            
            # Market Trend & RS Info
            market_trend = None
            rs_rating = 0.0 # Default
            
            if market_df is not None:
                date_str = row_today['date']
                if date_str in market_df.index:
                    m_row = market_df.loc[date_str]
                    
                    # 1. Market Trend
                    market_trend = {
                        'close': m_row['close'],
                        'ma200': m_row['market_ma200'],
                        'is_uptrend': m_row['close'] > m_row['market_ma200']
                    }
                    
                    # 2. Relative Strength (RS)
                    # Use pre-calculated rs_rating
                    rs_rating = row_today['rs_rating']
                    
            # Detect Patterns
            # Pass rs_rating and high_52w to VCP
            high_52w = row_today['high_52w']
            is_vcp, vcp_buy, vcp_stop = detect_vcp(window, row_today['vol_ma50'], row_today['ma50'], rs_rating=rs_rating, high_52w=high_52w) 
            is_htf, htf_buy, htf_stop = detect_htf(window, rs_rating=rs_rating) 
            is_cup, cup_buy, cup_stop = detect_cup(window, ma_info, rs_rating=rs_rating)
            
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

if __name__ == "__main__":
    main()
