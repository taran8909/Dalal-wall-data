"""Every company listed on the NSE (main board and SME) and the BSE, merged by ISIN.

Writes listed/companies.json: {"updated", "count", "sources", "rows": [[name, nse_symbol, bse_code], ...]}.
Dalal & Wall copies it into its search box each week. If one exchange can't be reached,
that exchange's rows from the previous file are kept.
"""
import csv, io, json, datetime, pathlib, sys, time
import requests

OUT = pathlib.Path(__file__).with_name('companies.json')
UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36', 'Accept': '*/*', 'Accept-Language': 'en-GB,en;q=0.9'}
NSE = ['https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv', 'https://archives.nseindia.com/content/equities/EQUITY_L.csv']
NSE_SME = ['https://nsearchives.nseindia.com/emerge/corporates/content/SME_EQUITY_L.csv', 'https://archives.nseindia.com/emerge/corporates/content/SME_EQUITY_L.csv']
BSE = 'https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scripcode=&industry=&segment=Equity&status=Active'


def get(url, **kw):
    for attempt in range(3):
        try:
            r = requests.get(url, headers={**UA, **kw.pop('headers', {})}, timeout=60, **kw)
            if r.ok and r.content:
                return r
            print(f'{url}: HTTP {r.status_code}')
        except Exception as e:
            print(f'{url}: {e}')
        time.sleep(3 * (attempt + 1))
    return None


def nse_rows(urls):
    for u in urls:
        r = get(u)
        if r:
            rows = list(csv.DictReader(io.StringIO(r.content.decode('utf-8-sig'))))
            rows = [{k.strip(): (v or '').strip() for k, v in x.items() if k} for x in rows]
            out = [{'isin': x.get('ISIN NUMBER', ''), 'name': x.get('NAME OF COMPANY', ''), 'nse': x.get('SYMBOL', '')} for x in rows if x.get('SYMBOL')]
            print(f'{u}: {len(out)} rows')
            return out
    return None


def bse_rows():
    r = get(BSE, headers={'Referer': 'https://www.bseindia.com/', 'Origin': 'https://www.bseindia.com'})
    if not r:
        return None
    try:
        data = r.json()
    except ValueError:
        print('BSE: not JSON'); return None
    out = [{'isin': (x.get('ISIN_NUMBER') or '').strip(), 'name': (x.get('Issuer_Name') or x.get('Scrip_Name') or '').strip(), 'bse': str(x.get('SCRIP_CD') or '').strip()} for x in data if x.get('SCRIP_CD')]
    print(f'BSE: {len(out)} rows')
    return out or None


def main():
    prev = json.loads(OUT.read_text()) if OUT.exists() else {'rows': []}
    nse = nse_rows(NSE)
    sme = nse_rows(NSE_SME)
    bse = bse_rows()
    if not nse and not bse:
        sys.exit('Neither exchange could be reached; keeping the previous list.')
    by_key = {}
    def put(isin, name, nse_sym='', bse_code=''):
        k = isin or ('NSE:' + nse_sym if nse_sym else 'BSE:' + bse_code)
        row = by_key.setdefault(k, {'name': '', 'nse': '', 'bse': ''})
        if name and (not row['name'] or nse_sym):
            row['name'] = name  # NSE's company names are the cleanest
        row['nse'] = row['nse'] or nse_sym
        row['bse'] = row['bse'] or bse_code
    # Keep the previous rows of an exchange that couldn't be reached this time.
    if not nse or not bse:
        for name, s, c in prev.get('rows', []):
            if (s and not nse) or (c and not bse):
                put('', name, s if not nse else '', c if not bse else '')
    for x in (nse or []) + (sme or []):
        put(x['isin'], x['name'], nse_sym=x['nse'])
    for x in bse or []:
        put(x['isin'], x['name'], bse_code=x['bse'])
    rows = sorted(([r['name'], r['nse'], r['bse']] for r in by_key.values() if r['name']), key=lambda r: r[0].lower())
    OUT.write_text(json.dumps({'updated': datetime.date.today().isoformat(), 'count': len(rows),
                               'sources': {'nse': bool(nse), 'nse_sme': bool(sme), 'bse': bool(bse)}, 'rows': rows},
                              ensure_ascii=False, separators=(',', ':')))
    print(f'{len(rows)} companies written')


if __name__ == '__main__':
    main()
