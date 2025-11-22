"""
CatBoost 資料準備腳本 (簡單包裝版本)

直接呼叫 ml_enhanced/scripts/prepare_ml_data.py 中的 generate_catboost_global_features() 函數

Usage:
    python catboost_enhanced/scripts/prepare_catboost_data.py

Output:
    catboost_enhanced/data/catboost_features.csv
    catboost_enhanced/models/catboost_feature_info.pkl
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.logger import setup_logger
from ml_enhanced.scripts.prepare_ml_data import generate_catboost_global_features, load_data_polars
from src.ml.features import calculate_technical_indicators
from src.data.institutional import load_institutional_raw, compute_institutional_features
from ml_enhanced.scripts.prepare_ml_data import apply_group_zscore
import pandas as pd
import numpy as np

logger = setup_logger('prepare_catboost_data')

# 配置
OUTPUT_DIR = os.path.join(Path(__file__).resolve().parents[0], '..', 'data')
OUTPUT_FILE = os.path.join(OUTPUT_DIR, 'catboost_features.csv')


def main():
    logger.info("="*80)
    logger.info("CatBoost Data Preparation (via ml_enhanced)")
    logger.info("="*80)

    # 1. 載入原始資料
    logger.info("\n[1/5] Loading data...")
    df = load_data_polars()
    if df is None:
        logger.error("❌ Failed to load data")
        return

    df_pd = df.to_pandas()
    df_pd['sid'] = df_pd['sid'].astype(str)
    df_pd['date'] = pd.to_datetime(df_pd['date'])
    logger.info(f"✓ Loaded {len(df_pd)} rows")

    # 2. 合併機構流特徵
    logger.info("\n[2/5] Loading institutional features...")
    inst_raw = load_institutional_raw()
    if inst_raw is None or inst_raw.empty:
        logger.warning("⚠️ No institutional data; filling with zeros")
        inst_feature_cols = [
            'foreign_net_lag1', 'investment_net_lag1', 'dealer_net_lag1', 'total_net_lag1',
            'foreign_net_sum_3d', 'foreign_net_sum_5d', 'foreign_net_sum_10d', 'foreign_net_sum_20d',
            'total_net_sum_3d', 'total_net_sum_5d', 'total_net_sum_10d', 'total_net_sum_20d',
            'foreign_investment_spread_lag1', 'dealer_dominance_lag1',
            'foreign_net_to_vol_lag1', 'total_net_to_vol_lag1'
        ]
        for col in inst_feature_cols:
            df_pd[col] = 0
    else:
        inst_feat_df = compute_institutional_features(inst_raw)
        inst_feat_df['sid'] = inst_feat_df['sid'].astype(str)
        inst_feat_df['date'] = pd.to_datetime(inst_feat_df['date'])
        df_pd = df_pd.merge(inst_feat_df, on=['sid', 'date'], how='left')

        # 計算機構流與成交量比率
        volume_safe = df_pd['volume'].replace(0, np.nan)
        df_pd['foreign_net_to_vol_lag1'] = df_pd['foreign_net_lag1'] / volume_safe
        df_pd['total_net_to_vol_lag1'] = df_pd['total_net_lag1'] / volume_safe

        # 填補缺失值
        inst_feature_cols = [
            'foreign_net_lag1', 'investment_net_lag1', 'dealer_net_lag1', 'total_net_lag1',
            'foreign_net_sum_3d', 'foreign_net_sum_5d', 'foreign_net_sum_10d', 'foreign_net_sum_20d',
            'total_net_sum_3d', 'total_net_sum_5d', 'total_net_sum_10d', 'total_net_sum_20d',
            'foreign_investment_spread_lag1', 'dealer_dominance_lag1',
            'foreign_net_to_vol_lag1', 'total_net_to_vol_lag1'
        ]
        for col in inst_feature_cols:
            if col not in df_pd.columns:
                df_pd[col] = np.nan
        median_fill = df_pd[inst_feature_cols].median()
        df_pd[inst_feature_cols] = df_pd[inst_feature_cols].fillna(median_fill)
        logger.info(f"✓ Merged institutional features")

    # 3. 計算技術指標
    logger.info("\n[3/5] Calculating technical indicators...")
    df_pd = df_pd.groupby('sid', group_keys=False).apply(calculate_technical_indicators).reset_index(drop=True)
    logger.info("✓ Technical indicators calculated")

    # 4. 標準化漂移敏感特徵
    logger.info("\n[4/5] Applying z-score normalization...")
    drift_cols = [
        'foreign_net_sum_3d', 'foreign_net_sum_5d', 'foreign_net_sum_10d', 'foreign_net_sum_20d',
        'total_net_sum_3d', 'total_net_sum_5d', 'total_net_sum_10d', 'total_net_sum_20d',
        'volatility', 'atr_ratio', 'price_vs_ma20', 'price_vs_ma50',
        'volume_ratio_ma20', 'volume_ratio_ma50',
        'momentum_5d', 'momentum_20d', 'rsi_14'
    ]
    df_pd = apply_group_zscore(df_pd, drift_cols, group_key='sid')
    logger.info("✓ Z-score normalization applied")

    # 5. 生成 CatBoost 全局特徵 (P0+P1+P2)
    logger.info("\n[5/5] Generating CatBoost global features...")
    generate_catboost_global_features(df_pd, OUTPUT_FILE)

    logger.info("\n" + "="*80)
    logger.info("✅ CatBoost Data Preparation Complete!")
    logger.info("="*80)


if __name__ == "__main__":
    main()
