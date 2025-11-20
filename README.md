# 台股 ML-Enhanced 交易系統

自動化台股型態識別與 ML 增強交易系統，每日掃描 HTF/CUP 型態並使用機器學習過濾高品質訊號。

## 🎯 系統簡介

本系統包含兩個並行的每日掃描系統：
1. **原始策略掃描**: 基於技術型態的傳統掃描（HTF, CUP, VCP）
2. **ML 增強掃描**: 使用 XGBoost 模型過濾，提供高品質訊號推薦

**核心優勢**:
- ✅ 年化報酬 **171.1%** (ML-Enhanced CUP R=2.0)
- ✅ Sharpe Ratio **2.99** (風險調整後報酬為原始策略的 2.5 倍)
- ✅ 勝率 **77.6%** (vs 原始策略 39.5%)
- ✅ 全自動化：每日掃描 + 每週模型更新

---

## 📂 專案結構

```
stock/
├── main.py                    # 原始策略每日掃描 (Crontab Entry 1)
├── config.py                  # 系統配置
├── scripts/                   # 核心執行腳本
│   ├── update_daily_data.py   # 數據更新 (TWSE + TPEX)
│   ├── run_historical_analysis.py  # 歷史型態分析
│   ├── run_daily_scan.py      # 每日訊號掃描
│   ├── run_backtest.py        # 回測引擎
│   └── backtest_engine_v2.py  # V2 回測引擎
├── src/                       # 核心邏輯
│   ├── strategies/            # 型態識別 (HTF, CUP, VCP)
│   ├── utils/                 # 工具函數
│   └── crawlers/              # 數據爬蟲
├── ml_enhanced/               # ML 增強系統 (Production)
│   ├── daily_ml_scanner.py    # ML 每日掃描 (Crontab Entry 2)
│   ├── weekly_retrain.py      # ML 週訓練 (Crontab Entry 3)
│   ├── scripts/
│   │   ├── prepare_ml_data.py # 特徵工程
│   │   └── train_models.py    # 模型訓練
│   ├── models/                # ML 模型檔案
│   ├── data/                  # ML 訓練數據
│   ├── daily_reports/         # 每日 ML 報告
│   ├── results/               # 回測結果
│   ├── README.md              # ML 系統說明
│   └── CRONTAB_SETUP.md       # 自動化設定
├── optimization/              # 超參數優化 (Historical)
│   └── optimize_hyperparameters.py
├── data/                      # 數據存放
│   ├── raw/daily_quotes/      # 每日股價
│   └── processed/             # 處理後數據
├── daily_tracking_stock/      # 每日原始報告
├── docs/                      # 文檔
└── archive/                   # 已棄用文件
```

---

## ⚙️ 自動化設定 (Crontab)

### 每日運行 (19:00-19:05)

```bash
# 每天晚上 7:00 - 原始策略掃描
0 19 * * * /Users/sony/ml_stock/stock/.venv/bin/python /Users/sony/ml_stock/stock/main.py >> /Users/sony/ml_stock/logs/original_scan.log 2>&1

# 每天晚上 7:05 - ML 增強掃描
5 19 * * * /Users/sony/ml_stock/stock/.venv/bin/python /Users/sony/ml_stock/stock/ml_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/ml_scanner.log 2>&1
```

### 每週模型更新 (週日 02:00)

```bash
# 每週日凌晨 2:00 - 重新訓練 ML 模型
0 2 * * 0 /Users/sony/ml_stock/stock/.venv/bin/python /Users/sony/ml_stock/stock/ml_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/ml_retrain.log 2>&1
```

詳細設定請見 [`ml_enhanced/CRONTAB_SETUP.md`](ml_enhanced/CRONTAB_SETUP.md)

---

## 📊 每日輸出報告

###1. 原始策略報告
**位置**: `stock/daily_tracking_stock/YYYY-MM-DD/daily_summary.md`

**內容**:
- 所有 HTF/CUP/VCP 型態訊號
- 過去一週訊號彙整
- Top 3 策略績效排名

### 2. ML 增強報告
**位置**: `stock/ml_enhanced/daily_reports/YYYY-MM-DD/ml_daily_summary.md`

**內容**:
- ✅ **ML 推薦訊號** (ML 分數 ≥ 0.4, 勝率 70-78%)
- 📋 原始訊號對比 (ML 分數 < 0.4)
- 📅 過去一週訊號彙整
- 🏆 Top 3 Strategies (ML-Enhanced)
- ML 分數解讀與策略說明

---

## 🚀 手動執行

### 每日掃描
```bash
cd /Users/sony/ml_stock

# 原始策略
stock/.venv/bin/python stock/main.py

# ML 增強
stock/.venv/bin/python stock/ml_enhanced/daily_ml_scanner.py
```

### ML 模型訓練
```bash
# 重新訓練 ML 模型 (每週自動執行)
stock/.venv/bin/python stock/ml_enhanced/weekly_retrain.py
```

---

## 📈 策略績效 (回測驗證)

### ML-Enhanced System (推薦) ⭐
- **策略**: CUP Fixed (R=2.0, T=20) + ML 0.4
- **年化報酬**: **171.1%**
- **Sharpe Ratio**: **2.99**
- **勝率**: **77.6%**
- **最大回撤**: ~-11.8%

### Original System (Baseline)
- **策略**: HTF Trailing (1.5R trigger, MA20)
- **年化報酬**: **153.4%**
- **Sharpe Ratio**: **1.19**
- **勝率**: **39.5%**
-最大回撤**: ~-30.9%

**結論**: ML 系統在相似報酬下，風險降低 2.5 倍，勝率提升 2 倍。

---

## 🔬 核心技術

### 型態識別
- **HTF (High Tight Flag)**: 高檔旗形突破
- **CUP (Cup with Handle)**: 杯柄型態
- **VCP (Volatility Contraction Pattern)**: 波動收縮

### ML 模型
- **算法**: XGBoost Classifier
- **特徵**: 型態品質、技術指標、市場趨勢 (10 features)
- **訓練**: 14,033 樣本 (時間序列分割)
- **性能**: ROC AUC 0.73, Threshold 0.4

### 回測引擎
- **資金管理**: 有限資本 (100萬初始)
- **倉位控制**: 每筆 10%, 最多 10 檔
- **複利計算**: 基於當前總資產
- **出場策略**: Trailing Stop / Fixed R-multiple

---

## 📖 文檔

- [`ml_enhanced/README.md`](ml_enhanced/README.md) - ML 系統詳細說明
- [`ml_enhanced/CRONTAB_SETUP.md`](ml_enhanced/CRONTAB_SETUP.md) - 自動化設定
- [`docs/pattern_logic.md`](docs/pattern_logic.md) - 型態定義細節
- [`docs/optimization_vs_baseline.md`](docs/optimization_vs_baseline.md) - 優化歷史

---

## 🛠️ 系統需求

- Python 3.8+
- Poetry (依賴管理)
- Pandas, NumPy, Polars
- XGBoost, scikit-learn
- yfinance

### 安裝
```bash
poetry install
poetry shell
```

---

## ⚠️ 風險聲明

本系統僅供輔助分析使用，不構成任何投資建議。股市投資有風險，請審慎評估。

---

**最後更新**: 2025-11-20  
**ML System Version**: 1.0 (Production Ready)
