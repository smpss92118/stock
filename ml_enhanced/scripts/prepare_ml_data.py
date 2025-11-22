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
import pickle
from datetime import datetime, timedelta

# Add paths
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

# Import original data loader
from scripts.run_backtest import load_data_polars, generate_trade_candidates

# Import shared modules
from src.utils.logger import setup_logger
from src.ml.features import calculate_technical_indicators, extract_ml_features
from src.data.institutional import load_institutional_raw, compute_institutional_features

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


def apply_group_zscore(df, cols, group_key='sid'):
    """
    以 group_key 分組，對指定欄位做「前值」的 expanding mean/std z-score，避免洩漏當日。
    當 std=0 或不足資料時補 0。
    """
    for col in cols:
        if col not in df.columns:
            df[col] = np.nan
        mean = df.groupby(group_key)[col].transform(lambda x: x.shift(1).expanding().mean())
        std = df.groupby(group_key)[col].transform(lambda x: x.shift(1).expanding().std(ddof=0))
        df[col] = (df[col] - mean) / std.replace(0, np.nan)
    df[cols] = df[cols].fillna(0)
    return df

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

def generate_catboost_data(df, output_path):
    """
    Generate expanded dataset for CatBoost Global Model.
    Features:
    - All technical indicators
    - pattern_type (Categorical)
    - exit_mode (Categorical)
    - efficiency_score (Target)
    - label (Target Class)
    """
    logger.info("Generating CatBoost Global Model Data...")
    
    # Define exit modes to simulate
    exit_modes = [
        {'name': 'fixed_r2_t20', 'type': 'fixed', 'r_mult': 2.0, 'time_exit': 20},
        {'name': 'fixed_r3_t20', 'type': 'fixed', 'r_mult': 3.0, 'time_exit': 20},
        {'name': 'trailing_15r', 'type': 'trailing', 'trigger_r': 1.5}
    ]
    
    expanded_rows = []
    
    # Ensure MA20 exists
    if 'ma20' not in df.columns:
        df['ma20'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(20).mean())
        
    # Partition by SID
    df_groups = dict(tuple(df.groupby('sid')))
    
    # Iterate over all patterns
    patterns = ['cup', 'htf', 'vcp']
    
    for pattern in patterns:
        pat_col = f'is_{pattern}'
        buy_col = f'{pattern}_buy_price'
        stop_col = f'{pattern}_stop_price'
        
        if pat_col not in df.columns: continue
        
        signals = df[
            (df[pat_col] == True) & 
            (df[buy_col].notna()) & 
            (df[stop_col].notna())
        ].copy()
        
        for idx, signal in signals.iterrows():
            sid = signal['sid']
            signal_date = signal['date']
            buy_price = signal[buy_col]
            stop_price = signal[stop_col]
            
            if sid not in df_groups: continue
            stock_df = df_groups[sid]
            
            # Get simulation data
            sim_data = stock_df[stock_df['date'] >= signal_date]
            if len(sim_data) < 2: continue # Need at least 2 days
            
            # Find entry (limit buy)
            # Note: reusing logic from generate_labels, but simplified
            # Assuming entry at buy_price if high >= buy_price in next 30 days
            future_30 = sim_data.iloc[1:31] # Next 30 days
            if len(future_30) == 0: continue
            
            entry_candidates = future_30[future_30['high'] >= buy_price]
            if len(entry_candidates) == 0: continue
            
            entry_idx = sim_data.index.get_loc(entry_candidates.index[0])
            sim_data_entry = sim_data.iloc[entry_idx:]
            
            high_np = sim_data_entry['high'].values
            low_np = sim_data_entry['low'].values
            close_np = sim_data_entry['close'].values
            ma_np = sim_data_entry['ma20'].values
            
            # Simulate each exit mode
            for mode in exit_modes:
                if mode['type'] == 'fixed':
                    pnl, duration = simulate_trade_fixed(
                        high_np, low_np, close_np, buy_price, stop_price,
                        r_mult=mode['r_mult'], time_exit=mode['time_exit']
                    )
                else:
                    pnl, duration = simulate_trade_trailing(
                        high_np, low_np, close_np, ma_np, buy_price, stop_price,
                        trigger_r=mode['trigger_r']
                    )
                
                # Calculate Score
                profit_pct = pnl * 100
                score = profit_pct / duration if duration > 0 else 0
                
                # Create row
                row = signal.copy()
                row['pattern_type'] = pattern.upper()
                row['exit_mode'] = mode['name']
                row['profit_pct'] = profit_pct
                row['holding_days'] = duration
                row['efficiency_score'] = score
                
                expanded_rows.append(row)
                
    if not expanded_rows:
        logger.warning("No expanded rows generated for CatBoost")
        return
        
    res_df = pd.DataFrame(expanded_rows)
    
    # Assign Labels (Quartiles)
    # Calculate quartiles on the entire dataset
    q25 = res_df['efficiency_score'].quantile(0.25)
    q50 = res_df['efficiency_score'].quantile(0.50)
    q75 = res_df['efficiency_score'].quantile(0.75)
    
    logger.info(f"Global Score Quartiles: Q25={q25:.2f}, Q50={q50:.2f}, Q75={q75:.2f}")
    
    def get_label(s):
        if s >= q75: return 3 # A
        elif s >= q50: return 2 # B
        elif s >= q25: return 1 # C
        else: return 0 # D
        
    res_df['label'] = res_df['efficiency_score'].apply(get_label)
    
    # Add Group ID for YetiRank (Date as integer)
    res_df['group_id'] = res_df['date'].dt.strftime('%Y%m%d').astype(int)
    
    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Drop unnecessary columns to save space/confusion
    # Keep features + targets + identifiers
    # We can reuse extract_ml_features logic or just keep what's in df
    # But df has many raw columns.
    # Let's keep everything for now, but ensure we know what the features are.
    
    res_df.to_csv(output_path, index=False)
    logger.info(f"✅ Saved CatBoost data to {output_path} ({len(res_df)} rows)")
    
    # Save feature info for CatBoost
    # Exclude targets and identifiers
    exclude = ['sid', 'date', 'profit_pct', 'holding_days', 'efficiency_score', 'label', 
               'actual_return', 'is_winner', 'pattern_type', 'exit_mode'] 
               # pattern_type and exit_mode are FEATURES but handled as cat_features
    
    # Identify numeric features from the original df columns
    # We can reuse the feature list from extract_ml_features if possible, 
    # or just take all numeric columns except excluded.
    
    numeric_cols = res_df.select_dtypes(include=[np.number]).columns.tolist()
    feature_cols = [c for c in numeric_cols if c not in exclude and not c.startswith('is_') and not c.endswith('_price')]
    
    # Add back specific features if they were excluded by type
    # Actually, pattern_type and exit_mode ARE features.
    
    cat_features = ['pattern_type', 'exit_mode']
    final_features = feature_cols + cat_features
    
    info = {
        'feature_cols': final_features,
        'cat_features': cat_features,
        'quartiles': {'q25': q25, 'q50': q50, 'q75': q75}
    }
    
    info_path = os.path.abspath(os.path.join(os.path.dirname(output_path), '../models/catboost_feature_info.pkl'))
    os.makedirs(os.path.dirname(info_path), exist_ok=True)
    with open(info_path, 'wb') as f:
        pickle.dump(info, f)
    logger.info(f"✅ Saved CatBoost feature info to {info_path}")



# ============================================================================
# 新增：給 CatBoost 使用的全局標籤生成函數 (P2 實現)
# ============================================================================

def generate_catboost_global_features(df, output_path):
    """
    為 CatBoost 全局模型生成擴展資料集

    關鍵特性 (P0+P1+P2):
    1. P0: 所有信號和出場模式放在一個大 DataFrame (全局模型)
    2. 使用統一的四分位數計算 ABCD 標籤 (不是按 pattern × exit 分別計算)
    3. 整合樣本權重信息用於後續的加權訓練

    Args:
        df: 完整的原始資料 DataFrame
        output_path: 輸出檔案路徑

    Output:
        catboost_features.csv: 包含所有特徵、標籤、權重信息的資料集
    """
    logger.info("\n" + "="*80)
    logger.info("Generating CatBoost Global Model Features (P0+P1+P2)")
    logger.info("="*80)

    # 定義出場模式
    exit_modes = [
        {'name': 'fixed_r2_t20', 'type': 'fixed', 'r_mult': 2.0, 'time_exit': 20},
        {'name': 'fixed_r3_t20', 'type': 'fixed', 'r_mult': 3.0, 'time_exit': 20},
        {'name': 'trailing_15r', 'type': 'trailing', 'trigger_r': 1.5}
    ]

    expanded_rows = []

    # 確保 MA20 存在
    if 'ma20' not in df.columns:
        df['ma20'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(20).mean())

    # 按 SID 分組以加速
    df_groups = dict(tuple(df.groupby('sid')))

    # 遍歷所有模式和信號
    for pattern in ['cup', 'htf', 'vcp']:
        logger.info(f"\n  Processing {pattern.upper()}...")

        pat_col = f'is_{pattern}'
        buy_col = f'{pattern}_buy_price'
        stop_col = f'{pattern}_stop_price'

        if pat_col not in df.columns:
            continue

        # 篩選該模式的信號
        signals = df[
            (df[pat_col] == True) &
            (df[buy_col].notna()) &
            (df[stop_col].notna())
        ].copy()

        logger.info(f"    Found {len(signals)} signals")

        for idx, signal in signals.iterrows():
            sid = signal['sid']
            signal_date = signal['date']
            buy_price = signal[buy_col]
            stop_price = signal[stop_col]

            if sid not in df_groups:
                continue

            stock_df = df_groups[sid]

            # 獲取信號後的資料
            sim_data = stock_df[stock_df['date'] >= signal_date]
            if len(sim_data) < 2:
                continue

            # 尋找進場點 (limit buy within 30 days)
            future_30 = sim_data.iloc[1:31]
            if len(future_30) == 0:
                continue

            entry_candidates = future_30[future_30['high'] >= buy_price]
            if len(entry_candidates) == 0:
                continue

            entry_idx = sim_data.index.get_loc(entry_candidates.index[0])
            sim_data_entry = sim_data.iloc[entry_idx:]

            high_np = sim_data_entry['high'].values
            low_np = sim_data_entry['low'].values
            close_np = sim_data_entry['close'].values
            ma_np = sim_data_entry['ma20'].values

            # 模擬每個出場模式
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

                # 計算分數
                score = (pnl * 100) / duration

                # 建立行
                row = signal.copy()
                row['pattern_type'] = pattern.upper()
                row['exit_mode'] = mode['name']
                row['actual_return'] = pnl
                row['duration'] = duration
                row['efficiency_score'] = score

                expanded_rows.append(row)

    if not expanded_rows:
        logger.error("✗ No expanded rows generated!")
        return

    res_df = pd.DataFrame(expanded_rows)
    logger.info(f"\n✓ Generated {len(res_df)} expanded rows (signal × exit_mode)")

    # ========== P2: 全局標籤分配 ==========
    # 關鍵: 使用統一的四分位數計算所有信號的標籤
    # (而不是按 pattern × exit_mode 分別計算)

    logger.info("\nAssigning global labels (P2)...")

    q25 = res_df['efficiency_score'].quantile(0.25)
    q50 = res_df['efficiency_score'].quantile(0.50)
    q75 = res_df['efficiency_score'].quantile(0.75)

    logger.info(f"  Global Quartiles: Q25={q25:.2f}, Q50={q50:.2f}, Q75={q75:.2f}")

    def get_label(s):
        if s >= q75:
            return 3  # A
        elif s >= q50:
            return 2  # B
        elif s >= q25:
            return 1  # C
        else:
            return 0  # D

    res_df['label_int'] = res_df['efficiency_score'].apply(get_label)

    # 也添加 ABCD 標籤供參考
    label_map = {0: 'D', 1: 'C', 2: 'B', 3: 'A'}
    res_df['label_abcd'] = res_df['label_int'].map(label_map)

    # 計算 is_winner (用於回測)
    res_df['is_winner'] = (res_df['label_int'] >= 2).astype(int)

    # 添加 group_id (用於 YetiRank，日期作為 group)
    res_df['group_id'] = res_df['date'].dt.strftime('%Y%m%d').astype(int)

    # 統計
    logger.info(f"\n  標籤分佈:")
    for label_val, label_char in label_map.items():
        count = (res_df['label_int'] == label_val).sum()
        pct = count / len(res_df) * 100
        logger.info(f"    {label_char}: {count:5d} ({pct:5.1f}%)")

    # 保存資料
    logger.info(f"\nSaving CatBoost features to {output_path}...")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    res_df.to_csv(output_path, index=False)
    logger.info(f"✓ Saved {len(res_df)} rows")

    # 保存特徵信息
    exclude_cols = {
        'sid', 'date', 'volume', 'open', 'high', 'low', 'close',
        'actual_return', 'duration', 'efficiency_score',
        'label_int', 'label_abcd', 'is_winner', 'group_id',
        'name', 'code', 'dd', 'exchange'  # 排除股票代碼、名稱、時間衰減、交易所
    }
    exclude_cols.update({c for c in res_df.columns if c.startswith('is_')})
    exclude_cols.update({c for c in res_df.columns if c.endswith('_price')})
    exclude_cols.update({c for c in res_df.columns if c.endswith('_days')})
    exclude_cols.update({c for c in res_df.columns if c.endswith('_grade')})
    exclude_cols.update({c for c in res_df.columns if c.endswith('_buy_price')})
    exclude_cols.update({c for c in res_df.columns if c.endswith('_stop_price')})
    # 排除信號相關的 R 倍數和停止點距離 (改用百分比距離)
    exclude_cols.update({c for c in res_df.columns if '_2R' in c or '_3R' in c or '_4R' in c or c.endswith('_stop')})

    # 只保留數值型特徵（除了類別特徵）
    feature_cols = [c for c in res_df.columns
                   if c not in exclude_cols and pd.api.types.is_numeric_dtype(res_df[c])]

    cat_features = ['pattern_type', 'exit_mode']
    numeric_features = [c for c in feature_cols if c not in cat_features]

    info = {
        'feature_cols': feature_cols,
        'numeric_features': numeric_features,
        'cat_features': cat_features,
        'n_features': len(feature_cols),
        'n_samples': len(res_df),
        'quartiles': {'q25': q25, 'q50': q50, 'q75': q75},
        'label_distribution': dict(res_df['label_int'].value_counts().sort_index()),
    }

    info_path = os.path.join(os.path.dirname(output_path), '../models/catboost_feature_info.pkl')
    os.makedirs(os.path.dirname(info_path), exist_ok=True)
    with open(info_path, 'wb') as f:
        pickle.dump(info, f)

    logger.info(f"✓ Saved feature info to {info_path}")
    logger.info(f"  Total features: {len(feature_cols)}")
    logger.info(f"    Numeric: {len(numeric_features)}")
    logger.info(f"    Categorical: {len(cat_features)}")


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
    # Ensure merge keys are aligned
    df_pd['sid'] = df_pd['sid'].astype(str)
    df_pd['date'] = pd.to_datetime(df_pd['date'])
    if 'volume' not in df_pd.columns:
        logger.error("❌ volume column missing in pattern_analysis_result.csv. Regenerate it with run_historical_analysis.py.")
        return
    if df_pd['volume'].isna().all():
        logger.error("❌ volume column is empty. Check data extraction before ML prep.")
        return
    
    # Merge institutional flows (use only past data to avoid leakage)
    inst_raw = load_institutional_raw()
    inst_feature_cols = [
        'foreign_net_lag1',
        'investment_net_lag1',
        'dealer_net_lag1',
        'total_net_lag1',
        'foreign_net_sum_3d',
        'foreign_net_sum_5d',
        'foreign_net_sum_10d',
        'foreign_net_sum_20d',
        'total_net_sum_3d',
        'total_net_sum_5d',
        'total_net_sum_10d',
        'total_net_sum_20d',
        'foreign_investment_spread_lag1',
        'dealer_dominance_lag1',
        'foreign_net_to_vol_lag1',
        'total_net_to_vol_lag1'
    ]
    if inst_raw is None or inst_raw.empty:
        logger.warning("⚠️ No institutional data found; continuing without new features.")
        for col in inst_feature_cols:
            df_pd[col] = 0
    else:
        logger.info("Merging institutional flow features (lagged/rolling only)...")
        inst_feat_df = compute_institutional_features(inst_raw)
        inst_feat_df['sid'] = inst_feat_df['sid'].astype(str)
        inst_feat_df['date'] = pd.to_datetime(inst_feat_df['date'])
        df_pd = df_pd.merge(inst_feat_df, on=['sid', 'date'], how='left')
        
        # Compute ratios vs volume using lagged flows
        volume_safe = df_pd['volume'].replace(0, np.nan)
        df_pd['foreign_net_to_vol_lag1'] = df_pd['foreign_net_lag1'] / volume_safe
        df_pd['total_net_to_vol_lag1'] = df_pd['total_net_lag1'] / volume_safe
        
        # Fill missing institutional features with median (per column)
        for col in inst_feature_cols:
            if col not in df_pd.columns:
                df_pd[col] = np.nan
        median_fill = df_pd[inst_feature_cols].median()
        df_pd[inst_feature_cols] = df_pd[inst_feature_cols].fillna(median_fill)
    
    # Calculate technical indicators
    logger.info("Calculating technical indicators for all stocks...")
    # Use group_keys=False to avoid FutureWarning while keeping all columns
    df_pd = df_pd.groupby('sid', group_keys=False).apply(lambda x: calculate_technical_indicators(x)).reset_index(drop=True)

    # Apply z-score to drift-heavy columns (per sid, using only past data via shift(1))
    drift_cols = [
        'foreign_net_sum_3d', 'foreign_net_sum_5d', 'foreign_net_sum_10d', 'foreign_net_sum_20d',
        'total_net_sum_3d', 'total_net_sum_5d', 'total_net_sum_10d', 'total_net_sum_20d',
        'volatility', 'atr_ratio', 'price_vs_ma20', 'price_vs_ma50',
        'volume_ratio_ma20', 'volume_ratio_ma50',
        'momentum_5d', 'momentum_20d', 'rsi_14'
    ]
    logger.info("Applying per-sid z-score to drift-prone features...")
    df_pd = apply_group_zscore(df_pd, drift_cols, group_key='sid')
    
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
    # This section is now handled by generate_catboost_data for the global model
    # The original intent was to generate features for a general model, but it's now specific to CatBoost.
    # Keeping the structure for clarity, but the actual feature generation is moved.
    
    # 1. Generate features for the general ML model (if any, currently handled by CatBoost function)
    # This part of the code was refactored into generate_catboost_data
    
    # 2. Generate CatBoost Data (Global Model with P0+P1+P2)
    CATBOOST_OUTPUT = os.path.join(os.path.dirname(__file__), '../../catboost_enhanced/data/catboost_features.csv')
    generate_catboost_global_features(df_pd, CATBOOST_OUTPUT)
    
    logger.info("✅ ML Data Preparation Complete!")

if __name__ == "__main__":
    main()
