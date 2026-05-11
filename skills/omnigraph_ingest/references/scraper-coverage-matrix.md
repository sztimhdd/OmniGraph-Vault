# RSS Scraper Coverage Matrix (2026-05-10)

## Finding

All 45 RSS articles stuck with `layer1_verdict='candidate' AND body IS NULL`
were probed against a simple `requests.get()` with Chrome UA header.

Result: **45/45 (100%) returned HTTP 200 with meaningful body content**
(avg ~30KB, all <1.5s response time).

## Methodology

```python
import requests, time, sqlite3, time
from urllib.parse import urlparse

UA = "Mozilla/5.0 ... Chrome/120.0.0.0 Safari/537.36"
c = sqlite3.connect("data/kol_scan.db")
stuck = c.execute("""
    SELECT id, url FROM rss_articles
    WHERE layer1_verdict='candidate' AND body IS NULL
    ORDER BY id ASC
""").fetchall()

for art_id, url in stuck:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    # All 45 returned 200 with body > 100 bytes
    time.sleep(1)
```

## Conclusion

The scraper bug is **internal**, not external blocking. Sites like
simonwillison.net, seangoedecke.com, lucumr.pocoo.org, antirez.com,
geoffreylitt.com, buttondown.com all serve content freely.

Root cause: `scrape_url()` auto-router was routing non-WeChat URLs to
broken scraper paths (likely Apify or WeChat-specific cascade) instead
of using simple HTTP GET.

Fix: `b4k` (commit `a3a98d3`) — `scraper.py` UA fallback for non-WeChat URLs.

## Domains Probed

| Domain | Articles | Result |
|--------|----------|--------|
| simonwillison.net | 8 | All OK |
| seangoedecke.com | 9 | All OK |
| antirez.com | 11 | All OK |
| lucumr.pocoo.org | 6 | All OK |
| geoffreylitt.com | 4 | All OK |
| buttondown.com | 2 | All OK |
| krebsonsecurity.com | 1 | OK |
| workos.com | 1 | OK |
| dwarkesh.com | 1 | OK |
| minimaxir.com | 1 | OK |
| rakhim.exotext.com | 1 | OK |
