#!/usr/bin/env python3
"""Stage 1 — Discovery.

Reads companies.txt, slugifies each name, and tries every slug against the four
public ATS job-board APIs. Any board that returns live jobs is recorded.

Retains slugs discovered on previous runs (from data/ats_hits.json) so the known
set only grows. Output: data/ats_hits.json.

Only Python stdlib + curl are required. curl inherits the environment's proxy /
CA settings, so it works behind an outbound HTTPS proxy without extra config.
"""
import json, re, subprocess, sys, os
import concurrent.futures as cf
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
os.makedirs(DATA, exist_ok=True)
HITS = os.path.join(DATA, "ats_hits.json")
COMPANIES = os.path.join(ROOT, "companies.txt")

# ATS endpoints. Add a new one here + a counter in `njobs` to extend coverage.
EP = {
    "ashby":      lambda s: f"https://api.ashbyhq.com/posting-api/job-board/{s}",
    "greenhouse": lambda s: f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs",
    "lever":      lambda s: f"https://api.lever.co/v0/postings/{s}?mode=json",
    "workable":   lambda s: f"https://apply.workable.com/api/v1/widget/accounts/{s}?details=true",
}

def slugs_for(name):
    """company name -> candidate ATS slugs (alnum and hyphenated variants)."""
    low = name.lower()
    out = set()
    a = re.sub(r"[^a-z0-9]", "", low)
    h = re.sub(r"[^a-z0-9]+", "-", low).strip("-")
    if a:
        out.add(a)
    if h and h != a:
        out.add(h)
    return out

def njobs(ats, body):
    try:
        d = json.loads(body)
    except Exception:
        return None
    if ats == "lever":
        return len(d) if isinstance(d, list) else None
    # Ashby / Greenhouse / Workable all expose a `jobs` array.
    # NOTE: Workable's widget returns HTTP 200 and echoes the slug back even for
    # accounts that don't exist, so only a non-empty jobs array counts as a hit.
    return len((d or {}).get("jobs") or [])

def probe(task):
    ats, slug = task
    try:
        r = subprocess.run(
            ["curl", "-sS", "--max-time", "20", "-w", "\n%{http_code}", EP[ats](slug)],
            capture_output=True, text=True, timeout=30)
        out = r.stdout
        nl = out.rfind("\n")
        code, body = out[nl + 1:].strip(), out[:nl]
        if code != "200":
            return (ats, slug, None)
        return (ats, slug, njobs(ats, body))
    except Exception:
        return (ats, slug, None)

def load_companies():
    names = []
    with open(COMPANIES) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                names.append(line)
    return names

def main():
    names = load_companies()
    cands = set()
    # keep slugs already known to resolve, so the set only grows
    if os.path.exists(HITS):
        prev = json.load(open(HITS)).get("hits", {})
        for ats in prev:
            for slug, _ in prev[ats]:
                cands.add(slug)
    for n in names:
        cands |= slugs_for(n)
    cands = {c for c in cands if 2 <= len(c) <= 40}

    tasks = [(ats, s) for ats in EP for s in sorted(cands)]
    print(f"probing {len(cands)} slugs x {len(EP)} ATS = {len(tasks)} requests", file=sys.stderr)

    hits = {k: [] for k in EP}
    empty = {k: [] for k in EP}
    with cf.ThreadPoolExecutor(max_workers=24) as ex:
        for ats, slug, n in ex.map(probe, tasks):
            if n and n > 0:
                hits[ats].append((slug, n))
            elif n == 0:
                empty[ats].append(slug)
    for ats in hits:
        hits[ats].sort(key=lambda x: -x[1])

    boards = sum(len(v) for v in hits.values())
    out = {
        "meta": {"generated": date.today().isoformat(), "probed": len(names), "boards": boards},
        "hits": hits, "empty": empty,
    }
    json.dump(out, open(HITS, "w"), indent=1)
    for ats in hits:
        print(f"{ats:11}: {len(hits[ats])} live boards")
    print(f"total: {boards} live boards -> {HITS}", file=sys.stderr)

if __name__ == "__main__":
    main()
