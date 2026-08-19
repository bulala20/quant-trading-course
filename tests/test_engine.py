import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from quant_trading.a_share import AShareConfig, run_a_share_backtest
from quant_trading.app import export_result, format_metric
from quant_trading.backtest import BacktestConfig, run_backtest
from quant_trading.cli import build_parser, main
from quant_trading.data import generate_synthetic_data, normalize_ohlcv
from quant_trading.strategy import sma_crossover_signals


class QuantTradingTests(unittest.TestCase):
    def test_synthetic_data_is_valid_and_reproducible(self):
        first = generate_synthetic_data(days=40, seed=11)
        second = generate_synthetic_data(days=40, seed=11)
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(list(first.columns), ["Date", "Open", "High", "Low", "Close", "Volume"])

    def test_normalize_rejects_missing_columns(self):
        with self.assertRaisesRegex(ValueError, "Missing OHLCV columns"):
            normalize_ohlcv(pd.DataFrame({"date": ["2024-01-01"], "close": [10]}))

    def test_backtest_does_not_hold_before_signal_is_known(self):
        dates = pd.bdate_range("2024-01-01", periods=8)
        close = [100, 100, 100, 110, 120, 130, 125, 120]
        data = pd.DataFrame(
            {
                "Date": dates,
                "Open": close,
                "High": [value + 1 for value in close],
                "Low": [value - 1 for value in close],
                "Close": close,
                "Volume": [1000] * len(close),
            }
        )
        signals = sma_crossover_signals(data, fast=2, slow=3)
        result = run_backtest(data, fast=2, slow=3, config=BacktestConfig(fee_rate=0, slippage_bps=0))
        self.assertEqual(result.frame.loc[0, "position"], 0.0)
        self.assertEqual(result.frame.loc[2, "position"], 0.0)
        self.assertEqual(signals.loc[3, "target_position"], 1.0)
        self.assertEqual(result.frame.loc[4, "position"], 1.0)

    def test_costs_reduce_equity_when_trades_exist(self):
        data = generate_synthetic_data(days=240, seed=3)
        free = run_backtest(data, fast=5, slow=20, config=BacktestConfig(fee_rate=0, slippage_bps=0))
        costly = run_backtest(data, fast=5, slow=20, config=BacktestConfig(fee_rate=0.01, slippage_bps=0))
        self.assertGreater(len(free.trades), 0)
        self.assertLess(costly.metrics["final_equity"], free.metrics["final_equity"])

    def test_cost_rate_cannot_make_a_trade_return_negative(self):
        with self.assertRaisesRegex(ValueError, "smaller than 1"):
            BacktestConfig(fee_rate=1.0, slippage_bps=0)

    def test_demo_cli_completes_and_exports_results(self):
        with TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory) / "demo"
            exit_code = main(["demo", "--days", "120", "--output-dir", str(output_dir)])
            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "metrics.json").is_file())
            self.assertTrue((output_dir / "equity_curve.csv").is_file())

    def test_desktop_app_command_is_registered(self):
        args = build_parser().parse_args(["app"])
        self.assertEqual(args.command, "app")

    def test_desktop_helpers_format_and_export_a_result(self):
        data = generate_synthetic_data(days=80, seed=5)
        result = run_backtest(data, fast=5, slow=20)
        self.assertEqual(format_metric("total_return", 0.01234), "1.23%")
        self.assertEqual(format_metric("trade_count", 3.0), "3")
        with TemporaryDirectory() as temporary_directory:
            files = export_result(result, data, Path(temporary_directory))
            self.assertTrue(all(path.is_file() for path in files))

    def test_a_share_buy_uses_integer_lots_and_available_cash(self):
        data = self._a_share_data([10, 10, 10, 11, 12, 13])
        result = run_a_share_backtest(
            data,
            fast=2,
            slow=3,
            config=AShareConfig(
                initial_cash=1_500,
                buy_commission_rate=0,
                sell_commission_rate=0,
                min_commission=0,
                sell_stamp_duty_rate=0,
                transfer_fee_rate=0,
                slippage_bps=0,
            ),
        )
        buy = result.trades.iloc[0]
        self.assertEqual(buy["action"], "BUY")
        self.assertEqual(buy["shares"], 100)
        self.assertEqual(buy["shares"] % 100, 0)
        self.assertGreaterEqual(result.frame["cash"].min(), 0)

    def test_a_share_blocks_buy_at_limit_up(self):
        data = self._a_share_data([10, 10, 10, 11, 12.1, 13])
        data.loc[4, ["Open", "High", "Low", "Close"]] = [12.1, 12.1, 12.1, 12.1]
        result = run_a_share_backtest(
            data,
            fast=2,
            slow=3,
            config=AShareConfig(min_commission=0, slippage_bps=0),
        )
        self.assertEqual(result.frame.loc[4, "blocked_reason"], "LIMIT_UP")
        self.assertGreaterEqual(result.metrics["blocked_signal_days"], 1)

    def test_a_share_blocks_trade_during_suspension(self):
        data = self._a_share_data([10, 10, 10, 11, 12, 13])
        data["Suspended"] = [False, False, False, False, True, False]
        result = run_a_share_backtest(
            data,
            fast=2,
            slow=3,
            config=AShareConfig(min_commission=0, slippage_bps=0),
        )
        self.assertEqual(result.frame.loc[4, "blocked_reason"], "SUSPENDED")

    def test_a_share_sell_happens_after_the_buy_day(self):
        data = self._a_share_data([10, 10, 10, 11, 10, 9.5, 9.0])
        result = run_a_share_backtest(
            data,
            fast=2,
            slow=3,
            config=AShareConfig(min_commission=0, slippage_bps=0),
        )
        buy_date = result.trades.loc[result.trades["action"] == "BUY", "Date"].iloc[0]
        sell_date = result.trades.loc[result.trades["action"] == "SELL", "Date"].iloc[0]
        self.assertGreater(sell_date, buy_date)

    @staticmethod
    def _a_share_data(close):
        return pd.DataFrame(
            {
                "Date": pd.bdate_range("2024-01-01", periods=len(close)),
                "Open": close,
                "High": close,
                "Low": close,
                "Close": close,
                "Volume": [1_000_000] * len(close),
            }
        )


if __name__ == "__main__":
    unittest.main()
