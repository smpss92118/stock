"""
P2: 損失函數和樣本權重設計

核心邏輯:
1. compute_sample_weights() - 基於 score 幅度和標籤計算樣本權重
2. verify_sample_weights() - 驗證權重分佈是否合理
3. weight_analysis() - 詳細的權重統計分析

設計原理:
- 層次 1: |score| 幅度權重 (高效率交易 > 低效率交易)
- 層次 2: 標籤權重 (A > B > C ≥ D)
- 層次 3: 類頻率補償 (稀有類權重提升)
- 標準化: 使得 mean(weights) = 1.0
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple


def compute_sample_weights(
    df_train: pd.DataFrame,
    score_col: str = 'score',
    label_col: str = 'label_int',
    score_weight_scale: float = 2.0,
    label_weights: Dict[int, float] = None,
    class_freq_power: float = 0.5,
    verbose: bool = True,
) -> np.ndarray:
    """
    計算樣本權重 (P2 核心)

    多層設計:
    1. Score 幅度層: sigmoid(|score| × scale) → [0.5, 1.0)
    2. 標籤層: A > B > C ≥ D
    3. 類頻率補償: 稀有類提權，常見類降權
    4. 標準化: mean = 1.0

    Args:
        df_train: 訓練數據 DataFrame
        score_col: score 欄位名稱
        label_col: label 欄位名稱 (應為 0-3 的整數)
        score_weight_scale: sigmoid 的 scale 參數 (預設 2.0)
        label_weights: 標籤權重字典 {0: 1.0, 1: 1.0, 2: 1.5, 3: 2.0}
        class_freq_power: 類頻率補償的冪次 (預設 0.5 = 平方根)
        verbose: 是否打印詳細統計

    Returns:
        np.ndarray of shape (n_samples,) with weights

    Example:
        >>> weights = compute_sample_weights(
        ...     df_train,
        ...     score_col='score',
        ...     label_col='label_int'
        ... )
        >>> print(f"Mean: {weights.mean():.4f}, Std: {weights.std():.4f}")
    """

    if label_weights is None:
        label_weights = {0: 1.0, 1: 1.0, 2: 1.5, 3: 2.0}

    n_samples = len(df_train)

    # ========== 層次 1: Score 幅度權重 ==========
    # sigmoid(|score| * scale) 映射到 [0.5, 1.0)
    # 原因: |score| 大的交易更值得學習，regardless 盈虧
    score_magnitude = np.abs(df_train[score_col].values)
    score_weights = 1.0 / (1.0 + np.exp(-score_magnitude * score_weight_scale))

    if verbose:
        print(f"✓ Score weights: min={score_weights.min():.4f}, "
              f"max={score_weights.max():.4f}, mean={score_weights.mean():.4f}")

    # ========== 層次 2: 標籤權重 ==========
    # A (3) > B (2) > C (1) ≥ D (0)
    # 原因: 稀有的 A 類更重要，常見的 D 類權重正常
    labels = df_train[label_col].values
    label_weight_array = np.array([label_weights.get(l, 1.0) for l in labels])

    if verbose:
        print(f"✓ Label weights: {label_weights}")

    # ========== 結合層次 1 和 2 ==========
    combined_weights = score_weights * label_weight_array

    if verbose:
        print(f"✓ Combined weights: min={combined_weights.min():.4f}, "
              f"max={combined_weights.max():.4f}, mean={combined_weights.mean():.4f}")

    # ========== 層次 3: 類頻率補償 ==========
    # 頻繁類 (C/D) 的權重下調，稀有類 (A/B) 的權重上調
    # 使用 sqrt 避免過度補償
    for label in [0, 1, 2, 3]:
        mask = labels == label
        count = mask.sum()
        if count > 0:
            # 除以 sqrt(count) → 頻繁類降權，稀有類提權
            combined_weights[mask] /= np.power(count, class_freq_power)

    if verbose:
        print(f"✓ After frequency compensation: min={combined_weights.min():.4f}, "
              f"max={combined_weights.max():.4f}, mean={combined_weights.mean():.4f}")

    # ========== 標準化: mean = 1.0 ==========
    final_weights = combined_weights / combined_weights.mean()

    if verbose:
        print(f"✓ Final normalized weights: min={final_weights.min():.4f}, "
              f"max={final_weights.max():.4f}, mean={final_weights.mean():.4f}, "
              f"std={final_weights.std():.4f}")

    return final_weights


def verify_sample_weights(
    weights: np.ndarray,
    df_train: pd.DataFrame,
    label_col: str = 'label_int',
    verbose: bool = True,
) -> Dict:
    """
    驗證樣本權重的分佈是否合理

    檢查項目:
    1. 權重統計 (mean ≈ 1.0, std reasonable)
    2. 按標籤的權重分佈
    3. 極端權重檢測 (是否有異常值)
    4. 權重和檢查

    Args:
        weights: 樣本權重陣列
        df_train: 訓練數據
        label_col: 標籤欄位名稱
        verbose: 是否打印結果

    Returns:
        dict with verification results:
            - 'is_valid': bool
            - 'weight_stats': dict (統計信息)
            - 'label_weight_stats': dict (按標籤的統計)
            - 'warnings': list (警告訊息)

    Example:
        >>> result = verify_sample_weights(weights, df_train)
        >>> if result['is_valid']:
        ...     print("✅ Weights are valid")
    """

    labels = df_train[label_col].values
    warnings = []

    # ===== 權重統計 =====
    weight_stats = {
        'count': len(weights),
        'mean': weights.mean(),
        'std': weights.std(),
        'min': weights.min(),
        'max': weights.max(),
        'median': np.median(weights),
    }

    # 檢查 mean ≈ 1.0
    if not (0.95 <= weight_stats['mean'] <= 1.05):
        warnings.append(f"⚠️  Mean weight {weight_stats['mean']:.4f} 離 1.0 較遠")

    # ===== 按標籤的權重統計 =====
    label_weight_stats = {}
    for label in [0, 1, 2, 3]:
        mask = labels == label
        if mask.sum() > 0:
            label_weights = weights[mask]
            label_weight_stats[label] = {
                'count': mask.sum(),
                'mean': label_weights.mean(),
                'std': label_weights.std(),
                'min': label_weights.min(),
                'max': label_weights.max(),
            }

    # ===== 極端權重檢測 =====
    extreme_high = (weights > weight_stats['mean'] * 5).sum()
    extreme_low = (weights < weight_stats['mean'] * 0.1).sum()

    if extreme_high > 0:
        warnings.append(f"⚠️  偵測到 {extreme_high} 個異常高的權重 (> 5 × mean)")

    if extreme_low > 0:
        warnings.append(f"⚠️  偵測到 {extreme_low} 個異常低的權重 (< 0.1 × mean)")

    # ===== 權重和檢查 =====
    weight_sum = weights.sum()
    expected_sum = len(weights)  # 因為已標準化
    if not (expected_sum * 0.95 <= weight_sum <= expected_sum * 1.05):
        warnings.append(f"⚠️  權重和 {weight_sum:.2f} 偏離預期 {expected_sum}")

    # ===== 驗證結果 =====
    is_valid = len(warnings) == 0

    result = {
        'is_valid': is_valid,
        'weight_stats': weight_stats,
        'label_weight_stats': label_weight_stats,
        'warnings': warnings,
    }

    # ===== 打印結果 =====
    if verbose:
        print("\n" + "=" * 80)
        print("樣本權重驗證結果")
        print("=" * 80)

        print(f"\n【整體統計】")
        print(f"  樣本數: {weight_stats['count']}")
        print(f"  Mean:   {weight_stats['mean']:.4f} (應接近 1.0)")
        print(f"  Std:    {weight_stats['std']:.4f}")
        print(f"  Min:    {weight_stats['min']:.4f}")
        print(f"  Max:    {weight_stats['max']:.4f}")
        print(f"  Median: {weight_stats['median']:.4f}")

        print(f"\n【按標籤統計】")
        label_names = {0: 'D', 1: 'C', 2: 'B', 3: 'A'}
        for label in [0, 1, 2, 3]:
            if label in label_weight_stats:
                stats = label_weight_stats[label]
                print(f"  Label {label_names[label]}: "
                      f"n={stats['count']}, "
                      f"mean={stats['mean']:.4f}, "
                      f"min={stats['min']:.4f}, "
                      f"max={stats['max']:.4f}")

        if warnings:
            print(f"\n【警告】")
            for w in warnings:
                print(f"  {w}")
        else:
            print(f"\n✅ 所有驗證通過！")

        print("=" * 80 + "\n")

    return result


def weight_analysis(
    weights: np.ndarray,
    df_train: pd.DataFrame,
    score_col: str = 'score',
    label_col: str = 'label_int',
) -> Dict:
    """
    進行詳細的權重分析

    分析內容:
    1. 權重與 score 的相關性
    2. 權重的分佈特性 (偏度、峰度)
    3. 樣本權重的 Top-K 分析

    Args:
        weights: 樣本權重陣列
        df_train: 訓練數據
        score_col: score 欄位名稱
        label_col: label 欄位名稱

    Returns:
        dict with analysis results
    """

    from scipy.stats import spearmanr, pearsonr

    analysis = {}

    # ===== 相關性分析 =====
    scores = df_train[score_col].values
    spearman_corr, spearman_pval = spearmanr(weights, scores)
    pearson_corr, pearson_pval = pearsonr(weights, np.abs(scores))

    analysis['correlation'] = {
        'spearman_with_score': spearman_corr,
        'pearson_with_abs_score': pearson_corr,
    }

    # ===== 分佈特性 =====
    from scipy.stats import skew, kurtosis

    analysis['distribution'] = {
        'skewness': skew(weights),
        'kurtosis': kurtosis(weights),
    }

    # ===== Top-K 樣本 =====
    top_k = 10
    top_indices = np.argsort(weights)[-top_k:][::-1]
    bottom_indices = np.argsort(weights)[:top_k]

    analysis['top_weighted_samples'] = {
        'indices': top_indices.tolist(),
        'weights': weights[top_indices].tolist(),
        'scores': scores[top_indices].tolist(),
    }

    analysis['bottom_weighted_samples'] = {
        'indices': bottom_indices.tolist(),
        'weights': weights[bottom_indices].tolist(),
        'scores': scores[bottom_indices].tolist(),
    }

    return analysis


if __name__ == '__main__':
    # 簡單測試
    print("測試 loss_functions...")

    # 創建虛擬數據
    np.random.seed(42)
    n_samples = 1000

    scores = np.random.normal(0.5, 2.0, n_samples)  # 均值 0.5, 標準差 2.0
    labels = np.random.choice([0, 1, 2, 3], n_samples, p=[0.4, 0.35, 0.15, 0.1])

    df_train = pd.DataFrame({
        'score': scores,
        'label_int': labels,
    })

    print(f"\n測試數據:\n  樣本數: {len(df_train)}")
    print(f"  標籤分佈: {dict(zip(*np.unique(labels, return_counts=True)))}")

    # 計算權重
    weights = compute_sample_weights(df_train, verbose=True)

    # 驗證權重
    result = verify_sample_weights(weights, df_train, verbose=True)

    # 權重分析
    analysis = weight_analysis(weights, df_train)
    print(f"\n【權重分析】")
    print(f"  Spearman with score: {analysis['correlation']['spearman_with_score']:.4f}")
    print(f"  Pearson with |score|: {analysis['correlation']['pearson_with_abs_score']:.4f}")
    print(f"  Skewness: {analysis['distribution']['skewness']:.4f}")
    print(f"  Kurtosis: {analysis['distribution']['kurtosis']:.4f}")

    print("\n✅ 所有測試通過！")
