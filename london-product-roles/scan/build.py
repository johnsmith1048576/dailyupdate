#!/usr/bin/env python3
"""Stage 3 — Render.

Turns data/roles.json into a self-contained, filterable HTML page at
output/index.html by injecting the role data into scan/template.html.

The page is Artifact-ready: publish output/index.html with the Artifact tool
(or open it directly in a browser).
"""
import json, os, csv
from datetime import date
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
ROLES = os.path.join(DATA, "roles.json")
HITS = os.path.join(DATA, "ats_hits.json")
SAVED = os.path.join(DATA, "saved.csv")   # durable, committed shortlist
TEMPLATE = os.path.join(ROOT, "scan", "template.html")
OUT = os.path.join(ROOT, "output", "index.html")

def load_saved_urls():
    urls = []
    if os.path.exists(SAVED):
        with open(SAVED, newline="") as f:
            for row in csv.DictReader(f):
                u = (row.get("url") or "").strip()
                if u:
                    urls.append(u)
    return urls

# Display-name overrides for slugs whose casing can't be inferred.
DISP = {
    'openai': 'OpenAI', 'elevenlabs': 'ElevenLabs', 'gitlab': 'GitLab', 'n8n': 'n8n',
    'truelayer': 'TrueLayer', 'commercetools': 'commercetools', 'gopuff': 'Gopuff',
    'dbt': 'dbt', 'blockchain': 'Blockchain.com', 'bloomreach': 'Bloomreach',
    'typeform': 'Typeform', 'algolia': 'Algolia', 'speechmatics': 'Speechmatics',
    'fireblocks': 'Fireblocks', 'datadog': 'Datadog', 'adyen': 'Adyen', 'airbnb': 'Airbnb',
    'affirm': 'Affirm', 'robinhood': 'Robinhood', 'stripe': 'Stripe', 'intercom': 'Intercom',
    'monzo': 'Monzo', 'deliveroo': 'Deliveroo', 'lendable': 'Lendable', 'lovable': 'Lovable',
    'pleo': 'Pleo', 'decagon': 'Decagon', 'sierra': 'Sierra', 'synthesia': 'Synthesia',
    'wayve': 'Wayve', 'zego': 'Zego', 'yapily': 'Yapily', 'persona': 'Persona',
    'multiverse': 'Multiverse', 'heygen': 'HeyGen', 'coreweave': 'CoreWeave',
    'launchdarkly': 'LaunchDarkly', 'cresta': 'Cresta', 'justworks': 'Justworks',
    'cerebras': 'Cerebras', 'cartesia': 'Cartesia',
}

def disp(c):
    if c in DISP:
        return DISP[c]
    if any(ch.isupper() for ch in c):
        return c
    return c[:1].upper() + c[1:]

def main():
    roles = json.load(open(ROLES))

    # dedupe by (company, title), keeping the best location tag
    rank = {"London": 0, "UK": 1, "Remote-EMEA": 2}
    best = {}
    for r in roles:
        k = (r["company"], r["title"])
        if k not in best or rank[r["tag"]] < rank[best[k]["tag"]]:
            best[k] = r
    roles = list(best.values())
    for r in roles:
        r["companyName"] = disp(r["company"])

    groups = defaultdict(list)
    for r in roles:
        groups[r["companyName"]].append(r)

    def pm_ct(rs):
        return sum(1 for x in rs if x["category"] == "PM")

    comps = []
    for name, rs in groups.items():
        rs.sort(key=lambda x: (x.get("posted") or "0000-00-00"), reverse=True)  # newest first
        comps.append({"name": name, "source": rs[0]["source"], "roles": rs,
                      "pm": pm_ct(rs), "helpful": len(rs) - pm_ct(rs), "total": len(rs)})
    comps.sort(key=lambda c: (-c["pm"], -c["total"], c["name"]))

    total = len(roles)
    pm = sum(c["pm"] for c in comps)
    data = {"companies": comps,
            "stats": {"companies": len(comps), "total": total, "pm": pm, "helpful": total - pm},
            "saved": load_saved_urls()}

    meta = json.load(open(HITS)).get("meta", {}) if os.path.exists(HITS) else {}
    swept = date.today().strftime("%-d %b %Y") if hasattr(date, "strftime") else date.today().isoformat()
    boards = str(meta.get("boards", "—"))
    probed = str(meta.get("probed", "—"))

    html = open(TEMPLATE).read()
    html = (html
            .replace("__PAYLOAD__", json.dumps(data, ensure_ascii=False))
            .replace("__SWEPT__", swept)
            .replace("__BOARDS__", boards)
            .replace("__PROBED__", probed))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write(html)
    live_saved = sum(1 for c in comps for r in c["roles"] if r["url"] in set(data["saved"]))
    print(f"wrote {OUT} — {total} roles ({pm} PM / {total - pm} helpful), {len(comps)} companies; "
          f"{len(data['saved'])} saved in CSV ({live_saved} still live)")

if __name__ == "__main__":
    main()
