import subprocess
import sys
import os
from datetime import datetime
import pandas as pd

import shutil

# Add project root to path - 指向原始 stock 目錄
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import config
# from src.utils.email_sender import send_email # Disabled

def run_script(script_name):
    """Run a python script located in scripts/ directory"""
    script_path = os.path.join(config.SCRIPTS_DIR, script_name)
    print(f"\n>>> Running {script_name}...")
    
    try:
        # Don't capture output to allow tqdm and real-time progress display
        result = subprocess.run(
            [sys.executable, script_path], 
            check=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running {script_name}")
        return False

def generate_report_content():
    """Parse reports and generate summary content"""
    from datetime import timedelta
    
    today = datetime.now()
    body = f"# Stock Bot Report - {today.strftime('%Y-%m-%d')}\n\n"
    
    # 1. Daily Scan Report (Today's signals)
    report_path = os.path.join(config.DATA_DIR, 'processed/latest_signals_report.md')
    if os.path.exists(report_path):
        with open(report_path, 'r') as f:
            body += "## Daily Scan Results (Today)\n"
            body += f.read()
            body += "\n\n"
    else:
        body += "⚠️ No daily scan report found.\n\n"
    
    # 2. Weekly Signal History (Past 7 days from pattern_analysis_result.csv)
    body += "---\n\n## 📅 過去一週訊號彙整\n\n"
    
    pattern_result_path = os.path.join(config.DATA_DIR, 'processed/pattern_analysis_result.csv')
    if os.path.exists(pattern_result_path):
        try:
            # Load pattern analysis results
            df_all = pd.read_csv(pattern_result_path)
            df_all['date'] = pd.to_datetime(df_all['date'])
            
            # Filter for past 7 days
            end_date = today
            start_date = today - timedelta(days=7)
            df_week = df_all[(df_all['date'] >= start_date) & (df_all['date'] <= end_date)].copy()
            
            if not df_week.empty:
                # Get current prices (use the close price from the data)
                weekly_signals = []
                
                # Process CUP patterns
                cup_df = df_week[df_week['is_cup'] == True].copy()
                if not cup_df.empty:
                    for _, row in cup_df.iterrows():
                        # Calculate distance and status
                        current_price = row['close']
                        buy_price = row['cup_buy_price']
                        stop_price = row['cup_stop_price']
                        
                        if pd.notna(buy_price) and pd.notna(stop_price):
                            distance_pct = (buy_price - current_price) / buy_price * 100
                            status = "等待突破" if current_price < buy_price else "已突破"
                            
                            # Only include if pattern is not broken
                            if current_price > stop_price:
                                weekly_signals.append({
                                    'date': row['date'].strftime('%Y-%m-%d'),
                                    'sid': row['sid'],
                                    'pattern': 'CUP',
                                    'current_price': round(current_price, 2),
                                    'buy_price': round(buy_price, 2),
                                    'stop_price': round(stop_price, 2),
                                    'distance_pct': round(distance_pct, 2),
                                    'status': status,
                                    'grade': 'N/A',
                                    'rs_rating': 'N/A'
                                })
                
                # Process HTF patterns
                htf_df = df_week[df_week['is_htf'] == True].copy()
                if not htf_df.empty:
                    for _, row in htf_df.iterrows():
                        current_price = row['close']
                        buy_price = row['htf_buy_price']
                        stop_price = row['htf_stop_price']
                        
                        if pd.notna(buy_price) and pd.notna(stop_price):
                            distance_pct = (buy_price - current_price) / buy_price * 100
                            status = "等待突破" if current_price < buy_price else "已突破"
                            
                            # Only include if pattern is not broken
                            if current_price > stop_price:
                                weekly_signals.append({
                                    'date': row['date'].strftime('%Y-%m-%d'),
                                    'sid': row['sid'],
                                    'pattern': 'HTF',
                                    'current_price': round(current_price, 2),
                                    'buy_price': round(buy_price, 2),
                                    'stop_price': round(stop_price, 2),
                                    'distance_pct': round(distance_pct, 2),
                                    'status': status,
                                    'grade': row.get('htf_grade', 'N/A'),
                                    'rs_rating': 'N/A'
                                })
                
                if weekly_signals:
                    df_signals = pd.DataFrame(weekly_signals)
                    df_signals = df_signals.sort_values(['date', 'distance_pct'], ascending=[False, True])
                    
                    # CUP signals
                    cup_signals = df_signals[df_signals['pattern'] == 'CUP']
                    if not cup_signals.empty:
                        body += f"### 🏆 CUP 型態訊號 ({len(cup_signals)} 檔)\n\n"
                        body += "| 日期 | 股票代號 | 當前價 | 買入價 | 停損價 | 距離% | 狀態 |\n"
                        body += "|------|---------|--------|--------|--------|-------|------|\n"
                        for _, row in cup_signals.iterrows():
                            body += (
                                f"| {row['date']} | {row['sid']} | {row['current_price']} | "
                                f"{row['buy_price']} | {row['stop_price']} | {row['distance_pct']}% | "
                                f"{row['status']} |\n"
                            )
                        body += "\n"
                    
                    # HTF signals
                    htf_signals = df_signals[df_signals['pattern'] == 'HTF']
                    if not htf_signals.empty:
                        body += f"### 🚀 HTF 型態訊號 ({len(htf_signals)} 檔)\n\n"
                        body += "| 日期 | 股票代號 | 當前價 | 買入價 | 停損價 | 距離% | 狀態 | Grade |\n"
                        body += "|------|---------|--------|--------|--------|-------|------|-------|\n"
                        for _, row in htf_signals.iterrows():
                            body += (
                                f"| {row['date']} | {row['sid']} | {row['current_price']} | "
                                f"{row['buy_price']} | {row['stop_price']} | {row['distance_pct']}% | "
                                f"{row['status']} | {row['grade']} |\n"
                            )
                        body += "\n"
                    
                    body += f"**統計**: 共 {len(df_signals)} 個訊號來自過去 7 天\n\n"
                else:
                    body += "過去一週無符合條件的型態訊號。\n\n"
            else:
                body += "過去一週無數據記錄。\n\n"
                
        except Exception as e:
            body += f"⚠️ 讀取歷史訊號時發生錯誤: {e}\n\n"
    else:
        body += "⚠️ 找不到 pattern_analysis_result.csv 檔案。\n\n"
    
    body += "---\n\n"
        
    # 3. Backtest Top Strategies
    backtest_csv = os.path.join(config.DATA_DIR, 'processed/backtest_results_v2.csv')
    if os.path.exists(backtest_csv):
        try:
            df = pd.read_csv(backtest_csv)
            
            # Filter for Limited Capital only
            # Note: 'Unlimited' also contains 'Limited', so we match '(Limited)'
            df = df[df['Strategy'].str.contains('(Limited)', regex=False, na=False)]
            
            body += "## Top 3 Strategies (Ann. Return %) - Limited Capital\n"
            top_ret = df.sort_values('Ann. Return %', ascending=False).head(3)
            for _, row in top_ret.iterrows():
                body += f"- **{row['Strategy']}** ({row['Settings']}): Ann. Return {row['Ann. Return %']}%, Sharpe {row['Sharpe']}\n"
            
            body += "\n## Top 3 Strategies (Sharpe) - Limited Capital\n"
            top_sharpe = df.sort_values('Sharpe', ascending=False).head(3)
            for _, row in top_sharpe.iterrows():
                body += f"- **{row['Strategy']}** ({row['Settings']}): Sharpe {row['Sharpe']}, Ann. Return {row['Ann. Return %']}%\n"
                
        except Exception as e:
            body += f"\n⚠️ Error parsing backtest results: {e}\n"
    else:
        body += "⚠️ No backtest results found.\n"
        
    return body

def main():
    print(f"=== Starting Daily Automation: {datetime.now()} ===")
    
    # 1. Update Data
    if not run_script('update_daily_data.py'):
        print("⚠️ Data update failed. Continuing...")
        
    # 2. Daily Scan
    if not run_script('run_daily_scan.py'):
        print("❌ Daily scan failed. Aborting.")
        return
        
    # 3. Historical Analysis (Update for backtest)
    if not run_script('run_historical_analysis.py'):
        print("⚠️ Historical analysis failed. Backtest might be outdated.")
        
    # 4. Backtest
    if not run_script('run_backtest.py'):
        print("⚠️ Backtest failed.")
        
    # 5. Save Reports Locally
    print("\n>>> Saving Reports Locally...")
    today_str = datetime.now().strftime('%Y-%m-%d')
    output_dir = os.path.join(config.PROJECT_ROOT, 'daily_tracking_stock', today_str)
    
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Created directory: {output_dir}")
        
    # Generate Summary Report
    summary_content = generate_report_content()
    summary_path = os.path.join(output_dir, 'daily_summary.md')
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(summary_content)
    print(f"Saved summary report to: {summary_path}")
    
    # Copy Files
    files_to_copy = [
        os.path.join(config.DATA_DIR, 'processed/latest_signals.csv'),
        os.path.join(config.DATA_DIR, 'processed/backtest_results_v2.csv')
        # Removed latest_signals_report.md as it is redundant
    ]
    
    for src in files_to_copy:
        if os.path.exists(src):
            dst = os.path.join(output_dir, os.path.basename(src))
            shutil.copy2(src, dst)
            print(f"Copied {os.path.basename(src)} to {output_dir}")
        else:
            print(f"⚠️ Source file not found: {src}")
    
    print("\n=== Automation Complete ===")

if __name__ == "__main__":
    main()
