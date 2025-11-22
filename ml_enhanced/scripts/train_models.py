"""
ML Model Training Script

訓練兩個模型:
1. Stock Selector: 預測訊號勝率 (分類)
2. Position Sizer: 預測預期報酬 (回歸)

Usage:
    python stock/ml_enhanced/scripts/train_models.py
    
Output:
    stock/ml_enhanced/models/stock_selector.pkl
    stock/ml_enhanced/models/position_sizer.pkl
"""

import sys
import os
import pandas as pd
import numpy as np
import pickle
import json
from datetime import datetime

# Add paths
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

# ML Libraries
try:
    import xgboost as xgb
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.metrics import classification_report, roc_auc_score, mean_squared_error, r2_score, precision_score, recall_score
except ImportError:
    print("❌ Missing ML libraries. Installing...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "xgboost", "scikit-learn"], check=True)
    import xgboost as xgb
    from sklearn.model_selection import train_test_split, cross_val_score
    from sklearn.metrics import classification_report, roc_auc_score, mean_squared_error, r2_score, precision_score, recall_score

# Configuration
DATA_FILE = os.path.join(os.path.dirname(__file__), '../data/ml_features.csv')
MODEL_DIR = os.path.join(os.path.dirname(__file__), '../models')
RESULTS_DIR = os.path.join(os.path.dirname(__file__), '../results')
SELECTOR_MODEL_PATH = os.path.join(MODEL_DIR, 'stock_selector.pkl')
SIZER_MODEL_PATH = os.path.join(MODEL_DIR, 'position_sizer.pkl')

# Feature columns (24 features total - updated 2025-11-21)
FEATURE_COLS = [
    # Pattern quality (3)
    'grade_numeric',
    'distance_to_buy_pct',
    'risk_pct',
    
    # Volume indicators (4) - NEW
    'volume_ratio_ma20',
    'volume_ratio_ma50',
    'volume_surge',
    'volume_trend_5d',
    
    # Momentum indicators (4) - NEW
    'momentum_5d',
    'momentum_20d',
    'price_vs_ma20',
    'price_vs_ma50',
    
    # RSI features (2)
    'rsi_14',              # UPDATED: now real RSI (was placeholder=50)
    'rsi_divergence',      # NEW
    
    # Technical indicators (3)
    'ma_trend',
    'volatility',
    'atr_ratio',
    
    # Market environment (2)
    'market_trend',
    'market_volatility',   # NEW
    
    # Relative strength (1) - NEW
    'rs_rating',
    
    # Pattern specific (1) - NEW
    'consolidation_days',
    
    # Signal counts (2) - placeholder for future implementation
    'signal_count_ma10',
    'signal_count_ma60',

    # Institutional flows (lag/rolling) - NEW
    'foreign_net_lag1',
    'investment_net_lag1',
    'dealer_net_lag1',
    'total_net_lag1',
    'foreign_net_sum_3d',
    'foreign_net_sum_5d',
    'foreign_net_sum_10d',
    'foreign_net_sum_20d',
    'total_net_sum_3d',
    'total_net_sum_5d',
    'total_net_sum_10d',
    'total_net_sum_20d',
    'foreign_investment_spread_lag1',
    'dealer_dominance_lag1',
    'foreign_net_to_vol_lag1',
    'total_net_to_vol_lag1'
]

def load_and_prepare_data():
    """載入並準備訓練數據"""
    print("="*80)
    print("Loading ML Features")
    print("="*80)
    
    # Load data
    df = pd.read_csv(DATA_FILE)
    print(f"\nLoaded {len(df)} samples")
    
    # Convert date to datetime for time-based split
    df['date'] = pd.to_datetime(df['date'])
    
    # Sort by date
    df = df.sort_values('date').reset_index(drop=True)
    
    # Remove rows with missing features
    df_clean = df.dropna(subset=FEATURE_COLS + ['actual_return', 'is_winner'])
    print(f"After removing NaN: {len(df_clean)} samples")
    
    # Show data distribution
    print(f"\nData Distribution:")
    print(f"  Winners (>10% return): {df_clean['is_winner'].sum()} ({df_clean['is_winner'].mean()*100:.1f}%)")
    print(f"  Average return: {df_clean['actual_return'].mean()*100:.2f}%")
    print(f"  Median return: {df_clean['actual_return'].median()*100:.2f}%")
    
    # Show date range
    print(f"\nDate Range:")
    print(f"  Start: {df_clean['date'].min()}")
    print(f"  End: {df_clean['date'].max()}")
    
    return df_clean

def time_based_split(df, test_size=0.2):
    """時間序列分割 (避免未來資訊洩漏)"""
    split_idx = int(len(df) * (1 - test_size))
    
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]
    
    print(f"\nTime-Based Split:")
    print(f"  Train: {len(train_df)} samples ({train_df['date'].min()} to {train_df['date'].max()})")
    print(f"  Test:  {len(test_df)} samples ({test_df['date'].min()} to {test_df['date'].max()})")
    
    return train_df, test_df


def generate_walk_forward_windows(df, train_months=3, test_months=1, min_train=50, min_test=20, max_windows=24):
    """產生滑動窗口 (月為單位)，避免資料洩漏。"""
    df_sorted = df.sort_values("date").reset_index(drop=True)
    if df_sorted.empty:
        return []

    windows = []
    start = df_sorted["date"].min()
    end = df_sorted["date"].max()
    window_count = 0

    while window_count < max_windows:
        train_end = start + pd.DateOffset(months=train_months)
        test_end = train_end + pd.DateOffset(months=test_months)

        train_mask = (df_sorted["date"] >= start) & (df_sorted["date"] < train_end)
        test_mask = (df_sorted["date"] >= train_end) & (df_sorted["date"] < test_end)

        train_df = df_sorted[train_mask]
        test_df = df_sorted[test_mask]

        if len(train_df) < min_train or len(test_df) < min_test:
            break

        windows.append(
            {
                "train_df": train_df,
                "test_df": test_df,
                "train_start": train_df["date"].min(),
                "train_end": train_df["date"].max(),
                "test_start": test_df["date"].min(),
                "test_end": test_df["date"].max(),
            }
        )

        window_count += 1
        start = start + pd.DateOffset(months=test_months)
        if start >= end:
            break

    return windows

def train_stock_selector(train_df, test_df):
    """訓練股票選擇模型 (分類)"""
    print("\n" + "="*80)
    print("Training Stock Selector (XGBoost Classifier)")
    print("="*80)
    
    # Prepare features and labels
    X_train = train_df[FEATURE_COLS]
    y_train = train_df['is_winner']
    X_test = test_df[FEATURE_COLS]
    y_test = test_df['is_winner']
    
    print(f"\nTraining samples: {len(X_train)}")
    print(f"Positive class ratio: {y_train.mean()*100:.1f}%")
    
    # Train XGBoost Classifier
    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric='logloss',
        use_label_encoder=False
    )
    
    print("\nTraining...")
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False
    )
    
    # Evaluate
    print("\n" + "-"*80)
    print("Evaluation on Test Set")
    print("-"*80)
    
    y_pred = model.predict(X_test)
    y_pred_proba = model.predict_proba(X_test)[:, 1]
    
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=['Loser', 'Winner']))
    
    auc = roc_auc_score(y_test, y_pred_proba)
    print(f"\nROC AUC Score: {auc:.4f}")
    
    # Feature importance
    print("\nTop 5 Important Features:")
    feature_importance = pd.DataFrame({
        'feature': FEATURE_COLS,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)
    print(feature_importance.head(5).to_string(index=False))
    
    # Test different thresholds
    print("\n" + "-"*80)
    print("Threshold Analysis")
    print("-"*80)
    
    for threshold in [0.5, 0.6, 0.7]:
        y_pred_thresh = (y_pred_proba >= threshold).astype(int)
        precision = (y_test[y_pred_thresh == 1] == 1).mean() if (y_pred_thresh == 1).sum() > 0 else 0
        recall = (y_pred_thresh[y_test == 1] == 1).mean()
        selected_pct = (y_pred_thresh == 1).mean() * 100
        
        print(f"\nThreshold {threshold}:")
        print(f"  Precision: {precision:.2%} (of selected, how many are winners)")
        print(f"  Recall: {recall:.2%} (of all winners, how many selected)")
        print(f"  Selected: {selected_pct:.1f}% of signals")
    
    return model

def train_position_sizer(train_df, test_df):
    """訓練倉位分配模型 (回歸)"""
    print("\n" + "="*80)
    print("Training Position Sizer (XGBoost Regressor)")
    print("="*80)
    
    # Prepare features and labels
    X_train = train_df[FEATURE_COLS]
    y_train = train_df['actual_return']
    X_test = test_df[FEATURE_COLS]
    y_test = test_df['actual_return']
    
    print(f"\nTraining samples: {len(X_train)}")
    print(f"Target mean: {y_train.mean()*100:.2f}%")
    print(f"Target std: {y_train.std()*100:.2f}%")
    
    # Train XGBoost Regressor
    model = xgb.XGBRegressor(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42
    )
    
    print("\nTraining...")
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False
    )
    
    # Evaluate
    print("\n" + "-"*80)
    print("Evaluation on Test Set")
    print("-"*80)
    
    y_pred = model.predict(X_test)
    
    mse = mean_squared_error(y_test, y_pred)
    rmse = np.sqrt(mse)
    r2 = r2_score(y_test, y_pred)
    
    print(f"\nMSE: {mse:.6f}")
    print(f"RMSE: {rmse:.4f} ({rmse*100:.2f}%)")
    print(f"R² Score: {r2:.4f}")
    
    # Correlation
    corr = np.corrcoef(y_test, y_pred)[0, 1]
    print(f"Correlation: {corr:.4f}")
    
    # Feature importance
    print("\nTop 5 Important Features:")
    feature_importance = pd.DataFrame({
        'feature': FEATURE_COLS,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)
    print(feature_importance.head(5).to_string(index=False))
    
    # Prediction distribution
    print("\n" + "-"*80)
    print("Prediction Distribution")
    print("-"*80)
    
    print(f"\nActual Returns:")
    print(f"  Mean: {y_test.mean()*100:.2f}%")
    print(f"  Median: {y_test.median()*100:.2f}%")
    print(f"  Min: {y_test.min()*100:.2f}%")
    print(f"  Max: {y_test.max()*100:.2f}%")
    
    print(f"\nPredicted Returns:")
    print(f"  Mean: {y_pred.mean()*100:.2f}%")
    print(f"  Median: {np.median(y_pred)*100:.2f}%")
    print(f"  Min: {y_pred.min()*100:.2f}%")
    print(f"  Max: {y_pred.max()*100:.2f}%")
    
    return model


def adversarial_validation_walk_forward(df, feature_cols, train_months=3, test_months=1):
    """
    對抗驗證：以 walk-forward 將 train 標為 0、test 標為 1，觀察分佈漂移。
    """
    windows = generate_walk_forward_windows(df, train_months=train_months, test_months=test_months)
    if not windows:
        print("⚠️ Not enough data for adversarial validation.")
        return []

    reports = []
    for idx, w in enumerate(windows, start=1):
        train_df = w["train_df"]
        test_df = w["test_df"]
        adv_df = pd.concat(
            [
                train_df.assign(split_label=0),
                test_df.assign(split_label=1),
            ],
            ignore_index=True,
        )

        X = adv_df[feature_cols]
        y = adv_df["split_label"]

        model = xgb.XGBClassifier(
            n_estimators=120,
            max_depth=4,
            learning_rate=0.08,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            eval_metric="logloss",
            use_label_encoder=False,
        )
        model.fit(X, y)

        proba = model.predict_proba(X)[:, 1]
        auc = roc_auc_score(y, proba)

        feature_importance = pd.DataFrame(
            {
                "feature": feature_cols,
                "importance": model.feature_importances_,
            }
        ).sort_values("importance", ascending=False)

        top_features = feature_importance.head(10).to_dict(orient="records")

        report = {
            "window": idx,
            "train_start": str(w["train_start"].date()),
            "train_end": str(w["train_end"].date()),
            "test_start": str(w["test_start"].date()),
            "test_end": str(w["test_end"].date()),
            "auc": float(auc),
            "top_features": top_features,
        }
        reports.append(report)

        print(f"\n[Adversarial] Window {idx}: AUC={auc:.4f} ({w['train_start'].date()}~{w['test_end'].date()})")
        print("  Top drift candidates:")
        print(feature_importance.head(5).to_string(index=False))

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "adversarial_report.json")
    with open(out_path, "w") as f:
        json.dump(reports, f, indent=2)
    print(f"\n✅ Adversarial validation saved to: {out_path}")
    return reports


def walk_forward_classification(df, feature_cols, train_months=3, test_months=1):
    """
    滑動窗口驗證：使用分類模型，回報各窗口 AUC/Precision/Recall。
    """
    windows = generate_walk_forward_windows(df, train_months=train_months, test_months=test_months)
    if not windows:
        print("⚠️ Not enough data for walk-forward evaluation.")
        return []

    results = []
    for idx, w in enumerate(windows, start=1):
        train_df = w["train_df"]
        test_df = w["test_df"]
        X_train = train_df[feature_cols]
        y_train = train_df["is_winner"]
        X_test = test_df[feature_cols]
        y_test = test_df["is_winner"]

        model = xgb.XGBClassifier(
            n_estimators=150,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            eval_metric="logloss",
            use_label_encoder=False,
        )
        model.fit(X_train, y_train)
        proba = model.predict_proba(X_test)[:, 1]
        y_pred = (proba >= 0.5).astype(int)

        auc = roc_auc_score(y_test, proba)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)

        result = {
            "window": idx,
            "train_start": str(w["train_start"].date()),
            "train_end": str(w["train_end"].date()),
            "test_start": str(w["test_start"].date()),
            "test_end": str(w["test_end"].date()),
            "train_samples": len(train_df),
            "test_samples": len(test_df),
            "auc": float(auc),
            "precision": float(precision),
            "recall": float(recall),
        }
        results.append(result)

        print(f"\n[Walk-Forward] Window {idx}: AUC={auc:.4f}, Precision={precision:.3f}, Recall={recall:.3f}")
        print(f"  Train {len(train_df)} samples ({w['train_start'].date()}~{w['train_end'].date()}), "
              f"Test {len(test_df)} samples ({w['test_start'].date()}~{w['test_end'].date()})")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "walk_forward_summary.csv")
    pd.DataFrame(results).to_csv(out_path, index=False)
    print(f"\n✅ Walk-forward summary saved to: {out_path}")
    return results

def save_models(selector_model, sizer_model):
    """儲存模型"""
    print("\n" + "="*80)
    print("Saving Models")
    print("="*80)
    
    # Create model directory
    os.makedirs(MODEL_DIR, exist_ok=True)
    
    # Save Stock Selector
    with open(SELECTOR_MODEL_PATH, 'wb') as f:
        pickle.dump(selector_model, f)
    print(f"\n✅ Stock Selector saved to: {SELECTOR_MODEL_PATH}")
    
    # Save Position Sizer
    with open(SIZER_MODEL_PATH, 'wb') as f:
        pickle.dump(sizer_model, f)
    print(f"✅ Position Sizer saved to: {SIZER_MODEL_PATH}")
    
    # Save feature columns for reference
    feature_info = {
        'feature_cols': FEATURE_COLS,
        'trained_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    feature_info_path = os.path.join(MODEL_DIR, 'feature_info.pkl')
    with open(feature_info_path, 'wb') as f:
        pickle.dump(feature_info, f)
    print(f"✅ Feature info saved to: {feature_info_path}")

def train_pattern_model(pattern_type, df):
    """Train model for a specific pattern type"""
    print(f"\n{'='*80}")
    print(f"Training Model for: {pattern_type.upper()}")
    print(f"{'='*80}")
    
    # Filter data for this pattern
    pattern_df = df[df['pattern_type'] == pattern_type.upper()].copy()
    
    if len(pattern_df) < 50:
        print(f"⚠️ Not enough data for {pattern_type} (n={len(pattern_df)}). Skipping.")
        return None, None
        
    print(f"Samples: {len(pattern_df)}")
    
    # Time split
    train_df, test_df = time_based_split(pattern_df, test_size=0.2)
    
    # Train Selector
    selector_model = train_stock_selector(train_df, test_df)
    
    # Train Sizer (Optional, maybe just use one global sizer? Or specific?)
    # Let's train specific sizer too for completeness
    sizer_model = train_position_sizer(train_df, test_df)
    
    return selector_model, sizer_model

def main():
    print("="*80)
    print("ML Model Training (Pattern × Exit Mode)")
    print("="*80)
    
    # 1. Load data
    df = load_and_prepare_data()
    
    # 1b. Drift check with adversarial validation (walk-forward)
    adversarial_validation_walk_forward(df, FEATURE_COLS, train_months=3, test_months=1)
    
    # 1c. Walk-forward evaluation (classification only, all patterns combined)
    walk_forward_classification(df, FEATURE_COLS, train_months=3, test_months=1)
    
    # 2. Train per pattern × exit_mode combination
    patterns = ['cup', 'htf', 'vcp']
    exit_modes = ['fixed_r2_t20', 'fixed_r3_t20', 'trailing_15r']
    
    for pat in patterns:
        for exit_mode in exit_modes:
            print(f"\n{'='*80}")
            print(f"Training Model: {pat.upper()} + {exit_mode}")
            print(f"{'='*80}")
            
            # Filter data for this specific combination
            pattern_df = df[
                (df['pattern_type'] == pat.upper()) &
                (df['exit_mode'] == exit_mode)
            ].copy()
            
            if len(pattern_df) < 50:
                print(f"⚠️ Not enough data for {pat} + {exit_mode} (n={len(pattern_df)}). Skipping.")
                continue
                
            print(f"Samples: {len(pattern_df)}")
            
            # Time split
            train_df, test_df = time_based_split(pattern_df, test_size=0.2)
            
            # Train Selector
            selector_model = train_stock_selector(train_df, test_df)
            
            # Train Sizer (Optional - we may skip sizer for now as we're focusing on selection)
            # sizer_model = train_position_sizer(train_df, test_df)
            
            # Save models
            model_name = f'stock_selector_{pat}_{exit_mode}.pkl'
            sel_path = os.path.join(MODEL_DIR, model_name)
            
            with open(sel_path, 'wb') as f:
                pickle.dump(selector_model, f)
                
            print(f"✅ Saved: {model_name}")

    # Save feature info (shared across all models)
    feature_info = {
        'feature_cols': FEATURE_COLS,
        'trained_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'patterns': patterns,
        'exit_modes': exit_modes
    }
    with open(os.path.join(MODEL_DIR, 'feature_info.pkl'), 'wb') as f:
        pickle.dump(feature_info, f)

    print("\n" + "="*80)
    print("Training Complete!")
    print("="*80)
    print(f"\nTrained {len(patterns) * len(exit_modes)} models:")
    for pat in patterns:
        for exit_mode in exit_modes:
            print(f"  - stock_selector_{pat}_{exit_mode}.pkl")

if __name__ == "__main__":
    main()
