# import pandas as pd
# from config import INIT_CASH, FEE, BACKTEST_START

# MAX_POS_TREND = 5
# POS_SIZE_TREND = 0.20
# DAILY_CRASH_PCT = 0.20             # 单日跌幅 ≥ 20% 立即清仓
# HOLD_TOLERANCE = 10                # 排名跌出 top 10 才踢出（之前是 top 5）


# def run_trend_backtest(out):
#     close, open_ = out["close"], out["open"]
#     exit_sma, eligibility, momentum = out["exit_sma"], out["eligibility"], out["momentum"]
#     spy_below_200 = out["spy_below_200"]

#     dates = close.index[close.index >= BACKTEST_START]
#     all_idx = close.index

#     cash = INIT_CASH
#     pos = {}
#     trades, equity = [], []

#     def open_position(tkr, today, equity_now):
#         nonlocal cash
#         px = open_.at[today, tkr]
#         if pd.isna(px) or px <= 0:
#             return False
#         target = equity_now * POS_SIZE_TREND
#         shares = int(target / (px * (1 + FEE)))
#         cost = shares * px * (1 + FEE)
#         if shares > 0 and cost <= cash:
#             cash -= cost
#             pos[tkr] = {
#                 "entry_date": today, "entry_price": px,
#                 "shares": shares, "entry_i": all_idx.get_loc(today),
#             }
#             return True
#         return False

#     def close_position(tkr, today, exit_price, reason):
#         nonlocal cash
#         p = pos[tkr]
#         cash += p["shares"] * exit_price * (1 - FEE)
#         trades.append({
#             "ticker": tkr,
#             "entry_date": p["entry_date"], "entry_price": p["entry_price"],
#             "exit_date": today, "exit_price": exit_price,
#             "shares": p["shares"],
#             "return": exit_price / p["entry_price"] - 1,
#             "hold_days": all_idx.get_loc(today) - p["entry_i"],
#             "exit_reason": reason,
#         })
#         del pos[tkr]

#     for i, today in enumerate(dates):
#         loc = all_idx.get_loc(today)
#         if loc == 0:
#             equity.append((today, cash))
#             continue
#         prev = all_idx[loc - 1]
#         spy_bad = bool(spy_below_200.loc[prev]) if prev in spy_below_200.index else False

#         # 1) 单日暴跌熔断
#         for tkr in list(pos):
#             c_prev = close.at[prev, tkr]
#             c_today = close.at[today, tkr]
#             if pd.isna(c_prev) or pd.isna(c_today):
#                 continue
#             if c_today / c_prev - 1 <= -DAILY_CRASH_PCT:
#                 close_position(tkr, today, c_today, "daily_crash")

#         # 2) SPY 跌破 200 日线 → 全部清仓
#         if spy_bad:
#             for tkr in list(pos):
#                 px = open_.at[today, tkr]
#                 if not pd.isna(px):
#                     close_position(tkr, today, px, "spy_below_200")

#         # 3) 跌破 50 日线 → 出场
#         for tkr in list(pos):
#             c = close.at[prev, tkr]
#             sma = exit_sma.at[prev, tkr]
#             if pd.isna(c) or pd.isna(sma):
#                 continue
#             if c < sma:
#                 px = open_.at[today, tkr]
#                 if not pd.isna(px):
#                     close_position(tkr, today, px, "below_sma50")

#         # 4) 周一调仓: 只踢出前10之外的，让赢家继续持有
#         if today.weekday() == 0 and not spy_bad:
#             elig = eligibility.loc[prev]
#             cands = momentum.loc[prev, elig[elig].index].dropna()
#             ranked = cands.sort_values(ascending=False)

#             # 关键改动：top 10 容忍区
#             top_tolerance = ranked.head(HOLD_TOLERANCE).index.tolist()  # 前10名
#             top_buy = ranked.head(MAX_POS_TREND).index.tolist()         # 前5名（用于买入）

#             # 持仓中跌出前10的才卖出
#             for tkr in list(pos):
#                 if tkr not in top_tolerance:
#                     px = open_.at[today, tkr]
#                     if not pd.isna(px):
#                         close_position(tkr, today, px, "rebalance_out")

#             # 重新计算净值
#             mv_prev = sum(p["shares"] * close.at[prev, t]
#                           for t, p in pos.items()
#                           if not pd.isna(close.at[prev, t]))
#             equity_now = cash + mv_prev

#             # 用前5买入空缺仓位
#             for tkr in top_buy:
#                 if len(pos) >= MAX_POS_TREND:
#                     break
#                 if tkr not in pos:
#                     open_position(tkr, today, equity_now)

#         # 盯市
#         mv = sum(p["shares"] * close.at[today, t]
#                  for t, p in pos.items()
#                  if not pd.isna(close.at[today, t]))
#         equity.append((today, cash + mv))

#     eq = pd.DataFrame(equity, columns=["date", "equity"]).set_index("date")
#     tr = pd.DataFrame(trades)
#     return eq, tr

import pandas as pd
from config import INIT_CASH, FEE, BACKTEST_START

MAX_POS_TREND = 5
POS_SIZE_TREND = 0.20
DAILY_CRASH_PCT = 0.20
TWO_DAY_CRASH_PCT = 0.20
HOLD_TOLERANCE = 10
WEEKLY_DD_LIMIT = 0.001


def _next_monday(date):
    days_ahead = 7 - date.weekday()
    if days_ahead == 7:
        days_ahead = 7
    return date + pd.Timedelta(days=days_ahead)


def run_trend_backtest(out):
    close, open_ = out["close"], out["open"]
    exit_sma, eligibility, momentum = out["exit_sma"], out["eligibility"], out["momentum"]
    spy_below_200 = out["spy_below_200"]

    dates = close.index[close.index >= BACKTEST_START]
    all_idx = close.index

    cash = INIT_CASH
    pos = {}
    cooldown_until = {}  # {ticker: 下周一日期}，冷却期内不买
    trades, equity = [], []
    refill_next_open = False  # 暴跌清仓后次日补仓标志

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

    for i, today in enumerate(dates):
        loc = all_idx.get_loc(today)
        if loc < 3:
            equity.append((today, cash))
            continue
        prev  = all_idx[loc - 1]
        prev2 = all_idx[loc - 2]
        prev3 = all_idx[loc - 3]
        spy_bad = bool(spy_below_200.loc[prev]) if prev in spy_below_200.index else False

        # ====== 0) 暴跌后次日补仓 ======
        if refill_next_open and not spy_bad and len(pos) < MAX_POS_TREND:
            elig   = eligibility.loc[prev]
            cands  = momentum.loc[prev, elig[elig].index].dropna()
            ranked = cands.sort_values(ascending=False)
            ranked = ranked[ranked.index.map(
                lambda t: cooldown_until.get(t, pd.Timestamp.min) <= today
            )]
            mv_prev    = sum(p["shares"] * close.at[prev, t]
                             for t, p in pos.items()
                             if not pd.isna(close.at[prev, t]))
            equity_now = cash + mv_prev
            for tkr in ranked.head(MAX_POS_TREND).index:
                if len(pos) >= MAX_POS_TREND:
                    break
                if tkr not in pos:
                    open_position(tkr, today, equity_now)
        refill_next_open = False

        # ====== 1) 单日暴跌熔断 ======
        crashed = False
        for tkr in list(pos):
            c_prev  = close.at[prev, tkr]
            c_today = close.at[today, tkr]
            if pd.isna(c_prev) or pd.isna(c_today):
                continue
            if c_today / c_prev - 1 <= -DAILY_CRASH_PCT:
                close_position(tkr, today, c_today, "daily_crash")
                crashed = True

        # ====== 2) 连续2日累计跌幅熔断 ======
        for tkr in list(pos):
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

        # ====== 3) 连续3日累计跌幅熔断 ======
        for tkr in list(pos):
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

        if crashed:
            refill_next_open = True

        # ====== 3) SPY 跌破 200 日线 → 全部清仓 ======
        if spy_bad:
            for tkr in list(pos):
                px = open_.at[today, tkr]
                if not pd.isna(px):
                    close_position(tkr, today, px, "spy_below_200")

        # ====== 4) 跌破 50 日线 → 出场 ======
        for tkr in list(pos):
            c   = close.at[prev, tkr]
            sma = exit_sma.at[prev, tkr]
            if pd.isna(c) or pd.isna(sma):
                continue
            if c < sma:
                px = open_.at[today, tkr]
                if not pd.isna(px):
                    close_position(tkr, today, px, "below_sma50")

        # ====== 5) 周一调仓 ======
        if today.weekday() == 0 and not spy_bad:
            elig   = eligibility.loc[prev]
            cands  = momentum.loc[prev, elig[elig].index].dropna()
            ranked = cands.sort_values(ascending=False)

            # 排除冷却期中的股票
            ranked = ranked[ranked.index.map(
                lambda t: cooldown_until.get(t, pd.Timestamp.min) <= today
            )]

            top_tolerance = ranked.head(HOLD_TOLERANCE).index.tolist()
            top_buy       = ranked.head(MAX_POS_TREND).index.tolist()

            # 踢出不在 top 10 的持仓
            for tkr in list(pos):
                if tkr not in top_tolerance:
                    px = open_.at[today, tkr]
                    if not pd.isna(px):
                        close_position(tkr, today, px, "rebalance_out")

            # 重新计算净值
            mv_prev = sum(p["shares"] * close.at[prev, t]
                          for t, p in pos.items()
                          if not pd.isna(close.at[prev, t]))
            equity_now = cash + mv_prev

            # 买入空缺仓位
            for tkr in top_buy:
                if len(pos) >= MAX_POS_TREND:
                    break
                if tkr not in pos:
                    open_position(tkr, today, equity_now)

        # ====== 盯市 ======
        mv = sum(p["shares"] * close.at[today, t]
                 for t, p in pos.items()
                 if not pd.isna(close.at[today, t]))
        equity.append((today, cash + mv))

    eq = pd.DataFrame(equity, columns=["date", "equity"]).set_index("date")
    tr = pd.DataFrame(trades)
    return eq, tr