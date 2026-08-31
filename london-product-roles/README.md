# London Product Roles — ATS scanner

A small, reproducible pipeline that finds **London (or London-remote) product-management
roles** across four public ATS job-board APIs, then renders them as a filterable,
self-contained web page.

Only roles whose **job title** is Product Management are kept (Product Manager, Head/Director
of Product, Product Owner, VP Product …); product marketing, design, support and analyst
titles are excluded. Descriptions are never fetched or scanned. Every role is dated so you
can see how stale a posting is at a glance.

The most recent rendered snapshot lives at [`output/index.html`](output/index.html);
publish it as an Artifact or open it in any browser.

## How it works

Three stages, each a plain Python script (stdlib + `curl` only):

| Stage | Script | Reads | Writes |
|------|--------|-------|--------|
| 1. Discover | `scan/probe.py` | `companies.txt` | `data/ats_hits.json` |
| 2. Sweep | `scan/sweep.py` | `data/ats_hits.json` | `data/roles.json` |
| 3. Render | `scan/build.py` | `data/roles.json` + `scan/template.html` | `output/index.html` (+ `data/history.json`) |

- **Discover** turns each name in `companies.txt` into candidate slugs and tries them
  against all four ATS APIs, keeping any board that returns live jobs. Slugs found on
  earlier runs are retained, so coverage only grows.
- **Sweep** pulls current postings from every live board and keeps the London-eligible ones
  whose title is a PM role. Location tags: **London**, **UK**, **Remote-EMEA** (fully remote,
  open to UK/Europe).
- **Render** dedupes, groups by company, sorts newest-first, and injects the data into the
  HTML template. It also maintains **`data/history.json`** — a durable archive of every role URL
  ever seen — and computes the **posting-cadence** chart from it (see below), so the chart is
  regenerated automatically on every run with no extra step.

### Posting-cadence chart

The page has an expandable **Posting cadence** panel: a stacked bar chart of roles by the month
their posting went up, for the current year. Each bar splits **live** PM roles (green) from
**expired** ones (pale green) — URLs that appeared in an earlier sweep but are no longer live.
`build.py` derives this from `data/history.json`:

- every currently-live role is upserted into the archive (keyed by URL) on each run;
- any archived URL not in the current sweep counts as *expired*;
- the counts are bucketed by posting month and injected into the template as `__CHART__`.

`data/history.json` is committed, so the expired history survives across refreshes and machines —
without it, "expired" can't be known (a sweep only ever sees what's *currently* live). The current
month's bar is partial (through today) and marked with a dashed cap.

## Run it

```bash
cd london-product-roles
./run.sh            # auto: sweep + render; discovery only if the board list is stale (>7d)
./run.sh all        # force a full discovery pass first
./run.sh sweep      # never discover; reuse the known board list (fastest)
```

`auto` is the efficient default: discovery is ~3,000 requests but the set of companies using
these ATSs barely moves, so it re-runs only when `data/ats_hits.json` is older than
`DISCOVERY_MAX_AGE_DAYS` (default 7).

## Automated daily refresh (no Claude required)

`.github/workflows/refresh-roles.yml` runs the whole pipeline on GitHub's runners at **06:00 UTC
daily** and commits any changed `data/` + `output/index.html` back to the repo. The pipeline is
plain Python 3 (stdlib) + `curl`, so this costs nothing beyond Actions minutes. You can also run
it on demand from the Actions tab (**Run workflow**), optionally forcing full discovery. Each run
also uploads the rendered page as a downloadable artifact.

> Scheduled workflows only fire from the repository's **default branch** — which this branch
> currently is.

Or stage by stage:

```bash
python3 scan/probe.py     # -> data/ats_hits.json
python3 scan/sweep.py     # -> data/roles.json
python3 scan/build.py     # -> output/index.html
```

### Requirements
- Python 3 (standard library only — no `pip install`).
- `curl` on PATH.
- Outbound HTTPS to the four API hosts:
  `api.ashbyhq.com`, `boards-api.greenhouse.io`, `api.lever.co`, `apply.workable.com`.
  Behind a proxy, `curl` inherits the usual `HTTPS_PROXY` / CA environment, so no extra
  config is needed. If a host is blocked by a network policy, that ATS is simply skipped.

## Marking roles: save · applied · dismiss

Each role row carries three one-click markers, plus matching filters:

- **Star (★)** — save a role; the **★ Saved** filter shows only your marks.
- **Tick (✓)** — mark a role as *applied*; the row shows an "Applied" badge and the **✓ Applied**
  filter narrows to those.
- **Dismiss (✕)** — hide a role from every view, so the location / freshness filters stay
  free of roles you've already ruled out. The **✕ Dismissed** filter lists what you've hidden so
  you can restore any of them (the button flips to ↺).

All three live in the browser's `localStorage` (keyed by posting URL), so they persist across
refreshes in that browser. Stars can additionally be made durable via `data/saved.csv`
(below); applied/dismissed marks are browser-only for now.

**Filtering & sorting.** Freshness is **multi-select** — pick any combination of Fresh / Aging /
Stale to widen the results. **Sort** switches between the default *by company* grouping and a flat
list ordered by publish date (*Newest first* / *Oldest first*), which shows each role's company
inline.

### Saving roles (durable shortlist)

Stars live in the browser's `localStorage` too — instant, but per-browser and wiped if you clear
browsing data.

For a **permanent** shortlist, the source of truth is [`data/saved.csv`](data/saved.csv),
committed to the repo. `build.py` bakes it into every render, so saved roles show up
**pre-starred on every refresh** regardless of browser state. Three ways to write
to it:

```bash
python3 scan/save.py add    "deliveroo payments"      # match by title/company text…
python3 scan/save.py add    "https://jobs.ashbyhq…"   # …or by exact posting URL
python3 scan/save.py remove "payments"
python3 scan/save.py list                             # shows shortlist + which are still live
python3 scan/save.py import saved-roles.csv           # merge a browser "Export CSV"
```

Round-trip from the page: click **Export CSV** to download your current stars, then
`scan/save.py import <that file>` folds them into `data/saved.csv` permanently. Each of
`add` / `remove` / `import` rebuilds the page automatically.

> A published Artifact is a static page with no backend, so it can't write files itself —
> `data/saved.csv` is the durable store, written from the CLI or via Export → import.

## Keeping it fresh

The daily GitHub Actions workflow above does this for you. To run it elsewhere, the pipeline is
stateless and idempotent — just run `./run.sh` on a timer (e.g. `0 6 * * * cd /path/to/london-product-roles && ./run.sh >> run.log 2>&1`).

**Publishing to a Claude Artifact** is the one step a scheduler can't do: an Artifact is written
by the Artifact tool from a Claude session, and a published page can't fetch job boards itself
(its sandbox blocks outbound requests), so it can't self-refresh from a button. Options: open
`output/index.html` from the repo after a workflow run, or have a scheduled Claude session
republish the page to the same Artifact URL.

## Extending

- **More companies**: add names to `companies.txt` (one per line). They're slugified and
  tried automatically on the next discovery run.
- **Another ATS**: add an endpoint in `scan/probe.py` (`EP` + `njobs`) and a puller in
  `scan/sweep.py` (`do_*` + the `PLAN` list).
- **Classification tuning**: the title / location / product-signal regexes live at the top
  of `scan/sweep.py`.
- **Design**: edit `scan/template.html` (placeholders: `__PAYLOAD__`, `__SWEPT__`,
  `__BOARDS__`, `__PROBED__`).

## Caveats

- A snapshot in time — listings change daily; always confirm on the employer's own posting.
- Coverage is limited to companies in `companies.txt` whose slug is name-guessable.
  Workable slugs in particular often aren't, so its coverage is thin.
- Some ATS hosts may be blocked by a given network policy; those are skipped, not errored.
