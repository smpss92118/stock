#!/usr/bin/env python3
"""
Weekly ML Model Retraining

每週重新訓練 ML 模型，使用最新數據

Usage:
    python stock/ml_enhanced/weekly_retrain.py
    
Output:
    stock/ml_enhanced/models/stock_selector.pkl (updated)
    stock/ml_enhanced/models/position_sizer.pkl (updated)
    stock/ml_enhanced/models/feature_info.pkl (updated)
    
Crontab:
    # 每週日凌晨 2:00 重新訓練
    0 2 * * 0 cd /Users/sony/ml_stock && python stock/ml_enhanced/weekly_retrain.py >> logs/ml_retrain.log 2>&1
"""

import sys
import os

# Add paths
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import training script
from ml_enhanced.scripts.prepare_ml_data import main as prepare_data
from ml_enhanced.scripts.train_models import main as train_models

# Import shared logger
from src.utils.logger import setup_logger

# Setup Logger
logger = setup_logger('weekly_retrain')

def main():
    logger.info("="*80)
    logger.info("Weekly ML Model Retraining")
    logger.info("="*80)
    
    # 1. 準備最新數據
    logger.info("\n>>> Step 1: Preparing ML features with latest data...")
    try:
        prepare_data()
        logger.info("✅ Feature preparation complete")
    except Exception as e:
        logger.error(f"❌ Feature preparation failed: {e}")
        return
    
    # 2. 重新訓練模型
    logger.info("\n>>> Step 2: Retraining ML models...")
    try:
        train_models()
        logger.info("✅ Model training complete")
    except Exception as e:
        logger.error(f"❌ Model training failed: {e}")
        return

    # 3. 執行回測驗證
    logger.info("\n>>> Step 3: Running ML Backtest...")
    try:
        from ml_enhanced.scripts.run_ml_backtest import main as run_backtest
        run_backtest()
        logger.info("✅ Backtest complete")
    except Exception as e:
        logger.error(f"❌ Backtest failed: {e}")
        # Don't return, still show completion message

    
    logger.info("\n" + "="*80)
    logger.info("Weekly Retraining Complete!")
    logger.info("="*80)
    logger.info("\nModels updated (9 models total):")
    logger.info("  CUP Models:")
    logger.info("    - stock/ml_enhanced/models/stock_selector_cup_fixed_r2_t20.pkl")
    logger.info("    - stock/ml_enhanced/models/stock_selector_cup_fixed_r3_t20.pkl")
    logger.info("    - stock/ml_enhanced/models/stock_selector_cup_trailing_15r.pkl")
    logger.info("  HTF Models:")
    logger.info("    - stock/ml_enhanced/models/stock_selector_htf_fixed_r2_t20.pkl")
    logger.info("    - stock/ml_enhanced/models/stock_selector_htf_fixed_r3_t20.pkl")
    logger.info("    - stock/ml_enhanced/models/stock_selector_htf_trailing_15r.pkl")
    logger.info("  VCP Models:")
    logger.info("    - stock/ml_enhanced/models/stock_selector_vcp_fixed_r2_t20.pkl")
    logger.info("    - stock/ml_enhanced/models/stock_selector_vcp_fixed_r3_t20.pkl")
    logger.info("    - stock/ml_enhanced/models/stock_selector_vcp_trailing_15r.pkl")
    logger.info("  Other:")
    logger.info("    - stock/ml_enhanced/models/feature_info.pkl")
    logger.info("\nNext steps:")
    logger.info("  - New models will be used in tomorrow's daily scan")
    logger.info("  - Monitor performance in daily reports")
    logger.info("  - Each pattern now has 3 exit strategies (R=2.0, R=3.0, Trailing)")

if __name__ == "__main__":
    main()
