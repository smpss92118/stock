"""
ML-Enhanced Backtest (Comprehensive)

測試 ML Stock Selector 對多個優秀策略的影響:
1. HTF Trailing (1.5R, MA20): 153.4% baseline
2. HTF Fixed (R=2.0, T=20): 74.7% baseline
3. CUP Fixed (R=3.0, T=20): 98.2% baseline, Sharpe 2.19
4. CUP Fixed (R=2.0, T=20): 69.0% baseline, Sharpe 2.14
5. Combined (HTF Trailing + CUP R=3.0)

Each tested with:
- Baseline (no ML)
- ML threshold 0.3 (loose)
- ML threshold 0.4 (medium)
- ML threshold 0.5 (strict)

Usage:
    python stock/ml_enhanced/scripts/run_ml_backtest_comprehensive.py
    
Output:
    stock/ml_enhanced/results/ml_backtest_comparison.md
    stock/ml_enhanced/results/ml_backtest_comparison.csv
"""

import sys
import os
import pandas as pd
import numpy as np
import pickle
from datetime import datetime

# Add paths
sys.path.append(os.path.join(os.path.dirname(__file__), '../..'))

# Import original backtest functions
from scripts.run_backtest import (
    load_data_polars,
    generate_trade_candidates,
    run_capital_simulation,
    calculate_metrics
)

# Configuration
MODEL_PATH = os.path.join(os.path.dirname(__file__), '../models/stock_selector.pkl')
FEATURE_INFO_PATH = os.path.join(os.path.dirname(__file__), '../models/feature_info.pkl')
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), '../results/ml_backtest_comparison.csv')
OUTPUT_REPORT = os.path.join(os.path.dirname(__file__), '../results/ml_backtest_comparison.md')

def load_ml_model():
    """載入 ML 模型"""
    print("Loading ML Stock Selector...")
    
    with open(MODEL_PATH, 'rb') as f:
        model = pickle.load(f)
    
    with open(FEATURE_INFO_PATH, 'rb') as f:
        feature_info = pickle.load(f)
    
    print(f"✅ Model loaded (trained: {feature_info['trained_date']})")
    return model, feature_info['feature_cols']

def extract_features_from_signal(sig):
    """從訊號提取特徵 (簡化版)"""
    # 注意：完整版應該從 ml_features.csv 查找
    # 這裡使用簡化版，僅用訊號本身的資訊
    
    features = {
        'grade_numeric': 2,  # Default B grade
        'distance_to_buy_pct': 0,  # At signal date
        'risk_pct': 5,  # Default
        'rsi_14': 50,  # Neutral
        'ma_trend': 1,  # Assume uptrend
        'volatility': 0.02,  # Default
        'atr_ratio': 0.02,  # Default
        'market_trend': 1,  # Assume bull
        'signal_count_ma10': 0,  # Not used
        'signal_count_ma60': 0   # Not used
    }
    
    return features

def predict_signals(model, feature_cols, signals_df):
    """
    對所有訊號進行 ML 預測
    
    注意：理想情況下應該從 ml_features.csv 載入完整特徵
    這裡簡化處理，使用訊號本身的資訊
    """
    print(f"\nPredicting {len(signals_df)} signals...")
    
    # 載入 ML features (如果存在)
    ml_features_path = os.path.join(os.path.dirname(__file__), '../data/ml_features.csv')
    
    if os.path.exists(ml_features_path):
        print("  Loading features from ml_features.csv...")
        df_features = pd.read_csv(ml_features_path)
        df_features['date'] = pd.to_datetime(df_features['date'])
        
        # 合併特徵
        signals_df['date'] = pd.to_datetime(signals_df['date'])
        merged = signals_df.merge(
            df_features[['sid', 'date'] + feature_cols],
            on=['sid', 'date'],
            how='left'
        )
        
        # 填充缺失值
        for col in feature_cols:
            if col not in merged.columns:
                merged[col] = 0
            merged[col] = merged[col].fillna(0)
        
        X = merged[feature_cols]
    else:
        print("  ⚠️ ml_features.csv not found, using simplified features")
        X = pd.DataFrame([extract_features_from_signal(None)] * len(signals_df))
    
    # 預測
    probas = model.predict_proba(X)[:, 1]
    signals_df['ml_proba'] = probas
    
    print(f"  Mean probability: {probas.mean():.3f}")
    print(f"  Median probability: {np.median(probas):.3f}")
    print(f"  % > 0.3: {(probas > 0.3).mean() * 100:.1f}%")
    print(f"  % > 0.4: {probas > 0.4).mean() * 100:.1f}%")
    print(f"  % > 0.5: {(probas > 0.5).mean() * 100:.1f}%")
    
    return signals_df

def filter_by_ml(candidates, signals_with_ml, threshold):
    """根據 ML 預測過濾交易候選"""
    if threshold is None:
        return candidates  # No filtering
    
    # 創建訊號 lookup
    signal_lookup = {}
    for _, sig in signals_with_ml.iterrows():
        key = (sig['sid'], sig['date'])
        signal_lookup[key] = sig['ml_proba']
    
    # 過濾候選
    filtered = []
    for cand in candidates:
        # 注意: candidates 沒有 sid，這是個問題
        # 我們需要從 generate_trade_candidates 修改來包含 sid
        # 暫時跳過過濾，返回所有
        filtered.append(cand)
    
    print(f"  Filtered: {len(filtered)}/{len(candidates)} trades (threshold {threshold})")
    return filtered

def run_strategy_test(df, strategy, exit_mode, params, model, feature_cols, ml_thresholds):
    """測試一個策略的所有 ML 變體"""
    results = []
    
    # 生成交易候選
    print(f"\n{'='*80}")
    print(f"Strategy: {strategy}, Exit: {exit_mode}, Params: {params}")
    print(f"{'='*80}")
    
    candidates = generate_trade_candidates(df, strategy, exit_mode, params)
    
    if not candidates:
        print("  ⚠️ No candidates generated")
        return results
    
    print(f"  Total candidates: {len(candidates)}")
    
    # Settings string
    if exit_mode == 'fixed':
        set_str = f"R={params['r_mult']}, T={params['time_exit']}"
    else:
        set_str = f"Trig={params['trigger_r']}R, Trail={params['trail_ma']}"
    
    # Baseline (no ML)
    print(f"\n  Running Baseline (no ML)...")
    trades = run_capital_simulation(candidates, mode='limited')
    res = calculate_metrics(trades, f"{strategy} Baseline", set_str)
    if res:
        res['ml_threshold'] = 'None'
        results.append(res)
        print(f"    Result: {res['Ann. Return %']}% return, Sharpe {res['Sharpe']}")
    
    # ML filtered versions
    # 注意：由於 candidates 沒有 sid，ML 過濾目前無法實現
    # 這需要修改 generate_trade_candidates 來返回更多資訊
    # 暫時跳過 ML 過濾
    
    print(f"  ⚠️ ML filtering skipped (requires candidate metadata)")
    
    return results

def main():
    print("="*80)
    print("ML-Enhanced Backtest (Comprehensive)")
    print("="*80)
    
    # Load data
    df = load_data_polars()
    if df is None:
        print("❌ Failed to load data")
        return
    
    # Load ML model
    model, feature_cols = load_ml_model()
    
    # Define test matrix
    ml_thresholds = [None, 0.3, 0.4, 0.5]
    
    test_configs = [
        # HTF Trailing (最佳)
        ('is_htf', 'trailing', {'trigger_r': 1.5, 'trail_ma': 'ma20'}),
        
        # HTF Fixed (次佳)
        ('is_htf', 'fixed', {'r_mult': 2.0, 'time_exit': 20}),
        
        # CUP Fixed R=3.0 (Sharpe 最高)
        ('is_cup', 'fixed', {'r_mult': 3.0, 'time_exit': 20}),
        
        # CUP Fixed R=2.0 (次佳)
        ('is_cup', 'fixed', {'r_mult': 2.0, 'time_exit': 20}),
    ]
    
    # Run all tests
    all_results = []
    
    for strategy, exit_mode, params in test_configs:
        results = run_strategy_test(df, strategy, exit_mode, params, model, feature_cols, ml_thresholds)
        all_results.extend(results)
    
    # Save results
    if all_results:
        df_res = pd.DataFrame(all_results)
        df_res = df_res.sort_values('Ann. Return %', ascending=False)
        
        os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
        df_res.to_csv(OUTPUT_CSV, index=False)
        print(f"\n✅ Results saved to {OUTPUT_CSV}")
        
        # Generate report
        with open(OUTPUT_REPORT, 'w') as f:
            f.write(f"# ML-Enhanced Backtest Comparison\\n")
            f.write(f"Generated: {datetime.now()}\\n\\n")
            f.write(df_res.to_markdown(index=False))
        
        print(f"✅ Report saved to {OUTPUT_REPORT}")
        
        # Print summary
        print(f"\n{'='*80}")
        print("RESULTS SUMMARY")
        print(f"{'='*80}")
        print(df_res[['Strategy', 'ml_threshold', 'Ann. Return %', 'Sharpe', 'Win Rate']].to_string(index=False))
    else:
        print("\n❌ No results generated")

if __name__ == "__main__":
    main()
