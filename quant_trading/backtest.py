"""带交易成本和基础风险指标的单标的回测引擎。"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Dict

import numpy as np
import pandas as pd

from .data import normalize_ohlcv
from .strategy import sma_crossover_signals


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 100_000.0
    fee_rate: float = 0.0003
    slippage_bps: float = 2.0

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.fee_rate < 0 or self.slippage_bps < 0:
            raise ValueError("fee_rate and slippage_bps cannot be negative")
        if self.fee_rate + self.slippage_bps / 10_000.0 >= 1:
            raise ValueError("fee_rate plus slippage must be smaller than 1")


@dataclass
class BacktestResult:
    frame: pd.DataFrame
    trades: pd.DataFrame
    metrics: Dict[str, float]


def _build_trades(frame: pd.DataFrame) -> pd.DataFrame:
    changes = frame["position"].diff().fillna(frame["position"])
    mask = changes.abs() > 0
    if not mask.any():
        return pd.DataFrame(columns=["Date", "action", "price", "position_after", "turnover"])
    trades = pd.DataFrame(
        {
            "Date": frame.loc[mask, "Date"].values,
            "action": np.where(changes.loc[mask] > 0, "BUY", "SELL"),
            "price": frame.loc[mask, "Close"].values,
            "position_after": frame.loc[mask, "position"].values,
            "turnover": changes.loc[mask].abs().values,
        }
    )
    return trades.reset_index(drop=True)


def _metrics(frame: pd.DataFrame, initial_cash: float, trades: pd.DataFrame) -> Dict[str, float]:
    equity = frame["equity"]
    daily_returns = frame["strategy_return"]
    total_return = equity.iloc[-1] / initial_cash - 1.0
    years = max(len(frame) / 252.0, 1.0 / 252.0)
    annualized_return = (1.0 + total_return) ** (1.0 / years) - 1.0
    running_max = equity.cummax()
    max_drawdown = (equity / running_max - 1.0).min()
    volatility = float(daily_returns.std(ddof=0) * sqrt(252))
    mean_return = float(daily_returns.mean())
    sharpe = mean_return / float(daily_returns.std(ddof=0)) * sqrt(252) if daily_returns.std(ddof=0) > 0 else 0.0
    non_zero_days = daily_returns[daily_returns != 0]
    win_rate = float((non_zero_days > 0).mean()) if not non_zero_days.empty else 0.0
    return {
        "initial_cash": float(initial_cash),
        "final_equity": float(equity.iloc[-1]),
        "total_return": float(total_return),
        "annualized_return": float(annualized_return),
        "max_drawdown": float(max_drawdown),
        "annualized_volatility": volatility,
        "sharpe_ratio": float(sharpe),
        "win_rate": win_rate,
        "trade_count": float(len(trades)),
        "days": float(len(frame)),
    }


def run_backtest(
    data: pd.DataFrame,
    fast: int = 20,
    slow: int = 60,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """执行单标的、只做多、按收盘价近似成交的双均线回测。"""
    config = config or BacktestConfig()
    clean = normalize_ohlcv(data)
    signals = sma_crossover_signals(clean, fast=fast, slow=slow)
    frame = clean.join(signals)
    frame["position"] = frame["target_position"].shift(1).fillna(0.0)
    frame["asset_return"] = frame["Close"].pct_change().fillna(0.0)
    frame["turnover"] = frame["position"].diff().abs().fillna(frame["position"].abs())
    cost_rate = config.fee_rate + config.slippage_bps / 10_000.0
    frame["trading_cost"] = frame["turnover"] * cost_rate
    frame["strategy_return"] = frame["position"] * frame["asset_return"] - frame["trading_cost"]
    frame["equity"] = config.initial_cash * (1.0 + frame["strategy_return"]).cumprod()
    frame["buy_and_hold_equity"] = config.initial_cash * (1.0 + frame["asset_return"]).cumprod()
    trades = _build_trades(frame)
    return BacktestResult(frame=frame, trades=trades, metrics=_metrics(frame, config.initial_cash, trades))
