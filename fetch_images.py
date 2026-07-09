#!/usr/bin/env python3
"""
fetch_images.py  -  Azur Lane tier list icon downloader

Run this inside your repo folder (the one that contains index.html).
It downloads ship icons from the Lycoris-AzurAPI dataset (weekly-refreshed
from AzurLaneTools/AzurLaneData) into an images/ folder next to index.html.
index.html then shows an icon next to each ship.

Ship IDs to fetch are read directly out of index.html's DATA block, so this
script stays in sync automatically as ships are added to the sheet.

For ships with no direct match (mostly Retrofit/META variants that share
their base ship's artwork), it falls back to the base ship's image.

Usage:
    python fetch_images.py

Requires: Python 3 (standard library only - no pip installs needed).
It is safe to re-run; already-downloaded icons are skipped.
"""

import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

SHIPS_JSON_URL = "https://raw.githubusercontent.com/iujab/Lycoris-AzurAPI/main/data/ships.json"
THUMB_URL = "https://raw.githubusercontent.com/iujab/azurlane-images/main/thumbnails/{gid}.png"

OUT_DIR = "images"

SUFFIX_PATTERNS = [
    r"\s*\(with .*?\)\s*$",
    r"\s*\(combo\)\s*$",
    r"\s*without .*$",
    r"\s*\(Retrofit\)\s*\(Main\)\s*$",
    r"\s*\(Retrofit\)\s*$",
    r"\s*META\s*$",
    r"\s*μ\s*$",
    r"-chan\s*$",
    r"\s*\(Main\)\s*$",
]


def base_name(name):
    x = name
    for pat in SUFFIX_PATTERNS:
        x = re.sub(pat, "", x)
    return x.strip()


def fetch(url, binary=False, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "azur-tier-list/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
                return data if binary else data.decode("utf-8")
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def load_ships_from_data(here):
    index_path = os.path.join(here, "index.html")
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
    os.makedirs(OUT_DIR, exist_ok=True)

    print("Reading ship list from index.html ...")
    data = load_ships_from_data(here)

    # gid -> ship name (first one wins), name -> gid (for base-name fallback lookup)
    gid_to_name = {}
    name_to_gid = {}
    for fleet, ships in data["ships"].items():
        for s in ships:
            if s.get("id") is None:
                continue
            gid = int(s["id"] // 10)
            gid_to_name.setdefault(gid, s["name"])
            name_to_gid.setdefault(s["name"], gid)

    gids = sorted(gid_to_name.keys())
    print("Ships needing icons: {}".format(len(gids)))

    print("Downloading Lycoris-AzurAPI ship dataset ...")
    try:
        ships = json.loads(fetch(SHIPS_JSON_URL))
    except Exception as e:
        print("ERROR: could not download ships.json:", e)
        print("Check your internet connection and try again.")
        sys.exit(1)

    available_gids = set(int(k) for k in ships.keys())

    total = len(gids)
    downloaded = 0
    skipped = 0
    fallback_used = 0
    missing = []
    failed = []

    print("Fetching {} ship icons ...".format(total))
    for i, gid in enumerate(gids, 1):
        out_path = os.path.join(OUT_DIR, "{}.png".format(gid))
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            skipped += 1
            continue

        source_gid = gid if gid in available_gids else None

        if source_gid is None:
            # Fall back to the base ship's gid (e.g. "X (Retrofit)" / "X META" -> "X")
            bname = base_name(gid_to_name[gid])
            candidate = name_to_gid.get(bname)
            if candidate is not None and candidate in available_gids:
                source_gid = candidate

        if source_gid is None:
            missing.append(gid)
            continue

        url = THUMB_URL.format(gid=source_gid)
        try:
            data_bytes = fetch(url, binary=True)
            with open(out_path, "wb") as f:
                f.write(data_bytes)
            downloaded += 1
            if source_gid != gid:
                fallback_used += 1
        except Exception as e:
            failed.append((gid, source_gid, str(e)))
        if i % 50 == 0 or i == total:
            print("  {}/{} processed (downloaded {}, skipped {})".format(i, total, downloaded, skipped))

    print()
    print("=" * 48)
    print("Done.")
    print("  Downloaded this run   : {}".format(downloaded))
    print("    (via base-ship fallback: {})".format(fallback_used))
    print("  Already had           : {}".format(skipped))
    print("  Not found (no icon)   : {}".format(len(missing)))
    print("  Failed downloads      : {}".format(len(failed)))
    if missing:
        print()
        print("Ships with no available icon (not in dataset, no fallback match):")
        print("  " + ", ".join("{}({})".format(g, gid_to_name[g]) for g in missing))
    if failed:
        print()
        print("Failed to download (network hiccups - just re-run the script):")
        for gid, source_gid, err in failed[:20]:
            print("  gid {} (source {}): {}".format(gid, source_gid, err))
    print("=" * 48)
    print("Now commit index.html and the images/ folder to your repo.")


if __name__ == "__main__":
    main()
