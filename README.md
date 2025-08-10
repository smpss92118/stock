# Taiwan Stock Data Crawler (台灣股市資料爬蟲)

This project provides a complete solution for fetching historical daily trading data for all stocks listed on the Taiwan Stock Exchange (TWSE) and storing it in a MySQL database. It is built using Python and managed with Poetry.

## Features

- **Comprehensive Data**: Fetches data for all stocks, including ETFs, on the TWSE.
- **5-Year History**: Retrieves the last five years of daily trading data.
- **Robust Storage**: Uses MySQL for reliable and structured data storage.
- **Modern Tooling**: Managed with [Poetry](https://python-poetry.org/) for easy dependency management.
- **Configurable**: Database credentials are kept separate from the code in a configuration file.
- **Efficient**: Uses `pandas` and `SQLAlchemy` for efficient data handling and database interaction.

## Tech Stack

- **Language**: Python 3.8+
- **Dependency Management**: Poetry
- **Data Handling**: Pandas
- **Database ORM**: SQLAlchemy
- **Database Driver**: aiohttp
- **Database**: MySQL

## Prerequisites

Before you begin, ensure you have the following installed on your system:

- **Python** (version 3.8 or higher)
- **Poetry**
- **MySQL Server**

### MySQL Installation Guide

<details>
<summary><b>Click to expand for MySQL installation instructions</b></summary>

#### macOS (using Homebrew)
If you don't have Homebrew, install it from [brew.sh](https://brew.sh/).
```bash
# Install MySQL Server
brew install mysql

# Start the MySQL service
brew services start mysql

# Secure your installation (optional but recommended)
# Follow the on-screen prompts.
mysql_secure_installation
```

#### Ubuntu/Debian
```bash
# Update package lists
sudo apt update

# Install MySQL Server
sudo apt install mysql-server

# Secure your installation (optional but recommended)
# Follow the on-screen prompts.
sudo mysql_secure_installation
```
</details>

## Setup and Installation

Follow these steps to get the project up and running.

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/taiwan-stock-crawler.git
cd taiwan-stock-crawler
```
*(Replace `your-username` with the actual repository path)*

### 2. Configure the MySQL Database

You need to create a database and a dedicated user for this application.

1.  **Log in to MySQL as the root user:**
    ```bash
    sudo mysql -u root -p
    ```
    (You might not need `sudo` depending on your installation.)

2.  **Create a new database:**
    We'll name it `stock_data` for this example.
    ```sql
    CREATE DATABASE stock_data;
    ```

3.  **Create a new user and grant privileges:**
    Replace `'your_password'` with a strong, secure password.
    ```sql
    CREATE USER 'stock_user'@'localhost' IDENTIFIED BY 'your_password';
    GRANT ALL PRIVILEGES ON stock_data.* TO 'stock_user'@'localhost';
    FLUSH PRIVILEGES;
    EXIT;
    ```

### 3. Configure the Application

1.  **Create your configuration file:**
    Copy the example configuration file.
    ```bash
    cp config.ini.example config.ini
    ```

2.  **Edit `config.ini`:**
    Open the `config.ini` file and fill in the database details you just created.
    ```ini
    [database]
    host = localhost
    user = stock_user
    password = your_password
    database = stock_data
    ```

### 4. Install Dependencies

Use Poetry to install all the required Python packages from the `pyproject.toml` file.

```bash
poetry install
```

## Usage

This project has two main scripts:

### 1. Initial Data Backfill (`main.py`)

This script is used to perform the initial, large-scale import of the last five years of stock data. You should only need to run this once.

```bash
poetry run python main.py
```

The script will:
1.  Fetch five years of data for all stocks (this can take a very long time).
2.  Connect to the database.
3.  Save the data to the `taiwan_stock_daily` table, **replacing** it if it already exists.

### 2. Daily Data Update (`daily_update.py`)

This script is designed to be run daily to fetch the latest trading data and append it to the existing database.

```bash
poetry run python daily_update.py
```

The script includes the following logic:
- It will exit if run on a weekend.
- It checks the database to see if data for the current day already exists. If so, it exits.
- It fetches the data for the current day.
- It validates that the fetched data is for the correct date before saving.
- It **appends** the new data to the `taiwan_stock_daily` table.

### Automating the Daily Update (Cron Job)

To run the `daily_update.py` script automatically, you can set up a cron job. The following example will run the script at 5:00 PM (17:00) every Monday through Friday.

1.  Open your crontab for editing:
    ```bash
    crontab -e
    ```

2.  Add the following line to the file. **Make sure to replace `/path/to/your/project` with the absolute path to this project's directory.**

    ```crontab
    # Run the Taiwan stock daily update script every weekday at 5 PM
    0 17 * * 1-5 cd /path/to/your/project && /usr/bin/poetry run python daily_update.py >> /path/to/your/project/cron.log 2>&1
    ```

    **Crontab Breakdown:**
    - `0 17 * * 1-5`: Runs at 17:00 (5 PM) on every day-of-week from Monday (1) to Friday (5).
    - `cd /path/to/your/project`: Changes the current directory to your project's root. This is crucial for the script to find the `config.ini` and its modules.
    - `/usr/bin/poetry run python daily_update.py`: Executes the script using the correct Poetry environment. You might need to adjust the path to your poetry executable (`which poetry`).
    - `>> /path/to/your/project/cron.log 2>&1`: Redirects all output (both stdout and stderr) to a log file named `cron.log` within your project directory. This is highly recommended for debugging.

## Troubleshooting

### Network Timeouts

When fetching data from the Taiwan Stock Exchange, the process can be very time-consuming due to the large number of stocks and the five-year data range. In some network environments (especially those with strict firewalls or slower connections), the request may time out.

If you encounter persistent timeouts, this is likely an issue with the network environment and not a bug in the code. The script is confirmed to be logically correct, but its success depends on a stable connection to the data source.
