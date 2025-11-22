# Repository Guidelines
## 通用規則
- 回覆我的語言都要是繁體中文

## Project Structure & Module Organization
- Root workspace: `stock/` (core pipeline), `stock/ml_enhanced/` (ML layer), `stock/src/` (shared libs), `stock/scripts/` (data prep/backtest utilities), `stock/data/` (raw + processed CSVs).  
- Key flows: `scripts/run_historical_analysis.py` → `data/processed/pattern_analysis_result.csv`; `ml_enhanced/scripts/prepare_ml_data.py` → `ml_enhanced/data/ml_features.csv`; `ml_enhanced/scripts/train_models.py` → `ml_enhanced/models/`.
- Shared feature logic lives in `src/ml/features.py`; backtest engine in `scripts/run_backtest.py`.

## Build, Test, and Development Commands
- Refresh pattern detections: `python stock/scripts/run_historical_analysis.py` (writes `pattern_analysis_result.csv` with volume).
- Create ML training data: `python stock/ml_enhanced/scripts/prepare_ml_data.py`.
- Train models: `python stock/ml_enhanced/scripts/train_models.py`.
- Run ML backtest (optional validation): `python stock/ml_enhanced/scripts/run_ml_backtest.py`.
- Daily ML scan (manual): `python stock/ml_enhanced/daily_ml_scanner.py`.

## Coding Style & Naming Conventions
- Python 3.11+; prefer type-aware code paths but repo is mostly dynamically typed.
- Indentation: 4 spaces. Keep lines reasonably short (<120 chars).
- Use descriptive snake_case for variables/functions; UpperCamelCase for classes.
- Logs: use `src.utils.logger.setup_logger` where available; avoid silent failures.
- Data columns: keep consistent lower_snake_case (`volume_ratio_ma20`, `is_htf`, etc.).

## Testing Guidelines
- No formal test suite is present; validate changes by running the data and backtest scripts above.
- When adding calculations, spot-check sample rows in generated CSVs (e.g., via `python -c "import pandas as pd; print(pd.read_csv('stock/ml_enhanced/data/ml_features.csv').head())"`).
- If adding tests, place them under `tests/` with `pytest`-style `test_*.py` filenames and keep them fast and data-light.

## Commit & Pull Request Guidelines
- Commits: use short, imperative messages (e.g., “Add volume features to pattern output”). Group related changes; avoid committing large generated artifacts unless necessary.
- PRs: include a concise description of scope, key commands run (and results), and any data/regression risks. Link related issues/tasks. Add screenshots or sample rows for data/ML changes when helpful.

## Security & Data Handling
- Avoid committing large/proprietary CSVs or model `.pkl` files unless intentionally updating canonical artifacts.
- Treat credentials/keys as secrets; do not hardcode. Use environment variables or config files that are gitignored.

## Agent Tips
- When modifying feature logic, ensure `pattern_analysis_result.csv` retains required columns (notably `volume`) to keep downstream ML scripts from failing.
- Keep edits ASCII-only unless the file already uses other characters. Use `rg` for fast searches. Prefer `apply_patch` for small, targeted changes.
