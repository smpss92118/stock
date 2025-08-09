# Taiwan Stock Data Crawler

This project fetches the last five years of daily trading data for all stocks listed on the Taiwan Stock Exchange (TWSE) and stores it in a MySQL database.

## Prerequisites

- Python 3.8+
- Poetry for dependency management
- A running MySQL server

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository_url>
   cd <repository_directory>
   ```

2. **Install dependencies:**
   Make sure you have [Poetry](https://python-poetry.org/docs/#installation) installed. Then, run the following command in the project root to install the required Python packages:
   ```bash
   poetry install
   ```

## Configuration

Before running the application, you need to configure your database connection.

1. **Copy the example configuration file:**
   Rename `config.ini` to your preferred name or edit it directly.

2. **Edit `config.ini`:**
   Open `config.ini` and replace the placeholder values with your MySQL database credentials:
   ```ini
   [database]
   host = localhost
   user = your_username
   password = your_password
   database = your_database
   ```

## Usage

To run the data crawler, execute the following command from the project's root directory:

```bash
poetry run python main.py
```

The script will fetch the stock data and save it to the `taiwan_stock_daily` table in your database. The table will be replaced if it already exists.
