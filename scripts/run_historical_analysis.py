import sys
import os
import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from tqdm import tqdm  # 需要安裝: pip install tqdm
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
    # Ensure valid index
    df = df.set_index('date')
    # Convert to dictionary: {date: {col: value}}
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
    Worker function to process a single stock group.
    args: (sid, group_df, market_data_dict)
    """
    sid, g, market_dict = args
    results = []
    n_rows = len(g)
    
    # 如果資料長度不足，直接返回空列表
    if n_rows < WINDOW_DAYS:
        return results

    # 為了加速，將常用的 column 轉為 numpy array 或直接提取 series
    # 但因為策略函數 (detect_cup 等) 可能依賴 DataFrame 結構，
    # 我們保留 window 為 DataFrame，但在迴圈外的 lookup 做優化。
    
    # Iterate through the required range
    for i in range(WINDOW_DAYS - 1, n_rows):
        # Slice window (This is the heavy part, but required by strategy logic)
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
        # i > 0 is guaranteed by loop range (WINDOW_DAYS >= 126)
        prev_close = g.iloc[i-1]['close'] 
        
        window_high = window['high'].max()
        if window_high == 0: 
            dd = 0
        else: 
            dd = 1.0 - row_today['close'] / window_high
            
        change_pct = (row_today['close'] / prev_close - 1.0) if prev_close != 0 else np.nan
        
        # Market Trend & RS Info
        rs_rating = row_today['rs_rating'] # Pre-calculated
        
        # 這裡不使用 rs_rating 進行 market trend 判斷，只保留原邏輯
        if market_dict is not None:
            date_str = row_today['date']
            # Dict lookup is O(1), much faster than df.loc
            m_row = market_dict.get(date_str)
            # 原程式碼中雖然提取了 m_row，但在 detect_vcp 傳入參數時並沒有用到 m_row 的內容
            # 僅傳入了 rs_rating。若策略內部有用到 market_trend，請確認策略函數定義。
            # 根據您提供的代碼，detect_vcp 只吃了 high_52w 和 rs_rating。
        
        # Detect Patterns
        high_52w = row_today['high_52w']
        
        # 呼叫策略
        is_vcp, vcp_buy, vcp_stop = detect_vcp(window, row_today['vol_ma50'], row_today['ma50'], rs_rating=rs_rating, high_52w=high_52w) 
        is_htf, htf_buy, htf_stop, htf_grade = detect_htf(window, rs_rating=rs_rating) 
        is_cup, cup_buy, cup_stop = detect_cup(window, ma_info, rs_rating=rs_rating)
        
        # Outcome Eval
        vcp_2R = vcp_3R = vcp_4R = vcp_stop_hit = False
        htf_2R = htf_3R = htf_4R = htf_stop_hit = False
        cup_2R = cup_3R = cup_4R = cup_stop_hit = False

        # eval_R_outcome 內部可能會有迴圈，傳入 g 和 current index i
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
            'is_htf': is_htf, 'htf_buy_price': htf_buy, 'htf_stop_price': htf_stop, 'htf_grade': htf_grade,
            'htf_2R': htf_2R, 'htf_3R': htf_3R, 'htf_4R': htf_4R, 'htf_stop': htf_stop_hit,
            'is_cup': is_cup, 'cup_buy_price': cup_buy, 'cup_stop_price': cup_stop,
            'cup_2R': cup_2R, 'cup_3R': cup_3R, 'cup_4R': cup_4R, 'cup_stop': cup_stop_hit,
        })
        
    return results

def main():
    # 1. Load Data
    market_dict = load_market_data_as_dict()
    if market_dict is None:
        print("Warning: Market data not found.")
    else:
        print("Market data loaded (Optimized into Dict).")

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
    grouped_iterator = df.groupby('sid')
    
    # 為了確保 transform 正確，我們先計算指標再拆分
    # 其實直接在這裡全域計算比在 loop 裡安全且快
    df['ma50'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(50).mean())
    df['ma150'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(150).mean())
    df['ma200'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(200).mean())
    df['low52'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(252).min())
    df['vol_ma50'] = df.groupby('sid')['volume'].transform(lambda x: x.rolling(50).mean())

    # 3. Prepare for Parallel Processing
    print("Preparing tasks for parallel processing...", flush=True)
    
    # 將 DataFrame 依照 sid 拆分成小塊 (Group)
    # list of (sid, group_df)
    # reset_index(drop=True) is important for logic relying on integer indexing (0 to N)
    tasks = []
    for sid, group in df.groupby('sid'):
        tasks.append((sid, group.reset_index(drop=True), market_dict))

    total_stocks = len(tasks)
    print(f"Starting analysis on {total_stocks} stocks using Multiprocessing...", flush=True)
    
    all_results = []
    
    # 使用 ProcessPoolExecutor 進行平行運算
    # max_workers 預設為 CPU 核心數，這通常是最佳設定
    with ProcessPoolExecutor() as executor:
        # 使用 tqdm 包裹 executor.map 以顯示進度條
        results_generator = list(tqdm(
            executor.map(process_single_stock, tasks), 
            total=total_stocks, 
            unit="stock",
            desc="Processing"
        ))
        
        # 合併結果
        for res in results_generator:
            all_results.extend(res)

    # 4. Save Results
    print("Saving results...", flush=True)
    result_df = pd.DataFrame(all_results)
    result_df.to_csv(OUTPUT_FILE, index=False)
    print(f"Done. Saved to {OUTPUT_FILE}", flush=True)

if __name__ == "__main__":
    # Windows 下使用 Multiprocessing 必須在 if __name__ == "__main__": 之下執行
    main()