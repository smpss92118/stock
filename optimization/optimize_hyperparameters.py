"""
超參數網格搜索優化系統 (Polars Accelerated)

對 CUP、HTF、VCP 策略進行參數優化
使用 Polars 進行數據處理，並行計算，並使用 Limited Capital 回測引擎
"""

import sys
import os
import pandas as pd
import numpy as np
from itertools import product
from tqdm import tqdm
import time
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
import polars as pl

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.strategies.optimizable import (
    detect_htf_optimizable,
    detect_cup_optimizable,
    detect_vcp_optimizable
)
from src.strategies import eval_R_outcome
from src.utils.data_loader import loader
from parameter_configs import HTF_PARAM_GRID, CUP_PARAM_GRID, VCP_PARAM_GRID, OUTPUT_CONFIG
from backtest_engine_v2 import run_capital_simulation_limited, calculate_metrics, simulate_exit_fixed

# === Configuration ===
DATA_DIR = os.path.join(os.path.dirname(__file__), '../data')
RESULTS_DIR = os.path.join(os.path.dirname(__file__), 'results')
WINDOW_DAYS = 126

# === Worker Function ===

def load_base_data_polars():
    """
    Load data using Polars and pre-calculate indicators
    """
    print("Loading data with Polars...", flush=True)
    
    df_pd = loader.load_data()
    if df_pd.empty:
        return None
        
    # Ensure types
    numeric_cols = ['open', 'high', 'low', 'close', 'volume']
    for col in numeric_cols:
        df_pd[col] = pd.to_numeric(df_pd[col], errors='coerce')
    
    # Convert to Polars
    df = pl.from_pandas(df_pd)
    
    # Sort
    df = df.sort(["sid", "date"])
    
    print("Calculating indicators (Vectorized)...", flush=True)
    
    # Calculate Indicators using Polars expressions
    df = df.with_columns([
        pl.col("close").pct_change(n=252).over("sid").alias("return_52w"),
        pl.col("high").rolling_max(window_size=252).over("sid").alias("high_52w"),
        pl.col("close").rolling_mean(window_size=50).over("sid").alias("ma50"),
        pl.col("close").rolling_mean(window_size=150).over("sid").alias("ma150"),
        pl.col("close").rolling_mean(window_size=200).over("sid").alias("ma200"),
        pl.col("close").rolling_min(window_size=252).over("sid").alias("low52"),
        pl.col("volume").rolling_mean(window_size=50).over("sid").alias("vol_ma50"),
    ])
    
    # RS Rating (Rank of return_52w per date)
    df = df.with_columns(
        (pl.col("return_52w").rank("ordinal").over("date") / pl.col("return_52w").count().over("date") * 100).alias("rs_rating")
    )
    
    return df

def process_stock_group_wrapper(args):
    """
    Wrapper to unpack args including fixed_params
    """
    stock_df, strategy, combinations, param_keys, fixed_params = args
    
    df_pd = stock_df.to_pandas()
    results_map = {tuple(combo): [] for combo in combinations}
    grouped = df_pd.groupby('sid')
    
    for sid, g in grouped:
        g = g.reset_index(drop=True)
        n_rows = len(g)
        if n_rows < WINDOW_DAYS: continue
        
        # Extract arrays for fast simulation
        high_np = g['high'].values
        low_np = g['low'].values
        close_np = g['close'].values
        # Convert dates to python date objects for the engine
        date_list = [pd.Timestamp(d).date() for d in g['date'].values]
        
        rs_ratings = g['rs_rating'].values
        
        if strategy == 'cup':
            ma50 = g['ma50'].values
            ma150 = g['ma150'].values
            ma200 = g['ma200'].values
            low52 = g['low52'].values
        elif strategy == 'vcp':
            vol_ma50 = g['vol_ma50'].values
            ma50 = g['ma50'].values
            high_52w = g['high_52w'].values
            
        for i in range(WINDOW_DAYS - 1, n_rows):
            window = g.iloc[i - WINDOW_DAYS + 1 : i + 1]
            row_rs = rs_ratings[i]
            
            for combo in combinations:
                params = dict(zip(param_keys, combo))
                params.update(fixed_params)
                
                is_pattern = False
                buy_price = np.nan
                stop_price = np.nan
                
                # Detection
                if strategy == 'htf':
                    is_pattern, buy_price, stop_price, _ = detect_htf_optimizable(
                        window, rs_rating=row_rs, params=params
                    )
                elif strategy == 'cup':
                    ma_info = {'ma50': ma50[i], 'ma150': ma150[i], 'ma200': ma200[i], 'low52': low52[i]}
                    is_pattern, buy_price, stop_price = detect_cup_optimizable(
                        window, ma_info, rs_rating=row_rs, params=params
                    )
                elif strategy == 'vcp':
                    is_pattern, buy_price, stop_price = detect_vcp_optimizable(
                        window, vol_ma50[i], ma50[i], rs_rating=row_rs, high_52w=high_52w[i], params=params
                    )
                
                if is_pattern:
                    # Check Entry (Limit Buy within 30 days)
                    # simulate_exit_fixed expects entry_idx. 
                    # But we first need to trigger ENTRY.
                    # Logic from run_backtest.py:
                    # 1. Find future high >= buy_price
                    
                    future_end = min(i + 31, n_rows)
                    future_high = high_np[i+1 : future_end]
                    
                    if len(future_high) == 0: continue
                    
                    entry_candidates = np.where(future_high >= buy_price)[0]
                    if entry_candidates.size == 0: continue
                    
                    entry_rel = entry_candidates[0]
                    entry_abs = i + 1 + entry_rel
                    
                    # Simulate Exit (Fixed R=2, Time=20 - matching report baseline)
                    # User can change this later, but for optimization we need a standard.
                    # The report showed R=2, T=20 as a good baseline.
                    trade_res = simulate_exit_fixed(
                        high_np, low_np, close_np, date_list,
                        entry_idx=entry_abs,
                        buy_price=buy_price,
                        stop_price=stop_price,
                        r_mult=2.0,
                        time_exit=20
                    )
                    
                    if trade_res:
                        results_map[tuple(combo)].append({
                            'sid': sid,
                            **trade_res
                        })
                    
    return results_map

def optimize_strategy_parallel(df_pl, strategy, param_grid):
    """
    Main optimization driver
    """
    # 1. Generate Combinations
    var_params = {k: v for k, v in param_grid.items() if isinstance(v, list)}
    fixed_params = {k: v for k, v in param_grid.items() if not isinstance(v, list)}
    
    param_keys = list(var_params.keys())
    param_values = list(var_params.values())
    combinations = list(product(*param_values))
    
    full_combinations = []
    for combo in combinations:
        full_combinations.append(combo)
        
    print(f"\n{'='*60}")
    print(f"Optimizing {strategy.upper()} - {len(combinations)} combinations")
    print(f"Parallelizing by Stock Groups...")
    print(f"{'='*60}\n")
    
    # 2. Split Stocks
    sids = df_pl['sid'].unique().to_list()
    n_workers = max(1, os.cpu_count() - 1)
    chunk_size = len(sids) // n_workers + 1
    
    stock_groups = []
    for i in range(0, len(sids), chunk_size):
        chunk_sids = sids[i:i + chunk_size]
        group_df = df_pl.filter(pl.col('sid').is_in(chunk_sids))
        stock_groups.append(group_df)
        
    print(f"Split {len(sids)} stocks into {len(stock_groups)} groups for {n_workers} workers.")
    
    # 3. Run Parallel Workers
    all_results_map = {tuple(c): [] for c in combinations}
    
    with ProcessPoolExecutor(max_workers=n_workers) as executor:
        futures = []
        for group in stock_groups:
            futures.append(executor.submit(process_stock_group_wrapper, (group, strategy, full_combinations, param_keys, fixed_params)))
            
        for future in tqdm(as_completed(futures), total=len(futures), desc="Processing Stock Groups"):
            try:
                group_results = future.result()
                for combo, signals in group_results.items():
                    all_results_map[combo].extend(signals)
            except Exception as e:
                print(f"Worker failed: {e}")
                import traceback
                traceback.print_exc()

    # 4. Run Backtest Simulation
    print("\nRunning Portfolio Simulations...")
    final_metrics = []
    
    for combo in tqdm(combinations, desc="Simulating Portfolios"):
        signals = all_results_map[tuple(combo)]
        
        params = dict(zip(param_keys, combo))
        params.update(fixed_params)
        
        if len(signals) < OUTPUT_CONFIG['min_trades']:
            continue
            
        # Run Limited Capital Simulation (Robust V2)
        trades = run_capital_simulation_limited(signals)
        metrics = calculate_metrics(trades)
        
        if metrics:
            result = {**params, **metrics}
            final_metrics.append(result)
        
    return pd.DataFrame(final_metrics)

# === Summary Generation ===

def generate_summary(results_df, strategy='htf', top_n=3):
    if results_df.empty:
        print(f"⚠️  No valid results for {strategy}")
        return None, None
        
    top_return = results_df.nlargest(top_n, 'ann_return')
    top_sharpe = results_df.nlargest(top_n, 'sharpe')
    return top_return, top_sharpe

# === Main ===

import argparse

def main():
    parser = argparse.ArgumentParser(description='Hyperparameter Optimization')
    parser.add_argument('--strategies', nargs='+', default=['htf', 'cup', 'vcp'],
                        help='Strategies to optimize (htf, cup, vcp)')
    args = parser.parse_args()
    
    start_time = time.time()
    
    # 1. Load Data
    df_pl = load_base_data_polars()
    if df_pl is None: return
    
    # 2. Run selected strategies
    if 'htf' in args.strategies:
        print("\n🎯 Starting HTF Optimization...")
        htf_results = optimize_strategy_parallel(df_pl, 'htf', HTF_PARAM_GRID)
        
        if not htf_results.empty:
            output_file = os.path.join(RESULTS_DIR, 'htf_optimization.csv')
            htf_results.to_csv(output_file, index=False)
            print(f"✅ Saved HTF results to {output_file}")
            
            top_return, top_sharpe = generate_summary(htf_results, 'htf', OUTPUT_CONFIG['top_n_return'])
            
            if top_return is not None:
                print("\n" + "="*80)
                print("HTF - Top 3 by Annualized Return (Limited Capital)")
                print("="*80)
                print(top_return.to_string(index=False))
                
                print("\n" + "="*80)
                print("HTF - Top 3 by Sharpe Ratio (Limited Capital)")
                print("="*80)
                print(top_sharpe.to_string(index=False))
                
                summary_file = os.path.join(RESULTS_DIR, 'htf_best_params.md')
                with open(summary_file, 'w', encoding='utf-8') as f:
                    f.write("# HTF 超參數優化結果\n\n")
                    f.write("## Top 3 by Annualized Return\n\n")
                    f.write(top_return.to_markdown(index=False))
                    f.write("\n\n## Top 3 by Sharpe Ratio\n\n")
                    f.write(top_sharpe.to_markdown(index=False))
                print(f"\n✅ Saved summary to {summary_file}")

    if 'cup' in args.strategies:
        print("\n🎯 Starting CUP Optimization...")
        cup_results = optimize_strategy_parallel(df_pl, 'cup', CUP_PARAM_GRID)
        
        if not cup_results.empty:
            output_file = os.path.join(RESULTS_DIR, 'cup_optimization.csv')
            cup_results.to_csv(output_file, index=False)
            print(f"✅ Saved CUP results to {output_file}")
            
            top_return, top_sharpe = generate_summary(cup_results, 'cup', OUTPUT_CONFIG['top_n_return'])
            
            if top_return is not None:
                print("\n" + "="*80)
                print("CUP - Top 3 by Annualized Return (Limited Capital)")
                print("="*80)
                print(top_return.to_string(index=False))
                
                print("\n" + "="*80)
                print("CUP - Top 3 by Sharpe Ratio (Limited Capital)")
                print("="*80)
                print(top_sharpe.to_string(index=False))
                
                summary_file = os.path.join(RESULTS_DIR, 'cup_best_params.md')
                with open(summary_file, 'w', encoding='utf-8') as f:
                    f.write("# CUP 超參數優化結果\n\n")
                    f.write("## Top 3 by Annualized Return\n\n")
                    f.write(top_return.to_markdown(index=False))
                    f.write("\n\n## Top 3 by Sharpe Ratio\n\n")
                    f.write(top_sharpe.to_markdown(index=False))
                print(f"\n✅ Saved summary to {summary_file}")

    if 'vcp' in args.strategies:
        print("\n🎯 Starting VCP Optimization...")
        vcp_results = optimize_strategy_parallel(df_pl, 'vcp', VCP_PARAM_GRID)
        
        if not vcp_results.empty:
            output_file = os.path.join(RESULTS_DIR, 'vcp_optimization.csv')
            vcp_results.to_csv(output_file, index=False)
            print(f"✅ Saved VCP results to {output_file}")
            
            top_return, top_sharpe = generate_summary(vcp_results, 'vcp', OUTPUT_CONFIG['top_n_return'])
            
            if top_return is not None:
                print("\n" + "="*80)
                print("VCP - Top 3 by Annualized Return (Limited Capital)")
                print("="*80)
                print(top_return.to_string(index=False))
                
                print("\n" + "="*80)
                print("VCP - Top 3 by Sharpe Ratio (Limited Capital)")
                print("="*80)
                print(top_sharpe.to_string(index=False))
                
                summary_file = os.path.join(RESULTS_DIR, 'vcp_best_params.md')
                with open(summary_file, 'w', encoding='utf-8') as f:
                    f.write("# VCP 超參數優化結果\n\n")
                    f.write("## Top 3 by Annualized Return\n\n")
                    f.write(top_return.to_markdown(index=False))
                    f.write("\n\n## Top 3 by Sharpe Ratio\n\n")
                    f.write(top_sharpe.to_markdown(index=False))
                print(f"\n✅ Saved summary to {summary_file}")
            
    elapsed = time.time() - start_time
    print(f"\n⏱️  Total time: {elapsed:.1f} seconds ({elapsed/60:.1f} minutes)")

if __name__ == "__main__":
    main()
