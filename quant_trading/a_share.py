"""A 股日线研究回测：本地 CSV、整数股、T+1 和基础成交约束。"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Dict, Tuple

import pandas as pd

from .backtest import BacktestResult, _metrics
from .data import normalize_ohlcv
from .strategy import sma_crossover_signals


@dataclass(frozen=True)
class AShareConfig:
    """默认参数是研究起点，费用和涨跌停限制必须按证券与券商规则核对。"""

    initial_cash: float = 100_000.0
    buy_commission_rate: float = 0.0003
    sell_commission_rate: float = 0.0003
    min_commission: float = 5.0
    sell_stamp_duty_rate: float = 0.0005
    transfer_fee_rate: float = 0.00001
    slippage_bps: float = 2.0
    lot_size: int = 100
    price_limit_rate: float = 0.10

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.lot_size <= 0:
            raise ValueError("lot_size must be positive")
        if not 0 < self.price_limit_rate < 1:
            raise ValueError("price_limit_rate must be between 0 and 1")
        rates = (
            self.buy_commission_rate,
            self.sell_commission_rate,
            self.sell_stamp_duty_rate,
            self.transfer_fee_rate,
            self.slippage_bps,
            self.min_commission,
        )
        if any(rate < 0 for rate in rates):
            raise ValueError("fees, slippage, and min_commission cannot be negative")
        if self.buy_commission_rate + self.transfer_fee_rate + self.slippage_bps / 10_000 >= 1:
            raise ValueError("buy-side transaction costs must be smaller than 1")


def _boolean_series(data: pd.DataFrame, clean: pd.DataFrame) -> pd.Series:
    aliases = {str(column).strip().lower(): column for column in data.columns}
    suspended_column = aliases.get("suspended")
    if suspended_column is None:
        return pd.Series(False, index=clean.index, dtype=bool)

    source = data[[aliases.get("date", "Date"), suspended_column]].copy()
    source.columns = ["Date", "Suspended"]
    source["Date"] = pd.to_datetime(source["Date"], errors="coerce")
    values = source["Suspended"]
    if values.dtype == bool:
        source["Suspended"] = values
    else:
        source["Suspended"] = values.astype(str).str.strip().str.lower().isin({"1", "true", "yes", "y", "suspended", "停牌"})
    source = source.dropna(subset=["Date"]).drop_duplicates(subset=["Date"], keep="last")
    return clean[["Date"]].merge(source, on="Date", how="left")["Suspended"].fillna(False).astype(bool)


def _fees(gross_value: float, commission_rate: float, config: AShareConfig, is_sell: bool) -> Tuple[float, float, float]:
    commission = max(gross_value * commission_rate, config.min_commission) if gross_value else 0.0
    transfer_fee = gross_value * config.transfer_fee_rate
    stamp_duty = gross_value * config.sell_stamp_duty_rate if is_sell else 0.0
    return commission, transfer_fee, stamp_duty


def _max_buyable_shares(cash: float, execution_price: float, config: AShareConfig) -> int:
    estimated_rate = 1 + config.buy_commission_rate + config.transfer_fee_rate
    quantity = floor(cash / (execution_price * estimated_rate) / config.lot_size) * config.lot_size
    while quantity > 0:
        gross_value = quantity * execution_price
        commission, transfer_fee, _ = _fees(gross_value, config.buy_commission_rate, config, is_sell=False)
        if gross_value + commission + transfer_fee <= cash + 1e-8:
            return quantity
        quantity -= config.lot_size
    return 0


def _limit_block_reason(action: str, row: pd.Series, previous_close: float, config: AShareConfig) -> str:
    if bool(row["Suspended"]):
        return "SUSPENDED"
    if previous_close <= 0:
        return ""
    tolerance = 1e-8
    if action == "BUY" and row["Open"] >= previous_close * (1 + config.price_limit_rate - tolerance):
        return "LIMIT_UP"
    if action == "SELL" and row["Open"] <= previous_close * (1 - config.price_limit_rate + tolerance):
        return "LIMIT_DOWN"
    return ""


def run_a_share_backtest(
    data: pd.DataFrame,
    fast: int = 20,
    slow: int = 60,
    config: AShareConfig | None = None,
) -> BacktestResult:
    """运行单标的 A 股日线研究回测，不连接券商，也不生成任何实盘订单。"""
    config = config or AShareConfig()
    clean = normalize_ohlcv(data)
    clean["Suspended"] = _boolean_series(data, clean)
    signals = sma_crossover_signals(clean, fast=fast, slow=slow)
    frame = clean.join(signals)
    frame["desired_position"] = frame["target_position"].shift(1).fillna(0.0)
    frame["previous_close"] = frame["Close"].shift(1)

    cash = config.initial_cash
    shares = 0
    previous_equity = config.initial_cash
    records = []
    trades = []

    for _, row in frame.iterrows():
        desired_position = int(row["desired_position"])
        action = ""
        if desired_position == 1 and shares == 0:
            action = "BUY"
        elif desired_position == 0 and shares > 0:
            action = "SELL"

        blocked_reason = _limit_block_reason(action, row, row["previous_close"], config) if action else ""
        executed_shares = 0
        commission = 0.0
        transfer_fee = 0.0
        stamp_duty = 0.0
        execution_price = 0.0
        slippage_cost = 0.0

        if action == "BUY" and not blocked_reason:
            execution_price = float(row["Open"]) * (1 + config.slippage_bps / 10_000)
            executed_shares = _max_buyable_shares(cash, execution_price, config)
            if executed_shares == 0:
                blocked_reason = "INSUFFICIENT_CASH"
            else:
                gross_value = executed_shares * execution_price
                commission, transfer_fee, _ = _fees(gross_value, config.buy_commission_rate, config, is_sell=False)
                cash -= gross_value + commission + transfer_fee
                shares += executed_shares
                slippage_cost = executed_shares * (execution_price - float(row["Open"]))
        elif action == "SELL" and not blocked_reason:
            execution_price = float(row["Open"]) * (1 - config.slippage_bps / 10_000)
            executed_shares = shares
            gross_value = executed_shares * execution_price
            commission, transfer_fee, stamp_duty = _fees(gross_value, config.sell_commission_rate, config, is_sell=True)
            cash += gross_value - commission - transfer_fee - stamp_duty
            shares -= executed_shares
            slippage_cost = executed_shares * (float(row["Open"]) - execution_price)

        if executed_shares:
            trades.append(
                {
                    "Date": row["Date"],
                    "action": action,
                    "shares": executed_shares,
                    "price": execution_price,
                    "gross_value": executed_shares * execution_price,
                    "commission": commission,
                    "transfer_fee": transfer_fee,
                    "stamp_duty": stamp_duty,
                    "slippage_cost": slippage_cost,
                }
            )

        equity = cash + shares * float(row["Close"])
        strategy_return = equity / previous_equity - 1.0
        records.append(
            {
                "cash": cash,
                "shares": shares,
                "market_value": shares * float(row["Close"]),
                "position": float(shares * float(row["Close"]) / equity) if equity else 0.0,
                "execution_action": action,
                "executed_shares": executed_shares,
                "execution_price": execution_price,
                "blocked_reason": blocked_reason,
                "commission": commission,
                "transfer_fee": transfer_fee,
                "stamp_duty": stamp_duty,
                "slippage_cost": slippage_cost,
                "trading_cost": commission + transfer_fee + stamp_duty + slippage_cost,
                "equity": equity,
                "strategy_return": strategy_return,
            }
        )
        previous_equity = equity

    execution_frame = pd.DataFrame(records, index=frame.index)
    frame = frame.join(execution_frame)
    frame["asset_return"] = frame["Close"].pct_change().fillna(0.0)
    frame["buy_and_hold_equity"] = config.initial_cash * frame["Close"] / float(frame.loc[0, "Close"])
    trades_frame = pd.DataFrame(
        trades,
        columns=[
            "Date",
            "action",
            "shares",
            "price",
            "gross_value",
            "commission",
            "transfer_fee",
            "stamp_duty",
            "slippage_cost",
        ],
    )
    metrics: Dict[str, float] = _metrics(frame, config.initial_cash, trades_frame)
    metrics["blocked_signal_days"] = float((frame["blocked_reason"] != "").sum())
    return BacktestResult(frame=frame, trades=trades_frame, metrics=metrics)
