#!/usr/bin/env python3
"""
Run after each successful scrape to generate and store the top-250 predictions
for each lottery in Supabase (table: latest_predictions).

For each lottery we store TWO records:

* ``{lot_key}``         — "live" predictions built from ALL available draws.
                         Used by ``/predict`` to suggest bets for the next, still
                         unknown draw.
* ``{lot_key}_holdout`` — "holdout" predictions built from data with the most
                         recent draw EXCLUDED. ``based_on`` is the previous
                         draw date. These are compared against the latest draw
                         in the admin panel to give a true out-of-sample
                         match rate (no data leakage).

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


def _serialize(ranked):
    return [
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


def _upsert(row_id: str, payload: dict) -> str:
    if not (_SB_URL and _SB_KEY):
        return "skipped"
    r = _req.post(
        f"{_SB_URL}/rest/v1/latest_predictions",
        headers={**_sb_headers(), "Prefer": "resolution=merge-duplicates"},
        json={"id": row_id, "data": json.dumps(payload, ensure_ascii=False)},
        timeout=10,
    )
    return "OK" if r.status_code in (200, 201) else f"HTTP {r.status_code}"


def main():
    data = load_results()
    if not data:
        print("ERROR: No results data found")
        sys.exit(1)

    sorted_dates  = sorted(data.keys())
    last_draw     = sorted_dates[-1]
    prev_draw     = sorted_dates[-2] if len(sorted_dates) >= 2 else ""
    holdout_data  = {d: v for d, v in data.items() if d != last_draw}
    generated_at  = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    print(f"Generating top-{TOP_N} predictions")
    print(f"  live    based_on = {last_draw}  (all {len(data)} draws)")
    if prev_draw:
        print(f"  holdout based_on = {prev_draw}  ({len(holdout_data)} draws, latest excluded)")
    else:
        print("  holdout: skipped (need at least 2 draws)")

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

    top_picks = {}

    for lot_key, lot_val in LOTTERY_KEYS.items():
        # Live predictions — for users picking next-draw bets
        ranked_live = _boosted_ranked_scores(data, lot_val)
        top_picks[lot_key] = [r["num"] for r in ranked_live[:10]]
        payload_live = {
            "based_on":     last_draw,
            "generated_at": generated_at,
            "nums":         _serialize(ranked_live),
        }
        status_live = _upsert(lot_key, payload_live)
        print(f"  {lot_key:8s}: live    → {status_live}")

        # Holdout predictions — built without the latest draw, for honest validation
        if prev_draw and holdout_data:
            ranked_ho = _boosted_ranked_scores(holdout_data, lot_val)
            payload_ho = {
                "based_on":     prev_draw,
                "generated_at": generated_at,
                "nums":         _serialize(ranked_ho),
            }
            status_ho = _upsert(f"{lot_key}_holdout", payload_ho)
            print(f"  {lot_key:8s}: holdout → {status_ho}")

    # Write top-10 summary for Telegram notification
    try:
        with open("/tmp/predict_summary.txt", "w") as f:
            for key, nums in top_picks.items():
                f.write(f"{key}={' '.join(nums)}\n")
    except Exception as e:
        print(f"  Warning: could not write summary: {e}")

    print("Done.")


if __name__ == "__main__":
    main()
