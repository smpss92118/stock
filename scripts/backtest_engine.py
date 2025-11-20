"""
Backtest Engine for Limited Capital Simulation

Extracted and optimized from run_backtest.py.
Focuses solely on 'Limited Capital' mode (Fixed Initial Capital, Max Positions).
"""

import pandas as pd
import numpy as np
from datetime import datetime

# --- Configuration ---
INITIAL_CAPITAL = 1_000_000
MAX_POSITIONS = 10
POSITION_SIZE_PCT = 0.10  # 10% per trade
RISK_FREE_RATE = 0.02

def run_capital_simulation_limited(candidates):
    """
    Run portfolio simulation with limited capital and max positions.
    
    Args:
        candidates: List of dicts with {'entry_date', 'exit_date', 'pnl', ...}
        
    Returns:
        List of executed trades (dicts)
    """
    if not candidates:
        return []
        
    # Sort by entry date (FIFO)
    # Ensure dates are comparable (all date objects or all timestamps)
    # We assume they are normalized before passing here, but let's be safe
    candidates.sort(key=lambda x: x['entry_date'])
    
    executed_trades = []
    current_cash = INITIAL_CAPITAL
    active_positions = [] # list of {'exit_date': date, 'cost': float, 'return_cash': float}
    
    # We need to iterate through time or through candidates.
    # Iterating through candidates is faster if sparse.
    
    for t in candidates:
        today = t['entry_date']
        
        # 1. Release funds from expired positions (exit_date <= today)
        # Note: In real trading, funds might settle T+2, here we assume T+0 or T+1 available for next trade
        # We assume if exit_date <= today, it means we exited BEFORE this new entry.
        # (If exit_date == today, we exited at open/close and entering now? 
        #  Conservatively, let's say funds return NEXT day. But for simplicity, same day is fine if we assume exit at Open, entry at Close?)
        # Let's stick to: if exit_date <= today, funds are back.
        
        still_active = []
        for p in active_positions:
            if p['exit_date'] <= today:
                current_cash += p['return_cash']
            else:
                still_active.append(p)
        active_positions = still_active
        
        # 2. Calculate Current Total Equity
        # Equity = Cash + Cost of Active Positions (Book Value)
        # We don't mark-to-market daily here for speed, just use Cost.
        total_equity = current_cash + sum(p['cost'] for p in active_positions)
        
        # 3. Calculate Position Size (10% of Current Equity)
        position_size = total_equity * POSITION_SIZE_PCT
        
        # 4. Try to Enter
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
            t_record['equity_at_entry'] = total_equity
            executed_trades.append(t_record)
            
    return executed_trades


def calculate_portfolio_metrics(trades, strategy_name="Strategy"):
    """
    Calculate Annualized Return, Sharpe, etc. from executed trades.
    """
    if not trades:
        return {
            'ann_return': 0.0,
            'sharpe': 0.0,
            'win_rate': 0.0,
            'trade_count': 0,
            'max_dd': 0.0
        }
        
    df = pd.DataFrame(trades)
    
    # Basic Stats
    count = len(df)
    win_rate = (df['pnl'] > 0).mean()
    total_profit = df['profit'].sum()
    
    # Equity Curve Construction
    # We need a daily equity curve for Sharpe and MaxDD
    df['exit_date'] = pd.to_datetime(df['exit_date'])
    df['entry_date'] = pd.to_datetime(df['entry_date'])
    
    min_date = df['entry_date'].min()
    max_date = df['exit_date'].max()
    
    if pd.isna(min_date) or pd.isna(max_date):
        return {'ann_return': 0, 'sharpe': 0, 'win_rate': 0, 'trade_count': 0, 'max_dd': 0}
        
    # Create daily index
    idx = pd.date_range(min_date, max_date)
    daily_pnl = df.groupby('exit_date')['profit'].sum()
    
    equity = pd.Series(0.0, index=idx)
    equity.loc[daily_pnl.index] = daily_pnl
    equity = equity.fillna(0).cumsum() + INITIAL_CAPITAL
    
    final_equity = equity.iloc[-1]
    
    # Annualized Return
    days = (max_date - min_date).days
    if days > 0:
        years = days / 365.25
        ann_ret = (final_equity / INITIAL_CAPITAL) ** (1 / years) - 1
    else:
        ann_ret = 0
        
    # Sharpe Ratio
    daily_ret = equity.pct_change().fillna(0)
    std = daily_ret.std()
    if std == 0:
        sharpe = 0
    else:
        sharpe = (daily_ret.mean() - (RISK_FREE_RATE/252)) / std * np.sqrt(252)
        
    # Max Drawdown
    roll_max = equity.cummax()
    dd = (equity - roll_max) / roll_max
    max_dd = dd.min()
    
    return {
        'ann_return': round(ann_ret * 100, 2),
        'sharpe': round(sharpe, 2),
        'win_rate': round(win_rate * 100, 2),
        'trade_count': count,
        'max_dd': round(max_dd * 100, 2)
    }
