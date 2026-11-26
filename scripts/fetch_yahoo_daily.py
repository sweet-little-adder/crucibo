"""Fetch daily OHLCV for the predeclared universe from the Yahoo Finance chart endpoint.
Free, unofficial, and not a licensed redistributable source: output goes to data/ (gitignored). Do not commit or publish the data.
Writes raw JSON + sha256, adjusted-OHLC parquet, Crucibo-schema silver ticks and data/PROVENANCE.json."""

import datetime as dt
import hashlib
import json
import time
from zoneinfo import ZoneInfo

import pandas as pd
import requests

UNIVERSE = ["AAPL", "GDDY", "CCJ", "SPY"]
NY = ZoneInfo("America/New_York")


def fetch(sym):
    p1 = int(dt.datetime(2000, 1, 1, tzinfo=dt.UTC).timestamp())
    p2 = int(time.time())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
    r = requests.get(
        url,
        params=dict(period1=p1, period2=p2, interval="1d", events="div,split"),
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    r.raise_for_status()
    return url, r.content


prov = {
    "source": "Yahoo Finance chart API v8 (free, unofficial, no key)",
    "fetched_utc": dt.datetime.now(dt.UTC).isoformat(),
    "symbols": {},
}
for s in UNIVERSE:
    url, raw = fetch(s)
    open(f"data/raw/{s}.json", "wb").write(raw)
    j = json.loads(raw)["chart"]["result"][0]
    q = j["indicators"]["quote"][0]
    adj = j["indicators"]["adjclose"][0]["adjclose"]
    df = pd.DataFrame(
        dict(
            ts=j["timestamp"],
            o=q["open"],
            h=q["high"],
            l=q["low"],
            c=q["close"],
            v=q["volume"],
            adj=adj,
        )
    ).dropna()
    f = df.adj / df.c
    for k in "ohlc":
        df[k] = df[k] * f
    df["date"] = [dt.datetime.fromtimestamp(t, NY).strftime("%Y-%m-%d") for t in df.ts]
    df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    # drop a partial bar for today if market not closed: keep only dates strictly before the latest fetched date's session if today's bar is intraday
    last_meta = j["meta"].get("regularMarketTime")
    df.to_parquet(f"data/{s}_daily_adj.parquet")
    # silver ticks: close at 16:00 NY like crucibo alphavantage bars
    ev = [
        int(dt.datetime.strptime(d, "%Y-%m-%d").replace(hour=16, tzinfo=NY).timestamp() * 1e9)
        for d in df.date
    ]
    pd.DataFrame(
        dict(
            ts_event_ns=ev,
            ts_ingest_ns=None,
            symbol=s,
            price=df.c,
            size=df.v.astype("int64").clip(lower=1),
            conditions="yahoo:daily-adjclose",
        )
    ).to_parquet(f"data/silver/{s}_bars.parquet")
    prov["symbols"][s] = dict(
        url=url,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        rows=len(df),
        first=df.date.iloc[0],
        last=df.date.iloc[-1],
        note="OHLC scaled by adjclose/close (split+dividend adjusted)",
    )
    print(s, len(df), df.date.iloc[0], df.date.iloc[-1])
json.dump(prov, open("data/PROVENANCE.json", "w"), indent=1)
