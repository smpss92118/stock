# 三大法人數據增強實驗

**目標**: 測試三大法人數據對 ML 系統的效益提升

---

## 📊 數據來源

### TWSE (上市股票)
- **URL**: https://www.twse.com.tw/fund/T86
- **內容**: 外資、投信、自營商每日買賣超
- **格式**: CSV
- **可用期間**: 2004/10/01 - 現在

### TPEX (上櫃股票)
- **URL**: https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge.php
- **內容**: 三大法人每日買賣超  
- **格式**: CSV
- **可用期間**: 2012/04/01 - 現在

---

## 🎯 實驗目標

1. ✅ 爬取三大法人歷史數據
2. ✅ 設計新特徵
3. ✅ 實作 Ensemble Learning
4. ✅ 實作 AutoML
5. ✅ 回測驗證效益

**成功指標**:
- 年化報酬: 156% → 170%+
- Sharpe: 2.59 → 2.8+

---

## 📁 目錄說明

```
crawlers/          # 數據爬蟲
├── fetch_institution.py     # 單日爬取
└── backfill_history.py      # 補齊歷史

data/
├── raw/           # 原始 CSV
└── processed/     # 清理後數據

features/          # 特徵工程
└── institution_features.py

models/            # 模型實驗
├── ensemble.py    # Ensemble Learning
└── automl.py      # AutoML

notebooks/         # Jupyter 分析

results/           # 回測結果
```

---

## 🚀 執行順序

1. `python crawlers/fetch_institution.py --date 2024-11-21`
2. `python crawlers/backfill_history.py --start 2020-01-01 --end 2024-11-21`
3. `python features/institution_features.py`
4. `python models/ensemble.py`
5. `python models/automl.py`

---

**下一步**: 開始建立爬蟲
