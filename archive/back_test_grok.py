import polars as pl
import numpy as np
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

# --- Configuration ---
PATTERN_FILE = './pattern_analysis_result.csv'
OUTPUT_REPORT = './backtest_report.md'
OUTPUT_CSV = './backtest_results_summary.csv'

# Backtest Parameters (only used if you implement Limited later)
INITIAL_CAPITAL = 1_000_000
MAX_POSITIONS = 10
POSITION_SIZE_PCT = 0.10

def load_data_polars():
    print("Loading data with Polars...", flush=True)
    
    df = pl.read_csv(
        PATTERN_FILE,
        try_parse_dates=True,
        infer_schema_length=10000  # 重要：讓 Polars 看到更多行來正確猜型別
    )
    
    # 強制轉所有價格欄位為 float64，無法轉的變 null
    price_cols = [
        col for col in df.columns 
        if any(keyword in col.lower() for keyword in ["price", "open", "high", "low", "close", "volume"])
    ]
    
    df = df.with_columns([
        pl.col(col).cast(pl.Float64, strict=False) for col in price_cols
    ])
    
    df = df.sort(["sid", "date"])
    
    df = df.with_columns([
        pl.col("close").rolling_mean(window_size=20).over("sid").alias("ma20"),
        pl.col("close").rolling_mean(window_size=50).over("sid").alias("ma50")
    ])
    
    print(f"Data loaded: {df.shape[0]:,} rows, {df.shape[1]} columns", flush=True)
    return df

# --- Optimized Unlimited / Fixed Exit Scenario
def run_scenario_unlimited_task(strategy: str, r_mult: float, time_exit: int | None):
    df = load_data_polars()
    
    pat = strategy[3:]  # "is_vcp" → "vcp"
    buy_col = f"{pat}_buy_price"
    stop_col = f"{pat}_stop_price"
    
    signals = df.filter(
        (pl.col(strategy) == True) &
        pl.col(buy_col).is_not_null() &
        pl.col(stop_col).is_not_null() &
        (pl.col(buy_col) > pl.col(stop_col))
    )
    
    if signals.is_empty():
        return {}
    
    # Partition once → O(N) and very fast
    all_partitions = df.partition_by("sid", as_dict=True, maintain_order=True)
    sig_partitions = signals.partition_by("sid", as_dict=True, maintain_order=True)
    
    trades = []
    
    for sid, sigs_df in sig_partitions.items():
        stock_df = all_partitions[sid]
        if stock_df.is_empty():
            continue
            
        high_np = stock_df["high"].to_numpy()
        low_np = stock_df["low"].to_numpy()
        close_np = stock_df["close"].to_numpy()
        date_col = stock_df.get_column("date")
        
        for sig in sigs_df.to_dicts():
            buy = sig[buy_col]
            stop = sig[stop_col]
            risk = buy - stop
            if risk <= 0:
                continue
                
            sig_date = sig["date"]
            sig_idx = date_col.search_sorted(sig_date)  # exact match guaranteed
            
            # Entry search window = 30 trading days after the signal day
            future_end = min(sig_idx + 31, len(high_np))
            future_high = high_np[sig_idx + 1 : future_end]
            if len(future_high) == 0:
                continue
                
            entry_candidates = np.where(future_high >= buy)[0]
            if entry_candidates.size == 0:
                continue
            entry_rel = entry_candidates[0]
            entry_abs = sig_idx + 1 + entry_rel
            
            target = buy + risk * r_mult
            
            # Path start / end
            if time_exit is not None:
                path_end = min(entry_abs + time_exit, len(high_np))
            else:
                path_end = len(high_np)
                
            if path_end == entry_abs:  # impossible, but safety
                continue
                
            path_high = high_np[entry_abs:path_end]
            path_low = low_np[entry_abs:path_end]
            close_last = close_np[path_end - 1]
            
            stop_hits = np.where(path_low <= stop)[0]
            target_hits = np.where(path_high >= target)[0]
            
            stop_i = stop_hits[0] if stop_hits.size > 0 else np.inf
            target_i = target_hits[0] if target_hits.size > 0 else np.inf
            
            min_i = min(stop_i, target_i)
            
            if np.isinf(min_i):
                pnl = (close_last - buy) / buy
            elif stop_i < target_i:
                pnl = (stop - buy) / buy
            else:
                pnl = (target - buy) / buy
                
            trades.append(pnl)
            
    if not trades:
        return {}
        
    trades_np = np.array(trades, dtype=np.float64)
    return {
        'Scenario': 'Unlimited_Fixed',
        'Strategy': strategy,
        'R': r_mult,
        'TimeExit': time_exit if time_exit is not None else 'Unlimited',
        'Win Rate': np.mean(trades_np > 0),
        'Avg PnL': np.mean(trades_np),
        'Total PnL (Sum %)': np.sum(trades_np),
        'Count': len(trades_np)
    }

# Optimized Trailing-Stop Scenario
def run_scenario_trailing_task(strategy: str, r_trigger: float, trail_ma_col: str):
    df = load_data_polars()
    
    pat = strategy[3:]
    buy_col = f"{pat}_buy_price"
    stop_col = f"{pat}_stop_price"
    
    signals = df.filter(
        (pl.col(strategy) == True) &
        pl.col(buy_col).is_not_null() &
        pl.col(stop_col).is_not_null() &
        (pl.col(buy_col) > pl.col(stop_col))
    )
    
    if signals.is_empty():
        return {}
    
    all_partitions = df.partition_by("sid", as_dict=True, maintain_order=True)
    sig_partitions = signals.partition_by("sid", as_dict=True, maintain_order=True)
    
    trades = []
    
    for sid, sigs_df in sig_partitions.items():
        stock_df = all_partitions[sid]
        high_np = stock_df["high"].to_numpy()
        low_np = stock_df["low"].to_numpy()
        close_np = stock_df["close"].to_numpy()
        ma_np = stock_df[trail_ma_col].to_numpy()
        date_col = stock_df.get_column("date")
        
        for sig in sigs_df.to_dicts():
            buy = sig[buy_col]
            stop = sig[stop_col]
            risk = buy - stop
            if risk <= 0:
                continue
                
            sig_date = sig["date"]
            sig_idx = date_col.search_sorted(sig_date)
            
            future_end = min(sig_idx + 31, len(high_np))
            future_high = high_np[sig_idx + 1 : future_end]
            entry_candidates = np.where(future_high >= buy)[0]
            if entry_candidates.size == 0:
                continue
            entry_rel = entry_candidates[0]
            entry_abs = sig_idx + 1 + entry_rel
            
            # Path = everything from entry day onward
            highs = high_np[entry_abs:]
            lows = low_np[entry_abs:]
            mas = ma_np[entry_abs:]
            closes = close_np[entry_abs:]
            
            current_stop = stop
            trailing_active = False
            trigger_price = buy + risk * r_trigger
            
            exit_pnl = 0.0
            broken = False
            for j in range(len(highs)):
                h = highs[j]
                l = lows[j]
                ma = mas[j]
                
                if l <= current_stop:
                    exit_pnl = (current_stop - buy) / buy
                    broken = True
                    break
                    
                if not trailing_active:
                    if h >= trigger_price:
                        trailing_active = True
                        current_stop = buy  # breakeven
                        
                if trailing_active and not np.isnan(ma):
                    current_stop = max(current_stop, ma)
            
            if not broken:
                exit_pnl = (closes[-1] - buy) / buy
                
            trades.append(exit_pnl)
    
    if not trades:
        return {}
        
    trades_np = np.array(trades, dtype=np.float64)
    return {
        'Scenario': 'Trailing_Stop',
        'Strategy': strategy,
        'R': f'Trigger {r_trigger}R',
        'TimeExit': f'Trail {trail_ma_col}',
        'Win Rate': np.mean(trades_np > 0),
        'Avg PnL': np.mean(trades_np),
        'Total PnL (Sum %)': np.sum(trades_np),
        'Count': len(trades_np)
    }

def main():
    start_time = time.time()
    
    strategies = ['is_vcp', 'is_htf', 'is_cup']
    rs = [2.0, 3.0, 4.0]
    times = [10, 15, 20, 30, None]
    
    tasks_unlimited = [(strat, r, t) for strat in strategies for r in rs for t in times]
    tasks_trailing = [(strat, 2.0, ma) for strat in strategies for ma in ['ma20', 'ma50']]
    
    results = []
    
    print(f"Running {len(tasks_unlimited)} Unlimited scenarios + {len(tasks_trailing)} Trailing scenarios with {os.cpu_count()} workers...")
    
    with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
        # Unlimited
        future_to_param_unl = {executor.submit(run_scenario_unlimited_task, strat, r, t): (strat, r, t) for strat, r, t in tasks_unlimited}
        
        for future in as_completed(future_to_param_unl):
            strat, r, t = future_to_param_unl[future]
            try:
                res = future.result()
                if res:  # only append if there were trades
                    res.update({'Scenario': 'Unlimited_Fixed', 'Strategy': strat, 'R': r, 'TimeExit': t if t is not None else 'Unlimited'})
                    results.append(res)
            except Exception as e:
                print(f"Unlimited error {strat} {r}R {t}: {e}")
        
        # Trailing
        future_to_param_tr = {executor.submit(run_scenario_trailing_task, strat, r_trig, ma): (strat, r_trig, ma) for strat, r_trig, ma in tasks_trailing}
        
        for future in as_completed(future_to_param_tr):
            strat, r_trig, ma = future_to_param_tr[future]
            try:
                res = future.result()
                if res:
                    res.update({'Scenario': 'Trailing_Stop', 'Strategy': strat, 'R': f'Trigger {r_trig}R', 'TimeExit': f'Trail {ma}'})
                    results.append(res)
            except Exception as e:
                print(f"Trailing error {strat} {ma}: {e}")
    
    # Save
    if results:
        res_df = pl.DataFrame(results)
        res_df.write_csv(OUTPUT_CSV)
        
        with open(OUTPUT_REPORT, "w") as f:
            f.write("# Backtest Report\n\n")
            f.write(f"Execution Time: {time.time() - start_time:.2f}s\n\n")
            f.write("## Summary\n")
            f.write(res_df.to_pandas().to_markdown(index=False))  # Polars → Pandas only for markdown
        
    print(f"Done. Total time: {time.time() - start_time:.2f}s")

if __name__ == "__main__":
    main()