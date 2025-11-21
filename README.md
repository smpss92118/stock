# 台股 ML-Enhanced 交易系統

自動化台股型態識別與 ML 增強交易系統，每日掃描 HTF/CUP 型態並使用機器學習過濾高品質訊號。

## 🎯 系統簡介

本系統包含兩個並行的每日掃描系統：
1. **原始策略掃描**: 基於技術型態的傳統掃描（HTF, CUP, VCP）
2. **ML 增強掃描**: 使用 XGBoost 模型過濾，提供高品質訊號推薦

**核心優勢**:
- ✅ 年化報酬 **151.2%** (HTF Trailing with Pyramiding)
- ✅ ML 增強報酬 **146.7%** (CUP R=2.0 ML 0.5)
- ✅ Sharpe Ratio **3.13** (風險調整後收益極佳)
- ✅ 勝率 **74.6%** (ML 過濾後)
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

### 最佳策略組合（允許 Pyramiding）🏆

**Top 3 策略**：
1. **HTF Trailing (Baseline)**: 年化 **151.2%**, Sharpe **1.19**, 勝率 **38.7%**
2. **CUP R=2.0 (ML 0.5)**: 年化 **146.7%**, Sharpe **3.13**, 勝率 **74.6%** ⭐
3. **CUP R=3.0 (ML 0.5)**: 年化 **125.6%**, Sharpe **2.76**, 勝率 **73.2%**

### 系統配置

**回測參數**：
- ✅ **允許 Pyramiding**：同一股票可多次進場（捕捉超級股票）
- ⏱️ **追蹤窗口**：30 天（最佳平衡點）
- 💰 **初始資金**：100 萬
- 📊 **最大持倉**：10 個部位
- 📈 **部位大小**：總資產的 10%（複利）

**新增指標**：
- 平均持倉天數
- 最大連勝/連敗
- 最大回撤 (MDD)

**結論**: ML 系統提供最佳風險調整後收益（Sharpe 3.13），適合追求穩健報酬的投資人。HTF Trailing 提供最高絕對報酬，適合可承受較高波動的投資人。

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
- **Pyramiding**: 允許同股票多次進場（最佳化報酬）
- **追蹤窗口**: 30 天（訊號後 30 天內等待進場）
- **出場策略**: Trailing Stop / Fixed R-multiple
- **現金管理**: 每次進場前檢查現金，T+0 假設

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

**最後更新**: 2025-11-21  
**ML System Version**: 2.0  
**系統狀態**: Production Ready  
**關鍵改進**: 移除 No Pyramiding限制、30天追蹤窗口、完整 TPEX 數據源
