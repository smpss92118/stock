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

if __name__ == '__main__':
    # Example usage:
    stock_data = fetch_all_stock_data()
    if not stock_data.empty:
        print(f"Successfully fetched data for {stock_data['stock_code'].nunique()} stocks.")
        print(stock_data.head())
    else:
        print("Could not fetch any stock data.")
