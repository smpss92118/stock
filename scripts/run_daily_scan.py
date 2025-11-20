#!/usr/bin/env python3
"""
每日股票訊號掃描器
掃描最新日期的股票數據，識別符合 CUP/HTF 型態的股票
"""

import sys
import os

# 添加 src 到路徑
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pandas as pd
import numpy as np
from datetime import datetime
from src.strategies.cup import detect_cup
from src.strategies.htf import detect_htf
from src.strategies.vcp import detect_vcp
from src.utils.data_loader import loader

# 設定檔案路徑
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), '../data/processed/latest_signals.csv')
OUTPUT_REPORT = os.path.join(os.path.dirname(__file__), '../data/processed/latest_signals_report.md')
WINDOW_DAYS = 126
COL_NAMES = ['sid', 'name', 'date', 'open', 'high', 'low', 'close', 'volume']

def load_data():
    """載入並準備數據 (使用 DataLoader)"""
    print("載入數據 (最近 126 天)...", flush=True)
    # Load slightly more than 126 days to ensure we have enough valid trading days
    df = loader.load_data(days=150) 
    
    if df.empty:
        print("❌ 無法載入數據")
        return None, None
        
    # 轉換數據類型
    numeric_cols = ['open', 'high', 'low', 'close', 'volume']
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    # 確保日期格式
    df['date'] = pd.to_datetime(df['date'])
    
    # 獲取最新日期
    latest_date = df['date'].max().strftime('%Y-%m-%d')
    print(f"最新數據日期: {latest_date}")
    
    # 計算 52 週報酬率和 RS Rating
    print("計算 RS Ratings...", flush=True)
    df['return_52w'] = df.groupby('sid')['close'].pct_change(periods=252)
    df['rs_rating'] = df.groupby('date')['return_52w'].transform(
        lambda x: x.rank(pct=True) * 100
    )
    
    # 計算 52 週高點
    df['high_52w'] = df.groupby('sid')['high'].transform(
        lambda x: x.rolling(window=252, min_periods=1).max()
    )
    
    # 轉換回字串日期
    df['date'] = df['date'].dt.strftime('%Y-%m-%d')
    
    # 轉換其他欄位
    for col in ['open', 'high', 'low', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    df.dropna(subset=['sid', 'date', 'close'], inplace=True)
    
    # 計算移動平均線
    print("計算技術指標...", flush=True)
    df['ma50'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(50).mean())
    df['ma150'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(150).mean())
    df['ma200'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(200).mean())
    df['low52'] = df.groupby('sid')['close'].transform(lambda x: x.rolling(252).min())
    df['vol_ma50'] = df.groupby('sid')['volume'].transform(lambda x: x.rolling(50).mean())
    
    return df, latest_date

def scan_latest_date(df):
    """掃描最新日期的股票"""
    # 找出最新日期
    latest_date = df['date'].max()
    print(f"\n掃描日期: {latest_date}", flush=True)
    
    # 獲取該日期的所有股票
    latest_stocks = df[df['date'] == latest_date]['sid'].unique()
    print(f"股票數量: {len(latest_stocks)}", flush=True)
    
    signals = []
    processed = 0
    
    for sid in latest_stocks:
        processed += 1
        if processed % 100 == 0:
            print(f"已處理 {processed}/{len(latest_stocks)} 檔股票...", flush=True)
        
        # 獲取該股票的歷史數據
        stock_df = df[df['sid'] == sid].reset_index(drop=True)
        n_rows = len(stock_df)
        
        if n_rows < WINDOW_DAYS:
            continue
        
        # 使用最新的視窗
        i = n_rows - 1
        window = stock_df.iloc[i - WINDOW_DAYS + 1 : i + 1]
        row_today = stock_df.iloc[i]
        
        # 確認是最新日期
        if row_today['date'] != latest_date:
            continue
        
        # 準備 MA 資訊
        ma_info = {
            'ma50': row_today['ma50'],
            'ma150': row_today['ma150'],
            'ma200': row_today['ma200'],
            'low52': row_today['low52']
        }
        
        # 獲取 RS Rating
        rs_rating = row_today['rs_rating'] if not pd.isna(row_today['rs_rating']) else 0.0
        high_52w = row_today['high_52w']
        
        # 檢測 CUP
        is_cup, cup_buy, cup_stop = detect_cup(window, ma_info, rs_rating=rs_rating)
        if is_cup:
            current_price = row_today['close']
            
            # 驗證 1: 型態是否完好（尚未破壞）
            if current_price <= cup_stop:
                continue  # 型態已破壞，跳過
            
            # 狀態判斷
            status = "等待突破"
            if current_price >= cup_buy:
                status = "已突破"
            
            # 計算距離與風險
            risk_pct = (cup_buy - cup_stop) / cup_buy * 100
            distance_pct = (cup_buy - current_price) / cup_buy * 100
            
            signals.append({
                'date': latest_date,
                'sid': sid,
                'name': row_today['name'],
                'pattern': 'CUP',
                'buy_price': round(cup_buy, 2),
                'stop_price': round(cup_stop, 2),
                'risk_pct': round(risk_pct, 2),
                'rs_rating': round(rs_rating, 1),
                'grade': 'N/A',
                'current_price': round(row_today['close'], 2),
                'distance_pct': round(distance_pct, 2),
                'status': status
            })
        
        # 檢測 HTF
        is_htf, htf_buy, htf_stop, htf_grade = detect_htf(window, rs_rating=rs_rating)
        if is_htf:
            current_price = row_today['close']
            
            # 驗證 1: 型態是否完好（尚未破壞）
            if current_price <= htf_stop:
                continue  # 型態已破壞，跳過
            
            # 狀態判斷
            status = "等待突破"
            if current_price >= htf_buy:
                status = "已突破"
            
            # 計算距離與風險
            risk_pct = (htf_buy - htf_stop) / htf_buy * 100
            distance_pct = (htf_buy - current_price) / htf_buy * 100
            
            signals.append({
                'date': latest_date,
                'sid': sid,
                'name': row_today['name'],
                'pattern': 'HTF',
                'buy_price': round(htf_buy, 2),
                'stop_price': round(htf_stop, 2),
                'risk_pct': round(risk_pct, 2),
                'rs_rating': round(rs_rating, 1),
                'grade': htf_grade if htf_grade else 'C',
                'current_price': round(row_today['close'], 2),
                'distance_pct': round(distance_pct, 2),
                'status': status
            })
        
        # 檢測 VCP（可選，因為表現不佳）
        # is_vcp, vcp_buy, vcp_stop = detect_vcp(window, row_today['vol_ma50'], row_today['ma50'], rs_rating=rs_rating, high_52w=high_52w)
        # if is_vcp:
        #     current_price = row_today['close']
        #     if current_price <= vcp_stop or current_price >= vcp_buy:
        #         continue
        #     ... (類似處理)
    
    return signals, latest_date

def generate_report(signals, scan_date):
    """生成報告"""
    if not signals:
        print("\n❌ 未發現符合條件的訊號")
        # Create empty report
        with open(OUTPUT_REPORT, 'w', encoding='utf-8') as f:
            f.write(f"# 股票訊號報告\n")
            f.write(f"**掃描日期**: {scan_date}\n")
            f.write(f"**訊號數量**: 0\n\n")
            f.write("---\n\n")
            f.write("本日無符合條件的型態訊號。\n")
        print(f"✅ 空報告已儲存至: {OUTPUT_REPORT}")
        
        # Create empty CSV with headers
        pd.DataFrame(columns=['date', 'sid', 'name', 'pattern', 'buy_price', 'stop_price', 'risk_pct', 'rs_rating', 'grade', 'current_price', 'distance_pct', 'status']).to_csv(OUTPUT_CSV, index=False)
        return
    
    # 轉換為 DataFrame
    df_signals = pd.DataFrame(signals)
    
    # 儲存 CSV
    df_signals.to_csv(OUTPUT_CSV, index=False)
    print(f"\n✅ 訊號已儲存至: {OUTPUT_CSV}")
    
    # 生成 Markdown 報告
    report_lines = []
    report_lines.append(f"# 股票訊號報告")
    report_lines.append(f"**掃描日期**: {scan_date}")
    report_lines.append(f"**訊號數量**: {len(signals)}\n")
    report_lines.append("---\n")
    
    # CUP 訊號
    cup_signals = df_signals[df_signals['pattern'] == 'CUP']
    if not cup_signals.empty:
        report_lines.append(f"## 🏆 CUP 型態訊號 ({len(cup_signals)} 檔)\n")
        report_lines.append("| 股票代號 | 股票名稱 | 當前價 | 買入價 | 停損價 | 距離% | 狀態 | RS Rating |")
        report_lines.append("|---------|---------|--------|--------|--------|-------|------|-----------|")
        for _, row in cup_signals.sort_values('distance_pct').iterrows():
            report_lines.append(
                f"| {row['sid']} | {row['name']} | {row['current_price']} | "
                f"{row['buy_price']} | {row['stop_price']} | {row['distance_pct']}% | "
                f"{row['status']} | {row['rs_rating']} |"
            )
        report_lines.append("\n**建議策略**: R=3.0, T=20 (目標 3R，20天出場)\n")
        report_lines.append("**註**: 距離% = 當前價距離買入價的百分比（負值代表已突破）\n")
        report_lines.append("---\n")
    
    # HTF 訊號
    htf_signals = df_signals[df_signals['pattern'] == 'HTF']
    if not htf_signals.empty:
        report_lines.append(f"## 🚀 HTF 型態訊號 ({len(htf_signals)} 檔)\n")
        report_lines.append("| 股票代號 | 股票名稱 | 當前價 | 買入價 | 停損價 | 距離% | 狀態 | Grade | RS Rating |")
        report_lines.append("|---------|---------|--------|--------|--------|-------|------|-------|-----------|")
        for _, row in htf_signals.sort_values('distance_pct').iterrows():
            report_lines.append(
                f"| {row['sid']} | {row['name']} | {row['current_price']} | "
                f"{row['buy_price']} | {row['stop_price']} | {row['distance_pct']}% | "
                f"{row['status']} | {row['grade']} | {row['rs_rating']} |"
            )
        report_lines.append("\n**建議策略**: Trig=1.5R, Trail=MA20 (追蹤止損)\n")
        report_lines.append("**註**: 距離% = 當前價距離買入價的百分比（負值代表已突破）\n")
        report_lines.append("---\n")
    
    # 輸出到終端
    print("\n" + "\n".join(report_lines))
    
    # 儲存 Markdown
    with open(OUTPUT_REPORT, 'w', encoding='utf-8') as f:
        f.write("\n".join(report_lines))
    print(f"✅ 報告已儲存至: {OUTPUT_REPORT}")

def main():
    """主程式"""
    print("=" * 60)
    print("每日股票訊號掃描器")
    print("=" * 60)
    
    # 1. 載入數據
    result = load_data()
    if result is None:
        return
    df, latest_date = result
    if df is None:
        return
    
    # 掃描最新日期
    signals, scan_date = scan_latest_date(df)
    
    # 生成報告
    generate_report(signals, scan_date)
    
    print("\n" + "=" * 60)
    print("掃描完成！")
    print("=" * 60)

if __name__ == "__main__":
    main()
