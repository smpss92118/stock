"""
ML-Enhanced Backtest (Signal-Level Filtering)

直接在訊號層面應用 ML 過濾，然後使用原始回測引擎。

Strategy:
1. Load ml_features.csv (contains all signals with ML predictions)
2. Filter signals by ML threshold
3. Create filtered pattern_analysis_result.csv
4. Run original backtest on filtered data
5. Compare with baseline

Usage:
    python stock/ml_enhanced/scripts/run_ml_backtest.py
"""

import sys
import os
import pandas as pd
import numpy as np
import pickle
from datetime import datetime
import polars as pl

# Add paths
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

from scripts.run_backtest import (
    generate_trade_candidates,
    run_capital_simulation,
    calculate_metrics,
    load_data_polars
)

# Configuration
# Configuration
MODEL_DIR = os.path.join(os.path.dirname(__file__), '../models')
FEATURE_INFO_PATH = os.path.join(MODEL_DIR, 'feature_info.pkl')
ML_FEATURES_PATH = os.path.join(os.path.dirname(__file__), '../data/ml_features.csv')
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), '../results/ml_backtest_final.csv')
OUTPUT_REPORT = os.path.join(os.path.dirname(__file__), '../results/ml_backtest_final.md')

def load_ml_models():
    """載入 ML 模型 (Pattern Specific)"""
    print("Loading ML Stock Selectors...")
    models = {}
    
    try:
        with open(FEATURE_INFO_PATH, 'rb') as f:
            feature_info = pickle.load(f)
        
        patterns = ['cup', 'htf', 'vcp']
        for pat in patterns:
            path = os.path.join(MODEL_DIR, f'stock_selector_{pat}.pkl')
            if os.path.exists(path):
                with open(path, 'rb') as f:
                    models[pat] = pickle.load(f)
                print(f"✅ Loaded model: {pat.upper()}")
            else:
                print(f"⚠️ Model not found: {path}")
                
        print(f"✅ Feature info loaded (trained: {feature_info['trained_date']})")
        return models, feature_info['feature_cols']
    except Exception as e:
        print(f"❌ Failed to load models: {e}")
        return {}, []

def predict_all_signals(models, feature_cols):
    """對所有訊號進行預測 (使用特定模型)"""
    print("\nLoading ML features...")
    df_features = pd.read_csv(ML_FEATURES_PATH)
    print(f"  Total signals: {len(df_features)}")
    
    # Initialize proba column
    df_features['ml_proba'] = 0.0
    
    # Predict per pattern
    for pattern, model in models.items():
        # Filter by pattern type (case insensitive)
        mask = df_features['pattern_type'].str.lower() == pattern
        if not mask.any():
            continue
            
        X = df_features.loc[mask, feature_cols]
        if len(X) > 0:
            probas = model.predict_proba(X)[:, 1]
            df_features.loc[mask, 'ml_proba'] = probas
            print(f"  Predicted {len(X)} {pattern.upper()} signals")
    
    probas = df_features['ml_proba']
    print(f"\nPrediction Distribution:")
    print(f"  Mean: {probas.mean():.3f}")
    print(f"  Median: {np.median(probas):.3f}")
    print(f"  % > 0.3: {(probas > 0.3).mean() * 100:.1f}%")
    print(f"  % > 0.4: {(probas > 0.4).mean() * 100:.1f}%")
    print(f"  % > 0.5: {(probas > 0.5).mean() * 100:.1f}%")
    
    return df_features

def run_strategy_with_ml(df_polars, df_ml_signals, strategy, exit_mode, params, threshold, strategy_name):
    """運行單個策略的 ML 版本"""
    
    # Filter ML signals by threshold
    if threshold is not None:
        pattern_type = strategy.replace('is_', '').upper()
        df_filtered = df_ml_signals[
            (df_ml_signals['pattern_type'] == pattern_type) &
            (df_ml_signals['ml_proba'] >= threshold)
        ].copy()
        
        print(f"\n  ML threshold {threshold}: {len(df_filtered)}/{len(df_ml_signals[df_ml_signals['pattern_type'] == pattern_type])} signals selected")
        
        if len(df_filtered) == 0:
            print(f"    ⚠️ No signals selected, skipping")
            return None
    else:
        # Baseline: use all signals
        print(f"\n  Baseline (no ML filtering)")
        df_filtered = None
    
    # If ML filtering, modify the polars dataframe to zero out non-selected signals
    if df_filtered is not None:
        # Convert to pandas for easier manipulation
        df_pd = df_polars.to_pandas()
        
        # Create set of selected signals
        df_filtered['date'] = pd.to_datetime(df_filtered['date'])
        selected = set(zip(df_filtered['sid'], df_filtered['date'].dt.strftime('%Y-%m-%d')))
        
        # Zero out non-selected signals for this pattern
        df_pd['date_str'] = pd.to_datetime(df_pd['date']).dt.strftime('%Y-%m-%d')
        mask = df_pd.apply(lambda x: (x['sid'], x['date_str']) not in selected, axis=1)
        df_pd.loc[mask, strategy] = False
        df_pd = df_pd.drop(columns=['date_str'])
        
        # Convert back to polars
        df_data = pl.from_pandas(df_pd)
    else:
        df_data = df_polars
    
    # Generate candidates
    candidates = generate_trade_candidates(df_data, strategy, exit_mode, params)
    
    if not candidates:
        print(f"    ⚠️ No candidates generated")
        return None
    
    # Run simulation
    trades = run_capital_simulation(candidates, mode='limited')
    
    if not trades:
        print(f"    ⚠️ No trades executed")
        return None
    
    # Settings string
    if exit_mode == 'fixed':
        set_str = f"R={params['r_mult']}, T={params['time_exit']}"
    else:
        set_str = f"Trig={params['trigger_r']}R, Trail={params['trail_ma']}"
    
    # Calculate metrics
    ml_label = f"ML {threshold}" if threshold else "Baseline"
    res = calculate_metrics(trades, f"{strategy_name} ({ml_label})", set_str)
    
    if res:
        res['ml_threshold'] = threshold if threshold else 'None'
        res['signal_count'] = len(df_filtered) if df_filtered is not None else 'All'
        print(f"    {ml_label}: {res['Ann. Return %']}% return, Sharpe {res['Sharpe']}, {res['Trades']} trades")
    
    return res

def main():
    print("="*80)
    print("ML-Enhanced Backtest (Final)")
    print("="*80)
    
    # Load ML models
    models, feature_cols = load_ml_models()
    
    # Predict all signals
    df_ml_signals = predict_all_signals(models, feature_cols)
    
    # Load original data using load_data_polars (which calculates MA)
    print(f"\nLoading pattern data with MA...")
    df_polars = load_data_polars()
    
    if df_polars is None:
        print("❌ Failed to load data")
        return
    
    print(f"  Total rows: {df_polars.shape[0]}")
    
    # Test configurations
    test_configs = [
        ('is_htf', 'trailing', {'trigger_r': 1.5, 'trail_ma': 'ma20'}, 'HTF Trailing'),
        ('is_htf', 'fixed', {'r_mult': 2.0, 'time_exit': 20}, 'HTF Fixed (R=2.0, T=20)'),
        ('is_cup', 'fixed', {'r_mult': 3.0, 'time_exit': 20}, 'CUP Fixed (R=3.0, T=20)'),
        ('is_cup', 'fixed', {'r_mult': 2.0, 'time_exit': 20}, 'CUP Fixed (R=2.0, T=20)'),
    ]
    
    ml_thresholds = [None, 0.3, 0.4, 0.5]
    
    # Run all tests
    all_results = []
    
    for strategy, exit_mode, params, strategy_name in test_configs:
        print(f"\n{'='*80}")
        print(f"Testing: {strategy_name}")
        print(f"{'='*80}")
        
        for threshold in ml_thresholds:
            res = run_strategy_with_ml(
                df_polars, df_ml_signals, 
                strategy, exit_mode, params,
                threshold, strategy_name
            )
            if res:
                all_results.append(res)
    
    # Save results
    if all_results:
        df_res = pd.DataFrame(all_results)
        df_res = df_res.sort_values('Ann. Return %', ascending=False)
        
        os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
        df_res.to_csv(OUTPUT_CSV, index=False)
        print(f"\n✅ Results saved to {OUTPUT_CSV}")
        
        # Generate report
        with open(OUTPUT_REPORT, 'w') as f:
            f.write(f"# ML-Enhanced Backtest Final Results\n")
            f.write(f"Generated: {datetime.now()}\n\n")
            f.write("## Full Results\n\n")
            f.write(df_res.to_markdown(index=False))
            
            # Group by strategy
            f.write("\n\n## Results by Strategy\n\n")
            for strategy_name in df_res['Strategy'].str.extract(r'(.+?) \(')[0].unique():
                if pd.isna(strategy_name):
                    continue
                strategy_res = df_res[df_res['Strategy'].str.contains(strategy_name, na=False)]
                f.write(f"\n### {strategy_name}\n\n")
                # Include new metrics in strategy summary
                cols_to_show = ['ml_threshold', 'Ann. Return %', 'Sharpe', 'Win Rate', 'Trades', 
                               'Avg Holding Days', 'Max Win Streak', 'Max Loss Streak', 'Max DD %']
                f.write(strategy_res[cols_to_show].to_markdown(index=False))
                f.write("\n")
        
        print(f"✅ Report saved to {OUTPUT_REPORT}")
        
        # Print summary
        print(f"\n{'='*80}")
        print("FINAL RESULTS")
        print(f"{'='*80}\n")
        cols_to_print = ['Strategy', 'ml_threshold', 'Ann. Return %', 'Sharpe', 'Win Rate', 'Avg Holding Days']
        print(df_res[cols_to_print].to_string(index=False))
        
    else:
        print("\n❌ No results generated")

if __name__ == "__main__":
    main()
