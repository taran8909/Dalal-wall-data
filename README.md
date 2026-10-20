# dalal-wall-data

Public data for Dalal & Wall, a private claude.ai newspaper.

- `listed/companies.json`: every company listed on the NSE (main board and SME) and the BSE, merged by ISIN, as `[name, NSE symbol, BSE code]` rows. Built every Monday by the *Refresh the list of listed companies* GitHub Action (`listed/fetch_listed.py`) from the exchanges' own lists. Run it by hand from Actions → *Refresh the list of listed companies* → *Run workflow*.

- `prices` branch, `p/<KEY>.json`: two years of daily closes for every company in that list, from Yahoo Finance (unofficial), rebuilt every weekday after the close by *Refresh prices for all listed companies* (`prices/fetch_prices.py`). KEY is the NSE symbol (`&` as `_`), or `BSE` plus the scrip code for BSE-only companies. The branch is replaced on each run, so the repository doesn't grow.

The paper's update run copies the list into the page's company search each week, and copies the price files of the reader's companies into the page.
