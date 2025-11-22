# Crontab 更新指南

## 🔴 系統現狀分析

### 你的現有 Crontab

```bash
# 每天晚上 7:00 - 執行原始策略掃描
0 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python main.py >> /Users/sony/ml_stock/logs/original_scan.log 2>&1

# 每天晚上 7:05 - 執行 ML 增強掃描
5 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/ml_scanner.log 2>&1

# 每週日凌晨 2:00 - 重新訓練 ML 模型
0 2 * * 0 cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/ml_retrain.log 2>&1
```

### ❌ 問題清單

| # | 問題 | 嚴重性 | 影響 |
|---|------|--------|------|
| 1 | **CatBoost 日常掃描完全缺失** | 🔴 Critical | CatBoost 模型訓練但從不預測，無法驗證效果 |
| 2 | **CatBoost 週期重訓未執行** | 🔴 Critical | 無法並行比較兩套系統性能 |
| 3 | 日誌名稱不一致 | 🟡 Minor | 難以區分 ml_enhanced 和 catboost 的日誌 |
| 4 | 缺少錯誤通知 | 🟡 Medium | 任務失敗無法及時發現 |
| 5 | 無依賴關係檢查 | 🟡 Medium | 高風險執行順序不確定 |

---

## ✅ 正確的 Crontab 配置

### 推薦方案

```bash
# ════════════════════════════════════════════════════════════════════════════
# 每日流程 (19:00 - 19:20)
# ════════════════════════════════════════════════════════════════════════════

# [1] 19:00 - 執行原始策略掃描 (市場收盤後)
0 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python main.py >> /Users/sony/ml_stock/logs/original_scan.log 2>&1

# [2] 19:05 - 執行 ML Enhanced 掃描 (等待原始策略完成)
5 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/ml_enhanced_scanner.log 2>&1

# [3] 19:10 - 執行 CatBoost Enhanced 掃描 (新增 ⭐)
10 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python catboost_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/catboost_scanner.log 2>&1


# ════════════════════════════════════════════════════════════════════════════
# 每週流程 (週日 01:00 - 03:00)
# ════════════════════════════════════════════════════════════════════════════

# [4] 02:00 - ML Enhanced 週期重訓 (並行)
0 2 * * 0 cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/ml_enhanced_retrain.log 2>&1

# [5] 02:00 - CatBoost Enhanced 週期重訓 (新增 ⭐，並行執行)
0 2 * * 0 cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python catboost_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/catboost_retrain.log 2>&1
```

---

## 📝 變更對比

### 刪除 (OLD)

```diff
- 5 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/ml_scanner.log 2>&1
- 0 2 * * 0 cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/ml_retrain.log 2>&1
```

### 添加 (NEW)

```diff
+ 5 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/ml_enhanced_scanner.log 2>&1
+ 10 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python catboost_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/catboost_scanner.log 2>&1
+ 0 2 * * 0 cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/ml_enhanced_retrain.log 2>&1
+ 0 2 * * 0 cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python catboost_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/catboost_retrain.log 2>&1
```

---

## 🔧 更新步驟

### Step 1: 備份現有設置

```bash
crontab -l > ~/crontab_backup_$(date +%Y%m%d).txt
echo "✅ Backup saved to ~/crontab_backup_$(date +%Y%m%d).txt"
```

### Step 2: 編輯 Crontab

```bash
crontab -e
```

**編輯器會打開，按照以下步驟:**

1. **找到這三行並檢查:**
   ```
   0 19 * * * cd /Users/sony/ml_stock/stock && ...main.py...
   5 19 * * * cd /Users/sony/ml_stock/stock && ...ml_enhanced/daily_ml_scanner.py...
   0 2 * * 0 cd /Users/sony/ml_stock/stock && ...ml_enhanced/weekly_retrain.py...
   ```

2. **修改第二行** (19:05 ML Enhanced):
   ```
   舊: ...ml_scanner.log...
   新: ...ml_enhanced_scanner.log...
   ```

3. **在第二行下面添加新行** (19:10 CatBoost):
   ```
   10 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python catboost_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/catboost_scanner.log 2>&1
   ```

4. **修改第三行** (02:00 ML Enhanced):
   ```
   舊: ...ml_retrain.log...
   新: ...ml_enhanced_retrain.log...
   ```

5. **在第三行下面添加新行** (02:00 CatBoost):
   ```
   0 2 * * 0 cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python catboost_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/catboost_retrain.log 2>&1
   ```

6. **保存並退出**
   - Vim: `:wq` 然後 Enter
   - Nano: Ctrl+X → Y → Enter

### Step 3: 驗證

```bash
# 列出所有 crontab 任務
crontab -l

# 應該看到 5 行任務
```

**預期輸出:**
```
0 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python main.py >> /Users/sony/ml_stock/logs/original_scan.log 2>&1
5 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/ml_enhanced_scanner.log 2>&1
10 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python catboost_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/catboost_scanner.log 2>&1
0 2 * * 0 cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/ml_enhanced_retrain.log 2>&1
0 2 * * 0 cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python catboost_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/catboost_retrain.log 2>&1
```

### Step 4: 測試新任務

```bash
# 手動執行 CatBoost 掃描測試
cd /Users/sony/ml_stock/stock
/Users/sony/.local/bin/poetry run python catboost_enhanced/daily_ml_scanner.py

# 檢查日誌
tail -50 /Users/sony/ml_stock/logs/catboost_scanner.log
```

---

## 📊 時序圖

### 每日流程

```
19:00
├─ [1] 原始策略掃描 (main.py) ............ 5分鐘 ────┐
│                                                    │
19:05                                                │
├─ [2] ML Enhanced 掃描 (ml_enhanced) ... 3分鐘 ───┐│
│                                                  ││
19:08                                              ││
├─ [3] CatBoost 掃描 (catboost) ........ 2分鐘 ───┤│
│                                                  ││
19:10 ✅ 所有推薦清單完成                           ││
                                                   │└─ 順序執行時間間隔: 5分鐘
                                                   └── 總耗時: ~10 分鐘
```

### 週日流程

```
02:00
├─ [4] ML Enhanced 重訓 ..................... 15分鐘  ┐
├─ [5] CatBoost 重訓 ....................... 20分鐘  ├─ 並行執行
│  ├─ prepare_catboost_data.py        5分鐘
│  ├─ train.py (P0+P1+P2)            10分鐘
│  ├─ run_catboost_backtest.py         5分鐘
│  └─ 自動對比分析                     5分鐘          │
│                                                   ┘
02:20 ✅ 兩套系統重訓完成
│   週報告: weekly_comparison_report.md
│   對比數據: comparison_data.json
│
02:50 ✅ 所有操作完成
```

---

## 🚨 常見問題

### Q: 我應該立即更新嗎?

**答: 是的，強烈建議。**

**原因:**
- 現在 CatBoost 模型訓練但從不預測，**無法驗證其效果**
- 兩套系統不對稱，無法進行公平的性能對比
- 無法衡量 P0+P1+P2 的改進是否值得

### Q: 更新會影響現有的 ML Enhanced 系統嗎?

**答: 否，完全不會。**

- ML Enhanced 的三個任務完全保留，只是日誌文件名改了
- 日誌改名是為了方便區分 (ml_enhanced_scanner vs catboost_scanner)
- 功能完全相同

### Q: 如果 CatBoost 掃描失敗會怎樣?

**答: 不會影響其他任務。**

- 19:10 的 CatBoost 掃描失敗不會阻止其他任務執行
- 日誌會記錄錯誤信息，方便診斷
- 建議定期檢查日誌文件

### Q: 週日重訓時，兩套系統並行會不會互相干擾?

**答: 不會。**

- 它們各自有獨立的數據、模型、結果目錄
- 並行執行節省時間 (20分鐘 vs 30分鐘)
- 都安全完成後再生成對比報告

### Q: 我可以只運行 CatBoost 而不運行 ML Enhanced 嗎?

**答: 可以，但不建議。**

**不建議的原因:**
- 失去了對 ML Enhanced 已驗證性能的參考點
- 新系統 (CatBoost) 的效果需要與舊系統對比才有意義
- 萬一新系統出問題，沒有 fallback

**如果要這樣做:**
- 刪除 [4] 和 [5] 中的一個
- 但建議至少運行 2-4 週看看效果再做決定

---

## 📋 驗證清單

### 更新前

- [ ] 備份現有 crontab: `crontab -l > ~/crontab_backup.txt`
- [ ] 檢查日誌目錄是否存在: `ls -la /Users/sony/ml_stock/logs/`
- [ ] 測試 CatBoost 掃描能否手動執行
- [ ] 檢查 catboost_enhanced/daily_ml_scanner.py 是否存在且可執行

### 更新後立即

- [ ] 驗證 crontab 已保存: `crontab -l | grep catboost`
- [ ] 檢查新增了 2 行 (CatBoost 掃描 + CatBoost 重訓)
- [ ] 檢查日誌文件名已更新 (ml_enhanced_scanner, catboost_scanner, ml_enhanced_retrain, catboost_retrain)

### 運行前 (本週)

- [ ] 手動測試: `poetry run python catboost_enhanced/daily_ml_scanner.py`
- [ ] 驗證日誌輸出: `tail /Users/sony/ml_stock/logs/catboost_scanner.log`
- [ ] 檢查推薦清單生成: `ls catboost_enhanced/results/daily_scan_*.csv`

### 週日驗證 (下個週日)

- [ ] 檢查 ml_enhanced_retrain.log
- [ ] 檢查 catboost_retrain.log
- [ ] 驗證週報告生成: `cat catboost_enhanced/results/weekly_comparison_report.md`
- [ ] 檢查對比數據: `cat catboost_enhanced/results/comparison_data.json`

---

## ⚡ 快速更新 (一行命令)

如果你想要一個更快的方式，可以直接編輯文件:

```bash
# 備份
crontab -l > ~/crontab_backup_$(date +%Y%m%d).txt

# 使用 cat 建立新的 crontab 內容
cat > /tmp/new_crontab.txt << 'EOF'
# 每天晚上 7:00 - 執行原始策略掃描
0 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python main.py >> /Users/sony/ml_stock/logs/original_scan.log 2>&1

# 每天晚上 7:05 - 執行 ML 增強掃描
5 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/ml_enhanced_scanner.log 2>&1

# 每天晚上 7:10 - 執行 CatBoost 增強掃描 (新增)
10 19 * * * cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python catboost_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/catboost_scanner.log 2>&1

# 每週日凌晨 2:00 - 重新訓練 ML Enhanced 模型
0 2 * * 0 cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python ml_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/ml_enhanced_retrain.log 2>&1

# 每週日凌晨 2:00 - 重新訓練 CatBoost 模型 (新增)
0 2 * * 0 cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python catboost_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/catboost_retrain.log 2>&1
EOF

# 應用新的 crontab
crontab /tmp/new_crontab.txt

# 驗證
echo "✅ Updated! Verify with:"
crontab -l
```

---

## 📞 如果出問題

### 恢復到備份

```bash
# 列出所有備份
ls -la ~/ | grep crontab_backup

# 恢復到最新備份
crontab ~/crontab_backup_20251122.txt

# 驗證
crontab -l
```

### 檢查任務是否執行

```bash
# 檢查 macOS cron 日誌
log stream --predicate 'process == "cron"' --level debug

# 或者檢查系統日誌
sudo log stream --predicate 'process == "cron"'
```

### 檢查 Poetry 環境

```bash
# 確保 poetry 命令可用
/Users/sony/.local/bin/poetry --version

# 確保在正確的目錄
cd /Users/sony/ml_stock/stock && /Users/sony/.local/bin/poetry run python -c "print('OK')"
```

---

## 📌 總結

| 變更 | 內容 | 優先級 |
|------|------|--------|
| 添加日常掃描 | 19:10 CatBoost 掃描 | 🔴 Critical |
| 添加週期重訓 | 02:00 CatBoost 重訓 | 🔴 Critical |
| 改進日誌名稱 | 區分 ml_enhanced 和 catboost | 🟢 Nice-to-have |
| 添加通知機制 | 錯誤郵件通知 | 🟡 Future |

**立即行動的變更**: 前 2 項
**建議本週完成**: 前 3 項
**未來優化**: 第 4 項

---

**建議行動時機:** 今天或明天
**預期完成時間:** 5 分鐘
**復原時間:** < 1 分鐘 (有備份)

