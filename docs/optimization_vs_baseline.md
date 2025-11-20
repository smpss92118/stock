# Optimization vs Baseline Comparison Report
Generated: 2025-11-20

This report compares the results of the recent Hyperparameter Optimization (using the Robust Backtest Engine) against the original Baseline Report (`backtest_report_v2.md`).

## Summary

The optimization process successfully identified parameter sets that outperform or match the baseline configurations.

*   **HTF Strategy**: **Significant Improvement**. Annualized Return increased by **14.3%** and Sharpe Ratio by **0.28**.
*   **VCP Strategy**: **Improved Quality**. While Return is slightly higher (+1.8%), the **Win Rate doubled** (20% -> 40%) and Sharpe Ratio improved significantly (+0.31), indicating a much more stable strategy.
*   **CUP Strategy**: **Consistent High Performance**. The optimized results are comparable to the high baseline, confirming the strategy's robustness.

## Detailed Comparison Table (Limited Capital Mode)

| Strategy | Metric | Baseline (Best Config) | Optimized (Top 1) | Difference |
| :--- | :--- | :--- | :--- | :--- |
| **HTF** | **Ann. Return** | 56.3% | **70.6%** | 🟢 **+14.3%** |
| | **Sharpe** | 1.18 | **1.46** | 🟢 **+0.28** |
| | Win Rate | 44.4% | 45.0% | +0.6% |
| | *Best Params* | R=2.0, T=20 | *min_up=0.6, max_pb=0.15* | |
| | | | | |
| **VCP** | **Ann. Return** | 21.3% | **23.1%** | 🟢 +1.8% |
| | **Sharpe** | 0.45 | **0.76** | 🟢 **+0.31** |
| | **Win Rate** | 19.9% | **40.6%** | 🟢 **+20.7%** |
| | *Best Params* | Trig=1.5R, Trail=ma50 | *zig=0.07, min_up=0.5* | |
| | | | | |
| **CUP** | Ann. Return | **98.2%** | 93.1% | 🔴 -5.1% |
| | Sharpe | 2.19 | **2.20** | 🟢 +0.01 |
| | Win Rate | 57.4% | 53.8% | 🔴 -3.6% |
| | *Best Params* | R=3.0, T=20 | *rs=70, min_d=0.1* | |

## Key Takeaways

1.  **HTF Optimization Success**: The grid search found a "looser" configuration (`min_up_ratio=0.6`) that captures more opportunities without sacrificing quality, leading to higher total returns.
2.  **VCP Stability**: The optimized VCP parameters (`zigzag=0.07`) filter out noise much better, doubling the win rate. This makes the strategy psychologically much easier to trade, even if the total return is similar.
3.  **CUP Robustness**: The CUP strategy is very strong. The baseline parameters were already near-optimal, but the optimization confirms this high performance ceiling (~90%+ Ann. Return).

## Next Steps

*   Update the production strategy configurations in `src/strategies/` with these new "Optimized" parameters.
*   Consider running a "Walk-Forward" analysis to ensure these parameters are not overfitted.
