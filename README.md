# 台股型態識別與回測系統 (Stock Pattern Analysis System)

這是一個自動化的台股型態識別系統，專門用於識別 CUP (杯柄)、HTF (高窄旗形) 和 VCP (波動收縮) 等高勝率型態，並結合回測系統驗證策略績效。

## 📂 專案結構

本專案採用模組化架構，確保程式碼清晰且易於維護：

```
stock/
├── README.md           # 專案說明文件
├── data/               # 數據資料夾
│   ├── raw/            # 原始數據 (股價資料、大盤資料)
│   └── processed/      # 處理後數據 (掃描結果、回測報告)
# 台股每日自動化掃描與回測系統

這是一個全自動化的台股交易策略系統，旨在每日掃描符合特定型態（CUP, HTF）的股票，並進行回測與報告生成。

## 系統架構與流程

本系統的每日運作流程如下：

1.  **數據更新 (`scripts/update_daily_data.py`)**:
    -   從 **TWSE 證交所**抓取上市股票每日收盤行情。
    -   從 **TPEX 櫃買中心**抓取上櫃股票每日收盤行情。
    -   合併兩個市場數據並儲存至 `data/raw/daily_quotes/YYYY-MM-DD.csv`。
    -   自動過濾掉非 4 位數或非 1-9 開頭的股票代號。

2.  **型態掃描 (`scripts/run_daily_scan.py`)**:
    -   讀取最新的歷史數據（預設過去 126 天）。
    -   計算技術指標（MA, RS Rating, 52週高點等）。
    -   **CUP 型態**: 檢測杯柄型態，確認是否在右側形成柄部。
    -   **HTF 型態**: 檢測高檔旗型，確認是否在強勢上漲後進行窄幅整理。
    -   **訊號判斷**:
        -   **等待突破**: 當前價格 < 買入點，且型態未被破壞。
        -   **已突破**: 當前價格 >= 買入點，視為強勢訊號。
    -   生成每日掃描報告 (`daily_tracking_stock/YYYY-MM-DD/latest_signals_report.md`)。

3.  **歷史回測 (`scripts/run_historical_analysis.py`)**:
    -   針對掃描出的訊號，進行歷史模擬交易。
    -   使用多核心平行運算加速處理。
    -   模擬 "Limited Capital" (有限資金) 與 "Unlimited" (無限資金) 兩種情境。

4.  **回測報告 (`scripts/run_backtest.py`)**:
    -   彙整回測結果，計算關鍵指標：
        -   **Ann. Return %**: 年化報酬率。
        -   **Sharpe**: 夏普比率（風險調整後報酬）。
        -   **Win Rate**: 勝率。
    -   生成回測統計報告。

5.  **總控與歸檔 (`main.py`)**:
    -   串聯以上所有步驟。
    -   將所有產出的報告與 CSV 檔案歸檔至 `daily_tracking_stock/YYYY-MM-DD/` 資料夾。
    -   生成最終的 `daily_summary.md` 摘要報告。

## 如何執行

### 環境設定

本專案使用 `poetry` 進行套件管理。

```bash
# 安裝相依套件
poetry install

# 進入虛擬環境
poetry shell
```

### 每日執行

只需執行主程式即可完成所有工作：

```bash
python stock/main.py
```

執行後，請查看 `stock/daily_tracking_stock/` 目錄下的當日資料夾，裡面會有：
- `daily_summary.md`: 當日總結報告（含訊號與回測排名）。
- `latest_signals.csv`: 詳細的訊號數據。
- `backtest_results_v2.csv`: 詳細的回測數據。

## 策略邏輯細節

本系統的核心策略邏輯較為複雜，詳細定義請參考以下文件：

- **[型態定義與進出場邏輯](docs/pattern_logic.md)**: 詳細說明 CUP 與 HTF 的數學定義、買入點與停損點計算方式。
- **[優化日誌](docs/optimization_log.md)**: 記錄了策略參數的調整歷程與回測結果對比。

### 核心指標說明

- **RS Rating (相對強度評分)**:
    - 計算過去 52 週的股價漲幅。
    - 與全市場所有股票進行排名比較 (0-100)。
    - 分數越高代表相對大盤與其他股票越強勢。本系統通常過濾 RS > 70 或 80 的強勢股。

- **VCP / CUP / HTF**:
    - 這些都是動能交易的經典型態，旨在捕捉股價在經歷一段整理後，即將突破創高的時機。
    - 系統會自動計算型態的深度、長度、波動收縮程度來判斷是否成立。

## 檔案結構

- `stock/main.py`: 總控程式。
- `stock/scripts/`: 各個功能模組的執行腳本。
- `stock/src/strategies/`: 策略核心邏輯 (CUP, HTF, VCP)。
- `stock/src/crawlers/`: 爬蟲模組。
- `stock/data/`: 數據存放區。
- `stock/daily_tracking_stock/`: 每日產出的報告存檔。
- `stock/archive/`: 舊的或不再使用的程式碼。

---
**注意**: 本系統僅供輔助分析使用，不構成任何投資建議。股市投資有風險，請審慎評估。

## 🛠️ 系統需求

*   Python 3.8+
*   Poetry (依賴管理)
*   Pandas, NumPy
*   Polars (用於高速回測)
*   yfinance (用於下載數據)

---
*最後更新: 2025-11-20*
