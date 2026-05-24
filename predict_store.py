#!/usr/bin/env python3
"""
Run after each successful scrape to generate and store the top-250 predictions
for each lottery in Supabase (table: latest_predictions).

Usage:
    python predict_store.py

Requires env vars: SUPABASE_URL, SUPABASE_KEY
"""
import json
import os
import sys
from datetime import datetime

# Allow importing app.py from the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Provide a dummy SECRET_KEY so Flask initialises without error
if not os.environ.get("SECRET_KEY"):
    os.environ["SECRET_KEY"] = "predict-store-dummy"

from app import (
    _boosted_ranked_scores,
    load_results,
    LOTTERY_KEYS,
    _SB_URL,
    _SB_KEY,
    _sb_headers,
)
import requests as _req

TOP_N = 250


def main():
    data = load_results()
    if not data:
        print("ERROR: No results data found")
        sys.exit(1)

    last_draw    = max(data.keys())
    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    print(f"Generating top-{TOP_N} predictions based on draw: {last_draw}")

    # Backup current predictions before overwriting
    if _SB_URL and _SB_KEY:
        try:
            r = _req.get(f"{_SB_URL}/rest/v1/latest_predictions?select=id,data",
                         headers={**_sb_headers(), "apikey": _SB_KEY}, timeout=5)
            for row in r.json():
                _req.post(f"{_SB_URL}/rest/v1/previous_predictions",
                          headers={**_sb_headers(), "apikey": _SB_KEY,
                                   "Prefer": "resolution=merge-duplicates"},
                          json={"id": row["id"], "data": row["data"]}, timeout=10)
            print("  Backed up previous predictions")
        except Exception as e:
            print(f"  Warning: backup failed: {e}")

    for lot_key, lot_val in LOTTERY_KEYS.items():
        ranked = _boosted_ranked_scores(data, lot_val)
        nums = [
            {
                "num":           r["num"],
                "rank":          r.get("rank", 0),
                "score_pct":     r.get("score_pct", 0),
                "percentile":    r.get("percentile", 0),
                "colour":        r.get("colour", "#888"),
                "label":         r.get("label", ""),
                "count":         r.get("count", 0),
                "last_seen_fmt": r.get("last_seen_fmt", "Never"),
            }
            for r in ranked[:TOP_N]
        ]
        payload = {
            "based_on":     last_draw,
            "generated_at": generated_at,
            "nums":         nums,
        }

        if _SB_URL and _SB_KEY:
            r = _req.post(
                f"{_SB_URL}/rest/v1/latest_predictions",
                headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates"},
                json={"id": lot_key, "data": json.dumps(payload, ensure_ascii=False)},
                timeout=10,
            )
            status = "OK" if r.status_code in (200, 201) else f"HTTP {r.status_code}"
            print(f"  {lot_key:8s}: {len(nums)} numbers → Supabase {status}")
        else:
            print(f"  {lot_key:8s}: Supabase not configured, skipping")

    print("Done.")


if __name__ == "__main__":
    main()
