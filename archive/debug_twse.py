import sys
import os
import pandas as pd
import requests

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def debug_institutional(date_str):
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?date={date_str}&selectType=ALL&response=json"
    print(f"Fetching {url}...")
    
    response = requests.get(url)
    data = response.json()
    
    if data.get('stat') != 'OK':
        print("Stat not OK")
        return

    df = pd.DataFrame(data['data'], columns=data['fields'])
    print("\nOriginal Columns:")
    print(df.columns.tolist())
    
    # Simulate the renaming logic
    cols_map = {}
    for col in df.columns:
        if '證券代號' in col: cols_map[col] = 'sid'
        elif '證券名稱' in col: cols_map[col] = 'name'
        elif '外陸資買賣超股數' in col: cols_map[col] = 'foreign_net'
        elif '投信買賣超股數' in col: cols_map[col] = 'trust_net'
        elif '自營商買賣超股數' in col and '避險' not in col: cols_map[col] = 'dealer_net'
    
    print("\nMapping:")
    print(cols_map)
    
    df = df.rename(columns=cols_map)
    print("\nRenamed Columns:")
    print(df.columns.tolist())
    
    if 'dealer_net' in df.columns:
        dealer_col = df['dealer_net']
        print(f"\ndealer_net type: {type(dealer_col)}")
        if isinstance(dealer_col, pd.DataFrame):
            print("WARNING: dealer_net is a DataFrame (Duplicate columns?)")
            print(dealer_col.head())
        else:
            print("dealer_net is a Series")
            print(dealer_col.head())

if __name__ == "__main__":
    debug_institutional('20251118')
