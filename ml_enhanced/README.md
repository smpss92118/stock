# ML-Enhanced Trading System

## 概述

這是基於原始交易系統的 ML 增強版本，使用機器學習進行：
- **股票選擇**: 預測訊號勝率，過濾低品質訊號
- **倉位分配**: 動態調整每個股票的資金配置
- **動態管理**: 提前出場虧損部位

**重要**: 原始 `main.py` 完全不受影響，此系統完全獨立運行。

---

## 目錄結構

```
ml_enhanced/
├── main_ml.py                  # ML 版本的 main.py
├── ml_engine.py                # ML 決策引擎
├── data/
│   ├── ml_features.csv         # 訓練特徵數據
│   └── ml_predictions.csv      # 預測結果
├── models/
│   ├── stock_selector.pkl      # 股票選擇模型
│   └── position_sizer.pkl      # 倉位分配模型
├── scripts/
│   ├── prepare_ml_data.py      # 特徵工程
│   ├── train_models.py         # 模型訓練
│   ├── run_ml_backtest.py      # ML 回測
│   └── run_ml_scan.py          # ML 每日掃描
└── results/
    ├── ml_backtest_results.csv
    ├── performance_chart.png   # 績效日線圖
    └── comparison_report.md    # 對比報告
```

---

## 使用方式

### 1. 數據準備 (首次執行)

```bash
# 生成 ML 訓練數據
python stock/ml_enhanced/scripts/prepare_ml_data.py
```

### 2. 訓練模型

```bash
# 訓練股票選擇和倉位分配模型
python stock/ml_enhanced/scripts/train_models.py
```

### 3. 運行 ML 回測

```bash
# 使用 ML 模型進行歷史回測
python stock/ml_enhanced/scripts/run_ml_backtest.py
```

### 4. 每日運行 (生產環境)

```bash
# 運行 ML 增強的每日流程
python stock/ml_enhanced/main_ml.py
```

---

## ML 模型說明

### Stock Selector (股票選擇模型)

**目的**: 預測每個訊號的勝率

**輸入特徵**:
- 型態品質 (HTF Grade, 距離買入價, 成交量)
- 技術指標 (RSI, MA 趨勢, 波動率)
- 市場環境 (TAIEX 趨勢, 訊號數量)

**輸出**: `win_probability` (0-1)

**決策規則**:
- `win_probability > 0.6`: 交易
- `win_probability < 0.6`: 跳過

### Position Sizer (倉位分配模型)

**目的**: 預測每個訊號的預期報酬

**輸入特徵**: 所有特徵 + `win_probability`

**輸出**: `expected_return`

**決策規則**:
- 高預期報酬 (> 20%): 大倉位 (15-20%)
- 中預期報酬 (10-20%): 中倉位 (10%)
- 低預期報酬 (< 10%): 小倉位 (5%) 或跳過

---

## 績效對比

運行回測後，查看 `results/comparison_report.md` 了解 ML 系統 vs 原始系統的績效對比。

---

## 回滾

如果 ML 系統表現不佳，直接刪除整個 `ml_enhanced/` 目錄即可：

```bash
rm -rf stock/ml_enhanced/
```

原始 `main.py` 完全不受影響。

---

## 開發狀態

- [x] Week 1: 數據準備
- [ ] Week 2: 模型訓練
- [ ] Week 3: 回測整合
- [ ] Week 4: 視覺化與部署
