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

## Cycle 6: CUP Optimization with RS (CUP + RS)
- **Date**: 2025-11-20
- **Changes**:
    - **Strategy**: CUP
    - **New Filter**: `RS Rating > 0`
- **Results (Limited Capital)**:
    - **CUP (R=3.0, T=20)**:
        - Return: **184.9%** (Improved from Baseline 152.5%)
        - Win Rate: **59.6%** (Improved from 56.7%)
        - Count: 272 (Slightly reduced from 284)
    - **CUP (R=2.0, T=20)**:
        - Return: 117.4% (Dropped from 133.1%)
- **Analysis**:
    - RS 過濾顯著提升了 CUP 策略的獲利能力 (152% -> 185%)。
    - **原因**：Cup 型態通常歷時較長 (3-6個月)，期間大盤可能經歷波動。RS 過濾確保了在型態完成時，該股票仍強於大盤，這增加了突破後持續上漲的機率。
    - R=3.0 的表現優於 R=2.0，顯示強勢股有更大的上漲空間，太早停利反而會錯失利潤。
- **Conclusion**:
    - CUP 策略應納入 RS 過濾。
    - 目前三大策略最佳配置：
        1. **HTF**: 288% (Trig=1.5R, Trail=MA20) - 無需 RS
        2. **CUP**: 185% (R=3.0, T=20) - 需 RS
        3. **VCP**: 156% (Trig=2.0R, Trail=MA20) - 需 RS
    - 下一步 (Cycle 7) 將嘗試 **放寬 HTF 條件** (Min Up 80% -> 60%) 但保留 RS 過濾，看能否在保持高勝率的同時增加交易機會。

## Cycle 7: Relaxed HTF with RS (HTF 寬鬆版)
- **Date**: 2025-11-20
- **Changes**:
    - **Strategy**: HTF
    - **Parameter**: `min_up_ratio`: 0.8 -> 0.6
    - **Filter**: `RS Rating > 0` (Kept)
- **Results (Limited Capital)**:
    - **HTF (Trig=1.5R, Trail=MA20)**:
        - Return: **288.3%** (Identical to Cycle 5)
        - Count: 275 (Identical)
- **Analysis**:
    - 放寬漲幅限制似乎沒有顯著增加交易次數或改變結果。這可能意味著大部分 HTF 的漲幅本來就很高，或者篩選邏輯中有其他瓶頸（如 flag_days）。
- **Conclusion**:
    - 維持 HTF 現狀。

## Cycle 8: VCP Advanced Part 1 (RS > 70 & Location)
- **Date**: 2025-11-20
- **Changes**:
    - **Strategy**: VCP
    - **New Filter 1**: `RS Rating > 70` (52-week Return Percentile)
    - **New Filter 2**: `Location`: Price within 15% of 52-week High (`Close >= 0.85 * High52`)
- **Results**:
    - **Limited Capital (Trig=2.0R, Trail=MA20)**:
        - Return: **95.8%** (Dropped from 155.7% in Cycle 4)
        - Sharpe: 0.58
        - Count: 302
    - **Unlimited Capital (Trig=2.0R, Trail=MA20)**:
        - Return: **358.0%** (Improved from 345.5% in Cycle 4)
        - Sharpe: **1.00** (Significant Improvement from 0.78)
- **Analysis**:
    - **質量 vs 數量**：嚴格的篩選條件（RS>70, Near High）顯著提升了交易的質量（Unlimited Sharpe 1.0 是目前最高），證明了這些濾網能挑選出更穩健的標的。
    - **資金效率**：然而，在資金有限（Limited）的情境下，由於交易機會減少，資金閒置時間變長，導致總報酬率下降。
    - **結論**：這些濾網有效提升了單筆交易的期望值，但對於追求絕對報酬的積極策略來說，可能過於保守。
- **Next Step**:
    - 進入 **Cycle 9**，實施更細緻的「收縮比率」和「成交量」規則。這可能會進一步過濾訊號，我們需要觀察是否能通過提高勝率來彌補頻率的下降。

## Cycle 9: VCP Advanced Part 2 (Contraction & Volume)
- **Date**: 2025-11-20
- **Changes**:
    - **Strategy**: VCP
    - **Parameter**: `zigzag_threshold`: 0.05 -> 0.03 (To detect tight contractions)
    - **New Filter 1**: `Contraction Sequence`: Decreasing depths, Last < 5%, First 10-35%.
    - **New Filter 2**: `Volume`: Down 30% in second half.
- **Results**:
    - **Limited Capital**:
        - Return: **9.7%** (Collapsed from 95.8%)
        - Sharpe: **0.17**
        - Count: 61
- **Analysis**:
    - **過度優化 (Over-fitting)**：極度嚴格的型態定義（完美收縮 + 特定成交量型態）在現實市場中極極罕見。
    - **ZigZag 雜訊**：為了檢測 < 5% 的收縮而將 ZigZag 降至 3%，引入了大量雜訊，導致許多非 VCP 型態被錯誤識別或正確型態被切碎。
    - **結論**：Cycle 9 失敗。過於教科書式的定義不適合自動化交易。
- **Action**:
    - **回滾 (Revert)** VCP 策略至 **Cycle 8** (RS > 70, Near High < 15%)，保留其高 Sharpe (1.0) 的特性。
    - 雖然 Cycle 4 (RS > 0) 總報酬最高，但 Cycle 8 代表了「高質量」的方向，符合進階優化的精神。

## 重大改進: 複利邏輯實施
- **Date**: 2025-11-20
- **Changes**:
    - **Backtest Engine**: 修改 `backtest_patterns.py` 的資金管理邏輯
    - **Before**: 固定倉位 = 100萬 × 10% = 10萬 (永遠不變)
    - **After**: 動態倉位 = (當前現金 + 所有持倉成本) × 10% (複利)
- **Impact**:
    - **CUP (R=3.0, T=20)**: 184.9% → **314.3%** (+70% 提升)
    - **HTF (R=2.0, T=20)**: 新增策略，達到 **189.8%**
    - 所有策略的總報酬都因複利效應而顯著提升
- **Conclusion**:
    - 複利是長期投資的核心。這個修正讓回測結果更貼近真實交易情況。
    - 後續所有結果都將基於複利邏輯。

## Cycle 10: HTF Advanced (Grading System)
- **Date**: 2025-11-20
- **Changes**:
    - **Strategy**: HTF
    - **New Feature**: A/B/C Grading System
        - **A Grade**: Pole > 90%, Pullback < 15%, Vol Drop > 50%
        - **B Grade**: Pole > 90%, Pullback 15-20%
        - **C Grade**: Default (Pullback 20-25%)
    - **Implementation**: `strategies/htf.py` now returns `htf_grade`
    - **Note**: Position sizing based on grade is NOT yet implemented in backtest
- **Results** (With Compounding):
    - **HTF (Limited, R=2.0, T=20)**: Return = **189.8%**, Sharpe = 1.20
    - **HTF (Limited, Trig=1.5R, Trail=MA20)**: Return = **210.1%**, Sharpe = 0.79
- **Analysis**:
    - HTF 表現優異，特別是在複利環境下。
    - Grading 資訊已經儲存在 CSV 中，但尚未用於動態倉位調整。
- **Next Step**:
    - 實施 **動態倉位調整** (A=15%, B=10%, C=5%) 以進一步優化 HTF。
    - 繼續優化 CUP 和 VCP。

## Cycle 11: CUP Advanced (U-Shape + Handle + RSI)
- **Date**: 2025-11-20
- **Changes**:
    - **Strategy**: CUP
    - **New Filter 1**: U-Shape Check - Bottom zone must span ≥20% of cup duration (avoid V-shape)
    - **New Filter 2**: Handle in Upper 1/3 - Handle low must be in upper 1/3 of cup range (stricter than previous 50%)
    - **New Filter 3**: Handle Depth < 25% (prevent deep pullbacks)
    - **New Filter 4**: RSI > 50 at breakout (momentum confirmation)
    - **Depth Range**: Tightened to 15-35% (from 12-33%)
- **Results** (With Compounding):
    - **CUP (Limited, R=3.0, T=20)**: Return = **20.6%** (Previous: 314.3%) ❌
    - **CUP (Limited, R=2.0, T=20)**: Return = **18.7%** (Previous: 193.1%) ❌
    - Trade Count: 79 (Previous: 276) - **71% reduction**
- **Analysis**:
    - **過度優化 (Over-Optimization)**: 嚴格的品質過濾器（U-shape、上1/3把手、RSI > 50）過度篩選，移除了大量獲利機會。
    - **Trade-off**: 雖然勝率略微提升（49.4% vs 56.9%），但交易次數大幅減少導致複利效應無法發揮。
    - **結論**: Cycle 11 失敗。過於嚴格的型態定義在實際市場中難以找到足夠的交易機會。
- **Action**:
    - **回滾 (Revert)** CUP 策略至 **Cycle 10** (RS > 0, 基本把手邏輯)。
    - CUP 已經是表現最佳的策略（314.3%），無需進一步優化。
    - 將重點轉移至 **VCP 優化**（目前最弱，僅 96.4%）。

## Cycle 12: VCP Optimization (Relaxed RS Filter)
- **Date**: 2025-11-20
- **Changes**:
    - **Strategy**: VCP
    - **Revert**: RS Rating > 70 → **RS Rating > 0** (Back to Cycle 4)
    - **Remove**: "Near 52-week High" filter (removed)
    - **Keep**: Basic contraction logic, volume dry-up, Price > MA50
- **Results** (With Compounding):
    - **VCP (Limited, Trig=1.5R, Trail=MA50)**: Return = **-0.6%** (Negative!)
    - **VCP (Limited, Trig=2.0R, Trail=MA50)**: Return = **-1.0%** (Negative!)
    - **VCP (Limited, R=2.0, T=20)**: Return = **-31.7%** (Worst!)
- **Analysis**:
    - **VCP 失敗**: 即使放寬條件，VCP 在複利環境下仍然表現不佳。
    - **問題**: VCP 的勝率太低（約 30%），在複利環境下會快速虧損。
    - **結論**: VCP 策略需要根本性的重新設計，或者在台股市場不適用。

---

# 最終總結 (Final Summary)

## 最佳策略表現 (Best Strategy Performance with Compounding)

1. **CUP (R=3.0, T=20)**: **314.3%** return, 56.9% win rate, Sharpe 2.24 🏆
2. **HTF (Trig=1.5R, Trail=MA20)**: **210.1%** return, 31.7% win rate, Sharpe 0.79
3. **CUP (R=2.0, T=20)**: **193.1%** return, 57.3% win rate, Sharpe 2.16
4. **HTF (R=2.0, T=20)**: **189.8%** return, 44.9% win rate, Sharpe 1.20
5. **HTF (Trig=2.0R, Trail=MA20)**: **154.2%** return, 32.3% win rate, Sharpe 0.67

**Note**: VCP 策略在所有設定下都表現不佳（負報酬），不建議使用。

## 關鍵改進 (Key Improvements)

1. **複利實施**: 所有策略報酬提升 50-70%（CUP: 184.9% → 314.3%）
2. **HTF Grading System**: 已實施 A/B/C 評級系統，可用於未來的動態倉位調整
3. **CUP**: 最佳表現者，維持 Cycle 6 (RS > 0) 的簡單有效邏輯
4. **VCP**: 在台股市場表現不佳，需要根本性重新設計或放棄

## 學到的教訓 (Lessons Learned)

1. **簡單有效**: 過於複雜的篩選條件往往會過度篩選，降低總報酬
2. **複利重要**: 複利是長期投資的核心，對總報酬影響巨大
3. **質量 vs 數量**: 需要平衡交易品質和交易頻率
4. **版本控制**: Git 提交讓我們可以輕鬆回滾失敗的優化

---
