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

def simulate_trade_trailing(high_np, low_np, close_np, ma_np, buy_price, stop_price):
    """
    Simulate trade with Trailing Stop (Trigger 1.5R, Trail MA20).
    Returns: pnl, duration
    """
    risk = buy_price - stop_price
    if risk <= 0: return 0.0, 1
    
    trigger_price = buy_price + risk * 1.5
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

def generate_labels(df, pattern_type):
    """
    Generate labels based on Score = Profit% / Duration.
    Uses Trailing Stop simulation.
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
    
    trade_results = []
    
    # Prepare data for fast access
    # We need to group by sid to get full history for simulation
    # But df passed here might be the full dataframe? Yes, load_data_polars returns full df.
    # df is a pandas DataFrame here.
    
    # Ensure MA20 exists (it should be calculated in main)
    if 'ma20' not in df.columns:
        # Fallback if not present (should be added in main)
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
        # We need to find where signal_date is
        # Assuming sorted
        future_data = stock_df[stock_df['date'] > signal_date]
        if len(future_data) == 0: continue
        
        # Check Entry (Limit Buy within 30 days)
        # Find first day where High >= Buy
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
        
        pnl, duration = simulate_trade_trailing(high_np, low_np, close_np, ma_np, buy_price, stop_price)
        
        score = (pnl * 100) / duration
        
        trade_results.append({
            'sid': sid,
            'date': signal_date,
            'actual_return': pnl,
            'duration': duration,
            'score': score
        })
        
    if not trade_results:
        return {}
        
    # Convert to DF to calculate quantiles
    res_df = pd.DataFrame(trade_results)
    
    # Calculate Quartiles
    q25 = res_df['score'].quantile(0.25)
    q50 = res_df['score'].quantile(0.50)
    q75 = res_df['score'].quantile(0.75)
    
    logger.info(f"Score Quartiles for {pattern_type}: 25%={q25:.2f}, 50%={q50:.2f}, 75%={q75:.2f}")
    
    trade_lookup = {}
    for r in trade_results:
        s = r['score']
        if s >= q75:
            label = 'A'
            is_investable = 1
        elif s >= q50:
            label = 'B'
            is_investable = 1 # Treat B as investable? Plan said A/B.
        elif s >= q25:
            label = 'C'
            is_investable = 0
        else:
            label = 'D'
            is_investable = 0
            
        trade_lookup[(r['sid'], r['date'])] = {
            'actual_return': r['actual_return'],
            'score': s,
            'label_abcd': label,
            'is_winner': is_investable # Mapping is_winner to is_investable for compatibility
        }
        
    return trade_lookup

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
        logger.info(f"  Generated {len(labels)} trade candidates")
        
        # Extract features
        count = 0
        for idx, row in signals.iterrows():
            sid = row['sid']
            date = row['date']
            
            # Get label
            label_data = labels.get((sid, date))
            
            # Extract features using shared module
            features = extract_ml_features(row, pattern_type)
            
            # Add metadata
            features['sid'] = sid
            features['date'] = date
            
            # Add label
            # Add label
            if label_data:
                features['actual_return'] = label_data['actual_return']
                features['is_winner'] = label_data['is_winner']
                features['score'] = label_data['score']
                features['label_abcd'] = label_data['label_abcd']
            else:
                # If no label (e.g. recent data), mark as unknown or skip
                features['actual_return'] = 0
                features['is_winner'] = 0
                features['score'] = 0
                features['label_abcd'] = 'Unknown'
            
            all_features.append(features)
            count += 1
            
        logger.info(f"  Generated labels for {count} signals")

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
