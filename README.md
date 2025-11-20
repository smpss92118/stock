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
├── docs/               # 文檔資料夾 (策略邏輯、優化日誌)
├── src/                # 核心程式碼庫
│   ├── strategies/     # 型態識別策略 (CUP, HTF, VCP)
│   └── utils/          # 通用工具 (數據載入等)
├── scripts/            # 執行腳本 (使用者主要操作區)
│   ├── run_daily_scan.py         # 每日掃描器 (產出最新訊號)
│   ├── run_historical_analysis.py # 歷史全量掃描 (用於回測)
│   ├── run_backtest.py           # 回測執行引擎
│   └── update_market_data.py     # 更新大盤數據
└── archive/            # 舊版或備份檔案
```

## 🚀 如何使用

請在 `stock/` 目錄下執行以下指令：

### 1. 每日掃描 (最常用)
掃描最新日期的股票，找出符合型態的潛在標的。
```bash
python scripts/run_daily_scan.py
```
*   **輸出**: `data/processed/latest_signals.csv` 和 `data/processed/latest_signals_report.md`

### 2. 更新大盤與個股數據 (自動化)
本系統內建 TWSE 爬蟲，可自動從台灣證交所抓取最新的：
-   **個股日成交資訊** (MI_INDEX)
-   **三大法人買賣超** (T86)
-   **大盤指數** (MI_INDEX)

```bash
python scripts/update_daily_data.py
```
*   **輸出**: 
    - `data/raw/daily_quotes/YYYY-MM-DD.csv` (個股，僅保留 4 位數代碼且 1-9 開頭)
    - `data/raw/institutional/YYYY-MM-DD.csv` (法人)
    - `data/raw/market_data.csv` (大盤更新)

### 3. 執行歷史全量掃描
掃描過去所有日期的型態 (通常只需在修改策略邏輯後執行)。
```bash
python scripts/run_historical_analysis.py
```
*   **輸出**: `data/processed/pattern_analysis_result.csv`

### 4. 執行回測
基於歷史掃描結果進行回測，計算報酬率與勝率。
```bash
python scripts/run_backtest.py
```
*   **輸出**: `data/processed/backtest_results_v2.csv`

## 📊 策略說明

詳細的策略邏輯與參數設定請參考 `docs/pattern_logic.md`。

*   **CUP (杯柄型態)**: 尋找 U 型底與成交量萎縮的把手。
*   **HTF (高窄旗形)**: 尋找短時間內飆漲後的旗形整理。
*   **VCP (波動收縮)**: 尋找波動率逐漸收縮的型態 (目前作為輔助)。

## 🛠️ 環境設定

本專案使用 **Poetry** 進行依賴管理。在執行任何腳本之前，請確保您已進入虛擬環境：

```bash
# 啟用 Poetry 虛擬環境
eval $(poetry env activate)
```

啟用後，即可直接執行上述的 Python 指令。

## 🛠️ 系統需求

*   Python 3.8+
*   Poetry (依賴管理)
*   Pandas, NumPy
*   Polars (用於高速回測)
*   yfinance (用於下載數據)

---
*最後更新: 2025-11-20*
