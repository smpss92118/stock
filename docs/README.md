# 文檔索引 (Documentation Map)

快速導覽專案的核心說明文件。數據產出報告（`data/processed/`, `daily_tracking_stock/`, `ml_enhanced/daily_reports/`, `optimization/results/` 等）保持原位，以下聚焦在常讀的設計/操作文檔。

- **系統架構**: `docs/system_overview.md` — 整體架構、每日/週期流程、模組邏輯。
- **運維操作**: `docs/operations.md` — 環境需求、排程設定、手動執行、檢查輸出與故障排除。
- **策略型態**: `docs/strategy_patterns.md` — CUP/HTF/VCP 偵測條件與交易建議。
- **回測引擎**: `docs/backtest_engine.md` — 進出場與資金管理細節。
- **ML 系統**
  - `docs/ml/overview.md` — ML 增強系統概覽與目錄。
  - `docs/ml/system_logic.md` — 特徵工程、訓練、每日預測流程。
- **策略優化**
  - `docs/optimization/hyperparameter_guide.md` — 可調參數與建議範圍。
  - `docs/optimization/change_log.md` — 每次優化循環的變更紀錄。
- **回測/優化報告 (產出)**: `docs/backtest_report_v2.md`, `docs/optimization_vs_baseline.md`（生成報告，未重構）。 
