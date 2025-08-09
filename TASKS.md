# 專案：每日台灣股市數據抓取與儲存系統

這份文件描述了建構一個自動化台灣股市數據收集系統的完整任務與子任務流程。

---

## 階段一：專案初始化與環境設定

- [ ] **任務 1.1：建立專案目錄結構**
    - [ ] 建立主要的 Python 原始碼目錄 (例如 `stock_crawler/`)。
    - [ ] 建立測試目錄 (`tests/`)。

- [ ] **任務 1.2：使用 Poetry 初始化 Python 環境**
    - [ ] 在專案根目錄執行 `poetry init`，並依照提示設定專案名稱、描述等。
    - [ ] 執行 `poetry install` 來生成 `poetry.lock` 檔案。

- [ ] **任務 1.3：安裝初步的核心依賴套件**
    - [ ] `poetry add python-dotenv`: 用於管理環境變數（資料庫密碼等）。
    - [ ] `poetry add twstock`: 用於抓取台灣股市數據的主要套件。
    - [ ] `poetry add mysql-connector-python`: 用於連接 MySQL 資料庫。
    - [ ] `poetry add pandas`: 用於數據處理與轉換。

- [ ] **任務 1.4：設定環境變數檔案**
    - [ ] 在專案根目錄建立一個 `.env` 檔案。
    - [ ] 在 `.env` 中定義資料庫連線資訊 (主機, 使用者, 密碼, 資料庫名稱)。
    - [ ] 建立一個 `.env.example` 檔案作為範例，並將 `.env` 加入 `.gitignore` 中。

---

## 階段二：資料庫設定

- [ ] **任務 2.1：安裝與設定 MySQL**
    - [ ] 根據 `README.md` 的指引安裝 MySQL Server。
    - [ ] 啟動 MySQL 並完成安全性設定。

- [ ] **任務 2.2：建立資料庫與使用者**
    - [ ] 登入 MySQL。
    - [ ] 建立一個專門給此專案使用的資料庫 (例如 `tw_stock_data`)。
    - [ ] 建立一個專門的使用者，並授與該使用者對 `tw_stock_data` 資料庫的完整權限。

- [ ] **任務 2.3：設計與建立資料表 (Schema)**
    - [ ] 設計一個 `daily_transactions` 資料表來儲存每日交易數據。
    - [ ] 欄位應包含：
        - `id` (自動增長主鍵)
        - `stock_code` (股票代碼, VARCHAR)
        - `trade_date` (交易日期, DATE)
        - `capacity` (成交股數, BIGINT)
        - `turnover` (成交金額, BIGINT)
        - `open_price` (開盤價, DECIMAL)
        - `high_price` (最高價, DECIMAL)
        - `low_price` (最低價, DECIMAL)
        - `close_price` (收盤價, DECIMAL)
        - `created_at` (資料建立時間, TIMESTAMP)
    - [ ] 設定 `(stock_code, trade_date)` 為唯一約束(Unique Constraint)，防止重複寫入。

- [ ] **任務 2.4：撰寫資料庫初始化腳本**
    - [ ] 建立一個 `initialize_database.py` 腳本。
    - [ ] 此腳本讀取環境變數，連線到 MySQL，並自動建立 `daily_transactions` 資料表。

---

## 階段三：核心邏輯開發

- [ ] **任務 3.1：開發資料庫連線模組**
    - [ ] 建立 `database.py` 模組。
    - [ ] 撰寫一個函數，可以建立並返回一個資料庫連線物件。
    - [ ] 撰寫一個函數，用於將 Pandas DataFrame 的數據寫入到 MySQL 資料表中。

- [ ] **任務 3.2：開發股市數據抓取模組**
    - [ ] 建立 `crawler.py` 模組。
    - [ ] 撰寫一個函數 `fetch_daily_data(stock_code, date)`，使用 `twstock` 套件抓取指定股票和日期的交易數據。
    - [ ] 處理可能發生的錯誤（例如：當天未開盤、找不到股票）。
    - [ ] 撰寫一個主函數 `run_fetch_all()`，該函數：
        - 獲取所有台灣股票的代碼列表。
        - 遍歷所有股票代碼。
        - 呼叫 `fetch_daily_data()` 來抓取當日數據。
        - 將所有抓取到的數據整合成一個 Pandas DataFrame。

- [ ] **任務 3.3：整合主腳本**
    - [ ] 建立 `main.py` 主執行腳本。
    - [ ] 該腳本執行時：
        1. 呼叫 `crawler.run_fetch_all()` 獲取數據 DataFrame。
        2. 呼叫 `database.write_to_db()` 將 DataFrame 存入 MySQL。
        3. 加入日誌記錄 (Logging) 功能，記錄每次執行的成功或失敗訊息。

---

## 階段四：自動化與排程

- [ ] **任務 4.1：設定 Cron Job (macOS/Linux)**
    - [ ] 撰寫一個 shell 腳本 `run.sh`，內容為 `cd /path/to/project && poetry run python main.py`。
    - [ ] 使用 `crontab -e` 指令設定排程。
    - [ ] 加入一行 `0 17 * * * /bin/bash /path/to/project/run.sh`，設定在每天下午 5:00 執行。
    - [ ] 確保 Cron Job 的執行環境可以找到 `poetry` 指令。

---

## 階段五：測試與驗證

- [ ] **任務 5.1：單元測試**
    - [ ] 對資料庫模組的連線功能進行測試。
    - [ ] 對爬蟲模組的數據格式進行測試。

- [ ] **任務 5.2：整合測試**
    - [ ] 手動執行 `main.py`，確認數據能從頭到尾正確抓取並存入資料庫。
    - [ ] 檢查資料庫中的數據是否符合預期。

- [ ] **任務 5.3：排程測試**
    - [ ] 將排程時間改為幾分鐘後，測試 Cron Job 是否能自動觸發並成功執行。
    - [ ] 檢查日誌檔案確認執行結果。
