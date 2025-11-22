"""
Weekly Model Retraining Orchestration

並行更新 ML 系統中兩套模型的權重:
1. ml_enhanced: 9 個獨立 XGBoost 模型 (每個 pattern×exit_mode 一個)
2. catboost_enhanced: 1 個全局 CatBoost 模型 (pattern_type 和 exit_mode 作為特徵)

流程:
1. 載入最新的訊號和市場資料
2. 準備特徵資料
3. 並行訓練:
   - ml_enhanced/scripts/prepare_ml_data.py + train_models.py
   - catboost_enhanced/scripts/prepare_catboost_data.py + train.py
4. 並行執行回測驗證:
   - ml_enhanced/scripts/run_ml_backtest.py
   - catboost_enhanced/scripts/run_catboost_backtest.py
5. 比較性能並生成報告

Usage:
    python catboost_enhanced/weekly_retrain.py [--compare-only]

Options:
    --compare-only: 只比較現有模型，不執行訓練
"""

import os
import sys
import time
import json
import subprocess
from pathlib import Path
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
import pandas as pd

# Add parent directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.utils.logger import setup_logger

logger = setup_logger('weekly_retrain')

# 配置
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ML_ENHANCED_DIR = PROJECT_ROOT / 'ml_enhanced'
CATBOOST_ENHANCED_DIR = PROJECT_ROOT / 'catboost_enhanced'

PREPARE_ML_SCRIPT = ML_ENHANCED_DIR / 'scripts' / 'prepare_ml_data.py'
TRAIN_ML_SCRIPT = ML_ENHANCED_DIR / 'scripts' / 'train_models.py'
RUN_ML_BACKTEST_SCRIPT = PROJECT_ROOT / 'scripts' / 'run_backtest.py'

PREPARE_CATBOOST_SCRIPT = CATBOOST_ENHANCED_DIR / 'scripts' / 'prepare_catboost_data.py'
TRAIN_CATBOOST_SCRIPT = CATBOOST_ENHANCED_DIR / 'scripts' / 'train.py'
RUN_CATBOOST_BACKTEST_SCRIPT = CATBOOST_ENHANCED_DIR / 'scripts' / 'run_catboost_backtest.py'

COMPARISON_REPORT = CATBOOST_ENHANCED_DIR / 'results' / 'weekly_comparison_report.md'
COMPARISON_DATA = CATBOOST_ENHANCED_DIR / 'results' / 'comparison_data.json'

ML_BACKTEST_RESULTS = PROJECT_ROOT / 'data' / 'processed' / 'backtest_results_v2.csv'
CATBOOST_BACKTEST_RESULTS = CATBOOST_ENHANCED_DIR / 'results' / 'backtest_by_group.csv'


def run_command(cmd, description):
    """執行單個命令並捕獲輸出"""
    logger.info(f"\n{'='*80}")
    logger.info(f"執行: {description}")
    logger.info(f"命令: {' '.join(cmd)}")
    logger.info(f"{'='*80}")

    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )

        if result.stdout:
            logger.info(result.stdout)

        if result.returncode != 0:
            logger.error(f"❌ 失敗: {description}")
            if result.stderr:
                logger.error(result.stderr)
            return False, result.stderr
        else:
            logger.info(f"✓ 成功: {description}")
            return True, result.stdout

    except subprocess.TimeoutExpired:
        logger.error(f"❌ 超時: {description} (timeout after 1 hour)")
        return False, "Timeout"
    except Exception as e:
        logger.error(f"❌ 錯誤: {description} - {e}")
        return False, str(e)


def train_ml_enhanced():
    """訓練 ml_enhanced 模型"""
    logger.info("\n【ML Enhanced 訓練流程】")

    # 準備資料
    success, output = run_command(
        [sys.executable, str(PREPARE_ML_SCRIPT)],
        "ML Enhanced 特徵準備"
    )
    if not success:
        return False, "Feature preparation failed"

    # 訓練模型
    success, output = run_command(
        [sys.executable, str(TRAIN_ML_SCRIPT)],
        "ML Enhanced 模型訓練"
    )
    if not success:
        return False, "Model training failed"

    return True, "ML Enhanced training completed"


def train_catboost_enhanced():
    """訓練 catboost_enhanced 模型"""
    logger.info("\n【CatBoost Enhanced 訓練流程】")

    # 準備資料
    success, output = run_command(
        [sys.executable, str(PREPARE_CATBOOST_SCRIPT)],
        "CatBoost Enhanced 特徵準備"
    )
    if not success:
        return False, "Feature preparation failed"

    # 訓練模型
    success, output = run_command(
        [sys.executable, str(TRAIN_CATBOOST_SCRIPT)],
        "CatBoost Enhanced 模型訓練"
    )
    if not success:
        return False, "Model training failed"

    return True, "CatBoost Enhanced training completed"


def backtest_ml_enhanced():
    """執行 ml_enhanced 回測"""
    logger.info("\n【ML Enhanced 回測】")

    success, output = run_command(
        [sys.executable, str(RUN_ML_BACKTEST_SCRIPT)],
        "ML Enhanced 回測執行"
    )

    if success and os.path.exists(ML_BACKTEST_RESULTS):
        try:
            df = pd.read_csv(ML_BACKTEST_RESULTS)
            logger.info(f"✓ 回測結果: {len(df)} 筆交易")
            return True, df
        except Exception as e:
            logger.warning(f"⚠️ 無法讀取回測結果: {e}")
            return False, None
    else:
        return False, None


def backtest_catboost_enhanced():
    """執行 catboost_enhanced 回測"""
    logger.info("\n【CatBoost Enhanced 回測】")

    success, output = run_command(
        [sys.executable, str(RUN_CATBOOST_BACKTEST_SCRIPT)],
        "CatBoost Enhanced 回測執行"
    )

    if success and os.path.exists(CATBOOST_BACKTEST_RESULTS):
        try:
            df = pd.read_csv(CATBOOST_BACKTEST_RESULTS)
            logger.info(f"✓ 回測結果: {len(df)} 個組合")
            return True, df
        except Exception as e:
            logger.warning(f"⚠️ 無法讀取回測結果: {e}")
            return False, None
    else:
        return False, None


def compare_models(ml_backtest_df, catboost_backtest_df):
    """
    比較兩套模型的性能

    ml_backtest_df: ml_enhanced backtest 結果
    catboost_backtest_df: catboost_enhanced backtest 結果
    """
    logger.info("\n" + "="*80)
    logger.info("模型性能對比分析")
    logger.info("="*80)

    comparison_data = {
        "timestamp": datetime.now().isoformat(),
        "ml_enhanced": {},
        "catboost_enhanced": {},
        "comparison": {}
    }

    # 解析 ml_enhanced 結果
    if ml_backtest_df is not None:
        # ml_enhanced 結果通常按照各種組合 (pattern_type, exit_mode) 分組
        # 基本的績效統計
        ml_stats = {
            "total_trades": len(ml_backtest_df),
            "avg_return_pct": ml_backtest_df.get('return_pct', pd.Series()).mean() if 'return_pct' in ml_backtest_df.columns else 0,
            "win_rate_pct": (ml_backtest_df['return_pct'] > 0).sum() / len(ml_backtest_df) * 100 if 'return_pct' in ml_backtest_df.columns else 0,
            "max_return_pct": ml_backtest_df.get('return_pct', pd.Series()).max() if 'return_pct' in ml_backtest_df.columns else 0,
            "min_return_pct": ml_backtest_df.get('return_pct', pd.Series()).min() if 'return_pct' in ml_backtest_df.columns else 0,
        }
        comparison_data["ml_enhanced"] = ml_stats
        logger.info("\n【ML Enhanced 統計】")
        for key, val in ml_stats.items():
            logger.info(f"  {key}: {val:.2f}")

    # 解析 catboost_enhanced 結果
    if catboost_backtest_df is not None:
        catboost_cols = catboost_backtest_df.columns
        catboost_stats = {
            "total_combinations": len(catboost_backtest_df),
            "avg_annual_return_pct": catboost_backtest_df.get('Ann. Return %', pd.Series()).mean() if 'Ann. Return %' in catboost_cols else 0,
            "avg_win_rate_pct": catboost_backtest_df.get('Win Rate', pd.Series()).mean() if 'Win Rate' in catboost_cols else 0,
            "best_annual_return_pct": catboost_backtest_df.get('Ann. Return %', pd.Series()).max() if 'Ann. Return %' in catboost_cols else 0,
            "worst_annual_return_pct": catboost_backtest_df.get('Ann. Return %', pd.Series()).min() if 'Ann. Return %' in catboost_cols else 0,
        }
        comparison_data["catboost_enhanced"] = catboost_stats
        logger.info("\n【CatBoost Enhanced 統計】")
        for key, val in catboost_stats.items():
            logger.info(f"  {key}: {val:.2f}")

        # 顯示最佳組合
        if 'Ann. Return %' in catboost_cols:
            best_idx = catboost_backtest_df['Ann. Return %'].idxmax()
            best_row = catboost_backtest_df.loc[best_idx]
            logger.info("\n【最佳組合】")
            logger.info(f"  Pattern: {best_row.get('pattern', 'N/A')}")
            logger.info(f"  Exit Mode: {best_row.get('exit_mode', 'N/A')}")
            logger.info(f"  年化報酬: {best_row.get('Ann. Return %', 0):.2f}%")
            logger.info(f"  勝率: {best_row.get('Win Rate', 0):.2f}%")
            logger.info(f"  夏普值: {best_row.get('Sharpe', 0):.2f}")

    return comparison_data


def generate_report(comparison_data):
    """生成比較報告"""
    logger.info("\n" + "="*80)
    logger.info("生成比較報告")
    logger.info("="*80)

    report = f"""# 週期模型重訓報告

生成時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 執行摘要

本週期對兩套機器學習系統進行平行重訓和性能評估:

### ML Enhanced 系統
- **架構**: 9 個獨立 XGBoost 模型 (pattern_type × exit_mode)
- **訓練方法**: 傳統監督學習，各模型獨立訓練
- **特徵數**: 24 個

### CatBoost Enhanced 系統
- **架構**: 1 個全局 CatBoost 多分類模型 (pattern_type 和 exit_mode 作為特徵)
- **訓練方法**: P0 全局模型 + P1 Embargo 隔離 + P2 樣本權重
- **特徵數**: 52 個數值 + 2 個分類

## 性能統計

### ML Enhanced
"""
    if comparison_data.get("ml_enhanced"):
        for key, val in comparison_data["ml_enhanced"].items():
            report += f"- **{key}**: {val:.2f}\n"
    else:
        report += "- 未執行或執行失敗\n"

    report += "\n### CatBoost Enhanced\n"
    if comparison_data.get("catboost_enhanced"):
        for key, val in comparison_data["catboost_enhanced"].items():
            report += f"- **{key}**: {val:.2f}\n"
    else:
        report += "- 未執行或執行失敗\n"

    report += f"""

## 關鍵發現

1. **模型架構差異**:
   - ML Enhanced: 9 個獨立模型，各自預測該組合的信號品質
   - CatBoost Enhanced: 全局模型學習最佳 pattern-exit_mode 組合

2. **樣本權重差異**:
   - ML Enhanced: 使用簡單的勝負標籤
   - CatBoost Enhanced: P2 三層權重 (score幅度 + 標籤等級 + 類頻率補償)

3. **特徵差異**:
   - CatBoost Enhanced 包含更多機構流特徵和技術指標

## 後續建議

根據回測結果，請評估:
1. 年化報酬率的差異是否顯著
2. 樣本權重策略 (P2) 是否改善了預測準確率
3. 全局模型是否比獨立模型更能捕捉 pattern-exit_mode 相互作用

## 詳細數據

更多信息見: {COMPARISON_DATA}

---
Report generated by weekly_retrain.py
"""

    os.makedirs(COMPARISON_REPORT.parent, exist_ok=True)
    with open(COMPARISON_REPORT, 'w', encoding='utf-8') as f:
        f.write(report)

    logger.info(f"✓ 報告已保存: {COMPARISON_REPORT}")

    # 保存數據為 JSON
    with open(COMPARISON_DATA, 'w', encoding='utf-8') as f:
        json.dump(comparison_data, f, indent=2, ensure_ascii=False)

    logger.info(f"✓ 數據已保存: {COMPARISON_DATA}")


def main():
    """主程序"""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--compare-only', action='store_true', help='只比較現有模型，不執行訓練')
    args = parser.parse_args()

    logger.info("\n" + "="*80)
    logger.info("週期模型重訓開始")
    logger.info("="*80)

    start_time = time.time()

    # 執行並行訓練
    if not args.compare_only:
        logger.info("\n【階段 1: 並行特徵準備和模型訓練】")

        with ProcessPoolExecutor(max_workers=2) as executor:
            # 提交訓練任務
            ml_future = executor.submit(train_ml_enhanced)
            catboost_future = executor.submit(train_catboost_enhanced)

            # 等待結果
            ml_success, ml_msg = ml_future.result()
            catboost_success, catboost_msg = catboost_future.result()

        if not ml_success:
            logger.warning(f"⚠️ ML Enhanced 訓練失敗: {ml_msg}")
        if not catboost_success:
            logger.warning(f"⚠️ CatBoost Enhanced 訓練失敗: {catboost_msg}")

    # 執行並行回測
    logger.info("\n【階段 2: 並行回測驗證】")

    with ProcessPoolExecutor(max_workers=2) as executor:
        ml_backtest_future = executor.submit(backtest_ml_enhanced)
        catboost_backtest_future = executor.submit(backtest_catboost_enhanced)

        ml_success, ml_backtest_df = ml_backtest_future.result()
        catboost_success, catboost_backtest_df = catboost_backtest_future.result()

    # 比較結果
    logger.info("\n【階段 3: 性能比較】")
    comparison_data = compare_models(ml_backtest_df, catboost_backtest_df)

    # 生成報告
    logger.info("\n【階段 4: 生成報告】")
    generate_report(comparison_data)

    # 統計
    elapsed = time.time() - start_time
    logger.info("\n" + "="*80)
    logger.info("✅ 週期模型重訓完成")
    logger.info(f"總耗時: {elapsed/60:.1f} 分鐘")
    logger.info("="*80)


if __name__ == "__main__":
    main()
