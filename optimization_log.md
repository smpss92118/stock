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

---
