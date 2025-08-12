# -*- coding: utf-8 -*-
"""
Configuration settings for the Taiwan Stock Screener.
"""

# 粗篩條件 (Coarse Screening Criteria)
MIN_PRICE = 20.0
MIN_50D_TURNOVER = 3e8  # 3 億 (300 million)
DIST_TO_52W_MAX = 0.10  # 距 52 週高點不超過 10% (Within 10% of 52-week high)
RS_PERCENTILE_MIN = 80  # RS 百分位至少 80 (Relative Strength percentile minimum 80)

# 缺口判定與形態參數 (Gap and Pattern Parameters)
GAP_PCT_MIN = 0.035           # 缺口幅度門檻 (Gap percentage threshold)
VOLUME_BOOST = 1.8            # 突破時的放量倍數 vs 50日均量 (Volume boost factor vs 50-day average)
EMA_SLOPE_LOOKBACK = 5        # 均線斜率計算回看天數 (Lookback period for EMA slope)
RS_LOOKBACK = 252             # RS 計算回看天數 (Lookback period for Relative Strength)
RS_LEAD_WINDOW = 60           # RS 領先創高觀察天數 (Window for RS leading new high)

# 平台/杯柄形態參數 (Platform/Cup-with-Handle Pattern Parameters)
PLATFORM_MIN_DAYS = 30        # 平台最小時長 (Minimum days for platform base)
PLATFORM_MAX_DAYS = 150       # 平台最大時長 (Maximum days for platform base)
PLATFORM_MAX_DEPTH = 0.33     # 平台最大回檔深度 (Maximum depth for platform base)

# VCP 形態參數 (Volatility Contraction Pattern - VCP Parameters)
VCP_ATR_WINDOW = 20           # VCP 中 ATR 計算週期 (ATR window for VCP)
VCP_WINDOWS = [(120, 90), (90, 60), (60, 30), (30, 0)]  # VCP 收斂觀察視窗 (Contraction windows for VCP)
VCP_RANGE_DECAY = 0.75        # VCP 振幅收斂比例 (Range decay factor for VCP)
VCP_ATR_DECAY = 0.7           # VCP ATR 下降比例 (ATR decay factor for VCP)

# 首次回測參數 (First Pullback Parameters)
FIRST_PULLBACK_LOOKBACK = 25  # 突破後首次回測觀察天數 (Lookback window for first pullback after breakout)
