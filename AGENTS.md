# 指南：AI Agent 協作規範

歡迎來到本專案！本文件旨在為所有參與此專案的 AI Agent 提供清晰的開發指南，以確保程式碼品質、風格和目標的一致性。

## 1. 專案目標

本專案是一個 Python 應用程式，其主要目標是：
- **抓取台灣證券交易所（TWSE）所有上市股票的歷史交易資料**。
- **將過去五年的每日交易資料儲存到 MySQL 資料庫中**。

核心邏輯分為兩個模組：
- `stock_crawler/fetcher.py`：負責從網路來源獲取資料。
- `stock_crawler/database.py`：負責將資料寫入資料庫。

## 2. 開發環境設置

本專案使用 [Poetry](https://python-poetry.org/) 進行依賴管理。

1.  **安裝依賴**：
    在對專案進行任何修改之前，請務必安裝所需的依賴。
    ```bash
    poetry install
    ```

2.  **執行環境**：
    所有 Python 腳本都應透過 Poetry 的虛擬環境執行，以確保一致性。
    ```bash
    poetry run python your_script.py
    ```

## 3. 程式碼風格與品質

為維持程式碼的一致性與可讀性，我們採用 `ruff` 作為唯一的 linter 和 formatter。

1.  **程式碼格式化**：
    在提交任何程式碼變更之前，請務必使用 `ruff` 自動格式化所有變更過的檔案。
    ```bash
    poetry run ruff format .
    ```

2.  **程式碼檢查 (Linting)**：
    同樣地，在提交前，請執行 linter 以檢查潛在的錯誤或風格問題。
    ```bash
    poetry run ruff check --fix .
    ```
    `--fix` 參數會自動修正大部分常見問題。

3.  **核心風格**：
    - 所有程式碼都應有符合 `PEP 257` 的 docstrings。
    - 使用 Type Hinting 進行類型註解。

## 4. I/O 規約 (Input/Output Conventions)

模組之間的資料傳遞有明確的規約：

-   **`fetcher.py` -> `main.py`**:
    -   `fetch_all_stock_data()` 函數**必須**返回一個 `pandas.DataFrame`。
    -   如果無法獲取資料，應返回一個空的 DataFrame，而不是 `None`。
    -   DataFrame 應包含 `stock_id`, `date`, `open`, `high`, `low`, `close`, `volume` 等欄位。

-   **`database.py` 的輸入**:
    -   `get_db_engine()` 函數接收資料庫連線參數（字串），返回一個 `sqlalchemy.engine.Engine` 物件。
    -   `save_data_to_db()` 函數接收一個 `pandas.DataFrame`、一個表格名稱（字串）和一個 `sqlalchemy.engine.Engine` 物件作為輸入。

## 5. 測試策略

我們使用 `pytest` 作為測試框架，以確保程式碼的穩定性和可靠性。

1.  **測試檔案位置**：
    所有測試檔案都必須放在根目錄下的 `tests/` 資料夾中。測試檔案的命名規則為 `test_*.py`。

2.  **測試要求**：
    -   **新功能**：任何新增的功能**必須**附帶對應的單元測試或整合測試。
    -   **錯誤修復**：任何錯誤修復**必須**包含一個迴歸測試（Regression Test），以驗證該錯誤已被修復且未來不會再發生。

3.  **執行測試**：
    在提交程式碼前，必須執行完整的測試套件，並確保所有測試都通過。
    ```bash
    poetry run pytest
    ```
    *(注意：您可能需要先執行 `poetry add --group dev pytest` 將 `pytest` 加入開發依賴中)*

## 6. 執行與驗證

專案的主入口點是 `main.py`。

1.  **環境設定**：
    執行前，請確保已根據 `config.ini.example` 創建並正確填寫了 `config.ini` 檔案，其中包含有效的資料庫連線資訊。

2.  **執行主程式**：
    ```bash
    poetry run python main.py
    ```

3.  **驗證**：
    提交前，請確保主程式可以無錯誤地執行完畢。由於完整抓取過程非常耗時，您可以在開發過程中修改 `fetcher.py` 以只抓取少量股票（例如 '0050', '2330'）作為測試，但提交前請務必將其恢復原狀。
