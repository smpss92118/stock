# CUP GOD MODE - 邏輯修正版 (Fixed Logic)

**說明**：此版本修正了現金流重複計算問題，並採用正確的部位規模計算 (Current Equity * 10%)。

執行時間: 1277.6秒

| Strategy                 | Final Equity   |   Total Return % |   Max Drawdown % |   Trades |
|:-------------------------|:---------------|-----------------:|-----------------:|---------:|
| PARTIAL 3R + MA20 (60d)  | 6,985          |            -99.3 |            99.3  |      169 |
| PARTIAL 2R + MA20 (60d)  | 46             |           -100   |            99.99 |      239 |
| PURE MA20 TRAILING (60d) | 0              |           -100   |           100    |      888 |