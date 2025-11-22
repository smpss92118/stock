"""
CatBoost Enhanced 特定的常數定義

這個檔案對應 src/ml/constants.py，但額外定義一些 catboost_enhanced 特定的設置
"""

import os
import sys
from pathlib import Path

# 導入共享的常數
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from src.ml.constants import *

# ============================================================================
# CatBoost 特定的路徑常數
# ============================================================================

CATBOOST_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CATBOOST_ENHANCED_ROOT = os.path.dirname(os.path.dirname(CATBOOST_SCRIPT_DIR))

# 訓練數據
CATBOOST_FEATURES_CSV = os.path.join(CATBOOST_DATA_DIR, 'catboost_features.csv')
CATBOOST_FEATURES_EXPANDED_CSV = os.path.join(CATBOOST_DATA_DIR, 'catboost_features_expanded.csv')

# 模型相關
CATBOOST_MODEL_FILE = os.path.join(CATBOOST_MODELS_DIR, 'catboost_global.cbm')
CATBOOST_FEATURE_INFO_FILE = os.path.join(CATBOOST_MODELS_DIR, 'catboost_feature_info.pkl')
CATBOOST_MODEL_METRICS_FILE = os.path.join(CATBOOST_MODELS_DIR, 'model_metrics.json')

# 結果路徑
CATBOOST_RESULTS_BACKTEST_FILE = os.path.join(CATBOOST_RESULTS_DIR, 'backtest_results.csv')
CATBOOST_RESULTS_FEATURE_IMPORTANCE_FILE = os.path.join(CATBOOST_RESULTS_DIR, 'feature_importance.csv')
CATBOOST_RESULTS_CV_METRICS_FILE = os.path.join(CATBOOST_RESULTS_DIR, 'cv_metrics.csv')
CATBOOST_DAILY_REPORT_DIR = os.path.join(CATBOOST_RESULTS_DIR, 'daily_reports')

# ============================================================================
# CatBoost 訓練設置
# ============================================================================

# 數據驗證
VALIDATE_EMBARGO = True  # 驗證 embargo 是否真正生效
VALIDATE_FEATURE_ALIGNMENT = True  # 驗證特徵對齊

# 訓練驗證集分割
TRAIN_TEST_RATIO = 0.8  # 80% 訓練，20% 測試 (如果不使用 CV)

# ============================================================================
# 出場模式的詳細參數
# ============================================================================

# 固定 R 倍數的出場
FIXED_EXIT_PARAMS = {
    'fixed_r2_t20': {
        'r_multiplier': 2.0,
        'max_holding_days': 20,
        'description': '目標 2R，或 20 天時間止損'
    },
    'fixed_r3_t20': {
        'r_multiplier': 3.0,
        'max_holding_days': 20,
        'description': '目標 3R，或 20 天時間止損'
    }
}

# 尾隨止損的出場
TRAILING_EXIT_PARAMS = {
    'trailing_15r': {
        'trigger_r': 1.5,
        'trailing_ma': 20,
        'description': '1.5R 觸發後尾隨 MA20'
    }
}

# ============================================================================
# 特徵相關設置
# ============================================================================

# 需要進行 z-score 標準化的特徵 (避免數據漂移)
# 這些特徵在 apply_group_zscore 中使用
ZSCORE_NORMALIZATION_FEATURES = [
    # 成交量指標
    'volume_ratio_ma20',
    'volume_ratio_ma50',
    'volume_surge',
    'volume_trend_5d',

    # 動量指標
    'momentum_5d',
    'momentum_20d',
    'price_vs_ma20',
    'price_vs_ma50',

    # 波動性指標
    'volatility',
    'atr_ratio',

    # 機構流指標 (全部)
] + INSTITUTIONAL_FEATURES

# 類別特徵 (使用 CatBoost 的原生類別支持，不進行 one-hot encoding)
CATEGORICAL_FEATURES = [
    'pattern_type',
    'exit_mode',
    'ma_trend',
]

# ============================================================================
# 樣本權重計算參數
# ============================================================================

# Score 幅度權重的 sigmoid 參數
# sigmoid(|score| * SCORE_WEIGHT_SCALE)
SCORE_WEIGHT_SCALE = 2.0

# 類別標籤的權重係數
# 基於您的決策：D/C 正常，B 稍高，A 最高
LABEL_WEIGHT_MULTIPLIERS = {
    0: 1.0,   # D
    1: 1.0,   # C
    2: 1.5,   # B
    3: 2.0,   # A
}

# 類頻率補償的平方根參數 (1.0 = 開平方根，0.5 = 四次方根)
CLASS_FREQ_COMPENSATION_POWER = 0.5

# ============================================================================
# 日誌和監控
# ============================================================================

LOG_LEVEL = 'INFO'
LOG_TO_FILE = True

# 在訓練過程中每 N 次迭代打印一次進度
VERBOSE_EVERY_N_ITERATIONS = 100

# ============================================================================
# 回測相關參數
# ============================================================================

# 回測時考慮的信號比例 (如果無法測試所有信號)
BACKTEST_SIGNAL_SAMPLE_RATIO = 1.0  # 1.0 = 使用所有信號

# 回測的 ML 阈值 (用於評估模型的精度-召回權衡)
BACKTEST_ML_THRESHOLDS = [0.3, 0.4, 0.5, 0.6, 0.7]
