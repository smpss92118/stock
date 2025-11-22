"""
ML Data Preparation Script

生成 ML 訓練數據，包含特徵工程和標籤生成。

Usage:
    python stock/ml_enhanced/scripts/prepare_ml_data.py
    
Output:
    stock/ml_enhanced/data/ml_features.csv
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add paths
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

# Import original data loader
from scripts.run_backtest import load_data_polars, generate_trade_candidates

# Import shared modules
from src.utils.logger import setup_logger
from src.ml.features import calculate_technical_indicators, extract_ml_features

# Configuration
PATTERN_FILE = os.path.join(os.path.dirname(__file__), '../../data/processed/pattern_analysis_result.csv')
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), '../data/ml_features.csv')
STOCK_INFO_FILE = os.path.join(os.path.dirname(__file__), '../../data/raw/2023_2025_daily_stock_info.csv')

# Setup Logger
logger = setup_logger('prepare_ml_data')

def simulate_trade_trailing(high_np, low_np, close_np, ma_np, buy_price, stop_price, trigger_r=1.5):
    """
    Simulate trade with Trailing Stop (Trigger 1.5R, Trail MA20).
    Returns: pnl, duration
    """
    risk = buy_price - stop_price
    if risk <= 0: return 0.0, 1
    
    trigger_price = buy_price + risk * trigger_r
    current_stop = stop_price
    trailing_active = False
    
    exit_idx = -1
    pnl = 0.0
    
    for k in range(len(high_np)):
        h = high_np[k]
        l = low_np[k]
        c = close_np[k]
        m = ma_np[k] if ma_np is not None else np.nan
        
        # 1. Check Stop
        if l <= current_stop:
            pnl = (current_stop - buy_price) / buy_price
            exit_idx = k
            break
        
        # 2. Check Trigger
        if not trailing_active and h >= trigger_price:
            trailing_active = True
            current_stop = buy_price # Breakeven
            
        # 3. Update Trail
        if trailing_active and not np.isnan(m):
            current_stop = max(current_stop, m)
            
    if exit_idx == -1:
        # End of data
        exit_idx = len(high_np) - 1
        pnl = (close_np[exit_idx] - buy_price) / buy_price
        
    duration = max(exit_idx, 1) # Avoid 0
    return pnl, duration

def simulate_trade_fixed(high_np, low_np, close_np, buy_price, stop_price, r_mult=2.0, time_exit=20):
    """
    Simulate trade with Fixed R-multiple Target and Time Exit.
    Returns: pnl, duration
    """
    risk = buy_price - stop_price
    if risk <= 0: return 0.0, 1
    
    target_price = buy_price + risk * r_mult
    
    # Limit path to time_exit
    path_len = min(time_exit, len(high_np))
    
    exit_idx = -1
    pnl = 0.0
    
    for k in range(path_len):
        h = high_np[k]
        l = low_np[k]
        
        # Check Stop Hit (priority 1)
        if l <= stop_price:
            pnl = (stop_price - buy_price) / buy_price
            exit_idx = k
            break
        
        # Check Target Hit (priority 2)
        if h >= target_price:
            pnl = (target_price - buy_price) / buy_price
            exit_idx = k
            break
    
    if exit_idx == -1:
        # Time Exit
        exit_idx = path_len - 1
        pnl = (close_np[exit_idx] - buy_price) / buy_price
    
    duration = max(exit_idx + 1, 1)
    return pnl, duration

def generate_labels(df, pattern_type):
    """
    Generate labels based on Score = Profit% / Duration.
    NEW: Calculates for MULTIPLE exit strategies per signal.
    Returns 3x data (one row per exit mode).
    """
    pattern_col = f'is_{pattern_type}'
    buy_col = f'{pattern_type}_buy_price'
    stop_col = f'{pattern_type}_stop_price'
    
    # Filter signals
    signals = df[
        (df[pattern_col] == True) &
        (df[buy_col].notna()) &
        (df[stop_col].notna())
    ].copy()
    
    # Define exit modes
    exit_modes = [
        {'name': 'fixed_r2_t20', 'type': 'fixed', 'r_mult': 2.0, 'time_exit': 20},
        {'name': 'fixed_r3_t20', 'type': 'fixed', 'r_mult': 3.0, 'time_exit': 20},
        {'name': 'trailing_15r', 'type': 'trailing', 'trigger_r': 1.5}
    ]
    
    all_trade_results = {mode['name']: [] for mode in exit_modes}
    
    # Ensure MA20 exists
    if 'ma20' not in df.columns:
        df['ma20'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(20).mean())

    # Partition by SID for speed
    df_groups = dict(tuple(df.groupby('sid')))
    
    for idx, signal in signals.iterrows():
        sid = signal['sid']
        signal_date = signal['date']
        buy_price = signal[buy_col]
        stop_price = signal[stop_col]
        
        if sid not in df_groups: continue
        stock_df = df_groups[sid]
        
        # Get data AFTER signal
        future_data = stock_df[stock_df['date'] > signal_date]
        if len(future_data) == 0: continue
        
        # Check Entry (Limit Buy within 30 days)
        entry_candidates = future_data[future_data['high'] >= buy_price]
        if len(entry_candidates) == 0: continue
        
        entry_date = entry_candidates.iloc[0]['date']
        
        # Simulation Data (from entry onwards)
        sim_data = stock_df[stock_df['date'] >= entry_date]
        if len(sim_data) < 1: continue
        
        high_np = sim_data['high'].values
        low_np = sim_data['low'].values
        close_np = sim_data['close'].values
        ma_np = sim_data['ma20'].values
        
        # Simulate ALL exit modes for this signal
        for mode in exit_modes:
            if mode['type'] == 'fixed':
                pnl, duration = simulate_trade_fixed(
                    high_np, low_np, close_np, buy_price, stop_price,
                    r_mult=mode['r_mult'], time_exit=mode['time_exit']
                )
            else:  # trailing
                pnl, duration = simulate_trade_trailing(
                    high_np, low_np, close_np, ma_np, buy_price, stop_price,
                    trigger_r=mode['trigger_r']
                )
            
            score = (pnl * 100) / duration
            
            all_trade_results[mode['name']].append({
                'sid': sid,
                'date': signal_date,
                'actual_return': pnl,
                'duration': duration,
                'score': score
            })
    
    # Now calculate quartiles PER exit mode and assign labels
    final_lookup = {}
    
    for exit_mode_name, trade_results in all_trade_results.items():
        if not trade_results:
            logger.info(f"No results for {pattern_type} + {exit_mode_name}")
            continue
            
        # Convert to DF to calculate quantiles
        res_df = pd.DataFrame(trade_results)
        
        # Calculate Quartiles
        q25 = res_df['score'].quantile(0.25)
        q50 = res_df['score'].quantile(0.50)
        q75 = res_df['score'].quantile(0.75)
        
        logger.info(f"Score Quartiles for {pattern_type} + {exit_mode_name}: 25%={q25:.2f}, 50%={q50:.2f}, 75%={q75:.2f}")
        
        for r in trade_results:
            s = r['score']
            if s >= q75:
                label = 'A'
                is_investable = 1
            elif s >= q50:
                label = 'B'
                is_investable = 1
            elif s >= q25:
                label = 'C'
                is_investable = 0
            else:
                label = 'D'
                is_investable = 0
                
            # Key: (sid, date, exit_mode)
            key = (r['sid'], r['date'], exit_mode_name)
            final_lookup[key] = {
                'actual_return': r['actual_return'],
                'score': s,
                'label_abcd': label,
                'is_winner': is_investable,
                'duration': r['duration']
            }
    
    return final_lookup

def main():
    logger.info("="*80)
    logger.info("ML Data Preparation")
    logger.info("="*80)
    
    # Load data
    logger.info("Loading data...")
    df = load_data_polars()
    if df is None:
        logger.error("❌ Failed to load data")
        return
    
    # Convert to pandas for easier manipulation
    df_pd = df.to_pandas()
    if 'volume' not in df_pd.columns:
        logger.error("❌ volume column missing in pattern_analysis_result.csv. Regenerate it with run_historical_analysis.py.")
        return
    if df_pd['volume'].isna().all():
        logger.error("❌ volume column is empty. Check data extraction before ML prep.")
        return
    
    # Calculate technical indicators
    logger.info("Calculating technical indicators for all stocks...")
    # Use group_keys=False to avoid FutureWarning while keeping all columns
    df_pd = df_pd.groupby('sid', group_keys=False).apply(lambda x: calculate_technical_indicators(x)).reset_index(drop=True)
    
    # Ensure MA20 is present for simulation
    if 'ma20' not in df_pd.columns:
        logger.info("Calculating MA20 for simulation...")
        df_pd['ma20'] = df_pd.groupby('sid')['close'].transform(lambda x: x.rolling(20).mean())
    
    # Generate features for each pattern type
    all_features = []
    
    for pattern_type in ['htf', 'cup', 'vcp']:
        logger.info(f"\n{'='*80}")
        logger.info(f"Processing {pattern_type.upper()} patterns...")
        logger.info(f"{'='*80}")
        
        # Filter signals
        pattern_col = f'is_{pattern_type}'
        signals = df_pd[df_pd[pattern_col] == True].copy()
        logger.info(f"Found {len(signals)} {pattern_type.upper()} signals")
        
        if len(signals) == 0:
            continue
            
        # Generate labels (Target)
        logger.info(f"Generating labels for {pattern_type}...")
        labels = generate_labels(df_pd, pattern_type)
        logger.info(f"  Generated labels for {len(labels)} combinations (signal × exit_mode)")
        
        # Extract features
        count = 0
        for idx, row in signals.iterrows():
            sid = row['sid']
            date = row['date']
            
            # Extract features ONCE per signal (features are same across exit modes)
            features = extract_ml_features(row, pattern_type)
            if features is None: continue
            
            if pattern_type == 'cup':
                features['consolidation_days'] = row.get('cup_days', 10)
            elif pattern_type == 'htf':
                features['consolidation_days'] = row.get('htf_days', 5)
            elif pattern_type == 'vcp':
                features['consolidation_days'] = row.get('vcp_days', 10)
            else:
                features['consolidation_days'] = 0          
            # Create ONE row per exit mode
            for exit_mode in ['fixed_r2_t20', 'fixed_r3_t20', 'trailing_15r']:
                # Get label for this specific exit mode
                label_data = labels.get((sid, date, exit_mode))
                
                if not label_data: continue
                
                # Combine features + labels + metadata
                row_data = {
                    'sid': sid,
                    'date': date,
                    'pattern_type': pattern_type.upper(),
                    'exit_mode': exit_mode,
                    **features,
                    'actual_return': label_data['actual_return'],
                    'duration': label_data['duration'],
                    'score': label_data['score'],
                    'label_abcd': label_data['label_abcd'],
                    'is_winner': label_data['is_winner']
                }
                
                all_features.append(row_data)
                count += 1
        
        logger.info(f"  Extracted features for {count} rows")

    # Create DataFrame
    if not all_features:
        logger.warning("No features generated!")
        return

    feature_df = pd.DataFrame(all_features)
    
    # Save to CSV
    logger.info(f"\n{'='*80}")
    logger.info("Feature Generation Complete")
    logger.info(f"{'='*80}")
    logger.info(f"Total samples: {len(feature_df)}")
    logger.info(f"Winners (>10% return): {feature_df['is_winner'].sum()} ({feature_df['is_winner'].mean()*100:.1f}%)")
    logger.info(f"Average return: {feature_df['actual_return'].mean()*100:.2f}%")
    logger.info(f"Median return: {feature_df['actual_return'].median()*100:.2f}%")
    logger.info(f"Max return: {feature_df['actual_return'].max()*100:.2f}%")
    logger.info(f"Min return: {feature_df['actual_return'].min()*100:.2f}%")
    
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    feature_df.to_csv(OUTPUT_FILE, index=False)
    logger.info(f"\n✅ Features saved to {OUTPUT_FILE}")
    
    # Show sample
    print("\nSample features:")
    print(feature_df.head(20)[['sid', 'date', 'pattern_type', 'grade_numeric', 'distance_to_buy_pct', 'actual_return', 'is_winner']])
    
    logger.info("✅ Feature preparation complete")

if __name__ == "__main__":
    main()
