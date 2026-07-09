#!/usr/bin/env python3
"""
sync_sheet.py  -  Azur Lane tier list sheet sync

Pulls ship ratings/notes from the "Master Main", "Master VG", and
"Master Subs" tabs of the public Google Sheet and rewrites the
`ships` section of index.html's DATA block to match.

Everything else in DATA (fleets, contentLabels, hullNames, tierOrder)
is left untouched - only the per-fleet ship lists are regenerated.

Usage:
    python sync_sheet.py

Requires: Python 3 (standard library only - no pip installs needed).
"""

import csv
import io
import json
import os
import sys
import time
import urllib.request

SHEET_ID = "13YbPw3dM2eN6hr3YfVABIK9LVuCWnVZF0Zp2BGOZXc0"
CSV_URL = "https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"

# fleet key -> gid of that fleet's "Master ..." data tab in the sheet
FLEET_TABS = {
    "main": 1378196099,   # Master Main
    "vg": 2033513712,     # Master VG
    "subs": 501493009,    # Master Subs
}


def fetch_csv(gid, retries=3):
    url = CSV_URL.format(sheet_id=SHEET_ID, gid=gid)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "azur-tier-list/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read().decode("utf-8")
            return list(csv.reader(io.StringIO(raw)))
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def parse_fleet(rows, contents, hull_order):
    header_idx = next(i for i, r in enumerate(rows) if r and r[0].strip() == "id")
    header = [h.strip() for h in rows[header_idx]]
    col = {name: header.index(name) for name in ("id", "Hull", "Name", "Notes")}
    tier_cols = {label: header.index(label) for label in contents}

    ships = []
    for r in rows[header_idx + 1:]:
        if len(r) <= col["Name"]:
            continue
        name = r[col["Name"]].strip()
        if not name:
            continue
        notes = r[col["Notes"]].strip()
        hull = r[col["Hull"]].strip()
        id_str = r[col["id"]].strip()
        ships.append({
            "id": float(int(id_str)) if id_str else None,
            "hull": hull,
            "name": name,
            "notes": notes if notes else None,
            "tiers": {label: r[c].strip() for label, c in tier_cols.items()},
            "hullRank": hull_order.index(hull) if hull in hull_order else 999,
        })
    return ships


def load_current_data(index_path):
    with open(index_path, encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith("const DATA"):
                raw = line.strip()[len("const DATA = "):].rstrip(";")
                return json.loads(raw)
    raise RuntimeError("Could not find 'const DATA = ' line in index.html")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    here = os.path.dirname(os.path.abspath(__file__))
    os.chdir(here)
    index_path = os.path.join(here, "index.html")

    print("Reading current DATA from index.html ...")
    data = load_current_data(index_path)

    for fleet_key, gid in FLEET_TABS.items():
        print("Fetching '{}' tab ...".format(fleet_key))
        rows = fetch_csv(gid)
        contents = data["fleets"][fleet_key]["contents"]
        hull_order = data["fleets"][fleet_key]["hull_order"]
        ships = parse_fleet(rows, contents, hull_order)
        print("  {} ships parsed".format(len(ships)))
        data["ships"][fleet_key] = ships

    new_line = "const DATA = " + json.dumps(data, ensure_ascii=False) + ";"

    with open(index_path, encoding="utf-8") as f:
        lines = f.readlines()

    for i, line in enumerate(lines):
        if line.strip().startswith("const DATA"):
            changed = line.rstrip("\n") != new_line
            lines[i] = new_line + "\n"
            break
    else:
        raise RuntimeError("Could not find 'const DATA = ' line in index.html")

    if not changed:
        print("No changes - index.html already matches the sheet.")
        return

    with open(index_path, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(lines)
    print("index.html updated.")


if __name__ == "__main__":
    main()
