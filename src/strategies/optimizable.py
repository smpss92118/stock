"""
Optimizable Strategy Wrappers

提供可調參數的策略檢測函數，用於超參數優化
不修改原始策略函數，保持系統穩定性
"""

from .cup import detect_cup as _original_cup
from .htf import detect_htf as _original_htf
from .vcp import detect_vcp as _original_vcp

# === HTF Optimizable Wrapper ===

def detect_htf_optimizable(window, rs_rating=0.0, params=None):
    """
    HTF detector with customizable parameters
    
    Args:
        window: DataFrame with price/volume data
        rs_rating: RS Rating score
        params: Dict with optional parameters:
            - min_up_ratio: float (default 0.6)
            - max_pullback: float (default 0.25)
            - min_flag_days: int (default 3)
            - max_flag_days: int (default 12)
    
    Returns:
        (is_htf, buy_price, stop_price, grade)
    """
    if params is None:
        params = {}
    
    # Apply RS threshold filter BEFORE calling original function
    rs_threshold = params.get('rs_rating_threshold', 0)
    if rs_rating < rs_threshold:
        return False, None, None, None
    
    return _original_htf(
        window,
        rs_rating=rs_rating,
        min_up_ratio=params.get('min_up_ratio', 0.6),
        max_pullback=params.get('max_pullback', 0.25),
        min_flag_days=params.get('min_flag_days', 3),
        max_flag_days=params.get('max_flag_days', 12)
    )


# === CUP Optimizable Wrapper ===

def detect_cup_optimizable(window, ma_info, rs_rating=0.0, params=None):
    """
    CUP detector with customizable parameters
    
    Args:
        window: DataFrame with price/volume data
        ma_info: Dict with MA values
        rs_rating: RS Rating score
        params: Dict with optional parameters:
            - min_depth: float (default 0.12)
            - max_depth: float (default 0.33)
            - handle_max_depth: float (default 0.15)
    
    Returns:
        (is_cup, buy_price, stop_price)
    """
    if params is None:
        params = {}
    
    # Apply RS threshold filter
    rs_threshold = params.get('rs_rating_threshold', 0)
    if rs_rating < rs_threshold:
        return False, None, None
    
    return _original_cup(
        window,
        ma_info,
        rs_rating=rs_rating,
        min_depth=params.get('min_depth', 0.12),
        max_depth=params.get('max_depth', 0.33),
        handle_max_depth=params.get('handle_max_depth', 0.15)
    )


# === VCP Optimizable Wrapper ===

def detect_vcp_optimizable(window, vol_ma50_val, price_ma50_val, 
                          rs_rating=0.0, high_52w=None, params=None):
    """
    VCP detector with customizable parameters
    
    Args:
        window: DataFrame with price/volume data
        vol_ma50_val: Volume MA50 value
        price_ma50_val: Price MA50 value
        rs_rating: RS Rating score
        high_52w: 52-week high
        params: Dict with optional parameters:
            - zigzag_threshold: float (default 0.05)
            - min_up_ratio: float (default 0.5)
            - vol_dry_up_ratio: float (default 0.5)
    
    Returns:
        (is_vcp, buy_price, stop_price)
    """
    if params is None:
        params = {}
    
    # Apply RS threshold filter
    rs_threshold = params.get('rs_rating_threshold', 0)
    if rs_rating < rs_threshold:
        return False, None, None
    
    return _original_vcp(
        window,
        vol_ma50_val,
        price_ma50_val,
        rs_rating=rs_rating,
        high_52w=high_52w,
        zigzag_threshold=params.get('zigzag_threshold', 0.05),
        min_up_ratio=params.get('min_up_ratio', 0.5),
        vol_dry_up_ratio=params.get('vol_dry_up_ratio', 0.5)
    )
