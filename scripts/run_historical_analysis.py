import sys
import os
import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm
import time

# 添加 src 到路徑
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.strategies.cup import detect_cup
from src.strategies.htf import detect_htf
from src.strategies.vcp import detect_vcp
from src.strategies import eval_R_outcome
from src.utils.data_loader import loader

# --- Configuration ---
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), '../data/processed/pattern_analysis_result.csv')
MARKET_FILE = os.path.join(os.path.dirname(__file__), '../data/raw/market_data.csv')
WINDOW_DAYS = 126
COL_NAMES = ['sid', 'name', 'date', 'open', 'high', 'low', 'close', 'volume']

# --- Global Helper Functions ---

def load_market_data_as_dict():
    """
    Load market data and convert to dict for O(1) lookup speed.
    Returns: { 'YYYY-MM-DD': {'close': val, 'market_ma200': val, ...} }
    """
    if not os.path.exists(MARKET_FILE):
        return None
    df = pd.read_csv(MARKET_FILE)
    df = df.set_index('date')
    return df.to_dict(orient='index')

def load_data():
    print("Loading data...", flush=True)
    df = loader.load_data()
    if df.empty:
        print("No data loaded.")
        return None
        
    numeric_cols = ['open', 'high', 'low', 'close', 'volume']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    df['date'] = pd.to_datetime(df['date'])
    return df

def process_single_stock(args):
    """
    保守優化版: 只優化明確安全的部分
    - 使用 NumPy arrays 進行讀取（不改變計算邏輯）
    - 增加 chunksize
    - 其他邏輯完全保持不變
    """
    sid, g, market_dict = args
    results = []
    n_rows = len(g)
    
    if n_rows < WINDOW_DAYS:
        return results

    # === 僅此優化：將欄位轉為 NumPy arrays 以加速「讀取」（不改變計算） ===
    # 注意：我們仍然保留 DataFrame g 給策略函數使用
    closes_arr = g['close'].values
    highs_arr = g['high'].values
    lows_arr = g['low'].values
    dates_arr = g['date'].values
    
    # Iterate through the required range
    for i in range(WINDOW_DAYS - 1, n_rows):
        # === 保持原始邏輯：仍然切片 DataFrame ===
        window = g.iloc[i - WINDOW_DAYS + 1 : i + 1]
        row_today = g.iloc[i]  # 仍然使用 iloc，確保邏輯完全一致
        
        # Prepare MA info for CUP
        ma_info = {
            'ma50': row_today['ma50'],
            'ma150': row_today['ma150'],
            'ma200': row_today['ma200'],
            'low52': row_today['low52']
        }
        
        # Basic info
        prev_close = g.iloc[i-1]['close'] 
        
        # === 保持原始邏輯：window['high'].max() ===
        window_high = window['high'].max()
        if window_high == 0: 
            dd = 0
        else: 
            dd = 1.0 - row_today['close'] / window_high
            
        change_pct = (row_today['close'] / prev_close - 1.0) if prev_close != 0 else np.nan
        
        # Market Trend & RS Info
        rs_rating = row_today['rs_rating']
        
        if market_dict is not None:
            date_str = row_today['date']
            m_row = market_dict.get(date_str)
        
        # Detect Patterns
        high_52w = row_today['high_52w']
        
        is_vcp, vcp_buy, vcp_stop = detect_vcp(window, row_today['vol_ma50'], row_today['ma50'], rs_rating=rs_rating, high_52w=high_52w) 
        is_htf, htf_buy, htf_stop, htf_grade = detect_htf(window, rs_rating=rs_rating) 
        is_cup, cup_buy, cup_stop = detect_cup(window, ma_info, rs_rating=rs_rating)
        
        # Outcome Eval
        vcp_2R = vcp_3R = vcp_4R = vcp_stop_hit = False
        htf_2R = htf_3R = htf_4R = htf_stop_hit = False
        cup_2R = cup_3R = cup_4R = cup_stop_hit = False

        if is_vcp:
            vcp_2R, vcp_3R, vcp_4R, vcp_stop_hit = eval_R_outcome(g, i, vcp_buy, vcp_stop)
        if is_htf:
            htf_2R, htf_3R, htf_4R, htf_stop_hit = eval_R_outcome(g, i, htf_buy, htf_stop)
        if is_cup:
            cup_2R, cup_3R, cup_4R, cup_stop_hit = eval_R_outcome(g, i, cup_buy, cup_stop)

        # === 僅此優化：使用 array 讀取以加速（值完全相同） ===
        results.append({
            'sid': sid,
            'date': dates_arr[i],  # 使用 array（值相同）
            'dd': dd,
            'high': highs_arr[i],  # 使用 array（值相同）
            'low': lows_arr[i],    # 使用 array（值相同）
            'close': closes_arr[i], # 使用 array（值相同）
            'change_pct': change_pct,
            'is_vcp': is_vcp, 'vcp_buy_price': vcp_buy, 'vcp_stop_price': vcp_stop,
            'vcp_2R': vcp_2R, 'vcp_3R': vcp_3R, 'vcp_4R': vcp_4R, 'vcp_stop': vcp_stop_hit,
            'is_htf': is_htf, 'htf_buy_price': htf_buy, 'htf_stop_price': htf_stop, 'htf_grade': htf_grade,
            'htf_2R': htf_2R, 'htf_3R': htf_3R, 'htf_4R': htf_4R, 'htf_stop': htf_stop_hit,
            'is_cup': is_cup, 'cup_buy_price': cup_buy, 'cup_stop_price': cup_stop,
            'cup_2R': cup_2R, 'cup_3R': cup_3R, 'cup_4R': cup_4R, 'cup_stop': cup_stop_hit,
        })
        
    return results

def main():
    start_time = time.time()
    
    # 1. Load Data
    market_dict = load_market_data_as_dict()
    if market_dict is None:
        print("Warning: Market data not found.")
    else:
        print(f"Market data loaded ({len(market_dict)} dates).")

    df = load_data()
    if df is None:
        return
        
    df = df[COL_NAMES].copy()
    
    # 2. Pre-calculation (Vectorized - Fast)
    print("Calculating RS Ratings and Indicators...", flush=True)
    df['close'] = pd.to_numeric(df['close'], errors='coerce')
    df['date'] = pd.to_datetime(df['date'])
    df.sort_values(['sid', 'date'], inplace=True)
    
    # 52-week Return & Rank
    df['return_52w'] = df.groupby('sid')['close'].pct_change(periods=252)
    df['rs_rating'] = df.groupby('date')['return_52w'].transform(
        lambda x: x.rank(pct=True) * 100
    )
    
    # 52-week High
    df['high_52w'] = df.groupby('sid')['high'].transform(
        lambda x: x.rolling(window=252, min_periods=1).max()
    )
    
    # Convert date back to string
    df['date'] = df['date'].dt.strftime('%Y-%m-%d')

    # Numeric conversion
    for col in ['open', 'high', 'low', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df.dropna(subset=['sid', 'date', 'close'], inplace=True)
    
    # Indicators
    print("Calculating moving averages...", flush=True)
    df['ma50'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(50).mean())
    df['ma150'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(150).mean())
    df['ma200'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(200).mean())
    df['low52'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(252).min())
    df['vol_ma50'] = df.groupby('sid')['volume'].transform(lambda x: x.rolling(50).mean())

    # 3. Prepare for Parallel Processing
    print("Preparing tasks for parallel processing...", flush=True)
    
    tasks = []
    for sid, group in df.groupby('sid'):
        tasks.append((sid, group.reset_index(drop=True), market_dict))

    total_stocks = len(tasks)
    # === 優化：使用更多核心 ===
    max_workers = max(1, os.cpu_count() - 1) if os.cpu_count() else None
    print(f"Starting analysis on {total_stocks} stocks using {max_workers or 'all'} workers...", flush=True)
    
    all_results = []
    
    # 使用 ProcessPoolExecutor 進行平行運算
    # === 優化：增加 chunksize 減少進程間通訊開銷 ===
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        results_generator = list(tqdm(
            executor.map(process_single_stock, tasks, chunksize=10), 
            total=total_stocks, 
            unit="stock",
            desc="Processing",
            ncols=100
        ))
        
        for res in results_generator:
            all_results.extend(res)

    # 4. Save Results
    print(f"\nSaving {len(all_results)} results...", flush=True)
    
    if all_results:
        result_df = pd.DataFrame(all_results)
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        result_df.to_csv(OUTPUT_FILE, index=False)
        print(f"Done. Saved to {OUTPUT_FILE}", flush=True)
        
        # 統計資訊
        print(f"\nSummary:")
        print(f"  Total records: {len(result_df)}")
        print(f"  VCP patterns: {result_df['is_vcp'].sum()}")
        print(f"  HTF patterns: {result_df['is_htf'].sum()}")
        print(f"  CUP patterns: {result_df['is_cup'].sum()}")
    else:
        print("Warning: No results generated.")
    
    elapsed = time.time() - start_time
    print(f"\n⏱️  Total execution time: {elapsed:.2f} seconds ({elapsed/60:.1f} minutes)")

if __name__ == "__main__":
    main()