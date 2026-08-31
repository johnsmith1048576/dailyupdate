#!/usr/bin/env python3
"""Stage 2 — Sweep.

For every live board in data/ats_hits.json, pulls the current postings and keeps
the London-eligible ones whose *title* is a Product Management role.

Only PM roles are collected — job descriptions are never fetched or scanned, so
each board is pulled with the smallest response its API offers.

Each kept role records its published date. Output: data/roles.json.
"""
import json, re, subprocess, html, sys, os
from datetime import datetime, timezone
import concurrent.futures as cf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
HITS = os.path.join(DATA, "ats_hits.json")
ROLES = os.path.join(DATA, "roles.json")

# --- classification vocabulary -------------------------------------------------
PMTITLE = re.compile(
    r"\bproduct manager\b|\bhead of product\b|\bproduct lead\b|\bdirector of product\b|"
    r"\bdirector,? product\b|\bvp,? product\b|\bvp of product\b|\bgroup product manager\b|"
    r"\bprincipal product manager\b|\bstaff product manager\b|\bsenior product manager\b|"
    r"\blead product manager\b|\btechnical product manager\b|\bproduct owner\b|"
    r"\bchief product officer\b|\bproduct management\b", re.I)
# titles that contain "product" but are NOT product management
NOTPM = re.compile(
    r"product (marketing|design|support|counsel|analyst|data scientist|ops)|"
    r"marketing manager|engineer\b|engineering", re.I)
UKRX = re.compile(r"\bunited kingdom\b|\bengland\b|\bU\.?K\.?\b", re.I)
REGION = re.compile(r"europe|emea|\buk\b|united kingdom|\bglobal\b|worldwide|international|anywhere|london", re.I)
USONLY = re.compile(r"us/canada|united states|u\.s\.|americas|north america|latam|apac|india only", re.I)

def loc_tag(txt, is_remote=False):
    """Return London / UK / Remote-EMEA, or None if not London-doable."""
    low = txt.lower()
    if "london" in low:
        return "London"
    if UKRX.search(txt):
        return "UK"
    if ("remote" in low or is_remote) and REGION.search(low):
        if USONLY.search(low) and not re.search(
                r"europe|emea|\buk\b|united kingdom|london|\bglobal\b|worldwide", low):
            return None
        return "Remote-EMEA"
    return None

def is_pm(title):
    """True when the job title itself is a Product Management role."""
    return bool(PMTITLE.search(title)) and not NOTPM.search(title)

def dt_iso(s):
    if not s:
        return ""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(s))
    return m.group(1) if m else ""

def dt_ms(ms):
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return ""

def curl(url):
    try:
        return subprocess.run(["curl", "-sS", "--max-time", "45", url],
                              capture_output=True, text=True, timeout=70).stdout
    except Exception:
        return ""

roles = []
def add(company, source, title, tag, loctext, url, comp="", posted=""):
    if not is_pm(title):
        return
    roles.append(dict(company=company, source=source, title=title.strip(), category="PM",
                      tag=tag, location=re.sub(r"\s+", " ", loctext).strip()[:80],
                      url=url, comp=comp, posted=posted))

# --- per-ATS pullers -----------------------------------------------------------
def do_ashby(slug):
    out = []
    try:
        d = json.loads(curl(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"))
    except Exception:
        return out
    for j in d.get("jobs", []):
        parts = [j.get("location", "") or ""] + [s.get("location", "") or "" for s in (j.get("secondaryLocations") or [])]
        txt = " | ".join(p for p in parts if p)
        tag = loc_tag(txt, j.get("isRemote"))
        if not tag:
            continue
        comp = (j.get("compensation") or {}).get("compensationTierSummary") or ""
        out.append((slug, "Ashby", j["title"], tag, txt, j.get("jobUrl", ""),
                    comp, dt_iso(j.get("publishedAt"))))
    return out

def do_greenhouse(slug):
    out = []
    try:
        d = json.loads(curl(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"))
    except Exception:
        return out
    for j in d.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "") or ""
        offices = " ".join(o.get("name", "") for o in (j.get("offices") or []))
        txt = (loc + " " + offices).strip()
        tag = loc_tag(txt)
        if not tag:
            continue
        posted = dt_iso(j.get("first_published")) or dt_iso(j.get("updated_at"))
        out.append((slug, "Greenhouse", j["title"], tag, txt, j.get("absolute_url", ""),
                    "", posted))
    return out

def do_lever(slug):
    out = []
    try:
        d = json.loads(curl(f"https://api.lever.co/v0/postings/{slug}?mode=json"))
    except Exception:
        return out
    if not isinstance(d, list):
        return out
    for j in d:
        cats = j.get("categories") or {}
        txt = " | ".join([cats.get("location", "") or ""] + (cats.get("allLocations") or []))
        tag = loc_tag(txt, (j.get("workplaceType", "") == "remote"))
        if not tag:
            continue
        out.append((slug, "Lever", j.get("text", ""), tag, txt, j.get("hostedUrl", ""),
                    "", dt_ms(j.get("createdAt"))))
    return out

def do_workable(slug):
    out = []
    try:
        d = json.loads(curl(f"https://apply.workable.com/api/v1/widget/accounts/{slug}?details=true"))
    except Exception:
        return out
    for j in (d.get("jobs") or []):
        txt = " ".join(x for x in [j.get("city", ""), j.get("state", ""), j.get("country", "")] if x)
        tag = loc_tag(txt, j.get("telecommuting"))
        if not tag:
            continue
        posted = dt_iso(j.get("published_on")) or dt_iso(j.get("created_at"))
        out.append((slug, "Workable", j.get("title", ""), tag, txt, j.get("url", ""),
                    "", posted))
    return out

PLAN = [("ashby", do_ashby), ("greenhouse", do_greenhouse), ("lever", do_lever), ("workable", do_workable)]

def main():
    hits = json.load(open(HITS))["hits"]
    for key, fn in PLAN:
        slugs = [s for s, _ in hits.get(key, [])]
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            for res in ex.map(fn, slugs):
                for r in res:
                    add(*r)
        print(f"after {key}: {len(roles)} roles", file=sys.stderr)

    # dedupe identical (company, title, url)
    seen, uniq = set(), []
    for r in roles:
        k = (r["company"], r["title"], r["url"])
        if k in seen:
            continue
        seen.add(k); uniq.append(r)
    json.dump(uniq, open(ROLES, "w"), indent=1)

    print(f"TOTAL {len(uniq)} PM roles | dated {sum(1 for r in uniq if r['posted'])} -> {ROLES}")

if __name__ == "__main__":
    main()
