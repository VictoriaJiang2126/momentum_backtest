import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from universe import get_russell3000
from data_loader import download_prices
from trend_signals import compute_trend_signals
from trend_backtest import run_trend_backtest
from metrics import print_metrics

print("[1/4] 加载股票池...")
tickers = get_russell3000()

print("[2/4] 加载价格数据...")
df = download_prices(tickers)

print("[3/4] 计算趋势信号...")
out = compute_trend_signals(df)
print(f"      合格股票天数: {out['eligibility'].sum().sum()}")
print(f"      日均合格数: {out['eligibility'].sum(axis=1).mean():.1f}")

print("[4/4] 运行回测...")
eq, tr = run_trend_backtest(out)

print_metrics(eq, tr)

eq.to_csv(Path(__file__).parent / "equity.csv")
tr.to_csv(Path(__file__).parent / "trades.csv", index=False)

# 打印持仓最长的几笔
if len(tr) > 0:
    print("\n持仓时间最长的5笔交易:")
    print(tr.nlargest(5, "hold_days")[["ticker", "entry_date", "exit_date", "hold_days", "return"]].to_string(index=False))
    print("\n收益最高的5笔交易:")
    print(tr.nlargest(5, "return")[["ticker", "entry_date", "exit_date", "hold_days", "return"]].to_string(index=False))


import pandas as pd
import yfinance as yf

#年度收益对比
# 策略年度收益（从净值曲线算）
eq = pd.read_csv('equity.csv', index_col='date', parse_dates=True)
year_end = eq['equity'].resample('YE').last()
 
# 第一年用初始资金 100,000 作为基准
prev = year_end.shift(1).fillna(100_000)
strategy_annual = (year_end / prev - 1)
strategy_annual.index = strategy_annual.index.year
strategy_annual.name = 'strategy_return'
 
# 基准年度收益
bench = yf.download(['SPY', 'QQQ'], start='2010-01-01', end='2025-12-31',
                    auto_adjust=True, progress=False)['Close']
annual = bench.resample('YE').last().pct_change().dropna()
annual.index = annual.index.year
annual.columns = ['QQQ_return', 'SPY_return']
 
result = pd.concat([strategy_annual, annual], axis=1).dropna().round(3)
result['vs_SPY'] = (result['strategy_return'] - result['SPY_return']).round(3)
result['vs_QQQ'] = (result['strategy_return'] - result['QQQ_return']).round(3)
print(result.to_string())


