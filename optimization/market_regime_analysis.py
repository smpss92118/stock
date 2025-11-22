#!/usr/bin/env python3
"""
Market Regime Analysis
Analyzes the relationship between market conditions (Uptrend/Downtrend) and signal frequency.
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import polars as pl

# Configuration
DATA_DIR = os.path.join(os.path.dirname(__file__), '../data')
PROCESSED_DIR = os.path.join(DATA_DIR, 'processed')
RAW_DIR = os.path.join(DATA_DIR, 'raw')
OUTPUT_REPORT = os.path.join(PROCESSED_DIR, 'market_regime_analysis.md')
OUTPUT_PLOT = os.path.join(PROCESSED_DIR, 'market_regime_analysis.png')

def load_data():
    """Load signals and market data"""
    print("Loading data...")
    
    # 1. Load Signals (Polars for speed, then convert to pandas)
    signals_path = os.path.join(PROCESSED_DIR, 'pattern_analysis_result.csv')
    if not os.path.exists(signals_path):
        raise FileNotFoundError(f"Signals file not found: {signals_path}")
        
    df_signals = pl.read_csv(signals_path).to_pandas()
    df_signals['date'] = pd.to_datetime(df_signals['date'])
    
    # 2. Load Market Data
    market_path = os.path.join(RAW_DIR, 'market_data.csv')
    if not os.path.exists(market_path):
        # Fallback: Try to find a proxy or use average of stocks?
        # For now, assume it exists as per previous checks
        raise FileNotFoundError(f"Market data file not found: {market_path}")
        
    df_market = pd.read_csv(market_path)
    df_market['date'] = pd.to_datetime(df_market['date'])
    df_market = df_market.sort_values('date').set_index('date')
    
    return df_signals, df_market

def analyze_regime(df_signals, df_market):
    """Analyze signal frequency in different regimes"""
    print("Analyzing regimes...")
    
    # 1. Define Market Regime
    # Calculate MA200 if not present
    if 'market_ma200' not in df_market.columns:
        df_market['market_ma200'] = df_market['close'].rolling(200).mean()
        
    df_market['regime'] = np.where(df_market['close'] > df_market['market_ma200'], 'Bull', 'Bear')
    
    # 2. Count Daily Signals (CORRECTED: Filter for actual patterns first)
    valid_signals = df_signals[
        (df_signals['is_htf'] == True) | 
        (df_signals['is_cup'] == True) | 
        (df_signals['is_vcp'] == True)
    ]
    
    daily_counts = valid_signals.groupby('date').size().reindex(df_market.index, fill_value=0)
    df_market['signal_count'] = daily_counts
    
    # 3. Calculate Stats
    bull_days = df_market[df_market['regime'] == 'Bull']
    bear_days = df_market[df_market['regime'] == 'Bear']
    
    stats = {
        'Total Days': len(df_market),
        'Bull Days': len(bull_days),
        'Bear Days': len(bear_days),
        'Avg Signals (All)': df_market['signal_count'].mean(),
        'Avg Signals (Bull)': bull_days['signal_count'].mean(),
        'Avg Signals (Bear)': bear_days['signal_count'].mean(),
        'Ratio (Bull/Bear)': bull_days['signal_count'].mean() / bear_days['signal_count'].mean() if bear_days['signal_count'].mean() > 0 else np.inf
    }
    
    return df_market, stats

def simulate_exposure(df_signals, df_market, hold_days=10, max_positions=10):
    """Simulate daily exposure with capital constraints"""
    print(f"Simulating exposure (Hold {hold_days} days, Max {max_positions} positions)...")
    
    # Filter valid signals
    valid_signals = df_signals[
        (df_signals['is_htf'] == True) | 
        (df_signals['is_cup'] == True) | 
        (df_signals['is_vcp'] == True)
    ].sort_values('date')
    
    # Group signals by date for faster iteration
    signals_by_date = valid_signals.groupby('date')
    
    # Simulation variables
    active_positions = [] # List of exit dates
    capital_usage = [] # Percentage (0.0 to 1.0)
    
    dates = df_market.index
    
    for current_date in dates:
        # 1. Remove expired positions
        active_positions = [exit_date for exit_date in active_positions if exit_date > current_date]
        
        # 2. Check for new signals
        if current_date in signals_by_date.groups:
            daily_sigs = signals_by_date.get_group(current_date)
            
            # Try to take trades if slots available
            for _ in range(len(daily_sigs)):
                if len(active_positions) < max_positions:
                    # Add new position
                    # Calculate exit date (approximate using business days or just calendar days)
                    # Here we use index-based logic or simple timedelta if index is datetime
                    # Since we iterate dates, we can just add hold_days to current_date if it's valid
                    # But df_market index is datetime.
                    # Let's use simple timedelta for approximation
                    exit_date = current_date + pd.Timedelta(days=hold_days * 1.4) # *1.4 to approx trading days
                    active_positions.append(exit_date)
                else:
                    break # Portfolio full
        
        # 3. Record usage
        usage_pct = len(active_positions) / max_positions
        capital_usage.append(usage_pct * 100) # Store as percentage
            
    df_market['capital_usage'] = capital_usage
    return df_market

def plot_analysis(df_market):
    """Generate visualization"""
    print("Generating plots...")
    
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 18), sharex=True)
    
    # Plot 1: Market Price & Regime
    ax1.plot(df_market.index, df_market['close'], label='Market Index', color='black', linewidth=1)
    ax1.plot(df_market.index, df_market['market_ma200'], label='MA200', color='blue', linestyle='--', alpha=0.7)
    
    # Highlight Bear Markets
    y_min, y_max = ax1.get_ylim()
    ax1.fill_between(df_market.index, y_min, y_max, 
                     where=(df_market['regime'] == 'Bear'), 
                     color='red', alpha=0.1, label='Bear Market')
    
    ax1.set_title('Market Price & Regime (Bear Market Highlighted)', fontsize=14)
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Daily Signal Count
    ax2.bar(df_market.index, df_market['signal_count'], color='green', alpha=0.6, label='Daily Signals')
    # Add rolling average
    ax2.plot(df_market.index, df_market['signal_count'].rolling(20).mean(), color='darkgreen', linewidth=2, label='20-Day Avg')
    
    ax2.set_title('Daily Signal Frequency (Filtered Patterns)', fontsize=14)
    ax2.legend(loc='upper left')
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Capital Usage %
    ax3.plot(df_market.index, df_market['capital_usage'], color='purple', label='Capital Usage % (Max 10 Positions)')
    ax3.fill_between(df_market.index, 0, df_market['capital_usage'], color='purple', alpha=0.2)
    ax3.set_ylim(0, 105)
    ax3.set_ylabel('Usage %')
    
    ax3.set_title('Daily Total Capital Usage % (Simulated)', fontsize=14)
    ax3.legend(loc='upper left')
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(OUTPUT_PLOT)
    print(f"Plot saved to {OUTPUT_PLOT}")

def generate_report(stats, df_market):
    """Generate Markdown report"""
    print("Generating report...")
    
    # Calculate correlation
    corr_price_sig = df_market['close'].corr(df_market['signal_count'])
    corr_regime_sig = (df_market['regime'] == 'Bull').astype(int).corr(df_market['signal_count'])
    
    with open(OUTPUT_REPORT, 'w') as f:
        f.write("# Market Regime Analysis: Why is Sharpe High?\n\n")
        f.write(f"**Generated**: {pd.Timestamp.now()}\n\n")
        
        f.write("## 1. Hypothesis\n")
        f.write("The hypothesis is that the strategy naturally reduces exposure during market downturns (Bear Markets) because fewer breakout signals are generated. This 'natural hedging' mechanism could explain the high Sharpe ratio and low drawdown.\n\n")
        
        f.write("## 2. Statistical Evidence\n\n")
        f.write("| Metric | Value |\n")
        f.write("|---|---|\n")
        f.write(f"| **Total Days Analyzed** | {stats['Total Days']} |\n")
        f.write(f"| **Bull Market Days** | {stats['Bull Days']} ({stats['Bull Days']/stats['Total Days']*100:.1f}%) |\n")
        f.write(f"| **Bear Market Days** | {stats['Bear Days']} ({stats['Bear Days']/stats['Total Days']*100:.1f}%) |\n")
        f.write(f"| **Avg Signals/Day (Bull)** | **{stats['Avg Signals (Bull)']:.2f}** |\n")
        f.write(f"| **Avg Signals/Day (Bear)** | **{stats['Avg Signals (Bear)']:.2f}** |\n")
        f.write(f"| **Bull/Bear Signal Ratio** | **{stats['Ratio (Bull/Bear)']:.1f}x** |\n")
        f.write(f"| **Correlation (Regime vs Signals)** | {corr_regime_sig:.2f} |\n\n")
        
        f.write("## 3. Analysis Findings\n\n")
        
        ratio = stats['Ratio (Bull/Bear)']
        if ratio > 2.0:
            f.write(f"### ✅ Confirmed: Signals Dry Up in Bear Markets\n")
            f.write(f"The data strongly supports the hypothesis. On average, you get **{ratio:.1f} times more signals** in a Bull Market than in a Bear Market.\n\n")
            f.write("- **Bull Market**: High signal frequency leads to full capital deployment.\n")
            f.write("- **Bear Market**: Low signal frequency leads to **cash preservation**. The strategy naturally goes to cash when the market is weak.\n")
        elif ratio > 1.2:
            f.write(f"### ⚠️ Partially Confirmed: Moderate Reduction\n")
            f.write(f"There is a moderate reduction in signals ({ratio:.1f}x), but not a complete dry-up. The strategy still takes some trades in Bear Markets.\n")
        else:
            f.write(f"### ❌ Rejected: No Significant Difference\n")
            f.write(f"The signal frequency is similar in both regimes ({ratio:.1f}x). The high Sharpe ratio likely comes from high win rate or R/R, not exposure management.\n")
            
        f.write("\n## 4. Visual Analysis\n")
        f.write(f"![Market Regime Analysis]({os.path.basename(OUTPUT_PLOT)})\n\n")
        f.write("- **Top Panel**: Market Index (Black) with Bear Markets highlighted in Red.\n")
        f.write("- **Middle Panel**: Daily Signal Count. Notice how the green bars likely diminish in the red zones.\n")
        f.write("- **Bottom Panel**: **Capital Usage %** (Simulated). This shows how fully invested the portfolio is (assuming Max 10 positions). Notice if it drops during Bear Markets.\n")

    print(f"Report saved to {OUTPUT_REPORT}")

def main():
    try:
        df_signals, df_market = load_data()
        df_market, stats = analyze_regime(df_signals, df_market)
        df_market = simulate_exposure(df_signals, df_market)
        plot_analysis(df_market)
        generate_report(stats, df_market)
        print("\nAnalysis Complete!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
