import requests
import pandas as pd
from datetime import datetime
import time

class InstitutionalCrawler:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }

    def fetch_twse_data(self, date_str):
        """
        Fetch TWSE institutional data
        Args:
            date_str: 'YYYY-MM-DD'
        """
        try:
            # Convert date to YYYYMMDD
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            twse_date = date_obj.strftime('%Y%m%d')
            
            url = 'https://www.twse.com.tw/rwd/zh/fund/T86'
            params = {
                'date': twse_date,
                'selectType': 'ALLBUT0999',
                'response': 'json'
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=30)
            if response.status_code != 200:
                print(f"  ❌ TWSE HTTP Error: {response.status_code}")
                return None
                
            data = response.json()
            
            if data.get('stat') != 'OK':
                # Common when no data (holiday)
                return None
                
            if 'data' not in data or not data['data']:
                return None
                
            records = []
            for row in data['data']:
                try:
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
                except (ValueError, IndexError, KeyError):
                    continue
                    
            return pd.DataFrame(records) if records else None
            
        except Exception as e:
            print(f"  ❌ TWSE Fetch Error: {e}")
            return None

    def fetch_tpex_data(self, date_str):
        """
        Fetch TPEX institutional data
        Args:
            date_str: 'YYYY-MM-DD'
        """
        try:
            # Convert date to ROC format YYY/MM/DD
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            year = date_obj.year - 1911
            tpex_date = f"{year}/{date_obj.month:02d}/{date_obj.day:02d}"
            
            url = 'https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php'
            params = {
                'l': 'zh-tw',
                'd': tpex_date,
                'se': 'AL',
                't': 'D'
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=30)
            if response.status_code != 200:
                print(f"  ❌ TPEX HTTP Error: {response.status_code}")
                return None
                
            try:
                data = response.json()
            except:
                return None
                
            if not data or not isinstance(data, dict):
                return None
                
            if 'tables' not in data or not data['tables']:
                return None
                
            table_data = data['tables'][0] if isinstance(data['tables'], list) else data['tables']
            if 'data' not in table_data or not table_data['data']:
                return None
                
            records = []
            for row in table_data['data']:
                try:
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
                except (ValueError, IndexError, KeyError):
                    continue
                    
            return pd.DataFrame(records) if records else None
            
        except Exception as e:
            print(f"  ❌ TPEX Fetch Error: {e}")
            return None

    def fetch_daily_data(self, date_str):
        """
        Fetch and combine data from both exchanges
        Args:
            date_str: 'YYYY-MM-DD'
        Returns:
            DataFrame or None
        """
        print(f"📥 Fetching Institutional Data: {date_str}")
        
        # Fetch TWSE
        df_twse = self.fetch_twse_data(date_str)
        time.sleep(1) # Polite delay
        
        # Fetch TPEX
        df_tpex = self.fetch_tpex_data(date_str)
        
        dfs = []
        if df_twse is not None and not df_twse.empty:
            dfs.append(df_twse)
        if df_tpex is not None and not df_tpex.empty:
            dfs.append(df_tpex)
            
        if not dfs:
            print(f"  ⚠️ No institutional data found for {date_str}")
            return None
            
        df_combined = pd.concat(dfs, ignore_index=True)
        
        # Filter for common stocks (4 digits, starts with 1-9)
        df_combined = df_combined[df_combined['sid'].astype(str).str.match(r'^[1-9]\d{3}$')]
        
        if df_combined.empty:
            return None
            
        # Sort
        df_combined = df_combined.sort_values('sid').reset_index(drop=True)
        
        print(f"  ✅ Retrieved {len(df_combined)} records")
        return df_combined
