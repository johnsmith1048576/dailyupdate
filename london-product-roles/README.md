# London Product Roles — ATS scanner

A small, reproducible pipeline that finds **London (or London-remote) product-management
roles** — and non-PM roles where product experience is explicitly valued — across four
public ATS job-board APIs, then renders them as a filterable, self-contained web page.

Every role is tagged **PM role** or **PM helpful**, and dated so you can see how stale a
posting is at a glance.

The most recent rendered snapshot lives at [`output/index.html`](output/index.html);
publish it as an Artifact or open it in any browser.

## How it works

Three stages, each a plain Python script (stdlib + `curl` only):

| Stage | Script | Reads | Writes |
|------|--------|-------|--------|
| 1. Discover | `scan/probe.py` | `companies.txt` | `data/ats_hits.json` |
| 2. Sweep & classify | `scan/sweep.py` | `data/ats_hits.json` | `data/roles.json` |
| 3. Render | `scan/build.py` | `data/roles.json` + `scan/template.html` | `output/index.html` |

- **Discover** turns each name in `companies.txt` into candidate slugs and tries them
  against all four ATS APIs, keeping any board that returns live jobs. Slugs found on
  earlier runs are retained, so coverage only grows.
- **Sweep** pulls current postings from every live board, keeps London-eligible ones, and
  classifies each:
  - **PM role** — the title itself is Product Management (Product Manager, Head/Director of
    Product, Product Owner, …).
  - **PM helpful** — not a PM title, but the description asks for *product sense / judgment /
    instinct* (candidate-facing phrasing; simple negations like "does not require product
    management experience" are excluded). The matching sentence is quoted on the page.
  - Location tags: **London**, **UK**, **Remote-EMEA** (fully remote, open to UK/Europe).
- **Render** dedupes, groups by company, sorts newest-first, and injects the data into the
  HTML template.

## Run it

```bash
cd london-product-roles
./run.sh            # all three stages (~a few minutes; discovery is the slow part)
./run.sh sweep      # skip discovery, reuse the known board list (fast refresh)
```

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

## Saving roles (durable shortlist)

The rendered page lets you **star** roles; those marks live in the browser's
`localStorage` — instant, but per-browser and wiped if you clear browsing data.

For a **permanent** shortlist, the source of truth is [`data/saved.csv`](data/saved.csv),
committed to the repo. `build.py` bakes it into every render, so saved roles show up
**pre-starred on every weekly refresh** regardless of browser state. Three ways to write
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

## Scheduling (for later)

The pipeline is stateless and idempotent — just run `./run.sh` on a timer.

- **cron** (weekly, Mondays 07:00):
  ```cron
  0 7 * * 1  cd /path/to/london-product-roles && ./run.sh >> run.log 2>&1
  ```
- **GitHub Actions**: a `schedule:` workflow that runs `./run.sh` and commits
  `output/index.html` + `data/*.json` back to the repo.
- **Claude Code Routine**: a scheduled trigger that re-runs the sweep and republishes the
  Artifact to the same URL.

A full discovery pass is only worth running occasionally (to catch companies newly adopting
these ATSs). For routine freshness, `./run.sh sweep` is enough and much faster.

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
