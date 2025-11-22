"""
CatBoost 全局模型 Backtest (P0+P1+P2)

CatBoost 模型預測 (pattern, exit_mode) 的最佳組合和品質等級 (A/B/C/D)。
本腳本執行真正的回測：

1. 用 CatBoost 預測每個訊號的等級
2. 根據預測等級過濾訊號 (使用 A/B 級訊號進行交易)
3. 調用既有的 backtest engine (資金管理、手續費、稅金)
4. 輸出按 pattern×exit_mode 分組的績效統計

這些數據後續會被用於:
- Daily Scanner: 顯示推薦清單和該組合的歷史績效
- 特徵分析: 說明為什麼某個訊號被預測為 A/B/C/D

Usage:
    python catboost_enhanced/scripts/run_catboost_backtest.py

Output:
    catboost_enhanced/results/backtest_detail.csv - 每筆交易的詳細資訊
    catboost_enhanced/results/backtest_by_group.csv - 按 pattern×exit_mode 分組的績效
"""

import pandas as pd
import numpy as np
import os
import sys
import pickle
import polars as pl
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.logger import setup_logger
from scripts.run_backtest import (
    load_data_polars,
    generate_trade_candidates,
    run_capital_simulation,
    calculate_metrics
)

try:
    from catboost import CatBoostClassifier, Pool
except ImportError:
    print("❌ CatBoost 未安裝")
    sys.exit(1)

# 配置
CATBOOST_DATA_FILE = os.path.join(Path(__file__).resolve().parents[0], '..', 'data', 'catboost_features.csv')
MODEL_PATH = os.path.join(Path(__file__).resolve().parents[0], '..', 'models', 'catboost_global.cbm')
FEATURE_INFO_PATH = os.path.join(Path(__file__).resolve().parents[0], '..', 'models', 'catboost_feature_info.pkl')
RESULTS_DIR = os.path.join(Path(__file__).resolve().parents[0], '..', 'results')
BACKTEST_DETAIL_FILE = os.path.join(RESULTS_DIR, 'backtest_detail.csv')
BACKTEST_GROUP_FILE = os.path.join(RESULTS_DIR, 'backtest_by_group.csv')

logger = setup_logger('catboost_backtest')


def load_model_and_features():
    """載入模型和特徵信息"""
    logger.info("載入 CatBoost 模型...")

    if not os.path.exists(MODEL_PATH):
        logger.error(f"❌ 模型不存在: {MODEL_PATH}")
        return None, None

    model = CatBoostClassifier()
    model.load_model(MODEL_PATH)
    logger.info(f"✓ 模型載入成功")

    if not os.path.exists(FEATURE_INFO_PATH):
        logger.error(f"❌ 特徵信息不存在: {FEATURE_INFO_PATH}")
        return model, None

    with open(FEATURE_INFO_PATH, 'rb') as f:
        feature_info = pickle.load(f)

    logger.info(f"✓ 特徵信息載入成功 ({len(feature_info['feature_cols'])} 個特徵)")
    return model, feature_info


def load_catboost_features():
    """載入 CatBoost 特徵資料（包含預測標籤）"""
    logger.info(f"載入 CatBoost 特徵資料: {CATBOOST_DATA_FILE}")

    if not os.path.exists(CATBOOST_DATA_FILE):
        logger.error(f"❌ 檔案不存在: {CATBOOST_DATA_FILE}")
        return None

    df = pd.read_csv(CATBOOST_DATA_FILE)
    df['date'] = pd.to_datetime(df['date'])
    logger.info(f"✓ 載入 {len(df)} 筆樣本")
    return df


def predict_signals(model, feature_info, df_catboost):
    """
    用 CatBoost 模型預測每個訊號的等級 (A/B/C/D)

    Returns:
        df_catboost with columns:
        - pred_label: 預測標籤 (0-3)
        - pred_proba_*: 各類別概率
    """
    logger.info("\n進行 CatBoost 預測...")

    feature_cols = feature_info['feature_cols']
    cat_features = feature_info.get('cat_features', [])

    # 重建完整的特徵列表 (包含分類特徵)
    full_feature_cols = feature_cols + cat_features

    # 確保所有特徵存在
    missing = [c for c in full_feature_cols if c not in df_catboost.columns]
    if missing:
        logger.error(f"❌ 缺失特徵: {missing}")
        return None

    X = df_catboost[full_feature_cols].copy()

    # 預測
    y_pred = model.predict(X)
    y_pred_proba = model.predict_proba(X)

    df_catboost['pred_label'] = y_pred
    for i in range(4):
        df_catboost[f'pred_proba_{i}'] = y_pred_proba[:, i]

    # 統計
    label_map = {0: 'D', 1: 'C', 2: 'B', 3: 'A'}
    logger.info("  預測標籤分佈:")
    for label_val in range(4):
        count = (y_pred == label_val).sum()
        pct = count / len(y_pred) * 100
        logger.info(f"    {label_map[label_val]}: {count:5d} ({pct:5.1f}%)")

    return df_catboost


def run_backtest_with_predictions(df_polars, df_predictions):
    """
    執行真正的回測：

    1. 用 CatBoost 預測過濾訊號 (只保留 A/B 級訊號)
    2. 為每個訊號組合 (pattern × exit_mode) 執行交易模擬
    3. 統計按組合分組的績效

    Args:
        df_polars: 原始市場資料 (from load_data_polars)
        df_predictions: 帶有預測標籤的訊號資料

    Returns:
        detail_results: 每筆交易的詳細資訊
        group_results: 按 pattern×exit_mode 分組的績效統計
    """
    logger.info("\n" + "="*80)
    logger.info("執行 Backtest")
    logger.info("="*80)

    # 轉換為 pandas 便於操作
    df_polars_pd = df_polars.to_pandas()

    # 定義交易組合
    patterns = ['cup', 'htf', 'vcp']
    exit_modes_config = [
        {'name': 'fixed_r2_t20', 'type': 'fixed', 'r_mult': 2.0, 'time_exit': 20},
        {'name': 'fixed_r3_t20', 'type': 'fixed', 'r_mult': 3.0, 'time_exit': 20},
        {'name': 'trailing_15r', 'type': 'trailing', 'trigger_r': 1.5},
    ]

    all_trades = []
    group_results = []

    for pattern in patterns:
        for exit_mode_cfg in exit_modes_config:
            group_name = f"{pattern}_{exit_mode_cfg['name']}"

            # 過濾該組合的訊號 (只保留 A/B 級)
            pattern_col = f'is_{pattern}'
            df_filtered = df_predictions[
                (df_predictions['pattern_type'].str.upper() == pattern.upper()) &
                (df_predictions['pred_label'] >= 2)  # A/B 級
            ].copy()

            if len(df_filtered) == 0:
                logger.info(f"  {group_name}: 無 A/B 級訊號")
                continue

            logger.info(f"  {group_name}: {len(df_filtered)} 個 A/B 級訊號")

            # 將篩選後的訊號應用到原始資料
            df_test = df_polars_pd.copy()
            df_test['date'] = pd.to_datetime(df_test['date'])

            # 建立篩選集合
            filtered_set = set(zip(
                df_filtered['sid'].astype(str),
                df_filtered['date'].dt.strftime('%Y-%m-%d')
            ))

            # 只保留篩選後的訊號
            df_test['date_str'] = df_test['date'].dt.strftime('%Y-%m-%d')
            df_test['sid_str'] = df_test['sid'].astype(str)
            mask = df_test.apply(
                lambda x: (x['sid_str'], x['date_str']) not in filtered_set,
                axis=1
            )
            df_test.loc[mask, pattern_col] = False

            # 轉換回 Polars
            df_test_polars = pl.from_pandas(df_test.drop(columns=['date_str', 'sid_str']))

            # 執行交易模擬
            try:
                if exit_mode_cfg['type'] == 'fixed':
                    candidates = generate_trade_candidates(
                        df_test_polars, pattern_col, 'fixed',
                        {'r_mult': exit_mode_cfg['r_mult'], 'time_exit': exit_mode_cfg['time_exit']}
                    )
                else:
                    candidates = generate_trade_candidates(
                        df_test_polars, pattern_col, 'trailing',
                        {'trigger_r': exit_mode_cfg['trigger_r'], 'trail_ma': 'ma20'}
                    )

                if not candidates:
                    logger.info(f"    → 未生成交易候選")
                    continue

                trades = run_capital_simulation(candidates, mode='limited')

                if not trades:
                    logger.info(f"    → 未執行交易")
                    continue

                # 計算績效
                metrics = calculate_metrics(
                    trades,
                    f"{pattern.upper()} {exit_mode_cfg['name']}",
                    f"ML_A/B_Filtered"
                )

                if metrics:
                    logger.info(f"    → {len(trades)} 筆交易, "
                              f"勝率 {metrics.get('Win Rate %', 0):.1f}%, "
                              f"年化報酬 {metrics.get('Ann. Return %', 0):.1f}%")

                    # 添加到結果
                    metrics['pattern'] = pattern
                    metrics['exit_mode'] = exit_mode_cfg['name']
                    metrics['signal_count'] = len(df_filtered)
                    group_results.append(metrics)

                    # 保存交易詳情
                    for trade in trades:
                        trade_detail = {
                            'pattern': pattern,
                            'exit_mode': exit_mode_cfg['name'],
                            **trade
                        }
                        all_trades.append(trade_detail)

            except Exception as e:
                logger.warning(f"    ✗ 錯誤: {e}")
                continue

    return all_trades, group_results


def main():
    logger.info("="*80)
    logger.info("CatBoost 全局模型 Backtest")
    logger.info("="*80)

    # 1. 載入模型
    model, feature_info = load_model_and_features()
    if model is None or feature_info is None:
        return

    # 2. 載入特徵資料
    df_catboost = load_catboost_features()
    if df_catboost is None:
        return

    # 3. 預測
    df_catboost = predict_signals(model, feature_info, df_catboost)
    if df_catboost is None:
        return

    # 4. 載入市場資料 (for backtest engine)
    df_polars = load_data_polars()
    if df_polars is None:
        logger.error("❌ 無法載入市場資料")
        return

    # 5. 執行回測
    all_trades, group_results = run_backtest_with_predictions(df_polars, df_catboost)

    # 6. 保存結果
    logger.info("\n" + "="*80)
    logger.info("保存結果")
    logger.info("="*80)

    os.makedirs(RESULTS_DIR, exist_ok=True)

    if all_trades:
        df_trades = pd.DataFrame(all_trades)
        df_trades.to_csv(BACKTEST_DETAIL_FILE, index=False)
        logger.info(f"✓ 交易詳情保存: {BACKTEST_DETAIL_FILE} ({len(all_trades)} 筆)")

    if group_results:
        df_groups = pd.DataFrame(group_results)
        df_groups = df_groups.sort_values('Ann. Return %', ascending=False)
        df_groups.to_csv(BACKTEST_GROUP_FILE, index=False)
        logger.info(f"✓ 組合績效保存: {BACKTEST_GROUP_FILE}")

        logger.info("\n【按 Pattern×Exit_Mode 分組的績效】")
        cols_to_show = ['pattern', 'exit_mode', 'Ann. Return %', 'Win Rate', 'Sharpe', 'Trades']
        cols_available = [c for c in cols_to_show if c in df_groups.columns]
        print(df_groups[cols_available].to_string(index=False))


if __name__ == "__main__":
    main()
