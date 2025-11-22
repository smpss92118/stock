# 運維與操作手冊

集中每日/每週排程、手動執行與監控指引。所有命令均假設工作目錄為 `/Users/sony/ml_stock/stock`，並使用 Poetry 建立的虛擬環境 `stock/.venv/`.

## 環境需求
- Python 3.11+（Poetry 管理依賴）
- 主要入口：`main.py`（原始策略）、`ml_enhanced/daily_ml_scanner.py`（ML 過濾）、`ml_enhanced/weekly_retrain.py`（每週訓練）
- 建議建立日誌目錄：`mkdir -p /Users/sony/ml_stock/logs`

## 排程（Crontab 範本）
每天生成兩份報告，週日凌晨重訓模型：
```bash
# 每天 19:00 - 原始策略掃描
0 19 * * * /Users/sony/ml_stock/stock/.venv/bin/python /Users/sony/ml_stock/stock/main.py >> /Users/sony/ml_stock/logs/original_scan.log 2>&1

# 每天 19:05 - ML 增強掃描（確保原始掃描已完成）
5 19 * * * /Users/sony/ml_stock/stock/.venv/bin/python /Users/sony/ml_stock/stock/ml_enhanced/daily_ml_scanner.py >> /Users/sony/ml_stock/logs/ml_scanner.log 2>&1

# 每週日 02:00 - 重新訓練 ML 模型
0 2 * * 0 /Users/sony/ml_stock/stock/.venv/bin/python /Users/sony/ml_stock/stock/ml_enhanced/weekly_retrain.py >> /Users/sony/ml_stock/logs/ml_retrain.log 2>&1
```
> 使用絕對路徑的 Python 以避免系統環境差異。

## 手動執行
```bash
# 原始策略每日掃描
stock/.venv/bin/python main.py

# ML 增強掃描
stock/.venv/bin/python ml_enhanced/daily_ml_scanner.py

# 每週模型再訓練（如需強制重訓）
stock/.venv/bin/python ml_enhanced/weekly_retrain.py
```

## 每日輸出位置
- 原始策略報告：`daily_tracking_stock/YYYY-MM-DD/daily_summary.md`
- ML 增強報告：`ml_enhanced/daily_reports/YYYY-MM-DD/ml_daily_summary.md`（含對應 CSV）
- 歷史/回測報告：`data/processed/`、`docs/backtest_report_v2.md`（屬於數據輸出，未在本次重構中調整）

## 監控與故障排除
- 檢查排程是否寫入：`crontab -l`
- 觀察執行日誌：
  - 原始掃描：`tail -f /Users/sony/ml_stock/logs/original_scan.log`
  - ML 掃描：`tail -f /Users/sony/ml_stock/logs/ml_scanner.log`
  - ML 重訓：`tail -f /Users/sony/ml_stock/logs/ml_retrain.log`
- 常見問題：
  - **Crontab 未執行**：確認 Python 路徑正確，或檢查系統郵件/`/var/log/system.log`。
  - **模組找不到**：必要時設置 `export PYTHONPATH=/Users/sony/ml_stock:$PYTHONPATH`。
  - **權限問題**：確保腳本可執行（`chmod +x` 對應腳本）。

更多架構與流程說明見 `docs/system_overview.md`，ML 詳解見 `docs/ml/overview.md` 與 `docs/ml/system_logic.md`。
