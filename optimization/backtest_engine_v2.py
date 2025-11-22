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
# --- Configuration ---
INITIAL_CAPITAL = 1_000_000
MAX_POSITIONS = 10
POSITION_SIZE_PCT = 0.10
RISK_FREE_RATE = 0.02
FEE_RATE = 0.001425  # Discounted fee? User said 0.1% (0.001). Let's stick to user request 0.001
FEE_RATE = 0.001
TAX_RATE = 0.003

def get_tick_size(price):
    """
    Get tick size based on price range (TW Stock Exchange rules).
    """
    if price < 10:
        return 0.01
    elif price < 50:
        return 0.05
    elif price < 100:
        return 0.1
    elif price < 500:
        return 0.5
    elif price < 1000:
        return 1.0
    else:
        return 5.0

def calculate_net_pnl(buy_price, sell_price, shares=1000):
    """
    Calculate Net PnL % considering Slippage, Fee, and Tax.
    Slippage is applied to the prices BEFORE passing to this function? 
    No, let's apply slippage inside the simulation logic.
    Here we just do the fee/tax math.
    
    Net PnL % = (Net Proceeds - Total Cost) / Total Cost
    Total Cost = Buy Price * (1 + Fee)
    Net Proceeds = Sell Price * (1 - Fee - Tax)
    """
    cost = buy_price * (1 + FEE_RATE)
    proceeds = sell_price * (1 - FEE_RATE - TAX_RATE)
    return (proceeds - cost) / cost

def simulate_exit_fixed(high_np, low_np, close_np, date_list, entry_idx, buy_price, stop_price, r_mult=2.0, time_exit=20):
    """
    Simulate a trade exit with Fixed Target (R-multiple) and Time Stop.
    Includes Slippage (1 tick) and Transaction Costs.
    """
    # 1. Apply Slippage to Entry
    entry_tick = get_tick_size(buy_price)
    real_buy_price = buy_price + entry_tick # Buy higher
    
    # Adjust Stop/Target based on REAL buy price? 
    # Usually stop is based on technical level. 
    # If we buy higher, risk increases.
    # Let's assume Stop Price is fixed technical level.
    
    risk = real_buy_price - stop_price
    if risk <= 0: return None
    
    target = real_buy_price + risk * r_mult
    
    # Define path slice
    path_len = len(high_np)
    end_idx = min(entry_idx + time_exit, path_len)
    
    path_high = high_np[entry_idx:end_idx]
    path_low = low_np[entry_idx:end_idx]
    
    # Check hits
    stop_hits = np.where(path_low <= stop_price)[0]
    target_hits = np.where(path_high >= target)[0]
    
    stop_i = stop_hits[0] if stop_hits.size > 0 else np.inf
    target_i = target_hits[0] if target_hits.size > 0 else np.inf
    
    exit_rel_idx = -1
    raw_exit_price = 0.0
    
    if np.isinf(stop_i) and np.isinf(target_i):
        # Time Exit
        exit_rel_idx = (end_idx - entry_idx) - 1
        raw_exit_price = close_np[entry_idx + exit_rel_idx]
    elif stop_i < target_i:
        # Stop Hit
        exit_rel_idx = int(stop_i)
        raw_exit_price = stop_price # Assume filled at stop price (worst case gap handled by low?)
        # If low is much lower than stop, we might fill lower. 
        # For simplicity, use stop price, but apply slippage.
    else:
        # Target Hit
        exit_rel_idx = int(target_i)
        raw_exit_price = target
        
    # 2. Apply Slippage to Exit
    exit_tick = get_tick_size(raw_exit_price)
    real_exit_price = raw_exit_price - exit_tick # Sell lower
    
    # 3. Calculate Net PnL
    pnl = calculate_net_pnl(real_buy_price, real_exit_price)
    
    exit_abs_idx = entry_idx + exit_rel_idx
    
    return {
        'entry_date': date_list[entry_idx],
        'exit_date': date_list[exit_abs_idx],
        'pnl': pnl,
        'duration': exit_rel_idx
    }

def simulate_exit_trailing(high_np, low_np, close_np, ma_np, date_list, entry_idx, buy_price, stop_price, trigger_r=1.5, trail_ma_type='ma20'):
    """
    Simulate a trade exit with Dynamic Trailing Stop.
    Includes Slippage (1 tick) and Transaction Costs.
    """
    # 1. Apply Slippage to Entry
    entry_tick = get_tick_size(buy_price)
    real_buy_price = buy_price + entry_tick
    
    risk = real_buy_price - stop_price
    if risk <= 0: return None
    
    trigger_price = real_buy_price + risk * trigger_r
    current_stop = stop_price
    trailing_active = False
    
    path_high = high_np[entry_idx:]
    path_low = low_np[entry_idx:]
    path_close = close_np[entry_idx:]
    path_ma = ma_np[entry_idx:]
    
    exit_rel_idx = -1
    raw_exit_price = 0.0
    exit_found = False
    
    for k in range(len(path_high)):
        h = path_high[k]
        l = path_low[k]
        m = path_ma[k]
        
        # 1. Check Stop Hit
        if l <= current_stop:
            raw_exit_price = current_stop
            exit_rel_idx = k
            exit_found = True
            break
        
        # 2. Check Trigger
        if not trailing_active and h >= trigger_price:
            trailing_active = True
            current_stop = real_buy_price # Breakeven
        
        # 3. Update Trail
        if trailing_active:
            if not np.isnan(m):
                current_stop = max(current_stop, m)
                
    if not exit_found:
        exit_rel_idx = len(path_high) - 1
        raw_exit_price = path_close[-1]
        
    # 2. Apply Slippage to Exit
    exit_tick = get_tick_size(raw_exit_price)
    real_exit_price = raw_exit_price - exit_tick
    
    # 3. Calculate Net PnL
    pnl = calculate_net_pnl(real_buy_price, real_exit_price)
    
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
