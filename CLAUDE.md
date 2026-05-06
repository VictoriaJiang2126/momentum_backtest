# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the backtest

```bash
python main.py          # 完整回测，输出 equity.csv + trades.csv
python test.py          # 年度收益对比（需先跑 main.py 生成 equity.csv）
```

所有可调参数集中在 `config.py`，无需改动其他文件即可调整策略。

## Architecture

Pipeline: `universe.py` → `data_loader.py` → `signals.py` → `backtest.py` → `metrics.py`

**信号生成是向量化的（pandas），回测执行是自定义事件驱动循环（非 vectorbt）。**

| 文件 | 职责 |
|------|------|
| `config.py` | 全部参数（时间范围、仓位、止损、筛选阈值） |
| `universe.py` | 从 iShares IWV ETF CSV 抓取 Russell 3000 成分股，缓存到 `cache/russell3000.parquet` |
| `data_loader.py` | 批量下载 yfinance 数据，增量补缺，每 20 批中途保存，缓存到 `cache/prices.parquet` |
| `signals.py` | 向量化计算指标（SMA/RVol/52w high/周涨幅），生成入场布尔矩阵，叠加 SPY 市场过滤器 |
| `backtest.py` | 事件驱动日循环：前一日收盘出场信号 → 当日开盘卖，前一日入场信号按 RVol 排序 → 当日开盘买 |
| `metrics.py` | 计算并打印 CAGR、Sharpe、最大回撤、胜率、盈亏比等指标 |

## Key design decisions

**防前视偏差（Lookahead Bias）：** t 日信号 → t+1 日开盘成交。`backtest.py` 中出场检查用 `prev`（前一日收盘），买卖执行用 `today`（当日开盘价）。

**市场过滤器：** `signals.py` 中当 SPY 收盘价 < 200 日均线时，屏蔽当日所有入场信号。

**持仓限制（跨股票资金约束）：** `backtest.py` 的 `run_backtest()` 中用 `pos` dict 跟踪当前持仓，每日候选按 RVol 降序排序后，只买到 `MAX_POS`（5只）为止。

**数据缓存策略：** `download_prices()` 增量下载——读取已有 parquet，只补缺失的 ticker，每 20 批写一次磁盘防中途丢失。

## Known limitations

- **幸存者偏差**：只用当前 Russell 3000 成分股，已退市股票不包含，回测收益率系统性偏高（约 2-5%/年）。
- `doc.md` 中的设计方案（vectorbt）与实际实现（自定义事件驱动循环）不同，以代码为准。
