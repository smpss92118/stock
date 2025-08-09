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
    Saves a pandas DataFrame to a table in the database.

    Args:
        df (pandas.DataFrame): The DataFrame to save.
        table_name (str): The name of the table to create or replace.
        engine (sqlalchemy.engine.Engine): The SQLAlchemy engine.
    """
    df.to_sql(table_name, con=engine, if_exists='replace', index=False)
    print(f"Data saved to table '{table_name}' successfully.")
