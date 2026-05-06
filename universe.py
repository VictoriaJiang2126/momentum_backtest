import pandas as pd
import requests
from io import StringIO
from config import CACHE

URL = ("https://www.ishares.com/us/products/239714/ishares-russell-3000-etf/"
       "1467271812596.ajax?fileType=csv&fileName=IWV_holdings&dataType=fund")


def get_russell3000(refresh=False):
    cache = CACHE / "russell3000.parquet"
    if cache.exists() and not refresh:
        return pd.read_parquet(cache)["ticker"].tolist()

    r = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text), skiprows=9, on_bad_lines="skip")

    tickers = (df["Ticker"].dropna().astype(str)
               .str.upper().str.replace(".", "-", regex=False))
    tickers = sorted({t for t in tickers
                     if t.replace("-", "").isalpha() and 1 <= len(t) <= 6})

    pd.DataFrame({"ticker": tickers}).to_parquet(cache)
    print(f"Russell 3000: {len(tickers)} tickers")
    return tickers
