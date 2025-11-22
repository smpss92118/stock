"""
Generate Enhanced Daily Position Report

Replays backtest simulation day-by-day to track:
- Holdings and portfolio metrics
- Capital utilization
- Ignored signals (due to No Pyramiding or insufficient cash)
- Daily P&L and performance

Usage:
    python stock/scripts/generate_daily_position_report.py
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

# Add project root to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from scripts.run_backtest import (
    load_data_polars,
    generate_trade_candidates,
    INITIAL_CAPITAL,
    MAX_POSITIONS,
    POSITION_SIZE_PCT
)

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), '../data/processed/daily_position_report.csv')

def replay_simulation_with_tracking(candidates, df_polars):
    """
    Day-by-day simulation replay with detailed tracking
    
    Note: No Pyramiding restriction REMOVED - same stock can have multiple positions
    
    Returns:
        list of daily reports with metrics
    """
    print("\n" + "="*80)
    print("Starting Day-by-Day Simulation Replay")
    print("="*80)
    
    # Convert to pandas for easier lookup
    df_pd = df_polars.to_pandas()
    df_pd['date'] = pd.to_datetime(df_pd['date'])
    
    # Create price lookup: {(sid, date): close}
    price_map = df_pd.set_index(['sid', 'date'])['close'].to_dict()
    
    # Group candidates by entry date
    df_cand = pd.DataFrame(candidates)
    df_cand['entry_date'] = pd.to_datetime(df_cand['entry_date'])
    df_cand['exit_date'] = pd.to_datetime(df_cand['exit_date'])
    
    # Get all unique dates
    all_dates = sorted(df_cand['entry_date'].unique())
    if not all_dates:
        return []
    
    min_date = min(all_dates)
    max_date = df_cand['exit_date'].max()
    date_range = pd.date_range(min_date, max_date)
    
    print(f"Simulation period: {min_date.date()} to {max_date.date()}")
    print(f"Total days: {len(date_range)}")
    print(f"Total candidates: {len(df_cand)}\n")
    
    # Initialize state
    current_cash = INITIAL_CAPITAL
    active_positions = []  # list of {sid, entry_date, buy_price, exit_date, cost}
    daily_reports = []
    
    for current_date in date_range:
        # 1. Process Exits
        exits = []
        positions_to_remove = []
        
        for pos in active_positions:
            if pos['exit_date'] <= current_date:
                # Calculate exit value
                exit_return = pos['cost'] * (1 + pos['pnl'])
                current_cash += exit_return
                
                exits.append({
                    'sid': pos['sid'],
                    'entry_price': pos['buy_price'],
                    'exit_price': round(pos['buy_price'] * (1 + pos['pnl']), 2),
                    'pnl_pct': round(pos['pnl'] * 100, 2),
                    'days_held': (pos['exit_date'] - pos['entry_date']).days
                })
                positions_to_remove.append(pos)
        
        for pos in positions_to_remove:
            active_positions.remove(pos)
        
        # 2. Get today's candidate signals
        today_candidates = df_cand[df_cand['entry_date'] == current_date].to_dict('records')
        
        # 3. Process Entries (NO Pyramiding restriction - allow same stock multiple times)
        entries = []
        ignored_signals = []
        
        for cand in today_candidates:
            sid = cand['sid']
            
            # Only check: position limit and cash availability
            # REMOVED: No Pyramiding check
            
            # Check position limit
            if len(active_positions) >= MAX_POSITIONS:
                ignored_signals.append({
                    'sid': sid,
                    'reason': 'max_positions',
                    'buy_price': cand['buy_price']
                })
                continue
            
            # Calculate position size
            total_equity = current_cash + sum(p['cost'] for p in active_positions)
            position_size = total_equity * POSITION_SIZE_PCT
            
            # Check cash
            if current_cash < position_size:
                ignored_signals.append({
                    'sid': sid,
                    'reason': 'insufficient_cash',
                    'buy_price': cand['buy_price']
                })
                continue
            
            # Enter position
            current_cash -= position_size
            active_positions.append({
                'sid': sid,
                'entry_date': cand['entry_date'],
                'buy_price': cand['buy_price'],
                'exit_date': cand['exit_date'],
                'pnl': cand['pnl'],
                'cost': position_size
            })
            
            entries.append({
                'sid': sid,
                'buy_price': cand['buy_price'],
                'position_size': position_size
            })
        
        # 4. Calculate current portfolio value
        holdings_details = []
        total_holdings_value = 0
        
        for pos in active_positions:
            current_price = price_map.get((pos['sid'], current_date), np.nan)
            if pd.notna(current_price):
                current_value = pos['cost'] * (current_price / pos['buy_price'])
                unrealized_pnl_pct = (current_price / pos['buy_price'] - 1) * 100
            else:
                current_value = pos['cost']
                unrealized_pnl_pct = 0
            
            total_holdings_value += current_value
            days_held = (current_date - pos['entry_date']).days
            
            holdings_details.append({
                'sid': pos['sid'],
                'entry_date': pos['entry_date'].strftime('%Y-%m-%d'),
                'buy_price': round(pos['buy_price'], 2),
                'current_price': round(current_price, 2) if pd.notna(current_price) else 'N/A',
                'unrealized_pnl_pct': round(unrealized_pnl_pct, 2),
                'position_value': round(current_value, 0),
                'days_held': days_held
            })
        
        total_equity = current_cash + total_holdings_value
        
        # 5. Calculate metrics
        position_utilization = len(active_positions) / MAX_POSITIONS * 100
        cash_invested = sum(p['cost'] for p in active_positions)
        capital_utilization = cash_invested / INITIAL_CAPITAL * 100
        cumulative_return = (total_equity / INITIAL_CAPITAL - 1) * 100
        
        # 6. Save daily report (only if there's activity or holdings)
        if holdings_details or entries or exits or ignored_signals:
            daily_reports.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'total_positions': len(active_positions),
                'max_positions': MAX_POSITIONS,
                'position_utilization_pct': round(position_utilization, 1),
                'cash_available': round(current_cash, 0),
                'cash_invested': round(cash_invested, 0),
                'capital_utilization_pct': round(capital_utilization, 1),
                'total_equity': round(total_equity, 0),
                'cumulative_return_pct': round(cumulative_return, 2),
                'new_entries_count': len(entries),
                'exits_count': len(exits),
                'signals_ignored_count': len(ignored_signals),
                'holdings': str(holdings_details),
                'new_entries': str(entries),
                'exits': str(exits),
                'signals_ignored': str(ignored_signals)
            })
    
    print(f"\n✅ Generated {len(daily_reports)} daily reports")
    return daily_reports

def main():
    print("="*80)
    print("Enhanced Daily Position Report Generator")
    print("="*80)
    
    # 1. Load Data
    df_polars = load_data_polars()
    if df_polars is None:
        print("❌ Failed to load data")
        return
    
    # 2. Generate trade candidates (CUP Fixed R=2, T=20)
    strategy = 'is_cup'
    exit_mode = 'fixed'
    params = {'r_mult': 2.0, 'time_exit': 20}
    
    print(f"\nGenerating candidates: {strategy} ({exit_mode} {params})...")
    candidates = generate_trade_candidates(df_polars, strategy, exit_mode, params)
    
    if not candidates:
        print("❌ No candidates generated")
        return
    
    print(f"✅ Generated {len(candidates)} trade candidates")
    
    # 3. Replay simulation day-by-day
    daily_reports = replay_simulation_with_tracking(candidates, df_polars)
    
    if not daily_reports:
        print("❌ No daily reports generated")
        return
    
    # 4. Save to CSV
    df_report = pd.DataFrame(daily_reports)
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    df_report.to_csv(OUTPUT_FILE, index=False)
    
    print(f"\n✅ Report saved to: {OUTPUT_FILE}")
    
    # 5. Print summary statistics
    print("\n" + "="*80)
    print("SUMMARY STATISTICS")
    print("="*80)
    print(f"Average Position Utilization: {df_report['position_utilization_pct'].mean():.1f}%")
    print(f"Average Capital Utilization: {df_report['capital_utilization_pct'].mean():.1f}%")
    print(f"Total Entries: {df_report['new_entries_count'].sum()}")
    print(f"Total Exits: {df_report['exits_count'].sum()}")
    print(f"Total Signals Ignored: {df_report['signals_ignored_count'].sum()}")
    
    if df_report['signals_ignored_count'].sum() > 0:
        total_signals = df_report['new_entries_count'].sum() + df_report['signals_ignored_count'].sum()
        ignore_rate = df_report['signals_ignored_count'].sum() / total_signals * 100
        print(f"Signal Ignore Rate: {ignore_rate:.1f}%")
    
    print(f"\nFinal Equity: ${df_report.iloc[-1]['total_equity']:,.0f}")
    print(f"Total Return: {df_report.iloc[-1]['cumulative_return_pct']:.2f}%")
    
    # 6. Print sample
    print("\n" + "="*80)
    print("SAMPLE (Last 5 Days)")
    print("="*80)
    cols_to_show = ['date', 'total_positions', 'position_utilization_pct', 
                    'capital_utilization_pct', 'new_entries_count', 'exits_count', 
                    'signals_ignored_count', 'cumulative_return_pct']
    print(df_report[cols_to_show].tail(5).to_string(index=False))

if __name__ == "__main__":
    main()
