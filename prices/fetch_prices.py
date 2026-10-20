"""Two years of daily closes for every company in listed/companies.json, from Yahoo Finance.

Writes out/p/<KEY>.json in Dalal & Wall's price format. KEY is the NSE symbol (with & as _),
or BSE plus the scrip code for a company listed only on BSE. The workflow force-pushes out/ to
the "prices" branch, so the repository doesn't grow with each day's data. A company whose
download fails keeps its previous file.
"""
import datetime, json, pathlib, sys, time
import pandas as pd
import yfinance as yf

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'out' / 'p'
BATCH = 80
PERIOD = '2y'


def targets():
    rows = json.loads((ROOT / 'listed' / 'companies.json').read_text())['rows']
    out = {}
    for name, nse, bse in rows:
        name = name.replace(' Limited', '').replace(' Ltd.', '').replace(' Ltd', '').strip()
        if nse:
            out[nse + '.NS'] = (nse.replace('&', '_'), nse, name)
        elif bse:
            out[bse + '.BO'] = ('BSE' + bse, bse, name)
    return out


def closes(frame):
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(-1) if 'Close' in frame.columns.get_level_values(-1) else frame.columns.get_level_values(0)
    if 'Close' not in frame.columns:
        return None
    s = frame['Close'].dropna()
    s = s[s > 0]
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s if len(s) >= 5 else None


def download(tickers):
    got = {}
    try:
        raw = yf.download(tickers, period=PERIOD, interval='1d', group_by='ticker', auto_adjust=False, threads=True, progress=False)
    except Exception as e:
        print('batch failed:', str(e)[:200]); return got
    for t in tickers:
        try:
            sub = raw[t] if isinstance(raw.columns, pd.MultiIndex) and t in raw.columns.get_level_values(0) else (raw if len(tickers) == 1 else None)
            s = closes(sub.copy()) if sub is not None else None
            if s is not None:
                got[t] = s
        except Exception:
            pass
    return got


def doc(sym, name, s):
    dates = [d.date() for d in s.index]
    d0 = dates[0]
    return {'s': sym, 'n': name, 'ind': '', 'idx': None, 'from': d0.isoformat(), 'd': [(d - d0).days for d in dates],
            'c': [round(float(v), 2) for v in s.values], 'last': round(float(s.values[-1]), 2), 'lastDate': dates[-1].isoformat()}


def main():
    want = targets()
    OUT.mkdir(parents=True, exist_ok=True)
    tickers = list(want)
    print(len(tickers), 'companies')
    got = {}
    for i in range(0, len(tickers), BATCH):
        got.update(download(tickers[i:i + BATCH]))
        if i // BATCH % 10 == 0:
            print(f'{i + BATCH}/{len(tickers)} tried, {len(got)} with prices')
        time.sleep(1)
    missing = [t for t in tickers if t not in got]
    print(len(missing), 'missing after the first pass; retrying in small batches')
    time.sleep(20)
    for i in range(0, len(missing), 10):
        got.update(download(missing[i:i + 10]))
        time.sleep(2)
    written = 0
    for t, s in got.items():
        key, sym, name = want[t]
        (OUT / f'{key}.json').write_text(json.dumps(doc(sym, name, s), separators=(',', ':')))
        written += 1
    kept = sum(1 for t in tickers if t not in got and (OUT / f'{want[t][0]}.json').exists())
    last = max((s.index[-1].date() for s in got.values()), default=None)
    meta = {'updated': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'lastTradingDate': last.isoformat() if last else None,
            'companies': len(tickers), 'refreshed': written, 'keptFromBefore': kept, 'none': len(tickers) - written - kept,
            'source': 'Yahoo Finance daily closes via yfinance (unofficial)'}
    (OUT / '_meta.json').write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))
    if written < len(tickers) * 0.5:
        sys.exit('Fewer than half the companies downloaded; not publishing this run.')


if __name__ == '__main__':
    main()
