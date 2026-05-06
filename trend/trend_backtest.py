




import pandas as pd
import yfinance as yf
from config import INIT_CASH, FEE, BACKTEST_START, START, END

MAX_POS_TREND = 5
POS_SIZE_TREND = 0.20
DAILY_CRASH_PCT = 0.15
TWO_DAY_CRASH_PCT = 0.15
HOLD_TOLERANCE = 10
WEEKLY_DD_LIMIT = 0.001


def _next_monday(date):
    days_ahead = 7 - date.weekday()
    if days_ahead == 7:
        days_ahead = 7
    return date + pd.Timedelta(days=days_ahead)


def _load_tqqq(close_index):
    """下载 TQQQ 历史价格，对齐到回测日期索引"""
    raw = yf.download("TQQQ", start=START, end=END,
                      auto_adjust=True, progress=False)["Close"].squeeze()
    return raw.reindex(close_index).ffill()


def run_trend_backtest(out):
    close, open_ = out["close"], out["open"]
    exit_sma = out["exit_sma"]
    eligibility, momentum = out["eligibility"], out["momentum"]
    spy_below_200 = out["spy_below_200"]
    market_has_leaders = out["market_has_leaders"]

    print("  下载 TQQQ 数据...")
    tqqq_close = _load_tqqq(close.index)

    dates = close.index[close.index >= BACKTEST_START]
    all_idx = close.index

    cash = INIT_CASH
    pos = {}                 # 动量持仓 {ticker: {...}}
    tqqq_shares = 0          # TQQQ 持仓数量
    tqqq_entry_price = 0
    cooldown_until = {}
    trades, equity = [], []

    week_start_equity = INIT_CASH
    weekly_halt = False

    def current_equity(ref_date):
        mv = sum(p["shares"] * close.at[ref_date, t]
                 for t, p in pos.items()
                 if t in close.columns and not pd.isna(close.at[ref_date, t]))
        tqqq_mv = tqqq_shares * tqqq_close.at[ref_date] if tqqq_shares > 0 and not pd.isna(tqqq_close.at[ref_date]) else 0
        return cash + mv + tqqq_mv

    def open_position(tkr, today, equity_now):
        nonlocal cash
        px = open_.at[today, tkr]
        if pd.isna(px) or px <= 0:
            return False
        target = equity_now * POS_SIZE_TREND
        shares = int(target / (px * (1 + FEE)))
        cost = shares * px * (1 + FEE)
        if shares > 0 and cost <= cash:
            cash -= cost
            pos[tkr] = {
                "entry_date": today, "entry_price": px,
                "shares": shares, "entry_i": all_idx.get_loc(today),
            }
            return True
        return False

    def close_position(tkr, today, exit_price, reason):
        nonlocal cash
        p = pos[tkr]
        cash += p["shares"] * exit_price * (1 - FEE)
        trades.append({
            "ticker": tkr,
            "entry_date": p["entry_date"], "entry_price": p["entry_price"],
            "exit_date": today, "exit_price": exit_price,
            "shares": p["shares"],
            "return": exit_price / p["entry_price"] - 1,
            "hold_days": all_idx.get_loc(today) - p["entry_i"],
            "exit_reason": reason,
        })
        del pos[tkr]

    def buy_tqqq(today, equity_now):
        """全仓买入 TQQQ"""
        nonlocal cash, tqqq_shares, tqqq_entry_price
        px = tqqq_close.at[today]
        if pd.isna(px) or px <= 0:
            return
        shares = int(equity_now * (1 - FEE) / px)
        cost = shares * px * (1 + FEE)
        if shares > 0 and cost <= cash:
            cash -= cost
            tqqq_shares = shares
            tqqq_entry_price = px
            trades.append({
                "ticker": "TQQQ",
                "entry_date": today, "entry_price": px,
                "exit_date": None, "exit_price": None,
                "shares": shares, "return": None,
                "hold_days": None, "exit_reason": None,
            })

    def sell_tqqq(today):
        """卖出全部 TQQQ"""
        nonlocal cash, tqqq_shares, tqqq_entry_price
        if tqqq_shares <= 0:
            return
        px = tqqq_close.at[today]
        if pd.isna(px):
            return
        cash += tqqq_shares * px * (1 - FEE)
        ret = px / tqqq_entry_price - 1 if tqqq_entry_price > 0 else 0
        # 更新最后一笔 TQQQ 交易记录
        for t in reversed(trades):
            if t["ticker"] == "TQQQ" and t["exit_date"] is None:
                t["exit_date"] = today
                t["exit_price"] = px
                t["return"] = ret
                t["hold_days"] = (today - t["entry_date"]).days
                t["exit_reason"] = "regime_switch"
                break
        tqqq_shares = 0
        tqqq_entry_price = 0

    for i, today in enumerate(dates):
        loc = all_idx.get_loc(today)
        if loc < 3:
            equity.append((today, INIT_CASH))
            continue
        prev  = all_idx[loc - 1]
        prev2 = all_idx[loc - 2]
        prev3 = all_idx[loc - 3]
        spy_bad = bool(spy_below_200.loc[prev]) if prev in spy_below_200.index else False
        has_leaders = bool(market_has_leaders.loc[prev]) if prev in market_has_leaders.index else False

        # 周一重置周度追踪
        if today.weekday() == 0:
            week_start_equity = current_equity(prev)
            weekly_halt = False

        # ====== 市场状态切换 ======
        if has_leaders and tqqq_shares > 0:
            # 有领跑股了，卖掉 TQQQ，切换到动量策略
            sell_tqqq(today)

        if not has_leaders and len(pos) > 0:
            # 没有领跑股，清掉动量持仓，切换到 TQQQ
            for tkr in list(pos):
                px = open_.at[today, tkr]
                if not pd.isna(px):
                    close_position(tkr, today, px, "regime_switch_to_tqqq")

        # ====== TQQQ 模式 ======
        if not has_leaders and not spy_bad:
            if tqqq_shares == 0 and cash > 0:
                eq_now = current_equity(today)
                buy_tqqq(today, eq_now)

        # ====== 动量策略模式 ======
        if has_leaders:
            crashed = False

            # 1) 单日暴跌熔断
            for tkr in list(pos):
                c_prev  = close.at[prev, tkr]
                c_today = close.at[today, tkr]
                if pd.isna(c_prev) or pd.isna(c_today):
                    continue
                if c_today / c_prev - 1 <= -DAILY_CRASH_PCT:
                    close_position(tkr, today, c_today, "daily_crash")
                    crashed = True

            # 2) 2日熔断（持仓至少2天）
            for tkr in list(pos):
                if (today - pos[tkr]["entry_date"]).days < 2:
                    continue
                c_prev2 = close.at[prev2, tkr]
                c_today = close.at[today, tkr]
                if pd.isna(c_prev2) or pd.isna(c_today):
                    continue
                if c_today / c_prev2 - 1 <= -TWO_DAY_CRASH_PCT:
                    px = open_.at[today, tkr]
                    if not pd.isna(px):
                        close_position(tkr, today, px, "two_day_crash")
                        cooldown_until[tkr] = _next_monday(today)
                        crashed = True

            # 3) 3日熔断（持仓至少3天）
            for tkr in list(pos):
                if (today - pos[tkr]["entry_date"]).days < 3:
                    continue
                c_prev3 = close.at[prev3, tkr]
                c_today = close.at[today, tkr]
                if pd.isna(c_prev3) or pd.isna(c_today):
                    continue
                if c_today / c_prev3 - 1 <= -TWO_DAY_CRASH_PCT:
                    px = open_.at[today, tkr]
                    if not pd.isna(px):
                        close_position(tkr, today, px, "three_day_crash")
                        cooldown_until[tkr] = _next_monday(today)
                        crashed = True

            # 4) SPY 跌破 200 日线
            if spy_bad:
                for tkr in list(pos):
                    px = open_.at[today, tkr]
                    if not pd.isna(px):
                        close_position(tkr, today, px, "spy_below_200")
                if tqqq_shares > 0:
                    sell_tqqq(today, reason="spy_below_200")     # 同时清 TQQQ ← 新增

            # 5) 跌破 50 日线
            for tkr in list(pos):
                c   = close.at[prev, tkr]
                sma = exit_sma.at[prev, tkr]
                if pd.isna(c) or pd.isna(sma):
                    continue
                if c < sma:
                    px = open_.at[today, tkr]
                    if not pd.isna(px):
                        close_position(tkr, today, px, "below_sma50")

            # 6) 周度亏损熔断 检查
            if week_start_equity > 0:
                eq_now = current_equity(today)
                if eq_now / week_start_equity - 1 <= -WEEKLY_DD_LIMIT:
                    weekly_halt = True

            # 7) 周一调仓
            if today.weekday() == 0 and not spy_bad and not weekly_halt:
                elig   = eligibility.loc[prev]
                cands  = momentum.loc[prev, elig[elig].index].dropna()
                ranked = cands.sort_values(ascending=False)
                ranked = ranked[ranked.index.map(
                    lambda t: cooldown_until.get(t, pd.Timestamp.min) <= today
                )]
                top_tolerance = ranked.head(HOLD_TOLERANCE).index.tolist()
                top_buy       = ranked.head(MAX_POS_TREND).index.tolist()

                for tkr in list(pos):
                    if tkr not in top_tolerance:
                        px = open_.at[today, tkr]
                        if not pd.isna(px):
                            close_position(tkr, today, px, "rebalance_out")

                mv_prev = sum(p["shares"] * close.at[prev, t]
                              for t, p in pos.items()
                              if not pd.isna(close.at[prev, t]))
                equity_now = cash + mv_prev

                for tkr in top_buy:
                    if len(pos) >= MAX_POS_TREND:
                        break
                    if tkr not in pos:
                        open_position(tkr, today, equity_now)

        # ====== 盯市 ======
        mv = sum(p["shares"] * close.at[today, t]
                 for t, p in pos.items()
                 if not pd.isna(close.at[today, t]))
        tqqq_mv = tqqq_shares * tqqq_close.at[today] if tqqq_shares > 0 and not pd.isna(tqqq_close.at[today]) else 0
        equity.append((today, cash + mv + tqqq_mv))

    eq = pd.DataFrame(equity, columns=["date", "equity"]).set_index("date")
    tr_df = pd.DataFrame([t for t in trades if t["return"] is not None])
    return eq, tr_df

