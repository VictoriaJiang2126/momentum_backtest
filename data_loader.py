# import yfinance as yf
# import pandas as pd
# from config import CACHE, START, END

# PRICES = CACHE / "prices.parquet"


# def download_prices(tickers, refresh=False):
#     if PRICES.exists() and not refresh:
#         return pd.read_parquet(PRICES)

#     print(f"Downloading {len(tickers)} tickers from {START} to {END}...")
#     raw = yf.download(tickers, start=START, end=END,
#                       auto_adjust=True, threads=True, progress=True)

#     # MultiIndex (Field, Ticker) -> long format
#     df = raw.stack(level=1, future_stack=True).reset_index()
#     df.columns = ["date", "ticker"] + [c.lower() for c in df.columns[2:]]
#     df = df.dropna(subset=["close"]).sort_values(["ticker", "date"])

#     df.to_parquet(PRICES)
#     print(f"Saved {len(df):,} rows, {df['ticker'].nunique()} tickers")
#     return df


import time
import yfinance as yf
import pandas as pd
from config import CACHE, START, END

PRICES = CACHE / "prices.parquet"
FAILED = CACHE / "failed_tickers.txt"
_cache = None


def _load_failed():
    if FAILED.exists():
        return set(FAILED.read_text().splitlines())
    return set()


def _save_failed(failed_set):
    FAILED.write_text("\n".join(sorted(failed_set)))

BATCH_SIZE = 50          # 每批 50 只（之前 yfinance 一次性发太多被限流）
SLEEP_BETWEEN = 3        # 每批间停 3 秒
MAX_RETRIES = 3          # 失败重试次数
RETRY_WAIT = 60          # 触发限流后等 60 秒再试


def _download_batch(tickers):
    """下载一批，处理列格式，失败时返回空 DataFrame"""
    raw = yf.download(tickers, start=START, end=END,
                      auto_adjust=True, threads=True, progress=False)
    if raw.empty:
        return pd.DataFrame()
    # 单票时 columns 不是 MultiIndex
    if not isinstance(raw.columns, pd.MultiIndex):
        df = raw.reset_index()
        df.columns = [c.lower() for c in df.columns]
        df["ticker"] = tickers[0]
    else:
        df = raw.stack(level=1, future_stack=True).reset_index()
        df.columns = ["date", "ticker"] + [c.lower() for c in df.columns[2:]]
    return df.dropna(subset=["close"])

#refresh=True 可以强制重新加载。
def download_prices(tickers, refresh=False):
    global _cache
    if _cache is not None and not refresh:
        return _cache

    # 已有缓存的处理：只补缺失的 ticker
    have = set()
    existing = []
    if PRICES.exists() and not refresh:
        old = pd.read_parquet(PRICES)
        # 只保留时间范围内的旧数据
        old = old[(old["date"] >= START) & (old["date"] <= END)]
        if not old.empty:
            have = set(old["ticker"].unique())
            existing.append(old)

    known_failed = set() if refresh else _load_failed()
    todo = sorted(set(tickers) - have - known_failed)
    if not todo:
        _cache = pd.concat(existing, ignore_index=True)
        return _cache

    print(f"已有 {len(have)} 只，需下载 {len(todo)} 只 ({START} ~ {END})")
    print(f"批次大小 {BATCH_SIZE}, 每批间隔 {SLEEP_BETWEEN}s")

    n_batches = (len(todo) - 1) // BATCH_SIZE + 1
    new_frames = []

    for i in range(0, len(todo), BATCH_SIZE):
        batch = todo[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1

        for attempt in range(MAX_RETRIES):
            try:
                df = _download_batch(batch)
                if not df.empty:
                    new_frames.append(df)
                    got_tickers = set(df["ticker"].unique())
                else:
                    got_tickers = set()
                got = len(got_tickers)
                print(f"  批次 {batch_num}/{n_batches}: 成功 {got}/{len(batch)}")
                failed_in_batch = set(batch) - got_tickers
                if failed_in_batch:
                    known_failed |= failed_in_batch
                    _save_failed(known_failed)
                break
            except Exception as e:
                msg = str(e).lower()
                if "rate" in msg or "too many" in msg or "429" in msg:
                    print(f"  批次 {batch_num} 触发限流，等 {RETRY_WAIT}s 后重试 ({attempt+1}/{MAX_RETRIES})")
                    time.sleep(RETRY_WAIT)
                else:
                    print(f"  批次 {batch_num} 错误: {e}")
                    break

        time.sleep(SLEEP_BETWEEN)

        # 每 20 批存一次盘，防止跑到一半挂掉前功尽弃
        if batch_num % 20 == 0 and new_frames:
            tmp = pd.concat(existing + new_frames, ignore_index=True)
            tmp = tmp.drop_duplicates(["date", "ticker"]).sort_values(["ticker", "date"])
            tmp.to_parquet(PRICES)
            print(f"  [中途保存] 当前累计 {tmp['ticker'].nunique()} 只")

    # 最终合并保存
    all_frames = existing + new_frames
    if not all_frames:
        return pd.DataFrame()
    out = pd.concat(all_frames, ignore_index=True)
    out = out.drop_duplicates(["date", "ticker"]).sort_values(["ticker", "date"])
    out.to_parquet(PRICES)
    print(f"完成：{len(out):,} 行, {out['ticker'].nunique()} 只股票")
    _cache = out
    return out