"""
Daily CatBoost Scanner

功能：
1. 載入 Global CatBoost Model
2. 讀取每日 Pattern 掃描結果
3. 為每個訊號生成多種 Exit Mode 的預測輸入
4. 預測 Efficiency Label (A/B/C/D) 與機率
5. 生成獨立報告 (CatBoost Enhanced Report)
"""
import pandas as pd
import numpy as np
import os
import sys
import pickle
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.utils.logger import setup_logger
from src.ml.features import extract_ml_features

from src.ml.features import calculate_technical_indicators
from src.data.institutional import load_institutional_raw, compute_institutional_features

try:
    from catboost import CatBoostClassifier
except ImportError:
    print("❌ CatBoost not installed")
    sys.exit(1)

# Configuration
MODEL_DIR = os.path.join(os.path.dirname(__file__), '../models')
MODEL_PATH = os.path.join(MODEL_DIR, 'global_catboost.cbm')
FEATURE_INFO_PATH = os.path.join(MODEL_DIR, 'catboost_feature_info.pkl')
PATTERN_FILE = os.path.join(os.path.dirname(__file__), '../../data/processed/pattern_analysis_result.csv')
STOCK_INFO_FILE = os.path.join(os.path.dirname(__file__), '../../data/raw/2023_2025_daily_stock_info.csv')
REPORT_FILE = os.path.join(os.path.dirname(__file__), '../results/daily_catboost_report.md')

logger = setup_logger('catboost_scan')

def load_model():
    if not os.path.exists(MODEL_PATH):
        logger.error(f"❌ Model not found: {MODEL_PATH}")
        return None, None
        
    model = CatBoostClassifier()
    model.load_model(MODEL_PATH)
    logger.info("✅ Global CatBoost model loaded")
    
    if not os.path.exists(FEATURE_INFO_PATH):
        logger.error(f"❌ Feature info not found: {FEATURE_INFO_PATH}")
        return None, None

    with open(FEATURE_INFO_PATH, 'rb') as f:
        info = pickle.load(f)
        
    return model, info

def apply_group_zscore(df, cols, group_key='sid'):
    """Same as in prepare_ml_data.py"""
    for col in cols:
        if col not in df.columns:
            df[col] = np.nan
        mean = df.groupby(group_key)[col].transform(lambda x: x.shift(1).expanding().mean())
        std = df.groupby(group_key)[col].transform(lambda x: x.shift(1).expanding().std(ddof=0))
        df[col] = (df[col] - mean) / std.replace(0, np.nan)
    df[cols] = df[cols].fillna(0)
    return df

def scan_latest():
    logger.info("Starting Daily CatBoost Scan...")
    
    # 1. Load Model
    model, info = load_model()
    if model is None: return
    
    feature_cols = info['feature_cols']
    
    # 2. Load Latest Pattern Data
    if not os.path.exists(PATTERN_FILE):
        logger.error("❌ Pattern data not found")
        return
        
    df_pattern = pd.read_csv(PATTERN_FILE)
    df_pattern['date'] = pd.to_datetime(df_pattern['date'])
    latest_date = df_pattern['date'].max()
    
    logger.info(f"Scanning date: {latest_date}")
    
    latest_patterns = df_pattern[df_pattern['date'] == latest_date].copy()
    if len(latest_patterns) == 0:
        logger.info("No signals found for latest date")
        return
        
    logger.info(f"Found {len(latest_patterns)} signals")
    
    # 3. Prepare Features (Must match training)
    # Need historical data for indicators
    if not os.path.exists(STOCK_INFO_FILE):
        logger.error("❌ Stock info not found")
        return
        
    df_daily = pd.read_csv(STOCK_INFO_FILE)
    df_daily['date'] = pd.to_datetime(df_daily['date'])
    df_daily['sid'] = df_daily['sid'].astype(str)
    
    # Filter for relevant stocks only to speed up
    relevant_sids = latest_patterns['sid'].astype(str).unique()
    df_daily = df_daily[df_daily['sid'].isin(relevant_sids)].copy()
    
    # Merge institutional data
    inst_raw = load_institutional_raw()
    inst_feature_cols = [
        'foreign_net_lag1', 'investment_net_lag1', 'dealer_net_lag1', 'total_net_lag1',
        'foreign_net_sum_3d', 'foreign_net_sum_5d', 'foreign_net_sum_10d', 'foreign_net_sum_20d',
        'total_net_sum_3d', 'total_net_sum_5d', 'total_net_sum_10d', 'total_net_sum_20d',
        'foreign_investment_spread_lag1', 'dealer_dominance_lag1',
        'foreign_net_to_vol_lag1', 'total_net_to_vol_lag1'
    ]
    
    if inst_raw is not None and not inst_raw.empty:
        inst_feat_df = compute_institutional_features(inst_raw)
        inst_feat_df['sid'] = inst_feat_df['sid'].astype(str)
        inst_feat_df['date'] = pd.to_datetime(inst_feat_df['date'])
        df_daily = df_daily.merge(inst_feat_df, on=['sid', 'date'], how='left')
        
        volume_safe = df_daily['volume'].replace(0, np.nan)
        df_daily['foreign_net_to_vol_lag1'] = df_daily['foreign_net_lag1'] / volume_safe
        df_daily['total_net_to_vol_lag1'] = df_daily['total_net_lag1'] / volume_safe
        
        median_fill = df_daily[inst_feature_cols].median()
        df_daily[inst_feature_cols] = df_daily[inst_feature_cols].fillna(median_fill)
    else:
        for col in inst_feature_cols: df_daily[col] = 0

    # Calculate Technical Indicators
    logger.info("Calculating technical indicators...")
    df_daily = df_daily.groupby('sid', group_keys=False).apply(lambda x: calculate_technical_indicators(x)).reset_index(drop=True)
    
    # Apply Z-Score
    drift_cols = [
        'foreign_net_sum_3d', 'foreign_net_sum_5d', 'foreign_net_sum_10d', 'foreign_net_sum_20d',
        'total_net_sum_3d', 'total_net_sum_5d', 'total_net_sum_10d', 'total_net_sum_20d',
        'volatility', 'atr_ratio', 'price_vs_ma20', 'price_vs_ma50',
        'volume_ratio_ma20', 'volume_ratio_ma50',
        'momentum_5d', 'momentum_20d', 'rsi_14'
    ]
    df_daily = apply_group_zscore(df_daily, drift_cols, group_key='sid')
    
    # Get latest rows for prediction
    latest_features = df_daily[df_daily['date'] == latest_date].copy()
    
    # 4. Generate Predictions for Multiple Exit Modes
    results = []
    exit_modes = ['fixed_r2_t20', 'fixed_r3_t20', 'trailing_15r']
    
    for idx, row in latest_patterns.iterrows():
        sid = str(row['sid'])
        
        # Get feature row
        feat_row = latest_features[latest_features['sid'] == sid]
        if len(feat_row) == 0:
            logger.warning(f"No features found for {sid}")
            continue
        feat_row = feat_row.iloc[0].to_dict()
        
        # Determine Pattern Type
        pat_type = 'UNKNOWN'
        if row.get('is_cup'): pat_type = 'CUP'
        elif row.get('is_htf'): pat_type = 'HTF'
        elif row.get('is_vcp'): pat_type = 'VCP'
        
        for exit_mode in exit_modes:
            sample = feat_row.copy()
            sample['pattern_type'] = pat_type
            sample['exit_mode'] = exit_mode
            
            # Add pattern specific prices if needed by model (unlikely if using tech indicators)
            # But let's ensure we have what we need.
            
            try:
                X_pred = pd.DataFrame([sample])
                X_pred['pattern_type'] = X_pred['pattern_type'].astype(str)
                X_pred['exit_mode'] = X_pred['exit_mode'].astype(str)
                
                # Ensure columns match
                missing = [c for c in feature_cols if c not in X_pred.columns]
                if missing:
                    # logger.warning(f"Missing cols: {missing}")
                    for c in missing: X_pred[c] = 0
                
                X_pred = X_pred[feature_cols]
                
                probs = model.predict_proba(X_pred)[0]
                pred_label = np.argmax(probs) # 0=D, 1=C, 2=B, 3=A
                
                res = {
                    'sid': sid,
                    'name': row.get('name', 'Unknown'),
                    'pattern': pat_type,
                    'exit_mode': exit_mode,
                    'pred_label': pred_label,
                    'prob_A': probs[3] if len(probs) > 3 else 0,
                    'prob_B': probs[2] if len(probs) > 2 else 0,
                    'close': row['close']
                }
                results.append(res)
            except Exception as e:
                logger.warning(f"Prediction error for {sid}: {e}")
                continue

    # 5. Generate Report
    if not results:
        logger.info("No predictions generated")
        return
        
    res_df = pd.DataFrame(results)
    top_picks = res_df[res_df['pred_label'] >= 2].sort_values('prob_A', ascending=False)
    
    logger.info(f"Generated {len(res_df)} predictions. Top picks (A/B): {len(top_picks)}")
    
    os.makedirs(os.path.dirname(REPORT_FILE), exist_ok=True)
    with open(REPORT_FILE, 'w') as f:
        f.write(f"# 🚀 CatBoost Enhanced Daily Report ({latest_date.date()})\n\n")
        f.write("## 🏆 Top Efficiency Picks (Class A & B)\n")
        f.write("這些股票被預測具有高效率 (Profit/Days)，且已針對不同出場策略進行優化。\n\n")
        
        if len(top_picks) > 0:
            f.write("| Stock | Pattern | Recommended Exit | Class | Prob(A) | Prob(B) | Price |\n")
            f.write("|-------|---------|------------------|-------|---------|---------|-------|\n")
            
            for _, row in top_picks.iterrows():
                cls = 'A' if row['pred_label'] == 3 else 'B'
                f.write(f"| {row['sid']} {row['name']} | {row['pattern']} | {row['exit_mode']} | **{cls}** | {row['prob_A']:.2f} | {row['prob_B']:.2f} | {row['close']} |\n")
        else:
            f.write("No high-efficiency signals found today.\n")
            
    logger.info(f"✅ Report saved to {REPORT_FILE}")

if __name__ == "__main__":
    scan_latest()
