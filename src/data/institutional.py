import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Optional

INSTITUTIONAL_COLUMNS: List[str] = [
    "date",
    "sid",
    "name",
    "foreign_buy",
    "foreign_sell",
    "foreign_net",
    "investment_buy",
    "investment_sell",
    "investment_net",
    "dealer_net",
    "total_net",
    "exchange",
]


def load_institutional_raw(data_dir: str = "data/raw/institutional") -> Optional[pd.DataFrame]:
    """
    讀取並合併機構買賣超原始資料。
    - 轉換 date 為 datetime
    - sid 保持字串
    - 數值欄位 coercion 為數值並以 0 補缺
    - 按 sid、date 排序
    """
    path = Path(data_dir)
    files = sorted(path.glob("institution_*.csv"))
    if not files:
        return None

    dfs = []
    for f in files:
        df = pd.read_csv(f)
        dfs.append(df)

    data = pd.concat(dfs, ignore_index=True)
    data["date"] = pd.to_datetime(data["date"])
    data["sid"] = data["sid"].astype(str)

    num_cols = [c for c in data.columns if c not in ["date", "sid", "name", "exchange"]]
    for col in num_cols:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data[num_cols] = data[num_cols].fillna(0)

    data = data.sort_values(["sid", "date"]).reset_index(drop=True)
    return data


def compute_institutional_features(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    產生避免洩漏的機構買賣特徵（僅使用當日以前資訊）。
    回傳含原始欄位與新特徵的 DataFrame（sid, date 唯一）。
    """
    if raw_df is None or raw_df.empty:
        return pd.DataFrame()

    base_cols = ["foreign_net", "investment_net", "dealer_net", "total_net"]
    windows = [3, 5, 10, 20]

    groups = []
    for sid, grp in raw_df.groupby("sid"):
        grp = grp.sort_values("date").copy()

        # 前一日淨買賣
        for col in base_cols:
            grp[f"{col}_lag1"] = grp[col].shift(1)

        # 過去 N 日滾動和（不含當日）
        shifted = grp[base_cols].shift(1)
        for w in windows:
            rolled = shifted.rolling(window=w, min_periods=1).sum()
            for col in base_cols:
                grp[f"{col}_sum_{w}d"] = rolled[col]

        # 參與者關係特徵
        grp["foreign_investment_spread_lag1"] = grp["foreign_net_lag1"] - grp["investment_net_lag1"]
        denom = grp["total_net_lag1"].replace(0, np.nan)
        grp["dealer_dominance_lag1"] = grp["dealer_net_lag1"] / denom
        grp["dealer_dominance_lag1"] = grp["dealer_dominance_lag1"].fillna(0)

        groups.append(grp)

    feat_df = pd.concat(groups, ignore_index=True)
    return feat_df
