"""OHLCV 数据读取、校验与教学用合成数据。"""

from __future__ import annotations

from pathlib import Path
from typing import Union

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = ("Date", "Open", "High", "Low", "Close", "Volume")


def normalize_ohlcv(data: pd.DataFrame) -> pd.DataFrame:
    """把常见的 OHLCV 列名统一，并做基础数据质量检查。"""
    if data.empty:
        raise ValueError("OHLCV data is empty")

    aliases = {str(column).strip().lower(): column for column in data.columns}
    missing = [column for column in REQUIRED_COLUMNS if column.lower() not in aliases]
    if missing:
        raise ValueError("Missing OHLCV columns: " + ", ".join(missing))

    normalized = data[[aliases[column.lower()] for column in REQUIRED_COLUMNS]].copy()
    normalized.columns = list(REQUIRED_COLUMNS)
    normalized["Date"] = pd.to_datetime(normalized["Date"], errors="coerce")
    for column in REQUIRED_COLUMNS[1:]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")

    normalized = (
        normalized.dropna(subset=list(REQUIRED_COLUMNS))
        .sort_values("Date")
        .drop_duplicates(subset=["Date"], keep="last")
        .reset_index(drop=True)
    )
    if normalized.empty:
        raise ValueError("OHLCV data has no valid rows after cleaning")
    if (normalized[["Open", "High", "Low", "Close"]] <= 0).any().any():
        raise ValueError("OHLC prices must be positive")
    if (normalized["Volume"] < 0).any():
        raise ValueError("Volume cannot be negative")
    if (normalized["High"] < normalized[["Open", "Close"]].max(axis=1)).any():
        raise ValueError("High must be >= Open and Close")
    if (normalized["Low"] > normalized[["Open", "Close"]].min(axis=1)).any():
        raise ValueError("Low must be <= Open and Close")
    return normalized


def load_ohlcv_csv(path: Union[str, Path]) -> pd.DataFrame:
    """读取 CSV 格式的日线数据，列名需包含 Date/Open/High/Low/Close/Volume。"""
    csv_path = Path(path)
    if not csv_path.is_file():
        raise FileNotFoundError("Data file not found: " + str(csv_path))
    return normalize_ohlcv(pd.read_csv(csv_path))


def generate_synthetic_data(days: int = 720, seed: int = 7) -> pd.DataFrame:
    """生成带有趋势、波动和成交量的教学数据，不代表任何真实证券。"""
    if days < 10:
        raise ValueError("days must be at least 10")
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=days)
    index = np.arange(days)
    drift = np.where(index < days * 0.45, 0.00035, -0.00005)
    returns = drift + rng.normal(0, 0.012, size=days)
    close = 100 * np.exp(np.cumsum(returns))
    open_price = close * (1 + rng.normal(0, 0.003, size=days))
    high = np.maximum(open_price, close) * (1 + rng.uniform(0.001, 0.012, size=days))
    low = np.minimum(open_price, close) * (1 - rng.uniform(0.001, 0.012, size=days))
    volume = rng.integers(500_000, 2_500_000, size=days)
    return normalize_ohlcv(
        pd.DataFrame(
            {
                "Date": dates,
                "Open": open_price,
                "High": high,
                "Low": low,
                "Close": close,
                "Volume": volume,
            }
        )
    )
