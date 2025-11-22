# 台股 ML-Enhanced 交易系統

自動化台股型態識別與 ML 增強交易系統，每日掃描 HTF/CUP 型態並使用機器學習過濾高品質訊號。

## 🎯 系統簡介

本系統包含兩個並行的每日掃描系統：
1. **原始策略掃描**: 基於技術型態的傳統掃描（HTF, CUP, VCP）
2. **ML 增強掃描**: 使用 XGBoost 模型過濾，提供高品質訊號推薦

**核心優勢**:
- ✅ **智能出場策略**: ML 自動推薦最佳出場方式
- ✅ 年化報酬 **156.0%** (HTF Fixed R=2.0 ML 0.4)
- ✅ Sharpe Ratio **2.62** (HTF Fixed R=2.0 ML 0.5)
- ✅ 勝率 **74.4%** (CUP Fixed R=3.0 ML 0.5)
- ✅ **9 個 ML 模型**: 3 patterns × 3 exit strategies
- ✅ 全自動化：每日掃描 + 每週模型更新
- ✅ 完整數據：TWSE + TPEX 約 1900 檔股票

---

## 📂 專案結構

```
stock/
├── main.py                    # 原始策略每日掃描 (Crontab Entry 1)
├── config.py                  # 系統配置
├── scripts/                   # 核心執行腳本
│   ├── update_daily_data.py   # 數據更新 (TWSE + TPEX 約1900檔)
│   ├── run_historical_analysis.py  # 歷史型態分析
│   ├── run_daily_scan.py      # 每日訊號掃描
│   ├── run_backtest.py        # 回測引擎 (支援 Pyramiding)
│   ├── generate_daily_position_report.py  # 每日持倉報告
│   └── backtest_engine_v2.py  # V2 回測引擎
├── src/                       # 核心邏輯
│   ├── strategies/            # 策略邏輯 (HTF, CUP, VCP)
│   ├── ml/                    # [NEW] ML 共享模組 (features.py)
│   ├── utils/                 # [NEW] 通用工具 (logger.py, data_loader.py)
│   └── crawlers/              # 數據爬蟲
├── ml_enhanced/               # ML 增強系統 (Production v2.0)
│   ├── daily_ml_scanner.py    # ML 每日掃描 (Crontab Entry 2)
│   ├── weekly_retrain.py      # ML 週訓練 (Crontab Entry 3)
│   ├── scripts/
│   │   ├── prepare_ml_data.py # 特徵工程 (多出場方式)
│   │   ├── train_models.py    # 模型訓練 (9 個模型)
│   │   └── run_ml_backtest.py # ML 回測驗證
│   ├── models/                # 9 個 ML 模型檔案 (pattern × exit)
│   ├── data/                  # ML 訓練數據
│   ├── daily_reports/         # 每日 ML 報告
│   ├── results/               # 回測結果
│   └── docs/                  #（文檔集中於 docs/ml/）
├── optimization/              # 超參數優化 (Historical)
│   └── optimize_hyperparameters.py
├── data/                      # 數據存放
│   ├── raw/daily_quotes/      # 每日股價
│   └── processed/             # 處理後數據
├── daily_tracking_stock/      # 每日原始報告
├── docs/                      # 文檔（索引見 docs/README.md）
│   ├── system_overview.md
│   ├── operations.md
│   ├── strategy_patterns.md
│   ├── backtest_engine.md
│   ├── ml/
│   │   ├── overview.md
│   │   └── system_logic.md
│   └── optimization/
│       ├── hyperparameter_guide.md
│       └── change_log.md
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

詳細設定請見 `docs/operations.md`

---

## 📊 每日輸出報告

### 1. 原始策略報告
**位置**: `stock/daily_tracking_stock/YYYY-MM-DD/daily_summary.md`

**內容**:
- 所有 HTF/CUP/VCP 型態訊號
- 過去一週訊號彙整
- Top 3 策略績效排名

### 2. ML 增強報告
**位置**: `stock/ml_enhanced/daily_reports/YYYY-MM-DD/ml_daily_summary.md`

**內容**:
- ✅ **ML 推薦訊號** (ML 分數 ≥ 0.4, 勝率 70-78%)
  - **NEW**: 智能推薦最佳出場策略 (Fixed R=2.0/3.0 或 Trailing)
  - 顯示所有 3 種策略的 ML 分數
- 📋 原始訊號對比 (ML 分數 < 0.4)
- 📅 過去一週訊號彙整
- 🏆 Top 3 Strategies (ML-Enhanced, 動態更新)
- 📖 交易策略說明 (從最新回測讀取)

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

## 📈 策略績效 (回測驗證 2025-11-22)

### 最佳策略組合（ML 智能選擇）🏆

**Top 3 策略**：
1. **HTF Fixed R=2.0 (ML 0.4)**: 年化 **156.0%**, Sharpe **2.59**, 勝率 **60.2%**, 交易 425 ⭐
2. **HTF Fixed R=2.0 (ML 0.5)**: 年化 **145.7%**, Sharpe **2.62**, 勝率 **62.8%**, 交易 374 ⭐
3. **CUP Fixed R=3.0 (ML 0.5)**: 年化 **129.7%**, Sharpe **2.09**, 勝率 **74.4%**, 交易 246

### 系統配置

**回測參數**：
- ✅ **允許 Pyramiding**：同一股票可多次進場（捕捉超級股票）
- ⏱️ **追蹤窗口**：30 天（最佳平衡點）
- 💰 **初始資金**：100 萬
- 📊 **最大持倉**：10 個部位
- 📈 **部位大小**：總資產的 10%（複利）

**ML v2.0 新功能**：
- 🤖 **9 個模型**: 3 patterns × 3 exit strategies
- 🎯 **智能選擇**: 自動推薦最佳出場方式
- 📊 **動態更新**: 報告數據自動從最新回測讀取
- 📈 **最佳表現**: ROC AUC 0.55-0.63, HTF 模型表現最佳

**結論**: ML 系統智能選擇出場策略，最大化每個訊號的潛力。HTF Fixed 提供優異的風險調整後報酬 (Sharpe > 2.5)。

---

## 🔬 核心技術

### 型態識別
- **HTF (High Tight Flag)**: 高檔旗形突破
- **CUP (Cup with Handle)**: 杯柄型態
- **VCP (Volatility Contraction Pattern)**: 波動收縮

### ML 模型 (v2.0 Multi-Exit System)
- **系統架構**: 9 個獨立模型 (3 patterns × 3 exit strategies)
- **算法**: XGBoost Classifier
- **特徵**: 24 項（型態品質、成交量、動能、RSI、趨勢/波動、市場環境、RS、型態專屬、訊號密度）
- **訓練**: 36,822 樣本 (12,274 訊號 × 3 出場方式)
- **性能**: ROC AUC 0.55-0.63, Threshold 0.4
- **智能功能**: 自動推薦最佳出場策略

### 回測引擎
- **資金管理**: 有限資本 (100萬初始)
- **倉位控制**: 每筆 10%, 最多 10 檔
- **複利計算**: 基於當前總資產
- **Pyramiding**: 允許同股票多次進場（最佳化報酬）
- **追蹤窗口**: 30 天（訊號後 30 天內等待進場）
- **出場策略**: Trailing Stop / Fixed R-multiple
- **現金管理**: 每次進場前檢查現金，T+0 假設

---

## 📖 文檔

- `docs/README.md` - 文檔索引
- `docs/system_overview.md` - 系統架構與流程
- `docs/operations.md` - 排程與手動執行
- `docs/strategy_patterns.md` - 型態定義細節
- `docs/backtest_engine.md` - 回測引擎邏輯 ⭐
- `docs/ml/overview.md` / `docs/ml/system_logic.md` - ML 系統與特徵說明
- `docs/optimization/hyperparameter_guide.md` / `docs/optimization/change_log.md` - 策略優化指南與紀錄
- （產出報告，未重構）`docs/backtest_report_v2.md`, `docs/optimization_vs_baseline.md`

---

## 🛠️ 系統需求

- Python 3.11+
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

**最後更新**: 2025-11-22  
**ML System Version**: 2.0 (Multi-Exit)  
**系統狀態**: Production Ready  
**關鍵改進**: 9 個 ML 模型 (3 patterns × 3 exits)、智能出場選擇、報告動態更新
