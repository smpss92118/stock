import sys
import os
import pandas as pd
from datetime import datetime, timedelta
import time

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.crawlers.twse import TWSECrawler
from src.crawlers.tpex import TPEXCrawler

DATA_DIR = os.path.join(os.path.dirname(__file__), '../data/raw')
QUOTES_DIR = os.path.join(DATA_DIR, 'daily_quotes')
INST_DIR = os.path.join(DATA_DIR, 'institutional')
MARKET_FILE = os.path.join(DATA_DIR, 'market_data.csv')

def get_last_date(directory):
    files = sorted([f for f in os.listdir(directory) if f.endswith('.csv')])
    if not files:
        return None
    last_file = files[-1]
    return datetime.strptime(last_file.replace('.csv', ''), '%Y-%m-%d').date()

def update_market_file(index_data):
    """Append new index data to market_data.csv"""
    if not index_data:
        return
        
    # Check if file exists
    if os.path.exists(MARKET_FILE):
        df = pd.read_csv(MARKET_FILE)
        # Normalize column names to lowercase for check
        df.columns = [c.lower() for c in df.columns]
        # Check if date already exists
        if index_data['date'] in df['date'].values:
            return
    else:
        df = pd.DataFrame(columns=['date', 'close'])
        
    new_row = pd.DataFrame([{'date': index_data['date'], 'close': index_data['close']}])
    # Append mode if file exists to avoid reading/writing huge file? 
    # Market data is small, reading/writing is fine.
    # But we need to preserve original columns if we just read/write.
    # Actually, let's just append to file directly to be safe and simple.
    
    write_header = not os.path.exists(MARKET_FILE)
    new_row.to_csv(MARKET_FILE, mode='a', header=write_header, index=False)
    print(f"Updated market index for {index_data['date']}")

def main():
    crawler = TWSECrawler()
    tpex_crawler = TPEXCrawler()
    
    # 1. Determine start date
    last_date = get_last_date(QUOTES_DIR)
    if not last_date:
        print("No existing data found. Please run split_history.py first or specify start date.")
        return
        
    start_date = last_date + timedelta(days=1)
    today = datetime.now().date()
    
    if start_date > today:
        print("Data is already up to date.")
        return
        
    print(f"Updating data from {start_date} to {today}...")
    
    current_date = start_date
    while current_date <= today:
        # Skip weekends (simple check, TWSE might also have holidays)
        if current_date.weekday() >= 5:
            print(f"Skipping weekend: {current_date}")
            current_date += timedelta(days=1)
            continue
            
        date_str = current_date.strftime('%Y%m%d')
        formatted_date = current_date.strftime('%Y-%m-%d')
        
        # A. Fetch Quotes
        quotes_twse = crawler.fetch_daily_quotes(date_str)
        quotes_tpex = tpex_crawler.fetch_daily_quotes(date_str)
        
        quotes_df = pd.DataFrame()
        if quotes_twse is not None and not quotes_twse.empty:
            quotes_df = pd.concat([quotes_df, quotes_twse], ignore_index=True)
            
        if quotes_tpex is not None and not quotes_tpex.empty:
            quotes_df = pd.concat([quotes_df, quotes_tpex], ignore_index=True)
            
        if not quotes_df.empty:
            # Save to CSV
            output_path = os.path.join(QUOTES_DIR, f"{formatted_date}.csv")
            quotes_df.to_csv(output_path, index=False)
            print(f"Saved quotes for {formatted_date} (Total: {len(quotes_df)})")
        else:
            print(f"No quotes data for {formatted_date} (Holiday?)")
            
        # B. Fetch Institutional (Disabled per user request)
        # inst_df = crawler.fetch_institutional(date_str)
        # if inst_df is not None and not inst_df.empty:
        #     output_path = os.path.join(INST_DIR, f"{formatted_date}.csv")
        #     inst_df.to_csv(output_path, index=False)
        #     print(f"Saved institutional data for {formatted_date}")
            
        # C. Fetch Market Index
        index_data = crawler.fetch_market_index(date_str)
        if index_data:
            update_market_file(index_data)
            
        current_date += timedelta(days=1)
        
    print("Update complete!")

if __name__ == "__main__":
    main()
