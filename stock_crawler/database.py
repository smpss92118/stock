from sqlalchemy import create_engine
import pandas as pd

def get_db_engine(user, password, host, database):
    """
    Creates a SQLAlchemy engine for connecting to a MySQL database.

    Args:
        user (str): The database user.
        password (str): The database password.
        host (str): The database host.
        database (str): The database name.

    Returns:
        sqlalchemy.engine.Engine: The SQLAlchemy engine.
    """
    connection_string = f"mysql+mysqlconnector://{user}:{password}@{host}/{database}"
    return create_engine(connection_string)

def save_data_to_db(df, table_name, engine):
    """
    Saves a pandas DataFrame to a table in the database, replacing it if it exists.

    Args:
        df (pandas.DataFrame): The DataFrame to save.
        table_name (str): The name of the table to create or replace.
        engine (sqlalchemy.engine.Engine): The SQLAlchemy engine.
    """
    df.to_sql(table_name, con=engine, if_exists='replace', index=False)
    print(f"Data saved to table '{table_name}' successfully.")


def append_data_to_db(df, table_name, engine):
    """
    Appends a pandas DataFrame to an existing table in the database.

    Args:
        df (pandas.DataFrame): The DataFrame to append.
        table_name (str): The name of the table to append to.
        engine (sqlalchemy.engine.Engine): The SQLAlchemy engine.
    """
    df.to_sql(table_name, con=engine, if_exists='append', index=False)
    print(f"Data appended to table '{table_name}' successfully.")


def check_data_exists(date, table_name, engine):
    """
    Checks if data for a specific date already exists in the table.

    Args:
        date (datetime.date): The date to check for.
        table_name (str): The name of the table to check.
        engine (sqlalchemy.engine.Engine): The SQLAlchemy engine.

    Returns:
        bool: True if data for the given date exists, False otherwise.
    """
    query = f"SELECT 1 FROM {table_name} WHERE DATE(date) = %s LIMIT 1"
    try:
        with engine.connect() as connection:
            result = pd.read_sql_query(query, connection, params=(date,))
            return not result.empty
    except Exception as e:
        # This can happen if the table doesn't exist yet (e.g., first run)
        if "doesn't exist" in str(e):
            return False
        raise e
