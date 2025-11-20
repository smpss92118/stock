import sys
import os
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

# 設定檔案路徑
MARKET_DATA_FILE = os.path.join(os.path.dirname(__file__), '../data/raw/market_data.csv')
TICKER = '^TWII' # Taiwan Weighted Index

def download_market_data():
    print(f"Downloading market data for {TICKER}...")
    
    # Download data from 2023-01-01 to present (matching stock data range)
    # Stock data is 2023-2025, so let's get same range.
    start_date = "2023-01-01"
    end_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    try:
        df = yf.download(TICKER, start=start_date, end=end_date)
        if df.empty:
            print("Error: No data downloaded.")
            return
            
        # Reset index to get Date column
        df.reset_index(inplace=True)
        
        # Flatten columns if MultiIndex (yfinance update)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # Rename columns to lowercase
        df.columns = [c.lower() for c in df.columns]
        
        # Ensure date format
        df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
        
        # Calculate MAs
        df['market_ma50'] = df['close'].rolling(50).mean()
        df['market_ma150'] = df['close'].rolling(150).mean()
        df['market_ma200'] = df['close'].rolling(200).mean()
        
        # Save
        df.to_csv(OUTPUT_FILE, index=False)
        print(f"Market data saved to {OUTPUT_FILE} ({len(df)} rows)")
        print(df.tail())
        
    except Exception as e:
        print(f"Failed to download data: {e}")

if __name__ == "__main__":
    download_market_data()
