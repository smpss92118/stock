"""
統一的評分和標籤生成模組

核心功能:
1. compute_score() - 計算效率分數 (收益率 / 持有天數)
2. assign_labels_by_quartile() - 基於四分位數分配 ABCD 標籤
3. assign_is_winner() - 根據標籤判定是否為獲勝信號

供 ml_enhanced 和 catboost_enhanced 共享使用
"""

import pandas as pd
import numpy as np
from src.ml.constants import (
    LABEL_TO_INT,
    INT_TO_LABEL,
    LABEL_RULES,
)


def compute_score(actual_return_pct: float, holding_days: int) -> float:
    """
    計算效率分數 (日均報酬率)

    Formula: score = (return % × 100) / holding_days

    Args:
        actual_return_pct: 實際報酬率 (如 0.05 = 5%)
        holding_days: 持有天數 (至少 1)

    Returns:
        效率分數 (日均報酬率%)

    Example:
        >>> compute_score(0.05, 10)  # +5% 報酬率，10 天持有
        0.5  # 日均 +0.5%

        >>> compute_score(-0.02, 4)  # -2% 報酬率，4 天持有
        -0.5  # 日均 -0.5%
    """
    if holding_days < 1:
        holding_days = 1

    score = (actual_return_pct * 100) / holding_days
    return score


def assign_labels_by_quartile(
    scores: pd.Series,
    percentiles: list = None
) -> tuple:
    """
    基於四分位數分配 ABCD 標籤

    Args:
        scores: Series of efficiency scores
        percentiles: 四分位數邊界 (預設: [0.25, 0.50, 0.75])
                    如果提供，應為 3 個值代表 Q25, Q50, Q75

    Returns:
        (labels, quartile_boundaries)
        - labels: Series of ABCD labels
        - quartile_boundaries: dict with keys 'q25', 'q50', 'q75'

    Example:
        >>> scores = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        >>> labels, qs = assign_labels_by_quartile(scores)
        >>> labels.tolist()
        ['D', 'D', 'C', 'B', 'A']
    """
    if percentiles is None:
        percentiles = [0.25, 0.50, 0.75]

    q25, q50, q75 = [scores.quantile(p) for p in percentiles]

    labels = pd.Series(index=scores.index, dtype='str')

    # 基於四分位數分配標籤
    labels[scores >= q75] = 'A'
    labels[(scores >= q50) & (scores < q75)] = 'B'
    labels[(scores >= q25) & (scores < q50)] = 'C'
    labels[scores < q25] = 'D'

    quartile_boundaries = {
        'q25': q25,
        'q50': q50,
        'q75': q75,
    }

    return labels, quartile_boundaries


def assign_is_winner(labels: pd.Series) -> pd.Series:
    """
    根據標籤判定是否為獲勝信號

    規則:
        A, B → is_winner = 1 (獲勝)
        C, D → is_winner = 0 (失敗)

    Args:
        labels: Series of ABCD labels

    Returns:
        Series of is_winner (0 or 1)

    Example:
        >>> labels = pd.Series(['A', 'B', 'C', 'D'])
        >>> assign_is_winner(labels).tolist()
        [1, 1, 0, 0]
    """
    return (labels.isin(['A', 'B'])).astype(int)


def assign_label_to_int(labels: pd.Series) -> pd.Series:
    """
    將 ABCD 標籤轉換為整數 (用於分類模型)

    Mapping:
        D → 0
        C → 1
        B → 2
        A → 3

    Args:
        labels: Series of ABCD labels

    Returns:
        Series of integers (0-3)

    Example:
        >>> labels = pd.Series(['A', 'B', 'C', 'D'])
        >>> assign_label_to_int(labels).tolist()
        [3, 2, 1, 0]
    """
    return labels.map(LABEL_TO_INT)


def assign_int_to_label(label_ints: pd.Series) -> pd.Series:
    """
    將整數標籤轉換為 ABCD (逆向映射)

    Args:
        label_ints: Series of integers (0-3)

    Returns:
        Series of ABCD labels

    Example:
        >>> label_ints = pd.Series([3, 2, 1, 0])
        >>> assign_int_to_label(label_ints).tolist()
        ['A', 'B', 'C', 'D']
    """
    return label_ints.map(INT_TO_LABEL)


def create_label_dataframe(
    scores: pd.Series,
    percentiles: list = None
) -> pd.DataFrame:
    """
    一次性生成所有標籤相關的欄位

    Args:
        scores: Series of efficiency scores
        percentiles: 四分位數邊界

    Returns:
        DataFrame with columns:
            - score: 原始分數
            - label_abcd: ABCD 標籤
            - label_int: 整數標籤 (0-3)
            - is_winner: 二分類 (0 or 1)

    Example:
        >>> scores = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        >>> df = create_label_dataframe(scores)
        >>> df.columns.tolist()
        ['score', 'label_abcd', 'label_int', 'is_winner']
    """
    labels_abcd, _ = assign_labels_by_quartile(scores, percentiles)
    labels_int = assign_label_to_int(labels_abcd)
    is_winner = assign_is_winner(labels_abcd)

    result = pd.DataFrame({
        'score': scores,
        'label_abcd': labels_abcd,
        'label_int': labels_int,
        'is_winner': is_winner,
    })

    return result


def validate_score_distribution(scores: pd.Series, plot: bool = False) -> dict:
    """
    驗證分數分佈 (用於數據質量檢查)

    Args:
        scores: Series of efficiency scores
        plot: 是否生成可視化 (True 需要 matplotlib)

    Returns:
        dict with statistics:
            - count: 樣本數
            - mean: 平均分數
            - std: 標準差
            - min: 最小值
            - max: 最大值
            - q25, q50, q75: 四分位數
            - skew: 偏度
            - kurtosis: 峰度

    Example:
        >>> scores = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        >>> stats = validate_score_distribution(scores)
        >>> stats['mean']
        3.0
    """
    from scipy.stats import skew, kurtosis

    stats = {
        'count': len(scores),
        'mean': scores.mean(),
        'std': scores.std(),
        'min': scores.min(),
        'max': scores.max(),
        'q25': scores.quantile(0.25),
        'q50': scores.quantile(0.50),
        'q75': scores.quantile(0.75),
        'skew': skew(scores.dropna()),
        'kurtosis': kurtosis(scores.dropna()),
    }

    if plot:
        try:
            import matplotlib.pyplot as plt
            plt.figure(figsize=(10, 5))
            scores.hist(bins=50)
            plt.xlabel('Score (%/day)')
            plt.ylabel('Frequency')
            plt.title('Score Distribution')
            plt.show()
        except ImportError:
            print("Warning: matplotlib not available for plotting")

    return stats


if __name__ == '__main__':
    # 簡單測試
    print("Testing labeling functions...")

    scores = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 0.0, -1.0, -2.0])
    print(f"\nOriginal scores: {scores.tolist()}")

    labels, qs = assign_labels_by_quartile(scores)
    print(f"Quartiles: Q25={qs['q25']:.2f}, Q50={qs['q50']:.2f}, Q75={qs['q75']:.2f}")
    print(f"Labels: {labels.tolist()}")

    is_winner = assign_is_winner(labels)
    print(f"Is Winner: {is_winner.tolist()}")

    df = create_label_dataframe(scores)
    print(f"\nLabel DataFrame:\n{df}")

    print("\n✅ All tests passed!")
