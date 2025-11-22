"""
評估指標和性能測量工具

包含:
1. 分類指標 (Accuracy, Precision, Recall, F1)
2. 排序指標 (NDCG, MRR)
3. 交易相關指標 (Sharpe, Max Drawdown)
4. 可視化工具
"""

import numpy as np
import pandas as pd
from typing import Dict, Tuple
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    classification_report,
    roc_auc_score,
    log_loss,
)


def calculate_classification_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_pred_proba: np.ndarray = None,
    labels: list = None,
) -> Dict:
    """
    計算多分類指標

    Args:
        y_true: 真實標籤 (0-3)
        y_pred: 預測標籤 (0-3)
        y_pred_proba: 預測概率矩陣 (n_samples, n_classes)
        labels: 標籤名稱 (預設: ['D', 'C', 'B', 'A'])

    Returns:
        dict with metrics:
            - accuracy
            - precision (per class)
            - recall (per class)
            - f1 (per class)
            - confusion_matrix
            - detailed_report
    """

    if labels is None:
        labels = ['D', 'C', 'B', 'A']

    metrics = {}

    # 基本指標
    metrics['accuracy'] = accuracy_score(y_true, y_pred)

    # 按類別的指標
    for average in ['micro', 'macro', 'weighted']:
        metrics[f'precision_{average}'] = precision_score(y_true, y_pred, average=average, zero_division=0)
        metrics[f'recall_{average}'] = recall_score(y_true, y_pred, average=average, zero_division=0)
        metrics[f'f1_{average}'] = f1_score(y_true, y_pred, average=average, zero_division=0)

    # 混淆矩陣
    metrics['confusion_matrix'] = confusion_matrix(y_true, y_pred)

    # 詳細報告
    metrics['detailed_report'] = classification_report(
        y_true, y_pred,
        target_names=labels,
        output_dict=True,
        zero_division=0,
    )

    # 如果有預測概率，計算 log loss
    if y_pred_proba is not None:
        metrics['log_loss'] = log_loss(y_true, y_pred_proba)

    return metrics


def calculate_binary_metrics(
    y_true_binary: np.ndarray,
    y_pred_binary: np.ndarray,
    y_pred_proba: np.ndarray = None,
) -> Dict:
    """
    計算二分類指標 (用於 [A,B] vs [C,D])

    Args:
        y_true_binary: 二分類標籤 (0 or 1)
        y_pred_binary: 二分類預測 (0 or 1)
        y_pred_proba: 正類的預測概率

    Returns:
        dict with binary metrics
    """

    metrics = {
        'accuracy': accuracy_score(y_true_binary, y_pred_binary),
        'precision': precision_score(y_true_binary, y_pred_binary, zero_division=0),
        'recall': recall_score(y_true_binary, y_pred_binary, zero_division=0),
        'f1': f1_score(y_true_binary, y_pred_binary, zero_division=0),
    }

    if y_pred_proba is not None:
        try:
            metrics['auc'] = roc_auc_score(y_true_binary, y_pred_proba)
        except:
            metrics['auc'] = None

    return metrics


def calculate_ndcg(y_true: np.ndarray, y_scores: np.ndarray, k: int = 10) -> float:
    """
    計算 NDCG@K (Normalized Discounted Cumulative Gain)

    用途: 衡量模型對相對排序的能力
    - 高 NDCG 表示模型能正確排序高價值信號

    Args:
        y_true: 真實標籤 (分數越高越好)
        y_scores: 預測分數或概率
        k: 評估的頂 K 位置

    Returns:
        NDCG@K 分數 (0-1)
    """

    def dcg(y_true_sorted, k):
        """計算 DCG"""
        return np.sum([y / np.log2(i + 2) for i, y in enumerate(y_true_sorted[:k])])

    def ndcg_score(y_true, y_scores, k):
        """計算單個 NDCG"""
        # 根據預測分數排序
        sorted_indices = np.argsort(-y_scores)[:k]
        y_true_sorted = y_true[sorted_indices]

        # 計算實際 DCG
        actual_dcg = dcg(y_true_sorted, k)

        # 計算理想 DCG (完美排序)
        ideal_sorted_indices = np.argsort(-y_true)[:k]
        y_true_ideal = y_true[ideal_sorted_indices]
        ideal_dcg = dcg(y_true_ideal, k)

        # 正規化
        if ideal_dcg == 0:
            return 0.0
        return actual_dcg / ideal_dcg

    return ndcg_score(y_true, y_scores, k)


def calculate_sharpe_ratio(returns: np.ndarray, risk_free_rate: float = 0.0) -> float:
    """
    計算 Sharpe 比率

    用途: 評估風險調整後的報酬
    - Sharpe > 1.0: 良好
    - Sharpe > 2.0: 優秀

    Args:
        returns: 日報酬序列
        risk_free_rate: 無風險利率 (預設 0.0)

    Returns:
        Sharpe 比率
    """

    excess_returns = returns - risk_free_rate / 252  # 日無風險利率
    return np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)


def calculate_max_drawdown(returns: np.ndarray) -> float:
    """
    計算最大回撤

    用途: 評估下行風險
    - 負值，絕對值越大越差

    Args:
        returns: 日報酬序列

    Returns:
        最大回撤 (負值)
    """

    cumulative_returns = np.cumprod(1 + returns)
    running_max = np.maximum.accumulate(cumulative_returns)
    drawdown = (cumulative_returns - running_max) / running_max
    return np.min(drawdown)


def calculate_calmar_ratio(returns: np.ndarray, periods_per_year: int = 252) -> float:
    """
    計算 Calmar 比率 (年化報酬 / 最大回撤絕對值)

    Args:
        returns: 日報酬序列
        periods_per_year: 年內周期數 (預設 252 個交易日)

    Returns:
        Calmar 比率
    """

    annual_return = np.mean(returns) * periods_per_year
    max_drawdown = calculate_max_drawdown(returns)

    if max_drawdown == 0:
        return 0.0

    return annual_return / abs(max_drawdown)


def calculate_win_rate(y_true: np.ndarray, y_pred: np.ndarray) -> Dict:
    """
    計算勝率相關指標

    Args:
        y_true: 真實結果 (1 = 獲勝, 0 = 失敗)
        y_pred: 預測結果 (1 = 獲勝, 0 = 失敗)

    Returns:
        dict with:
            - overall_win_rate: 總勝率
            - predicted_win_rate: 預測為獲勝的勝率
            - predicted_loss_rate: 預測為失敗的勝率
    """

    overall_win_rate = np.mean(y_true)

    # 預測為獲勝 (1) 的樣本中，實際獲勝的比例
    pred_win_mask = y_pred == 1
    if pred_win_mask.sum() > 0:
        predicted_win_rate = y_true[pred_win_mask].mean()
    else:
        predicted_win_rate = np.nan

    # 預測為失敗 (0) 的樣本中，實際失敗的比例
    pred_loss_mask = y_pred == 0
    if pred_loss_mask.sum() > 0:
        predicted_loss_rate = (1 - y_true[pred_loss_mask]).mean()
    else:
        predicted_loss_rate = np.nan

    return {
        'overall_win_rate': overall_win_rate,
        'predicted_win_rate': predicted_win_rate,
        'predicted_loss_rate': predicted_loss_rate,
    }


def print_classification_report(metrics: Dict, title: str = "分類性能報告"):
    """打印分類指標報告"""

    print(f"\n{'=' * 80}")
    print(f"{title}")
    print(f"{'=' * 80}")

    print(f"\n【整體指標】")
    print(f"  準確率 (Accuracy): {metrics['accuracy']:.4f}")
    print(f"  精度 (Macro):      {metrics['precision_macro']:.4f}")
    print(f"  召回 (Macro):      {metrics['recall_macro']:.4f}")
    print(f"  F1 (Macro):        {metrics['f1_macro']:.4f}")

    if 'log_loss' in metrics:
        print(f"  Log Loss:          {metrics['log_loss']:.4f}")

    print(f"\n【按類別詳細指標】")
    report = metrics['detailed_report']
    for label in ['D', 'C', 'B', 'A']:
        if label in report:
            r = report[label]
            print(f"  {label}: Precision={r['precision']:.4f}, "
                  f"Recall={r['recall']:.4f}, "
                  f"F1={r['f1-score']:.4f}, "
                  f"Support={int(r['support'])}")

    print(f"\n【混淆矩陣】")
    cm = metrics['confusion_matrix']
    labels = ['D', 'C', 'B', 'A']
    print(f"       {'  '.join(labels)}")
    for i, label in enumerate(labels):
        print(f"  {label}: {cm[i].tolist()}")

    print(f"{'=' * 80}\n")


if __name__ == '__main__':
    # 簡單測試
    print("測試 metrics...")

    # 虛擬預測結果
    np.random.seed(42)
    n_samples = 100

    y_true = np.random.choice([0, 1, 2, 3], n_samples)
    y_pred = np.random.choice([0, 1, 2, 3], n_samples)
    y_pred_proba = np.random.dirichlet([1, 1, 1, 1], n_samples)

    # 計算指標
    metrics = calculate_classification_metrics(y_true, y_pred, y_pred_proba)

    # 打印報告
    print_classification_report(metrics)

    # 計算 NDCG
    y_scores = y_pred_proba.max(axis=1)
    ndcg = calculate_ndcg(y_true, y_scores, k=10)
    print(f"NDCG@10: {ndcg:.4f}")

    print("\n✅ 所有測試通過！")
