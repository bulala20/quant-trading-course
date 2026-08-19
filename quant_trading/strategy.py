"""可解释的教学策略。"""

from __future__ import annotations

import pandas as pd


def sma_crossover_signals(data: pd.DataFrame, fast: int = 20, slow: int = 60) -> pd.DataFrame:
    """计算双均线信号。

    target_position 是收盘后才知道的目标仓位，0 表示空仓，1 表示满仓做多。
    回测引擎会把它向后移动一根 K 线再执行，避免使用未来信息。
    """
    if fast <= 0 or slow <= 0:
        raise ValueError("fast and slow windows must be positive")
    if fast >= slow:
        raise ValueError("fast window must be smaller than slow window")
    if "Close" not in data:
        raise ValueError("data must contain a Close column")

    close = data["Close"].astype(float)
    fast_ma = close.rolling(fast, min_periods=fast).mean()
    slow_ma = close.rolling(slow, min_periods=slow).mean()
    target = (fast_ma > slow_ma).astype(float)
    target[slow_ma.isna()] = 0.0
    return pd.DataFrame(
        {
            "fast_ma": fast_ma,
            "slow_ma": slow_ma,
            "target_position": target,
            "signal": target.diff().fillna(target),
        },
        index=data.index,
    )
