import polars as pl
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import os
import sys
from datetime import datetime, date

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from src.utils.logger import setup_logger

logger = setup_logger('pattern_analyzer')

# --- Configuration ---
PATTERN_FILE = os.path.join(os.path.dirname(__file__), '../data/processed/pattern_analysis_result.csv')
OUTPUT_PLOT = os.path.join(os.path.dirname(__file__), '../data/processed/breakout_score_distribution.png')

def load_data():
    """Load and prepare pattern data."""
    logger.info("Loading data...")
    try:
        df = pl.read_csv(PATTERN_FILE, try_parse_dates=True, infer_schema_length=10000)
    except Exception as e:
        logger.error(f"Failed to load data: {e}")
        return None

    # Cast numeric columns
    price_cols = [col for col in df.columns if any(k in col.lower() for k in ["price", "open", "high", "low", "close", "volume"])]
    df = df.with_columns([pl.col(col).cast(pl.Float64, strict=False) for col in price_cols])
    
    # Sort
    df = df.sort(["sid", "date"])
    
    # Calculate Moving Averages for Trailing Stop if not present
    if "ma20" not in df.columns:
        df = df.with_columns(pl.col("close").rolling_mean(window_size=20).over("sid").alias("ma20"))
    if "ma50" not in df.columns:
        df = df.with_columns(pl.col("close").rolling_mean(window_size=50).over("sid").alias("ma50"))
        
    logger.info(f"Loaded {df.shape[0]:,} rows")
    return df

def simulate_trade(high_np, low_np, close_np, ma_np, entry_idx, buy_price, stop_price, exit_config):
    """
    Simulate a single trade with specified exit logic.
    
    Args:
        exit_config (dict):
            - mode: 'fixed' or 'trailing'
            - r_mult: Target R (for fixed)
            - time_exit: Max days (for fixed)
            - trigger_r: R-multiple to activate trail (for trailing)
            - trail_ma: 'ma20' or 'ma50' (passed as ma_np)
    """
    risk = buy_price - stop_price
    if risk <= 0: return None
    
    path_len = len(high_np)
    entry_abs = entry_idx
    
    # Slices from entry
    path_high = high_np[entry_abs:]
    path_low = low_np[entry_abs:]
    path_close = close_np[entry_abs:]
    path_ma = ma_np[entry_abs:] if ma_np is not None else None
    
    exit_rel = -1
    pnl = 0.0
    exit_reason = ""
    
    mode = exit_config.get('mode', 'fixed')
    
    if mode == 'fixed':
        r_mult = exit_config.get('r_mult', 2.0)
        time_exit = exit_config.get('time_exit', 20)
        target = buy_price + risk * r_mult
        
        # Limit path to time_exit
        check_len = min(time_exit, len(path_high))
        
        # Check hits
        # Note: We check from index 0 (entry day) or 1 (next day)? 
        # Usually entry is intraday, so we check same day for hits? 
        # Let's assume we check from entry day onwards.
        
        stop_hits = np.where(path_low[:check_len] <= stop_price)[0]
        target_hits = np.where(path_high[:check_len] >= target)[0]
        
        stop_i = stop_hits[0] if stop_hits.size > 0 else np.inf
        target_i = target_hits[0] if target_hits.size > 0 else np.inf
        
        if np.isinf(stop_i) and np.isinf(target_i):
            # Time Exit
            exit_rel = check_len - 1
            pnl = (path_close[exit_rel] - buy_price) / buy_price
            exit_reason = "Time"
        elif stop_i < target_i:
            exit_rel = int(stop_i)
            pnl = (stop_price - buy_price) / buy_price
            exit_reason = "Stop"
        else:
            exit_rel = int(target_i)
            pnl = (target - buy_price) / buy_price
            exit_reason = "Target"
            
    elif mode == 'trailing':
        trigger_r = exit_config.get('trigger_r', 1.5)
        trigger_price = buy_price + risk * trigger_r
        current_stop = stop_price
        trailing_active = False
        
        exit_found = False
        
        for k in range(len(path_high)):
            h = path_high[k]
            l = path_low[k]
            c = path_close[k]
            m = path_ma[k] if path_ma is not None else np.nan
            
            # 1. Check Stop
            if l <= current_stop:
                pnl = (current_stop - buy_price) / buy_price
                exit_rel = k
                exit_reason = "TrailStop" if trailing_active else "InitialStop"
                exit_found = True
                break
            
            # 2. Check Trigger
            if not trailing_active and h >= trigger_price:
                trailing_active = True
                current_stop = buy_price # Breakeven
                
            # 3. Update Trail
            if trailing_active and not np.isnan(m):
                current_stop = max(current_stop, m)
                
        if not exit_found:
            exit_rel = len(path_high) - 1
            pnl = (path_close[-1] - buy_price) / buy_price
            exit_reason = "EndData"

    return {
        'pnl': pnl,
        'duration': exit_rel, # Days held (0 means exited same day)
        'reason': exit_reason
    }

def run_analysis():
    df = load_data()
    if df is None: return
    
    strategies = ['is_cup', 'is_htf', 'is_vcp']
    
    # Configuration for the "Research"
    # Run BOTH strategies to define levels
    configs = [
        {
            'name': 'Trailing',
            'mode': 'trailing',
            'trigger_r': 1.5,
            'trail_ma': 'ma20'
        },
        {
            'name': 'Fixed',
            'mode': 'fixed',
            'r_mult': 3.0,
            'time_exit': 40 # Extended time for fixed to allow pattern to play out
        }
    ]
    
    results = []
    
    # Partition for speed
    all_partitions = df.partition_by("sid", as_dict=True, maintain_order=True)
    
    logger.info("Starting simulation...")
    
    for strategy in strategies:
        pat = strategy[3:]
        buy_col = f"{pat}_buy_price"
        stop_col = f"{pat}_stop_price"
        
        # Filter potential signals
        signals = df.filter(
            (pl.col(strategy) == True) &
            pl.col(buy_col).is_not_null()
        )
        
        sig_partitions = signals.partition_by("sid", as_dict=True, maintain_order=True)
        
        for sid_key, sigs_df in sig_partitions.items():
            if sid_key not in all_partitions: continue
            stock_df = all_partitions[sid_key]
            
            # Arrays
            high_np = stock_df["high"].to_numpy()
            low_np = stock_df["low"].to_numpy()
            close_np = stock_df["close"].to_numpy()
            ma_np = stock_df["ma20"].to_numpy() 
            date_list = stock_df["date"].to_list()
            
            # Date lookup
            date_map = {d: i for i, d in enumerate(date_list)}
            
            for sig in sigs_df.to_dicts():
                buy = sig[buy_col]
                stop = sig[stop_col]
                
                # Find signal index
                sig_date = sig["date"]
                if sig_date not in date_map: continue
                sig_idx = date_map[sig_date]
                
                # Check Entry (next 30 days)
                future_end = min(sig_idx + 31, len(high_np))
                future_high = high_np[sig_idx + 1 : future_end]
                
                if len(future_high) == 0: continue
                
                entry_candidates = np.where(future_high >= buy)[0]
                if entry_candidates.size == 0: continue
                
                entry_rel = entry_candidates[0]
                entry_abs = sig_idx + 1 + entry_rel
                
                # Run Simulation for BOTH configs
                for cfg in configs:
                    res = simulate_trade(
                        high_np, low_np, close_np, ma_np,
                        entry_abs, buy, stop, cfg
                    )
                    
                    if res:
                        duration = max(res['duration'], 1) 
                        score = (res['pnl'] * 100) / duration
                        
                        results.append({
                            'Strategy': strategy,
                            'ExitType': cfg['name'],
                            'Symbol': sid_key[0] if isinstance(sid_key, tuple) else sid_key,
                            'EntryDate': date_list[entry_abs],
                            'PnL': res['pnl'],
                            'Duration': res['duration'],
                            'Score': score,
                            'Reason': res['reason']
                        })
                    
    if not results:
        logger.warning("No trades generated.")
        return

    res_df = pd.DataFrame(results)
    logger.info(f"Generated {len(res_df)} trades.")
    
    # --- Visualization ---
    logger.info("Generating plot...")
    plt.figure(figsize=(14, 8))
    
    # Boxplot to show distribution per Group (Strategy + ExitType)
    res_df['Group'] = res_df['Strategy'] + " - " + res_df['ExitType']
    
    # Order groups
    groups = sorted(res_df['Group'].unique())
    
    # Boxplot
    plt.subplot(2, 1, 1)
    # Clip outliers for better boxplot visualization (optional, but good for readability)
    # Let's just plot as is, or limit Y axis
    plt.boxplot([res_df[res_df['Group']==g]['Score'] for g in groups], labels=groups)
    plt.title('Score Distribution by Pattern & Strategy')
    plt.ylabel('Score (%/Day)')
    plt.grid(True, alpha=0.3)
    
    # Histogram (Combined)
    plt.subplot(2, 1, 2)
    for g in groups:
        subset = res_df[res_df['Group'] == g]
        plt.hist(subset['Score'], bins=50, alpha=0.3, label=g, density=True, histtype='step', linewidth=2)
    plt.legend()
    plt.title('Score Density')
    plt.xlabel('Score')
    
    plt.tight_layout()
    plt.savefig(OUTPUT_PLOT)
    logger.info(f"Plot saved to {OUTPUT_PLOT}")
    
    # --- Percentile Analysis for A/B/C/D ---
    print("\n--- Percentile Analysis (Score) ---")
    print(f"{'Group':<25} | {'Count':<6} | {'Min':<6} | {'20%':<6} | {'40%':<6} | {'60%':<6} | {'80%':<6} | {'Max':<6} | {'Mean':<6}")
    print("-" * 90)
    
    stats_list = []
    
    for g in groups:
        scores = res_df[res_df['Group'] == g]['Score']
        p20, p40, p60, p80 = np.percentile(scores, [20, 40, 60, 80])
        
        print(f"{g:<25} | {len(scores):<6} | {scores.min():.2f} | {p20:.2f} | {p40:.2f} | {p60:.2f} | {p80:.2f} | {scores.max():.2f} | {scores.mean():.2f}")
        
        stats_list.append({
            'Group': g,
            'P20': p20, 'P40': p40, 'P60': p60, 'P80': p80
        })
        
    print("\n--- Proposed Thresholds (Quantile Based) ---")
    print("D: < 20% | C: 20-40% | B: 40-60% | A: > 60% (Just an example, check values)")

if __name__ == "__main__":
    run_analysis()
