# Week 2: ML Model Training 總結

## 訓練結果

### 數據分割
- **訓練集**: 11,226 samples (2023-08-17 to 2025-03-10)
- **測試集**: 2,807 samples (2025-03-10 to 2025-11-14)
- **Winners**: 20.7% (>10% return)

---

## Model 1: Stock Selector (股票選擇)

### 模型配置
- **Algorithm**: XGBoost Classifier
- **Parameters**:
  - n_estimators=200
  - max_depth=5
  - learning_rate=0.05

### 績效指標
- **ROC AUC**: 0.7269
- **Accuracy**: 82%
- **Precision (Winner)**: 35%
- **Recall (Winner)**: 3%

### Threshold 分析

| Threshold | Precision | Recall | Selected % |
|-----------|-----------|--------|------------|
| 0.5 | 34.78% | 3.22% | 1.6% |
| **0.6** | **50.00%** | **0.20%** | **0.1%** |
| 0.7 | 0.00% | 0.00% | 0.0% |

### 特徵重要性 (Top 5)

| Feature | Importance |
|---------|------------|
| risk_pct | 27.9% |
| atr_ratio | 13.7% |
| distance_to_buy_pct | 13.6% |
| volatility | 12.9% |
| grade_numeric | 10.9% |

### 問題分析

**❌ Threshold 0.6 過於保守**:
- 只選擇 0.1% 的訊號 (14,033 樣本中僅 14 個)
- Recall 僅 0.20% (幾乎錯過所有 winners)
- **結論**: 模型無法有效區分 winners 和 losers

**原因**:
1. 訓練數據不平衡 (21.4% winners vs 78.6% losers)
2. 特徵對勝率的預測能力有限
3. 10% return threshold 可能過高

---

## Model 2: Position Sizer (倉位分配)

### 模型配置
- **Algorithm**: XGBoost Regressor
- **Parameters**: 同 Stock Selector

### 績效指標
- **MSE**: 0.008256
- **RMSE**: 9.09%
- **R² Score**: -0.0203 ❌
- **Correlation**: 0.0933 ❌

### 預測分布

| Metric | Actual | Predicted |
|--------|--------|-----------|
| Mean | 1.03% | 1.43% |
| Median | 0.00% | 1.38% |
| Min | -29.03% | -13.66% |
| Max | 38.57% | 16.61% |

### 特徵重要性 (Top 5)

| Feature | Importance |
|---------|------------|
| risk_pct | 17.7% |
| ma_trend | 16.3% |
| atr_ratio | 15.6% |
| volatility | 13.8% |
| rsi_14 | 12.8% |

### 問題分析

**❌ 預測能力極弱**:
- R² = -0.02 (負值表示比平均值還差)
- Correlation = 0.09 (幾乎無相關性)
- **結論**: 模型無法預測實際報酬

**原因**:
1. 報酬率的隨機性高 (Median 0%)
2. 特徵無法捕捉未來價格走勢
3. 市場噪音遠大於訊號

---

## 整體評估

### ❌ ML 模型表現不佳

**Stock Selector**:
- ROC AUC 0.73 尚可，但實際應用時過於保守
- Threshold 0.6 幾乎不選擇任何訊號
- Threshold 0.5 選擇 1.6%，但 Precision 僅 35%

**Position Sizer**:
- 完全無法預測報酬 (R² < 0)
- 不應用於實際倉位分配

### 可能原因

1. **特徵不足**: 當前特徵無法捕捉型態成功的關鍵因素
2. **標籤噪音**: 10% return threshold 可能過高，導致正樣本過少
3. **市場隨機性**: 短期報酬受市場噪音影響大
4. **數據量**: 14,033 樣本可能不足以訓練穩健模型

---

## 下一步建議

### 選項 A: 改進 ML 模型 (需要更多時間)

**改進方向**:
1. **降低 Winner threshold**: 5% instead of 10%
2. **增加特徵**:
   - 市場狀態 (TAIEX 趨勢)
   - 產業相對強度
   - 訊號品質評分
3. **處理數據不平衡**: SMOTE, class_weight
4. **嘗試其他模型**: LightGBM, Neural Network

### 選項 B: 簡化 ML 應用 ✅ **推薦**

**實用策略**:
1. **放棄 Position Sizer**: 使用固定 10% 倉位
2. **降低 Stock Selector threshold**: 使用 0.4-0.5
3. **僅作為輔助過濾**: 原始策略 + ML 輕度過濾

### 選項 C: 放棄 ML，回歸原始策略 ⚠️

**理由**:
- 原始策略 (HTF Trailing Stop) 已達 143.2% 年化報酬
- ML 模型預測能力有限
- 增加複雜度但未必提升績效

---

## Week 3 計劃

**決定**: 繼續 Week 3，但調整策略

### 修改後的 ML 整合

1. **Stock Selector**:
   - 使用 threshold 0.4 (選擇約 5-10% 訊號)
   - 僅作為輔助過濾，不完全依賴

2. **Position Sizer**:
   - **不使用** (預測能力太弱)
   - 改用固定 10% 倉位

3. **回測對比**:
   - Original (無 ML)
   - ML Filtered (threshold 0.4)
   - ML Filtered (threshold 0.5)

### 預期結果

**如果 ML Filtered > Original**:
- 證明 ML 有價值，繼續優化

**如果 ML Filtered < Original**:
- 放棄 ML，回歸原始策略
- 刪除 `ml_enhanced/` 目錄

---

**報告生成時間**: 2025-11-20  
**模型儲存位置**: `stock/ml_enhanced/models/`
