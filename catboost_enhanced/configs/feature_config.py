"""
特徵配置管理

定義模型訓練和推理所需的完整特徵列表，並提供對齐檢查工具
"""

from src.ml.constants import FEATURE_COLS_24, INSTITUTIONAL_FEATURES

# ============================================================================
# 特徵分類和列表
# ============================================================================

# 模式相關特徵
PATTERN_FEATURES = [
    'buy_price',
    'stop_price',
    'grade_numeric',
    'distance_to_buy_pct',
    'risk_pct',
]

# 技術指標特徵
TECHNICAL_FEATURES = [
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
]

# 機構流特徵 (完整版本，用於擴展的數據)
INSTITUTIONAL_FEATURES_EXTENDED = INSTITUTIONAL_FEATURES

# 類別特徵 (不參與模型計算，但用於特徵交叉)
CATEGORICAL_FEATURES = [
    'pattern_type',    # 模式類型: htf, cup, vcp
    'exit_mode',       # 出場模式: fixed_r2_t20, fixed_r3_t20, trailing_15r
    'ma_trend',        # MA 趨勢: 0 or 1
]

# ============================================================================
# 完整特徵列表
# ============================================================================

# 核心特徵 (24 個) - 用於 ml_enhanced 相容性
FEATURE_COLS_CORE_24 = FEATURE_COLS_24

# 擴展特徵 (包含所有機構流) - 用於 catboost_enhanced
FEATURE_COLS_EXTENDED = (
    PATTERN_FEATURES +
    TECHNICAL_FEATURES +
    INSTITUTIONAL_FEATURES_EXTENDED
)

# 所有特徵 (包含類別特徵)
FEATURE_COLS_ALL = FEATURE_COLS_EXTENDED + CATEGORICAL_FEATURES

# ============================================================================
# 目標變數列表
# ============================================================================

TARGET_COLUMNS = {
    'score': 'float',  # 效率分數
    'label_abcd': 'str',  # ABCD 標籤
    'label_int': 'int',  # 整數標籤 (0-3)
    'is_winner': 'int',  # 二分類 (0 or 1)
    'actual_return': 'float',  # 實際報酬率
    'duration': 'int',  # 持有天數
}

# ============================================================================
# 特徵對齐檢查工具
# ============================================================================

def check_feature_alignment(df_actual, expected_features):
    """
    檢查實際 DataFrame 的特徵是否與預期對齊

    Args:
        df_actual: 實際的 DataFrame
        expected_features: 預期的特徵列表

    Returns:
        dict with keys:
            - 'aligned': bool
            - 'missing': list (在 df_actual 中缺失的特徵)
            - 'extra': list (在 df_actual 中額外的特徵)
            - 'reordered': bool (是否需要重新排序)

    Example:
        >>> result = check_feature_alignment(df, FEATURE_COLS_EXTENDED)
        >>> if not result['aligned']:
        ...     print(f"Missing: {result['missing']}")
    """
    actual_features = set(df_actual.columns)
    expected_features_set = set(expected_features)

    missing = list(expected_features_set - actual_features)
    extra = list(actual_features - expected_features_set)
    reordered = df_actual.columns.tolist() != expected_features

    aligned = len(missing) == 0 and len(extra) == 0 and not reordered

    return {
        'aligned': aligned,
        'missing': missing,
        'extra': extra,
        'reordered': reordered,
    }


def align_features(df, target_features, fill_missing=True):
    """
    將 DataFrame 的特徵對齐到目標列表

    Args:
        df: 原始 DataFrame
        target_features: 目標特徵列表
        fill_missing: 是否填補缺失特徵 (預設值為 0)

    Returns:
        對齐後的 DataFrame (僅包含目標特徵，按目標順序排列)

    Example:
        >>> df_aligned = align_features(df, FEATURE_COLS_EXTENDED)
    """
    missing_features = set(target_features) - set(df.columns)

    # 補齐缺失特徵
    if missing_features and fill_missing:
        for col in missing_features:
            df[col] = 0

    # 選擇並重新排序
    df_aligned = df[target_features].copy()

    return df_aligned


def get_feature_info(features):
    """
    取得特徵的元訊息

    Args:
        features: 特徵列表

    Returns:
        dict with:
            - 'total_count': 特徵總數
            - 'by_category': 按類別統計
            - 'feature_list': 完整的特徵列表

    Example:
        >>> info = get_feature_info(FEATURE_COLS_EXTENDED)
        >>> print(f"Total: {info['total_count']}")
        >>> print(f"By category: {info['by_category']}")
    """
    info = {
        'total_count': len(features),
        'by_category': {
            'pattern': len([f for f in features if f in PATTERN_FEATURES]),
            'technical': len([f for f in features if f in TECHNICAL_FEATURES]),
            'institutional': len([f for f in features if f in INSTITUTIONAL_FEATURES_EXTENDED]),
            'categorical': len([f for f in features if f in CATEGORICAL_FEATURES]),
        },
        'feature_list': features,
    }
    return info


# ============================================================================
# 特徵數據類型定義 (用於 pandas 讀取)
# ============================================================================

DTYPE_SPEC = {
    # 特徵
    'buy_price': 'float32',
    'stop_price': 'float32',
    'grade_numeric': 'float32',
    'distance_to_buy_pct': 'float32',
    'risk_pct': 'float32',

    # 技術指標
    'volume_ratio_ma20': 'float32',
    'volume_ratio_ma50': 'float32',
    'volume_surge': 'float32',
    'volume_trend_5d': 'float32',
    'momentum_5d': 'float32',
    'momentum_20d': 'float32',
    'price_vs_ma20': 'float32',
    'price_vs_ma50': 'float32',
    'rsi_14': 'float32',
    'rsi_divergence': 'float32',
    'market_trend': 'float32',
    'market_volatility': 'float32',
    'ma_trend': 'int8',
    'volatility': 'float32',
    'atr_ratio': 'float32',

    # 機構流
    'foreign_net_lag1': 'float32',
    'investment_net_lag1': 'float32',
    'dealer_net_lag1': 'float32',
    'foreign_net_sum_3d': 'float32',
    'foreign_net_sum_5d': 'float32',
    'foreign_net_sum_10d': 'float32',
    'foreign_net_sum_20d': 'float32',
    'investment_net_sum_3d': 'float32',
    'investment_net_sum_5d': 'float32',
    'investment_net_sum_10d': 'float32',
    'investment_net_sum_20d': 'float32',
    'dealer_net_sum_3d': 'float32',
    'dealer_net_sum_5d': 'float32',
    'dealer_net_sum_10d': 'float32',
    'dealer_net_sum_20d': 'float32',

    # 類別特徵
    'pattern_type': 'str',
    'exit_mode': 'str',

    # 目標變數
    'score': 'float32',
    'label_abcd': 'str',
    'label_int': 'int8',
    'is_winner': 'int8',
    'actual_return': 'float32',
    'duration': 'int16',
}

# ============================================================================
# 特徵標準化配置
# ============================================================================

# 哪些特徵需要進行 z-score 標準化
FEATURES_NEED_ZSCORE = [
    # 成交量
    'volume_ratio_ma20',
    'volume_ratio_ma50',
    'volume_surge',
    'volume_trend_5d',

    # 動量
    'momentum_5d',
    'momentum_20d',
    'price_vs_ma20',
    'price_vs_ma50',

    # 波動性
    'volatility',
    'atr_ratio',

    # 機構流 (全部)
] + INSTITUTIONAL_FEATURES_EXTENDED

if __name__ == '__main__':
    # 打印特徵配置
    print("=" * 80)
    print("Feature Configuration")
    print("=" * 80)

    print(f"\n核心特徵 (24): {len(FEATURE_COLS_CORE_24)}")
    print(f"  {FEATURE_COLS_CORE_24[:5]}...")

    print(f"\n擴展特徵 (含機構流): {len(FEATURE_COLS_EXTENDED)}")

    info = get_feature_info(FEATURE_COLS_EXTENDED)
    print(f"\n特徵分類統計:")
    for cat, count in info['by_category'].items():
        print(f"  {cat}: {count}")

    print(f"\n類別特徵: {CATEGORICAL_FEATURES}")

    print("\n✅ Feature configuration loaded successfully!")
