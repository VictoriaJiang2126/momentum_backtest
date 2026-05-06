

import pandas as pd
import yfinance as yf
from config import START, END, MARKET_FILTER

MOMENTUM_DAYS = 63
MIN_PRICE_TREND = 10
MIN_AVG_VOL_TREND = 1_000_000
MIN_DOLLAR_VOL = 300_000_000
EXIT_SMA_DAYS = 50


def compute_trend_signals(df):
    close = df.pivot(index="date", columns="ticker", values="close")
    open_ = df.pivot(index="date", columns="ticker", values="open")
    volume = df.pivot(index="date", columns="ticker", values="volume")

    sma50 = close.rolling(EXIT_SMA_DAYS).mean()
    sma200 = close.rolling(200).mean()
    avg_vol = volume.rolling(20).mean()
    dollar_vol = (close * volume).rolling(20).mean()
    momentum = close.pct_change(MOMENTUM_DAYS)
    above_sma50_pct = (close - sma50) / sma50

    eligibility = (
        (close > MIN_PRICE_TREND) &
        (avg_vol > MIN_AVG_VOL_TREND) &
        (dollar_vol > MIN_DOLLAR_VOL) &
        (close > sma50) &
        (sma50 > sma200) &
        (close > sma200) &
        (momentum > 0.20) &
        (above_sma50_pct > 0.03)
    ).fillna(False)

    spy = yf.download(MARKET_FILTER, start=START, end=END,
                      auto_adjust=True, progress=False)["Close"].squeeze()
    spy_sma200 = spy.rolling(200).mean()
    market_ok = (spy > spy_sma200).reindex(close.index).ffill().fillna(False)
    spy_below_200 = (spy < spy_sma200).reindex(close.index).ffill().fillna(False)

    # 改动：6个月 → 3个月动量检测领跑股
    momentum_3m = close.pct_change(63)           # ← 只改了这一行
    large_cap_mask = (avg_vol > MIN_AVG_VOL_TREND) & (dollar_vol > MIN_DOLLAR_VOL)
    leaders_count = (momentum_3m[large_cap_mask] > 0.50).sum(axis=1)
    market_has_leaders = (leaders_count >= 3).reindex(close.index).fillna(False)

    eligibility = eligibility & market_ok.values.reshape(-1, 1)

    return {
        "close": close, "open": open_,
        "exit_sma": sma50,
        "eligibility": eligibility,
        "momentum": momentum,
        "spy_below_200": spy_below_200,
        "market_has_leaders": market_has_leaders,
    }