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
    # 轉換日期格式: 20241120
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    twse_date = date_obj.strftime('%Y%m%d')
    
    # 正確的 TWSE API endpoint
    url = 'https://www.twse.com.tw/rwd/zh/fund/T86'
    
    params = {
        'date': twse_date,
        'selectType': 'ALLBUT0999',
        'response': 'json'
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    
    try:
        print(f"📥 爬取 TWSE 數據: {date_str}")
        response = requests.get(url, params=params, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"  ❌ HTTP Error: {response.status_code}")
            return None
        
        # 解析 JSON
        data = response.json()
        
        if data.get('stat') != 'OK':
            print(f"  ⚠️ API 返回錯誤: {data.get('stat')}")
            return None
        
        if 'data' not in data or not data['data']:
            print(f"  ⚠️ 無數據")
            return None
        
        # 解析數據
        # fields: [證券代號, 證券名稱, 外陸資買進, 外陸資賣出, 外陸資買賣超, ...、投信買進, 投信賣出, 投信買賣超, ...]
        records = []
        for row in data['data']:
            try:
                # row[0]=代號, row[1]=名稱
                # row[2]=外資買, row[3]=外資賣, row[4]=外資淨
                # row[8]=投信買, row[9]=投信賣, row[10]=投信淨
                # row[11]=自營商淨
                # row[18]=三大法人淨
                records.append({
                    'date': date_str,
                    'sid': row[0],
                    'name': row[1].strip(),
                    'foreign_buy': int(row[2].replace(',', '')) if row[2] else 0,
                    'foreign_sell': int(row[3].replace(',', '')) if row[3] else 0,
                    'foreign_net': int(row[4].replace(',', '')) if row[4] else 0,
                    'investment_buy': int(row[8].replace(',', '')) if row[8] else 0,
                    'investment_sell': int(row[9].replace(',', '')) if row[9] else 0,
                    'investment_net': int(row[10].replace(',', '')) if row[10] else 0,
                    'dealer_net': int(row[11].replace(',', '')) if row[11] else 0,
                    'total_net': int(row[18].replace(',', '')) if row[18] else 0,
                    'exchange': 'TWSE'
                })
            except (ValueError, IndexError, KeyError) as e:
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
    # 轉換日期格式: 113/11/20 (民國年)
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    year = date_obj.year - 1911  # 轉民國年
    tpex_date = f"{year}/{date_obj.month:02d}/{date_obj.day:02d}"
    
    # 正確的 TPEX API endpoint
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
        try:
            data = response.json()
        except:
            print(f"  ⚠️ JSON 解析失敗")
            return None
        
        if not data or not isinstance(data, dict):
            print(f"  ⚠️ 無效的響應格式")
            return None
        
        # 檢查是否有數據
        if 'tables' not in data or not data['tables']:
            print(f"  ⚠️ 無數據")
            return None
        
        # tables[0] 包含數據
        table_data = data['tables'][0] if isinstance(data['tables'], list) else data['tables']
        if 'data' not in table_data or not table_data['data']:
            print(f"  ⚠️ 無數據")
            return None
        
        # 解析數據
        # data格式: [代號, 名稱, 外資買, 外資賣, 外資淨, ..., 投信買, 投信賣, 投信淨, ..., 自營商淨, ..., 三大法人淨]
        records = []
        for row in table_data['data']:
            try:
                # row[0]=代號, row[1]=名稱
                # row[2]=外資買, row[3]=外資賣, row[4]=外資淨
                # row[8]=投信買, row[9]=投信賣, row[10]=投信淨  
                # row[22]=三大法人淨 (最後一欄)
                records.append({
                    'date': date_str,
                    'sid': row[0],
                    'name': row[1].strip(),
                    'foreign_buy': int(row[2].replace(',', '')) if row[2] else 0,
                    'foreign_sell': int(row[3].replace(',', '')) if row[3] else 0,
                    'foreign_net': int(row[4].replace(',', '')) if row[4] else 0,
                    'investment_buy': int(row[8].replace(',', '')) if row[8] else 0,
                    'investment_sell': int(row[9].replace(',', '')) if row[9] else 0,
                    'investment_net': int(row[10].replace(',', '')) if row[10] else 0,
                    'dealer_net': int(row[11].replace(',', '')) if len(row) > 11 and row[11] else 0,
                    'total_net': int(row[22].replace(',', '')) if len(row) > 22 and row[22] else 0,
                    'exchange': 'TPEX'
                })
            except (ValueError, IndexError, KeyError) as e:
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
    
    # 只保留普通股票 (4 位且以 1-9 開頭)
    df_combined = df_combined[df_combined['sid'].astype(str).str.match(r'^[1-9]\d{3}$')]
    
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
