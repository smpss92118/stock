#!/usr/bin/env python3
"""
Daily ML-Enhanced Stock Scanner

每日掃描系統，同時輸出:
1. 原始策略訊號 (HTF Trailing, CUP R=2.0)
2. ML 增強訊號 (經過 ML 0.4 threshold 過濾)
3. 進出場點、風險、ML 評分

Usage:
    python stock/ml_enhanced/daily_ml_scanner.py
    
Output:
    stock/ml_enhanced/daily_reports/YYYY-MM-DD/ml_daily_summary.md
    
Crontab:
    0 19 * * * cd /Users/sony/ml_stock && python stock/ml_enhanced/daily_ml_scanner.py
"""

import sys
import os
from datetime import datetime
import pandas as pd
import pickle

# Add paths
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from scripts.update_daily_data import main as update_data
from scripts.run_daily_scan import scan_latest_date, load_data
from src.strategies.htf import detect_htf
from src.strategies.cup import detect_cup
from src.strategies.vcp import detect_vcp

# Import shared modules
from src.utils.logger import setup_logger
from src.ml.features import extract_ml_features

# Configuration
MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')
FEATURE_INFO_PATH = os.path.join(MODEL_DIR, 'feature_info.pkl')
OUTPUT_BASE = os.path.join(os.path.dirname(__file__), 'daily_reports')
BACKTEST_RESULTS_PATH = os.path.join(os.path.dirname(__file__), 'results/ml_backtest_final.csv')

# Setup Logger
logger = setup_logger('daily_ml_scanner')

def load_all_ml_models():
    """載入所有 ML 模型 (9個: 3 patterns × 3 exit modes)"""
    try:
        models = {}
        patterns = ['cup', 'htf', 'vcp']
        exit_modes = ['fixed_r2_t20', 'fixed_r3_t20', 'trailing_15r']
        
        for pat in patterns:
            for exit_mode in exit_modes:
                model_key = f'{pat}_{exit_mode}'
                model_path = os.path.join(MODEL_DIR, f'stock_selector_{model_key}.pkl')
                
                if os.path.exists(model_path):
                    with open(model_path, 'rb') as f:
                        models[model_key] = pickle.load(f)
                else:
                    logger.warning(f"⚠️ Model not found: {model_path}")
        
        # Load feature info
        with open(FEATURE_INFO_PATH, 'rb') as f:
            feature_info = pickle.load(f)
        
        logger.info(f"✅ 載入 {len(models)} 個 ML 模型")
        return models, feature_info['feature_cols']
    except Exception as e:
        logger.error(f"⚠️ ML 模型載入失敗: {e}")
        return None, None

def load_backtest_results():
    """載入回測結果"""
    try:
        if not os.path.exists(BACKTEST_RESULTS_PATH):
            return None
        
        df = pd.read_csv(BACKTEST_RESULTS_PATH)
        return df
    except Exception as e:
        logger.error(f"⚠️ 回測結果載入失敗: {e}")
        return None

def predict_best_exit(models, feature_cols, features_dict, pattern_type):
    """
    預測最佳出場策略
    Returns: (best_exit_name, best_ml_score, all_predictions_dict)
    """
    if models is None:
        return 'fixed_r2_t20', 0.5, {}
    
    try:
        X = pd.DataFrame([features_dict])[feature_cols]
        
        # 預測所有3種出場方式
        exit_modes = ['fixed_r2_t20', 'fixed_r3_t20', 'trailing_15r']
        predictions = {}
        
        for exit_mode in exit_modes:
            model_key = f'{pattern_type}_{exit_mode}'
            if model_key in models:
                proba = models[model_key].predict_proba(X)[0][1]
                predictions[exit_mode] = proba
            else:
                predictions[exit_mode] = 0.5  # Fallback
        
        # 找出最佳策略
        best_exit = max(predictions.items(), key=lambda x: x[1])
        
        return best_exit[0], best_exit[1], predictions
        
    except Exception as e:
        logger.warning(f"    ⚠️ ML 預測失敗: {e}")
        return 'fixed_r2_t20', 0.5, {}

def scan_with_ml(df, model, feature_cols):
    """掃描並添加 ML 評分"""
    latest_date = df['date'].max()
    logger.info(f"\n掃描日期: {latest_date}")
    
    latest_stocks = df[df['date'] == latest_date]['sid'].unique()
    logger.info(f"股票數量: {len(latest_stocks)}")
    
    signals = []
    processed = 0
    
    for sid in latest_stocks:
        processed += 1
        if processed % 100 == 0:
            logger.info(f"已處理 {processed}/{len(latest_stocks)} 檔股票...")
        
        stock_df = df[df['sid'] == sid].reset_index(drop=True)
        n_rows = len(stock_df)
        
        if n_rows < 126:
            continue
        
        i = n_rows - 1
        window = stock_df.iloc[i - 126 + 1 : i + 1]
        row_today = stock_df.iloc[i]
        
        if row_today['date'] != latest_date:
            continue
        
        # MA info
        ma_info = {
            'ma50': row_today.get('ma50', 0),
            'ma150': row_today.get('ma150', 0),
            'ma200': row_today.get('ma200', 0),
            'low52': row_today.get('low52', 0)
        }
        
        rs_rating = row_today.get('rs_rating', 0)
        
        # Detect HTF
        is_htf, htf_buy, htf_stop, htf_grade = detect_htf(window, rs_rating=rs_rating)
        if is_htf and htf_buy and htf_stop and row_today['close'] > htf_stop:
            # Add temporary pattern info to row for feature extraction
            row_today_htf = row_today.copy()
            row_today_htf['htf_buy_price'] = htf_buy
            row_today_htf['htf_stop_price'] = htf_stop
            row_today_htf['htf_grade'] = htf_grade
            
            features = extract_ml_features(row_today_htf, 'htf')
            
            # 預測最佳出場策略
            best_exit, best_ml_score, all_preds = predict_best_exit(model, feature_cols, features, 'htf')
            
            # 出場策略名稱對照
            exit_names = {
                'fixed_r2_t20': 'Fixed R=2.0',
                'fixed_r3_t20': 'Fixed R=3.0',
                'trailing_15r': 'Trailing 1.5R'
            }
            
            signals.append({
                'date': latest_date,
                'sid': sid,
                'name': row_today['name'],
                'pattern': 'HTF',
                'buy_price': round(htf_buy, 2),
                'stop_price': round(htf_stop, 2),
                'risk_pct': round((htf_buy - htf_stop) / htf_buy * 100, 2),
                'grade': htf_grade if htf_grade else 'C',
                'current_price': round(row_today['close'], 2),
                'distance_pct': round((htf_buy - row_today['close']) / htf_buy * 100, 2),
                'ml_proba': round(best_ml_score, 3),
                'ml_selected': best_ml_score >= 0.4,
                'rs_rating': round(rs_rating, 1),
                'recommended_exit': exit_names.get(best_exit, best_exit),
                'exit_predictions': {
                    'r2': round(all_preds.get('fixed_r2_t20', 0), 2),
                    'r3': round(all_preds.get('fixed_r3_t20', 0), 2),
                    'trailing': round(all_preds.get('trailing_15r', 0), 2)
                }
            })
        
        # Detect CUP
        is_cup, cup_buy, cup_stop = detect_cup(window, ma_info, rs_rating=rs_rating)
        if is_cup and cup_buy and cup_stop and row_today['close'] > cup_stop:
            # Add temporary pattern info to row for feature extraction
            row_today_cup = row_today.copy()
            row_today_cup['cup_buy_price'] = cup_buy
            row_today_cup['cup_stop_price'] = cup_stop
            
            features = extract_ml_features(row_today_cup, 'cup')
            
            # 預測最佳出場策略
            best_exit, best_ml_score, all_preds = predict_best_exit(model, feature_cols, features, 'cup')
            
            exit_names = {
                'fixed_r2_t20': 'Fixed R=2.0',
                'fixed_r3_t20': 'Fixed R=3.0',
                'trailing_15r': 'Trailing 1.5R'
            }
            
            signals.append({
                'date': latest_date,
                'sid': sid,
                'name': row_today['name'],
                'pattern': 'CUP',
                'buy_price': round(cup_buy, 2),
                'stop_price': round(cup_stop, 2),
                'risk_pct': round((cup_buy - cup_stop) / cup_buy * 100, 2),
                'grade': 'N/A',
                'current_price': round(row_today['close'], 2),
                'distance_pct': round((cup_buy - row_today['close']) / cup_buy * 100, 2),
                'ml_proba': round(best_ml_score, 3),
                'ml_selected': best_ml_score >= 0.4,
                'rs_rating': round(rs_rating, 1),
                'recommended_exit': exit_names.get(best_exit, best_exit),
                'exit_predictions': {
                    'r2': round(all_preds.get('fixed_r2_t20', 0), 2),
                    'r3': round(all_preds.get('fixed_r3_t20', 0), 2),
                    'trailing': round(all_preds.get('trailing_15r', 0), 2)
                }
            })

        # Detect VCP
        vol_ma50 = window['volume'].rolling(50).mean().iloc[-1] if len(window) >= 50 else window['volume'].mean()
        is_vcp, vcp_buy, vcp_stop = detect_vcp(window, vol_ma50_val=vol_ma50, price_ma50_val=ma_info['ma50'], rs_rating=rs_rating)
        if is_vcp and vcp_buy and vcp_stop and row_today['close'] > vcp_stop:
            # Add temporary pattern info to row for feature extraction
            row_today_vcp = row_today.copy()
            row_today_vcp['vcp_buy_price'] = vcp_buy
            row_today_vcp['vcp_stop_price'] = vcp_stop
            
            features = extract_ml_features(row_today_vcp, 'vcp')
            
            # 預測最佳出場策略
            best_exit, best_ml_score, all_preds = predict_best_exit(model, feature_cols, features, 'vcp')
            
            exit_names = {
                'fixed_r2_t20': 'Fixed R=2.0',
                'fixed_r3_t20': 'Fixed R=3.0',
                'trailing_15r': 'Trailing 1.5R'
            }
            
            signals.append({
                'date': latest_date,
                'sid': sid,
                'name': row_today['name'],
                'pattern': 'VCP',
                'buy_price': round(vcp_buy, 2),
                'stop_price': round(vcp_stop, 2),
                'risk_pct': round((vcp_buy - vcp_stop) / vcp_buy * 100, 2),
                'grade': 'N/A',
                'current_price': round(row_today['close'], 2),
                'distance_pct': round((vcp_buy - row_today['close']) / vcp_buy * 100, 2),
                'ml_proba': round(best_ml_score, 3),
                'ml_selected': best_ml_score >= 0.4,
                'rs_rating': round(rs_rating, 1),
                'recommended_exit': exit_names.get(best_exit, best_exit),
                'exit_predictions': {
                    'r2': round(all_preds.get('fixed_r2_t20', 0), 2),
                    'r3': round(all_preds.get('fixed_r3_t20', 0), 2),
                    'trailing': round(all_preds.get('trailing_15r', 0), 2)
                }
            })
    
    total_signals = len(signals)
    ml_kept = sum(1 for s in signals if s['ml_selected'])
    logger.info(f"掃描完成: 總訊號 {total_signals}, ML≥0.4 {ml_kept}, 處理股票 {processed}")
    return signals, latest_date

def scan_past_week(df, model, feature_cols, latest_date):
    """掃描過去一週的訊號並加上 ML 評分"""
    from datetime import timedelta
    
    today = pd.to_datetime(latest_date)
    start_date = today - timedelta(days=7)
    
    # Filter for past 7 days (excluding today to avoid duplication if needed, but report separates them)
    # Actually report "Past Week" usually implies history excluding today, or including?
    # The original code used: df_week = df_full[pd.to_datetime(df_full['date']) >= start_date]
    # Let's keep it simple: Past 7 days excluding today for "Past Week" section
    
    mask = (pd.to_datetime(df['date']) >= start_date) & (pd.to_datetime(df['date']) < today)
    df_week = df[mask].copy()
    
    past_signals = []
    
    if df_week.empty:
        return past_signals
        
    # Iterate over patterns
    patterns = ['htf', 'cup', 'vcp']
    
    for pat in patterns:
        col_name = f'is_{pat}'
        if col_name not in df_week.columns:
            continue
            
        # Filter rows with this pattern
        pat_df = df_week[df_week[col_name] == True].copy()
        
        for _, row in pat_df.iterrows():
            # Basic validation
            buy_col = f'{pat}_buy_price'
            stop_col = f'{pat}_stop_price'
            
            if pd.isna(row.get(buy_col)) or pd.isna(row.get(stop_col)):
                continue
                
            # Extract features
            # Note: row must have necessary columns. extract_ml_features handles missing gracefully usually.
            # We need to ensure 'ma20', 'ma50' etc are present. load_data usually provides them.
            
            # Prepare row for feature extraction (needs specific format sometimes)
            # extract_ml_features expects the row to have specific pattern columns set if we pass pattern_type
            # It reads e.g. row['htf_buy_price'] which exists.
            
            features = extract_ml_features(row, pat)
            
            # 預測最佳出場策略
            best_exit, ml_proba, all_preds = predict_best_exit(models, feature_cols, features, pat)
            
            # Only keep if ML score is decent (e.g. >= 0.4) to show "High Quality" past signals
            if ml_proba >= 0.4:
                exit_names = {
                    'fixed_r2_t20': 'R=2.0',
                    'fixed_r3_t20': 'R=3.0',
                    'trailing_15r': 'Trail'
                }
                
                past_signals.append({
                    'date': pd.to_datetime(row['date']).strftime('%Y-%m-%d'),
                    'sid': row['sid'],
                    'name': row.get('name', ''),
                    'pattern': pat.upper(),
                    'buy_price': round(row[buy_col], 2),
                    'stop_price': round(row[stop_col], 2),
                    'ml_proba': round(ml_proba, 3),
                    'grade': row.get(f'{pat}_grade', 'N/A'),
                    'recommended_exit': exit_names.get(best_exit, best_exit),
                    'exit_predictions': {
                        'r2': round(all_preds.get('fixed_r2_t20', 0), 2),
                        'r3': round(all_preds.get('fixed_r3_t20', 0), 2),
                        'trailing': round(all_preds.get('trailing_15r', 0), 2)
                    }
                })
    
    return past_signals

def generate_ml_report(signals, scan_date, df_full=None, past_signals=None):
    """生成 ML 增強報告（即使今日無訊號也生成）"""
    
    # 創建輸出目錄
    today_str = datetime.now().strftime('%Y-%m-%d')
    output_dir = os.path.join(OUTPUT_BASE, today_str)
    os.makedirs(output_dir, exist_ok=True)
    
    # 處理訊號數據
    if signals:
        df_signals = pd.DataFrame(signals)
        # 分離 ML 選中和未選中
        ml_selected = df_signals[df_signals['ml_selected'] == True]
        ml_rejected = df_signals[df_signals['ml_selected'] == False]
    else:
        df_signals = pd.DataFrame()
        ml_selected = pd.DataFrame()
        ml_rejected = pd.DataFrame()
    
    # 生成報告
    report_path = os.path.join(output_dir, 'ml_daily_summary.md')
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"# ML-Enhanced 股票訊號報告\n")
        f.write(f"**掃描日期**: {scan_date}\n")
        f.write(f"**生成時間**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("---\n\n")
        
        # 統計摘要
        f.write(f"## 📊 本日訊號統計\n\n")
        
        if not df_signals.empty:
            f.write(f"- **總訊號數**: {len(df_signals)}\n")
            f.write(f"- **ML 推薦**: {len(ml_selected)} (高品質)\n")
            f.write(f"- **原始訊號**: {len(ml_rejected)} (參考)\n\n")
        else:
            f.write(f"- **總訊號數**: 0\n\n")
            f.write("**本日無符合條件的型態訊號。**\n\n")
        
        f.write("---\n\n")
        
        # ML 推薦訊號
        if not ml_selected.empty:
            f.write(f"## ✅ ML 推薦訊號 ({len(ml_selected)} 檔)\n\n")
            f.write("> **ML 機率 ≥ 0.4**：高品質訊號，建議優先研究\n\n")
            
            # HTF 推薦
            htf_ml = ml_selected[ml_selected['pattern'] == 'HTF'].sort_values('ml_proba', ascending=False)
            if not htf_ml.empty:
                f.write(f"### 🚀 HTF 型態 ({len(htf_ml)} 檔)\n\n")
                f.write("| 股票代號 | 股票名稱 | 當前價 | 買入價 | 停損價 | 距離% | Grade | **推薦出場** | ML分數 | 其他選項 |\n")
                f.write("|---------|---------|--------|--------|--------|-------|-------|------------|--------|----------|\n")
                for _, row in htf_ml.iterrows():
                    other_opts = f"R2:{row['exit_predictions']['r2']}, R3:{row['exit_predictions']['r3']}, Trail:{row['exit_predictions']['trailing']}"
                    f.write(f"| **{row['sid']}** | {row['name']} | {row['current_price']} | ")
                    f.write(f"{row['buy_price']} | {row['stop_price']} | {row['distance_pct']}% | ")
                    f.write(f"{row['grade']} | **{row['recommended_exit']}** ⭐ | **{row['ml_proba']}** | {other_opts} |\n")
                f.write("\n")
            
            # CUP 推薦
            cup_ml = ml_selected[ml_selected['pattern'] == 'CUP'].sort_values('ml_proba', ascending=False)
            if not cup_ml.empty:
                f.write(f"### 🏆 CUP 型態 ({len(cup_ml)} 檔)\n\n")
                f.write("| 股票代號 | 股票名稱 | 當前價 | 買入價 | 停損價 | 距離% | **推薦出場** | ML分數 | 其他選項 |\n")
                f.write("|---------|---------|--------|--------|--------|-------|------------|--------|----------|\n")
                for _, row in cup_ml.iterrows():
                    other_opts = f"R2:{row['exit_predictions']['r2']}, R3:{row['exit_predictions']['r3']}, Trail:{row['exit_predictions']['trailing']}"
                    f.write(f"| **{row['sid']}** | {row['name']} | {row['current_price']} | ")
                    f.write(f"{row['buy_price']} | {row['stop_price']} | {row['distance_pct']}% | ")
                    f.write(f"**{row['recommended_exit']}** ⭐ | **{row['ml_proba']}** | {other_opts} |\n")
                f.write("\n")

            # VCP 推薦
            vcp_ml = ml_selected[ml_selected['pattern'] == 'VCP'].sort_values('ml_proba', ascending=False)
            if not vcp_ml.empty:
                f.write(f"### 🌀 VCP 型態 ({len(vcp_ml)} 檔)\n\n")
                f.write("| 股票代號 | 股票名稱 | 當前價 | 買入價 | 停損價 | 距離% | **推薦出場** | ML分數 | 其他選項 |\n")
                f.write("|---------|---------|--------|--------|--------|-------|------------|--------|----------|\n")
                for _, row in vcp_ml.iterrows():
                    other_opts = f"R2:{row['exit_predictions']['r2']}, R3:{row['exit_predictions']['r3']}, Trail:{row['exit_predictions']['trailing']}"
                    f.write(f"| **{row['sid']}** | {row['name']} | {row['current_price']} | ")
                    f.write(f"{row['buy_price']} | {row['stop_price']} | {row['distance_pct']}% | ")
                    f.write(f"**{row['recommended_exit']}** ⭐ | **{row['ml_proba']}** | {other_opts} |\n")
                f.write("\n")
            
            f.write("---\n\n")
        
        # 原始訊號（未被 ML 選中）
        if not ml_rejected.empty:
            f.write(f"## 📋 其他原始訊號 ({len(ml_rejected)} 檔)\n\n")
            f.write("> **ML 機率 < 0.4**：品質較低，僅供參考\n\n")
            
            # HTF 其他
            htf_other = ml_rejected[ml_rejected['pattern'] == 'HTF'].sort_values('ml_proba', ascending=False)
            if not htf_other.empty:
                f.write(f"### HTF 型態 ({len(htf_other)} 檔)\n\n")
                f.write("| 股票代號 | 當前價 | 買入價 | 停損價 | Grade | ML分數 |\n")
                f.write("|---------|--------|--------|--------|-------|--------|\n")
                for _, row in htf_other.iterrows():
                    f.write(f"| {row['sid']} | {row['current_price']} | {row['buy_price']} | ")
                    f.write(f"{row['stop_price']} | {row['grade']} | {row['ml_proba']} |\n")
                f.write("\n")
            
            # CUP 其他
            cup_other = ml_rejected[ml_rejected['pattern'] == 'CUP'].sort_values('ml_proba', ascending=False)
            if not cup_other.empty:
                f.write(f"### CUP 型態 ({len(cup_other)} 檔)\n\n")
                f.write("| 股票代號 | 當前價 | 買入價 | 停損價 | ML分數 |\n")
                f.write("|---------|--------|--------|--------|--------|\n")
                for _, row in cup_other.iterrows():
                    f.write(f"| {row['sid']} | {row['current_price']} | {row['buy_price']} | ")
                    f.write(f"{row['stop_price']} | {row['ml_proba']} |\n")
                f.write("\n")

            # VCP 其他
            vcp_other = ml_rejected[ml_rejected['pattern'] == 'VCP'].sort_values('ml_proba', ascending=False)
            if not vcp_other.empty:
                f.write(f"### VCP 型態 ({len(vcp_other)} 檔)\n\n")
                f.write("| 股票代號 | 當前價 | 買入價 | 停損價 | ML分數 |\n")
                f.write("|---------|--------|--------|--------|--------|\n")
                for _, row in vcp_other.iterrows():
                    f.write(f"| {row['sid']} | {row['current_price']} | {row['buy_price']} | ")
                    f.write(f"{row['stop_price']} | {row['ml_proba']} |\n")
                f.write("\n")
        
        f.write("---\n\n")
        
        # 過去一週訊號彙整 (ML Enhanced)
        f.write("## 📅 過去一週訊號彙整 (ML Enhanced)\n\n")
        if past_signals:
            f.write("> 僅顯示 ML 分數 ≥ 0.4 的高品質歷史訊號\n\n")
            
            df_past = pd.DataFrame(past_signals)
            
            # HTF
            htf_past = df_past[df_past['pattern'] == 'HTF'].sort_values(['date', 'ml_proba'], ascending=[False, False])
            if not htf_past.empty:
                f.write(f"### 🚀 HTF ({len(htf_past)} 檔)\n\n")
                f.write("| 日期 | 股票代號 | 買入價 | 停損價 | Grade | ML分數 |\n")
                f.write("|------|---------|--------|--------|-------|--------|\n")
                for _, row in htf_past.iterrows():
                    f.write(f"| {row['date']} | {row['sid']} | {row['buy_price']} | {row['stop_price']} | {row['grade']} | **{row['ml_proba']}** |\n")
                f.write("\n")
            
            # CUP
            cup_past = df_past[df_past['pattern'] == 'CUP'].sort_values(['date', 'ml_proba'], ascending=[False, False])
            if not cup_past.empty:
                f.write(f"### 🏆 CUP ({len(cup_past)} 檔)\n\n")
                f.write("| 日期 | 股票代號 | 買入價 | 停損價 | ML分數 |\n")
                f.write("|------|---------|--------|--------|--------|\n")
                for _, row in cup_past.iterrows():
                    f.write(f"| {row['date']} | {row['sid']} | {row['buy_price']} | {row['stop_price']} | **{row['ml_proba']}** |\n")
                f.write("\n")
                
            # VCP
            vcp_past = df_past[df_past['pattern'] == 'VCP'].sort_values(['date', 'ml_proba'], ascending=[False, False])
            if not vcp_past.empty:
                f.write(f"### 🌀 VCP ({len(vcp_past)} 檔)\n\n")
                f.write("| 日期 | 股票代號 | 買入價 | 停損價 | ML分數 |\n")
                f.write("|------|---------|--------|--------|--------|\n")
                for _, row in vcp_past.iterrows():
                    f.write(f"| {row['date']} | {row['sid']} | {row['buy_price']} | {row['stop_price']} | **{row['ml_proba']}** |\n")
                f.write("\n")
                
        else:
            f.write("過去一週無 ML ≥ 0.4 的高品質訊號。\n\n")
            
        f.write("---\n\n")
        
        # Top Strategies (Dynamic)
        backtest_df = load_backtest_results()
        if backtest_df is not None and not backtest_df.empty:
            f.write("## 🏆 Top 3 Strategies (ML-Enhanced)\n\n")
            
            # Sort by Annual Return
            top_strategies = backtest_df.sort_values('Ann. Return %', ascending=False).head(3)
            
            f.write("### 依年化報酬排序\n\n")
            for i, (_, row) in enumerate(top_strategies.iterrows(), 1):
                strategy_name = row['Strategy']
                ann_ret = row['Ann. Return %']
                sharpe = row['Sharpe']
                avg_hold = row.get('Avg Holding Days', 'N/A')
                max_win = row.get('Max Win Streak', 'N/A')
                max_loss = row.get('Max Loss Streak', 'N/A')
                mdd = row.get('Max DD %', 'N/A')
                win_rate = row.get('Win Rate', 'N/A')
                
                f.write(f"{i}. **{strategy_name}**\n")
                f.write(f"   - 年化報酬: **{ann_ret}%**, Sharpe: **{sharpe}**, 勝率: {win_rate}%\n")
                f.write(f"   - 平均持倉: {avg_hold} 天, MDD: {mdd}%\n")
                f.write(f"   - 連勝/連敗: {max_win} / {max_loss}\n\n")

            # Sort by Sharpe
            top_sharpe = backtest_df.sort_values('Sharpe', ascending=False).head(3)
            f.write("### 依 Sharpe 排序\n\n")
            for i, (_, row) in enumerate(top_sharpe.iterrows(), 1):
                strategy_name = row['Strategy']
                ann_ret = row['Ann. Return %']
                sharpe = row['Sharpe']
                avg_hold = row.get('Avg Holding Days', 'N/A')
                max_win = row.get('Max Win Streak', 'N/A')
                max_loss = row.get('Max Loss Streak', 'N/A')
                mdd = row.get('Max DD %', 'N/A')
                win_rate = row.get('Win Rate', 'N/A')
                
                f.write(f"{i}. **{strategy_name}**\n")
                f.write(f"   - Sharpe: **{sharpe}**, 年化報酬: **{ann_ret}%**, 勝率: {win_rate}%\n")
                f.write(f"   - 平均持倉: {avg_hold} 天, MDD: {mdd}%\n")
                f.write(f"   - 連勝/連敗: {max_win} / {max_loss}\n\n")
            
            f.write("---\n\n")
        else:
            # Fallback if no backtest results
            f.write("## 🏆 Top 3 Strategies (ML-Enhanced)\n\n")
            f.write("> ⚠️ 無法載入最新回測結果，請檢查 ml_backtest_final.csv\n\n")
            f.write("---\n\n")
        
        # 交易策略說明 (從回測結果動態生成)
        f.write("## 📖 交易策略說明\n\n")
        
        # 從回測結果中找出最佳策略
        if backtest_df is not None and not backtest_df.empty:
            # HTF 最佳策略
            htf_best = backtest_df[
                (backtest_df['Strategy'].str.contains('HTF Fixed')) &
                (backtest_df['ml_threshold'].notna())
            ].nlargest(1, 'Ann. Return %')
            
            if not htf_best.empty:
                htf_row = htf_best.iloc[0]
                f.write(f"### HTF Fixed Exit (ML 推薦) ⭐\n")
                f.write(f"- **進場**: 價格突破買入價\n")
                f.write(f"- **出場**: **固定 2R 停利** 或 20 天時間出場\n")
                f.write(f"- **預期**: {htf_row['Ann. Return %']:.1f}% 年化報酬, ")
                f.write(f"Sharpe {htf_row['Sharpe']:.2f}, 勝率 {htf_row['Win Rate']:.1f}%\n")
                f.write(f"- **ML閾值**: {htf_row['ml_threshold']}, 交易次數: {int(htf_row['Trades'])}\n\n")
            
            # CUP 最佳策略
            cup_best = backtest_df[
                (backtest_df['Strategy'].str.contains('CUP Fixed')) &
                (backtest_df['ml_threshold'].notna())
            ].nlargest(1, 'Ann. Return %')
            
            if not cup_best.empty:
                cup_row = cup_best.iloc[0]
                # 判斷是 R=2.0 還是 R=3.0
                r_value = "3R" if "R=3.0" in cup_row['Strategy'] else "2R"
                f.write(f"### CUP Fixed Exit (ML 推薦) ⭐\n")
                f.write(f"- **進場**: 價格突破買入價\n")
                f.write(f"- **出場**: **固定 {r_value} 停利** 或 20 天時間出場\n")
                f.write(f"- **預期**: {cup_row['Ann. Return %']:.1f}% 年化報酬, ")
                f.write(f"Sharpe {cup_row['Sharpe']:.2f}, 勝率 {cup_row['Win Rate']:.1f}%\n")
                f.write(f"- **ML閾值**: {cup_row['ml_threshold']}, 交易次數: {int(cup_row['Trades'])}\n\n")
        else:
            # Fallback to hardcoded if backtest data not available
            f.write("### HTF Fixed Exit (ML 推薦) ⭐\n")
            f.write("- **進場**: 價格突破買入價\n")
            f.write("- **出場**: **固定 2R 停利** 或 20 天時間出場\n")
            f.write("- **預期**: 使用最新回測數據 (請執行 weekly_retrain.py)\n\n")
            f.write("### CUP Fixed Exit (ML 推薦) ⭐\n")
            f.write("- **進場**: 價格突破買入價\n")
            f.write("- **出場**: **固定 3R 停利** 或 20 天時間出場\n")
            f.write("- **預期**: 使用最新回測數據 (請執行 weekly_retrain.py)\n\n")
        
        f.write("### ML 分數解讀\n\n")
        
        # 從回測數據動態生成 ML 分數解讀
        if backtest_df is not None and not backtest_df.empty:
            # 找出各 ML 閾值的最佳 Sharpe
            ml_05 = backtest_df[backtest_df['ml_threshold'] == 0.5]['Sharpe'].max()
            ml_04 = backtest_df[backtest_df['ml_threshold'] == 0.4]['Sharpe'].max()
            ml_03 = backtest_df[backtest_df['ml_threshold'] == 0.3]['Sharpe'].max()
            
            f.write(f"- **≥ 0.5**: **Elite (頂級)** - 歷史回測最佳 Sharpe {ml_05:.2f}，極高勝率 ⭐\n")
            f.write(f"- **0.4-0.5**: **Strong (強力)** - 歷史回測最佳 Sharpe {ml_04:.2f}，適合標準操作\n")
            f.write(f"- **0.3-0.4**: **Moderate (普通)** - 歷史回測最佳 Sharpe {ml_03:.2f}，僅供觀察\n\n")
        else:
            # Fallback
            f.write("- **≥ 0.5**: **Elite (頂級)** - 高品質訊號 ⭐\n")
            f.write("- **0.4-0.5**: **Strong (強力)** - 適合標準操作\n")
            f.write("- **0.3-0.4**: **Moderate (普通)** - 僅供觀察\n\n")
    
    # 儲存 CSV (即使是空的也儲存)
    csv_path = os.path.join(output_dir, 'ml_signals.csv')
    if not df_signals.empty:
        df_signals.to_csv(csv_path, index=False)
    else:
        # 創建空 CSV
        pd.DataFrame(columns=['date', 'sid', 'name', 'pattern', 'buy_price', 'stop_price', 
                              'risk_pct', 'grade', 'current_price', 'distance_pct', 
                              'ml_proba', 'ml_selected', 'rs_rating']).to_csv(csv_path, index=False)
    
    logger.info(f"\n✅ ML 報告已儲存至: {report_path}")
    logger.info(f"✅ CSV 已儲存至: {csv_path}")
    
    # 顯示摘要
    logger.info(f"\n{'='*60}")
    logger.info(f"ML 推薦訊號統計")
    logger.info(f"{'='*60}")
    if not df_signals.empty:
        logger.info(f"HTF (ML ≥ 0.4): {len(ml_selected[ml_selected['pattern'] == 'HTF'])} 檔")
        logger.info(f"CUP (ML ≥ 0.4): {len(ml_selected[ml_selected['pattern'] == 'CUP'])} 檔")
        logger.info(f"VCP (ML ≥ 0.4): {len(ml_selected[ml_selected['pattern'] == 'VCP'])} 檔")
        logger.info(f"總計推薦: {len(ml_selected)} 檔")
    else:
        logger.info(f"本日無訊號")

def main():
    logger.info("="*60)
    logger.info("ML-Enhanced Daily Stock Scanner")
    logger.info("="*60)
    
    # 1. 更新數據
    logger.info("\n>>> 更新每日數據...")
    try:
        update_data()
    except Exception as e:
        logger.error(f"⚠️ 數據更新失敗: {e}")
    
    # 2. 載入 ML 模型
    logger.info("\n>>> 載入 ML 模型...")
    models, feature_cols = load_all_ml_models()
    if models is None or feature_cols is None:
        logger.error("❌ 模型或特徵列表載入失敗，停止流程。")
        return
    
    # 3. 載入數據
    logger.info("\n>>> 載入股票數據...")
    result = load_data()
    if result is None:
        logger.error("❌ 數據載入失敗")
        return
    df, latest_date = result
    logger.info(f"數據載入完成: {len(df)} 筆，股票 {df['sid'].nunique()} 檔，最新日期 {latest_date}")
    
    # 4. 掃描並評分
    logger.info("\n>>> 掃描股票訊號 (今日)...")
    signals, scan_date = scan_with_ml(df, models, feature_cols)
    
    logger.info("\n>>> 掃描股票訊號 (過去一週)...")
    past_signals = scan_past_week(df, models, feature_cols, latest_date)
    logger.info(f"過去一週高品質訊號 (ML>=0.4): {len(past_signals)} 檔")
    
    # 5. 生成報告
    logger.info("\n>>> 生成 ML 報告...")
    generate_ml_report(signals, scan_date, df_full=df, past_signals=past_signals)
    
    logger.info("\n" + "="*60)
    logger.info("掃描完成！")
    logger.info("="*60)

if __name__ == "__main__":
    main()
