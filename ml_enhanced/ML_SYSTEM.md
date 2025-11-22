# ML Enhanced 系統技術細節

本文件提供 ML Enhanced 系統的詳細技術資訊，包含模型訓練、特徵重要性與性能分析。

> [!NOTE]
> 本文件為技術細節參考，整體系統運作邏輯請參考 [ML Enhanced 系統文件](file:///Users/sony/ml_stock/stock/docs/05_ML_Enhanced系統.md)。

## 模型架構總覽

### 9 模型矩陣

| Pattern | Exit Mode | 模型檔名 | 訓練樣本數 | ROC AUC |
|---------|-----------|----------|-----------|---------|
| HTF | fixed_r2_t20 | stock_selector_htf_fixed_r2_t20.pkl | ~4,000 | 0.60 |
| HTF | fixed_r3_t20 | stock_selector_htf_fixed_r3_t20.pkl | ~4,000 | 0.58 |
| HTF | trailing_15r | stock_selector_htf_trailing_15r.pkl | ~4,000 | 0.63 |
| CUP | fixed_r2_t20 | stock_selector_cup_fixed_r2_t20.pkl | ~4,000 | 0.56 |
| CUP | fixed_r3_t20 | stock_selector_cup_fixed_r3_t20.pkl | ~4,000 | 0.55 |
| CUP | trailing_15r | stock_selector_cup_trailing_15r.pkl | ~4,000 | 0.57 |
| VCP | fixed_r2_t20 | stock_selector_vcp_fixed_r2_t20.pkl | ~4,000 | 0.58 |
| VCP | fixed_r3_t20 | stock_selector_vcp_fixed_r3_t20.pkl | ~4,000 | 0.56 |
| VCP | trailing_15r | stock_selector_vcp_trailing_15r.pkl | ~4,000 | 0.59 |

**總訓練樣本**: 約 36,822 (12,274 訊號 × 3 出場方式)

---

## 特徵工程詳解

### 24 項特徵清單

#### 1. 型態品質特徵 (3 項)
- `buy_price_pct`: 買入價相對當前價百分比
- `stop_price_pct`: 停損價相對當前價百分比
- `risk_pct`: 風險百分比 (買入價-停損價)/買入價

#### 2. 成交量特徵 (3 項)
- `volume_ratio`: 當前量 / MA50 量
- `volume_trend`: 成交量趨勢 (最近 5 日斜率)
- `volume_ma_ratio`: MA20 量 / MA50 量

#### 3. 動能指標 (3 項)
- `price_change_5d`: 5 日價格變化百分比
- `price_change_20d`: 20 日價格變化百分比
- `momentum`: 動量指標 (close - close_10d_ago) / close_10d_ago

#### 4. RSI 指標 (2 項)
- `rsi_14`: 14 日 RSI
- `rsi_divergence`: RSI 與價格背離指標

#### 5. 趨勢特徵 (3 項)
- `ema_alignment`: EMA 排列 (EMA12 > EMA26)
- `trend_strength`: 趨勢強度 (ADX 指標)
- `ma_slope`: MA50 斜率

#### 6. 波動特徵 (2 項)
- `volatility_20d`: 20 日波動率 (標準差)
- `atr_percent`: ATR 佔價格百分比

#### 7. 市場環境 (2 項)
- `near_52w_high`: 距離 52 週高點百分比
- `above_ma50`: 當前價是否高於 MA50 (布林值)

#### 8. RS Rating (2 項)
- `rs_rating`: 相對強度評分 (0-100)
- `rs_trend`: RS Rating 趨勢 (最近變化)

#### 9. 型態專屬特徵 (3 項)
- `htf_grade_encoded`: HTF Grade (A=3, B=2, C=1, N/A=0)
- `cup_depth`: CUP 深度百分比
- `vcp_contractions`: VCP 收縮次數

#### 10. 訊號密度 (1 項)
- `pattern_count_30d`: 最近 30 天該股票型態訊號數量

---

## 訓練流程

### 步驟 1: 數據準備

**腳本**: `ml_enhanced/scripts/prepare_ml_data.py`

**數據來源**: `data/processed/pattern_analysis_result.csv`

**標註邏輯**:

**Fixed R=2.0**:
- 成功 (1): 突破後漲幅 ≥ 2 × risk 且 ≤ 20 天內
- 失敗 (0): 觸及停損或 20 天內未達 2R

**Fixed R=3.0**:
- 成功 (1): 突破後漲幅 ≥ 3 × risk 且 ≤ 20 天內
- 失敗 (0): 觸及停損或 20 天內未達 3R

**Trailing 1.5R**:
- 成功 (1): 使用 Trailing Stop 出場有獲利
- 失敗 (0): 停損或時間出場虧損

### 步驟 2: 模型訓練

**腳本**: `ml_enhanced/scripts/train_models.py`

**XGBoost 超參數**:
```
{
    'max_depth': 3,
    'learning_rate': 0.1,
    'n_estimators': 100,
    'min_child_weight': 1,
    'gamma': 0,
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'scale_pos_weight': auto (平衡正負樣本),
    'objective': 'binary:logistic',
    'eval_metric': 'auc'
}
```

**訓練策略**:
- 訓練/測試分割: 80/20
- Early Stopping: 20 rounds
- 評估指標: ROC AUC, 準確率, Precision, Recall

### 步驟 3: 特徵重要性

**Top 10 重要特徵** (HTF Trailing 範例):
1. `rs_rating` (28.5%)
2. `buy_price_pct` (12.3%)
3. `momentum` (9.7%)
4. `rsi_14` (8.1%)
5. `volume_ratio` (7.4%)
6. `volatility_20d` (6.8%)
7. `risk_pct` (5.9%)
8. `trend_strength` (5.2%)
9. `near_52w_high` (4.7%)
10. `htf_grade_encoded` (4.1%)

**洞察**:
- RS Rating 是最關鍵特徵 (相對強度)
- 買入價位置與風險比例很重要
- 動能與 RSI 協助判斷進場時機
- 型態品質 (HTF Grade) 有顯著影響

---

## 模型性能

### ROC AUC 分數

**HTF 模型**: 0.58-0.63 (Trailing 最佳)
- HTF 型態快速爆發，Trailing 能捕捉大漲幅

**CUP 模型**: 0.55-0.57
- CUP 型態穩健，Fixed R=3.0 效果略好

**VCP 模型**: 0.56-0.59 (Trailing 略優)
- VCP 趨勢延伸，Trailing 適合

**總結**: ROC AUC 0.55-0.63 表示模型有明顯預測能力，過濾效果顯著。

### 回測績效 (ML ≥ 0.4)

**最佳組合**:
- HTF Fixed R=2.0 (ML 0.4): 年化 156%, Sharpe 2.59, 勝率 60.2%
- HTF Fixed R=2.0 (ML 0.5): 年化 145.7%, Sharpe 2.62, 勝率 62.8%
- CUP Fixed R=3.0 (ML 0.5): 年化 129.7%, Sharpe 2.09, 勝率 74.4%

**ML 閾值效果**:
- ML ≥ 0.5: 訊號少但品質極高 (Elite)
- ML ≥ 0.4: 平衡品質與數量 (Strong)
- ML < 0.4: 參考價值低

---

## 模型維護

### 每週重訓

**時間**: 每週日 02:00

**流程** (`ml_enhanced/weekly_retrain.py`):
1. 準備最新訓練數據 (包含本週新訊號)
2. 重新訓練 9 個模型
3. 回測驗證新模型績效
4. 更新模型檔案

**重訓週期選擇**:
- 每週: 及時反映市場變化
- 避免每日: 防止過度擬合雜訊

### 模型監控

**關鍵指標**:
- ROC AUC 應維持 > 0.55
- 回測年化報酬應維持 > 100%
- Sharpe 應維持 > 2.0

**異常偵測**:
- 若 ROC AUC < 0.52: 模型失效，需檢查數據或特徵
- 若勝率 < 55%: 市場環境改變，需調整策略

---

## 相關文件

- [ML Enhanced 系統](file:///Users/sony/ml_stock/stock/docs/05_ML_Enhanced系統.md) - 系統運作邏輯
- [型態策略](file:///Users/sony/ml_stock/stock/docs/03_型態策略.md) - 型態偵測基礎
- [開發指南](file:///Users/sony/ml_stock/stock/docs/09_開發指南.md) - 調整 ML 模型

## 實作參考

- 特徵工程: [src/ml/features.py](file:///Users/sony/ml_stock/stock/src/ml/features.py)
- 數據準備: [ml_enhanced/scripts/prepare_ml_data.py](file:///Users/sony/ml_stock/stock/ml_enhanced/scripts/prepare_ml_data.py)
- 模型訓練: [ml_enhanced/scripts/train_models.py](file:///Users/sony/ml_stock/stock/ml_enhanced/scripts/train_models.py)
- ML 回測: [ml_enhanced/scripts/run_ml_backtest.py](file:///Users/sony/ml_stock/stock/ml_enhanced/scripts/run_ml_backtest.py)
- 每日掃描: [ml_enhanced/daily_ml_scanner.py](file:///Users/sony/ml_stock/stock/ml_enhanced/daily_ml_scanner.py)
- 每週重訓: [ml_enhanced/weekly_retrain.py](file:///Users/sony/ml_stock/stock/ml_enhanced/weekly_retrain.py)
