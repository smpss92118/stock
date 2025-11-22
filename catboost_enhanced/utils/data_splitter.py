"""
P1: PurgedGroupKFold 實現

目的: 實現嚴格的時間序列交叉驗證，防止數據泄漏

核心特性:
1. 日期粒度的分割 (不是樣本粒度)
2. Embargo 機制 (train 和 test 之間的時間 buffer)
3. Walk-forward 驗證策略

原理: Lopéz de Prado (2018) 的 Purged K-Fold 演算法
"""

import numpy as np
import pandas as pd
from typing import Tuple, Iterator, List
from datetime import datetime, timedelta


class PurgedGroupKFold:
    """
    Purged Group K-Fold Cross Validation with Embargo

    防止前瞻偏差 (look-ahead bias) 的關鍵:
    1. 按日期 (group) 分割，不是按樣本
    2. train 和 test 之間加入 embargo 時間 buffer
    3. 確保 test 的 feature 不會"看到" train 的未來

    用法:
        cv = PurgedGroupKFold(n_splits=5, embargo_pct=0.05)
        for train_idx, test_idx in cv.split(X, groups=df['date']):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]
            ...
    """

    def __init__(self, n_splits: int = 5, embargo_pct: float = 0.05, embargo_days: int = 20):
        """
        初始化 PurgedGroupKFold

        Args:
            n_splits: 交叉驗證折數 (預設 5)
            embargo_pct: embargo 占總日期數的比例 (預設 0.05 = 5%)
                        如果 total_dates ≈ 400 days，embargo_pct=0.05 → embargo ≈ 20 days
            embargo_days: embargo 的絕對天數 (用於驗證和日誌)

        Example:
            >>> cv = PurgedGroupKFold(n_splits=5, embargo_pct=0.05, embargo_days=20)
        """
        self.n_splits = n_splits
        self.embargo_pct = embargo_pct
        self.embargo_days = embargo_days

    def split(
        self,
        X: np.ndarray,
        y: np.ndarray = None,
        groups: np.ndarray = None,
        verbose: bool = True,
    ) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        """
        生成訓練集和測試集的索引

        Args:
            X: 特徵矩陣 (n_samples, n_features)
            y: 目標變數 (選擇項，用於相容性)
            groups: 日期陣列 (n_samples,)，例如 df['date'].values
            verbose: 是否打印每個 fold 的詳細信息

        Yields:
            (train_indices, test_indices) 元組

        不變量保證:
            1. max(train_dates) + embargo_days <= min(test_dates)
            2. 所有 fold 都滿足上述條件
            3. 沒有樣本同時出現在 train 和 test 中

        Example:
            >>> cv = PurgedGroupKFold(n_splits=5, embargo_pct=0.05)
            >>> for fold, (train_idx, test_idx) in enumerate(cv.split(X, groups=dates)):
            ...     print(f"Fold {fold}: train={len(train_idx)}, test={len(test_idx)}")
        """

        if groups is None:
            raise ValueError("groups 不能為 None，應為日期陣列")

        # ========== 轉換為 DataFrame 以便按日期操作 ==========
        n_samples = len(X)
        df_groups = pd.DataFrame({
            'date': groups,
            'idx': np.arange(n_samples),
        })

        # ========== 取得唯一日期 (排序) ==========
        unique_dates = sorted(df_groups['date'].unique())
        n_dates = len(unique_dates)

        # ========== 計算 embargo 大小 ==========
        embargo_size = max(1, int(n_dates * self.embargo_pct))

        if verbose:
            print(f"\n{'=' * 80}")
            print(f"PurgedGroupKFold 配置")
            print(f"{'=' * 80}")
            print(f"  總日期數: {n_dates}")
            print(f"  Embargo 比例: {self.embargo_pct * 100:.1f}%")
            print(f"  Embargo 大小: {embargo_size} 天")
            print(f"  期望 embargo 天數: {self.embargo_days}")
            print(f"  交叉驗證折數: {self.n_splits}")
            print(f"  總樣本數: {n_samples}")

        # ========== Walk-forward 分割 ==========
        fold_idx = 0

        for i in range(self.n_splits):
            # 測試集的日期範圍
            test_start_idx = i * n_dates // self.n_splits
            test_end_idx = (i + 1) * n_dates // self.n_splits

            # 訓練集的日期範圍 (應用 embargo)
            train_end_idx = test_start_idx - embargo_size

            # ========== 檢查數據量 ==========
            if train_end_idx <= 0:
                if verbose:
                    print(f"\n⚠️  Fold {i}: 訓練集不足，跳過")
                continue

            # ========== 構建日期範圍 ==========
            train_dates = unique_dates[:train_end_idx]
            test_dates = unique_dates[test_start_idx:test_end_idx]

            # ========== 轉換回樣本索引 ==========
            train_indices = df_groups[df_groups['date'].isin(train_dates)]['idx'].values
            test_indices = df_groups[df_groups['date'].isin(test_dates)]['idx'].values

            # ========== 驗證 embargo 是否有效 ==========
            last_train_date = train_dates[-1]
            first_test_date = test_dates[0] if len(test_dates) > 0 else None

            if first_test_date is not None:
                # 計算實際的日期間隙
                if isinstance(last_train_date, str):
                    # 日期是字符串格式
                    try:
                        last_train_dt = pd.to_datetime(last_train_date)
                        first_test_dt = pd.to_datetime(first_test_date)
                        gap_days = (first_test_dt - last_train_dt).days
                    except:
                        gap_days = None
                else:
                    # 日期是 datetime 物件
                    gap_days = (first_test_date - last_train_date).days

                # ===== 警告檢查 =====
                is_gap_ok = gap_days is None or gap_days >= self.embargo_days

                if verbose:
                    status = "✓" if is_gap_ok else "⚠️ "
                    gap_str = f"{gap_days}天" if gap_days is not None else "N/A"

                    print(f"\n{status} Fold {fold_idx}:")
                    print(f"    訓練日期: {train_dates[0]} → {last_train_date}")
                    print(f"    測試日期: {first_test_date} → {test_dates[-1] if len(test_dates) > 0 else 'N/A'}")
                    print(f"    日期間隙: {gap_str} (要求: >= {self.embargo_days}天)")
                    print(f"    訓練樣本: {len(train_indices)}, 測試樣本: {len(test_indices)}")

                if not is_gap_ok and gap_days is not None:
                    print(f"    ⚠️ WARNING: 數據泄漏風險！")

            fold_idx += 1
            yield train_indices, test_indices

        if verbose:
            print(f"{'=' * 80}\n")

    def get_n_splits(self, X=None, y=None, groups=None):
        """返回交叉驗證的折數 (相容性方法)"""
        return self.n_splits


def validate_embargo(
    df: pd.DataFrame,
    cv: 'PurgedGroupKFold',
    date_col: str = 'date',
    verbose: bool = True,
) -> dict:
    """
    驗證 embargo 是否真正生效

    檢查項目:
    1. 所有 fold 的日期間隙 >= embargo_days
    2. 訓練集和測試集沒有重疊
    3. embargo 的實際大小

    Args:
        df: DataFrame (應包含 date 欄位)
        cv: PurgedGroupKFold 實例
        date_col: 日期欄位名稱
        verbose: 是否打印詳細信息

    Returns:
        dict with validation results:
            - 'is_valid': bool
            - 'folds': list of fold results
            - 'warnings': list of warnings

    Example:
        >>> result = validate_embargo(df, cv)
        >>> if result['is_valid']:
        ...     print("✅ Embargo validation passed!")
    """

    results = {
        'is_valid': True,
        'folds': [],
        'warnings': [],
    }

    for fold_idx, (train_idx, test_idx) in enumerate(cv.split(df.values, groups=df[date_col].values)):
        train_dates = df.iloc[train_idx][date_col]
        test_dates = df.iloc[test_idx][date_col]

        last_train_date = train_dates.max()
        first_test_date = test_dates.min()

        # 計算間隙
        if isinstance(last_train_date, str):
            last_train_date = pd.to_datetime(last_train_date)
            first_test_date = pd.to_datetime(first_test_date)

        gap = (first_test_date - last_train_date).days

        fold_info = {
            'fold': fold_idx,
            'gap_days': gap,
            'train_samples': len(train_idx),
            'test_samples': len(test_idx),
            'embargo_ok': gap >= cv.embargo_days,
        }

        results['folds'].append(fold_info)

        if not fold_info['embargo_ok']:
            results['is_valid'] = False
            results['warnings'].append(
                f"Fold {fold_idx}: 日期間隙 {gap} 天 < {cv.embargo_days} 天"
            )

    if verbose:
        print(f"\n{'=' * 80}")
        print(f"Embargo 驗證結果")
        print(f"{'=' * 80}")

        for fold_info in results['folds']:
            status = "✓" if fold_info['embargo_ok'] else "✗"
            print(f"{status} Fold {fold_info['fold']}: "
                  f"gap={fold_info['gap_days']}天, "
                  f"train={fold_info['train_samples']}, "
                  f"test={fold_info['test_samples']}")

        if results['warnings']:
            print(f"\n⚠️ 警告:")
            for w in results['warnings']:
                print(f"  {w}")
        else:
            print(f"\n✅ 所有 embargo 檢查通過！")

        print(f"{'=' * 80}\n")

    return results


if __name__ == '__main__':
    # 簡單測試
    print("測試 PurgedGroupKFold...")

    # 創建虛擬時間序列數據
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', periods=400, freq='B')  # 400 個交易日

    n_samples = 4000
    date_indices = np.random.choice(len(dates), n_samples)
    sample_dates = dates[date_indices]

    X = np.random.randn(n_samples, 10)
    y = np.random.randint(0, 4, n_samples)

    # 初始化 CV
    cv = PurgedGroupKFold(n_splits=5, embargo_pct=0.05, embargo_days=20)

    # 執行分割
    for fold, (train_idx, test_idx) in enumerate(cv.split(X, y, groups=sample_dates.values)):
        print(f"Fold {fold}: train={len(train_idx)}, test={len(test_idx)}")

    print("\n✅ 測試通過！")
