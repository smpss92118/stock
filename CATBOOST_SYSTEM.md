# CatBoost Enhanced 全局模型系統文檔

**狀態**: Production Ready (2025-11-22)
**版本**: 1.0 (P0 全局模型 + P1 Embargo 隔離 + P2 樣本權重)
**最後更新**: 2025-11-22

---

## 🎯 系統概述

### 兩套並行系統架構

本項目現在運行**兩套完全獨立的 ML 系統**，用於真實交易比較：

| 系統 | 架構 | 模型數量 | 樣本數 | 訓練方式 | 狀態 |
|------|------|---------|--------|---------|------|
| **ML Enhanced** | 獨立模型 | 9 個 XGBoost | 36,822 | 傳統監督學習 | Production v2.0 |
| **CatBoost Enhanced** | 全局模型 | 1 個 CatBoost | 28,758 | P0+P1+P2 (新) | Production v1.0 |

### 核心改進 (CatBoost Enhanced)

**P0: 全局單一模型**
- 單一 CatBoost 分類器預測 4 級品質 (A/B/C/D)
- Pattern 和 Exit Mode 作為**類別特徵** (不是標籤)
- 28,758 個樣本學習最佳 pattern×exit_mode 組合
- 可捕捉不同模式間的交互效應

**P1: Embargo 隔離防泄漏**
- PurgedGroupKFold 按日期分組 5-fold 交叉驗證
- Train 和 Test 之間 20 天 embargo buffer
- 防止測試集訪問訓練期間生成的特徵
- 模擬真實交易環境 (需要延遲)

**P2: 三層樣本權重**
- Layer 1: Sigmoid 分數幅度權重 - 高利潤交易獲得更高權重
- Layer 2: 標籤等級權重 - A=2.0x, B=1.5x, C/D=1.0x
- Layer 3: 類頻率補償 - 平衡訓練集類別不平衡

---

## 📂 專案結構

```
stock/
├── ml_enhanced/                          # ML v2.0 (9 獨立模型)
│   ├── daily_ml_scanner.py              # ✅ 每日掃描 (既有)
│   ├── weekly_retrain.py                # ✅ 週期重訓 (既有)
│   ├── scripts/
│   │   ├── prepare_ml_data.py           # ✅ 特徵準備
│   │   ├── train_models.py              # ✅ 9 個模型訓練
│   │   └── run_ml_backtest.py           # ✅ 回測驗證
│   └── models/, data/, results/ ...
│
├── catboost_enhanced/                    # CatBoost v1.0 (1 全局模型) ⭐ NEW
│   ├── daily_ml_scanner.py              # 🆕 日常推薦生成
│   ├── weekly_retrain.py                # 🆕 週期重訓協調
│   ├── scripts/
│   │   ├── prepare_catboost_data.py     # 🆕 特徵準備
│   │   ├── train.py                     # 🆕 P0+P1+P2 訓練
│   │   └── run_catboost_backtest.py     # 🆕 回測驗證
│   ├── configs/                         # 🆕 配置管理
│   │   ├── model_config.py
│   │   ├── feature_config.py
│   │   └── constants.py
│   ├── utils/                           # 🆕 工具函數庫
│   │   ├── loss_functions.py (P2)
│   │   ├── data_splitter.py (P1)
│   │   └── metrics.py
│   └── models/, data/, results/ ...
│
├── src/                                  # 共享核心模組
│   ├── ml/
│   │   ├── constants.py                 # 🆕 全局常數
│   │   ├── labeling.py                  # 🆕 標籤計算
│   │   └── features.py
│   ├── utils/
│   ├── strategies/
│   └── crawlers/
│
└── main.py, config.py, scripts/ ...      # 原始策略
```

---

## ⚙️ Crontab 配置指南

### 📌 現有配置問題分析

你的現有 crontab 配置：

```bash
# 每天晚上 7:00 - 執行原始策略掃描
0 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python main.py >> /Users/sony/ml_stock/logs/original_scan.log 2>&1

# 每天晚上 7:05 - 執行 ML 增強掃描
5 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/ml_scanner.log 2>&1

# 每週日凌晨 2:00 - 重新訓練 ML 模型
0 2 * * 0 cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/ml_retrain.log 2>&1
```

### ❌ 存在的問題

#### 1. **缺少 CatBoost Enhanced 的日常掃描**
現在只運行 ml_enhanced 的日常掃描，完全沒有執行 catboost_enhanced 的推薦生成。

**影響**: CatBoost 模型每週訓練但從不預測，無法驗證其實際效果。

#### 2. **CatBoost 模型無週期重訓協調**
你有 ml_enhanced 的 weekly_retrain.py，但 catboost_enhanced 的 weekly_retrain.py 沒有被執行。

**影響**: 無法並行比較兩套系統的性能。

#### 3. **日常掃描時序不合理**
19:00 (原始策略) → 19:05 (ML 掃描)，但都沒有等待數據準備完成。

**潛在風險**: 如果股市數據延遲更新，可能使用過時數據。

#### 4. **缺少依賴關係**
三個 crontab 任務沒有依賴關係定義，可能出現：
- 日常掃描執行時模型還未訓練完畢
- 數據準備還未完成就開始掃描

#### 5. **日誌輸出無錯誤通知機制**
所有輸出都直接重定向到文件，沒有異常時的郵件通知，容易發現不了失敗。

---

## ✅ 正確的 Crontab 配置

### 推薦配置方案

```bash
# ════════════════════════════════════════════════════════════════
# 每日流程 (19:00 - 19:20)
# ════════════════════════════════════════════════════════════════

# 1️⃣  19:00 - 執行原始策略掃描
0 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python main.py >> /Users/sony/ml_stock/logs/original_scan.log 2>&1

# 2️⃣  19:05 - 執行 ML Enhanced 掃描 (等待原始策略完成)
5 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/ml_enhanced_scanner.log 2>&1

# 3️⃣  19:10 - 執行 CatBoost Enhanced 掃描 (新增)
10 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python catboost_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/catboost_scanner.log 2>&1


# ════════════════════════════════════════════════════════════════
# 每週流程 (週日 01:00 - 03:00)
# ════════════════════════════════════════════════════════════════

# 4️⃣  02:00 - ML Enhanced 週期重訓 (並行執行)
0 2 * * 0 cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/ml_enhanced_retrain.log 2>&1

# 5️⃣  02:00 - CatBoost Enhanced 週期重訓 (並行執行，新增)
0 2 * * 0 cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python catboost_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/catboost_retrain.log 2>&1
```

### 配置說明

| 時間 | 任務 | 說明 |
|------|------|------|
| **19:00** | 原始策略掃描 | 檢測 HTF/CUP/VCP 型態訊號 (耗時 5 分鐘) |
| **19:05** | ML Enhanced 掃描 | 用 9 個 XGBoost 模型過濾訊號 (耗時 3 分鐘) |
| **19:10** | CatBoost Enhanced 掃描 | 用全局 CatBoost 模型預測訊號品質 (耗時 2 分鐘) **新** |
| **02:00 (週日)** | 並行週期重訓 | 同時重訓兩套系統並自動對比 (耗時 30 分鐘) **新** |

### 時序圖

```
週一至週六:
19:00 ┌────────────────────────────────┐
      │ 原始策略掃描 (5min)            │
19:05 └────────────────────────────────┘
      ┌────────────────────┐
      │ ML Enhanced 掃描    │
19:05 │ (3min)             │
19:08 └────────────────────┘
                ┌─────────────────────┐
19:08           │ CatBoost 掃描       │
19:10           │ (2min)              │
                └─────────────────────┘
19:10 完成，所有推薦清單生成

─────────────────────────────────────────

週日:
02:00 ┌────────────────────────────────┐
      │ ML Enhanced 重訓 (15min)        │
      │ ││                             │
      │ CatBoost 重訓 (20min)   ──┐    │ (並行)
      │                          │    │
      │ 並行回測驗證 (10min)    ──┤────│
      │                          │    │
      │ 自動對比分析 (5min)     ──┘    │
02:50 └────────────────────────────────┘
輸出: weekly_comparison_report.md + comparison_data.json
```

---

## 🚀 使用指南

### 初始化 (首次執行)

```bash
cd /Users/sony/ml_stock/stock

# 準備 CatBoost 資料並訓練
poetry run python catboost_enhanced/scripts/prepare_catboost_data.py
poetry run python catboost_enhanced/scripts/train.py

# 執行回測驗證
poetry run python catboost_enhanced/scripts/run_catboost_backtest.py
```

**預期輸出:**
- `catboost_enhanced/data/catboost_features.csv` (28,758 × 54)
- `catboost_enhanced/models/catboost_global.cbm`
- `catboost_enhanced/results/backtest_by_group.csv` ⭐

### 日常執行 (手動測試)

```bash
cd /Users/sony/ml_stock/stock

# 測試 CatBoost 日常掃描
poetry run python catboost_enhanced/daily_ml_scanner.py

# 輸出
# catboost_enhanced/results/daily_scan_[YYYY-MM-DD].csv
# catboost_enhanced/results/daily_scan_[YYYY-MM-DD].html
```

### 週期重訓 (手動測試)

```bash
cd /Users/sony/ml_stock/stock

# 並行重訓兩套系統 + 對比分析
poetry run python catboost_enhanced/weekly_retrain.py

# 輸出
# catboost_enhanced/results/weekly_comparison_report.md
# catboost_enhanced/results/comparison_data.json
```

---

## 📊 系統架構與數據流

### 日常流程圖

```
市場數據 (每日收盤)
     │
     ▼
┌──────────────────────┐
│ main.py              │  (19:00)
│ 原始策略掃描         │
│ HTF/CUP/VCP 檢測     │
└───────────┬──────────┘
            │
            ▼
      訊號: *.csv
            │
     ┌──────┴─────────┐
     │                │
     ▼                ▼
┌─────────────┐ ┌──────────────┐
│ ML Enhanced │ │ CatBoost     │  (19:05-19:10)
│ 9 模型過濾   │ │ Enhanced     │
│ (ML v2.0)   │ │ 全局預測     │
└──────┬──────┘ │ (CatBoost v1.0)
       │        └──────┬───────┘
       │               │
       ▼               ▼
    報告 A.md      報告 B.md
  (70-78% 勝率)   (性能TBD)
       │               │
       └───────┬───────┘
               │
               ▼
        推薦清單 (交易員參考)
```

### 週期流程圖

```
每週日 02:00
     │
     ├─ ML Enhanced                 CatBoost Enhanced
     │  ├─ prepare_ml_data.py      ├─ prepare_catboost_data.py
     │  ├─ train_models.py         ├─ train.py (P0+P1+P2)
     │  └─ run_ml_backtest.py      └─ run_catboost_backtest.py
     │       │                         │
     │  結果: backtest_results      結果: backtest_by_group
     │       _v2.csv                   .csv
     │
     ├─ weekly_retrain.py (協調器)
     │  ├─ 自動檢測兩套結果
     │  ├─ 性能對比分析
     │  └─ 生成週報告
     │
     └─ 輸出
        ├─ weekly_comparison_report.md (Markdown)
        └─ comparison_data.json (詳細數據)
```

---

## 📈 期望的系統性能

### ML Enhanced (既有系統)

**Top 3 策略** (回測驗證 2025-11-22):
1. HTF Fixed R=2.0 (ML 0.4): 年化 **156.0%**, Sharpe **2.59**, 勝率 **60.2%**
2. HTF Fixed R=2.0 (ML 0.5): 年化 **145.7%**, Sharpe **2.62**, 勝率 **62.8%**
3. CUP Fixed R=3.0 (ML 0.5): 年化 **129.7%**, Sharpe **2.09**, 勝率 **74.4%**

### CatBoost Enhanced (新系統)

**預期性能**:
- CV Accuracy: ~25-30% (4 分類，需要改進)
- 回測結果: 待執行驗證
- 特徵重要度: ma20, ma50, vol_ma20, pattern_type

**改進空間**:
- 模型準確率低，需要調整標籤規則或特徵工程
- 樣本權重 (P2) 效果需要驗證

---

## ⚠️ 系統設置是否正確?

### 答案: **目前不完整，需要調整**

### 主要問題

#### 1. ❌ CatBoost 掃描完全缺失
**現象**: daily_ml_scanner.py 只在 ml_enhanced 目錄，catboost_enhanced 版本沒有在 crontab 執行

**後果**:
- CatBoost 模型每週訓練，但從不用於實際推薦
- 無法驗證全局模型的實際效果
- 兩套系統無法真實對比

**修正**: 添加 19:10 的 catboost_enhanced/daily_ml_scanner.py

#### 2. ❌ 週期重訓機制不對稱
**現象**: 只有 ml_enhanced/weekly_retrain.py 在執行，catboost_enhanced/weekly_retrain.py 完全沒有

**後果**:
- CatBoost 系統無法進行自動化週期重訓
- 無法自動對比兩套系統的性能
- 無法生成週比較報告

**修正**: 添加 02:00 的 catboost_enhanced/weekly_retrain.py (並行執行)

#### 3. ⚠️ 時序規劃有改善空間
**現象**: 三個日常任務各自執行，無顯式依賴關係

**潛在風險**:
- 如果數據準備延遲，日常掃描可能使用過時數據
- 日常掃描任務之間沒有同步機制
- 日誌異常無通知機制

**建議**:
- 添加明確的時間間隔和依賴檢查
- 為關鍵任務添加郵件通知 (見下方進階配置)

---

## 🔧 進階配置 (可選)

### 添加錯誤通知機制

創建 `/Users/sony/ml_stock/logs/send_alert.sh`:

```bash
#!/bin/bash
# 發送失敗通知郵件

TASK_NAME=$1
LOG_FILE=$2
ERROR_PATTERN="Error|Traceback|failed|exception"

if grep -qi "$ERROR_PATTERN" "$LOG_FILE"; then
    echo "Failed task: $TASK_NAME" | mail -s "⚠️ ML Stock Alert: $TASK_NAME Failed" your-email@example.com
fi
```

更新 crontab:

```bash
# 19:10 CatBoost 掃描 + 錯誤檢查
10 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python catboost_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/catboost_scanner.log 2>&1; bash /Users/sony/ml_stock/logs/send_alert.sh "CatBoost Daily Scan" /Users/sony/ml_stock/logs/catboost_scanner.log
```

### 添加健康檢查

創建 `/Users/sony/ml_stock/scripts/health_check.py`:

```python
import os
import json
from datetime import datetime, timedelta

def check_system_health():
    issues = []

    # 檢查最新 backtest 文件時間
    catboost_backtest = '/Users/sony/ml_stock/stock/catboost_enhanced/results/backtest_by_group.csv'
    if os.path.exists(catboost_backtest):
        mtime = os.path.getmtime(catboost_backtest)
        age = datetime.now() - datetime.fromtimestamp(mtime)
        if age > timedelta(days=7):
            issues.append(f"CatBoost backtest file is {age.days} days old")
    else:
        issues.append("CatBoost backtest file missing")

    # 檢查模型文件
    model_file = '/Users/sony/ml_stock/stock/catboost_enhanced/models/catboost_global.cbm'
    if not os.path.exists(model_file):
        issues.append("CatBoost model file missing")

    return issues

if __name__ == "__main__":
    issues = check_system_health()
    if issues:
        print("⚠️ System Health Issues:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("✅ System Health: OK")
```

在每週日 03:00 執行:

```bash
0 3 * * 0 cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python scripts/health_check.py
```

---

## 📋 更新 Crontab 的步驟

### 1. 備份現有設置
```bash
crontab -l > ~/crontab_backup_20251122.txt
```

### 2. 編輯 crontab
```bash
crontab -e
```

### 3. 替換為新配置

刪除舊的三行：
```bash
0 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python main.py >> /Users/sony/ml_stock/logs/original_scan.log 2>&1
5 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/ml_scanner.log 2>&1
0 2 * * 0 cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/ml_retrain.log 2>&1
```

添加新的五行 (見上面 [正確的 Crontab 配置](#正確的-crontab-配置) 部分)

### 4. 驗證
```bash
crontab -l  # 檢查新設置
ls -la /Users/sony/ml_stock/logs/  # 確保日誌目錄存在
```

---

## 📊 監控清單

### 每日檢查 (19:00-19:20)

- [ ] `original_scan.log` - 原始策略是否執行成功
- [ ] `ml_enhanced_scanner.log` - ML Enhanced 是否執行成功
- [ ] `catboost_scanner.log` - CatBoost Enhanced 是否執行成功 (新)
- [ ] 檢查三份推薦清單是否生成

### 每週檢查 (週日 02:00-03:00)

- [ ] `ml_enhanced_retrain.log` - ML 模型是否訓練成功
- [ ] `catboost_retrain.log` - CatBoost 模型是否訓練成功 (新)
- [ ] `weekly_comparison_report.md` - 對比報告是否生成
- [ ] `comparison_data.json` - 對比數據是否完整

### 每月檢查

- [ ] 比較兩套系統的月度績效
- [ ] 檢查模型準確率趨勢
- [ ] 評估推薦訊號品質

---

## 📖 核心檔案清單

### CatBoost Enhanced 系統檔案

**主要執行檔:**
- `catboost_enhanced/daily_ml_scanner.py` - 日常推薦 (19:10)
- `catboost_enhanced/weekly_retrain.py` - 週期重訓 (02:00)

**訓練管線:**
- `catboost_enhanced/scripts/prepare_catboost_data.py` - 特徵準備
- `catboost_enhanced/scripts/train.py` - P0+P1+P2 訓練
- `catboost_enhanced/scripts/run_catboost_backtest.py` - 回測驗證

**配置和工具:**
- `catboost_enhanced/configs/` - 訓練參數配置
- `catboost_enhanced/utils/` - P1 (PurgedGroupKFold), P2 (樣本權重)

**輸出檔:**
- `catboost_enhanced/results/daily_scan_[YYYY-MM-DD].csv/html` - 日常推薦
- `catboost_enhanced/results/backtest_by_group.csv` - 回測性能
- `catboost_enhanced/results/weekly_comparison_report.md` - 週報告

---

## ✅ 系統設置正確性總結

| 項目 | 現況 | 應為 | 狀態 |
|------|------|------|------|
| 原始策略掃描 | ✅ 19:00 | ✅ 19:00 | ✅ 正確 |
| ML Enhanced 掃描 | ✅ 19:05 | ✅ 19:05 | ✅ 正確 |
| **CatBoost 掃描** | ❌ 無 | ✅ 19:10 | ⚠️ **需要添加** |
| ML Enhanced 重訓 | ✅ 02:00 | ✅ 02:00 | ✅ 正確 |
| **CatBoost 重訓** | ❌ 無 | ✅ 02:00 並行 | ⚠️ **需要添加** |
| 錯誤通知 | ❌ 無 | ✅ 有 | ⚠️ **建議添加** |

---

## 🎯 下一步行動

### 立即 (Priority: High)

1. **更新 crontab** 添加 CatBoost 掃描 (19:10)
2. **更新 crontab** 添加 CatBoost 重訓 (02:00)
3. **測試新任務** 執行一次完整流程驗證

### 本週 (Priority: Medium)

4. **驗證 CatBoost 效果** 運行 2-3 週觀察推薦清單品質
5. **對比兩套系統** 使用 weekly_comparison_report 分析性能
6. **調整超參數** 基於實際回測結果優化 CatBoost 模型

### 本月 (Priority: Low)

7. **添加健康檢查** 監控系統運行狀態
8. **優化特徵工程** 提升模型準確率 (現在 ~25%)
9. **評估模型選擇** 決定是否全面使用 CatBoost 替代 ML Enhanced

---

**重要**: 這個系統現在**不完整且不對稱**。強烈建議立即更新 crontab，使兩套系統並行運行，才能進行公平的實際交易比較。

---

**最後更新**: 2025-11-22
**文檔版本**: 1.0
**系統狀態**: ⚠️ Incomplete (待 crontab 更新)
