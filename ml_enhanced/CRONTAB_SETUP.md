# ML-Enhanced Trading System - Crontab 設定

## 每日自動掃描設定

### 完整 Crontab 配置 (使用 Poetry 環境)

每天晚上生成**兩份報告**：
1. 原始策略報告 (`stock/daily_tracking_stock/YYYY-MM-DD/`)
2. ML 增強報告 (`stock/ml_enhanced/daily_reports/YYYY-MM-DD/`)

```bash
# 每天晚上 7:00 - 執行原始策略掃描
0 19 * * * /Users/sony/ml_stock/stock/.venv/bin/python /Users/sony/ml_stock/stock/main.py >> /Users/sony/ml_stock/logs/original_scan.log 2>&1

# 每天晚上 7:05 - 執行 ML 增強掃描 (稍後5分鐘，確保數據更新完成)
5 19 * * * /Users/sony/ml_stock/stock/.venv/bin/python /Users/sony/ml_stock/stock/ml_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/ml_scanner.log 2>&1

# 每週日凌晨 2:00 - 重新訓練 ML 模型
0 2 * * 0 /Users/sony/ml_stock/stock/.venv/bin/python /Users/sony/ml_stock/stock/ml_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/ml_retrain.log 2>&1
```

> **注意**: 使用 Poetry 虛擬環境的 Python (`/Users/sony/ml_stock/stock/.venv/bin/python`)，而不是系統 Python。

---

## 每日輸出檔案

### 1. 原始策略報告 (由 main.py 生成)
```
stock/daily_tracking_stock/
└── YYYY-MM-DD/
    └── daily_summary.md    # 原始 HTF/CUP/VCP 訊號
```

### 2. ML 增強報告 (由 daily_ml_scanner.py 生成)
```
stock/ml_enhanced/daily_reports/
└── YYYY-MM-DD/
    ├── ml_daily_summary.md    # ML 過濾後的推薦訊號
    └── ml_signals.csv         # CSV 格式數據
```

**每天查看兩份報告**：
- **原始報告**: 所有策略訊號 (未過濾)
- **ML 報告**: ML 推薦訊號 (ML ≥ 0.4) + 原始訊號對比

---

## 報告內容

### 1. ML 推薦訊號 (ML ≥ 0.4)
- HTF 型態 + ML 分數
- CUP 型態 + ML 分數
- 包含買入價、停損價、當前價、距離%、RS Rating

### 2. 其他原始訊號 (ML < 0.4)
- 僅供參考
- 品質較低

### 3. 交易策略說明
- HTF: Trailing Stop (年化 153-171%)
- CUP: Fixed R=2.0 (年化 171%, Sharpe 2.99)

---

## 使用流程

### 每天晚上 7:05 後

1. **查看原始報告** (所有訊號):
   ```
   stock/daily_tracking_stock/YYYY-MM-DD/daily_summary.md
   ```

2. **查看 ML 報告** (推薦訊號):
   ```
   stock/ml_enhanced/daily_reports/YYYY-MM-DD/ml_daily_summary.md
   ```

3. **對比研究**:
   - 原始報告：看所有策略訊號
   - ML 報告：優先研究 ML ≥ 0.4 的訊號
   - 交叉驗證：在兩份報告都出現的訊號

4. **決策流程**:
   - ✅ **出現在 ML 推薦** → 最優先研究
   - ⚠️ **只在原始報告** → 參考，但品質較低
   - 📊 **檢查 ML 分數** → ≥ 0.4 為推薦標準

### 手動執行（測試用）

```bash
cd /Users/sony/ml_stock

# 使用 Poetry 環境執行
stock/.venv/bin/python stock/ml_enhanced/daily_ml_scanner.py

# 或使用 poetry run (需在 stock 目錄下)
cd stock
poetry run python ml_enhanced/daily_ml_scanner.py
```

---

## Crontab 安裝步驟

```bash
# 1. 創建 log 目錄
mkdir -p /Users/sony/ml_stock/logs

# 2. 確認 Poetry 虛擬環境存在
ls -la /Users/sony/ml_stock/stock/.venv/bin/python

# 3. 編輯 crontab
crontab -e

# 4. 添加以下三行（使用 Poetry 環境的 Python）
0 19 * * * /Users/sony/ml_stock/stock/.venv/bin/python /Users/sony/ml_stock/stock/main.py >> /Users/sony/ml_stock/logs/original_scan.log 2>&1
5 19 * * * /Users/sony/ml_stock/stock/.venv/bin/python /Users/sony/ml_stock/stock/ml_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/ml_scanner.log 2>&1
0 2 * * 0 /Users/sony/ml_stock/stock/.venv/bin/python /Users/sony/ml_stock/stock/ml_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/ml_retrain.log 2>&1

# 5. 儲存並退出 (:wq 在 vim)

# 6. 驗證 crontab
crontab -l
```

---

## 監控與維護

### 查看執行日誌
```bash
# 原始掃描日誌
tail -f /Users/sony/ml_stock/logs/original_scan.log

# ML 掃描日誌
tail -f /Users/sony/ml_stock/logs/ml_scanner.log

# ML 重新訓練日誌
tail -f /Users/sony/ml_stock/logs/ml_retrain.log
```

### 手動測試
```bash
cd /Users/sony/ml_stock

# 測試原始掃描 (使用 Poetry 環境)
stock/.venv/bin/python stock/main.py

# 測試 ML 掃描
stock/.venv/bin/python stock/ml_enhanced/daily_ml_scanner.py

# 或使用 poetry run (需在 stock 目錄下)
cd stock
poetry run python main.py
poetry run python ml_enhanced/daily_ml_scanner.py
```

### 檢查輸出
```bash
# 原始報告
ls -la stock/daily_tracking_stock/$(date +%Y-%m-%d)/

# ML 報告
ls -la stock/ml_enhanced/daily_reports/$(date +%Y-%m-%d)/
```

---

## 故障排除

### 問題: Crontab 沒執行
- 檢查 Python 路徑: `which python`
- 使用絕對路徑: `/Users/sony/.pyenv/shims/python`
- 檢查 crontab 日誌: `/var/mail/sony` 或 `tail /var/log/system.log`

### 問題: 找不到模組
- 在腳本開頭添加: `export PYTHONPATH=/Users/sony/ml_stock:$PYTHONPATH`

### 問題: 權限問題
```bash
chmod +x stock/ml_enhanced/daily_ml_scanner.py
chmod +x stock/ml_enhanced/run_daily_scanner.sh  # 如果使用方法二
```

---

**設定完成後，每天晚上 7:00 會自動生成 ML 推薦報告！** 🎯
