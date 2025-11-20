import requests
import pandas as pd
import time
import random
from datetime import datetime

class TPEXCrawler:
    def __init__(self):
        self.base_url = "https://www.tpex.org.tw/www/zh-tw"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Referer": "https://www.tpex.org.tw/zh-tw/mainboard/trading/info/pricing.html",
            "X-Requested-With": "XMLHttpRequest"
        }
        
    def _sleep(self):
        time.sleep(random.uniform(3, 5))  # Rate limiting
        
    def fetch_daily_quotes(self, date_str):
        """
        Fetch daily stock quotes from TPEX
        date_str: YYYYMMDD (e.g., '20251120')
        Returns: DataFrame with columns [sid, name, date, open, high, low, close, volume]
        """
        # Convert YYYYMMDD to YYYY/MM/DD format
        try:
            dt = datetime.strptime(date_str, '%Y%m%d')
            formatted_date = dt.strftime('%Y/%m/%d')
            output_date = dt.strftime('%Y-%m-%d')
        except:
            print(f"Invalid date format: {date_str}")
            return None
        
        url = f"{self.base_url}/afterTrading/dailyQuotes"
        print(f"Fetching TPEX quotes for {output_date}...")
        
        # POST data
        data = {
            'date': formatted_date,
            'id': '',
            'response': 'json'
        }
        
        try:
            self._sleep()
            response = requests.post(url, headers=self.headers, data=data, timeout=30)
            response.encoding = 'utf-8'  # Ensure proper Chinese character handling
            
            json_data = response.json()
            
            # Check if we have tables
            if 'tables' not in json_data or len(json_data['tables']) == 0:
                print(f"No data returned for {output_date}")
                return None
            
            # Find the main stock table (上櫃股票行情)
            target_table = None
            for table in json_data['tables']:
                if '代號' in table.get('fields', []) and '收盤' in table.get('fields', []):
                    target_table = table
                    break
            
            if not target_table:
                print("Could not find stock data table")
                return None
            
            # Create DataFrame
            df = pd.DataFrame(target_table['data'], columns=target_table['fields'])
            
            # Filter for 4-digit stock codes starting with 1-9 (exclude ETFs, warrants, etc.)
            df = df[df['代號'].str.match(r'^[1-9]\d{3}$', na=False)]
            
            if df.empty:
                print("No valid stock data after filtering")
                return None
            
            # Map columns to standard format
            result_df = pd.DataFrame({
                'sid': df['代號'],
                'name': df['名稱'],
                'date': output_date,
                'open': pd.to_numeric(df['開盤'].str.replace(',', ''), errors='coerce'),
                'high': pd.to_numeric(df['最高'].str.replace(',', ''), errors='coerce'),
                'low': pd.to_numeric(df['最低'].str.replace(',', ''), errors='coerce'),
                'close': pd.to_numeric(df['收盤'].str.replace(',', ''), errors='coerce'),
                'volume': pd.to_numeric(df['成交股數'].str.replace(',', ''), errors='coerce')
            })
            
            # Remove rows with missing critical data
            result_df = result_df.dropna(subset=['sid', 'close'])
            
            print(f"✓ Fetched {len(result_df)} TPEX stocks for {output_date}")
            return result_df
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching TPEX data: {e}")
            return None
        except Exception as e:
            print(f"Error parsing TPEX data: {e}")
            import traceback
            traceback.print_exc()
            return None

if __name__ == "__main__":
    # Test the crawler
    crawler = TPEXCrawler()
    df = crawler.fetch_daily_quotes('20251120')
    if df is not None:
        print(f"\nSample data:")
        print(df.head(10))
        print(f"\nTotal stocks: {len(df)}")
        print(f"Date range: {df['date'].unique()}")
