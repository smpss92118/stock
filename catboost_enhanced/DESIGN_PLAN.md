# CatBoost Enhanced - 重构设计规划 (v1.0)

**日期**: 2025-11-22
**目标**: 从碎片化的 9 模型系统升级到全局 CatBoost 模型，融合三大核心改进：P0（全局）、P1（数据隔离）、P2（目标函数）

---

## 📋 Executive Summary

### 现状问题
- **ml_enhanced**: 按 pattern × exit_mode 切分成 9 个独立 XGBoost 模型，每个仅 ~3000 样本，容易过拟合
- **catboost_enhanced**: 已有全局模型框架，但缺少严格的数据隔离、缺乏评分感知的权重设计
- **特征与标签**: 两套系统的 score 计算和标签生成逻辑重复，特征对齐存疑

### 改进目标
| 维度 | 当前 | 目标 | 预期收益 |
|------|-----|------|--------|
| **P0: 样本量** | 3000/model | 36,823/model | 过拟合↓, 稳定性↑ |
| **P1: 数据隔离** | walk-forward 无 embargo | PurgedGroupKFold (20day embargo) | Label leak ↓ |
| **P2: 目标函数** | 简单二分类 + class weight | Ordinal + score-aware weight + class weight | A 类捕捉↑, 虚假信号↓ |
| **部署** | 两套独立系统 | 单一全局模型 + 两套报告 | 维护成本↓, 一致性↑ |

---

## 🎯 三大核心改进（优先级）

### **P0: 全局模型 (Global Model)**

#### 问题分析
```
当前 ml_enhanced:
  for pattern in ['HTF', 'CUP', 'VCP']:
      for exit in ['fixed_r2_t20', 'fixed_r3_t20', 'trailing_15r']:
          # 训练 1 个模型 (pattern × exit)
          # 样本数: ~3000 (样本少 → 易过拟合)
          # 特征是否对齐? → 不清楚

目标 catboost_enhanced:
  # 训练 1 个全局模型
  # pattern_type, exit_mode → categorical features (不分割数据)
  # 样本数: 36,823 (3000×9 通过 categorical encoding)
  # 学习能力: 跨 pattern 学习共性 + 跨 exit 学习最优组合
```

#### 设计方案

**方案A: CatBoostClassifier (推荐)**
```python
# catboost_enhanced/scripts/train.py

from catboost import CatBoostClassifier, Pool

model = CatBoostClassifier(
    # === 基础配置 ===
    loss_function='MultiClass',
    classes_for_smooth_cat=4,  # D=0, C=1, B=2, A=3

    # === 类别特征 (避免数值化) ===
    cat_features=['pattern_type', 'exit_mode', 'ma_trend'],

    # === 类权重 (基础) ===
    class_weights=[1.0, 1.0, 1.5, 2.0],  # D, C, B, A

    # === 超参数 ===
    iterations=2000,
    learning_rate=0.05,
    depth=6,
    verbose=100,

    # === 数据泄漏防护 ===
    # 交叉验证采用 PurgedGroupKFold (见 P1)
)

# 特别: 样本权重来自 P2 (见下)
model.fit(
    X_train, y_train,
    sample_weight=compute_sample_weights(df_train),  # ⭐ 关键
    eval_set=[(X_test, y_test)],
)
```

**预期收益**:
- 样本量 3000 → 36,823 (12倍), 过拟合大幅下降
- CatBoost 对 categorical feature 的处理优于 one-hot encoding
- 跨 pattern 学习: 例如"高成交量通常利好"适用于所有形态
- 跨 exit 学习: 找到最优的 exit_mode 组合

---

### **P1: 数据隔离 (Embargo/Purging)**

#### 问题分析
```
当前 ml_enhanced (train_models.py):
  # 时间序列分割
  split_idx = len(df) * 0.8  # 80% train, 20% test
  train_df = df.iloc[:split_idx]
  test_df = df.iloc[split_idx:]

  # 问题: 没有 embargo
  # - train 最后一天和 test 第一天，数据可能重叠
  # - label = "未来 20 天收益率" → test 的 feature 可能"看到"train 的未来
  # - Walk-forward 窗口间可能有 label leak

目标:
  # 日期粒度的严格隔离
  # test 的第一天 ≥ train 的最后一天 + 20天(embargo)
  # 原因: predict horizon = 20 days, 需要额外 buffer
```

#### 设计方案

**实现 PurgedGroupKFold**
```python
# catboost_enhanced/utils/data_splitter.py

class PurgedGroupKFold:
    def __init__(self, n_splits=5, embargo_pct=0.05):
        """
        n_splits: 交叉验证折数 (默认 5)
        embargo_pct: embargo 占总日期数的比例
                     假设 20 天 embargo, 总 ~400 trading days/year
                     → embargo_pct ≈ 20/400 = 0.05 (5%)
        """
        self.n_splits = n_splits
        self.embargo_pct = embargo_pct

    def split(self, df, groups=None):
        """
        df: 数据集 (包含 'date' 列)
        groups: df['date'] (每行的交易日期)

        yield: (train_indices, test_indices)

        不变量:
        1. max(train_date) + embargo_days <= min(test_date)
        2. 所有 fold 都满足上述条件
        """
        unique_dates = sorted(df[groups].unique())
        n_dates = len(unique_dates)
        embargo_size = max(1, int(n_dates * self.embargo_pct))

        # Walk-forward 分割
        for fold_idx in range(self.n_splits):
            # 测试集范围 (日期索引)
            test_start_idx = fold_idx * n_dates // self.n_splits
            test_end_idx = (fold_idx + 1) * n_dates // self.n_splits

            # 训练集范围 (应用 embargo)
            train_end_idx = test_start_idx - embargo_size

            if train_end_idx <= 0:
                continue  # 第一个 fold 可能没有训练数据

            train_dates = unique_dates[:train_end_idx]
            test_dates = unique_dates[test_start_idx:test_end_idx]

            # 转换回样本索引
            train_indices = df[df['date'].isin(train_dates)].index.to_numpy()
            test_indices = df[df['date'].isin(test_dates)].index.to_numpy()

            yield train_indices, test_indices

# 使用示例:
from catboost_enhanced.utils.data_splitter import PurgedGroupKFold

cv = PurgedGroupKFold(n_splits=5, embargo_pct=0.05)

for fold, (train_idx, test_idx) in enumerate(cv.split(df, groups=df['date'])):
    # 验证: 没有数据泄漏
    last_train_date = df.iloc[train_idx]['date'].max()
    first_test_date = df.iloc[test_idx]['date'].min()
    gap = (first_test_date - last_train_date).days

    assert gap >= embargo_days, f"Fold {fold}: gap={gap}天, 小于 embargo_days={embargo_days}"
    print(f"✓ Fold {fold}: gap={gap}天 (符合 embargo 要求)")

    # 训练
    X_train, y_train = df.iloc[train_idx][feature_cols], df.iloc[train_idx]['label']
    X_test, y_test = df.iloc[test_idx][feature_cols], df.iloc[test_idx]['label']

    model.fit(X_train, y_train)
    # ...
```

**参数建议**:
```python
# 基于您的设置
embargo_days = 20  # 预测窗口长度
trading_days_per_year = 240  # ~1年 trading days
total_years = 1.5  # 数据跨度
total_trading_days = trading_days_per_year * total_years ≈ 360

embargo_pct = embargo_days / total_trading_days ≈ 0.056 ≈ 0.05
```

**预期收益**:
- 消除 label leak: test feature 不会"看到"train future
- 回测结果真实可信 (Sharpe, Sortino 不会虚高)
- CV folds 间的 generalization gap 更小 (如果模型真的有效)

---

### **P2: 目标函数与样本权重**

#### 问题分析
```
当前目标变量设计:
  is_winner = 1 if label in ['A', 'B'] else 0
  → 二分类问题

问题:
1. 信息损失: 丢弃了 A/B 的顺序、C/D 的顺序
   - 预测 B 和预测 A 的价值不同，但损失相同

2. 类别不平衡: A 类极少 (~10-15%)
   - 模型倾向于预测 D (最保守)
   - 高分 A 类信号被淹没

3. 忽视"效率": score 的绝对值被忽略
   - score = -10%/day 和 score = 0%/day 同等对待
   - 高风险交易应该有更高的学习权重 (regardless 赢输)

改进目标:
  1. 四分类 (ABCD) + ordinal loss: A > B > C > D
  2. 样本权重基于 |score|: 强制关注"高效率交易"
  3. 类权重: A/B 权重 > C/D (反映稀有性)
```

#### 设计方案

**1. 多层损失函数**

```python
# catboost_enhanced/utils/loss_functions.py

def compute_sample_weights(df_train):
    """
    根据 score 的绝对值 + 标签计算样本权重

    设计原理:
    1. score 幅度权重: |score| 越大，权重越高
       - 原因: 高效率交易 (正或负) 比低效率更值得学习
       - 使用 sigmoid 避免极端值主导

    2. 标签权重: A > B > C ≥ D
       - 原因: 稀有性和学习价值不同

    3. 类别平衡补偿: 按照类频率开平方根调整
       - 原因: 避免过度补偿

    4. 标准化: 使得 mean(weights) = 1
    """

    # === 第一层: 基于 |score| 的幅度 ===
    # sigmoid(|score| * 2) 映射到 [0.5, 1)
    score_magnitude = np.abs(df_train['score'])
    score_weights = 1 / (1 + np.exp(-score_magnitude * 2))

    # === 第二层: 基于标签 ===
    label_weight_map = {
        0: 1.0,   # D: 底部
        1: 1.0,   # C: 中下
        2: 1.5,   # B: 中上 (稀有+重要)
        3: 2.0,   # A: 顶部 (最稀有+最重要)
    }
    class_weights = df_train['label'].map(label_weight_map)

    # === 第三层: 结合两层 ===
    combined_weights = score_weights * class_weights

    # === 第四层: 类别平衡补偿 ===
    for label in [0, 1, 2, 3]:
        mask = df_train['label'] == label
        count = mask.sum()
        if count > 0:
            # 频繁的类 (C/D) 权重下调; 稀有的类 (A/B) 权重上调
            combined_weights[mask] /= np.sqrt(count)

    # === 标准化 ===
    return combined_weights / combined_weights.mean()


def verify_sample_weights(weights, df_train):
    """验证权重分布是否合理"""
    print("样本权重统计:")
    print(f"  Mean: {weights.mean():.4f} (应接近 1.0)")
    print(f"  Std:  {weights.std():.4f}")
    print(f"  Min:  {weights.min():.4f}")
    print(f"  Max:  {weights.max():.4f}")

    for label in [0, 1, 2, 3]:
        mask = df_train['label'] == label
        print(f"  Label {label} (n={mask.sum()}):"
              f" mean={weights[mask].mean():.4f}, "
              f"max={weights[mask].max():.4f}")
```

**2. Ordinal Loss (可选进阶)**

```python
# 原理: 如果真实是 D (0) 但预测为 A (3),
#       rank distance = 3, loss 更大
#       如果预测为 C (1), rank distance = 1, loss 更小

# 实现方法 (CatBoost 无内置 ordinal loss, 但可以通过 custom metric):
def ordinal_loss(y_true, y_pred):
    """Ordinal: A (3) > B (2) > C (1) > D (0)"""
    rank_distance = np.abs(y_true - y_pred)  # L1 distance
    return rank_distance  # CatBoost 会计算平均

# 在 CatBoost 中使用自定义 loss:
# model = CatBoostClassifier(
#     loss_function='MultiClass',  # 主损失
#     custom_loss=['Accuracy'],     # 辅助 metric
# )

# 或者, 通过修改 sample_weight 模拟 ordinal 效果:
def simulate_ordinal_with_weights(df_train, base_weights):
    """
    通过加权来模拟 ordinal loss
    如果数据中存在很多"预测错误 1 级别" vs "预测错误 3 级别",
    可以在准备数据时就调整权重。

    此处简化: 仅用基础的 sample_weight
    """
    return base_weights
```

**3. CatBoost 配置**

```python
# catboost_enhanced/configs/model_config.py

CATBOOST_PARAMS = {
    # === 基础 ===
    'loss_function': 'MultiClass',
    'classes_for_smooth_cat': 4,

    # === 类别特征 (避免 one-hot encoding) ===
    'cat_features': ['pattern_type', 'exit_mode', 'ma_trend'],

    # === 类权重 (基础, 不考虑 sample_weight) ===
    'class_weights': [1.0, 1.0, 1.5, 2.0],  # D, C, B, A

    # === 超参数 ===
    'iterations': 2000,
    'learning_rate': 0.05,
    'depth': 6,
    'l2_leaf_reg': 3,
    'bagging_temperature': 1.0,
    'random_strength': 1,

    # === 验证 ===
    'eval_metric': 'MultiClass',
    'verbose': 100,
    'early_stopping_rounds': 100,
}

# 在训练时应用:
model = CatBoostClassifier(**CATBOOST_PARAMS)
model.fit(
    X_train, y_train,
    sample_weight=compute_sample_weights(df_train),  # ⭐ 关键
    eval_set=[(X_test, y_test)],
    # eval_set 的权重不传 (只用于监控, 不更新权重)
)
```

**预期收益**:
- A 类捕捉率提升 (从 baseline ~50% 提升到 60%+)
- 虚假信号减少 (D 类被误分为 A 的概率下降)
- 模型更关注"高效率交易"而非"都预测 C" 的懒惰策略

---

## 🏗️ 目录重构设计

### 新的 catboost_enhanced 结构

```
/Users/sony/ml_stock/stock/catboost_enhanced/
├── README.md                              # 系统说明
├── DESIGN_PLAN.md                         # 本文档
│
├── configs/                               # ⭐ 新增: 配置管理
│   ├── __init__.py
│   ├── constants.py                       # Pattern/Exit/Label 常量
│   ├── model_config.py                    # 模型参数 (weight/loss)
│   └── feature_config.py                  # 特征列表
│
├── scripts/                               # 核心训练脚本
│   ├── __init__.py
│   ├── prepare_catboost_data.py           # ⭐ 新增: 数据准备 (复用 ml_enhanced)
│   ├── train.py                           # ⭐ 优化: P0+P1+P2 全局训练
│   ├── run_catboost_backtest.py           # ⭐ 新增: 回测验证
│   └── daily_scan.py                      # ⭐ 优化: 日常预测
│
├── utils/                                 # ⭐ 新增/扩展: 辅助函数
│   ├── __init__.py
│   ├── data_splitter.py                   # PurgedGroupKFold
│   ├── loss_functions.py                  # compute_sample_weights etc
│   ├── metrics.py                         # 评估指标 (NDCG, AUC等)
│   └── feature_alignment.py               # 特征对齐检查
│
├── weekly_retrain.py                      # ⭐ 新增: 周期自动化 (两套模型)
├── daily_ml_scanner.py                    # ⭐ 新增: 日常扫描 (两套报告)
│
├── models/                                # 模型存储
│   ├── catboost_global.cbm                # 全局模型
│   ├── feature_info.pkl                   # 特征元数据
│   └── model_metrics.json                 # 训练指标
│
├── data/                                  # 训练数据
│   ├── catboost_features.csv              # 完整特征集
│   ├── train_indices.pkl                  # 训练索引
│   └── test_indices.pkl                   # 测试索引
│
└── results/                               # 输出结果
    ├── feature_importance.csv
    ├── cv_metrics.csv
    ├── backtest_results.csv
    └── daily_reports/
        └── YYYY-MM-DD/
            └── catboost_daily_summary.md
```

### 与 ml_enhanced 共享的模块

需要抽取到 `src/ml/` 的通用部分:

```python
# src/ml/constants.py (新建)
PATTERN_TYPES = ['htf', 'cup', 'vcp']
EXIT_MODES = ['fixed_r2_t20', 'fixed_r3_t20', 'trailing_15r']
LABEL_RULES = {
    'A': (0.75, 1.0),   # Q75 - Q100
    'B': (0.50, 0.75),  # Q50 - Q75
    'C': (0.25, 0.50),  # Q25 - Q50
    'D': (0.00, 0.25),  # Q0 - Q25
}

# src/ml/labeling.py (新建)
def compute_score(profit_pct, holding_days):
    """计算效率分数"""
    return (profit_pct * 100) / holding_days

def assign_label(score, q25, q50, q75):
    """基于四分位数分配标签"""
    if score >= q75: return 'A'
    elif score >= q50: return 'B'
    elif score >= q25: return 'C'
    else: return 'D'

# src/ml/simulation.py (新建)
def simulate_trade_fixed(...): ...
def simulate_trade_trailing(...): ...
```

---

## 📝 任务清单与优先级

### 第一阶段: 基础设置 (Week 1)

- [ ] **Task 1.1**: 创建 `src/ml/constants.py` 和 `src/ml/labeling.py`
  - 输出: 统一的 PATTERN_TYPES, EXIT_MODES, 标签生成函数
  - 依赖: 无

- [ ] **Task 1.2**: 创建 `catboost_enhanced/configs/` 目录结构
  - 创建 `constants.py`, `model_config.py`, `feature_config.py`
  - 输出: 配置文件 + 模型参数中央管理
  - 依赖: Task 1.1

- [ ] **Task 1.3**: 创建 `catboost_enhanced/utils/` 并实现 core 函数
  - `data_splitter.py` (PurgedGroupKFold)
  - `loss_functions.py` (compute_sample_weights)
  - `metrics.py` (评估指标)
  - 输出: 可重用的工具库
  - 依赖: Task 1.1, 1.2

### 第二阶段: 核心训练管道 (Week 2-3)

- [ ] **Task 2.1**: 创建 `catboost_enhanced/scripts/prepare_catboost_data.py`
  - 复用 `ml_enhanced/scripts/prepare_ml_data.py` 的逻辑
  - 输出: `catboost_enhanced/data/catboost_features.csv`
  - 依赖: Task 1.1, 1.3

- [ ] **Task 2.2**: 优化 `catboost_enhanced/scripts/train.py`
  - 实现 P0 (全局模型, pattern/exit 作为特征)
  - 实现 P1 (PurgedGroupKFold + embargo)
  - 实现 P2 (样本权重 + 类权重)
  - 输出: `catboost_global.cbm` + `feature_info.pkl`
  - 依赖: Task 2.1, 1.3

- [ ] **Task 2.3**: 创建 `catboost_enhanced/scripts/run_catboost_backtest.py`
  - 实现与 `ml_enhanced/run_ml_backtest.py` 一致的回测逻辑
  - 输出: `catboost_backtest_results.csv`
  - 依赖: Task 2.2

### 第三阶段: 自动化与报告 (Week 3-4)

- [ ] **Task 3.1**: 创建 `catboost_enhanced/weekly_retrain.py`
  - 调用 prepare → train → backtest
  - 同时更新两套模型 (ml_enhanced + catboost_enhanced)
  - 输出: 模型权重 + 指标
  - 依赖: Task 2.1, 2.2, 2.3

- [ ] **Task 3.2**: 创建 `catboost_enhanced/daily_ml_scanner.py`
  - 生成两套推荐清单 (ml_enhanced + catboost_enhanced)
  - 输出: `ml_daily_summary.md` + `catboost_daily_summary.md`
  - 依赖: Task 2.2

- [ ] **Task 3.3**: 优化 cron 任务配置
  - 更新 crontab 或任务调度配置
  - 确保 weekly_retrain 和 daily_scanner 配合工作
  - 依赖: Task 3.1, 3.2

### 第四阶段: 验证与对比 (Week 4)

- [ ] **Task 4.1**: 对比 ml_enhanced vs catboost_enhanced
  - 回测性能对比 (Sharpe, Max DD, Win Rate 等)
  - 样本权重分析 (权重分布, 标签分布)
  - 特征重要性对比
  - 输出: 对比报告 + 可视化

- [ ] **Task 4.2**: 性能优化与调参
  - 根据对比结果调整 embargo_pct, class_weights, learning_rate 等
  - 测试不同的 ordinal loss 设计

- [ ] **Task 4.3**: 文档和监控
  - 更新 README, DESIGN_PLAN
  - 设置监控告警 (模型漂移检测)

---

## ⚠️ 改进建议与风险点

### 高优先级 (必须处理)

1. **特征对齐** (Task 1.3, 2.1)
   - 风险: ml_enhanced 和 catboost_enhanced 的特征列不同步
   - 对策:
     - 使用单一的 FEATURE_COLS 定义 (via config)
     - 在 prepare_*_data.py 开始时验证特征列顺序和类型
     - 保存 feature_info.pkl (名称 + dtype + 顺序)

2. **数据泄漏验证** (Task 1.3, 2.2)
   - 风险: PurgedGroupKFold 实现有 bug, embargo 没有真正生效
   - 对策:
     - 实现验证函数 (见 P1 设计中的 assert gap >= embargo_days)
     - 在每次训练前打印 fold 的日期范围和 gap
     - 对比有 embargo vs 无 embargo 的 CV 结果差异

3. **样本权重分布** (Task 1.3, 2.2)
   - 风险: compute_sample_weights 算法不稳定, 导致训练发散
   - 对策:
     - 实现 verify_sample_weights() 函数 (见 P2 设计)
     - 在训练前打印权重统计: mean, std, min, max, per-label
     - 对极端权重的样本进行检查 (如 |score| 很大的样本)

### 中优先级 (优化空间)

4. **CV 策略的一致性** (Task 2.2 vs ml_enhanced 的 train_models.py)
   - ml_enhanced 当前: 3month window + 1month test (不同 K 值)
   - catboost: PurgedGroupKFold (K=5)
   - 建议: 在对比时都用同一个 CV 策略

5. **Ordinal Loss** (Task 1.3)
   - 当前: 仅通过 sample_weight 模拟
   - 可选: 实现完整的 ordinal loss (需要自定义 gradient)
   - 不紧急: 先验证 sample_weight 的效果

6. **类权重的自适应调整** (Task 1.2)
   - 当前: 硬编码 [1.0, 1.0, 1.5, 2.0]
   - 改进: 基于实际类频率动态调整
   - 例如:
     ```python
     class_freq = df['label'].value_counts()
     class_weights = {
         0: 1.0 / (class_freq[0] + 1e-5),
         1: 1.0 / (class_freq[1] + 1e-5),
         2: 1.5 / (class_freq[2] + 1e-5),
         3: 2.0 / (class_freq[3] + 1e-5),
     }
     # 标准化使 mean = 1.0
     ```

### 低优先级 (长期)

7. **特征工程优化** (Task 2.1)
   - 新增 momentum indicators, market regime features
   - 但前期不推荐: 先验证核心 P0/P1/P2 的效果

8. **Hyperparameter Tuning** (Task 4.2)
   - 使用 Optuna 或 GridSearch 自动调参
   - 目标: maximize NDCG@10 或 Sharpe ratio

---

## 📊 预期回测效果

基于重构设计, 预期以下改进:

| 指标 | ml_enhanced | catboost_enhanced | 改进 |
|------|-----------|------------------|------|
| **样本量** | 3000/model | 36,823 global | 12倍 |
| **过拟合倾向** | 中等 | 低 | ✓ |
| **数据泄漏** | 可能存在 | 避免 (embargo) | ✓ |
| **A类捕捉率** | ~50% | 60%+ (目标) | ✓ |
| **虚假信号率** | ~30% | 20%+ (目标) | ✓ |
| **Sharpe Ratio** | baseline | baseline * 1.05-1.15 | ✓ |
| **Max Drawdown** | baseline | baseline * 0.9-0.95 | ✓ |

---

## ✅ 验收标准

### Task 完成标准

每个 Task 完成时应满足:

1. **代码质量**
   - 有清晰的 docstring 和注释
   - 遵循项目的 code style (见 CLAUDE.md)
   - 通过 linting 检查

2. **功能正确性**
   - 单元测试通过 (主要函数)
   - 输出文件的格式和内容符合预期
   - 与 ml_enhanced 的对应部分对齐

3. **性能基准**
   - 特征工程时间 < 30s
   - 模型训练时间 < 5 分钟 (含 CV)
   - 日常扫描时间 < 2 分钟

4. **文档**
   - 更新 README 或任务文档
   - 记录关键设计决策和参数

### 全项目完成标准

1. 两套系统 (ml_enhanced + catboost_enhanced) 的日报告一致性 > 90%
2. 回测 Sharpe ratio 对比: catboost >= ml_enhanced * 0.95 (不差于 5%)
3. 自动化成功率: weekly_retrain 和 daily_scanner 连续 4 周无失败
4. 代码重复度: < 20% (通过 src/ml 的共享库降低)

---

## 📚 参考资源

### 相关文件
- `ml_enhanced/scripts/prepare_ml_data.py` - score/label 计算参考
- `ml_enhanced/scripts/train_models.py` - feature_cols 定义
- `catboost_enhanced/scripts/train.py` - 现有 PurgedGroupKFold 实现

### CatBoost 官方文档
- [CatBoost MultiClass](https://catboost.ai/docs/concepts/loss-functions-multiclass)
- [CatBoost Categorical Features](https://catboost.ai/docs/concepts/categorical-features)
- [CatBoost Custom Metrics](https://catboost.ai/docs/concepts/custom-metric)

### 量化金融参考
- Purged K-Fold: Lopéz de Prado, M. (2018). Advances in Financial Machine Learning
- Sample Weighting: Bergstra & Bengio (2012). Random Search for Hyper-Parameter Optimization

---

**文档版本**: v1.0
**更新日期**: 2025-11-22
**所有者**: 用户
**状态**: 待审批与执行
