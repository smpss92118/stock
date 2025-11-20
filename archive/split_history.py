import pandas as pd
import os
import sys

# 添加 src 到路徑
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

INPUT_FILE = os.path.join(os.path.dirname(__file__), '../data/raw/2023_2025_daily_stock_info.csv')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '../data/raw/daily_quotes')

COL_NAMES = ['sid', 'name', 'date', 'open', 'high', 'low', 'close', 'volume']

def split_history():
    print(f"Reading {INPUT_FILE}...")
    # Read only necessary columns to save memory if needed, but dataset is manageable
    # The original file has no header
    df = pd.read_csv(INPUT_FILE, header=None, names=COL_NAMES + [f'col_{i}' for i in range(8, 20)])
    df = df[COL_NAMES]
    
    print("Filtering for individual stocks (4 digits, 1-9)...")
    # Ensure sid is string
    df['sid'] = df['sid'].astype(str)
    
    def is_valid_stock(sid):
        return len(sid) == 4 and sid[0] in '123456789'
        
    df = df[df['sid'].apply(is_valid_stock)]
    
    print("Grouping by date...")
    grouped = df.groupby('date')
    
    total_groups = len(grouped)
    print(f"Found {total_groups} unique dates.")
    
    for i, (date_str, group) in enumerate(grouped):
        # date_str is typically YYYY-MM-DD
        output_path = os.path.join(OUTPUT_DIR, f"{date_str}.csv")
        group.to_csv(output_path, index=False)
        
        if (i + 1) % 100 == 0:
            print(f"Processed {i + 1}/{total_groups} dates...")
            
    print("Done! All daily files created.")

if __name__ == "__main__":
    split_history()
