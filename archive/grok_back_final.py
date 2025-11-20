import polars as pl
import numpy as np
from datetime import date
import time

# ==========================================
# 設定區
# ==========================================
PATTERN_FILE = './pattern_analysis_result.csv'
OUTPUT_CSV = './cup_god_results_fixed.csv'
OUTPUT_REPORT = './cup_god_report_fixed.md'

INITIAL_CAPITAL = 1_000_000  # 初始資金 100萬
MAX_POSITIONS = 10           # 同時最大持倉 10 檔
POSITION_SIZE_PCT = 0.10     # 每檔佔總資金 10%

# ==========================================
# 載入數據
# ==========================================
def load_data():
    print("Loading data...")
    df = pl.read_csv(PATTERN_FILE, try_parse_dates=True, infer_schema_length=10000)
    
    # 轉換數值欄位
    price_cols = [c for c in df.columns if any(k in c.lower() for k in ["price","open","high","low","close","volume"])]
    df = df.with_columns([pl.col(c).cast(pl.Float64, strict=False) for c in price_cols])
    
    # 排序並計算均線 (用於移動止損)
    df = df.sort(["sid", "date"])
    df = df.with_columns([
        pl.col("close").rolling_mean(20).over("sid").alias("ma20"),
    ])
    df = df.with_columns(pl.col("date").cast(pl.Date))
    
    print(f"Loaded: {df.shape[0]:,} rows, {df['sid'].n_unique()} stocks, {df['date'].min()} ~ {df['date'].max()}")
    return df

def is_null_or_nan(v):
    return v is None or (isinstance(v, float) and np.isnan(v))

# ==========================================
# 核心回測引擎 (修正版)
# ==========================================
def run_god_backtest(df):
    # 1. 篩選出所有的杯柄買點信號
    signals = df.filter(
        (pl.col("is_cup") == True) &
        pl.col("cup_buy_price").is_not_null() &
        pl.col("cup_stop_price").is_not_null() &
        (pl.col("cup_buy_price") > pl.col("cup_stop_price"))
    ).select(["sid", "date", "cup_buy_price", "cup_stop_price"]).unique().to_dicts()
    
    if not signals:
        print("No signals found.")
        return []
    
    # 2. 將每日行情轉為 Hash Map 加速讀取 (Date -> DataFrame)
    partitions = df.partition_by("date", as_dict=True, maintain_order=True)
    partitions = {k[0]: v for k, v in partitions.items()}
    dates = sorted(partitions.keys())
    
    results = []
    
    # 3. 策略參數迴圈
    # partial_pct: 達到目標後賣出多少比例的持倉 (0.7 = 賣出70%)
    for strategy_name, partial_r, partial_pct in [
        ("PARTIAL 3R + MA20 (60d)", 3.0, 0.7),
        ("PARTIAL 2R + MA20 (60d)", 2.0, 0.7),
        ("PURE MA20 TRAILING (60d)", None, 0.0)
    ]:
        print(f"Running strategy: {strategy_name}...")
        
        # 初始化帳戶狀態
        cash = INITIAL_CAPITAL
        positions = {}  # key: sid, value: {shares, entry, stop, ...}
        pending_signals = signals[:] # 待入場清單
        
        trades_count = 0
        equity_curve = []
        
        for current_date in dates:
            today_df = partitions.get(current_date)
            if today_df is None: continue
            
            # 建立今日股價速查表 (SID -> Row)
            # 雖然 filter 也可以，但在大迴圈用 dict lookup 會快一點，這裡為求穩健用 filter
            
            # --- A. 計算當前總淨值 (用於部位大小計算) ---
            # 淨值 = 現金 + 所有持倉的今日市值 (若今日無報價則用昨日收盤估算，這裡簡化為忽略或用進場價)
            # 為求精確，我們先跑一次持倉更新市值
            current_positions_value = 0.0
            
            # 暫存要刪除的持倉 ID
            to_exit = []
            
            # --- B. 持倉管理 (出場檢查) ---
            for sid, pos in list(positions.items()):
                row = today_df.filter(pl.col("sid") == sid)
                if row.is_empty(): 
                    # 今日無交易(停牌)，市值以上次收盤計算(或是 entry/current price)
                    # 這裡簡單處理：不動作，市值用昨日價格(pos裡面要記錄 last_close)
                    current_positions_value += pos["shares"] * pos.get("last_close", pos["entry_price"])
                    continue
                
                high = row["high"][0]
                low = row["low"][0]
                close = row["close"][0]
                ma20 = row["ma20"][0]
                
                # 更新最後收盤價供市值計算
                pos["last_close"] = close
                
                # 取得當前止損價
                current_stop = pos["current_stop"]
                
                # 1. 檢查止盈 (Partial Take Profit)
                # 邏輯：如果 (High - Entry) / Risk >= R，則賣出部分
                if partial_r is not None and not pos["partial_done"]:
                    risk_per_share = pos["entry_price"] - pos["stop"]
                    if risk_per_share > 0:
                        # 目標價
                        target_price = pos["entry_price"] + (risk_per_share * partial_r)
                        
                        if high >= target_price:
                            # 執行部分止盈
                            shares_to_sell = pos["shares"] * partial_pct
                            revenue = shares_to_sell * target_price # 假設以目標價成交
                            
                            cash += revenue
                            pos["shares"] -= shares_to_sell
                            
                            # 剩餘倉位調整：止損上移至損益兩平(Entry Price)
                            pos["current_stop"] = pos["entry_price"]
                            current_stop = pos["entry_price"] # 更新當前變數
                            pos["partial_done"] = True
                
                # 2. 檢查移動止損 (Trailing Stop)
                # 邏輯：如果已經止盈過，或是純 MA20 策略，則止損跟隨 MA20
                if partial_r is None or pos["partial_done"]:
                    if not is_null_or_nan(ma20):
                        # 止損只能上移不能下移
                        if ma20 > current_stop:
                            current_stop = ma20
                            pos["current_stop"] = current_stop
                
                # 3. 檢查止損出場 (Stop Loss)
                # 邏輯：如果 Low <= Current Stop，全部賣出
                if low <= current_stop:
                    # 賣出所有持倉
                    # 假設以止損價成交 (較為保守)；若開盤就跳空跌破，理論上是用 Open，這裡簡化用 Stop Price
                    exit_price = current_stop
                    # 如果當天 High 都低於 Stop (跳空跌停)，則只能用 Close 或 Low 出場 (極端情況)
                    if high < current_stop: 
                        exit_price = close 
                    
                    revenue = pos["shares"] * exit_price
                    cash += revenue
                    
                    to_exit.append(sid)
                else:
                    # 沒出場，累加市值
                    current_positions_value += pos["shares"] * close
            
            # 移除已出場部位
            for sid in to_exit:
                del positions[sid]
            
            # 計算當下總資產 (Equity) 用於開新倉
            total_equity = cash + current_positions_value
            
            # --- C. 進場邏輯 (Entry) ---
            if len(positions) < MAX_POSITIONS and pending_signals:
                # 篩選過去 60 天內的信號
                valid_signals = [s for s in pending_signals if (current_date - s["date"]).days <= 60]
                
                # 隨機打亂避免只買特定順序的股票
                np.random.shuffle(valid_signals)
                
                for sig in valid_signals:
                    if len(positions) >= MAX_POSITIONS: break
                    
                    # 檢查今日是否有價格且觸發買入
                    row = today_df.filter(pl.col("sid") == sig["sid"])
                    # 條件：今日最高價 >= 買入價 (代表觸價成交)
                    if row.is_empty() or row["high"][0] < sig["cup_buy_price"]: continue
                    
                    entry_price = sig["cup_buy_price"]
                    stop_price = sig["cup_stop_price"]
                    
                    # 簡單風控
                    if entry_price <= stop_price: continue
                    if entry_price <= 0: continue
                    
                    # 資金管理：每個部位使用當前總資產的 N%
                    position_budget = total_equity * POSITION_SIZE_PCT
                    
                    # 檢查現金是否足夠
                    if cash >= position_budget:
                        shares = position_budget / entry_price
                        cost = shares * entry_price
                        
                        # 執行買入
                        cash -= cost
                        trades_count += 1
                        
                        positions[sig["sid"]] = {
                            "entry_price": entry_price,
                            "stop": stop_price,
                            "shares": shares,
                            "current_stop": stop_price,
                            "partial_done": False,
                            "last_close": entry_price
                        }
                        # 從待辦清單移除 (已進場)
                        pending_signals.remove(sig)
            
            # 記錄今日最終淨值
            # 需重新計算市值，因為剛才有新進場
            final_pos_value = 0
            for sid, pos in positions.items():
                # 如果剛進場，用 entry_price 估值；如果是舊倉，用 close
                # 簡單起見，直接查表，若無則用 last_close
                r = today_df.filter(pl.col("sid") == sid)
                if not r.is_empty():
                    price = r["close"][0]
                else:
                    price = pos.get("last_close", pos["entry_price"])
                final_pos_value += pos["shares"] * price
                
            equity_curve.append(cash + final_pos_value)

        # --- 績效計算 ---
        eq_series = pl.Series(equity_curve) if equity_curve else pl.Series([INITIAL_CAPITAL])
        final_equity = eq_series[-1]
        total_return = (final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
        
        # 最大回撤 (MDD)
        cum_max = eq_series.cum_max()
        drawdown = (cum_max - eq_series) / cum_max
        max_dd = drawdown.max() * 100
        
        results.append({
            "Strategy": strategy_name,
            "Final Equity": f"{final_equity:,.0f}",
            "Total Return %": round(total_return, 2),
            "Max Drawdown %": round(max_dd, 2),
            "Trades": trades_count
        })
    
    return results

def main():
    start_time = time.time()
    df = load_data()
    results = run_god_backtest(df)
    
    res_df = pl.DataFrame(results)
    res_df.write_csv(OUTPUT_CSV)
    
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        f.write("# CUP GOD MODE - 邏輯修正版 (Fixed Logic)\n\n")
        f.write(f"**說明**：此版本修正了現金流重複計算問題，並採用正確的部位規模計算 (Current Equity * 10%)。\n\n")
        f.write(f"執行時間: {time.time()-start_time:.1f}秒\n\n")
        f.write(res_df.to_pandas().to_markdown(index=False))
    
    print("\n" + "="*70)
    print(" GOD MODE 邏輯修正完畢。請參考以下真實績效：")
    print("="*70)
    print(res_df)

if __name__ == "__main__":
    main()