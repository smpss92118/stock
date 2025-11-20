"""
Backtest Engine V2 (Robust)

Extracted from stock/scripts/run_backtest.py
Provides precise trade simulation (path-dependent) and Limited Capital portfolio simulation.
"""

import polars as pl
import numpy as np
import pandas as pd
from datetime import datetime, date

# --- Configuration ---
INITIAL_CAPITAL = 1_000_000
MAX_POSITIONS = 10
POSITION_SIZE_PCT = 0.10
RISK_FREE_RATE = 0.02

def simulate_exit_fixed(high_np, low_np, close_np, date_list, entry_idx, buy_price, stop_price, r_mult=2.0, time_exit=20):
    """
    Simulate a trade exit with Fixed Target (R-multiple) and Time Stop.
    
    Args:
        high_np, low_np, close_np: Price arrays (full history or slice starting from entry)
        date_list: Date list corresponding to arrays
        entry_idx: Index of ENTRY day in the arrays
        buy_price: Entry Price
        stop_price: Initial Stop Price
        r_mult: Target R-multiple (Target = Buy + R * Risk)
        time_exit: Max holding days
        
    Returns:
        dict: {entry_date, exit_date, pnl, duration} or None if data error
    """
    risk = buy_price - stop_price
    if risk <= 0: return None
    
    target = buy_price + risk * r_mult
    
    # Define path slice
    path_len = len(high_np)
    end_idx = min(entry_idx + time_exit, path_len)
    
    # Slice arrays for the holding period
    # Note: We start checking from entry_idx (same day close?) or entry_idx + 1?
    # Usually we assume entry happens during the day. Exit checks start SAME day (intraday) or NEXT day?
    # run_backtest.py checks from entry_abs (which is the day of entry).
    # If we enter on a limit order, we might hit stop/target same day.
    
    path_high = high_np[entry_idx:end_idx]
    path_low = low_np[entry_idx:end_idx]
    
    # Check hits
    # We need to find the FIRST occurrence
    stop_hits = np.where(path_low <= stop_price)[0]
    target_hits = np.where(path_high >= target)[0]
    
    stop_i = stop_hits[0] if stop_hits.size > 0 else np.inf
    target_i = target_hits[0] if target_hits.size > 0 else np.inf
    
    exit_rel_idx = -1
    pnl = 0.0
    
    if np.isinf(stop_i) and np.isinf(target_i):
        # Time Exit
        exit_rel_idx = (end_idx - entry_idx) - 1
        exit_price = close_np[entry_idx + exit_rel_idx]
        pnl = (exit_price - buy_price) / buy_price
    elif stop_i < target_i:
        # Stop Hit
        exit_rel_idx = int(stop_i)
        pnl = (stop_price - buy_price) / buy_price
    else:
        # Target Hit
        exit_rel_idx = int(target_i)
        pnl = (target - buy_price) / buy_price
        
    exit_abs_idx = entry_idx + exit_rel_idx
    
    return {
        'entry_date': date_list[entry_idx],
        'exit_date': date_list[exit_abs_idx],
        'pnl': pnl,
        'duration': exit_rel_idx
    }

def run_capital_simulation_limited(candidates):
    """
    Run portfolio simulation with limited capital (1M, 10 pos).
    Logic copied from run_backtest.py
    """
    if not candidates:
        return []
        
    # Sort by entry date
    candidates.sort(key=lambda x: x['entry_date'])
    
    executed_trades = []
    current_cash = INITIAL_CAPITAL
    active_positions = [] # list of {'exit_date': date, 'cost': float, 'return_cash': float}
    
    for t in candidates:
        today = t['entry_date']
        
        # 1. Release funds
        still_active = []
        for p in active_positions:
            if p['exit_date'] <= today:
                current_cash += p['return_cash']
            else:
                still_active.append(p)
        active_positions = still_active
        
        # 2. Equity
        total_equity = current_cash + sum(p['cost'] for p in active_positions)
        
        # 3. Position Size
        position_size = total_equity * POSITION_SIZE_PCT
        
        # 4. Enter
        if len(active_positions) < MAX_POSITIONS and current_cash >= position_size:
            current_cash -= position_size
            
            profit = position_size * t['pnl']
            return_cash = position_size + profit
            
            active_positions.append({
                'exit_date': t['exit_date'],
                'return_cash': return_cash,
                'cost': position_size
            })
            
            t_record = t.copy()
            t_record['cost'] = position_size
            t_record['profit'] = profit
            executed_trades.append(t_record)
            
    return executed_trades

def calculate_metrics(trades, strategy_name="Strategy"):
    if not trades:
        return None
        
    df = pd.DataFrame(trades)
    
    count = len(df)
    win_rate = (df['pnl'] > 0).mean()
    total_profit = df['profit'].sum()
    
    # Equity Curve
    df['exit_date'] = pd.to_datetime(df['exit_date'])
    df['entry_date'] = pd.to_datetime(df['entry_date'])
    
    daily_pnl = df.groupby('exit_date')['profit'].sum()
    
    min_date = df['entry_date'].min()
    max_date = df['exit_date'].max()
    
    if pd.isna(min_date) or pd.isna(max_date):
        return None
        
    idx = pd.date_range(min_date, max_date)
    equity = pd.Series(0.0, index=idx)
    equity.loc[daily_pnl.index] = daily_pnl
    equity = equity.fillna(0).cumsum() + INITIAL_CAPITAL
    
    final_equity = equity.iloc[-1]
    
    # Drawdown
    roll_max = equity.cummax()
    dd = (equity - roll_max) / roll_max
    max_dd = dd.min()
    
    # Sharpe
    daily_ret = equity.pct_change().fillna(0)
    std = daily_ret.std()
    sharpe = (daily_ret.mean() - (RISK_FREE_RATE/252)) / std * np.sqrt(252) if std > 0 else 0
    
    # Ann Return
    days = (max_date - min_date).days
    ann_ret = (final_equity / INITIAL_CAPITAL) ** (365.25 / days) - 1 if days > 0 else 0
    
    return {
        'ann_return': round(ann_ret * 100, 2),
        'sharpe': round(sharpe, 2),
        'win_rate': round(win_rate * 100, 2),
        'trade_count': count,
        'max_dd': round(max_dd * 100, 2),
        'total_profit': int(total_profit)
    }
