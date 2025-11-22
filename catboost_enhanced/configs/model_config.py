"""
CatBoost 模型的超參數和配置

包含:
1. CatBoost 分類器的超參數
2. 訓練策略設置
3. 驗證策略設置
4. 早停和模型選擇策略
"""

from src.ml.constants import (
    CATBOOST_DEFAULT_PARAMS,
    NUM_CLASSES,
    CLASS_WEIGHTS,
    EMBARGO_PCT,
    CV_N_SPLITS,
)

# ============================================================================
# 基礎 CatBoost 超參數
# ============================================================================

# P0 + P1 + P2 的完整配置
CATBOOST_PARAMS = {
    # === P2: 損失函數和類權重設置 ===
    'loss_function': 'MultiClass',
    'class_weights': CLASS_WEIGHTS,  # [1.0, 1.0, 1.5, 2.0]

    # === 樹參數 ===
    'iterations': 2000,  # 最大迭代次數 (會因 early_stopping 提前停止)
    'learning_rate': 0.05,  # 學習率
    'depth': 6,  # 樹的深度

    # === 正則化參數 ===
    'l2_leaf_reg': 3,  # L2 正則化係數
    'bagging_temperature': 1.0,  # Bagging 溫度
    'random_strength': 1,  # 隨機性強度

    # === 驗證和早停 ===
    'eval_metric': 'MultiClass',  # 評估指標
    'early_stopping_rounds': 100,  # 如果 eval_metric 不改進則停止
    'verbose': 100,  # 每 N 次迭代打印進度

    # === 數據處理 ===
    'auto_class_weights': None,  # 使用 class_weights 而不是自動
    'scale_pos_weight': None,  # 不使用 pos_weight (多分類)

    # === 隨機種子 ===
    'random_seed': 42,
    'use_best_model': True,  # 使用最佳的 eval_set 模型

    # === 其他 ===
    'allow_writing_files': False,  # 不寫入臨時檔案
    'metric_period': 10,  # 評估指標的週期
}

# ============================================================================
# P1: PurgedGroupKFold 配置
# ============================================================================

CV_CONFIG = {
    'n_splits': CV_N_SPLITS,  # 5 折交叉驗證
    'embargo_pct': EMBARGO_PCT,  # 0.05 (5% of total dates)
    'embargo_days': 20,  # 絕對值，用於驗證

    # Walk-forward 相關 (用於驗證數據泄漏)
    'validate_embargo': True,
    'verbose_fold_info': True,  # 打印每個 fold 的日期範圍
}

# ============================================================================
# P2: 樣本權重配置
# ============================================================================

SAMPLE_WEIGHT_CONFIG = {
    # Score 幅度權重的 sigmoid 參數
    'score_weight_scale': 2.0,

    # 類別權重係數 (乘以基礎權重)
    'label_weight_multipliers': {
        0: 1.0,   # D
        1: 1.0,   # C
        2: 1.5,   # B
        3: 2.0,   # A
    },

    # 類頻率補償的平方根參數
    'class_freq_compensation_power': 0.5,

    # 驗證選項
    'verify_weights': True,  # 訓練前驗證權重分佈
    'verbose_weight_stats': True,  # 打印詳細的權重統計
}

# ============================================================================
# 特徵工程配置
# ============================================================================

FEATURE_CONFIG = {
    # 類別特徵 (CatBoost 會自動處理，不進行 one-hot encoding)
    'cat_features': ['pattern_type', 'exit_mode', 'ma_trend'],

    # 特徵標準化
    'normalize': False,  # CatBoost 對特徵歸一化不敏感
    'zscore_features': [
        # 來自 prepare_catboost_data.py
        'volume_ratio_ma20', 'volume_ratio_ma50', 'volume_surge', 'volume_trend_5d',
        'momentum_5d', 'momentum_20d', 'price_vs_ma20', 'price_vs_ma50',
        'volatility', 'atr_ratio',
        # 機構流 (在 prepare 階段會 z-score)
    ],

    # 特徵選擇 (暫不使用)
    'feature_selection': False,
}

# ============================================================================
# 訓練策略
# ============================================================================

TRAINING_CONFIG = {
    # 驗證集大小 (僅在不使用 CV 時使用)
    'eval_set_ratio': 0.2,

    # 使用交叉驗證 (推薦)
    'use_cv': True,
    'cv_strategy': 'PurgedGroupKFold',  # 或 'TimeSeriesSplit'

    # 早停耐心
    'early_stopping_rounds': 100,

    # 是否使用 GPU
    'task_type': 'CPU',  # 或 'GPU'

    # 並行處理
    'thread_count': -1,  # -1 = 自動使用所有 CPU
}

# ============================================================================
# 模型評估配置
# ============================================================================

EVALUATION_CONFIG = {
    # 計算的指標
    'metrics': [
        'MultiClass',
        'Accuracy',
        'Precision',
        'Recall',
        'F1',
    ],

    # 二分類轉化 (for 相容性)
    'binary_conversion': 'winner_vs_loser',  # [A,B] vs [C,D]

    # 排序指標 (可選，用於衡量相對排序能力)
    'ranking_metrics': [
        'NDCG:type=exp;denominator=log2;decay_type=exp',
    ],
}

# ============================================================================
# 輸出和日誌配置
# ============================================================================

OUTPUT_CONFIG = {
    # 保存模型
    'save_model': True,
    'save_feature_importance': True,
    'save_cv_metrics': True,

    # 視覺化
    'plot_feature_importance': True,
    'plot_cv_scores': True,
    'plot_sample_weights': True,

    # 報告
    'verbose_report': True,
    'save_detailed_results': True,
}

# ============================================================================
# 助手函數: 取得完整的模型參數字典
# ============================================================================

def get_catboost_params(**kwargs):
    """
    取得 CatBoost 參數，允許覆蓋預設值

    Args:
        **kwargs: 要覆蓋的參數

    Returns:
        完整的參數字典

    Example:
        >>> params = get_catboost_params(iterations=1000, depth=5)
        >>> params['iterations']
        1000
    """
    params = CATBOOST_PARAMS.copy()
    params.update(kwargs)
    return params


def get_training_config(**kwargs):
    """取得訓練配置，允許覆蓋預設值"""
    config = TRAINING_CONFIG.copy()
    config.update(kwargs)
    return config


def get_cv_config(**kwargs):
    """取得交叉驗證配置，允許覆蓋預設值"""
    config = CV_CONFIG.copy()
    config.update(kwargs)
    return config


if __name__ == '__main__':
    # 打印當前配置
    print("=" * 80)
    print("CatBoost Model Configuration")
    print("=" * 80)

    print("\n### 基礎超參數 ###")
    for k, v in CATBOOST_PARAMS.items():
        print(f"  {k}: {v}")

    print("\n### CV 配置 ###")
    for k, v in CV_CONFIG.items():
        print(f"  {k}: {v}")

    print("\n### 樣本權重配置 ###")
    for k, v in SAMPLE_WEIGHT_CONFIG.items():
        print(f"  {k}: {v}")

    print("\n✅ Configuration loaded successfully!")
