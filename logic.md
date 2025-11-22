# 專案邏輯與架構說明 (`logic.md`)

本文檔旨在詳細闡述此股票分析與交易訊號產生系統的核心架構、主要工作流程及關鍵邏輯。

## 1. 專案概觀

此專案是一個專為臺灣股市設計的自動化技術分析平台。其主要目標是每日自動化執行以下任務：
- **獲取最新行情**：從公開管道抓取每日股價資料。
- **訊號掃描**：基於經典的技術分析圖形（如杯柄、高而窄的旗形等）掃描潛在的交易機會。
- **策略回測**：提供一個高效能的回測引擎，用以評估和優化交易策略。
- **機器學習增強**：整合機器學習模型，進一步篩選和優化交易決策（例如，部位規模）。

系統的設計核心是**模組化**與**效率**。特別是在回測部分，採用了兩階段設計以實現快速的策略迭代與驗證。

## 2. 核心架構

系統由以下幾個關鍵元件構成：

- **資料管線 (Data Pipeline)**：負責從外部來源（臺灣證券交易所、櫃買中心）獲取、儲存及加載資料。
- **策略引擎 (Strategy Engine)**：實現各種技術分析圖形的偵測邏輯。
- **回測引擎 (Backtest Engine)**：模擬交易，並計算策略的績效指標。
- **優化模組 (Optimization Module)**：用於尋找策略的最佳參數組合。
- **機器學習模組 (ML Module)**：訓練模型以輔助交易決策。
- **執行腳本 (Scripts)**：將上述元件串連起來，執行具體的日常任務。

![System Architecture](https://i.imgur.com/your-architecture-diagram.png)  
*(註：此處可放置一張架構圖以獲得更佳的可視化效果)*

## 3. 主要工作流程

### 3.1 每日資料更新

- **觸發點**: `main.py` -> `scripts/update_daily_data.py`
- **流程**:
    1.  `update_daily_data.py` 腳本被執行。
    2.  它會實例化 `src/crawlers/twse.py` 和 `src/crawlers/tpex.py` 中的爬蟲。
    3.  爬蟲從臺灣證券交易所 (TWSE) 和證券櫃檯買賣中心 (TPEX) 抓取最新的每日股價。
    4.  原始資料以 CSV 格式儲存於 `data/raw/daily_quotes/` 目錄下，按股票代碼分子目錄存放。
    5.  `src/utils/data_loader.py` 提供了一個標準化的 `DataLoader` 類別，供其他腳本讀取這些原始資料。

### 3.2 每日訊號掃描

- **觸發點**: `main.py` -> `scripts/run_daily_scan.py`
- **流程**:
    1.  `run_daily_scan.py` 載入所有股票的最新資料。
    2.  它會遍歷每一支股票，並應用定義在 `src/strategies/` 中的策略邏輯，例如：
        - `cup.py` 中的 `detect_cup` 函數，用於偵測杯柄型態。
        - `htf.py` 中的 `detect_htf` 函數，用於偵測高而窄的旗形。
    3.  一旦偵測到符合條件的圖形，便會產生一筆交易訊號。
    4.  所有當日產生的訊號會被彙總並輸出成一份報告，存放於 `daily_tracking_stock/`。

### 3.3 歷史回測與分析

此系統採用一個高效的兩階段回測流程，以避免在每次調整出場或資金管理規則時都重新掃描歷史資料。

- **第一階段：歷史分析 (Pre-computation)**
    - **觸發點**: `scripts/run_historical_analysis.py`
    - **流程**:
        1. 此腳本會對資料庫中**每一支股票的完整歷史**執行所有策略的圖形偵測（`detect_cup`, `detect_htf` 等）。
        2. 所有歷史上出現過的潛在買入訊號及其基本結果（如未來幾日的漲跌幅）會被預先計算出來。
        3. 結果被儲存到一個大型的 `pattern_analysis_result.csv` 檔案中。這是一個計算密集且耗時的過程，但只需要執行一次。

- **第二階段：回測模擬 (Simulation)**
    - **觸發點**: `scripts/run_backtest.py`
    - **流程**:
        1. 回測引擎**直接讀取預先計算好的 `pattern_analysis_result.csv`**，而不是原始的日線資料。
        2. 基於這個包含所有歷史訊號的檔案，引擎可以快速測試各種不同的**出場策略**（如停損、停利）和**資金管理模型**。
        3. 由於最耗時的圖形掃描已經完成，這個階段可以非常快速地平行運行數百種場景，並產出詳細的績效報告，如 `data/processed/backtest_report_v2.md`。

> 關於回測引擎的更詳細設計，請參考：[回測引擎設計文檔](./docs/backtest_engine_logic.md)

### 3.4 參數優化

- **相關目錄**: `optimization/`
- **流程**:
    - `optimization/optimize_hyperparameters.py` 腳本利用 `optimization/backtest_engine_v2.py` 對策略的超參數（例如，杯身深度、成交量過濾器等）進行系統性優化。
    - 其目標是找到能產出最佳歷史回測績效的參數組合。
    - 優化結果存放於 `optimization/results/` 中。

> 更多細節請見：[超參數優化說明](./docs/hyperparameter_optimization.md)

### 3.5 機器學習增強

- **相關目錄**: `ml_enhanced/`
- **流程**:
    1.  **模型訓練 (`weekly_retrain.py`)**: 每週執行，使用最新的歷史資料重新訓練機器學習模型。模型可能包含：
        - **股票篩選器 (Stock Selector)**: 預測一個由基本策略產生的訊號是否值得交易。
        - **部位大小器 (Position Sizer)**: 根據訊號的品質或其他特徵，決定應該投入多少資金。
    2.  **每日預測 (`daily_ml_scanner.py`)**:
        - 載入當日由 `run_daily_scan.py` 產生的基本訊號。
        - 使用已訓練好的模型 (`.pkl` 檔) 對這些訊號進行評分或調整。
        - 產出經過 ML 增強後的每日報告，存放於 `ml_enhanced/daily_reports/`。

> 關於機器學習模型的邏輯，請參考：[ML 邏輯說明](./ml_enhanced/docs/ml_logic.md)

## 4. 目錄結構說明

- `data/`: 存放所有資料，`raw` 為原始資料，`processed` 為處理後的報告或分析結果。
- `docs/`: 存放專案的設計文檔和分析報告。
- `ml_enhanced/`: 包含所有機器學習相關的代碼、模型和報告。
- `optimization/`: 策略參數優化相關的腳本和結果。
- `scripts/`: 執行主要工作流程（數據更新、掃描、回測）的頂層腳本。
- `src/`: 專案的核心源代碼。
  - `crawlers/`: 資料爬蟲。
  - `ml/`: ML 模型的特徵工程等。
  - `strategies/`: 核心交易策略的偵測邏輯。
  - `utils/`: 共用的工具函數，如資料加載器、日誌等。
- `main.py`: 整個每日自動化流程的主要進入點。

## 5. 延伸閱讀

為了更深入地了解特定主題，您可以參考以下文件：

- **策略邏輯**: [圖形邏輯說明](./docs/pattern_logic.md)
- **回測引擎**: [回測引擎設計文檔](./docs/backtest_engine_logic.md)
- **參數優化**: [超參數優化說明](./docs/hyperparameter_optimization.md)
- **ML 整合**: [ML 邏輯說明](./ml_enhanced/docs/ml_logic.md)
- **專案讀我**: [README.md](./README.md)
