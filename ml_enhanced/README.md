# ML-Enhanced Trading System

## 🎯 系統概述

這是基於原始交易系統的 ML 增強版本，旨在通過機器學習模型過濾原始訊號，提高勝率並降低風險。

**核心理念**:
1. **原始掃描**: 使用傳統技術分析 (HTF, CUP, VCP) 找出所有潛在機會。
2. **ML 過濾**: 使用 XGBoost 模型預測每個訊號的勝率，只保留高品質訊號。
3. **允許 Pyramiding**: 同一股票可多次進場，捕捉超級股票的機會。

**最新績效** (2025-11-21):
- 🏆 **CUP R=2.0 (ML 0.5)**: 年化 146.7%, Sharpe **3.13**, 勝率 74.6%
- 🚀 **HTF Trailing**: 年化 151.2%, Sharpe 1.19, 勝率 38.7%

---

## 📂 目錄結構 (Production)

```
ml_enhanced/
├── daily_ml_scanner.py    # [核心] 每日 ML 掃描器 (Crontab 19:05)
├── weekly_retrain.py      # [核心] 每週模型再訓練 (Crontab Sun 02:00)
├── scripts/
│   ├── prepare_ml_data.py # 特徵工程 (使用 src.ml.features)
│   ├── train_models.py    # 模型訓練 (XGBoost)
│   ├── run_ml_backtest.py # [NEW] ML 回測系統
├── models/
│   ├── stock_selector.pkl # 股票選擇模型 (XGBoost Classifier)
│   └── feature_info.pkl   # 特徵元數據
├── daily_reports/         # 每日生成的 ML 報告
│   └── YYYY-MM-DD/
│       ├── ml_daily_summary.md
│       └── ml_signals.csv
├── data/                  # 訓練數據
│   └── ml_features.csv
├── README.md              # 本文件
└── CRONTAB_SETUP.md       # 自動化設定說明
```

> **注意**: 本系統依賴 `stock/src/ml/` (特徵提取) 和 `stock/src/utils/` (日誌記錄) 共享模組。

---

## 🚀 核心組件

### 1. 每日掃描 (`daily_ml_scanner.py`)
- **功能**: 執行每日掃描，並應用 ML 模型過濾。
- **輸入**: 每日股價數據
- **輸出**: `ml_daily_summary.md` (包含 ML 推薦訊號與原始訊號對比)
- **邏輯**:
    1. 執行原始掃描 (HTF/CUP/VCP)
    2. 載入 ML 模型 (`stock_selector.pkl`)
    3. 為每個訊號計算 ML 特徵
    4. 預測勝率 (Probability)
    5. 載入最新回測結果（包含 Avg Holding, MDD, 連勝/連敗等指標）
    6. 生成報告（推薦 Prob ≥ 0.4 的訊號）

### 2. 每週再訓練 (`weekly_retrain.py`)
- **功能**: 每週使用最新數據重新訓練模型，確保模型適應市場變化。
- **流程**:
    1. **準備數據**: 執行 `prepare_ml_data.py`，重新計算所有歷史特徵。
    2. **訓練模型**: 執行 `train_models.py`，使用 TimeSeriesSplit 驗證並訓練新模型。
    3. **執行回測**: 執行 `run_ml_backtest.py`，驗證新模型績效並生成報告。
    4. **更新模型**: 覆蓋舊的 `models/stock_selector.pkl`。

---

## 🤖 ML 模型說明

### Stock Selector (股票選擇模型)

- **算法**: XGBoost Classifier
- **目標**: 預測訊號是否為 "Winner" (未來 20 天漲幅 > 10%)
- **特徵 (24 Features)**:
    - **型態品質 (3)**: `grade_numeric`, `distance_to_buy_pct`, `risk_pct`
    - **成交量 (4)**: `volume_ratio_ma20`, `volume_ratio_ma50`, `volume_surge`, `volume_trend_5d`
    - **動能 (4)**: `momentum_5d`, `momentum_20d`, `price_vs_ma20`, `price_vs_ma50`
    - **RSI (2)**: `rsi_14`, `rsi_divergence`
    - **技術面 (3)**: `ma_trend`, `volatility`, `atr_ratio`
    - **市場環境 (2)**: `market_trend`, `market_volatility`
    - **相對強弱 (1)**: `rs_rating`
    - **型態專屬 (1)**: `consolidation_days`
    - **訊號密度 (2, placeholder)**: `signal_count_ma10`, `signal_count_ma60`
- **決策閾值**: Probability ≥ 0.4
- **績效** (2025-11-21 更新):
    - ROC AUC: ~0.73
    - 準確率: ~75% (在 0.4 閉值下)
    - 回測驗證: CUP R=2.0 (ML 0.5) 年化 146.7%, Sharpe 3.13

> 📘 **詳細特徵說明**: 查看 [ML 邏輯完整文檔](docs/ml_logic.md) 了解每個特徵的計算方式和來源

---

## 📊 使用方式

### 1. 自動化運行 (推薦)
請參考 [`CRONTAB_SETUP.md`](CRONTAB_SETUP.md) 設定每日自動排程。

### 2. 手動運行

**每日掃描**:
```bash
python stock/ml_enhanced/daily_ml_scanner.py
```

**重新訓練模型**:
```bash
python stock/ml_enhanced/weekly_retrain.py
```

---

## ⚠️ 注意事項

1. **依賴關係**: ML 系統依賴原始系統的數據更新 (`scripts/update_daily_data.py`)。務必確保原始數據是最新的 (TWSE + TPEX)。
2. **模型檔案**: `models/` 目錄下的 `.pkl` 檔案是自動生成的，請勿手動修改。
3. **回滾**: 如果 ML 系統出現問題，原始的 `main.py` 掃描完全獨立，不受影響，可隨時切回原始報告。
4. **績效更新**: 回測結果每週更新一次，平日報告使用上週日的數據。
5. **Volume 必須存在**: `pattern_analysis_result.csv` 會帶出 `volume` 欄位供 ML 使用；若缺少 volume，`prepare_ml_data.py` 會直接中止並提示你先重新產生分析結果。

---

**最後更新**: 2025-11-21  
**版本**: 2.0  
**關鍵改進**: 移除 No Pyramiding 限制、30天追蹤窗口、完整 TPEX 數據源、新增回測指標
