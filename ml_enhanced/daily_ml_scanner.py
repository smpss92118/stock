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
MODEL_PATH = os.path.join(os.path.dirname(__file__), 'models/stock_selector.pkl')
FEATURE_INFO_PATH = os.path.join(os.path.dirname(__file__), 'models/feature_info.pkl')
OUTPUT_BASE = os.path.join(os.path.dirname(__file__), 'daily_reports')
BACKTEST_RESULTS_PATH = os.path.join(os.path.dirname(__file__), 'results/ml_backtest_final.csv')

# Setup Logger
logger = setup_logger('daily_ml_scanner')

def load_ml_model():
    """載入 ML 模型"""
    try:
        with open(MODEL_PATH, 'rb') as f:
            model = pickle.load(f)
        with open(FEATURE_INFO_PATH, 'rb') as f:
            feature_info = pickle.load(f)
        return model, feature_info['feature_cols']
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

def predict_signal_quality(model, feature_cols, features_dict):
    """預測訊號品質"""
    if model is None:
        return 0.5  # Default
    
    try:
        X = pd.DataFrame([features_dict])[feature_cols]
        proba = model.predict_proba(X)[0][1]
        return proba
    except Exception as e:
        logger.warning(f"    ⚠️ ML 預測失敗: {e}")
        return 0.5

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
            ml_proba = predict_signal_quality(model, feature_cols, features)
            
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
                'ml_proba': round(ml_proba, 3),
                'ml_selected': ml_proba >= 0.4,
                'rs_rating': round(rs_rating, 1)
            })
        
        # Detect CUP
        is_cup, cup_buy, cup_stop = detect_cup(window, ma_info, rs_rating=rs_rating)
        if is_cup and cup_buy and cup_stop and row_today['close'] > cup_stop:
            # Add temporary pattern info to row for feature extraction
            row_today_cup = row_today.copy()
            row_today_cup['cup_buy_price'] = cup_buy
            row_today_cup['cup_stop_price'] = cup_stop
            
            features = extract_ml_features(row_today_cup, 'cup')
            ml_proba = predict_signal_quality(model, feature_cols, features)
            
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
                'ml_proba': round(ml_proba, 3),
                'ml_selected': ml_proba >= 0.4,
                'rs_rating': round(rs_rating, 1)
            })
    
    return signals, latest_date

def generate_ml_report(signals, scan_date, df_full=None):
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
                f.write("**推薦策略**: Trailing Stop (1.5R trigger, MA20)\n\n")
                f.write("| 股票代號 | 股票名稱 | 當前價 | 買入價 | 停損價 | 距離% | Grade | ML分數 | RS Rating |\n")
                f.write("|---------|---------|--------|--------|--------|-------|-------|--------|----------|\n")
                for _, row in htf_ml.iterrows():
                    f.write(f"| **{row['sid']}** | {row['name']} | {row['current_price']} | ")
                    f.write(f"{row['buy_price']} | {row['stop_price']} | {row['distance_pct']}% | ")
                    f.write(f"{row['grade']} | **{row['ml_proba']}** | {row['rs_rating']} |\n")
                f.write("\n")
            
            # CUP 推薦
            cup_ml = ml_selected[ml_selected['pattern'] == 'CUP'].sort_values('ml_proba', ascending=False)
            if not cup_ml.empty:
                f.write(f"### 🏆 CUP 型態 ({len(cup_ml)} 檔)\n\n")
                f.write("**推薦策略**: Fixed Exit (R=2.0, T=20 或 R=3.0, T=20)\n\n")
                f.write("| 股票代號 | 股票名稱 | 當前價 | 買入價 | 停損價 | 距離% | ML分數 | RS Rating |\n")
                f.write("|---------|---------|--------|--------|--------|-------|--------|----------|\n")
                for _, row in cup_ml.iterrows():
                    f.write(f"| **{row['sid']}** | {row['name']} | {row['current_price']} | ")
                    f.write(f"{row['buy_price']} | {row['stop_price']} | {row['distance_pct']}% | ")
                    f.write(f"**{row['ml_proba']}** | {row['rs_rating']} |\n")
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
        
        f.write("---\n\n")
        
        # 過去一週訊號彙整
        if df_full is not None:
            f.write("## 📅 過去一週訊號彙整\n\n")
            try:
                from datetime import timedelta
                today = pd.to_datetime(scan_date)
                start_date = today - timedelta(days=7)
                
                df_week = df_full[pd.to_datetime(df_full['date']) >= start_date].copy()
                
                if not df_week.empty:
                    weekly_signals = []
                    
                    # HTF signals - check if column exists
                    if 'is_htf' in df_week.columns:
                        htf_df = df_week[df_week['is_htf'] == True].copy()
                        for _, row in htf_df.iterrows():
                            if pd.notna(row.get('htf_buy_price')) and pd.notna(row.get('htf_stop_price')):
                                weekly_signals.append({
                                    'date': pd.to_datetime(row['date']).strftime('%Y-%m-%d'),
                                    'sid': row['sid'],
                                    'name': row.get('name', ''),
                                    'pattern': 'HTF',
                                    'buy_price': round(row['htf_buy_price'], 2),
                                    'stop_price': round(row['htf_stop_price'], 2),
                                    'grade': row.get('htf_grade', 'N/A')
                                })
                    
                    # CUP signals - check if column exists
                    if 'is_cup' in df_week.columns:
                        cup_df = df_week[df_week['is_cup'] == True].copy()
                        for _, row in cup_df.iterrows():
                            if pd.notna(row.get('cup_buy_price')) and pd.notna(row.get('cup_stop_price')):
                                weekly_signals.append({
                                    'date': pd.to_datetime(row['date']).strftime('%Y-%m-%d'),
                                    'sid': row['sid'],
                                    'name': row.get('name', ''),
                                    'pattern': 'CUP',
                                    'buy_price': round(row['cup_buy_price'], 2),
                                    'stop_price': round(row['cup_stop_price'], 2),
                                    'grade': 'N/A'
                                })
                    
                    if weekly_signals:
                        df_weekly = pd.DataFrame(weekly_signals)
                        
                        # HTF weekly
                        htf_weekly = df_weekly[df_weekly['pattern'] == 'HTF']
                        if not htf_weekly.empty:
                            f.write(f"### 🚀 HTF 型態訊號 ({len(htf_weekly)} 檔)\n\n")
                            f.write("| 日期 | 股票代號 | 買入價 | 停損價 | Grade |\n")
                            f.write("|------|---------|--------|--------|-------|\n")
                            for _, row in htf_weekly.iterrows():
                                f.write(f"| {row['date']} | {row['sid']} | {row['buy_price']} | {row['stop_price']} | {row['grade']} |\n")
                            f.write("\n")
                        
                        # CUP weekly
                        cup_weekly = df_weekly[df_weekly['pattern'] == 'CUP']
                        if not cup_weekly.empty:
                            f.write(f"### 🏆 CUP 型態訊號 ({len(cup_weekly)} 檔)\n\n")
                            f.write("| 日期 | 股票代號 | 買入價 | 停損價 |\n")
                            f.write("|------|---------|--------|--------|\n")
                            for _, row in cup_weekly.iterrows():
                                f.write(f"| {row['date']} | {row['sid']} | {row['buy_price']} | {row['stop_price']} |\n")
                            f.write("\n")
                        
                        f.write(f"**統計**: 共 {len(df_weekly)} 個訊號來自過去 7 天\n\n")
                    else:
                        f.write("過去一週無符合條件的訊號。\n\n")
                else:
                    f.write("過去一週無數據記錄。\n\n")
            except Exception as e:
                logger.error(f"⚠️ 讀取歷史訊號錯誤: {e}")
                f.write(f"⚠️ 讀取歷史訊號時發生錯誤: {str(e)}\n\n")
            
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
                
                f.write(f"{i}. **{strategy_name}**\n")
                f.write(f"   - 年化報酬: **{ann_ret}%**, Sharpe: **{sharpe}**\n")
                f.write(f"   - 平均持倉: {avg_hold} 天, MDD: {mdd}%\n")
                f.write(f"   - 連勝/連敗: {max_win} / {max_loss}\n\n")
            
            f.write("---\n\n")
        else:
            # Fallback if no backtest results
            f.write("## 🏆 Top 3 Strategies (ML-Enhanced)\n\n")
            f.write("> ⚠️ 無法載入最新回測結果，請檢查 ml_backtest_final.csv\n\n")
            f.write("---\n\n")
        
        # 交易策略說明
        f.write("## 📖 交易策略說明\n\n")
        f.write("### HTF Trailing Stop\n")
        f.write("- **進場**: 價格突破買入價\n")
        f.write("- **出場**: 1. 達到 1.5R 後啟動 MA20 追蹤止損  2. 跌破停損價\n")
        f.write("- **預期**: 153-171% 年化報酬\n\n")
        f.write("### CUP Fixed Exit (ML 推薦) ⭐\n")
        f.write("- **進場**: 價格突破買入價\n")
        f.write("- **出場**: 2R 目標或 20 天時間出場\n")
        f.write("- **預期**: 171% 年化報酬, Sharpe 2.99 (ML enhanced)\n\n")
        f.write("### ML 分數解讀\n")
        f.write("- **≥ 0.4**: 高品質訊號，勝率 70-78% ⭐\n")
        f.write("- **0.3-0.4**: 中等品質，勝率 60-70%\n")
        f.write("- **< 0.3**: 低品質，勝率 < 60%\n\n")
    
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
    model, feature_cols = load_ml_model()
    
    # 3. 載入數據
    logger.info("\n>>> 載入股票數據...")
    result = load_data()
    if result is None:
        logger.error("❌ 數據載入失敗")
        return
    df, latest_date = result
    
    # 4. 掃描並評分
    logger.info("\n>>> 掃描股票訊號...")
    signals, scan_date = scan_with_ml(df, model, feature_cols)
    
    # 5. 生成報告
    logger.info("\n>>> 生成 ML 報告...")
    generate_ml_report(signals, scan_date, df_full=df)
    
    logger.info("\n" + "="*60)
    logger.info("掃描完成！")
    logger.info("="*60)

if __name__ == "__main__":
    main()
