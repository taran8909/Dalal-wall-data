# dalal-wall-data

Public data for Dalal & Wall, a private claude.ai newspaper.

- `listed/companies.json`: every company listed on the NSE (main board and SME) and the BSE, merged by ISIN, as `[name, NSE symbol, BSE code]` rows. Built every Monday by the *Refresh the list of listed companies* GitHub Action (`listed/fetch_listed.py`) from the exchanges' own lists. Run it by hand from Actions → *Refresh the list of listed companies* → *Run workflow*.

The paper's update run copies the list into the page's company search each week.
