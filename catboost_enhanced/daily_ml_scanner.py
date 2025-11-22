"""
Daily ML Scanner - 生成每日機器學習推薦清單

根據 CatBoost 全局模型的預測，為每日訊號生成推薦清單和性能說明。

功能:
1. 載入今日檢測到的訊號 (pattern detection results)
2. 用 CatBoost 模型預測每個訊號的品質 (A/B/C/D)
3. 從 backtest 結果中提取該組合的歷史績效
4. 顯示訊號的特徵重要性解釋
5. 生成可讀的日常推薦報告 (HTML + CSV)

推薦清單結構:
- 股票代碼, 訊號日期, Pattern, Exit Mode
- 預測品質 (A/B/C/D), 預測信心度 (概率)
- 該組合的歷史年化報酬%, 歷史勝率%, Sharpe 值
- Top 5 特徵對該訊號的影響說明

Usage:
    python catboost_enhanced/daily_ml_scanner.py [--output-dir ./output]

Output:
    catboost_enhanced/results/daily_scan_[YYYY-MM-DD].csv
    catboost_enhanced/results/daily_scan_[YYYY-MM-DD].html
"""

import os
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, date
import pickle
from tqdm import tqdm

# 控制 tqdm 進度條寬度
tqdm.pandas(desc="processing")

# Add parent directory to path (to access stock/ and its subdirectories)
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.utils.logger import setup_logger
from ml_enhanced.scripts.prepare_ml_data import load_data_polars
from src.data.institutional import load_institutional_raw, compute_institutional_features
from src.ml.features import calculate_technical_indicators
from ml_enhanced.scripts.prepare_ml_data import apply_group_zscore

logger = setup_logger('daily_ml_scanner')

# 配置
CATBOOST_MODEL_PATH = Path(__file__).resolve().parents[0] / 'models' / 'catboost_global.cbm'
FEATURE_INFO_PATH = Path(__file__).resolve().parents[0] / 'models' / 'catboost_feature_info.pkl'
BACKTEST_RESULTS_PATH = Path(__file__).resolve().parents[0] / 'results' / 'backtest_by_group.csv'
FEATURE_IMPORTANCE_PATH = Path(__file__).resolve().parents[0] / 'results' / 'feature_importance.csv'

RESULTS_DIR = Path(__file__).resolve().parents[0] / 'results'

try:
    from catboost import CatBoostClassifier
except ImportError:
    logger.error("❌ CatBoost 未安裝")
    sys.exit(1)


def load_model_and_features():
    """載入 CatBoost 模型和特徵信息"""
    logger.info("載入 CatBoost 模型...")

    if not CATBOOST_MODEL_PATH.exists():
        logger.error(f"❌ 模型不存在: {CATBOOST_MODEL_PATH}")
        return None, None

    try:
        model = CatBoostClassifier()
        model.load_model(str(CATBOOST_MODEL_PATH))
        logger.info("✓ 模型載入成功")
    except Exception as e:
        logger.error(f"❌ 模型載入失敗: {e}")
        return None, None

    if not FEATURE_INFO_PATH.exists():
        logger.error(f"❌ 特徵信息不存在: {FEATURE_INFO_PATH}")
        return model, None

    try:
        with open(FEATURE_INFO_PATH, 'rb') as f:
            feature_info = pickle.load(f)
        logger.info(f"✓ 特徵信息載入成功 ({len(feature_info.get('feature_cols', []))} 個特徵)")
        return model, feature_info
    except Exception as e:
        logger.error(f"❌ 特徵信息載入失敗: {e}")
        return model, None


def load_feature_importance():
    """載入特徵重要性排名"""
    if not FEATURE_IMPORTANCE_PATH.exists():
        logger.warning(f"⚠️ 特徵重要性檔案不存在: {FEATURE_IMPORTANCE_PATH}")
        return {}

    try:
        df = pd.read_csv(FEATURE_IMPORTANCE_PATH)
        # 轉換為字典: feature -> importance score
        importance_dict = dict(zip(df['feature'], df['importance']))
        return importance_dict
    except Exception as e:
        logger.warning(f"⚠️ 無法載入特徵重要性: {e}")
        return {}


def load_backtest_performance():
    """載入 backtest 性能結果 (按 pattern×exit_mode 分組)"""
    if not BACKTEST_RESULTS_PATH.exists():
        logger.warning(f"⚠️ Backtest 結果不存在: {BACKTEST_RESULTS_PATH}")
        return None

    try:
        df = pd.read_csv(BACKTEST_RESULTS_PATH)
        logger.info(f"✓ Backtest 結果載入: {len(df)} 個組合")
        return df
    except Exception as e:
        logger.warning(f"⚠️ 無法載入 backtest 結果: {e}")
        return None


def get_today_signals():
    """
    載入今日檢測到的訊號，包含進場和停損價位

    預期結構:
    - sid: 股票代碼
    - date: 訊號日期
    - is_cup, is_htf, is_vcp: Pattern 標誌
    - cup_buy_price, htf_buy_price, vcp_buy_price: 進場價位
    - cup_stop_price, htf_stop_price, vcp_stop_price: 停損價位
    - 其他特徵列
    """
    logger.info("載入今日訊號...")

    try:
        # 載入市場資料
        df_polars = load_data_polars()
        if df_polars is None:
            logger.error("❌ 無法載入市場資料")
            return None

        df = df_polars.to_pandas()
        df['date'] = pd.to_datetime(df['date'])

        # 找出最新日期（今日）
        latest_date = df['date'].max()
        logger.info(f"  最新日期: {latest_date.strftime('%Y-%m-%d')}")

        # 只保留最新日期的資料
        df_today = df[df['date'] == latest_date].copy()
        logger.info(f"  今日資料筆數: {len(df_today)}")

        # 篩選今日訊號 (有任何 pattern 標誌)
        pattern_cols = ['is_cup', 'is_htf', 'is_vcp']

        # 檢查哪些 pattern 列存在
        available_patterns = [c for c in pattern_cols if c in df_today.columns]

        if not available_patterns:
            logger.warning("⚠️ 未找到訊號列")
            return pd.DataFrame()

        # 過濾有訊號的行 (任何 pattern 為 True)
        has_signal = df_today[available_patterns].any(axis=1)
        today_signals = df_today[has_signal].copy()

        if len(today_signals) == 0:
            logger.info("  今日無訊號")
            return pd.DataFrame()

        logger.info(f"✓ 掃描到 {len(today_signals)} 個訊號")
        logger.info(f"  (將進行 CatBoost 評分和過濾)")

        # 標準化訊號資料
        today_signals['sid'] = today_signals['sid'].astype(str)
        today_signals['date'] = pd.to_datetime(today_signals['date'])
        today_signals['current_price'] = today_signals['close']

        # 提取進場和停損價位信息
        # 根據哪個 pattern 為 True，取對應的買入價和停損價
        today_signals['buy_price'] = np.nan
        today_signals['stop_price'] = np.nan
        today_signals['pattern_type'] = 'unknown'

        if 'is_cup' in available_patterns:
            cup_mask = today_signals['is_cup'] == True
            if 'cup_buy_price' in today_signals.columns:
                today_signals.loc[cup_mask, 'buy_price'] = today_signals.loc[cup_mask, 'cup_buy_price']
                today_signals.loc[cup_mask, 'stop_price'] = today_signals.loc[cup_mask, 'cup_stop_price']
                today_signals.loc[cup_mask, 'pattern_type'] = 'cup'

        if 'is_htf' in available_patterns:
            htf_mask = today_signals['is_htf'] == True
            if 'htf_buy_price' in today_signals.columns:
                today_signals.loc[htf_mask, 'buy_price'] = today_signals.loc[htf_mask, 'htf_buy_price']
                today_signals.loc[htf_mask, 'stop_price'] = today_signals.loc[htf_mask, 'htf_stop_price']
                today_signals.loc[htf_mask, 'pattern_type'] = 'htf'

        if 'is_vcp' in available_patterns:
            vcp_mask = today_signals['is_vcp'] == True
            if 'vcp_buy_price' in today_signals.columns:
                today_signals.loc[vcp_mask, 'buy_price'] = today_signals.loc[vcp_mask, 'vcp_buy_price']
                today_signals.loc[vcp_mask, 'stop_price'] = today_signals.loc[vcp_mask, 'vcp_stop_price']
                today_signals.loc[vcp_mask, 'pattern_type'] = 'vcp'

        # 計算距離%
        today_signals['distance_pct'] = (today_signals['buy_price'] - today_signals['current_price']) / today_signals['buy_price'] * 100
        today_signals['status'] = today_signals.apply(
            lambda row: "已突破" if row['current_price'] >= row['buy_price'] else "等待突破",
            axis=1
        )

        return today_signals

    except Exception as e:
        logger.error(f"❌ 無法載入訊號: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def prepare_features_for_model(signals_df):
    """
    準備訊號特徵以供模型預測

    需要確保特徵與訓練時一致 (z-score 標準化等)
    """
    logger.info("準備訊號特徵...")

    if signals_df is None or signals_df.empty:
        return None

    try:
        logger.info("  [1/4] 載入機構流特徵...")
        # 載入機構流特徵
        inst_raw = load_institutional_raw()
        if inst_raw is not None and not inst_raw.empty:
            inst_feat_df = compute_institutional_features(inst_raw)
            inst_feat_df['sid'] = inst_feat_df['sid'].astype(str)
            inst_feat_df['date'] = pd.to_datetime(inst_feat_df['date'])
            signals_df = signals_df.merge(inst_feat_df, on=['sid', 'date'], how='left')
        else:
            logger.warning("⚠️ 機構流資料缺失，使用零填補")

        logger.info("  [2/4] 計算技術指標...")
        # 計算技術指標 (使用 tqdm 進度條)
        # 保留 sid 列以便後續使用
        signals_df = signals_df.groupby('sid', group_keys=False).apply(
            calculate_technical_indicators, include_groups=False
        ).reset_index(drop=True)
        # 確保 sid 是列而不是 index
        if 'sid' not in signals_df.columns and signals_df.index.name == 'sid':
            signals_df = signals_df.reset_index()

        logger.info("  [3/4] 添加機構流比率特徵...")
        # 添加缺失的機構流比率特徵
        volume_safe = signals_df['volume'].replace(0, np.nan)
        if 'foreign_net_lag1' in signals_df.columns:
            signals_df['foreign_net_to_vol_lag1'] = signals_df['foreign_net_lag1'] / volume_safe
        else:
            signals_df['foreign_net_to_vol_lag1'] = 0.0

        if 'total_net_lag1' in signals_df.columns:
            signals_df['total_net_to_vol_lag1'] = signals_df['total_net_lag1'] / volume_safe
        else:
            signals_df['total_net_to_vol_lag1'] = 0.0

        logger.info("  [4/4] 確認分類特徵...")
        # pattern_type 和 exit_mode 應該已經在 get_today_signals() 中設置
        # 這裡只確保它們存在
        if 'pattern_type' not in signals_df.columns:
            signals_df['pattern_type'] = 'unknown'

        if 'exit_mode' not in signals_df.columns:
            signals_df['exit_mode'] = 'fixed_r2_t20'

        # 填補 NaN 值為 0
        signals_df = signals_df.fillna(0)

        logger.info("✓ 特徵準備完成")
        return signals_df

    except Exception as e:
        logger.error(f"❌ 特徵準備失敗: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def predict_signal_quality(model, feature_info, signals_df):
    """
    用 CatBoost 模型預測每個訊號的品質

    返回: signals_df with columns:
    - pred_label: 0-3 (D/C/B/A)
    - pred_proba_A, pred_proba_B, pred_proba_C, pred_proba_D: 各類別概率
    """
    logger.info("預測訊號品質...")

    if model is None or feature_info is None or signals_df is None or signals_df.empty:
        logger.error("❌ 模型或資料缺失")
        return None

    try:
        feature_cols = feature_info.get('feature_cols', [])
        cat_features = feature_info.get('cat_features', [])

        # 重建完整特徵列表
        full_feature_cols = feature_cols + cat_features

        # 檢查特徵
        missing = [c for c in full_feature_cols if c not in signals_df.columns]
        if missing:
            logger.warning(f"⚠️ 缺失特徵: {missing}")

        # 篩選可用特徵 (必須按照模型期望的順序)
        available_features = [c for c in full_feature_cols if c in signals_df.columns]
        X = signals_df[available_features].copy()

        # 填補 NaN 值
        X = X.fillna(0)

        # 預測
        try:
            y_pred = model.predict(X)
            y_pred_proba = model.predict_proba(X)
        except Exception as pred_error:
            logger.error(f"❌ CatBoost 預測內部錯誤: {pred_error}")
            logger.warning(f"  使用特徵數: {X.shape[1]}, 期望特徵數: {len(full_feature_cols)}")
            logger.warning(f"  可用特徵: {available_features}")
            raise

        signals_df['pred_label'] = y_pred
        label_map = {0: 'D', 1: 'C', 2: 'B', 3: 'A'}
        signals_df['pred_grade'] = signals_df['pred_label'].map(label_map)

        # 添加概率列
        for i in range(4):
            grade = label_map[i]
            signals_df[f'pred_proba_{grade}'] = y_pred_proba[:, i]

        # 統計
        logger.info("  預測標籤分佈:")
        for label_val in range(4):
            count = (y_pred == label_val).sum()
            pct = count / len(y_pred) * 100 if len(y_pred) > 0 else 0
            logger.info(f"    {label_map[label_val]}: {count} ({pct:.1f}%)")

        return signals_df

    except Exception as e:
        logger.error(f"❌ 預測失敗: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return None


def enrich_with_backtest_performance(signals_df, backtest_df):
    """
    將 backtest 性能數據加入訊號列表

    根據 pattern 和 exit_mode 匹配，添加歷史績效指標
    """
    logger.info("添加 Backtest 性能數據...")

    if signals_df is None or signals_df.empty or backtest_df is None or backtest_df.empty:
        logger.warning("⚠️ 訊號或 backtest 結果缺失")
        return signals_df

    # 確保 pattern_type 和 exit_mode 列存在
    if 'pattern_type' not in signals_df.columns or 'exit_mode' not in signals_df.columns:
        logger.warning("⚠️ 訊號缺少 pattern_type 或 exit_mode 列")
        return signals_df

    # 預期的 backtest 列
    perf_cols = ['Ann. Return %', 'Win Rate', 'Sharpe', 'Max Drawdown %']
    available_perf_cols = [c for c in perf_cols if c in backtest_df.columns]

    # 合併
    try:
        signals_df = signals_df.merge(
            backtest_df[['pattern', 'exit_mode'] + available_perf_cols],
            left_on=['pattern_type', 'exit_mode'],
            right_on=['pattern', 'exit_mode'],
            how='left'
        )

        logger.info("✓ Backtest 性能數據已添加")
        return signals_df

    except Exception as e:
        logger.warning(f"⚠️ 無法合併 backtest 數據: {e}")
        return signals_df


def get_feature_explanation(signal_row, feature_importance, model, feature_info, top_n=5):
    """
    為單個訊號生成特徵重要性解釋

    返回: list of (feature_name, importance_score, direction) 的 top N
    """
    if not feature_importance or model is None:
        return []

    try:
        # 取模型的 top 特徵
        model_importance = model.get_feature_importance()
        feature_cols = feature_info.get('feature_cols', [])
        cat_features = feature_info.get('cat_features', [])
        all_features = feature_cols + cat_features

        # 配對特徵名稱和重要性
        feature_importance_dict = dict(zip(all_features, model_importance))

        # 排序並取 top N
        top_features = sorted(
            feature_importance_dict.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_n]

        explanations = []
        for feature_name, importance_score in top_features:
            if feature_name in signal_row.index:
                value = signal_row[feature_name]
                direction = "↑" if value > 0 else "↓"
                explanations.append((feature_name, importance_score, direction, value))

        return explanations

    except Exception as e:
        logger.warning(f"⚠️ 無法生成特徵說明: {e}")
        return []


def load_weekly_signals():
    """載入過去一週的推薦訊號清單"""
    try:
        from datetime import timedelta
        today = date.today()
        week_ago = today - timedelta(days=7)

        signals = []
        for i in range(7):
            check_date = week_ago + timedelta(days=i)
            date_str = check_date.strftime('%Y-%m-%d')
            # 載入這天掃描生成的訊號
            md_file = RESULTS_DIR / f'catboost_daily_summary_{date_str}.md'

            # 如果 MD 檔案存在，嘗試解析；否則尋找原始 CSV
            if md_file.exists():
                # 從 MD 報告中提取推薦訊號信息
                pass  # 簡化：直接使用 CSV

            csv_file = RESULTS_DIR / f'daily_scan_{date_str}.csv'
            if csv_file.exists():
                df = pd.read_csv(csv_file)
                df['scan_date'] = date_str
                signals.append(df)

        if signals:
            return pd.concat(signals, ignore_index=True)
        return pd.DataFrame()
    except Exception as e:
        logger.warning(f"⚠️ 無法載入一週訊號: {e}")
        return pd.DataFrame()


def get_top_strategies(backtest_df, n=3):
    """從 backtest 結果中取出 Top N 策略

    返回: [
        {'name': 'HTF fixed_r2_t20', 'return': 208.2, 'sharpe': 3.15, 'win_rate': 69.3,
         'mdd': 24.0, 'avg_holding': 11.5, 'max_wins': 34, 'max_losses': 23},
        ...
    ]
    """
    if backtest_df is None or backtest_df.empty:
        return []

    try:
        # 按年化報酬排序
        top_by_return = backtest_df.nlargest(n, 'Ann. Return %')
        strategies = []

        for _, row in top_by_return.iterrows():
            pattern = row.get('pattern', 'N/A')
            exit_mode = row.get('exit_mode', 'N/A')
            ret = row.get('Ann. Return %', 0)
            sharpe = row.get('Sharpe', 0)
            win_rate = row.get('Win Rate', 0)
            mdd = abs(float(row.get('Max DD %', row.get('Max Drawdown %', 0))))
            avg_holding = row.get('Avg Holding Days', 0)
            max_wins = row.get('Max Win Streak', 0)
            max_losses = row.get('Max Loss Streak', 0)

            strategies.append({
                'name': f"{pattern.upper()} {exit_mode}",
                'return': ret,
                'sharpe': sharpe,
                'win_rate': win_rate,
                'mdd': mdd,
                'avg_holding': avg_holding,
                'max_wins': max_wins,
                'max_losses': max_losses
            })

        return strategies
    except Exception as e:
        logger.warning(f"⚠️ 無法獲取 Top 策略: {e}")
        return []


def generate_recommendation_report(signals_df, backtest_df):
    """
    生成日常推薦報告 (Markdown 格式)

    包含:
    - 本日訊號統計 (當天檢測到的訊號)
    - 本日推薦清單 (當天的推薦訊號詳細列表)
    - 過去一週推薦清單 (近 7 天的推薦訊號清單)
    - Top 3 策略統計
    """
    logger.info("生成推薦報告...")

    # 即使無訊號也生成報告
    try:
        output_dir = RESULTS_DIR
        os.makedirs(output_dir, exist_ok=True)

        today_str = date.today().strftime('%Y-%m-%d')

        # 生成 Markdown 報告
        report = f"""# CatBoost Enhanced 股票訊號報告
**掃描日期**: {today_str}
**生成時間**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 📊 本日訊號統計

"""

        if signals_df is None or signals_df.empty:
            report += "- **總訊號數**: 0\n\n"
            report += "**本日無符合條件的型態訊號。**\n\n"
        else:
            report += f"- **總訊號數**: {len(signals_df)}\n\n"
        
        report += "\n---\n\n"

        # 本日推薦清單 (只在有訊號時顯示)
        if signals_df is not None and not signals_df.empty:
            # 篩選推薦的訊號 (A/B 級)
            recommended = signals_df[signals_df['pred_label'] >= 2].copy()
            
            report += "## 📋 本日推薦清單 (A/B 級、未突破)\n\n"

            # 篩選: 推薦等級 (A/B) + 狀態為"等待突破"
            recommended_not_broken = recommended[recommended['status'] == '等待突破'].copy()

            if len(recommended_not_broken) == 0:
                report += "本日無符合條件的推薦訊號 (未突破)。\n"
            else:
                # 按距離% 排序 (優先顯示離買入價近的)
                recommended_sorted = recommended_not_broken.sort_values('distance_pct')

                # 按等級顯示
                for grade in ['A', 'B']:
                    grade_signals = recommended_sorted[recommended_sorted['pred_grade'] == grade].copy()
                    if len(grade_signals) == 0:
                        continue

                    report += f"### {grade} 級推薦 ({len(grade_signals)} 個)\n\n"

                    # 表格頭
                    report += "| 代碼 | Pattern | 當前價 | 買入價 | 停損價 | 距離% | 狀態 | 年化報酬 | 勝率 | Sharpe | MDD | 連勝 | 連敗 |\n"
                    report += "|------|---------|--------|--------|--------|-------|------|---------|------|--------|-----|-------|-------|\n"

                    for _, row in grade_signals.head(50).iterrows():  # 限制每級最多 50 個
                        sid = str(row['sid']) if 'sid' in row and pd.notna(row['sid']) else 'N/A'
                        pattern = str(row.get('pattern_type', 'N/A')).upper()
                        current = float(row.get('current_price', 0))
                        buy = float(row.get('buy_price', 0))
                        stop = float(row.get('stop_price', 0))
                        dist = float(row.get('distance_pct', 0))
                        status = str(row.get('status', 'N/A'))

                        line = f"| {sid} | {pattern} | {current:.2f} | {buy:.2f} | {stop:.2f} | {dist:.1f}% | {status}"

                        # 年化報酬
                        if 'Ann. Return %' in row and pd.notna(row['Ann. Return %']):
                            ret = float(row['Ann. Return %'])
                            line += f" | {ret:.1f}%"
                        else:
                            line += " | N/A"

                        # 勝率
                        if 'Win Rate' in row and pd.notna(row['Win Rate']):
                            win = float(row['Win Rate'])
                            line += f" | {win:.1f}%"
                        else:
                            line += " | N/A"

                        # Sharpe
                        if 'Sharpe' in row and pd.notna(row['Sharpe']):
                            sharpe = float(row['Sharpe'])
                            line += f" | {sharpe:.2f}"
                        else:
                            line += " | N/A"

                        # Max Drawdown
                        if 'Max Drawdown %' in row and pd.notna(row['Max Drawdown %']):
                            mdd = float(row['Max Drawdown %'])
                            line += f" | {mdd:.1f}%"
                        else:
                            line += " | N/A"

                        # 連勝次數
                        if 'Max Win Streak' in row and pd.notna(row['Max Win Streak']):
                            wins = int(row['Max Win Streak'])
                            line += f" | {wins}"
                        else:
                            line += " | N/A"

                        # 連敗次數
                        if 'Max Loss Streak' in row and pd.notna(row['Max Loss Streak']):
                            losses = int(row['Max Loss Streak'])
                            line += f" | {losses}"
                        else:
                            line += " | N/A"

                        line += " |"
                        report += line + "\n"

                    report += "\n"

        report += "---\n\n"

        # 過去一週推薦清單 (還沒突破的訊號)
        report += "## 📅 過去一週推薦清單 (未突破)\n\n"

        # 載入過去一週的訊號，但需要檢查目前的狀態
        # 只顯示在過去 7 天出現且到現在還沒突破的訊號
        try:
            weekly_signals = load_weekly_signals()
            if weekly_signals.empty or len(weekly_signals) == 0:
                report += "過去一週無推薦訊號紀錄。\n"
            else:
                # 篩選 A/B 級
                weekly_recommended = weekly_signals[weekly_signals['pred_label'] >= 2].copy()

                if len(weekly_recommended) == 0:
                    report += "過去一週無 A/B 級推薦訊號。\n"
                else:
                    # 重新載入最新的市場數據，檢查這些訊號現在是否還沒突破
                    # 為了簡化，我們假設訊號資料中已經有最新的狀態
                    weekly_not_broken = weekly_recommended[weekly_recommended.get('status', '') == '等待突破'].copy()

                    if len(weekly_not_broken) == 0:
                        report += "過去一週的推薦訊號都已突破或過期。\n"
                    else:
                        # 按日期分組顯示推薦清單
                        for scan_date in sorted(weekly_not_broken['scan_date'].unique()):
                            day_signals = weekly_not_broken[weekly_not_broken['scan_date'] == scan_date]
                            report += f"### {scan_date} ({len(day_signals)} 個)\n\n"

                            # 表格頭
                            report += "| 代碼 | Pattern | 當前價 | 買入價 | 停損價 | 距離% | 級別 | 年化報酬 | Sharpe |\n"
                            report += "|------|---------|--------|--------|--------|-------|------|---------|--------|\n"

                            for _, row in day_signals.iterrows():
                                sid = str(row.get('sid', 'N/A'))
                                pattern = str(row.get('pattern_type', 'N/A')).upper()
                                current = float(row.get('current_price', 0)) if 'current_price' in row else 0
                                buy = float(row.get('buy_price', 0)) if 'buy_price' in row else 0
                                stop = float(row.get('stop_price', 0)) if 'stop_price' in row else 0
                                dist = float(row.get('distance_pct', 0)) if 'distance_pct' in row else 0
                                grade = str(row.get('pred_grade', 'N/A'))

                                line = f"| {sid} | {pattern} | {current:.2f} | {buy:.2f} | {stop:.2f} | {dist:.1f}% | {grade}"

                                # 年化報酬
                                if 'Ann. Return %' in row and pd.notna(row['Ann. Return %']):
                                    ret = float(row['Ann. Return %'])
                                    line += f" | {ret:.1f}%"
                                else:
                                    line += " | N/A"

                                # Sharpe
                                if 'Sharpe' in row and pd.notna(row['Sharpe']):
                                    sharpe = float(row['Sharpe'])
                                    line += f" | {sharpe:.2f}"
                                else:
                                    line += " | N/A"

                                line += " |\n"
                                report += line

                            report += "\n"
        except Exception as e:
            logger.warning(f"⚠️ 過去一週訊號載入失敗: {e}")
            report += f"無法載入過去一週訊號: {e}\n"

        report += "---\n\n"

        # Top 3 策略
        report += "## 🏆 Top 3 Strategies (CatBoost Enhanced)\n\n"

        report += "> **說明**：以下績效為 CatBoost 模型過濾後的回測結果\n"
        report += "> - 只使用 **A/B 級訊號**（模型預測信心度高的訊號）\n"
        report += "> - 策略名稱 = Pattern (HTF/CUP/VCP) + Exit Mode (fixed_r2_t20 等)\n"
        report += "> - 績效指標代表該策略組合的歷史平均表現\n\n"

        strategies_by_return = get_top_strategies(backtest_df, n=3)
        if strategies_by_return:
            # 依年化報酬排序
            report += "### 依年化報酬排序\n\n"
            for i, strat in enumerate(strategies_by_return, 1):
                report += f"""{i}. **{strat['name']}**
   - 年化報酬: **{strat['return']:.1f}%**, Sharpe: **{strat['sharpe']:.2f}**, 勝率: {strat['win_rate']:.1f}%
   - 平均持倉: {strat['avg_holding']:.1f} 天, MDD: -{strat['mdd']:.1f}%
   - 連勝/連敗: {int(strat['max_wins'])} / {int(strat['max_losses'])}

"""

            # 依 Sharpe 排序
            report += "### 依 Sharpe 排序\n\n"
            strategies_by_sharpe = sorted(strategies_by_return, key=lambda x: x['sharpe'], reverse=True)
            for i, strat in enumerate(strategies_by_sharpe, 1):
                report += f"""{i}. **{strat['name']}**
   - Sharpe: **{strat['sharpe']:.2f}**, 年化報酬: **{strat['return']:.1f}%**, 勝率: {strat['win_rate']:.1f}%
   - 平均持倉: {strat['avg_holding']:.1f} 天, MDD: -{strat['mdd']:.1f}%
   - 連勝/連敗: {int(strat['max_wins'])} / {int(strat['max_losses'])}

"""
        else:
            report += "無 backtest 數據可用。\n"

        # 保存報告
        report_file = output_dir / f'catboost_daily_summary_{today_str}.md'
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)

        logger.info(f"✓ 報告已保存: {report_file}")

        # 同時保存推薦訊號的 CSV (用於後續載入一週清單)
        csv_file = output_dir / f'daily_scan_{today_str}.csv'
        if signals_df is not None and not signals_df.empty:
            # 篩選推薦訊號 (A/B 級)
            recommended = signals_df[signals_df['pred_label'] >= 2]
            if len(recommended) > 0:
                cols = ['sid', 'pattern_type', 'exit_mode', 'pred_grade', 'pred_proba_A', 'pred_proba_B']
                if 'Ann. Return %' in recommended.columns:
                    cols.append('Ann. Return %')
                if 'Win Rate' in recommended.columns:
                    cols.append('Win Rate')
                available_cols = [c for c in cols if c in recommended.columns]
                recommended[available_cols].to_csv(csv_file, index=False, encoding='utf-8-sig')
            else:
                # 空推薦也要保存
                pd.DataFrame().to_csv(csv_file, index=False, encoding='utf-8-sig')
        else:
            # 空推薦也要保存（用於載入一週清單時的計數）
            pd.DataFrame().to_csv(csv_file, index=False, encoding='utf-8-sig')

        logger.info(f"✓ 訊號清單已保存: {csv_file}")

        # 輸出摘要到 terminal
        logger.info("\n" + "="*80)
        logger.info("【今日掃描完成】")
        logger.info("="*80)
        if signals_df is not None and not signals_df.empty:
            recommended_count = len(signals_df[signals_df['pred_label'] >= 2])
            logger.info(f"總訊號數: {len(signals_df)}")
            logger.info(f"推薦訊號: {recommended_count}")
        else:
            logger.info("總訊號數: 0")
        logger.info(f"報告: {report_file}")
        logger.info("="*80)

    except Exception as e:
        logger.error(f"❌ 報告生成失敗: {e}")
        import traceback
        logger.error(traceback.format_exc())


def generate_html_report(output_df, full_df):
    """生成 HTML 報告"""
    html = """
    <html>
    <head>
        <meta charset="utf-8">
        <title>Daily ML Scanner Report</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            h1 { color: #333; }
            table { border-collapse: collapse; width: 100%; margin: 20px 0; }
            th { background-color: #4CAF50; color: white; padding: 10px; text-align: left; }
            td { padding: 10px; border-bottom: 1px solid #ddd; }
            tr:hover { background-color: #f5f5f5; }
            .grade-A { background-color: #90EE90; font-weight: bold; }
            .grade-B { background-color: #FFD700; font-weight: bold; }
            .grade-C { background-color: #FFA500; }
            .grade-D { background-color: #FF6347; }
            .summary { background-color: #f9f9f9; padding: 15px; margin: 20px 0; }
        </style>
    </head>
    <body>
        <h1>Daily ML Scanner Report</h1>
        <p>Generated: """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>

        <div class="summary">
            <h2>Summary</h2>
            <p>Total Signals: """ + str(len(full_df)) + """</p>
            <p>Recommended (A/B): """ + str(len(output_df)) + """</p>
        </div>

        <h2>Recommended Signals</h2>
        <table>
            <tr>
    """

    # 表頭
    for col in output_df.columns:
        html += f"<th>{col}</th>"
    html += "</tr>\n"

    # 表格行
    for _, row in output_df.iterrows():
        grade = row.get('pred_grade', 'N/A')
        grade_class = f"grade-{grade}"
        html += f"<tr><td class='{grade_class}'>" + "</td><td>".join(
            str(v) for v in row.values
        ) + "</td></tr>\n"

    html += """
        </table>
    </body>
    </html>
    """

    return html


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', default=str(RESULTS_DIR), help='輸出目錄')
    args = parser.parse_args()

    logger.info("="*80)
    logger.info("Daily ML Scanner")
    logger.info("="*80)

    # 0. 更新每日數據
    logger.info("\n>>> 更新每日數據...")
    try:
        from scripts.update_daily_data import main as update_data
        update_data()
    except Exception as e:
        logger.error(f"⚠️ 數據更新失敗: {e}")

    # 1. 載入模型和 backtest 結果
    model, feature_info = load_model_and_features()
    if model is None:
        logger.error("❌ 無法載入模型，中止執行")
        return

    feature_importance = load_feature_importance()
    backtest_df = load_backtest_performance()

    # 2. 載入今日訊號
    signals_df = get_today_signals()
    
    # 如果有訊號，進行預測和特徵處理
    if signals_df is not None and not signals_df.empty:
        # 3. 準備特徵
        signals_df = prepare_features_for_model(signals_df)
        if signals_df is None:
            logger.error("❌ 特徵準備失敗")
            signals_df = pd.DataFrame()  # 設為空，繼續生成報告

        # 4. 預測品質
        if signals_df is not None and not signals_df.empty:
            signals_df = predict_signal_quality(model, feature_info, signals_df)
            if signals_df is None:
                logger.error("❌ 預測失敗")
                signals_df = pd.DataFrame()

        # 5. 添加 backtest 性能
        if signals_df is not None and not signals_df.empty and backtest_df is not None:
            signals_df = enrich_with_backtest_performance(signals_df, backtest_df)
    else:
        logger.info("今日無訊號，僅生成 Top Strategies 報告")
        signals_df = pd.DataFrame()  # 空的 DataFrame

    # 6. 生成報告 (即使無訊號也生成，包含 Top 策略統計)
    generate_recommendation_report(signals_df, backtest_df)

    logger.info("\n" + "="*80)
    logger.info("✅ Daily Scanner 完成")
    logger.info("="*80)


if __name__ == "__main__":
    main()
