"""命令行入口：demo 生成合成数据，backtest 回测用户 CSV。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from .a_share import AShareConfig, run_a_share_backtest
from .backtest import BacktestConfig, BacktestResult, run_backtest
from .data import generate_synthetic_data, load_ohlcv_csv


METRIC_LABELS = {
    "initial_cash": "Initial cash",
    "final_equity": "Final equity",
    "total_return": "Total return",
    "annualized_return": "Annualized return",
    "max_drawdown": "Max drawdown",
    "annualized_volatility": "Annualized volatility",
    "sharpe_ratio": "Sharpe ratio",
    "win_rate": "Winning-day ratio",
    "trade_count": "Trade count",
    "blocked_signal_days": "Blocked signal days",
    "days": "Trading days",
}


def _print_metrics(metrics: dict) -> None:
    print("\nBacktest results")
    print("-" * 40)
    for key, label in METRIC_LABELS.items():
        if key not in metrics:
            continue
        value = metrics[key]
        if key.endswith("return") or key in {"max_drawdown", "annualized_volatility", "win_rate"}:
            rendered = f"{value:.2%}"
        elif key == "sharpe_ratio":
            rendered = f"{value:.3f}"
        elif key in {"initial_cash", "final_equity"}:
            rendered = f"{value:,.2f}"
        else:
            rendered = f"{value:.0f}"
        print(f"{label:<12} {rendered}")


def _export(result: BacktestResult, data, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    data.to_csv(output_dir / "input_data.csv", index=False)
    result.frame.to_csv(output_dir / "equity_curve.csv", index=False)
    result.trades.to_csv(output_dir / "trades.csv", index=False)
    with (output_dir / "metrics.json").open("w", encoding="utf-8") as handle:
        json.dump(result.metrics, handle, ensure_ascii=False, indent=2)


def _common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--fast", type=int, default=20, help="fast SMA window")
    parser.add_argument("--slow", type=int, default=60, help="slow SMA window")
    parser.add_argument("--initial-cash", type=float, default=100_000.0, help="starting cash")
    parser.add_argument("--fee-rate", type=float, default=0.0003, help="one-way fee rate, e.g. 0.0003")
    parser.add_argument("--slippage-bps", type=float, default=2.0, help="one-way slippage in basis points")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"), help="output directory")


def _a_share_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--fast", type=int, default=20, help="fast SMA window")
    parser.add_argument("--slow", type=int, default=60, help="slow SMA window")
    parser.add_argument("--initial-cash", type=float, default=100_000.0, help="starting cash")
    parser.add_argument("--slippage-bps", type=float, default=2.0, help="one-way slippage in basis points")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs"), help="output directory")
    parser.add_argument("--buy-commission-rate", type=float, default=0.0003, help="buy-side commission rate")
    parser.add_argument("--sell-commission-rate", type=float, default=0.0003, help="sell-side commission rate")
    parser.add_argument("--min-commission", type=float, default=5.0, help="minimum commission per order")
    parser.add_argument("--sell-stamp-duty-rate", type=float, default=0.0005, help="sell-side stamp duty rate")
    parser.add_argument("--transfer-fee-rate", type=float, default=0.00001, help="transfer fee rate")
    parser.add_argument("--lot-size", type=int, default=100, help="minimum trade lot")
    parser.add_argument("--price-limit-rate", type=float, default=0.10, help="daily price-limit rate, e.g. 0.10")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stock quant research starter (research/backtest only)")
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo = subparsers.add_parser("demo", help="generate synthetic data and run a demo backtest")
    demo.add_argument("--days", type=int, default=720, help="number of synthetic trading days")
    demo.add_argument("--seed", type=int, default=7, help="random seed")
    _common_arguments(demo)
    backtest = subparsers.add_parser("backtest", help="load an OHLCV CSV and run a backtest")
    backtest.add_argument("csv", type=Path, help="path to an OHLCV CSV file")
    _common_arguments(backtest)
    a_share = subparsers.add_parser("a-share", help="run an A-share research backtest from a local CSV")
    a_share.add_argument("csv", type=Path, help="path to an OHLCV CSV file; optional Suspended column is supported")
    _a_share_arguments(a_share)
    subparsers.add_parser("app", help="launch the local desktop research workbench")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "app":
        from .app import run_app

        return run_app()
    if args.command == "demo":
        data = generate_synthetic_data(days=args.days, seed=args.seed)
    elif args.command == "a-share":
        if not args.csv.is_file():
            raise FileNotFoundError("Data file not found: " + str(args.csv))
        data = pd.read_csv(args.csv)
    else:
        data = load_ohlcv_csv(args.csv)
    if args.command == "a-share":
        config = AShareConfig(
            initial_cash=args.initial_cash,
            buy_commission_rate=args.buy_commission_rate,
            sell_commission_rate=args.sell_commission_rate,
            min_commission=args.min_commission,
            sell_stamp_duty_rate=args.sell_stamp_duty_rate,
            transfer_fee_rate=args.transfer_fee_rate,
            slippage_bps=args.slippage_bps,
            lot_size=args.lot_size,
            price_limit_rate=args.price_limit_rate,
        )
        result = run_a_share_backtest(data, fast=args.fast, slow=args.slow, config=config)
    else:
        config = BacktestConfig(
            initial_cash=args.initial_cash,
            fee_rate=args.fee_rate,
            slippage_bps=args.slippage_bps,
        )
        result = run_backtest(data, fast=args.fast, slow=args.slow, config=config)
    _export(result, data, args.output_dir)
    _print_metrics(result.metrics)
    print(f"\nResults written to: {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
