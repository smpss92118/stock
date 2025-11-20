import pandas as pd
import numpy as np

def calculate_technical_indicators(group):
    """
    Calculate technical indicators for a stock group.
    
    Args:
        group (pd.DataFrame): DataFrame containing stock data
        
    Returns:
        pd.DataFrame: DataFrame with added indicators
    """
    # RSI (Simplified for performance, can be expanded)
    group['rsi_14'] = 50 
    
    # MA Trend
    if 'ma20' in group.columns and 'ma50' in group.columns:
        group['ma_trend'] = (group['ma20'] > group['ma50']).astype(int)
    else:
        group['ma_trend'] = 1
    
    # Volatility (20-day rolling std of returns)
    if len(group) >= 20:
        group['volatility'] = group['close'].pct_change().rolling(20).std()
    else:
        group['volatility'] = 0.02
    
    # ATR Ratio (Simplified)
    if len(group) >= 14:
        high_low = group['high'] - group['low']
        group['atr_ratio'] = high_low.rolling(14).mean() / group['close']
    else:
        group['atr_ratio'] = 0.02
    
    # Market Trend (Placeholder, assume bullish for now)
    group['market_trend'] = 1
    
    return group

def extract_ml_features(row, pattern_type):
    """
    Extract ML features from a single row of signal data.
    
    Args:
        row (pd.Series): Row containing signal info and technical indicators
        pattern_type (str): 'htf', 'cup', or 'vcp'
        
    Returns:
        dict: Dictionary of features
    """
    features = {}
    
    # 1. Pattern Type & Grade
    features['pattern_type'] = pattern_type.upper()
    
    if pattern_type == 'htf':
        features['buy_price'] = row.get('htf_buy_price', 0)
        features['stop_price'] = row.get('htf_stop_price', 0)
        grade = row.get('htf_grade', 'C')
        grade_map = {'A': 3, 'B': 2, 'C': 1}
        features['grade_numeric'] = grade_map.get(grade, 1)
    elif pattern_type == 'cup':
        features['buy_price'] = row.get('cup_buy_price', 0)
        features['stop_price'] = row.get('cup_stop_price', 0)
        features['grade_numeric'] = 2  # Default to B for CUP
    elif pattern_type == 'vcp':
        features['buy_price'] = row.get('vcp_buy_price', 0)
        features['stop_price'] = row.get('vcp_stop_price', 0)
        features['grade_numeric'] = 2  # Default to B for VCP
        
    # 2. Price Action Features
    current_price = row['close']
    
    # Distance to Buy Price (%)
    if features['buy_price'] > 0:
        features['distance_to_buy_pct'] = (features['buy_price'] - current_price) / current_price * 100
    else:
        features['distance_to_buy_pct'] = 0
        
    # Risk Percentage (%)
    if features['buy_price'] > 0 and features['stop_price'] > 0:
        features['risk_pct'] = (features['buy_price'] - features['stop_price']) / features['buy_price'] * 100
    else:
        features['risk_pct'] = 0
        
    # 3. Technical Indicators (from calculate_technical_indicators)
    features['rsi_14'] = row.get('rsi_14', 50)
    features['ma_trend'] = row.get('ma_trend', 1)
    features['volatility'] = row.get('volatility', 0.02)
    features['atr_ratio'] = row.get('atr_ratio', 0.02)
    features['market_trend'] = row.get('market_trend', 1)
    
    # 4. Signal Counts (Placeholders)
    features['signal_count_ma10'] = 0
    features['signal_count_ma60'] = 0
    
    return features
