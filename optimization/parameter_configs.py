"""
超參數網格搜索配置

定義 CUP、HTF、VCP 策略的參數網格空間
"""

# === HTF (High Tight Flag) 參數網格 ===
# 優先級: 1 (最簡單，先測試)
# 組合數: 4 × 3 × 3 = 36
HTF_PARAM_GRID = {
    'min_up_ratio': [0.60, 0.80, 1.00, 1.20],        # 上漲幅度要求
    'max_pullback': [0.15, 0.20, 0.25],              # 回調最大值
    'rs_rating_threshold': [0, 70, 80],              # RS Rating 門檻
    # 固定參數（不優化）
    'min_flag_days': 3,
    'max_flag_days': 12,
}

# === CUP (Cup with Handle) 參數網格 ===
# 優先級: 2
# 組合數: 4 × 3 × 3 × 3 = 108
CUP_PARAM_GRID = {
    'rs_rating_threshold': [0, 70, 80, 90],          # RS Rating 門檻
    'min_depth': [0.10, 0.12, 0.15],                 # 杯底最小深度
    'max_depth': [0.28, 0.33, 0.38],                 # 杯底最大深度
    'handle_max_depth': [0.10, 0.15, 0.20],          # 手柄最大深度
    # 固定參數（不優化）
    'handle_length_ratio': 0.2,
    'min_handle_low_ratio': 0.5,
    'price_vs_low52': 1.25,  # 用戶改為 1.25, 1.35, 1.45，但我們先用 1.25 作為固定值
}

# === VCP (Volatility Contraction Pattern) 參數網格 ===
# 優先級: 3
# 組合數: 3 × 3 × 3 = 27
VCP_PARAM_GRID = {
    'zigzag_threshold': [0.04, 0.05, 0.07],          # ZigZag 轉折閾值
    'min_up_ratio': [0.40, 0.50, 0.60],              # 上漲幅度要求
    'vol_dry_up_ratio': [0.45, 0.50, 0.60],          # 成交量乾涸比例
    # 固定參數（不優化）
    'rs_rating_threshold': 0,
    'min_window_high_idx': 10,
    'pivot_proximity': 0.95,
    'min_contractions': 2,
    'recent_vol_window': 5,
}

# === 評估指標權重（根據用戶修改）===
METRIC_WEIGHTS = {
    'ann_return': 0.40,      # 年化報酬率
    'sharpe': 0.40,          # 夏普比率  
    'trade_count': 0.15,     # 交易次數
    'max_drawdown': 0.05,    # 最大回撤
}

# === 輸出配置 ===
OUTPUT_CONFIG = {
    'top_n_return': 3,       # 前 N 名（按年化報酬）
    'top_n_sharpe': 3,       # 前 N 名（按 Sharpe）
    'min_trades': 10,        # 最小交易次數（避免樣本過小）
}
