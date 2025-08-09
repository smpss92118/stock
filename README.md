# 台灣股市每日交易數據收集器

本專案是一個自動化工具，設計用於每日定時抓取台灣證券交易所（TWSE）所有上市股票的交易數據，並將其儲存於 MySQL 資料庫中，以供後續的數據分析或機器學習應用。

## ✨ 功能特性

- **自動化抓取**: 每日下午 5:00 自動執行，無需人工干預。
- **完整數據**: 涵蓋所有台灣上市股票的每日開盤價、最高價、最低價、收盤價及成交量等資訊。
- **穩定儲存**: 使用 MySQL 資料庫進行長期且結構化的數據儲存。
- **現代化開發**: 使用 Poetry 進行 Python 套件管理，確保環境一致性與可重現性。
- **易於設定**: 透過環境變數進行設定，保護敏感資訊且方便部署。

---

## 系統需求

- [Python](https://www.python.org/) (3.8 或更高版本)
- [Poetry](https://python-poetry.org/) (Python 依賴管理工具)
- [MySQL Server](https://www.mysql.com/) (5.7 或更高版本)
- [Git](https://git-scm.com/)

---

## 🚀 安裝與設定

請依照以下步驟完成專案的安裝與設定。

### 1. 複製專案

```bash
git clone <your-repository-url>
cd stock-crawler-project
```

### 2. 安裝與設定 MySQL

如果您尚未安裝 MySQL，建議使用 [Homebrew](https://brew.sh/) (macOS) 進行安裝。

```bash
# 使用 Homebrew 安裝 MySQL
brew install mysql

# 啟動 MySQL 服務
brew services start mysql

# 執行安全性設定，並設定 root 密碼
mysql_secure_installation
```

接下來，登入 MySQL 並建立專案所需的資料庫和使用者。

```sql
-- 使用您剛設定的密碼登入 MySQL
mysql -u root -p

-- 建立一個新的資料庫
CREATE DATABASE tw_stock_data CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 建立一個專用的使用者並授權 (請將 'your_password' 換成一個安全的密碼)
CREATE USER 'stock_user'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON tw_stock_data.* TO 'stock_user'@'localhost';
FLUSH PRIVILEGES;

-- 退出
EXIT;
```

### 3. 設定環境變數

本專案使用 `.env` 檔案來管理資料庫連線資訊。

```bash
# 複製範例檔案
cp .env.example .env
```

接著，編輯 `.env` 檔案，填入您在上一步設定的資料庫資訊：

```dotenv
# .env
DB_HOST=localhost
DB_PORT=3306
DB_USER=stock_user
DB_PASSWORD=your_password
DB_NAME=tw_stock_data
```
**重要**: `.env` 檔案包含敏感資訊，已被加入 `.gitignore`，請勿將其提交到版本控制中。

### 4. 安裝 Python 依賴套件

本專案使用 Poetry 管理套件，執行以下指令來安裝所有必要的函式庫：

```bash
poetry install
```

### 5. 初始化資料庫資料表

執行初始化腳本，程式將會自動連線到資料庫並建立所需的資料表。

```bash
poetry run python initialize_database.py
```

如果指令成功執行且沒有錯誤訊息，表示資料表已成功建立。

---

## 🛠️ 使用方式

### 手動執行

您可以隨時手動執行主程式來抓取當天的股市數據。

```bash
poetry run python main.py
```

程式會抓取數據並存入資料庫，並在終端機顯示進度與結果。

### 自動排程 (Cron Job)

為了實現每日自動抓取，您需要設定一個 Cron Job。

1.  **編輯 Crontab**

    ```bash
    crontab -e
    ```

2.  **加入排程任務**

    在檔案的最後加入以下這行。請務必將 `/path/to/your/project` 替換成您專案的 **絕對路徑**。

    ```crontab
    # 每天下午 5:00 執行股市數據抓取任務
    0 17 * * * cd /path/to/your/project && poetry run python main.py >> /path/to/your/project/cron.log 2>&1
    ```

    - `0 17 * * *`: 代表在每天的 17:00 (下午5點) 執行。
    - `cd /path/to/your/project`: 確保在正確的專案目錄下執行。
    - `poetry run python main.py`: 執行主程式。
    - `>> .../cron.log 2>&1`: 將所有輸出（包含錯誤）導向到一個日誌檔案，方便追蹤問題。

---

## 專案結構

```
.
├── .env                # 環境變數 (本地，不進版控)
├── .env.example        # 環境變數範例
├── .gitignore          # Git 忽略檔案列表
├── README.md           # 專案說明文件
├── TASKS.md            # 開發任務流程
├── poetry.lock         # Poetry 鎖定依賴版本
├── pyproject.toml      # Poetry 專案設定與依賴
├── stock_crawler/      # 主要程式碼目錄
│   ├── __init__.py
│   ├── main.py         # 主執行檔
│   ├── crawler.py      # 數據抓取模組
│   └── database.py     # 資料庫操作模組
└── tests/              # 測試程式碼目錄
```

---

## 📄 授權條款

本專案採用 [MIT License](LICENSE) 授權。