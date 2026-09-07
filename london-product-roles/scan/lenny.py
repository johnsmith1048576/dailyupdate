#!/usr/bin/env python3
"""Stage 0 (weekly) — sync the Lenny 100 company list into companies.txt.

Fetches https://www.lennysjobs.com/lenny100, extracts the company names, and
appends any that companies.txt doesn't already cover. Records the roster in
data/lenny100.json so additions and removals show up in git history.

Only ever ADDS to companies.txt — names are never removed, matching the rest of
the pipeline (coverage only grows). If the page can't be fetched or the parse
looks implausible, it prints a warning, changes nothing and exits 0, so a layout
change upstream can never break the nightly run or corrupt the company list.

  python3 scan/lenny.py            # sync
  python3 scan/lenny.py --dump     # diagnostics only, writes nothing
"""
import json, os, re, subprocess, sys, html
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPANIES = os.path.join(ROOT, "companies.txt")
ROSTER = os.path.join(ROOT, "data", "lenny100.json")
URL = "https://www.lennysjobs.com/lenny100"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# A parse is only trusted inside this band — "Lenny 100" should yield ~100 names.
MIN_EXPECTED, MAX_EXPECTED = 40, 300

# Words that signal navigation/boilerplate rather than a company name.
STOP = {
    "home","about","contact","jobs","job","careers","career","blog","newsletter","podcast",
    "sign in","sign up","log in","login","subscribe","search","menu","apply","apply now",
    "companies","company","the lenny 100","lenny 100","lennys jobs","lenny's jobs","lennysjobs",
    "privacy","terms","faq","all","more","view all","learn more","read more","next","previous",
    "products","pricing","resources","community","events","teams","people","hiring","remote",
    "full time","part time","engineering","design","marketing","sales","product","operations",
    "twitter","linkedin","facebook","instagram","youtube","github","rss","email",
}

def fetch(url):
    try:
        r = subprocess.run(["curl", "-sS", "-L", "--max-time", "45", "-A", UA, url],
                           capture_output=True, text=True, timeout=70)
        return r.stdout or ""
    except Exception as e:
        print(f"lenny: fetch failed ({e})", file=sys.stderr)
        return ""

def clean(name):
    n = html.unescape(str(name)).strip()
    n = re.sub(r"\s+", " ", n)
    n = re.sub(r"^[\d]{1,3}[.)\-–—\s]+", "", n)          # strip list numbering "12. Figma"
    n = n.strip(" \t​·|—–-")
    return n

def plausible(name):
    if not (2 <= len(name) <= 40):
        return False
    if name.lower() in STOP:
        return False
    if not re.search(r"[A-Za-z]", name):
        return False
    if re.search(r"[<>{}\[\]|]|https?://|@|\.com\b", name):
        return False
    if len(name.split()) > 4:                             # company names are short
        return False
    if re.search(r"\b(we|you|your|our|the best|apply|hiring|read|learn)\b", name, re.I):
        return False
    return True

def walk_json(node, out):
    """Collect values of name-ish keys from arbitrarily nested JSON."""
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str) and k.lower() in {"company", "companyname", "name", "title", "employer"}:
                out.append(v)
            else:
                walk_json(v, out)
    elif isinstance(node, list):
        for v in node:
            walk_json(v, out)

def strategy_embedded_json(doc):
    """__NEXT_DATA__ / application/json / ld+json blobs."""
    found = []
    for m in re.finditer(r'<script[^>]*type="application/(?:ld\+)?json"[^>]*>(.*?)</script>', doc, re.S):
        try:
            walk_json(json.loads(m.group(1)), found)
        except Exception:
            pass
    m = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', doc, re.S)
    if m:
        try:
            walk_json(json.loads(m.group(1)), found)
        except Exception:
            pass
    return found

def strategy_anchors(doc):
    """Visible link text — most listings link each company out."""
    return [re.sub(r"<[^>]+>", " ", m.group(1)) for m in
            re.finditer(r"<a\b[^>]*>(.*?)</a>", doc, re.S)]

def strategy_headings(doc):
    return [re.sub(r"<[^>]+>", " ", m.group(1)) for m in
            re.finditer(r"<h[2-5]\b[^>]*>(.*?)</h[2-5]>", doc, re.S)]

def extract(doc):
    """Return (names, strategy_name) for the first strategy that looks sane."""
    for label, fn in (("embedded-json", strategy_embedded_json),
                      ("anchors", strategy_anchors),
                      ("headings", strategy_headings)):
        seen, names = set(), []
        for raw in fn(doc):
            n = clean(raw)
            if plausible(n) and n.lower() not in seen:
                seen.add(n.lower()); names.append(n)
        print(f"lenny: strategy {label:14} -> {len(names)} candidate names", file=sys.stderr)
        if MIN_EXPECTED <= len(names) <= MAX_EXPECTED:
            return names, label
    return [], None

def load_companies():
    lines = open(COMPANIES).read().splitlines()
    header = [l for l in lines if l.startswith("#")]
    names = [l.strip() for l in lines if l.strip() and not l.startswith("#")]
    return header, names

def slug(n):
    return re.sub(r"[^a-z0-9]", "", n.lower())

def main():
    dump = "--dump" in sys.argv
    doc = fetch(URL)
    if not doc:
        print("lenny: could not fetch the Lenny 100 page — leaving companies.txt untouched")
        return 0
    print(f"lenny: fetched {len(doc)} bytes", file=sys.stderr)
    names, how = extract(doc)

    if dump:
        t = re.search(r"<title>(.*?)</title>", doc, re.S)
        print("TITLE:", clean(t.group(1)) if t else "(none)")
        print("HAS __NEXT_DATA__:", "__NEXT_DATA__" in doc)
        print(f"CHOSEN STRATEGY: {how}  ({len(names)} names)")
        print("SAMPLE:", ", ".join(names[:40]) or "(none)")
        return 0

    if not names:
        print("lenny: no plausible company list found (page layout may have changed) — "
              "companies.txt left untouched")
        return 0

    header, existing = load_companies()
    have = {n.lower() for n in existing} | {slug(n) for n in existing}
    added = []
    for n in names:
        if n.lower() in have or slug(n) in have:
            continue
        have.add(n.lower()); have.add(slug(n)); added.append(n)

    if added:
        allnames = sorted(existing + added, key=str.lower)
        open(COMPANIES, "w").write("\n".join(header + allnames) + "\n")

    os.makedirs(os.path.dirname(ROSTER), exist_ok=True)
    prev = []
    if os.path.exists(ROSTER):
        try:
            prev = json.load(open(ROSTER)).get("companies", [])
        except Exception:
            prev = []
    gone = [n for n in prev if n.lower() not in {x.lower() for x in names}]
    json.dump({"source": URL, "checked": date.today().isoformat(),
               "count": len(names), "strategy": how,
               "companies": sorted(names, key=str.lower)},
              open(ROSTER, "w"), indent=1)

    print(f"lenny: {len(names)} companies on the list (via {how}); "
          f"{len(added)} new -> companies.txt")
    if added:
        print("       added: " + ", ".join(added))
    if gone:
        print("       no longer on the list (kept in companies.txt): " + ", ".join(gone))
    return 0

if __name__ == "__main__":
    sys.exit(main())
