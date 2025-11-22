#!/usr/bin/env python3
"""
三大法人歷史數據補齊腳本

功能:
1. 批次補齊指定日期範圍的三大法人數據
2. 自動跳過週末與假日
3. 避免重複爬取
4. 支援斷點續傳

使用:
    python backfill_history.py --start 2020-01-01 --end 2024-11-21
    python backfill_history.py --start 2024-01-01  # end 預設今天
"""

import sys
import os
from pathlib import Path
import argparse
from datetime import datetime, timedelta
import time
import pandas as pd

# 加入上層目錄以import fetch_institution
sys.path.append(str(Path(__file__).parent))
from fetch_institution import fetch_and_save, RAW_DATA_DIR


def is_weekend(date_obj):
    """檢查是否為週末"""
    return date_obj.weekday() >= 5  # 5=六, 6=日


def file_exists(date_str):
    """檢查該日期的數據檔案是否已存在"""
    filename = f"institution_{date_str}.csv"
    filepath = RAW_DATA_DIR / filename
    return filepath.exists()


def backfill_historical_data(start_date, end_date, skip_existing=True, sleep_seconds=3):
    """
    批次補齊歷史數據
    
    Args:
        start_date: 起始日期 'YYYY-MM-DD'
        end_date: 結束日期 'YYYY-MM-DD'
        skip_existing: 是否跳過已存在的檔案
        sleep_seconds: 每次請求間隔秒數
    
    Returns:
        dict: 統計資訊
    """
    start_obj = datetime.strptime(start_date, '%Y-%m-%d')
    end_obj = datetime.strptime(end_date, '%Y-%m-%d')
    
    if start_obj > end_obj:
        print("❌ 起始日期不能晚於結束日期")
        return None
    
    print(f"\n{'='*70}")
    print(f"批次補齊三大法人歷史數據")
    print(f"{'='*70}")
    print(f"起始日期: {start_date}")
    print(f"結束日期: {end_date}")
    print(f"跳過已存在: {skip_existing}")
    print(f"請求間隔: {sleep_seconds} 秒")
    print(f"{'='*70}\n")
    
    # 統計資訊
    stats = {
        'total_days': 0,
        'success': 0,
        'failed': 0,
        'skipped_weekend': 0,
        'skipped_existing': 0
    }
    
    current_date = start_obj
    
    while current_date <= end_obj:
        date_str = current_date.strftime('%Y-%m-%d')
        stats['total_days'] += 1
        
        # 跳過週末
        if is_weekend(current_date):
            print(f"⏭️  {date_str} (週末，跳過)")
            stats['skipped_weekend'] += 1
            current_date += timedelta(days=1)
            continue
        
        # 跳過已存在的檔案
        if skip_existing and file_exists(date_str):
            print(f"✅ {date_str} (已存在，跳過)")
            stats['skipped_existing'] += 1
            current_date += timedelta(days=1)
            continue
        
        # 爬取數據
        try:
            success = fetch_and_save(date_str)
            
            if success:
                stats['success'] += 1
                print(f"✅ {date_str} - 成功 ({stats['success']}/{stats['total_days'] - stats['skipped_weekend'] - stats['skipped_existing']})")
            else:
                stats['failed'] += 1
                print(f"❌ {date_str} - 失敗 (可能為假日)")
            
            # 避免請求過快
            time.sleep(sleep_seconds)
            
        except KeyboardInterrupt:
            print("\n\n⚠️  使用者中斷爬取")
            print(f"已處理到: {date_str}")
            break
        except Exception as e:
            print(f"❌ {date_str} - 錯誤: {e}")
            stats['failed'] += 1
            time.sleep(sleep_seconds)
        
        current_date += timedelta(days=1)
    
    # 列印統計
    print(f"\n{'='*70}")
    print("補齊完成！")
    print(f"{'='*70}")
    print(f"總天數: {stats['total_days']}")
    print(f"成功: {stats['success']}")
    print(f"失敗: {stats['failed']}")
    print(f"跳過（週末）: {stats['skipped_weekend']}")
    print(f"跳過（已存在）: {stats['skipped_existing']}")
    print(f"{'='*70}\n")
    
    return stats


def consolidate_data():
    """
    將所有單日檔案合併為一個完整檔案
    
    Returns:
        DataFrame or None
    """
    print("\n📊 合併所有數據檔案...")
    
    csv_files = sorted(RAW_DATA_DIR.glob("institution_*.csv"))
    
    if not csv_files:
        print("❌ 找不到任何數據檔案")
        return None
    
    print(f"找到 {len(csv_files)} 個檔案")
    
    dfs = []
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            dfs.append(df)
        except Exception as e:
            print(f"⚠️  讀取失敗: {csv_file.name} - {e}")
    
    if not dfs:
        print("❌ 無法讀取任何檔案")
        return None
    
    df_combined = pd.concat(dfs, ignore_index=True)
    
    # 排序
    df_combined = df_combined.sort_values(['date', 'sid']).reset_index(drop=True)
    
    # 儲存合併檔案
    output_file = RAW_DATA_DIR.parent / 'processed' / 'institution_all.csv'
    output_file.parent.mkdir(parents=True, exist_ok=True)
    df_combined.to_csv(output_file, index=False, encoding='utf-8-sig')
    
    print(f"✅ 合併完成: {output_file}")
    print(f"   總筆數: {len(df_combined):,}")
    print(f"   日期範圍: {df_combined['date'].min()} ~ {df_combined['date'].max()}")
    print(f"   股票數: {df_combined['sid'].nunique():,}")
    
    return df_combined


def main():
    parser = argparse.ArgumentParser(description='批次補齊三大法人歷史數據')
    parser.add_argument('--start', type=str, required=True,
                       help='起始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, 
                       default=datetime.now().strftime('%Y-%m-%d'),
                       help='結束日期 (YYYY-MM-DD), 預設今天')
    parser.add_argument('--skip-existing', action='store_true', default=True,
                       help='跳過已存在的檔案 (預設開啟)')
    parser.add_argument('--no-skip-existing', dest='skip_existing', action='store_false',
                       help='重新爬取已存在的檔案')
    parser.add_argument('--sleep', type=int, default=3,
                       help='每次請求間隔秒數 (預設 3 秒)')
    parser.add_argument('--consolidate', action='store_true',
                       help='補齊後合併所有數據')
    
    args = parser.parse_args()
    
    # 驗證日期格式
    try:
        datetime.strptime(args.start, '%Y-%m-%d')
        datetime.strptime(args.end, '%Y-%m-%d')
    except ValueError:
        print("❌ 日期格式錯誤，請使用 YYYY-MM-DD")
        exit(1)
    
    # 開始補齊
    stats = backfill_historical_data(
        args.start, 
        args.end, 
        skip_existing=args.skip_existing,
        sleep_seconds=args.sleep
    )
    
    if stats is None:
        print("\n❌ 補齊失敗")
        exit(1)
    
    # 合併數據
    if args.consolidate and stats['success'] > 0:
        consolidate_data()
    
    print("\n🎉 全部完成！")


if __name__ == "__main__":
    main()
