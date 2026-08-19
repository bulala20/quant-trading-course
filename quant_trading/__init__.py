"""用于学习股票量化研究的轻量回测工具。"""

from .a_share import AShareConfig, run_a_share_backtest
from .backtest import BacktestConfig, BacktestResult, run_backtest
from .data import generate_synthetic_data, load_ohlcv_csv, normalize_ohlcv
from .strategy import sma_crossover_signals

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "AShareConfig",
    "generate_synthetic_data",
    "load_ohlcv_csv",
    "normalize_ohlcv",
    "run_backtest",
    "run_a_share_backtest",
    "sma_crossover_signals",
]
