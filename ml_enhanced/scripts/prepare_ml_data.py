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

def generate_labels(df, pattern_type):
    """
    生成標籤 (is_winner)
    
    Winner 定義:
    1. 未來 20 天內最大漲幅 > 10%
    2. 且在達到 10% 漲幅前，未觸及停損 (-5% 或 pattern stop)
    """
    pattern_col = f'is_{pattern_type}'
    buy_col = f'{pattern_type}_buy_price'
    stop_col = f'{pattern_type}_stop_price'
    
    signals = df[
        (df[pattern_col] == True) &
        (df[buy_col].notna()) &
        (df[stop_col].notna())
    ].copy()
    
    trade_lookup = {}
    
    for idx, signal in signals.iterrows():
        sid = signal['sid']
        signal_date = signal['date']
        buy_price = signal[buy_col]
        stop_price = signal[stop_col]
        
        # Get future prices for this stock
        stock_data = df[
            (df['sid'] == sid) &
            (df['date'] > signal_date)
        ].head(30)  # Next 30 days
        
        if len(stock_data) == 0:
            continue
        
        # Simple forward return calculation
        # Find if price ever reached buy_price
        entry_candidates = stock_data[stock_data['high'] >= buy_price]
        
        if len(entry_candidates) == 0:
            # Never triggered entry
            actual_return = 0.0
            is_winner = 0
        else:
            entry_date = entry_candidates.iloc[0]['date']
            
            # Look at price action AFTER entry
            post_entry = stock_data[stock_data['date'] >= entry_date].copy()
            
            if len(post_entry) < 2:
                actual_return = 0.0
                is_winner = 0
            else:
                # Calculate max potential return in next 20 days
                max_price = post_entry['high'].max()
                min_price = post_entry['low'].min()
                
                max_return = (max_price - buy_price) / buy_price
                max_drawdown = (min_price - buy_price) / buy_price
                
                # Winner definition: > 10% gain
                # Loser definition: Hit stop loss (pattern stop)
                
                # Check if stop hit before target
                stop_hit = False
                target_hit = False
                
                for _, day in post_entry.iterrows():
                    if day['low'] <= stop_price:
                        stop_hit = True
                        break
                    if day['high'] >= buy_price * 1.10:
                        target_hit = True
                        break
                
                if target_hit and not stop_hit:
                    is_winner = 1
                    actual_return = 0.10 # Cap at target
                elif stop_hit:
                    is_winner = 0
                    actual_return = (stop_price - buy_price) / buy_price
                else:
                    # Neither hit, take return at end of period
                    final_price = post_entry.iloc[-1]['close']
                    actual_return = (final_price - buy_price) / buy_price
                    is_winner = 1 if actual_return > 0.10 else 0
        
        trade_lookup[(sid, signal_date)] = {
            'actual_return': actual_return,
            'is_winner': is_winner
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
            if label_data:
                features['actual_return'] = label_data['actual_return']
                features['is_winner'] = label_data['is_winner']
            else:
                # If no label (e.g. recent data), mark as unknown or skip
                # For training, we need labels. For recent data, we might keep it for prediction?
                # Here we assume this script is for TRAINING data, so we skip if no label (future data)
                features['actual_return'] = 0
                features['is_winner'] = 0
            
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
