import twstock
import pandas as pd
from datetime import datetime, timedelta

def fetch_all_stock_data():
    """
    Fetches the last 5 years of daily stock data for all Taiwanese stocks.

    Returns:
        pandas.DataFrame: A DataFrame containing the stock data, or an empty
                          DataFrame if no data could be fetched.
    """
    five_years_ago = datetime.now() - timedelta(days=5*365)
    all_data = []

    for stock_code in twstock.codes:
        stock = twstock.Stock(stock_code)
        data = stock.fetch_from(five_years_ago.year, five_years_ago.month)
        if data:
            df = pd.DataFrame(data)
            df['stock_code'] = stock_code
            all_data.append(df)

    if not all_data:
        return pd.DataFrame()

    return pd.concat(all_data, ignore_index=True)

def fetch_daily_data(target_date):
    """
    Fetches daily stock data for all Taiwanese stocks for a specific date.

    Args:
        target_date (datetime.date): The specific date to fetch data for.

    Returns:
        pandas.DataFrame: A DataFrame containing the stock data for the given date,
                          or an empty DataFrame if no data could be fetched.
    """
    daily_data = []
    total_codes = len(twstock.codes)

    print(f"Fetching data for {target_date.strftime('%Y-%m-%d')}...")

    for i, stock_code in enumerate(twstock.codes):
        # Print progress to give feedback on the long-running process
        if (i + 1) % 100 == 0:
            print(f"  Processed {i + 1}/{total_codes} stocks...")

        stock = twstock.Stock(stock_code)
        # Fetch data for the entire month, as twstock doesn't support daily fetching directly
        monthly_data = stock.fetch(target_date.year, target_date.month)

        # Filter for the specific day
        for data in monthly_data:
            if data.date.date() == target_date:
                record = data._asdict()
                record['stock_code'] = stock_code
                daily_data.append(record)
                break  # Found the data for the target date, move to the next stock

    if not daily_data:
        return pd.DataFrame()

    df = pd.DataFrame(daily_data)
    # Ensure the date column is just the date part
    df['date'] = pd.to_datetime(df['date']).dt.date
    return df


if __name__ == '__main__':
    # Example usage for backfill:
    # print("--- Running Backfill (last 5 years) ---")
    # stock_data = fetch_all_stock_data()
    # if not stock_data.empty:
    #     print(f"Successfully fetched backfill data for {stock_data['stock_code'].nunique()} stocks.")
    #     print(stock_data.head())
    # else:
    #     print("Could not fetch any backfill stock data.")

    # Example usage for daily fetch:
    from datetime import date
    print("\n--- Running Daily Fetch ---")
    today_data = fetch_daily_data(date.today())
    if not today_data.empty:
        print(f"Successfully fetched daily data for {today_data['stock_code'].nunique()} stocks.")
        print(today_data.head())
    else:
        print("Could not fetch any daily stock data for today.")
