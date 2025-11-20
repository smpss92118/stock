# Optimization Log (優化記錄)

本文件記錄每次型態識別優化的過程、變更內容以及回測績效的改進。

## Cycle 0: Initial Refactoring (初始重構)
- **Date**: 2025-11-20
- **Changes**:
    - 將 `pattern_analysis.py` 拆分為模組化結構：
        - `stock/strategies/htf.py`
        - `stock/strategies/vcp.py`
        - `stock/strategies/cup.py`
        - `stock/strategies/utils.py`
    - 建立優化循環流程。
- **Performance Baseline (V2 Results)**:
    - **HTF**: 288.3% (Trig=1.5R, Trail=MA20)
    - **CUP**: 152.5% (R=3.0, T=20)
    - **VCP**: -6.8% (R=2.0, T=20) - *Needs Improvement*

## Cycle 1: VCP Optimization (VCP 優化)
- **Date**: 2025-11-20
- **Changes**:
    - **Strategy**: VCP
    - **Parameters**:
        - `zigzag_threshold`: 0.05 -> 0.04 (更敏感，捕捉更多波動)
        - `min_up_ratio`: 0.4 -> 0.5 (要求更強的上升趨勢)
        - `Trend Filter`: 新增 `Price > MA50` 條件
- **Results**:
    - **VCP (Trig=2.0R, Trail=MA20)**:
        - Return: **71.6%** (Significant Improvement from 23.0%)
        - Sharpe: 0.66
        - Win Rate: 23.6% (Dropped from 27.1%)
        - Count: 385
    - **VCP (R=2.0, T=20)**:
        - Return: -45.9% (Worsened)
        - Win Rate: 31.4%
- **Analysis**:
    - 追蹤止損策略 (Trailing Stop) 大幅改善了 VCP 的績效，顯示 VCP 更適合捕捉大波段趨勢而非固定目標。
    - ZigZag 敏感度提高導致交易次數增加，但勝率下降，顯示雜訊變多。
    - 固定目標策略失效，可能是因為波動變大導致容易掃到停損。
- **Next Step**:
    - 嘗試恢復 `zigzag_threshold` 至 0.05 以減少雜訊。
    - 進一步收緊成交量過濾 (`vol_dry_up_ratio` 0.6 -> 0.5)。

## Cycle 2: VCP Refinement (VCP 精煉)
- **Date**: 2025-11-20
- **Changes**:
    - **Strategy**: VCP
    - **Parameters**:
        - `zigzag_threshold`: 0.04 -> 0.05 (恢復至 5% 以減少雜訊)
        - `vol_dry_up_ratio`: 0.6 -> 0.5 (更嚴格的量縮要求，需小於 50 日均量的 50%)
        - `min_up_ratio`: 保持 0.5
        - `Trend Filter`: 保持 `Price > MA50`
- **Results**:
    - **VCP (Trig=2.0R, Trail=MA20)**:
        - Return: **150.2%** (Doubled from 71.6%)
        - Sharpe: 0.64
        - Win Rate: **25.5%** (Improved from 23.6%)
        - Max DD: **-13.4%** (Improved from -15.0%)
        - Count: 341 (Reduced from 385)
    - **VCP (R=2.0, T=20)**:
        - Return: **4.4%** (Turned Positive from -45.9%)
        - Win Rate: **35.0%** (Improved from 31.4%)
- **Analysis**:
    - 恢復 ZigZag 5% 並收緊成交量過濾至 50% 顯著提升了訊號品質。
    - 固定目標策略由負轉正，證明過濾掉許多失敗的交易。
    - 追蹤止損策略報酬率翻倍，達到 150%，顯示此參數組合能有效捕捉大波段。
- **Conclusion**:
    - VCP 優化成功，建議維持此參數組合。
    - 下一步可考慮優化 CUP 或 HTF，或針對 VCP 進行更細微的參數微調 (如 3 legs 強制要求)。

## Cycle 3: Market Trend Integration (大盤趨勢過濾)
- **Date**: 2025-11-20
- **Changes**:
    - **Strategy**: VCP
    - **New Filter**: `Market Price > Market MA200` (使用 TAIEX 指數)
    - **Parameters**: 其他參數維持 Cycle 2 設定
- **Results (Limited Capital)**:
    - **VCP (Trig=1.5R, Trail=MA20)**:
        - Return: **81.5%** (Dropped from 150.2% in Cycle 2)
        - Sharpe: **0.83** (Improved from 0.64)
        - Win Rate: **29.3%** (Improved from 25.5%)
        - Max DD: -15.7% (Slightly worse than -13.4%)
        - Count: 314
- **Analysis**:
    - 加入大盤 MA200 過濾後，雖然勝率和夏普比率提升（交易更穩健），但總報酬率大幅下降。
    - **原因推測**：MA200 是長期趨勢指標，反應較慢。許多強勢股在大盤尚未站上 MA200 時就已發動（例如市場從底部反轉初期），此過濾條件導致錯失了這些獲利最豐厚的早期波段。
    - **Limited Capital 觀點**：在資金有限情況下，雖然我們希望避開空頭，但過於保守的濾網會減少資金運用效率。
- **Conclusion**:
    - MA200 過濾過於嚴格/滯後，不適合追求高報酬。
    - 建議嘗試較靈敏的市場濾網 (如 Market > MA50) 或改用個股相對強度 (RS) 過濾。
    - 下一步 (Cycle 4) 將嘗試移除市場濾網，改為加入 **RS (Relative Strength)** 過濾，確保個股強於大盤。

## Cycle 4: Relative Strength (RS) Filter (相對強度過濾)
- **Date**: 2025-11-20
- **Changes**:
    - **Strategy**: VCP
    - **New Filter**: `RS Rating > 0` (Stock 6-month Return > Market 6-month Return)
    - **Removed Filter**: 移除 Cycle 3 的 `Market Price > MA200`
- **Results (Limited Capital)**:
    - **VCP (Trig=2.0R, Trail=MA20)**:
        - Return: **155.7%** (Best VCP Result so far! Cycle 2 was 150.2%)
        - Sharpe: **0.65** (Similar to Cycle 2)
        - Win Rate: **26.2%** (Improved from 25.5%)
        - Max DD: **-13.4%** (Same as Cycle 2)
        - Count: 340
- **Analysis**:
    - RS 過濾成功超越了單純的個股趨勢過濾 (Cycle 2) 和大盤趨勢過濾 (Cycle 3)。
    - **RS 的優勢**：它動態地篩選出比大盤強勢的股票，即使大盤處於震盪或弱勢，只要個股表現相對較好（例如抗跌或率先反彈），仍有機會進場。這解決了 MA200 過於滯後的問題，同時保持了過濾弱勢股的能力。
    - **VCP 優化總結**：從最初的 -6.8% (Cycle 0) -> 155.7% (Cycle 4)，進步巨大。
- **Conclusion**:
    - VCP 策略已達到一個穩定的高性能水平。
    - 下一步 (Cycle 5) 將轉向優化 **HTF (High Tight Flag)** 策略，目前 HTF 仍是冠軍 (288%)，嘗試將 RS 過濾應用於 HTF，看能否突破 300%。

## Cycle 5: HTF Optimization with RS (HTF + RS)
- **Date**: 2025-11-20
- **Changes**:
    - **Strategy**: HTF
    - **New Filter**: `RS Rating > 0`
- **Results (Limited Capital)**:
    - **HTF (Trig=1.5R, Trail=MA20)**:
        - Return: **288.3%** (Identical to Baseline)
        - Count: 275 (Identical to Baseline)
- **Analysis**:
    - 加入 RS 過濾對 HTF 策略 **完全沒有影響**。
    - **原因**：HTF 的定義本身就要求股價在短期內上漲 80% 以上。這本身就是極強的相對強度表現。在這種情況下，RS > 0 是一個多餘的條件，因為所有符合 HTF 的股票必然大幅跑贏大盤。
- **Conclusion**:
    - HTF 策略本身已隱含了極高的 RS 篩選。
    - 無需對 HTF 進行額外的 RS 過濾。
    - 下一步 (Cycle 6) 將轉向優化 **CUP (Cup with Handle)** 策略。CUP 的形成時間較長，相對強度可能不如 HTF 極端，因此 RS 過濾可能會有幫助。

---
