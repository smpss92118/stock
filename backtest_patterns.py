import polars as pl
import numpy as np
import pandas as pd
import os
import time
from datetime import datetime, date
from concurrent.futures import ProcessPoolExecutor, as_completed

# --- Configuration ---
PATTERN_FILE = './pattern_analysis_result.csv'
OUTPUT_REPORT = './backtest_report_v2.md'
OUTPUT_CSV = './backtest_results_v2.csv'

# --- Capital Management Settings ---
INITIAL_CAPITAL = 1_000_000
MAX_POSITIONS = 10
POSITION_SIZE_PCT = 0.10  # 10% per trade (100k)
RISK_FREE_RATE = 0.02     # For Sharpe Ratio

def load_data_polars():
    print("Loading data with Polars...", flush=True)
    try:
        df = pl.read_csv(
            PATTERN_FILE,
            try_parse_dates=True,
            infer_schema_length=10000
        )
    except Exception as e:
        print(f"Error loading file: {e}")
        return None
    
    # Cast numeric columns
    price_cols = [col for col in df.columns if any(k in col.lower() for k in ["price", "open", "high", "low", "close", "volume"])]
    df = df.with_columns([pl.col(col).cast(pl.Float64, strict=False) for col in price_cols])
    
    # Sort
    df = df.sort(["sid", "date"])
    
    # Calculate Moving Averages for Trailing Stop
    df = df.with_columns([
        pl.col("close").rolling_mean(window_size=20).over("sid").alias("ma20"),
        pl.col("close").rolling_mean(window_size=50).over("sid").alias("ma50")
    ])
    
    print(f"Data loaded: {df.shape[0]:,} rows. Columns: {df.columns}", flush=True)
    return df

# --- Core Engine: Trade Extractor ---
# 負責計算「每一筆」符合訊號的交易的進出場時間與損益，不考慮資金限制
def generate_trade_candidates(df, strategy, exit_mode, params):
    """
    exit_mode: 'fixed' or 'trailing'
    params: dict of parameters
            fixed: {'r_mult': float, 'time_exit': int|None}
            trailing: {'trigger_r': float, 'trail_ma': str}
    """
    pat = strategy[3:]  # is_vcp -> vcp
    buy_col = f"{pat}_buy_price"
    stop_col = f"{pat}_stop_price"
    
    # Check if columns exist
    if buy_col not in df.columns or stop_col not in df.columns:
        return []

    signals = df.filter(
        (pl.col(strategy) == True) &
        pl.col(buy_col).is_not_null() &
        pl.col(stop_col).is_not_null() &
        (pl.col(buy_col) > pl.col(stop_col))
    )
    
    if signals.is_empty():
        return []
    
    # Partition for speed
    all_partitions = df.partition_by("sid", as_dict=True, maintain_order=True)
    sig_partitions = signals.partition_by("sid", as_dict=True, maintain_order=True)
    
    candidates = []
    
    for sid, sigs_df in sig_partitions.items():
        if sid not in all_partitions: continue
        stock_df = all_partitions[sid]
        
        # Convert to numpy/list for fast indexing
        high_np = stock_df["high"].to_numpy()
        low_np = stock_df["low"].to_numpy()
        close_np = stock_df["close"].to_numpy()
        ma_np = None
        if exit_mode == 'trailing':
            ma_np = stock_df[params['trail_ma']].to_numpy()
            
        # Convert dates to python date objects immediately to fix comparison bugs
        date_list = [d.date() if isinstance(d, datetime) else d for d in stock_df["date"].to_list()]
        
        for sig in sigs_df.to_dicts():
            buy = sig[buy_col]
            stop = sig[stop_col]
            risk = buy - stop
            if risk <= 0: continue
                
            # Find signal index
            sig_date_val = sig["date"]
            if isinstance(sig_date_val, datetime):
                sig_date_obj = sig_date_val.date()
            else:
                sig_date_obj = sig_date_val # Assume it's date if not datetime

            try:
                sig_idx = date_list.index(sig_date_obj)
            except ValueError:
                continue # Date not found
            
            # 1. Entry Check (Limit Buy within 30 days)
            future_end = min(sig_idx + 31, len(high_np))
            future_high = high_np[sig_idx + 1 : future_end]
            if len(future_high) == 0: continue
            
            entry_candidates_idx = np.where(future_high >= buy)[0]
            if entry_candidates_idx.size == 0: continue
            
            entry_rel = entry_candidates_idx[0]
            entry_abs = sig_idx + 1 + entry_rel
            entry_date = date_list[entry_abs]
            
            # 2. Exit Logic
            pnl = 0.0
            exit_abs = -1
            
            # --- Logic A: Fixed Target / Time ---
            if exit_mode == 'fixed':
                r_mult = params['r_mult']
                time_exit = params['time_exit']
                target = buy + risk * r_mult
                
                path_end = len(high_np)
                if time_exit is not None:
                    path_end = min(entry_abs + time_exit, len(high_np))
                
                path_high = high_np[entry_abs:path_end]
                path_low = low_np[entry_abs:path_end]
                
                # Check hits
                stop_hits = np.where(path_low <= stop)[0]
                target_hits = np.where(path_high >= target)[0]
                
                stop_i = stop_hits[0] if stop_hits.size > 0 else np.inf
                target_i = target_hits[0] if target_hits.size > 0 else np.inf
                
                if np.isinf(stop_i) and np.isinf(target_i):
                    # Time exit
                    exit_abs = path_end - 1
                    pnl = (close_np[exit_abs] - buy) / buy
                elif stop_i < target_i:
                    exit_abs = entry_abs + int(stop_i)
                    pnl = (stop - buy) / buy
                else:
                    exit_abs = entry_abs + int(target_i)
                    pnl = (target - buy) / buy

            # --- Logic B: Dynamic Trailing Stop ---
            elif exit_mode == 'trailing':
                trigger_price = buy + risk * params['trigger_r']
                current_stop = stop
                trailing_active = False
                
                path_high = high_np[entry_abs:]
                path_low = low_np[entry_abs:]
                path_ma = ma_np[entry_abs:]
                path_close = close_np[entry_abs:]
                
                exit_found = False
                
                for k in range(len(path_high)):
                    h = path_high[k]
                    l = path_low[k]
                    c = path_close[k]
                    m = path_ma[k]
                    
                    # 1. Check Stop Hit
                    if l <= current_stop:
                        pnl = (current_stop - buy) / buy
                        exit_abs = entry_abs + k
                        exit_found = True
                        break
                    
                    # 2. Check Trigger (Activate Trail)
                    if not trailing_active and h >= trigger_price:
                        trailing_active = True
                        current_stop = buy # Move to Breakeven immediately
                    
                    # 3. Update Trail
                    if trailing_active:
                        # If MA is valid, use it, but never lower the stop
                        if not np.isnan(m):
                            current_stop = max(current_stop, m)
                            
                if not exit_found:
                    # Held until end of data
                    exit_abs = len(path_high) - 1 + entry_abs
                    pnl = (path_close[-1] - buy) / buy

            # Add candidate
            if exit_abs != -1:
                candidates.append({
                    'entry_date': entry_date,
                    'exit_date': date_list[exit_abs],
                    'pnl': pnl,
                    'duration': exit_abs - entry_abs
                })
                
    return candidates

# --- Manager: Capital Simulation ---
def run_capital_simulation(candidates, mode='limited'):
    """
    mode: 'limited' (100W, 10 pos) or 'unlimited'
    """
    # Sort by entry date is crucial for FIFO
    candidates.sort(key=lambda x: x['entry_date'])
    
    executed_trades = []
    
    if mode == 'unlimited':
        # Assume fixed investment amount per trade for stats comparison
        fixed_amt = INITIAL_CAPITAL * POSITION_SIZE_PCT
        for t in candidates:
            t_record = t.copy()
            t_record['cost'] = fixed_amt
            t_record['profit'] = fixed_amt * t['pnl']
            executed_trades.append(t_record)
            
    elif mode == 'limited':
        current_cash = INITIAL_CAPITAL
        active_positions = [] # list of {'exit_date': date, 'cost': float, 'current_value': float}
        
        for t in candidates:
            today = t['entry_date']
            
            # 1. Release funds from expired positions
            still_active = []
            for p in active_positions:
                if p['exit_date'] <= today:
                    current_cash += p['return_cash']
                else:
                    still_active.append(p)
            active_positions = still_active
            
            # 2. Calculate Current Total Equity (Compounding!)
            # Total Equity = Cash + Sum of all active position costs
            # (We use cost as proxy for current value since we don't track intraday)
            total_equity = current_cash + sum(p['cost'] for p in active_positions)
            
            # 3. Calculate Position Size based on Current Equity (10% of total)
            position_size = total_equity * POSITION_SIZE_PCT
            
            # 4. Try to Enter
            if len(active_positions) < MAX_POSITIONS and current_cash >= position_size:
                current_cash -= position_size
                
                profit = position_size * t['pnl']
                return_cash = position_size + profit
                
                active_positions.append({
                    'exit_date': t['exit_date'],
                    'return_cash': return_cash,
                    'cost': position_size  # Track cost for equity calculation
                })
                
                t_record = t.copy()
                t_record['cost'] = position_size
                t_record['profit'] = profit
                executed_trades.append(t_record)
                
    return executed_trades

# --- Accountant: Metrics Calculation ---
def calculate_metrics(trades, scenario_name, settings_str):
    if not trades:
        return None
        
    df = pd.DataFrame(trades)
    
    # Basic
    count = len(df)
    win_rate = (df['pnl'] > 0).mean()
    total_profit = df['profit'].sum()
    
    # Equity Curve (Daily)
    # Map profits to exit dates
    df['exit_date'] = pd.to_datetime(df['exit_date'])
    daily_pnl = df.groupby('exit_date')['profit'].sum()
    
    min_date = pd.to_datetime(df['entry_date']).min()
    max_date = df['exit_date'].max()
    idx = pd.date_range(min_date, max_date)
    
    equity = pd.Series(0.0, index=idx)
    equity.loc[daily_pnl.index] = daily_pnl
    equity = equity.fillna(0).cumsum() + INITIAL_CAPITAL
    
    final_equity = equity.iloc[-1]
    ret_pct = (final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL
    
    # Drawdown
    roll_max = equity.cummax()
    dd = (equity - roll_max) / roll_max
    max_dd = dd.min()
    
    # Sharpe
    daily_ret = equity.pct_change().fillna(0)
    std = daily_ret.std()
    if std == 0:
        sharpe = 0
    else:
        # Annualized Sharpe
        sharpe = (daily_ret.mean() - (RISK_FREE_RATE/252)) / std * np.sqrt(252)
        
    # Consec Wins/Losses
    is_win = df['pnl'] > 0
    groups = is_win.ne(is_win.shift()).cumsum()
    streak = is_win.groupby(groups).agg(['first', 'count'])
    max_win_streak = streak[streak['first']]['count'].max() if not streak.empty else 0
    max_loss_streak = streak[~streak['first']]['count'].max() if not streak.empty else 0
    
    return {
        'Strategy': scenario_name,
        'Settings': settings_str,
        'Count': count,
        'Win Rate': round(win_rate * 100, 1),
        'Return %': round(ret_pct * 100, 1),
        'Max DD %': round(max_dd * 100, 1),
        'Sharpe': round(sharpe, 2),
        'Max Win Streak': int(max_win_streak) if not pd.isna(max_win_streak) else 0,
        'Max Loss Streak': int(max_loss_streak) if not pd.isna(max_loss_streak) else 0,
        'Total Profit': int(total_profit)
    }

# --- Worker Wrapper ---
def process_task(strategy, exit_mode, params):
    # Reload data inside worker for Windows/Safety, or pass if using Fork
    # For simplicity/robustness here we assume load_data_polars is fast or cached by OS
    df = load_data_polars() 
    if df is None: return []
    
    # 1. Generate Candidates
    candidates = generate_trade_candidates(df, strategy, exit_mode, params)
    if not candidates: return []
    
    results = []
    
    # Settings String
    if exit_mode == 'fixed':
        set_str = f"R={params['r_mult']}, T={params['time_exit']}"
    else:
        set_str = f"Trig={params['trigger_r']}R, Trail={params['trail_ma']}"
        
    # 2. Run Limited Capital
    trades_lim = run_capital_simulation(candidates, mode='limited')
    res_lim = calculate_metrics(trades_lim, f"{strategy} (Limited)", set_str)
    if res_lim: results.append(res_lim)
    
    # 3. Run Unlimited Capital (for comparison)
    trades_unl = run_capital_simulation(candidates, mode='unlimited')
    res_unl = calculate_metrics(trades_unl, f"{strategy} (Unlimited)", set_str)
    if res_unl: results.append(res_unl)
    
    return results

def main():
    start_t = time.time()
    
    strategies = ['is_vcp', 'is_htf', 'is_cup'] # Added CUP
    
    # Define tasks
    tasks = []
    
    # A. Fixed Exit Tasks
    for s in strategies:
        for r in [2.0, 3.0]:
            for t in [20, 60]:
                params = {'r_mult': r, 'time_exit': t}
                tasks.append((s, 'fixed', params))
                
    # B. Dynamic Trailing Tasks
    for s in strategies:
        for trig in [1.5, 2.0]: # Activate trail early or late
            for ma in ['ma20', 'ma50']:
                params = {'trigger_r': trig, 'trail_ma': ma}
                tasks.append((s, 'trailing', params))
                
    print(f"Running {len(tasks)} simulation tasks...")
    
    final_results = []
    with ProcessPoolExecutor(max_workers=min(os.cpu_count(), 6)) as ex:
        futures = {ex.submit(process_task, s, m, p): (s,m,p) for s,m,p in tasks}
        
        for fut in as_completed(futures):
            try:
                res = fut.result()
                final_results.extend(res)
            except Exception as e:
                print(f"Task failed: {e}")
                
    if final_results:
        df_res = pd.DataFrame(final_results)
        
        # Sort for better readability
        df_res = df_res.sort_values(by=['Strategy', 'Sharpe'], ascending=[True, False])
        
        df_res.to_csv(OUTPUT_CSV, index=False)
        print(f"Saved CSV to {OUTPUT_CSV}")
        
        with open(OUTPUT_REPORT, 'w') as f:
            f.write(f"# Backtest Report V2\nGenerated: {datetime.now()}\n\n")
            f.write(df_res.to_markdown(index=False))
            
        print("Report generated.")
    else:
        print("No trades generated.")
        
    print(f"Total Time: {time.time() - start_t:.2f}s")

if __name__ == "__main__":
    main()