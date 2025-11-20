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

# Configuration
PATTERN_FILE = os.path.join(os.path.dirname(__file__), '../../data/processed/pattern_analysis_result.csv')
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), '../data/ml_features.csv')
STOCK_INFO_FILE = os.path.join(os.path.dirname(__file__), '../../data/raw/2023_2025_daily_stock_info.csv')

def calculate_technical_indicators(group):
    """計算技術指標（簡化版）"""
    # RSI
    group['rsi_14'] = 50  # Simplified
    
    # MA Trend
    if 'ma20' in group.columns and 'ma50' in group.columns:
        group['ma_trend'] = (group['ma20'] > group['ma50']).astype(int)
    else:
        group['ma_trend'] = 1
    
    # Volatility
    if len(group) >= 20:
        group['volatility'] = group['close'].pct_change().rolling(20).std()
    else:
        group['volatility'] = 0.02
    
    # ATR Ratio (Simplified)
    if len(group) >= 14:
        high_low = group['high'] - group['low']
        group['atr_ratio'] = high_low.rolling(14).mean() / group['close']
    else:
        group['atr_ratio'] = 0.02
    
    # Market Trend (Simplified: assume bullish)
    group['market_trend'] = 1
    
    return group

def extract_pattern_features(row, pattern_type):
    """提取型態特徵"""
    features = {}
    
    if pattern_type == 'htf':
        features['pattern_type'] = 'HTF'
        features['buy_price'] = row.get('htf_buy_price', 0)
        features['stop_price'] = row.get('htf_stop_price', 0)
        features['pattern_grade'] = row.get('htf_grade', 'C')
        # Convert grade to numeric
        grade_map = {'A': 3, 'B': 2, 'C': 1}
        features['grade_numeric'] = grade_map.get(features['pattern_grade'], 1)
    elif pattern_type == 'cup':
        features['pattern_type'] = 'CUP'
        features['buy_price'] = row.get('cup_buy_price', 0)
        features['stop_price'] = row.get('cup_stop_price', 0)
        features['pattern_grade'] = 'N/A'
        features['grade_numeric'] = 2  # Default to B
    elif pattern_type == 'vcp':
        features['pattern_type'] = 'VCP'
        features['buy_price'] = row.get('vcp_buy_price', 0)
        features['stop_price'] = row.get('vcp_stop_price', 0)
        features['pattern_grade'] = 'N/A'
        features['grade_numeric'] = 2  # Default to B
    
    # Distance to buy price
    current_price = row['close']
    if features['buy_price'] > 0:
        features['distance_to_buy_pct'] = (features['buy_price'] - current_price) / current_price * 100
    else:
        features['distance_to_buy_pct'] = 0
    
    # Risk percentage
    if features['buy_price'] > 0 and features['stop_price'] > 0:
        features['risk_pct'] = (features['buy_price'] - features['stop_price']) / features['buy_price'] * 100
    else:
        features['risk_pct'] = 0
    
    return features

def generate_labels(df, pattern_type):
    """
    生成標籤：使用原始回測引擎計算實際報酬
    
    注意：generate_trade_candidates 返回的是「進場後的交易」
    我們需要將其映射回「訊號日期」
    """
    print(f"Generating labels for {pattern_type}...")
    
    # Use original backtest engine to get actual returns
    strategy = f'is_{pattern_type}'
    
    # Best parameters from original backtest
    params = {'trigger_r': 1.5, 'trail_ma': 'ma20'}
    
    # Generate trade candidates
    candidates = generate_trade_candidates(df, strategy, 'trailing', params)
    
    print(f"  Generated {len(candidates)} trade candidates")
    
    # The problem: candidates don't have 'sid', we need to extract it from the backtest process
    # Solution: We'll match based on the pattern analysis result directly
    # For each signal, we simulate if it would have been traded and what the return would be
    
    # Instead, let's use a simpler approach:
    # Load the pattern analysis result and match signals with their future returns
    
    # For now, use a simplified labeling: calculate forward returns from signal date
    import polars as pl
    
    # Convert to pandas for easier manipulation
    df_pd = df.to_pandas()
    
    # For each signal, calculate forward return (30 days)
    pattern_col = f'is_{pattern_type}'
    buy_col = f'{pattern_type}_buy_price'
    stop_col = f'{pattern_type}_stop_price'
    
    signals = df_pd[
        (df_pd[pattern_col] == True) &
        (df_pd[buy_col].notna()) &
        (df_pd[stop_col].notna())
    ].copy()
    
    trade_lookup = {}
    
    for idx, signal in signals.iterrows():
        sid = signal['sid']
        signal_date = signal['date']
        buy_price = signal[buy_col]
        stop_price = signal[stop_col]
        
        # Get future prices for this stock
        stock_data = df_pd[
            (df_pd['sid'] == sid) &
            (df_pd['date'] > signal_date)
        ].head(30)  # Next 30 days
        
        if len(stock_data) == 0:
            continue
        
        # Simple forward return calculation
        # Find if price ever reached buy_price
        entry_candidates = stock_data[stock_data['high'] >= buy_price]
        
        if len(entry_candidates) == 0:
            # Never triggered
            trade_lookup[(sid, signal_date)] = 0.0
            continue
        
        # Entry on first day that hit buy_price
        entry_idx = entry_candidates.index[0]
        entry_price = buy_price
        
        # Get subsequent prices after entry
        future_data = df_pd[
            (df_pd['sid'] == sid) &
            (df_pd.index > entry_idx)
        ].head(20)  # Hold for max 20 days
        
        if len(future_data) == 0:
            trade_lookup[(sid, signal_date)] = 0.0
            continue
        
        # Simplified exit logic: check if hit stop or target (1.5R)
        risk = entry_price - stop_price
        target = entry_price + risk * 1.5
        
        pnl = 0.0
        for _, day in future_data.iterrows():
            # Check stop
            if day['low'] <= stop_price:
                pnl = (stop_price - entry_price) / entry_price
                break
            # Check target
            if day['high'] >= target:
                pnl = (target - entry_price) / entry_price
                break
        else:
            # Time exit
            pnl = (future_data.iloc[-1]['close'] - entry_price) / entry_price
        
        trade_lookup[(sid, signal_date)] = pnl
    
    print(f"  Generated labels for {len(trade_lookup)} signals")
    return trade_lookup

def main():
    print("="*80)
    print("ML Data Preparation")
    print("="*80)
    
    # Load data
    print("\nLoading data...")
    df = load_data_polars()
    if df is None:
        print("❌ Failed to load data")
        return
    
    # Convert to pandas for easier manipulation
    import polars as pl
    df_pd = df.to_pandas()
    
    # Calculate technical indicators
    print("Calculating technical indicators for all stocks...")
    # Use group_keys=False to avoid FutureWarning while keeping all columns
    df_pd = df_pd.groupby('sid', group_keys=False).apply(lambda x: calculate_technical_indicators(x)).reset_index(drop=True)
    
    # Generate features for each pattern type
    all_features = []
    
    for pattern_type in ['htf', 'cup', 'vcp']:
        print(f"\n{'='*80}")
        print(f"Processing {pattern_type.upper()} patterns...")
        print(f"{'='*80}")
        
        # Filter signals
        pattern_col = f'is_{pattern_type}'
        buy_col = f'{pattern_type}_buy_price'
        
        if pattern_col not in df_pd.columns or buy_col not in df_pd.columns:
            print(f"⚠️ Skipping {pattern_type}: columns not found")
            continue
        
        signals = df_pd[
            (df_pd[pattern_col] == True) &
            (df_pd[buy_col].notna())
        ].copy()
        
        print(f"Found {len(signals)} {pattern_type.upper()} signals")
        
        if len(signals) == 0:
            continue
        
        # Generate labels (actual returns from backtest)
        # Pass pandas df for simplified calculation
        trade_lookup = generate_labels(df, pattern_type)
        
        # Extract features for each signal
        for idx, row in signals.iterrows():
            # Pattern features
            pattern_features = extract_pattern_features(row, pattern_type)
            
            # Technical features
            tech_features = {
                'rsi_14': row.get('rsi_14', 50),
                'ma_trend': row.get('ma_trend', 0),
                'volatility': row.get('volatility', 0),
                'atr_ratio': row.get('atr_ratio', 0)
            }
            
            # Market features (simplified for now)
            market_features = {
                'market_trend': 1,  # TODO: Calculate from TAIEX
                'signal_count_ma10': 0,  # TODO: Calculate
                'signal_count_ma60': 0   # TODO: Calculate
            }
            
            # Combine all features
            features = {
                'sid': row['sid'],
                'date': row['date'],
                **pattern_features,
                **tech_features,
                **market_features
            }
            
            # Get label (actual return)
            key = (row['sid'], row['date'])
            actual_return = trade_lookup.get(key, 0)
            
            features['actual_return'] = actual_return
            features['is_winner'] = 1 if actual_return > 0.10 else 0  # 10% threshold
            
            all_features.append(features)
    
    # Create DataFrame
    if not all_features:
        print("\n❌ No features generated")
        return
    
    df_features = pd.DataFrame(all_features)
    
    # Remove rows with missing values
    df_features = df_features.dropna()
    
    print(f"\n{'='*80}")
    print(f"Feature Generation Complete")
    print(f"{'='*80}")
    print(f"Total samples: {len(df_features)}")
    print(f"Winners (>10% return): {df_features['is_winner'].sum()} ({df_features['is_winner'].mean()*100:.1f}%)")
    print(f"Average return: {df_features['actual_return'].mean()*100:.2f}%")
    print(f"Median return: {df_features['actual_return'].median()*100:.2f}%")
    print(f"Max return: {df_features['actual_return'].max()*100:.2f}%")
    print(f"Min return: {df_features['actual_return'].min()*100:.2f}%")
    
    # Save
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    df_features.to_csv(OUTPUT_FILE, index=False)
    print(f"\n✅ Features saved to {OUTPUT_FILE}")
    
    # Show sample
    print(f"\nSample features:")
    print(df_features[['sid', 'date', 'pattern_type', 'grade_numeric', 'distance_to_buy_pct', 'actual_return', 'is_winner']].head(20))

if __name__ == "__main__":
    main()
