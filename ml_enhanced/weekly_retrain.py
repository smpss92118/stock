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

def main():
    print("="*80)
    print("Weekly ML Model Retraining")
    print("="*80)
    
    # 1. 準備最新數據
    print("\n>>> Step 1: Preparing ML features with latest data...")
    try:
        prepare_data()
        print("✅ Feature preparation complete")
    except Exception as e:
        print(f"❌ Feature preparation failed: {e}")
        return
    
    # 2. 重新訓練模型
    print("\n>>> Step 2: Retraining ML models...")
    try:
        train_models()
        print("✅ Model training complete")
    except Exception as e:
        print(f"❌ Model training failed: {e}")
        return
    
    print("\n" + "="*80)
    print("Weekly Retraining Complete!")
    print("="*80)
    print("\nModels updated:")
    print("  - stock/ml_enhanced/models/stock_selector.pkl")
    print("  - stock/ml_enhanced/models/position_sizer.pkl")
    print("  - stock/ml_enhanced/models/feature_info.pkl")
    print("\nNext steps:")
    print("  - New models will be used in tomorrow's daily scan")
    print("  - Monitor performance in daily reports")

if __name__ == "__main__":
    main()
