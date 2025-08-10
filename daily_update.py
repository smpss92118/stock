import configparser
import sys
from datetime import date, datetime

from stock_crawler.database import (append_data_to_db, check_data_exists,
                                    get_db_engine)
from stock_crawler.fetcher import fetch_daily_data

TABLE_NAME = 'taiwan_stock_daily'

def main():
    """
    Main function for the daily stock data update process.
    - Checks if it's a weekday.
    - Checks if data for today already exists.
    - Fetches, validates, and stores new data if necessary.
    """
    today = date.today()

    # 1. Check for Weekend
    # weekday() returns 0 for Monday and 6 for Sunday.
    if today.weekday() >= 5:
        print(f"{today}: It's a weekend. No data to fetch.")
        sys.exit(0)

    # 2. Read Configuration
    config = configparser.ConfigParser()
    config.read('config.ini')

    if 'database' not in config:
        print("Error: 'database' section not found in config.ini. Please run the backfill first and set up the config.")
        sys.exit(1)

    db_config = config['database']

    # 3. Connect to Database
    try:
        engine = get_db_engine(
            user=db_config.get('user'),
            password=db_config.get('password'),
            host=db_config.get('host'),
            database=db_config.get('database')
        )
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        sys.exit(1)

    # 4. Check if Data Exists
    print(f"Checking if data for {today} already exists...")
    if check_data_exists(today, TABLE_NAME, engine):
        print(f"Data for {today} already exists in the database. Nothing to do.")
        sys.exit(0)

    print("No data found for today. Proceeding to fetch...")

    # 5. Fetch Daily Data
    # Note: This can be a very long process.
    daily_df = fetch_daily_data(today)

    # 6. Verify Fetched Data
    if daily_df.empty:
        print(f"No trading data was returned for {today}. It might be a holiday.")
        sys.exit(0)

    # Convert the 'date' column in the DataFrame to Python date objects for comparison
    # The fetcher already does this, but we do it again to be safe.
    daily_df['date'] = pd.to_datetime(daily_df['date']).dt.date

    first_date_in_data = daily_df['date'].iloc[0]
    if first_date_in_data != today:
        print(f"Error: Fetched data is for '{first_date_in_data}', but expected '{today}'.")
        print("This can happen if the market data for today is not yet available.")
        sys.exit(1)

    print(f"Successfully fetched {len(daily_df)} records for {today}.")

    # 7. Append to Database
    print("Appending new data to the database...")
    try:
        append_data_to_db(daily_df, TABLE_NAME, engine)
        print("Daily update complete.")
    except Exception as e:
        print(f"Error appending data to the database: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
