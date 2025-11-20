import pandas as pd
import os
import glob

class DataLoader:
    def __init__(self, data_dir=None):
        if data_dir is None:
            self.data_dir = os.path.join(os.path.dirname(__file__), '../../data/raw/daily_quotes')
        else:
            self.data_dir = data_dir
            
    def load_data(self, start_date=None, end_date=None, days=None):
        """
        Load data from daily CSVs.
        Args:
            start_date (str): 'YYYY-MM-DD'
            end_date (str): 'YYYY-MM-DD'
            days (int): Load last N days (if start_date is None)
        """
        all_files = sorted(glob.glob(os.path.join(self.data_dir, "*.csv")))
        
        if not all_files:
            print("No data files found.")
            return pd.DataFrame()
            
        selected_files = []
        
        if start_date:
            # Filter by date range
            for f in all_files:
                date_str = os.path.basename(f).replace('.csv', '')
                if start_date <= date_str:
                    if end_date and date_str > end_date:
                        continue
                    selected_files.append(f)
        elif days:
            # Take last N files
            selected_files = all_files[-days:]
        else:
            # Default to all? Or last 365 days?
            # Let's default to all for now, but warn
            selected_files = all_files
            
        if not selected_files:
            return pd.DataFrame()
            
        print(f"Loading {len(selected_files)} daily files...")
        
        # Use list comprehension for faster loading
        dfs = [pd.read_csv(f) for f in selected_files]
        full_df = pd.concat(dfs, ignore_index=True)
        
        return full_df

# Global instance for easy import
loader = DataLoader()
