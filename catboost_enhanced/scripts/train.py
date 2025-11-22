"""
CatBoost 全局模型訓練 (P0+P1+P2 完整實現)

P0: 全局模型
    - 單一 CatBoostClassifier (4 分類)
    - pattern_type, exit_mode 作為類別特徵
    - 從 36,823 個樣本學習，而非 3000 個/模型

P1: Embargo 數據隔離
    - PurgedGroupKFold 按日期分割
    - 20 天 embargo buffer
    - 防止 label leak

P2: 樣本權重和損失函數
    - 三層權重: score 幅度 + 標籤 + 類頻率補償
    - 類權重: D/C=1.0, B=1.5, A=2.0
    - MultiClass 損失函數 + class_weights

Usage:
    python catboost_enhanced/scripts/train.py

Output:
    catboost_enhanced/models/global_catboost.cbm
    catboost_enhanced/results/feature_importance.csv
    catboost_enhanced/results/cv_metrics.csv
"""

import pandas as pd
import numpy as np
import os
import sys
import pickle
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.utils.logger import setup_logger
from catboost_enhanced.utils.loss_functions import compute_sample_weights, verify_sample_weights
from catboost_enhanced.utils.data_splitter import PurgedGroupKFold, validate_embargo
from catboost_enhanced.utils.metrics import calculate_classification_metrics, print_classification_report
from catboost_enhanced.configs.model_config import (
    get_catboost_params,
    get_cv_config,
    SAMPLE_WEIGHT_CONFIG,
)

try:
    from catboost import CatBoostClassifier, Pool
    from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
except ImportError:
    print("❌ CatBoost 或 sklearn 未安裝")
    sys.exit(1)

# 配置
DATA_FILE = os.path.join(Path(__file__).resolve().parents[0], '..', 'data', 'catboost_features.csv')
MODEL_DIR = os.path.join(Path(__file__).resolve().parents[0], '..', 'models')
RESULTS_DIR = os.path.join(Path(__file__).resolve().parents[0], '..', 'results')
MODEL_PATH = os.path.join(MODEL_DIR, 'catboost_global.cbm')
FEATURE_INFO_PATH = os.path.join(MODEL_DIR, 'catboost_feature_info.pkl')
CV_METRICS_FILE = os.path.join(RESULTS_DIR, 'cv_metrics.csv')
FEATURE_IMPORTANCE_FILE = os.path.join(RESULTS_DIR, 'feature_importance.csv')

logger = setup_logger('catboost_train')


def load_and_prepare_data():
    """
    載入並準備訓練資料

    Returns:
        (X, y, df, feature_cols, cat_features)
    """
    logger.info("Loading data from {DATA_FILE}...")

    if not os.path.exists(DATA_FILE):
        logger.error(f"❌ 資料檔案不存在: {DATA_FILE}")
        return None, None, None, None, None

    df = pd.read_csv(DATA_FILE)
    df['date'] = pd.to_datetime(df['date'])

    logger.info(f"✓ 載入 {len(df)} 筆樣本")

    # 載入特徵信息
    if not os.path.exists(FEATURE_INFO_PATH):
        logger.error(f"❌ 特徵信息檔案不存在: {FEATURE_INFO_PATH}")
        return None, None, None, None, None

    with open(FEATURE_INFO_PATH, 'rb') as f:
        info = pickle.load(f)

    feature_cols = info['feature_cols']
    cat_features = info['cat_features']

    logger.info(f"✓ 特徵數: {len(feature_cols)}")
    logger.info(f"  - 類別特徵: {cat_features}")
    logger.info(f"  - 數值特徵: {len(feature_cols) - len(cat_features)}")

    # 檢查標籤列
    if 'label_int' not in df.columns:
        logger.error("❌ 標籤列 'label_int' 不存在")
        return None, None, None, None, None

    # 過濾掉非數值特徵 (只保留數值和已指定的類別特徵)
    numeric_cols = df[feature_cols].select_dtypes(include=[np.number]).columns.tolist()
    safe_feature_cols = numeric_cols + cat_features

    # 確保類別特徵存在
    for cat_feat in cat_features:
        if cat_feat not in df.columns:
            logger.warning(f"⚠️ 類別特徵 {cat_feat} 不在資料中")
            safe_feature_cols.remove(cat_feat)

    X = df[safe_feature_cols].copy()
    y = df['label_int'].copy()

    logger.info(f"✓ 過濾後的特徵數: {len(safe_feature_cols)}")
    logger.info(f"  - 數值特徵: {len(numeric_cols)}")
    logger.info(f"  - 類別特徵: {[c for c in cat_features if c in safe_feature_cols]}")

    return X, y, df, safe_feature_cols, [c for c in cat_features if c in safe_feature_cols]


def train_with_cv(X, y, df, feature_cols, cat_features):
    """
    使用 PurgedGroupKFold 進行交叉驗證訓練 (P1+P2)

    Args:
        X: 特徵矩陣
        y: 目標變數 (0-3)
        df: 完整 DataFrame (用於提取 date 和 score)
        feature_cols: 特徵列表
        cat_features: 類別特徵列表

    Returns:
        fold_results: 每個 fold 的結果列表
    """
    logger.info("\n" + "="*80)
    logger.info("P1+P2: 交叉驗證訓練 (Embargo + Sample Weights)")
    logger.info("="*80)

    cv_config = get_cv_config()
    cv = PurgedGroupKFold(
        n_splits=cv_config['n_splits'],
        embargo_pct=cv_config['embargo_pct'],
        embargo_days=cv_config['embargo_days']
    )

    fold_results = []
    all_predictions = []
    all_actuals = []

    for fold, (train_idx, val_idx) in enumerate(cv.split(X.values, y.values, groups=df['date'].values)):
        logger.info(f"\n【Fold {fold+1}/{cv_config['n_splits']}】")

        X_train = X.iloc[train_idx].reset_index(drop=True)
        y_train = y.iloc[train_idx].reset_index(drop=True)
        df_train = df.iloc[train_idx].reset_index(drop=True)

        X_val = X.iloc[val_idx].reset_index(drop=True)
        y_val = y.iloc[val_idx].reset_index(drop=True)

        logger.info(f"  訓練樣本: {len(X_train)}, 驗證樣本: {len(X_val)}")

        # ========== P2: 計算樣本權重 ==========
        logger.info(f"\n  計算樣本權重 (P2)...")
        sample_weights = compute_sample_weights(
            df_train,
            score_col='efficiency_score',
            label_col='label_int',
            score_weight_scale=SAMPLE_WEIGHT_CONFIG['score_weight_scale'],
            label_weights=SAMPLE_WEIGHT_CONFIG['label_weight_multipliers'],
            class_freq_power=SAMPLE_WEIGHT_CONFIG['class_freq_compensation_power'],
            verbose=False
        )

        # 驗證權重
        if SAMPLE_WEIGHT_CONFIG.get('verify_weights', True):
            verify_result = verify_sample_weights(
                sample_weights, df_train,
                label_col='label_int',
                verbose=False
            )
            if not verify_result['is_valid']:
                logger.warning(f"  ⚠️ 權重驗證警告:")
                for w in verify_result['warnings']:
                    logger.warning(f"    {w}")

        # ========== 訓練模型 (P0) ==========
        logger.info(f"\n  訓練 CatBoost 模型 (P0 全局)...")

        model_params = get_catboost_params()
        model_params['cat_features'] = cat_features
        model_params['random_seed'] = 42

        model = CatBoostClassifier(**model_params)

        # 訓練
        model.fit(
            X_train,
            y_train,
            sample_weight=sample_weights,
            eval_set=[(X_val, y_val)],
            verbose=False
        )

        logger.info(f"  ✓ 模型訓練完成")

        # ========== 評估 ==========
        logger.info(f"\n  評估模型...")

        y_pred = model.predict(X_val)
        y_pred_proba = model.predict_proba(X_val)

        metrics = calculate_classification_metrics(y_val.values, y_pred, y_pred_proba)

        logger.info(f"    準確率: {metrics['accuracy']:.4f}")
        logger.info(f"    精度 (macro): {metrics['precision_macro']:.4f}")
        logger.info(f"    召回 (macro): {metrics['recall_macro']:.4f}")
        logger.info(f"    F1 (macro): {metrics['f1_macro']:.4f}")

        if 'log_loss' in metrics:
            logger.info(f"    Log Loss: {metrics['log_loss']:.4f}")

        fold_result = {
            'fold': fold + 1,
            'train_size': len(X_train),
            'val_size': len(X_val),
            'metrics': metrics,
            'model': model,
            'y_pred': y_pred,
            'y_val': y_val.values,
        }

        fold_results.append(fold_result)

        all_predictions.extend(y_pred)
        all_actuals.extend(y_val.values)

    # ========== 交叉驗證統計 ==========
    logger.info("\n" + "="*80)
    logger.info("交叉驗證結果統計")
    logger.info("="*80)

    cv_df = pd.DataFrame([
        {
            'fold': r['fold'],
            'accuracy': r['metrics']['accuracy'],
            'precision_macro': r['metrics']['precision_macro'],
            'recall_macro': r['metrics']['recall_macro'],
            'f1_macro': r['metrics']['f1_macro'],
        }
        for r in fold_results
    ])

    logger.info("\n" + cv_df.to_string(index=False))

    mean_accuracy = cv_df['accuracy'].mean()
    mean_f1 = cv_df['f1_macro'].mean()

    logger.info(f"\n  平均準確率: {mean_accuracy:.4f} (± {cv_df['accuracy'].std():.4f})")
    logger.info(f"  平均 F1: {mean_f1:.4f} (± {cv_df['f1_macro'].std():.4f})")

    # 保存 CV 結果
    os.makedirs(RESULTS_DIR, exist_ok=True)
    cv_df.to_csv(CV_METRICS_FILE, index=False)
    logger.info(f"\n✓ 保存 CV 指標到 {CV_METRICS_FILE}")

    return fold_results


def train_final_model(X, y, df, feature_cols, cat_features):
    """
    在全部資料上訓練最終模型 (P0+P2)

    Args:
        X: 特徵矩陣
        y: 目標變數
        df: 完整 DataFrame
        feature_cols: 特徵列表
        cat_features: 類別特徵列表

    Returns:
        訓練好的模型
    """
    logger.info("\n" + "="*80)
    logger.info("最終模型訓練 (全資料, P0+P2)")
    logger.info("="*80)

    # 計算全資料的樣本權重 (P2)
    logger.info("\n計算全資料樣本權重...")
    sample_weights = compute_sample_weights(
        df,
        score_col='efficiency_score',
        label_col='label_int',
        score_weight_scale=SAMPLE_WEIGHT_CONFIG['score_weight_scale'],
        label_weights=SAMPLE_WEIGHT_CONFIG['label_weight_multipliers'],
        class_freq_power=SAMPLE_WEIGHT_CONFIG['class_freq_compensation_power'],
        verbose=True
    )

    # 訓練模型 (P0 全局)
    logger.info("\n訓練全局 CatBoost 模型...")

    model_params = get_catboost_params(iterations=2000)
    model_params['cat_features'] = cat_features
    model_params['random_seed'] = 42
    model_params['use_best_model'] = False  # 全資料訓練無驗證集，不使用 use_best_model

    model = CatBoostClassifier(**model_params)

    model.fit(
        X, y,
        sample_weight=sample_weights,
        verbose=100
    )

    logger.info("✓ 模型訓練完成")

    return model


def save_model_and_artifacts(model, X, feature_cols, cat_features):
    """保存模型和相關檔案"""
    logger.info("\n" + "="*80)
    logger.info("保存模型和工件")
    logger.info("="*80)

    # 保存模型
    os.makedirs(MODEL_DIR, exist_ok=True)
    model.save_model(MODEL_PATH)
    logger.info(f"✓ 模型保存到 {MODEL_PATH}")

    # 特徵重要性
    logger.info("\n計算特徵重要性...")
    importance = model.get_feature_importance()
    feat_imp = pd.DataFrame({
        'feature': feature_cols,
        'importance': importance
    }).sort_values('importance', ascending=False)

    logger.info("\n【Top 20 特徵】")
    print(feat_imp.head(20).to_string(index=False))

    os.makedirs(RESULTS_DIR, exist_ok=True)
    feat_imp.to_csv(FEATURE_IMPORTANCE_FILE, index=False)
    logger.info(f"\n✓ 特徵重要性保存到 {FEATURE_IMPORTANCE_FILE}")

    # 模型元資料
    metadata = {
        'n_features': len(feature_cols),
        'cat_features': cat_features,
        'n_samples': len(X),
        'training_date': datetime.now().isoformat(),
        'model_type': 'CatBoostClassifier',
        'objective': 'MultiClass (4-class: D/C/B/A)',
        'class_weights': [1.0, 1.0, 1.5, 2.0],
    }

    metadata_file = os.path.join(MODEL_DIR, 'model_metadata.json')
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"✓ 模型元資料保存到 {metadata_file}")


def main():
    logger.info("="*80)
    logger.info("CatBoost 全局模型訓練 (P0+P1+P2)")
    logger.info("="*80)

    # 1. 載入資料
    logger.info("\n【步驟 1/4】載入資料")
    X, y, df, feature_cols, cat_features = load_and_prepare_data()
    if X is None:
        return

    # 2. 交叉驗證訓練 (P1+P2)
    logger.info("\n【步驟 2/4】交叉驗證訓練")
    fold_results = train_with_cv(X, y, df, feature_cols, cat_features)

    # 3. 最終模型訓練 (P0+P2)
    logger.info("\n【步驟 3/4】最終模型訓練")
    final_model = train_final_model(X, y, df, feature_cols, cat_features)

    # 4. 保存模型和工件
    logger.info("\n【步驟 4/4】保存模型")
    save_model_and_artifacts(final_model, X, feature_cols, cat_features)

    logger.info("\n" + "="*80)
    logger.info("✅ CatBoost 訓練完成！")
    logger.info("="*80)
    logger.info(f"\n模型已保存到: {MODEL_PATH}")
    logger.info(f"結果已保存到: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
