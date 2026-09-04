# Fix these two first

Both bugs are already in `09-known-bugs.md` as C1 and C2. This document is the plain version: what
is broken, what it looks like when it happens, and the exact change to make.

Nothing else in the project matters until these two are done. Together they are the reason a run
produces almost nothing.

Written 4 September 2026.

---

## Bug 1 — The model names are out of date

### What is broken

`roxi/llm.py` lists the names of the AI models the system calls. Two of them no longer exist:

```python
SONNET = "claude-sonnet-4-6"     # wrong
OPUS   = "claude-opus-4-8"       # wrong
```

The correct names are `claude-sonnet-5` and `claude-opus-5`. The third one, Haiku, is fine.

### What it looks like when it happens

The first two steps of the pipeline work, because they use Haiku. Everything after them fails,
because they use Sonnet.

So a run collects job postings, reads them, scores them — and then delivers zero leads. It looks
exactly like a scoring problem, or a quiet day with nothing worth sending. It is neither. The
research and email-writing steps are erroring out on every single lead.

### Where to change it

The wrong names appear in four places. All four need updating, or the ones you miss will quietly
override the ones you fixed.

**1. `roxi/llm.py`**

```python
SONNET = "claude-sonnet-5"
OPUS   = "claude-opus-5"
```

**2. `roxi/config.py`** — inside `ModelsConfig`:

```python
researcher: str = "claude-sonnet-5"
drafter: str = "claude-sonnet-5"
```

**3. `verticals/hauler_ai.yaml`** and **4. `verticals/hvac_trades.yaml`** — the `models:` section
at the bottom of each:

```yaml
models:
  extractor: claude-haiku-4-5-20251001
  scorer: claude-haiku-4-5-20251001
  researcher: claude-sonnet-5
  drafter: claude-sonnet-5
```

There is a fifth place worth doing at the same time: `roxi/agents/compiler.py` has the same wrong
names as defaults inside `_EmittedConfig`, which means every new industry the setup interview
creates will be born broken.

### Do this properly while you are in there

The reason this bug spread to five files is that the model names are written out by hand in each
one. Make the config and the YAML files read from the constants in `llm.py` instead, so there is
one place to change next time. Model names change every few months.

### How to check it worked

Run the pipeline against the test examples. If you get research briefs and draft emails instead of
warnings in the log, it worked.

---

## Bug 2 — The job collector returns one job instead of twenty

### What is broken

This is the more damaging of the two, because it is silent.

`roxi/collectors/job_boards.py` searches Indeed and finds up to twenty job listings. For each one it
opens the listing to read the full description. The problem is that it opens each listing **in the
same browser tab it used to hold the search results**.

Opening the first listing navigates away from the search page. The list of the other nineteen jobs
is destroyed the moment that happens. When the code loops round to job number two, it is holding a
reference to something that no longer exists.

That failure is caught by a catch-all that ignores errors and moves on. So it fails nineteen times
in silence and returns one job.

### What it looks like when it happens

Nothing. No error, no warning, no red anything. The run reports that it collected a small number of
items. It looks like a slow week on the job boards.

Every search term you have configured is returning roughly five percent of what it should. If you
have five search terms, you are seeing five job postings a day instead of a hundred.

This is the single biggest reason the system currently produces so few leads.

### The fix

Two changes to `_search_indeed`:

**First, read everything off the search page before opening anything.** Loop through the listings
and collect the title, company, and link into a plain list. Do not open any listing while you are
still reading the search results.

**Second, use a separate browser tab for the descriptions.** Open one extra tab, use it for every
detail page, and close it at the end. The search results tab is never navigated away from.

Roughly:

```python
def _search_indeed(page, browser, query):
    url = f"https://ca.indeed.com/jobs?q={query.replace(' ', '+')}&l=Canada"
    page.goto(url, wait_until="domcontentloaded", timeout=15000)

    # Step 1 — read the whole list first. No navigation in this loop.
    listings = []
    for card in page.query_selector_all("div.job_seen_beacon")[:20]:
        title_el = card.query_selector("h2.jobTitle")
        link_el = card.query_selector("h2.jobTitle a")
        company_el = card.query_selector("[data-testid='company-name']")
        if not title_el or not link_el:
            continue
        href = link_el.get_attribute("href") or ""
        listings.append({
            "title": title_el.inner_text().strip(),
            "company": company_el.inner_text().strip() if company_el else "",
            "url": f"https://ca.indeed.com{href}" if href.startswith("/") else href,
        })

    # Step 2 — open descriptions in a second tab, leaving the results page alone.
    detail_page = browser.new_page()
    items = []
    try:
        for listing in listings:
            body = _fetch_detail(detail_page, listing["url"])
            if listing["company"]:
                body = f"Company: {listing['company']}\n\n{body}"
            items.append(RawItem(
                channel="job_boards",
                source_url=listing["url"],
                fetched_at=datetime.now(tz=timezone.utc),
                title=listing["title"],
                body=body[:8000],
            ))
            time.sleep(3)
    finally:
        detail_page.close()

    return items
```

`fetch()` needs to pass `browser` through to `_search_indeed` so the second tab can be created.

### Stop swallowing errors while you are here

The current code has `except Exception: continue` with nothing inside it. That is what turned a
crash into silence. Log the error, even at debug level. A bug you can see is worth ten you cannot.

### Add an alarm for silence

A collector returning zero results looks identical to a genuinely quiet day. It almost never is —
it usually means the website changed and the reader broke.

Compare each run's count against the recent average and raise a warning when a source falls to
zero or drops sharply. The event system already exists for this; it just is not being used for it.

Without this alarm, the next time a website changes its layout you will find out weeks later.

### How to check it worked

Run one search term and count what comes back. If you get somewhere near twenty postings instead of
one, it worked. Read two or three of the descriptions to confirm they are complete rather than
truncated.

---

## After both are fixed

Do not start building anything new. Do this instead:

1. **Run the test examples** and see how the scoring performs against the fifty hand-marked ones.
   That has never been done, so nobody knows whether the scoring works at all.
2. **Run against real Indeed results for a week** and read every lead it produces.
3. **Send some emails and count the replies.**

That third step is the only thing that tells you whether any of this works. Everything else is
preparation for it.

The remaining twenty bugs in `09-known-bugs.md` are real, but none of them stop you finding out
whether people reply. These two do.

---

## Fixed — 4 September 2026

### Bug 1 — Model names

Updated in all five places:

- `roxi/llm.py`: `SONNET = "claude-sonnet-5"`, `OPUS = "claude-opus-5"`
- `roxi/config.py`: now imports `HAIKU` and `SONNET` from `roxi.llm` and uses the constants as
  `ModelsConfig` defaults — one place to change next time a model is retired
- `roxi/agents/compiler.py`: `_EmittedConfig` defaults changed from hardcoded strings to the
  imported `HAIKU`/`SONNET` constants, so new verticals created by the setup interview are born
  with the correct model names
- `verticals/hauler_ai.yaml` and `verticals/hvac_trades.yaml`: `researcher` and `drafter` updated
  to `claude-sonnet-5`

### Bug 2 — Job collector

The two-tab fix (separate `search_page` and `detail_page`, card metadata collected before any
navigation) was already in the code. Three additional things were done while in the file:

- **Error logging**: every `except Exception: continue` now logs the error — at `warning` level for
  failures that drop a whole job listing, at `debug` level for individual card-parse failures.
  Silent failures are gone.
- **Zero-result alarm**: after each query, if zero items came back, a `log.warning` fires naming
  the query and saying Indeed may have changed its layout or blocked the request. A quiet day and
  a broken scraper no longer look identical in the logs.
- **Per-query count**: a `log.info` line records how many items each query returned, so volume
  trends are visible without digging into the database.
