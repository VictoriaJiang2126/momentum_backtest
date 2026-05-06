import numpy as np
import pandas as pd


def metrics(eq, tr, init_cash=100_000):
    """eq: 净值曲线 DataFrame, tr: 交易明细 DataFrame"""
    rets = eq["equity"].pct_change().dropna()
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25

    total_ret = eq["equity"].iloc[-1] / init_cash - 1
    cagr = (1 + total_ret) ** (1 / n_years) - 1 if n_years > 0 else 0
    sharpe = rets.mean() / rets.std() * np.sqrt(252) if rets.std() > 0 else 0
    max_dd = (eq["equity"] / eq["equity"].cummax() - 1).min()

    if len(tr) > 0:
        wins = tr[tr["return"] > 0]
        losses = tr[tr["return"] <= 0]
        win_rate = len(wins) / len(tr)
        avg_win = wins["return"].mean() if len(wins) else 0
        avg_loss = losses["return"].mean() if len(losses) else 0
        pf = -wins["return"].sum() / losses["return"].sum() if len(losses) and losses["return"].sum() < 0 else np.inf
        avg_hold = tr["hold_days"].mean()
    else:
        win_rate = avg_win = avg_loss = pf = avg_hold = 0

    return {
        "Total Return":  f"{total_ret*100:>8.2f}%",
        "CAGR":          f"{cagr*100:>8.2f}%",
        "Max Drawdown":  f"{max_dd*100:>8.2f}%",
        "Sharpe":        f"{sharpe:>8.2f}",
        "Trades":        f"{len(tr):>8d}",
        "Win Rate":      f"{win_rate*100:>8.1f}%",
        "Avg Win":       f"{avg_win*100:>8.2f}%",
        "Avg Loss":      f"{avg_loss*100:>8.2f}%",
        "Profit Factor": f"{pf:>8.2f}",
        "Avg Hold Days": f"{avg_hold:>8.1f}",
    }


def print_metrics(eq, tr, init_cash=100_000):
    m = metrics(eq, tr, init_cash)
    print("=" * 35)
    for k, v in m.items():
        print(f"  {k:<15} {v}")
    print("=" * 35)
