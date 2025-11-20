import sys
import os
import pandas as pd
import requests

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.crawlers.twse import TWSECrawler

def debug_twse_rows(date_str):
    crawler = TWSECrawler()
    print(f"Fetching quotes for {date_str}...")
    
    # Manually call fetch logic to see raw count
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={date_str}&type=ALL&response=json"
    print(f"Requesting {url}...")
    response = requests.get(url)
    data = response.json()
    
    if data['stat'] != 'OK':
        print(f"Stat: {data['stat']}")
        return

    print(f"Available keys: {data.keys()}")
    
    # Check tables
    if 'tables' in data:
        tables = data['tables']
        print(f"Found {len(tables)} tables")
        for i, table in enumerate(tables):
            print(f"Table {i} Title: {table.get('title')}")
            print(f"Table {i} Fields: {table.get('fields')}")
            print(f"Table {i} Rows: {len(table.get('data'))}")
            if '證券代號' in table.get('fields', []):
                print(f"*** Target Table Found at index {i} ***")
        return
    else:
        print("No tables found")
        return
    
    # Convert to DF
    df = pd.DataFrame(raw_data, columns=fields)
    
    # Filter logic check
    df_filtered = df.copy()
    
    # Rename
    df_filtered = df_filtered.rename(columns={
        '證券代號': 'sid',
        '證券名稱': 'name',
        '成交股數': 'TradeVolume',
        '成交筆數': 'Transaction',
        '成交金額': 'TradeValue',
        '開盤價': 'OpeningPrice',
        '最高價': 'HighestPrice',
        '最低價': 'LowestPrice',
        '收盤價': 'ClosingPrice',
        '漲跌(+/-)': 'Dir',
        '漲跌價差': 'Change'
    })
    
    # 1. Filter SID
    df_filtered = df_filtered[df_filtered['sid'].apply(lambda x: len(x) == 4 and x[0] in '123456789')]
    print(f"Rows after SID filter: {len(df_filtered)}")
    
    # 2. Clean numbers
    for col in ['TradeVolume', 'OpeningPrice', 'ClosingPrice']:
        df_filtered[col] = df_filtered[col].astype(str).str.replace(',', '')
        df_filtered[col] = pd.to_numeric(df_filtered[col], errors='coerce')
        
    # 3. Drop NaN
    before_drop = len(df_filtered)
    df_filtered.dropna(subset=['ClosingPrice', 'TradeVolume'], inplace=True)
    print(f"Rows after DropNA: {len(df_filtered)} (Dropped {before_drop - len(df_filtered)})")
    
    # Check dropped rows
    dropped = df[~df.index.isin(df_filtered.index) & df['證券代號'].apply(lambda x: len(x) == 4 and x[0] in '123456789')]
    if not dropped.empty:
        print("\nSample Dropped Rows:")
        print(dropped[['證券代號', '證券名稱', '收盤價', '成交股數']].head())

if __name__ == "__main__":
    debug_twse_rows('20251120')
