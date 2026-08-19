"""Screen liquid, non-ST main-board A shares under CNY 10.

This is a research watchlist generator, not an order or investment-advice tool.
The public quote endpoint can change without notice; always verify quotes in
your licensed data terminal before making any decision.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import statistics
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from typing import Optional


EASTMONEY_LIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_KLINE_URL = "https://push2.eastmoney.com/api/qt/stock/kline/get"


def history_start(today: Optional[dt.date] = None, calendar_days: int = 180) -> str:
    """Return a rolling history start date in the provider's YYYYMMDD format."""
    if calendar_days < 30:
        raise ValueError("calendar_days must be at least 30")
    anchor = today or dt.date.today()
    return (anchor - dt.timedelta(days=calendar_days)).strftime("%Y%m%d")


def fetch_json(url: str, params: dict) -> dict:
    full_url = url + "?" + urllib.parse.urlencode(params)
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if curl:
        result = subprocess.run(
            [curl, "--silent", "--show-error", "--fail", "--max-time", "20", "-A", "Mozilla/5.0", full_url],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode == 0:
            return json.loads(result.stdout)

    for attempt in range(4):
        try:
            request = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError):
            if attempt == 3:
                raise
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def load_universe() -> list[dict]:
    items = []
    page = 1
    while True:
        payload = fetch_json(
            EASTMONEY_LIST_URL,
            {
            "pn": page,
            "pz": 100,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f6",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f12,f14,f2,f3,f6,f8",
            },
        )
        data = payload.get("data") or {}
        batch = data.get("diff") or []
        items.extend(batch)
        total = int(data.get("total") or len(items))
        if not batch or len(items) >= total:
            return items
        page += 1
        time.sleep(0.03)


def load_daily_bars(code: str, start: str) -> list[dict]:
    market = "1" if code.startswith("6") else "0"
    payload = fetch_json(
        EASTMONEY_KLINE_URL,
        {
            "secid": f"{market}.{code}",
            "klt": 101,
            "fqt": 1,
            "beg": start,
            "end": "20500101",
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        },
    )
    bars = []
    for raw in ((payload.get("data") or {}).get("klines") or []):
        fields = raw.split(",")
        if len(fields) < 9:
            continue
        try:
            bars.append(
                {
                    "date": fields[0],
                    "close": float(fields[2]),
                    "volume": float(fields[5]),
                    "pct": float(fields[8]),
                }
            )
        except (TypeError, ValueError):
            continue
    return bars


def candidate_rows(max_stocks: int, min_amount: float) -> tuple[list[dict], int, int]:
    universe = load_universe()
    start = history_start()
    screened = []
    for item in universe:
        code = str(item.get("f12") or "")
        name = str(item.get("f14") or "")
        price = item.get("f2")
        amount = item.get("f6")
        if not code.startswith(("0", "6")):
            continue
        if price is None or amount is None or not 0 < float(price) <= 10:
            continue
        if any(flag in name.upper() for flag in ("ST", "退")):
            continue
        if float(amount) < min_amount:
            continue
        screened.append(
            {
                "code": code,
                "name": name,
                "price": float(price),
                "amount": float(amount),
                "today_pct": float(item.get("f3") or 0),
            }
        )

    rows = []
    for item in screened[:max_stocks]:
        try:
            bars = load_daily_bars(item["code"], start=start)
        except Exception:
            continue
        if len(bars) < 10:
            continue
        closes = [bar["close"] for bar in bars]
        volumes = [bar["volume"] for bar in bars]
        last = closes[-1]
        ma5 = statistics.mean(closes[-5:])
        ma10 = statistics.mean(closes[-10:])
        recent_volume = statistics.mean(volumes[-6:-1])
        ret1 = last / closes[-2] - 1
        ret3 = last / closes[-4] - 1
        ret5 = last / closes[-6] - 1
        volume_ratio = volumes[-1] / recent_volume if recent_volume else 0
        # A transparent momentum ranking, deliberately excluding one-day limit-up chasing.
        score = 100 * (
            0.45 * ret3
            + 0.30 * ret5
            + 0.15 * (last / ma5 - 1)
            + 0.10 * min(volume_ratio - 1, 2) / 10
        )
        if last <= ma5 or last <= ma10 or ret3 <= 0 or ret5 <= 0 or ret1 >= 0.095:
            continue
        rows.append(
            {
                **item,
                "last_date": bars[-1]["date"],
                "ret1": ret1,
                "ret3": ret3,
                "ret5": ret5,
                "ma5_gap": last / ma5 - 1,
                "ma10_gap": last / ma10 - 1,
                "volume_ratio": volume_ratio,
                "score": score,
            }
        )
        time.sleep(0.03)
    rows.sort(key=lambda row: row["score"], reverse=True)
    return rows, len(universe), len(screened)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an A-share under-CNY-10 research watchlist")
    parser.add_argument("--max-stocks", type=int, default=180, help="maximum liquid stocks to inspect")
    parser.add_argument("--min-amount", type=float, default=50_000_000, help="minimum daily turnover in CNY")
    parser.add_argument("--top", type=int, default=15, help="number of rows to print")
    args = parser.parse_args()

    try:
        rows, universe_count, screened_count = candidate_rows(args.max_stocks, args.min_amount)
    except Exception as exc:
        print(
            "Unable to retrieve the public quote data. "
            "The provider may be unavailable or rate-limiting requests; "
            "retry later and verify quotes in a licensed terminal.",
            file=sys.stderr,
        )
        print(f"Details: {exc}", file=sys.stderr)
        return 2
    print("DATA_RETRIEVED", dt.datetime.now().astimezone().isoformat(timespec="seconds"))
    print("UNIVERSE", universe_count)
    print("UNDER10_MAINBOARD_LIQUID", screened_count)
    print("MOMENTUM_CANDIDATES", len(rows))
    print("code|name|price|today_pct|ret3|ret5|ma5_gap|ma10_gap|volume_ratio|amount_million|last_date|score")
    for row in rows[: args.top]:
        print(
            f'{row["code"]}|{row["name"]}|{row["price"]:.2f}|'
            f'{row["today_pct"]:.2%}|{row["ret3"]:.2%}|{row["ret5"]:.2%}|'
            f'{row["ma5_gap"]:.2%}|{row["ma10_gap"]:.2%}|{row["volume_ratio"]:.2f}|'
            f'{row["amount"] / 1e6:.1f}|{row["last_date"]}|{row["score"]:.3f}'
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
