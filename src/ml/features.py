import pandas as pd
import numpy as np
import os

def calculate_technical_indicators(group):
    """
    Calculate technical indicators for a stock group.
    
    Args:
        group (pd.DataFrame): DataFrame containing stock data with columns:
            - close, high, low, volume (required)
            - ma20, ma50 (should be pre-calculated)
            - date (for market data lookup)
        
    Returns:
        pd.DataFrame: DataFrame with added indicators
    """
    # Ensure volume exists so downstream features use real data
    if 'volume' not in group.columns:
        raise ValueError("Volume column missing; rerun pattern generation with volume included.")
    group['volume'] = pd.to_numeric(group['volume'], errors='coerce')
    group['volume'] = group['volume'].ffill().bfill()
    if group['volume'].isna().all():
        raise ValueError("Volume data is empty after cleaning.")
    group['volume'] = group['volume'].fillna(group['volume'].median())
    
    # === Volume Features (4) ===
    if len(group) >= 20:
        group['vol_ma20'] = group['volume'].rolling(20).mean()
    else:
        group['vol_ma20'] = group['volume'].mean()
    
    if len(group) >= 50:
        group['vol_ma50'] = group['volume'].rolling(50).mean()
    else:
        group['vol_ma50'] = group['volume'].mean()
    
    # Volume ratios
    group['volume_ratio_ma20'] = group['volume'] / group['vol_ma20']
    group['volume_ratio_ma50'] = group['volume'] / group['vol_ma50']
    
    # Volume surge (>= 1.5x average)
    group['volume_surge'] = (group['volume_ratio_ma20'] >= 1.5).astype(int)
    
    # Volume trend (5-day: current > 5 days ago)
    vol_5d_ago = group['volume'].shift(5)
    group['volume_trend_5d'] = (group['volume'] > vol_5d_ago).astype(int)
    
    # === Momentum Features (4) ===
    # 5-day momentum
    close_5d_ago = group['close'].shift(5)
    group['momentum_5d'] = (group['close'] - close_5d_ago) / close_5d_ago
    
    # 20-day momentum
    close_20d_ago = group['close'].shift(20)
    group['momentum_20d'] = (group['close'] - close_20d_ago) / close_20d_ago
    
    # Price vs MA20
    if 'ma20' in group.columns:
        group['price_vs_ma20'] = (group['close'] - group['ma20']) / group['ma20']
    else:
        group['price_vs_ma20'] = 0.0
    
    # Price vs MA50
    if 'ma50' in group.columns:
        group['price_vs_ma50'] = (group['close'] - group['ma50']) / group['ma50']
    else:
        group['price_vs_ma50'] = 0.0
    
    # === RSI Features (2) ===
    # Real RSI calculation (14-period)
    if len(group) >= 15:
        delta = group['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # Use EMA for RSI (more standard)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        
        rs = avg_gain / avg_loss
        group['rsi_14'] = 100 - (100 / (1 + rs))
        
        # Fill NaN with neutral value
        group['rsi_14'] = group['rsi_14'].fillna(50)
    else:
        group['rsi_14'] = 50
    
    # RSI Divergence (price new high but RSI not hitting new high)
    if len(group) >= 20:
        # Check if price is at 20-day high
        price_high_20 = group['close'].rolling(20).max()
        is_price_high = (group['close'] == price_high_20)
        
        # Check if RSI is at 20-day high
        rsi_high_20 = group['rsi_14'].rolling(20).max()
        is_rsi_high = (group['rsi_14'] == rsi_high_20)
        
        # Divergence: price high but RSI not high
        group['rsi_divergence'] = (is_price_high & ~is_rsi_high).astype(int)
    else:
        group['rsi_divergence'] = 0
    
    # === Market Environment Features (2) ===
    # Load market data (cached for performance)
    market_file = os.path.join(os.path.dirname(__file__), 
                              '../../data/raw/market_data.csv')
    
    if os.path.exists(market_file):
        try:
            # Load and index market data
            market_df = pd.read_csv(market_file)
            market_df['date'] = pd.to_datetime(market_df['date']).dt.strftime('%Y-%m-%d')
            market_dict = market_df.set_index('date').to_dict(orient='index')
            
            # Convert group date to string format for matching
            if group['date'].dtype == 'object':
                date_series = group['date']
            else:
                date_series = pd.to_datetime(group['date']).dt.strftime('%Y-%m-%d')
            
            # Market trend (market close > market MA200)
            def get_market_trend(date_str):
                if date_str in market_dict:
                    close = market_dict[date_str].get('close', 0)
                    ma200 = market_dict[date_str].get('market_ma200', 0)
                    if pd.notna(close) and pd.notna(ma200) and ma200 > 0:
                        return 1 if close > ma200 else 0
                return 1  # Default bullish if no data
            
            group['market_trend'] = date_series.apply(get_market_trend)
            
            # Market volatility (simplified: use 20-day rolling std of market returns)
            # For now, use a placeholder based on market data availability
            def get_market_volatility(date_str):
                if date_str in market_dict:
                    # Simplified: assume volatility is pre-calculated or use default
                    return market_dict[date_str].get('volatility', 0.02)
                return 0.02  # Default volatility
            
            group['market_volatility'] = date_series.apply(get_market_volatility)
            
        except Exception as e:
            # If market data loading fails, use defaults
            group['market_trend'] = 1
            group['market_volatility'] = 0.02
    else:
        # No market data file, use defaults
        group['market_trend'] = 1
        group['market_volatility'] = 0.02
    
    # === MA Trend (existing) ===
    if 'ma20' in group.columns and 'ma50' in group.columns:
        group['ma_trend'] = (group['ma20'] > group['ma50']).astype(int)
    else:
        group['ma_trend'] = 1
    
    # === Volatility (existing) ===
    if len(group) >= 20:
        group['volatility'] = group['close'].pct_change().rolling(20).std()
    else:
        group['volatility'] = 0.02
    
    # === ATR Ratio (existing) ===
    if len(group) >= 14:
        high_low = group['high'] - group['low']
        group['atr_ratio'] = high_low.rolling(14).mean() / group['close']
    else:
        group['atr_ratio'] = 0.02
    
    return group


def extract_ml_features(row, pattern_type):
    """
    Extract ML features from a single row of signal data.
    
    Args:
        row (pd.Series): Row containing signal info and technical indicators
        pattern_type (str): 'htf', 'cup', or 'vcp'
        
    Returns:
        dict: Dictionary of features (24 features total)
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
        
    # 2. Price Action Features (Pattern Quality)
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
    
    # 3. Volume Features (4) - NEW
    features['volume_ratio_ma20'] = row.get('volume_ratio_ma20', 1.0)
    features['volume_ratio_ma50'] = row.get('volume_ratio_ma50', 1.0)
    features['volume_surge'] = row.get('volume_surge', 0)
    features['volume_trend_5d'] = row.get('volume_trend_5d', 1)
    
    # 4. Momentum Features (4) - NEW
    features['momentum_5d'] = row.get('momentum_5d', 0.0)
    features['momentum_20d'] = row.get('momentum_20d', 0.0)
    features['price_vs_ma20'] = row.get('price_vs_ma20', 0.0)
    features['price_vs_ma50'] = row.get('price_vs_ma50', 0.0)
    
    # 5. RSI Features (2) - UPDATED from placeholder
    features['rsi_14'] = row.get('rsi_14', 50)
    features['rsi_divergence'] = row.get('rsi_divergence', 0)
    
    # 6. Technical Indicators (existing)
    features['ma_trend'] = row.get('ma_trend', 1)
    features['volatility'] = row.get('volatility', 0.02)
    features['atr_ratio'] = row.get('atr_ratio', 0.02)
    
    # 7. Market Environment Features (2) - UPDATED from placeholder
    features['market_trend'] = row.get('market_trend', 1)
    features['market_volatility'] = row.get('market_volatility', 0.02)
    
    # 8. Relative Strength (1) - NEW
    features['rs_rating'] = row.get('rs_rating', 50)
    
    # 9. Pattern Specific Features (1) - NEW
    # Consolidation days (CUP/VCP specific, estimated from price stability)
    if pattern_type in ['cup', 'vcp']:
        # Use a heuristic: if available in row, otherwise estimate
        features['consolidation_days'] = row.get('consolidation_days', 10)
    else:
        features['consolidation_days'] = 0
    
    # 10. Signal Counts (2) - Placeholder (TODO: implement)
    features['signal_count_ma10'] = 0
    features['signal_count_ma60'] = 0
    
    return features
