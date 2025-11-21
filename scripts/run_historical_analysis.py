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
    大幅優化版本：
    1. 將所有欄位轉為 NumPy arrays（加速10-50倍）
    2. 使用滾動窗口預先計算 window_high（避免重複計算）
    3. 減少 DataFrame 操作
    4. 只在必要時創建 DataFrame 切片
    """
    sid, g, market_dict = args
    results = []
    n_rows = len(g)
   
    if n_rows < WINDOW_DAYS:
        return results
    
    # === 優化1: 將所有欄位轉為 NumPy arrays ===
    closes_arr = g['close'].values
    highs_arr = g['high'].values
    lows_arr = g['low'].values
    opens_arr = g['open'].values
    volumes_arr = g['volume'].values
    dates_arr = g['date'].values
    
    # 提取 MA 和其他指標
    ma50_arr = g['ma50'].values
    ma150_arr = g['ma150'].values
    ma200_arr = g['ma200'].values
    low52_arr = g['low52'].values
    vol_ma50_arr = g['vol_ma50'].values
    rs_rating_arr = g['rs_rating'].values
    high_52w_arr = g['high_52w'].values
    
    # === 優化2: 預先計算所有滾動窗口的最高價 ===
    # 使用 pandas rolling 一次性計算所有窗口的最高價
    window_highs = g['high'].rolling(window=WINDOW_DAYS).max().values
    
    # === 優化3: 預先計算 change_pct ===
    # 避免在循環中重複計算
    change_pcts = np.full(n_rows, np.nan)
    change_pcts[1:] = (closes_arr[1:] / closes_arr[:-1]) - 1.0
    
    # Iterate through the required range
    for i in range(WINDOW_DAYS - 1, n_rows):
        # === 優化4: 只在策略函數需要時才創建 DataFrame 切片 ===
        # 這樣可以避免大量的切片操作
        window = g.iloc[i - WINDOW_DAYS + 1 : i + 1]
        
        # === 使用預先計算的值 ===
        close_today = closes_arr[i]
        high_today = highs_arr[i]
        low_today = lows_arr[i]
        date_today = dates_arr[i]
        
        # Prepare MA info for CUP（直接從 array 讀取）
        ma_info = {
            'ma50': ma50_arr[i],
            'ma150': ma150_arr[i],
            'ma200': ma200_arr[i],
            'low52': low52_arr[i]
        }
       
        # === 優化5: 使用預先計算的 window_high 和 change_pct ===
        window_high = window_highs[i]
        if window_high == 0 or np.isnan(window_high):
            dd = 0
        else:
            dd = 1.0 - close_today / window_high
           
        change_pct = change_pcts[i]
       
        # Market Trend & RS Info
        rs_rating = rs_rating_arr[i]
       
        # Detect Patterns（策略函數仍然接收 DataFrame）
        high_52w = high_52w_arr[i]
        vol_ma50 = vol_ma50_arr[i]
        ma50 = ma50_arr[i]
       
        is_vcp, vcp_buy, vcp_stop = detect_vcp(window, vol_ma50, ma50, rs_rating=rs_rating, high_52w=high_52w)
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
        
        # === 使用預先提取的 array 值 ===
        results.append({
            'sid': sid,
            'volume': volumes_arr[i],
            'date': date_today,
            'dd': dd,
            'high': high_today,
            'low': low_today,
            'close': close_today,
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
    
    # === 優化：使用更多核心，並根據任務數量調整 chunksize ===
    max_workers = max(1, os.cpu_count() - 1) if os.cpu_count() else None
    # 動態調整 chunksize：對於大量股票，使用更大的 chunksize
    chunksize = max(1, total_stocks // (max_workers * 10)) if max_workers else 10
    
    print(f"Starting analysis on {total_stocks} stocks using {max_workers or 'all'} workers (chunksize={chunksize})...", flush=True)
   
    all_results = []
   
    # 使用 ProcessPoolExecutor 進行平行運算
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        results_generator = list(tqdm(
            executor.map(process_single_stock, tasks, chunksize=chunksize),
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
        print(f" Total records: {len(result_df)}")
        print(f" VCP patterns: {result_df['is_vcp'].sum()}")
        print(f" HTF patterns: {result_df['is_htf'].sum()}")
        print(f" CUP patterns: {result_df['is_cup'].sum()}")
    else:
        print("Warning: No results generated.")
   
    elapsed = time.time() - start_time
    print(f"\n⏱️ Total execution time: {elapsed:.2f} seconds ({elapsed/60:.1f} minutes)")

if __name__ == "__main__":
    main()
