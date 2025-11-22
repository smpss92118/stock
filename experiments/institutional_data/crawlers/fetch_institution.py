#!/usr/bin/env python3
"""
三大法人買賣超數據爬蟲 (TWSE + TPEX)

功能:
1. 爬取單日三大法人買賣超數據
2. 支援 TWSE (上市) 和 TPEX (上櫃)
3. 儲存為 CSV 格式

使用:
    python fetch_institution.py --date 2024-11-21
    python fetch_institution.py  # 預設今天
"""

import requests
import pandas as pd
import argparse
from datetime import datetime, timedelta
import time
import os
from pathlib import Path

# 數據儲存路徑
RAW_DATA_DIR = Path(__file__).parent.parent / 'data' / 'raw'
RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

def fetch_twse_institutional(date_str):
    """
    爬取 TWSE (上市) 三大法人數據
    
    Args:
        date_str: 日期字串 'YYYY-MM-DD'
    
    Returns:
        DataFrame or None
    """
    # 轉換日期格式: 20241121
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    twse_date = date_obj.strftime('%Y%m%d')
    
    url = 'https://www.twse.com.tw/fund/T86'
    
    params = {
        'response': 'csv',
        'date': twse_date,
        'selectType': 'ALLBUT0999'
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    
    try:
        print(f"📥 爬取 TWSE 數據: {date_str}")
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.encoding = 'big5'
        
        if response.status_code != 200:
            print(f"  ❌ HTTP Error: {response.status_code}")
            return None
        
        # 解析 CSV (TWSE 的 CSV 格式比較特殊)
        lines = response.text.strip().split('\n')
        
        # 找到數據起始行 (通常第一行是標題)
        data_lines = [line for line in lines if line.strip() and '證券代號' not in line]
        
        if len(data_lines) < 2:
            print(f"  ⚠️ 無數據或格式錯誤")
            return None
        
        # 解析數據
        records = []
        for line in data_lines[1:]:  # skip header
            parts = [p.strip().replace(',', '') for p in line.split(',')]
            if len(parts) >= 12:  # 確保欄位完整
                try:
                    records.append({
                        'date': date_str,
                        'sid': parts[0],
                        'name': parts[1],
                        'foreign_buy': int(parts[2]) if parts[2] and parts[2].isdigit() else 0,
                        'foreign_sell': int(parts[3]) if parts[3] and parts[3].isdigit() else 0,
                        'foreign_net': int(parts[4]) if parts[4] else 0,
                        'investment_buy': int(parts[5]) if parts[5] and parts[5].isdigit() else 0,
                        'investment_sell': int(parts[6]) if parts[6] and parts[6].isdigit() else 0,
                        'investment_net': int(parts[7]) if parts[7] else 0,
                        'dealer_buy': int(parts[8]) if parts[8] and parts[8].isdigit() else 0,
                        'dealer_sell': int(parts[9]) if parts[9] and parts[9].isdigit() else 0,
                        'dealer_net': int(parts[10]) if parts[10] else 0,
                        'total_net': int(parts[11]) if parts[11] else 0,
                        'exchange': 'TWSE'
                    })
                except (ValueError, IndexError) as e:
                    continue
        
        if not records:
            print(f"  ⚠️ 無有效數據")
            return None
        
        df = pd.DataFrame(records)
        print(f"  ✅ 取得 {len(df)} 筆數據")
        return df
        
    except Exception as e:
        print(f"  ❌ 爬取失敗: {e}")
        return None


def fetch_tpex_institutional(date_str):
    """
    爬取 TPEX (上櫃) 三大法人數據
    
    Args:
        date_str: 日期字串 'YYYY-MM-DD'
    
    Returns:
        DataFrame or None
    """
    # 轉換日期格式: 113/11/21 (民國年)
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    year = date_obj.year - 1911  # 轉民國年
    tpex_date = f"{year}/{date_obj.month:02d}/{date_obj.day:02d}"
    
    url = 'https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php'
    
    params = {
        'l': 'zh-tw',
        'd': tpex_date,
        'se': 'AL',  # All stocks
        't': 'D'      # Daily
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    
    try:
        print(f"📥 爬取 TPEX 數據: {date_str}")
        response = requests.get(url, params=params, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"  ❌ HTTP Error: {response.status_code}")
            return None
        
        # TPEX 返回 JSON
        data = response.json()
        
        if 'aaData' not in data or not data['aaData']:
            print(f"  ⚠️ 無數據")
            return None
        
        # 解析數據
        records = []
        for row in data['aaData']:
            try:
                records.append({
                    'date': date_str,
                    'sid': row[0],
                    'name': row[1],
                    'foreign_buy': int(row[2].replace(',', '')) if row[2] else 0,
                    'foreign_sell': int(row[3].replace(',', '')) if row[3] else 0,
                    'foreign_net': int(row[4].replace(',', '')) if row[4] else 0,
                    'investment_buy': int(row[5].replace(',', '')) if row[5] else 0,
                    'investment_sell': int(row[6].replace(',', '')) if row[6] else 0,
                    'investment_net': int(row[7].replace(',', '')) if row[7] else 0,
                    'dealer_buy': int(row[8].replace(',', '')) if row[8] else 0,
                    'dealer_sell': int(row[9].replace(',', '')) if row[9] else 0,
                    'dealer_net': int(row[10].replace(',', '')) if row[10] else 0,
                    'total_net': int(row[11].replace(',', '')) if row[11] else 0,
                    'exchange': 'TPEX'
                })
            except (ValueError, IndexError, KeyError):
                continue
        
        if not records:
            print(f"  ⚠️ 無有效數據")
            return None
        
        df = pd.DataFrame(records)
        print(f"  ✅ 取得 {len(df)} 筆數據")
        return df
        
    except Exception as e:
        print(f"  ❌ 爬取失敗: {e}")
        return None


def fetch_and_save(date_str):
    """
    爬取並儲存單日三大法人數據
    
    Args:
        date_str: 日期字串 'YYYY-MM-DD'
    
    Returns:
        bool: 是否成功
    """
    print(f"\n{'='*60}")
    print(f"爬取日期: {date_str}")
    print(f"{'='*60}")
    
    # 爬取 TWSE
    df_twse = fetch_twse_institutional(date_str)
    time.sleep(2)  # 避免請求過快
    
    # 爬取 TPEX
    df_tpex = fetch_tpex_institutional(date_str)
    
    # 合併數據
    dfs = [df for df in [df_twse, df_tpex] if df is not None]
    
    if not dfs:
        print("\n❌ 無法取得任何數據")
        return False
    
    df_combined = pd.concat(dfs, ignore_index=True)
    
    # 儲存檔案
    filename = f"institution_{date_str}.csv"
    filepath = RAW_DATA_DIR / filename
    df_combined.to_csv(filepath, index=False, encoding='utf-8-sig')
    
    print(f"\n✅ 儲存完成: {filepath}")
    print(f"   總筆數: {len(df_combined)}")
    print(f"   TWSE: {len(df_combined[df_combined['exchange']=='TWSE'])}")
    print(f"   TPEX: {len(df_combined[df_combined['exchange']=='TPEX'])}")
    
    return True


def main():
    parser = argparse.ArgumentParser(description='爬取三大法人買賣超數據')
    parser.add_argument('--date', type=str, 
                       default=datetime.now().strftime('%Y-%m-%d'),
                       help='日期 (YYYY-MM-DD), 預設今天')
    
    args = parser.parse_args()
    
    success = fetch_and_save(args.date)
    
    if success:
        print("\n🎉 爬取成功！")
    else:
        print("\n❌ 爬取失敗")
        exit(1)


if __name__ == "__main__":
    main()
