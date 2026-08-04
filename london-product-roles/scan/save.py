#!/usr/bin/env python3
"""Manage the durable shortlist in data/saved.csv.

The published web page can't write files (it's a static Artifact), so this is how
saved roles become permanent: they live in data/saved.csv, which build.py bakes
into every render as pre-starred rows. Survives browser-data clears.

Usage:
  python3 scan/save.py add    <url | text match>   add a role to the shortlist
  python3 scan/save.py remove <url | text match>   drop it
  python3 scan/save.py list                         show the shortlist (+ live?)
  python3 scan/save.py import  <exported.csv>       merge a browser "Export CSV"

Matching by text looks at title + company in data/roles.json; it must resolve to
exactly one role (otherwise it lists the candidates so you can be specific).
`add`/`remove`/`import` rebuild the page automatically.
"""
import csv, json, os, sys, subprocess
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SAVED = os.path.join(DATA, "saved.csv")
ROLES = os.path.join(DATA, "roles.json")
FIELDS = ["url", "title", "company", "saved_at"]

def load_roles():
    return json.load(open(ROLES)) if os.path.exists(ROLES) else []

def read_saved():
    if not os.path.exists(SAVED):
        return []
    with open(SAVED, newline="") as f:
        return [r for r in csv.DictReader(f)]

def write_saved(rows):
    with open(SAVED, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})

def resolve(query, roles):
    """Return a single role dict matching query (url exact/substring, else text)."""
    ql = query.lower()
    exact = [r for r in roles if r["url"] == query]
    if exact:
        return exact[0], []
    subs = [r for r in roles if ql in r["url"].lower()]
    if len(subs) == 1:
        return subs[0], []
    toks = ql.split()
    text = [r for r in roles
            if all(t in (r["title"] + " " + r.get("companyName", r["company"])).lower() for t in toks)]
    cands = subs or text
    if len(cands) == 1:
        return cands[0], []
    return None, cands

def rebuild():
    subprocess.run([sys.executable, os.path.join(ROOT, "scan", "build.py")], check=True)

def cmd_add(query):
    roles = load_roles()
    role, cands = resolve(query, roles)
    if not role:
        if cands:
            print(f"'{query}' is ambiguous ({len(cands)} matches) — be more specific:")
            for r in cands[:12]:
                print(f"   - {r['title']} · {r['company']} · {r['url']}")
        else:
            print(f"No role matches '{query}'. Pass a posting URL or a distinctive title.")
        return 1
    rows = read_saved()
    if any(r["url"] == role["url"] for r in rows):
        print(f"Already saved: {role['title']} · {role['company']}")
        return 0
    rows.append({"url": role["url"], "title": role["title"],
                 "company": role.get("company", ""), "saved_at": date.today().isoformat()})
    write_saved(rows)
    print(f"Saved: {role['title']} · {role['company']}  ({len(rows)} on shortlist)")
    rebuild()
    return 0

def cmd_remove(query):
    rows = read_saved()
    ql = query.lower(); toks = ql.split()
    def match(r):
        hay = (r["url"] + " " + r["title"] + " " + r["company"]).lower()
        return ql in r["url"].lower() or all(t in hay for t in toks)
    keep = [r for r in rows if not match(r)]
    if len(keep) == len(rows):
        print(f"Nothing on the shortlist matches '{query}'.")
        return 1
    write_saved(keep)
    print(f"Removed {len(rows) - len(keep)} — {len(keep)} remain.")
    rebuild()
    return 0

def cmd_list():
    rows = read_saved()
    if not rows:
        print("Shortlist is empty.")
        return 0
    live = {r["url"] for r in load_roles()}
    print(f"{len(rows)} saved role(s):")
    for r in rows:
        flag = "" if r["url"] in live else "  (no longer listed)"
        print(f"   - {r['title']} · {r['company']} · saved {r.get('saved_at','?')}{flag}")
    return 0

def cmd_import(path):
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return 1
    rows = read_saved()
    have = {r["url"] for r in rows}
    added = 0
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            u = (r.get("url") or "").strip()
            if u and u not in have:
                rows.append({"url": u, "title": r.get("title", ""), "company": r.get("company", ""),
                             "saved_at": date.today().isoformat()})
                have.add(u); added += 1
    write_saved(rows)
    print(f"Imported {added} new role(s) — {len(rows)} on shortlist.")
    rebuild()
    return 0

def main(argv):
    if len(argv) < 2 or argv[1] not in {"add", "remove", "list", "import"}:
        print(__doc__)
        return 2
    cmd = argv[1]
    if cmd == "list":
        return cmd_list()
    if len(argv) < 3:
        print(f"'{cmd}' needs an argument. See --help.")
        return 2
    arg = " ".join(argv[2:])
    return {"add": cmd_add, "remove": cmd_remove, "import": cmd_import}[cmd](arg)

if __name__ == "__main__":
    sys.exit(main(sys.argv))
