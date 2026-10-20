"""Daily closes for every company in listed/companies.json, for Dalal & Wall's price charts.

Sources:
- The exchanges' own daily trading files ("bhavcopies"): NSE's for NSE-listed companies (main
  board and SME) and BSE's for companies listed only on BSE. Each run adds the days it hasn't
  got yet, newest first, so two years build up over a few runs.
- Yahoo Finance, once, for the two-year history of NSE companies that have no file yet.

Writes out/p/<KEY>.json in the page's price format. KEY is the NSE symbol (with & as _), or BSE
plus the scrip code. The workflow force-pushes out/ to the "prices" branch, so the repository
doesn't grow with each day's data. out/p/_meta.json records which trading days are in.
"""
import csv, datetime, io, json, pathlib, sys, time, zipfile
import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'out' / 'p'
KEEP_DAYS = 760          # about two years
DAY_BUDGET = 170         # trading files per exchange per run
TIME_BUDGET = 70 * 60    # stop downloading after this many seconds
START = time.time()
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36', 'Accept': '*/*', 'Accept-Language': 'en-GB,en;q=0.9'}
SESSION = requests.Session()
NOTES = []


def note(msg):
    print(msg); NOTES.append(msg)


def get(url, headers=None):
    for attempt in range(2):
        try:
            r = SESSION.get(url, headers={**UA, **(headers or {})}, timeout=60)
            if r.status_code == 404:
                return None
            if r.ok and r.content:
                return r
        except Exception as e:
            print(url, type(e).__name__)
        time.sleep(2 + 3 * attempt)
    return False  # failed, unlike None (no file for that day)


def companies():
    rows = json.loads((ROOT / 'listed' / 'companies.json').read_text())['rows']
    out = {}
    for name, nse, bse in rows:
        name = name.replace(' Limited', '').replace(' Ltd.', '').replace(' Ltd', '').strip()
        if nse:
            out[nse.replace('&', '_')] = {'s': nse, 'n': name, 'nse': nse}
        elif bse:
            out['BSE' + bse] = {'s': bse, 'n': name, 'bse': bse}
    return out


def load_existing():
    series = {}
    for f in OUT.glob('*.json'):
        if f.name.startswith('_'):
            continue
        try:
            d = json.loads(f.read_text())
            d0 = datetime.date.fromisoformat(d['from'])
            series[f.stem] = {(d0 + datetime.timedelta(days=k)).isoformat(): v for k, v in zip(d['d'], d['c'])}
        except Exception:
            pass
    return series


def yahoo_history(want, series):
    """Two years of history from Yahoo for NSE companies with no file yet."""
    todo = [k for k, c in want.items() if 'nse' in c and len(series.get(k, {})) < 30]
    if not todo:
        return
    try:
        import pandas as pd
        import yfinance as yf
    except ImportError:
        note('yfinance not installed; skipping Yahoo'); return
    note(f'Yahoo: {len(todo)} NSE companies need history')
    got = 0
    for i in range(0, len(todo), 50):
        if time.time() - START > TIME_BUDGET / 2:
            note('Yahoo: stopped early for time'); break
        batch = todo[i:i + 50]
        tick = {want[k]['nse'] + '.NS': k for k in batch}
        try:
            raw = yf.download(list(tick), period='2y', interval='1d', group_by='ticker', auto_adjust=False, threads=True, progress=False)
        except Exception as e:
            print('Yahoo batch failed', str(e)[:120]); time.sleep(10); continue
        for t, k in tick.items():
            try:
                sub = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
                s = sub['Close'].dropna()
                s = s[s > 0]
                if len(s) >= 5:
                    ser = series.setdefault(k, {})
                    for d, v in s.items():
                        ser.setdefault(pd.Timestamp(d).date().isoformat(), round(float(v), 2))
                    got += 1
            except Exception:
                pass
        time.sleep(2)
    note(f'Yahoo: history for {got}')


def parse_udiff(content):
    if content[:2] == b'PK':
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            content = z.read(z.namelist()[0])
    return list(csv.DictReader(io.StringIO(content.decode('utf-8-sig', 'replace'))))


def nse_day(day):
    r = get(f'https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip', {'Referer': 'https://www.nseindia.com/'})
    if not r:
        return r
    out = {}
    for x in parse_udiff(r.content):
        sym, px = (x.get('TckrSymb') or '').strip(), x.get('ClsPric')
        if sym and px and (x.get('FinInstrmTp') or 'STK').strip() in ('STK', ''):
            try: out[sym] = float(px)
            except ValueError: pass
    # SME companies, if the main file doesn't carry them
    sme = get(f'https://nsearchives.nseindia.com/archives/sme/bhavcopy/sme{day:%d%m%y}.csv', {'Referer': 'https://www.nseindia.com/'})
    if sme:
        for x in csv.DictReader(io.StringIO(sme.content.decode('utf-8-sig', 'replace'))):
            x = {k.strip().upper(): (v or '').strip() for k, v in x.items() if k}
            sym, px = x.get('SYMBOL'), x.get('CLOSE_PRICE') or x.get('CLOSE')
            if sym and px and sym not in out:
                try: out[sym] = float(px)
                except ValueError: pass
    return out


def bse_day(day):
    r = get(f'https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{day:%Y%m%d}_F_0000.CSV', {'Referer': 'https://www.bseindia.com/'})
    if not r:
        return r
    if not r.content.lstrip().startswith(b'TradDt'):
        return False
    out = {}
    for x in parse_udiff(r.content):
        code, px = (x.get('FinInstrmId') or '').strip(), x.get('ClsPric')
        if code and px:
            try: out[code] = float(px)
            except ValueError: pass
    return out


def main():
    want = companies()
    OUT.mkdir(parents=True, exist_ok=True)
    meta_path = OUT / '_meta.json'
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    days_in = {ex: set(meta.get('days', {}).get(ex, [])) for ex in ('NSE', 'BSE')}
    no_file = {ex: set(meta.get('noFile', {}).get(ex, [])) for ex in ('NSE', 'BSE')}
    series = load_existing()
    note(f'{len(want)} companies, {len(series)} files from before')
    yahoo_history(want, series)

    nse_keys = {c['nse']: k for k, c in want.items() if 'nse' in c}
    bse_keys = {c['bse']: k for k, c in want.items() if 'bse' in c}
    today = datetime.date.today()
    weekdays = [today - datetime.timedelta(days=i) for i in range(0, KEEP_DAYS) if (today - datetime.timedelta(days=i)).weekday() < 5]
    for ex, fetch, keys in (('NSE', nse_day, nse_keys), ('BSE', bse_day, bse_keys)):
        done = 0
        for day in weekdays:
            iso = day.isoformat()
            # a day with no file is a holiday, unless it is recent and the file may not be out yet
            if iso in days_in[ex] or (iso in no_file[ex] and (today - day).days > 3):
                continue
            if ex == 'BSE' and iso in no_file['NSE'] and (today - day).days > 3:
                no_file['BSE'].add(iso); continue  # BSE doesn't say "no file" clearly; NSE's holidays are BSE's too
            if done >= DAY_BUDGET or time.time() - START > TIME_BUDGET:
                break
            rows = fetch(day); done += 1
            if rows is None:
                no_file[ex].add(iso); continue
            if rows is False:
                continue  # couldn't fetch; try again next run
            for code, px in rows.items():
                k = keys.get(code)
                if k and px > 0:
                    series.setdefault(k, {})[iso] = round(px, 2)
            days_in[ex].add(iso)
            time.sleep(0.7)
        note(f'{ex}: fetched {done} trading files this run; {len(days_in[ex])} days in')

    cutoff = (today - datetime.timedelta(days=KEEP_DAYS)).isoformat()
    written = 0
    for k, ser in series.items():
        if k not in want:
            continue
        pts = sorted((d, v) for d, v in ser.items() if d >= cutoff)
        if len(pts) < 2:
            continue
        d0 = datetime.date.fromisoformat(pts[0][0])
        c = want[k]
        doc = {'s': c['s'], 'n': c['n'], 'ind': '', 'idx': None, 'from': pts[0][0],
               'd': [(datetime.date.fromisoformat(d) - d0).days for d, _ in pts], 'c': [v for _, v in pts], 'last': pts[-1][1], 'lastDate': pts[-1][0]}
        (OUT / f'{k}.json').write_text(json.dumps(doc, separators=(',', ':')))
        written += 1
    last = max((max(ser) for k, ser in series.items() if ser and k in want), default=None)
    meta = {'updated': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'lastTradingDate': last,
            'companies': len(want), 'withPrices': written, 'withoutPrices': len(want) - written,
            'days': {ex: sorted(v) for ex, v in days_in.items()}, 'noFile': {ex: sorted(v) for ex, v in no_file.items()},
            'notes': NOTES[-20:], 'source': "NSE and BSE daily trading files, with Yahoo Finance (unofficial) for older NSE history"}
    meta_path.write_text(json.dumps(meta, separators=(',', ':')))
    print(json.dumps({k: v for k, v in meta.items() if k not in ('days', 'noFile')}))
    if written < len(series) * 0.5:
        sys.exit('Fewer than half the files could be written; not publishing this run.')


if __name__ == '__main__':
    main()
