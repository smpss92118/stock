"""
Performance Visualization - Generate Daily Equity Curves

Creates a comprehensive chart comparing:
1. ML-Enhanced Strategy (CUP R=2.0 + ML 0.4)
2. Original Best Strategy (HTF Trailing)
3. TAIEX Index

Usage:
    python stock/ml_enhanced/scripts/generate_performance_chart.py
    
Output:
    stock/ml_enhanced/results/performance_comparison.png
"""

import sys
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import pickle

# Add paths
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from scripts.run_backtest import (
    load_data_polars,
    generate_trade_candidates,
    run_capital_simulation
)

# Configuration
MODEL_PATH = os.path.join(os.path.dirname(__file__), '../models/stock_selector.pkl')
ML_FEATURES_PATH = os.path.join(os.path.dirname(__file__), '../data/ml_features.csv')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '../results/performance_comparison.png')
INITIAL_CAPITAL = 1_000_000

def load_ml_model():
    """載入 ML 模型"""
    with open(MODEL_PATH, 'rb') as f:
        model = pickle.load(f)
    return model

def get_daily_equity_from_trades(trades, start_date, end_date):
    """從交易記錄生成每日權益曲線"""
    df = pd.DataFrame(trades)
    df['exit_date'] = pd.to_datetime(df['exit_date'])
    
    # Group by exit date
    daily_pnl = df.groupby('exit_date')['profit'].sum()
    
    # Create full date range
    idx = pd.date_range(start_date, end_date, freq='D')
    equity = pd.Series(0.0, index=idx)
    
    # Fill in profits
    equity.loc[daily_pnl.index] = daily_pnl
    
    # Cumulative
    equity = equity.cumsum() + INITIAL_CAPITAL
    
    return equity

def run_ml_strategy():
    """運行 ML 增強策略 (CUP R=2.0 + ML 0.4)"""
    print("\n" + "="*80)
    print("Running ML-Enhanced Strategy: CUP R=2.0 + ML 0.4")
    print("="*80)
    
    # Load data
    df = load_data_polars()
    
    # Load ML model
    model = load_ml_model()
    
    # Load feature info
    feature_info_path = os.path.join(os.path.dirname(__file__), '../models/feature_info.pkl')
    with open(feature_info_path, 'rb') as f:
        feature_info = pickle.load(f)
    feature_cols = feature_info['feature_cols']
    
    # Load ML features and predict
    df_ml = pd.read_csv(ML_FEATURES_PATH)
    df_ml = df_ml[df_ml['pattern_type'] == 'CUP']
    
    # Predict probabilities
    X = df_ml[feature_cols]
    probas = model.predict_proba(X)[:, 1]
    df_ml['ml_proba'] = probas
    
    # Filter by threshold
    df_ml = df_ml[df_ml['ml_proba'] >= 0.4]
    
    print(f"  ML selected: {len(df_ml)} CUP signals (threshold 0.4)")
    
    # Convert to pandas for filtering
    df_pd = df.to_pandas()
    
    # Create filter set
    df_ml['date'] = pd.to_datetime(df_ml['date'])
    selected = set(zip(df_ml['sid'], df_ml['date'].dt.strftime('%Y-%m-%d')))
    
    # Filter signals
    df_pd['date_str'] = pd.to_datetime(df_pd['date']).dt.strftime('%Y-%m-%d')
    mask = df_pd.apply(lambda x: (x['sid'], x['date_str']) not in selected, axis=1)
    df_pd.loc[mask, 'is_cup'] = False
    df_pd = df_pd.drop(columns=['date_str'])
    
    # Convert back to polars
    import polars as pl
    df_filtered = pl.from_pandas(df_pd)
    
    # Generate candidates
    candidates = generate_trade_candidates(
        df_filtered, 
        'is_cup', 
        'fixed', 
        {'r_mult': 2.0, 'time_exit': 20}
    )
    
    print(f"  Candidates: {len(candidates)}")
    
    # Run simulation
    trades = run_capital_simulation(candidates, mode='limited')
    
    print(f"  Trades executed: {len(trades)}")
    
    # Get date range
    df_dates = df.to_pandas()
    start_date = df_dates['date'].min()
    end_date = df_dates['date'].max()
    
    # Generate equity curve
    equity = get_daily_equity_from_trades(trades, start_date, end_date)
    
    return equity

def run_original_strategy():
    """運行原始最佳策略 (HTF Trailing)"""
    print("\n" + "="*80)
    print("Running Original Strategy: HTF Trailing (1.5R, MA20)")
    print("="*80)
    
    # Load data
    df = load_data_polars()
    
    # Generate candidates
    candidates = generate_trade_candidates(
        df,
        'is_htf',
        'trailing',
        {'trigger_r': 1.5, 'trail_ma': 'ma20'}
    )
    
    print(f"  Candidates: {len(candidates)}")
    
    # Run simulation
    trades = run_capital_simulation(candidates, mode='limited')
    
    print(f"  Trades executed: {len(trades)}")
    
    # Get date range
    df_dates = df.to_pandas()
    start_date = df_dates['date'].min()
    end_date = df_dates['date'].max()
    
    # Generate equity curve
    equity = get_daily_equity_from_trades(trades, start_date, end_date)
    
    return equity

def load_taiex_data(start_date, end_date):
    """載入 TAIEX 數據"""
    print("\n" + "="*80)
    print("Loading TAIEX Data")
    print("="*80)
    
    try:
        import yfinance as yf
        
        # Download TAIEX
        taiex = yf.download('^TWII', start=start_date, end=end_date, progress=False)
        
        if taiex.empty:
            print("  ⚠️ No TAIEX data available")
            return None
        
        # Normalize to initial capital
        taiex_close = taiex['Close']
        taiex_normalized = (taiex_close / taiex_close.iloc[0]) * INITIAL_CAPITAL
        
        print(f"  TAIEX data points: {len(taiex_normalized)}")
        
        return taiex_normalized
        
    except Exception as e:
        print(f"  ⚠️ Error loading TAIEX: {e}")
        return None

def plot_performance_comparison(ml_equity, original_equity, taiex):
    """繪製績效對比圖"""
    print("\n" + "="*80)
    print("Generating Performance Chart")
    print("="*80)
    
    # Create figure
    fig, ax = plt.subplots(figsize=(16, 9))
    
    # Plot equity curves
    ax.plot(ml_equity.index, ml_equity, 
            label='ML-Enhanced (CUP R=2.0 + ML 0.4)', 
            linewidth=2.5, color='#00C853', alpha=0.9)
    
    ax.plot(original_equity.index, original_equity, 
            label='Original (HTF Trailing)', 
            linewidth=2.5, color='#2196F3', alpha=0.9)
    
    if taiex is not None:
        ax.plot(taiex.index, taiex, 
                label='TAIEX', 
                linewidth=2, color='#FF6F00', alpha=0.7, linestyle='--')
    
    # Format
    ax.set_xlabel('Date', fontsize=12, fontweight='bold')
    ax.set_ylabel('Portfolio Value (NT$)', fontsize=12, fontweight='bold')
    ax.set_title('ML-Enhanced Trading System Performance Comparison', 
                 fontsize=16, fontweight='bold', pad=20)
    
    # Grid
    ax.grid(True, alpha=0.3, linestyle='--')
    
    # Legend
    ax.legend(loc='upper left', fontsize=11, framealpha=0.9)
    
    # Format y-axis
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'NT${x/1e6:.1f}M'))
    
    # Format x-axis
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.xticks(rotation=45)
    
    # Add annotations
    final_ml = ml_equity.iloc[-1]
    final_orig = original_equity.iloc[-1]
    
    # Calculate returns
    ml_return = (final_ml / INITIAL_CAPITAL - 1) * 100
    orig_return = (final_orig / INITIAL_CAPITAL - 1) * 100
    
    # Add text box
    textstr = f'ML-Enhanced: NT${final_ml/1e6:.2f}M (+{ml_return:.1f}%)\n'
    textstr += f'Original: NT${final_orig/1e6:.2f}M (+{orig_return:.1f}%)\n'
    textstr += f'Improvement: +{ml_return - orig_return:.1f}%'
    
    props = dict(boxstyle='round', facecolor='wheat', alpha=0.8)
    ax.text(0.02, 0.98, textstr, transform=ax.transAxes, fontsize=11,
            verticalalignment='top', bbox=props, family='monospace')
    
    # Tight layout
    plt.tight_layout()
    
    # Save
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    plt.savefig(OUTPUT_PATH, dpi=300, bbox_inches='tight')
    print(f"\n✅ Chart saved to: {OUTPUT_PATH}")
    
    # Show stats
    print(f"\n{'='*80}")
    print("Final Statistics")
    print(f"{'='*80}")
    print(f"ML-Enhanced:  NT${final_ml:,.0f} ({ml_return:+.1f}%)")
    print(f"Original:     NT${final_orig:,.0f} ({orig_return:+.1f}%)")
    print(f"Improvement:  +{ml_return - orig_return:.1f}%")

def main():
    print("="*80)
    print("Performance Visualization")
    print("="*80)
    
    # Run ML strategy
    ml_equity = run_ml_strategy()
    
    # Run original strategy
    original_equity = run_original_strategy()
    
    # Load TAIEX
    start_date = ml_equity.index.min()
    end_date = ml_equity.index.max()
    taiex = load_taiex_data(start_date, end_date)
    
    # Plot
    plot_performance_comparison(ml_equity, original_equity, taiex)
    
    print("\n" + "="*80)
    print("Visualization Complete!")
    print("="*80)

if __name__ == "__main__":
    main()
