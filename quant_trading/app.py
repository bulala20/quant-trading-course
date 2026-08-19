"""本地桌面研究工作台，不连接券商或生成实盘订单。"""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Iterable, Tuple

import pandas as pd

from .a_share import AShareConfig, run_a_share_backtest
from .backtest import BacktestConfig, BacktestResult, run_backtest
from .data import generate_synthetic_data, load_ohlcv_csv


APP_BACKGROUND = "#F5F7FA"
SURFACE = "#FFFFFF"
INK = "#172033"
MUTED = "#667085"
ACCENT = "#087E8B"
ACCENT_DARK = "#05616B"
GRID = "#D7DEE8"
BENCHMARK = "#D97706"

METRIC_ORDER = (
    "final_equity",
    "total_return",
    "annualized_return",
    "max_drawdown",
    "annualized_volatility",
    "sharpe_ratio",
    "win_rate",
    "trade_count",
    "blocked_signal_days",
)

METRIC_LABELS = {
    "final_equity": "期末权益",
    "total_return": "累计收益",
    "annualized_return": "年化收益",
    "max_drawdown": "最大回撤",
    "annualized_volatility": "年化波动",
    "sharpe_ratio": "夏普比率",
    "win_rate": "盈利日比例",
    "trade_count": "交易次数",
    "blocked_signal_days": "受阻信号日",
}


def format_metric(key: str, value: float) -> str:
    """Format an engine metric for the desktop workbench."""
    if key in {"total_return", "annualized_return", "max_drawdown", "annualized_volatility", "win_rate"}:
        return f"{value:.2%}"
    if key == "final_equity":
        return f"{value:,.2f}"
    if key == "sharpe_ratio":
        return f"{value:.3f}"
    return f"{value:.0f}"


def export_result(result: BacktestResult, data: pd.DataFrame, output_dir: Path) -> Tuple[Path, ...]:
    """Write a completed local research run to a caller-selected directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    files = (
        output_dir / "input_data.csv",
        output_dir / "equity_curve.csv",
        output_dir / "trades.csv",
        output_dir / "metrics.json",
    )
    data.to_csv(files[0], index=False)
    result.frame.to_csv(files[1], index=False)
    result.trades.to_csv(files[2], index=False)
    with files[3].open("w", encoding="utf-8") as handle:
        json.dump(result.metrics, handle, ensure_ascii=False, indent=2)
    return files


class QuantTradingApp:
    """Tkinter desktop application for the existing backtest engines."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("股票量化研究工作台")
        self.root.minsize(1080, 740)
        self.root.geometry("1280x820")
        self.root.configure(background=APP_BACKGROUND)

        self.mode = tk.StringVar(value="a_share")
        self.data_source = tk.StringVar(value="demo")
        self.csv_path = tk.StringVar()
        self.fast = tk.StringVar(value="20")
        self.slow = tk.StringVar(value="60")
        self.initial_cash = tk.StringVar(value="100000")
        self.fee_rate = tk.StringVar(value="0.0003")
        self.slippage_bps = tk.StringVar(value="2")
        self.demo_days = tk.StringVar(value="720")
        self.demo_seed = tk.StringVar(value="7")
        self.buy_commission = tk.StringVar(value="0.0003")
        self.sell_commission = tk.StringVar(value="0.0003")
        self.min_commission = tk.StringVar(value="5")
        self.stamp_duty = tk.StringVar(value="0.0005")
        self.transfer_fee = tk.StringVar(value="0.00001")
        self.lot_size = tk.StringVar(value="100")
        self.price_limit = tk.StringVar(value="0.10")
        self.status = tk.StringVar(value="选择数据来源后运行回测。")
        self.last_result: BacktestResult | None = None
        self.last_data: pd.DataFrame | None = None

        self._configure_style()
        self._build_layout()
        self._update_form_state()
        self._update_mode_fields()

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background=APP_BACKGROUND)
        style.configure("Surface.TFrame", background=SURFACE)
        style.configure("Title.TLabel", background=APP_BACKGROUND, foreground=INK, font=("Microsoft YaHei UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background=APP_BACKGROUND, foreground=MUTED, font=("Microsoft YaHei UI", 10))
        style.configure("Section.TLabel", background=SURFACE, foreground=INK, font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("MetricName.TLabel", background=SURFACE, foreground=MUTED, font=("Microsoft YaHei UI", 9))
        style.configure("MetricValue.TLabel", background=SURFACE, foreground=INK, font=("Consolas", 13, "bold"))
        style.configure("Primary.TButton", background=ACCENT, foreground="white", borderwidth=0, font=("Microsoft YaHei UI", 10, "bold"), padding=(14, 8))
        style.map("Primary.TButton", background=[("active", ACCENT_DARK), ("disabled", "#AAB7C4")])
        style.configure("TButton", font=("Microsoft YaHei UI", 9), padding=(8, 5))
        style.configure("TLabel", background=SURFACE, foreground=INK, font=("Microsoft YaHei UI", 9))
        style.configure("TRadiobutton", background=SURFACE, foreground=INK, font=("Microsoft YaHei UI", 9))
        style.configure("TEntry", fieldbackground="white", padding=5)
        style.configure("Treeview", rowheight=27, background="white", fieldbackground="white", foreground=INK, font=("Consolas", 9))
        style.configure("Treeview.Heading", background="#E8EDF3", foreground=INK, font=("Microsoft YaHei UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#CAE9ED")], foreground=[("selected", INK)])

    def _build_layout(self) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame", padding=20)
        shell.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(1, weight=1)

        header = ttk.Frame(shell, style="App.TFrame")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="股票量化研究工作台", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="本地数据研究与历史回测 · 不连接券商 · 不生成订单",
            style="Subtitle.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        controls = ttk.Frame(shell, style="Surface.TFrame", padding=16)
        controls.grid(row=1, column=0, sticky="nsw", padx=(0, 16))
        controls.configure(width=320)
        controls.grid_propagate(False)
        self._build_controls(controls)

        results = ttk.Frame(shell, style="Surface.TFrame", padding=16)
        results.grid(row=1, column=1, sticky="nsew")
        results.columnconfigure(0, weight=1)
        results.rowconfigure(3, weight=1)
        self._build_results(results)

        footer = ttk.Label(shell, textvariable=self.status, style="Subtitle.TLabel", anchor="w")
        footer.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))

    def _build_controls(self, parent: ttk.Frame) -> None:
        row = 0
        ttk.Label(parent, text="研究模式", style="Section.TLabel").grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        modes = ttk.Frame(parent, style="Surface.TFrame")
        modes.grid(row=row, column=0, columnspan=2, sticky="ew", pady=(7, 14))
        ttk.Radiobutton(modes, text="A 股规则", value="a_share", variable=self.mode, command=self._update_mode_fields).grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(modes, text="通用回测", value="standard", variable=self.mode, command=self._update_mode_fields).grid(row=0, column=1, sticky="w", padx=(18, 0))
        row += 1

        ttk.Separator(parent).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        row += 1
        ttk.Label(parent, text="数据来源", style="Section.TLabel").grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        ttk.Radiobutton(parent, text="生成演示数据", value="demo", variable=self.data_source, command=self._update_form_state).grid(row=row, column=0, columnspan=2, sticky="w", pady=(7, 3))
        row += 1
        self._add_labeled_entry(parent, row, "交易日数量", self.demo_days)
        row += 1
        self._add_labeled_entry(parent, row, "随机种子", self.demo_seed)
        row += 1
        ttk.Radiobutton(parent, text="本地 CSV", value="csv", variable=self.data_source, command=self._update_form_state).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 3))
        row += 1
        self.csv_entry = ttk.Entry(parent, textvariable=self.csv_path, width=23)
        self.csv_entry.grid(row=row, column=0, sticky="ew")
        self.csv_button = ttk.Button(parent, text="选择文件", command=self._choose_csv)
        self.csv_button.grid(row=row, column=1, sticky="e", padx=(6, 0))
        row += 1

        ttk.Separator(parent).grid(row=row, column=0, columnspan=2, sticky="ew", pady=14)
        row += 1
        ttk.Label(parent, text="策略参数", style="Section.TLabel").grid(row=row, column=0, columnspan=2, sticky="w")
        row += 1
        self._add_labeled_entry(parent, row, "短期均线", self.fast)
        row += 1
        self._add_labeled_entry(parent, row, "长期均线", self.slow)
        row += 1
        self._add_labeled_entry(parent, row, "初始资金", self.initial_cash)
        row += 1
        self._add_labeled_entry(parent, row, "单边滑点 (bps)", self.slippage_bps)
        row += 1

        self.standard_costs = ttk.Frame(parent, style="Surface.TFrame")
        self.standard_costs.grid(row=row, column=0, columnspan=2, sticky="ew")
        self._add_labeled_entry(self.standard_costs, 0, "单边费率", self.fee_rate)
        self.a_share_costs = ttk.Frame(parent, style="Surface.TFrame")
        self._add_labeled_entry(self.a_share_costs, 0, "买入佣金率", self.buy_commission)
        self._add_labeled_entry(self.a_share_costs, 1, "卖出佣金率", self.sell_commission)
        self._add_labeled_entry(self.a_share_costs, 2, "最低佣金", self.min_commission)
        self._add_labeled_entry(self.a_share_costs, 3, "卖出印花税率", self.stamp_duty)
        self._add_labeled_entry(self.a_share_costs, 4, "过户费率", self.transfer_fee)
        self._add_labeled_entry(self.a_share_costs, 5, "最小交易手数", self.lot_size)
        self._add_labeled_entry(self.a_share_costs, 6, "涨跌停幅度", self.price_limit)
        row += 1

        ttk.Button(parent, text="运行回测", style="Primary.TButton", command=self._run_backtest).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(16, 7))
        row += 1
        self.export_button = ttk.Button(parent, text="导出结果", command=self._export_result, state="disabled")
        self.export_button.grid(row=row, column=0, columnspan=2, sticky="ew")
        parent.columnconfigure(0, weight=1)

    def _build_results(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="回测结果", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.metrics_frame = ttk.Frame(parent, style="Surface.TFrame")
        self.metrics_frame.grid(row=1, column=0, sticky="ew", pady=(8, 14))
        for column in range(5):
            self.metrics_frame.columnconfigure(column, weight=1)

        self.chart = tk.Canvas(parent, height=245, background=SURFACE, highlightthickness=0)
        self.chart.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        self.chart.bind("<Configure>", lambda _event: self._draw_chart())
        self._draw_empty_chart()

        trades_section = ttk.Frame(parent, style="Surface.TFrame")
        trades_section.grid(row=3, column=0, sticky="nsew")
        trades_section.columnconfigure(0, weight=1)
        trades_section.rowconfigure(1, weight=1)
        ttk.Label(trades_section, text="交易记录", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 7))
        self.trade_table = ttk.Treeview(trades_section, show="headings", height=12)
        self.trade_table.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(trades_section, orient="vertical", command=self.trade_table.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.trade_table.configure(yscrollcommand=scrollbar.set)

    @staticmethod
    def _add_labeled_entry(parent: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=variable, width=15).grid(row=row, column=1, sticky="e", pady=3)

    def _update_form_state(self) -> None:
        is_csv = self.data_source.get() == "csv"
        state = "normal" if is_csv else "disabled"
        self.csv_entry.configure(state=state)
        self.csv_button.configure(state=state)

    def _update_mode_fields(self) -> None:
        if self.mode.get() == "a_share":
            self.standard_costs.grid_remove()
            self.a_share_costs.grid()
        else:
            self.a_share_costs.grid_remove()
            self.standard_costs.grid()

    def _choose_csv(self) -> None:
        selected = filedialog.askopenfilename(
            title="选择日线 CSV 数据",
            filetypes=[("CSV 文件", "*.csv"), ("所有文件", "*.*")],
        )
        if selected:
            self.csv_path.set(selected)
            self.status.set("已选择本地数据文件：" + Path(selected).name)

    def _load_data(self) -> pd.DataFrame:
        if self.data_source.get() == "demo":
            return generate_synthetic_data(days=int(self.demo_days.get()), seed=int(self.demo_seed.get()))
        path = Path(self.csv_path.get())
        if not path.is_file():
            raise ValueError("请先选择存在的 CSV 文件")
        if self.mode.get() == "a_share":
            return pd.read_csv(path)
        return load_ohlcv_csv(path)

    def _run_backtest(self) -> None:
        try:
            data = self._load_data()
            fast = int(self.fast.get())
            slow = int(self.slow.get())
            if fast <= 0 or slow <= fast:
                raise ValueError("长期均线必须大于短期均线，且两者都必须为正数")
            if self.mode.get() == "a_share":
                config = AShareConfig(
                    initial_cash=float(self.initial_cash.get()),
                    buy_commission_rate=float(self.buy_commission.get()),
                    sell_commission_rate=float(self.sell_commission.get()),
                    min_commission=float(self.min_commission.get()),
                    sell_stamp_duty_rate=float(self.stamp_duty.get()),
                    transfer_fee_rate=float(self.transfer_fee.get()),
                    slippage_bps=float(self.slippage_bps.get()),
                    lot_size=int(self.lot_size.get()),
                    price_limit_rate=float(self.price_limit.get()),
                )
                result = run_a_share_backtest(data, fast=fast, slow=slow, config=config)
            else:
                config = BacktestConfig(
                    initial_cash=float(self.initial_cash.get()),
                    fee_rate=float(self.fee_rate.get()),
                    slippage_bps=float(self.slippage_bps.get()),
                )
                result = run_backtest(data, fast=fast, slow=slow, config=config)
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            self.status.set("无法运行回测。请检查数据和参数。")
            messagebox.showerror("回测未完成", str(exc), parent=self.root)
            return

        self.last_data = data
        self.last_result = result
        self._render_metrics(result.metrics)
        self._render_trades(result.trades)
        self._draw_chart()
        self.export_button.configure(state="normal")
        self.status.set(f"回测完成：{len(result.frame)} 个交易日，{int(result.metrics['trade_count'])} 次交易。")

    def _render_metrics(self, metrics: Dict[str, float]) -> None:
        for child in self.metrics_frame.winfo_children():
            child.destroy()
        visible = [key for key in METRIC_ORDER if key in metrics]
        for index, key in enumerate(visible):
            column = index % 5
            row = index // 5
            cell = ttk.Frame(self.metrics_frame, style="Surface.TFrame", padding=(8, 5))
            cell.grid(row=row, column=column, sticky="ew")
            ttk.Label(cell, text=METRIC_LABELS[key], style="MetricName.TLabel").grid(row=0, column=0, sticky="w")
            ttk.Label(cell, text=format_metric(key, metrics[key]), style="MetricValue.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))

    def _render_trades(self, trades: pd.DataFrame) -> None:
        for item in self.trade_table.get_children():
            self.trade_table.delete(item)
        preferred = ("Date", "action", "shares", "price", "gross_value", "commission", "stamp_duty", "turnover")
        columns = [column for column in preferred if column in trades.columns]
        self.trade_table.configure(columns=columns)
        for column in columns:
            self.trade_table.heading(column, text={"Date": "日期", "action": "方向", "shares": "股数", "price": "成交价", "gross_value": "成交金额", "commission": "佣金", "stamp_duty": "印花税", "turnover": "换手"}.get(column, column))
            self.trade_table.column(column, anchor="center", width=105, minwidth=80, stretch=True)
        for _, record in trades.iterrows():
            values = []
            for column in columns:
                value = record[column]
                if column == "Date":
                    values.append(str(value)[:10])
                elif isinstance(value, float):
                    values.append(f"{value:,.4f}" if column == "turnover" else f"{value:,.2f}")
                else:
                    values.append(str(value))
            self.trade_table.insert("", "end", values=values)

    def _draw_empty_chart(self) -> None:
        self.chart.delete("all")
        width = max(self.chart.winfo_width(), 320)
        height = max(self.chart.winfo_height(), 220)
        self.chart.create_text(width / 2, height / 2, text="运行回测后显示策略净值曲线", fill=MUTED, font=("Microsoft YaHei UI", 10))

    def _draw_chart(self) -> None:
        if self.last_result is None:
            self._draw_empty_chart()
            return
        self.chart.delete("all")
        width = max(self.chart.winfo_width(), 320)
        height = max(self.chart.winfo_height(), 220)
        left, right, top, bottom = 52, 20, 32, 32
        frame = self.last_result.frame
        strategy = frame["equity"].astype(float).tolist()
        benchmark = frame["buy_and_hold_equity"].astype(float).tolist()
        values = strategy + benchmark
        low, high = min(values), max(values)
        if high == low:
            high += 1
            low -= 1
        padding = (high - low) * 0.08
        low -= padding
        high += padding

        for step in range(5):
            ratio = step / 4
            y = top + (height - top - bottom) * ratio
            value = high - (high - low) * ratio
            self.chart.create_line(left, y, width - right, y, fill=GRID, width=1)
            self.chart.create_text(left - 8, y, text=f"{value:,.0f}", fill=MUTED, anchor="e", font=("Consolas", 8))

        def points(series: Iterable[float]) -> list[float]:
            values_list = list(series)
            if len(values_list) == 1:
                return [left, height / 2, width - right, height / 2]
            coordinates = []
            usable_width = width - left - right
            usable_height = height - top - bottom
            for index, value in enumerate(values_list):
                x = left + usable_width * index / (len(values_list) - 1)
                y = top + usable_height * (high - value) / (high - low)
                coordinates.extend((x, y))
            return coordinates

        self.chart.create_line(*points(benchmark), fill=BENCHMARK, width=2, smooth=True)
        self.chart.create_line(*points(strategy), fill=ACCENT, width=2, smooth=True)
        self.chart.create_text(left, 14, text="策略", fill=ACCENT, anchor="w", font=("Microsoft YaHei UI", 9, "bold"))
        self.chart.create_text(left + 54, 14, text="买入并持有", fill=BENCHMARK, anchor="w", font=("Microsoft YaHei UI", 9, "bold"))
        self.chart.create_text(left, height - 12, text=str(frame["Date"].iloc[0])[:10], fill=MUTED, anchor="w", font=("Consolas", 8))
        self.chart.create_text(width - right, height - 12, text=str(frame["Date"].iloc[-1])[:10], fill=MUTED, anchor="e", font=("Consolas", 8))

    def _export_result(self) -> None:
        if self.last_result is None or self.last_data is None:
            return
        selected = filedialog.askdirectory(title="选择结果导出文件夹")
        if not selected:
            return
        try:
            files = export_result(self.last_result, self.last_data, Path(selected))
        except OSError as exc:
            messagebox.showerror("导出未完成", str(exc), parent=self.root)
            return
        self.status.set("已导出结果到：" + str(Path(selected)))
        messagebox.showinfo("导出完成", "已写入：\n" + "\n".join(path.name for path in files), parent=self.root)

    def run(self) -> None:
        self.root.mainloop()


def run_app() -> int:
    """Launch the local desktop program."""
    application = QuantTradingApp()
    application.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(run_app())
