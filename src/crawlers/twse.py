import requests
import pandas as pd
import time
import random
import json
from datetime import datetime

class TWSECrawler:
    def __init__(self):
        self.base_url = "https://www.twse.com.tw/rwd/zh"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": "https://www.twse.com.tw/zh/",
            "X-Requested-With": "XMLHttpRequest"
        }
        
    def _sleep(self):
        time.sleep(random.uniform(3, 5))  # Rate limiting
        
    def fetch_daily_quotes(self, date_str):
        """
        Fetch daily stock quotes (MI_INDEX)
        date_str: YYYYMMDD (e.g., '20251120')
        """
        url = f"{self.base_url}/afterTrading/MI_INDEX?date={date_str}&type=ALL&response=json"
        print(f"Fetching quotes for {date_str}...")
        
        try:
            self._sleep()
            response = requests.get(url, headers=self.headers)
            data = response.json()
            
            if data.get('stat') != 'OK':
                print(f"Error or no data: {data.get('stat')}")
                return None
                
            # Parse MI_INDEX (Table 9 usually contains stock data)
            # We need to find the table with fields like "證券代號", "證券名稱", ...
            target_table = None
            for table in data.get('tables', []):
                if '證券代號' in table.get('fields', []) and '收盤價' in table.get('fields', []):
                    target_table = table
                    break
            
            if not target_table:
                print("Could not find stock data table")
                return None
                
            df = pd.DataFrame(target_table['data'], columns=target_table['fields'])
            
            # Clean data
            # 1. Filter out non-stock entries (length > 4 usually warrants/bonds, but we keep 4-digit stocks)
            # Actually user wants all stocks. Let's keep standard filtering if needed.
            # For now, keep everything and let downstream handle it, or filter by length of code.
            
            # Rename columns to match our system
            # Our system uses: sid, name, date, open, high, low, close, volume
            # TWSE fields: 證券代號, 證券名稱, 成交股數, 成交筆數, 成交金額, 開盤價, 最高價, 最低價, 收盤價, ...
            
            rename_map = {
                '證券代號': 'sid',
                '證券名稱': 'name',
                '成交股數': 'volume',
                '開盤價': 'open',
                '最高價': 'high',
                '最低價': 'low',
                '收盤價': 'close'
            }
            
            df = df.rename(columns=rename_map)
            
            # Add date column
            formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            df['date'] = formatted_date
            
            # Select and reorder columns
            cols = ['sid', 'name', 'date', 'open', 'high', 'low', 'close', 'volume']
            df = df[cols]
            
            # Clean numeric columns (remove commas, handle '--')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(str).str.replace(',', '').str.replace('--', 'NaN')
                # Convert volume to integer (TWSE is in shares)
                if col == 'volume':
                     df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
                else:
                     df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Filter out invalid rows (e.g. empty prices)
            df = df.dropna(subset=['close'])
            
            # Filter for individual stocks only: 4 digits, starts with 1-9
            # Ensure sid is string
            df['sid'] = df['sid'].astype(str)
            
            def is_valid_stock(sid):
                return len(sid) == 4 and sid[0] in '123456789'
                
            df = df[df['sid'].apply(is_valid_stock)]
            
            return df
            
        except Exception as e:
            print(f"Exception fetching quotes: {e}")
            return None

    def fetch_institutional(self, date_str):
        """
        Fetch institutional trading data (T86)
        date_str: YYYYMMDD
        """
        url = f"{self.base_url}/fund/T86?date={date_str}&selectType=ALL&response=json"
        print(f"Fetching institutional data for {date_str}...")
        
        try:
            self._sleep()
            response = requests.get(url, headers=self.headers)
            data = response.json()
            
            if data.get('stat') != 'OK':
                return None
                
            # Check if response contains 'tables' (New format)
            if 'tables' in data:
                tables = data['tables']
                target_table = None
                for table in tables:
                    fields = table.get('fields', [])
                    if '證券代號' in fields and '收盤價' in fields: # Note: '收盤價' is typically for daily quotes, not institutional data.
                        target_table = table
                        break
                
                if target_table:
                    fields = target_table['fields']
                    raw_data = target_table['data']
                else:
                    print(f"Error: Could not find stock data table in response for {date_str}")
                    return None
            # Fallback to old format
            elif 'fields9' in data and 'data9' in data:
                fields = data['fields9']
                raw_data = data['data9']
            elif 'fields8' in data and 'data8' in data:
                fields = data['fields8']
                raw_data = data['data8']
            else:
                # Original logic for T86 usually has data and fields directly
                if not data.get('data') or not data.get('fields'):
                    print(f"Error: Unexpected data format for {date_str}")
                    return None
                fields = data['fields']
                raw_data = data['data']
                
            df = pd.DataFrame(raw_data, columns=fields)
            
            # Rename columns (Foreign, Investment Trust, Dealer)
            # Fields: 證券代號, 證券名稱, 外陸資買賣超股數(不含外資自營商), 投信買賣超股數, 自營商買賣超股數, ...
            # We want: sid, name, foreign_net, trust_net, dealer_net
            
            rename_map = {
                '證券代號': 'sid',
                '證券名稱': 'name',
                '外陸資買賣超股數(不含外資自營商)': 'foreign_net',
                '投信買賣超股數': 'trust_net',
                '自營商買賣超股數': 'dealer_net'
            }
            
            # Note: Column names might vary slightly over time, need robust matching
            # Let's try to map by index or partial name if exact match fails?
            # For now assume standard names.
            
            # Handle potential column name variations
            cols_map = {}
            for col in df.columns:
                if '證券代號' in col: cols_map[col] = 'sid'
                elif '證券名稱' in col: cols_map[col] = 'name'
                elif '外陸資買賣超股數' in col: cols_map[col] = 'foreign_net'
                elif '投信買賣超股數' in col: cols_map[col] = 'trust_net'
                elif '自營商買賣超股數' in col and '避險' not in col: cols_map[col] = 'dealer_net' # Total dealer
            
            df = df.rename(columns=cols_map)
            
            # Keep only relevant columns
            target_cols = ['sid', 'name', 'foreign_net', 'trust_net', 'dealer_net']
            # Ensure columns exist
            for c in target_cols:
                if c not in df.columns:
                    df[c] = 0
            
            df = df[target_cols]
            
            # Clean numbers
            for col in ['foreign_net', 'trust_net', 'dealer_net']:
                # Ensure we are working with strings first, then replace comma
                # If it's already numeric (somehow), astype(str) handles it.
                # The issue might be that apply is receiving the whole series if not careful?
                # No, apply on Series works element-wise.
                # The error '0 0\n1 0...' suggests we might be trying to convert a Series to float directly somewhere?
                # Ah, wait. If I did df[col] = df[col].apply(...), that's correct.
                # But maybe the previous failed attempt left it in a weird state? No, it's a fresh fetch.
                # Let's use a more robust way:
                df[col] = df[col].astype(str).str.replace(',', '')
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
            return df
            
        except Exception as e:
            print(f"Exception fetching institutional: {e}")
            return None

    def fetch_market_index(self, date_str):
        """
        Fetch market index data (MI_INDEX)
        """
        # The index data is also in MI_INDEX but different table
        url = f"{self.base_url}/afterTrading/MI_INDEX?date={date_str}&type=ALL&response=json"
        
        try:
            self._sleep()
            response = requests.get(url, headers=self.headers)
            data = response.json()
            
            if data.get('stat') != 'OK':
                return None
                
            # Index table usually first or second
            # Fields: 指數, 收盤指數, ...
            target_table = None
            for table in data.get('tables', []):
                if '指數' in table.get('fields', []) and '收盤指數' in table.get('fields', []):
                    target_table = table
                    break
            
            if not target_table:
                return None
                
            df = pd.DataFrame(target_table['data'], columns=target_table['fields'])
            
            # Find '發行量加權股價指數' (TAIEX)
            taiex = df[df['指數'] == '發行量加權股價指數']
            if taiex.empty:
                return None
                
            close_idx = taiex['收盤指數'].values[0].replace(',', '')
            
            return {
                'date': f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}",
                'close': float(close_idx)
            }
            
        except Exception as e:
            print(f"Exception fetching index: {e}")
            return None
