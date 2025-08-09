import configparser
from stock_crawler.fetcher import fetch_all_stock_data
from stock_crawler.database import get_db_engine, save_data_to_db

def main():
    """
    Main function to fetch stock data and save it to the database.
    """
    config = configparser.ConfigParser()
    config.read('config.ini')

    db_config = config['database']
    user = db_config.get('user')
    password = db_config.get('password')
    host = db_config.get('host')
    database = db_config.get('database')

    print("Fetching stock data...")
    stock_data = fetch_all_stock_data()

    if not stock_data.empty:
        print("Connecting to the database...")
        engine = get_db_engine(user, password, host, database)

        print("Saving data to the database...")
        save_data_to_db(stock_data, 'taiwan_stock_daily', engine)
        print("Done.")
    else:
        print("No stock data fetched. Exiting.")

if __name__ == '__main__':
    main()
