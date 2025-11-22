"""
統一的 ML 常數定義

供 ml_enhanced 和 catboost_enhanced 共享使用
"""

# ============================================================================
# 模式類型定義
# ============================================================================

PATTERN_TYPES = ['htf', 'cup', 'vcp']

# Pattern 的中文標籤
PATTERN_NAMES = {
    'htf': '頭肩頂底',
    'cup': '杯柄形',
    'vcp': '股價固結'
}

# ============================================================================
# 出場模式定義
# ============================================================================

EXIT_MODES = ['fixed_r2_t20', 'fixed_r3_t20', 'trailing_15r']

# Exit Mode 的配置參數
EXIT_MODE_CONFIG = {
    'fixed_r2_t20': {
        'type': 'fixed',
        'r_mult': 2.0,
        'time_exit': 20,
        'description': '固定 2R 目標，20 天時間止損'
    },
    'fixed_r3_t20': {
        'type': 'fixed',
        'r_mult': 3.0,
        'time_exit': 20,
        'description': '固定 3R 目標，20 天時間止損'
    },
    'trailing_15r': {
        'type': 'trailing',
        'trigger_r': 1.5,
        'description': '1.5R 觸發後尾隨 MA20 止損'
    }
}

# ============================================================================
# 標籤與評分規則
# ============================================================================

# ABCD 標籤基於四分位數
# score = (return % × 100) / holding_days
LABEL_RULES = {
    'A': {'quantile': (0.75, 1.0), 'is_winner': 1, 'weight': 2.0},
    'B': {'quantile': (0.50, 0.75), 'is_winner': 1, 'weight': 1.5},
    'C': {'quantile': (0.25, 0.50), 'is_winner': 0, 'weight': 1.0},
    'D': {'quantile': (0.00, 0.25), 'is_winner': 0, 'weight': 1.0},
}

# 標籤到數字的映射 (用於分類模型)
LABEL_TO_INT = {
    'D': 0,
    'C': 1,
    'B': 2,
    'A': 3,
}

INT_TO_LABEL = {v: k for k, v in LABEL_TO_INT.items()}

# ============================================================================
# CatBoost 模型配置
# ============================================================================

# 基礎分類數
NUM_CLASSES = 4  # D, C, B, A

# 類別權重 (用於 class_weights 參數)
# 基礎權重: D < C ≤ B < A
CLASS_WEIGHTS = [1.0, 1.0, 1.5, 2.0]  # D, C, B, A

# CatBoost 超參數 (建議值)
CATBOOST_DEFAULT_PARAMS = {
    'loss_function': 'MultiClass',
    'classes_for_smooth_cat': NUM_CLASSES,
    'iterations': 2000,
    'learning_rate': 0.05,
    'depth': 6,
    'l2_leaf_reg': 3,
    'bagging_temperature': 1.0,
    'random_strength': 1,
    'verbose': 100,
    'early_stopping_rounds': 100,
}

# ============================================================================
# 特徵列表
# ============================================================================

# 來自 ml_enhanced 的特徵定義
# (應與 ml_enhanced/scripts/train_models.py line 48-106 對齐)
FEATURE_COLS_24 = [
    # Pattern 相關
    'buy_price',
    'stop_price',
    'grade_numeric',
    'distance_to_buy_pct',
    'risk_pct',

    # 技術指標 (來自 src/ml/features.py)
    'volume_ratio_ma20',
    'volume_ratio_ma50',
    'volume_surge',
    'volume_trend_5d',
    'momentum_5d',
    'momentum_20d',
    'price_vs_ma20',
    'price_vs_ma50',
    'rsi_14',
    'rsi_divergence',
    'market_trend',
    'market_volatility',
    'ma_trend',
    'volatility',
    'atr_ratio',

    # 機構流特徵 (來自 src/data/institutional.py)
    'foreign_net_lag1',
    'investment_net_lag1',
    'dealer_net_lag1',
]

# 機構流擴展特徵 (用於其他來源)
INSTITUTIONAL_FEATURES = [
    'foreign_net_lag1',
    'investment_net_lag1',
    'dealer_net_lag1',
    'foreign_net_sum_3d',
    'foreign_net_sum_5d',
    'foreign_net_sum_10d',
    'foreign_net_sum_20d',
    'investment_net_sum_3d',
    'investment_net_sum_5d',
    'investment_net_sum_10d',
    'investment_net_sum_20d',
    'dealer_net_sum_3d',
    'dealer_net_sum_5d',
    'dealer_net_sum_10d',
    'dealer_net_sum_20d',
]

# ============================================================================
# Embargo 和數據分割參數
# ============================================================================

# Embargo 比例 (占總日期數)
# 假設 20 個交易日的預測窗口，~400 個交易日/年
# embargo_pct ≈ 20 / 400 = 0.05
EMBARGO_PCT = 0.05

# Embargo 天數 (絕對值，用於驗證)
EMBARGO_DAYS = 20

# 交叉驗證折數
CV_N_SPLITS = 5

# Walk-forward 參數 (用於 ml_enhanced 相容性)
TRAIN_WINDOW_MONTHS = 3
TEST_WINDOW_MONTHS = 1

# ============================================================================
# 路徑常數
# ============================================================================

import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))

# ml_enhanced 路徑
ML_ENHANCED_DIR = os.path.join(PROJECT_ROOT, 'ml_enhanced')
ML_DATA_DIR = os.path.join(ML_ENHANCED_DIR, 'data')
ML_MODELS_DIR = os.path.join(ML_ENHANCED_DIR, 'models')

# catboost_enhanced 路徑
CATBOOST_ENHANCED_DIR = os.path.join(PROJECT_ROOT, 'catboost_enhanced')
CATBOOST_DATA_DIR = os.path.join(CATBOOST_ENHANCED_DIR, 'data')
CATBOOST_MODELS_DIR = os.path.join(CATBOOST_ENHANCED_DIR, 'models')
CATBOOST_RESULTS_DIR = os.path.join(CATBOOST_ENHANCED_DIR, 'results')

# 共享數據路徑
DATA_RAW_DIR = os.path.join(PROJECT_ROOT, 'data', 'raw')
DATA_PROCESSED_DIR = os.path.join(PROJECT_ROOT, 'data', 'processed')

# 模式分析結果 (source of truth for patterns)
PATTERN_ANALYSIS_FILE = os.path.join(DATA_PROCESSED_DIR, 'pattern_analysis_result.csv')
