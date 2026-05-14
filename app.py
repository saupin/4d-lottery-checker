#!/usr/bin/env python3
"""
4D Lottery Number Checker — Flask web app.
Reads lot_results.json and lets users check a 4-digit number for prizes.
"""

import json
import os
from collections import Counter
from datetime import datetime
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

RESULTS_FILE = os.path.join(os.path.dirname(__file__), "lot_results.json")

PRIZE_ORDER = ["1st", "2nd", "3rd", "special", "consolation"]
PRIZE_LABEL = {
    "1st": "1st Prize",
    "2nd": "2nd Prize",
    "3rd": "3rd Prize",
    "special": "Special",
    "consolation": "Consolation",
}
LOTTERY_ORDER = ["damacai", "magnum", "toto"]


def load_results() -> dict:
    if not os.path.exists(RESULTS_FILE):
        return {}
    with open(RESULTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def search_number(number: str, data: dict) -> list[dict]:
    matches = []
    for date_str in sorted(data.keys(), reverse=True):
        day = data[date_str]
        for key in LOTTERY_ORDER:
            lottery = day.get(key)
            if not lottery:
                continue
            prizes = lottery.get("prizes", {})
            for tier in PRIZE_ORDER:
                val = prizes.get(tier)
                hit = (val == number) if isinstance(val, str) else (number in (val or []))
                if hit:
                    matches.append({
                        "date": date_str,
                        "date_fmt": datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %d %b %Y"),
                        "lottery": lottery.get("label", key.upper()),
                        "draw_number": lottery.get("draw_number", ""),
                        "prize": PRIZE_LABEL[tier],
                        "tier": tier,
                    })
    return matches


def latest_draws(data: dict, n: int = 3) -> list[dict]:
    rows = []
    for date_str in sorted(data.keys(), reverse=True)[:n]:
        day = data[date_str]
        entry = {"date": date_str,
                 "date_fmt": datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %d %b %Y"),
                 "lotteries": []}
        for key in LOTTERY_ORDER:
            lot = day.get(key)
            if lot:
                entry["lotteries"].append({
                    "label": lot.get("label", key.upper()),
                    "draw_number": lot.get("draw_number", ""),
                    "prizes": lot.get("prizes", {}),
                })
        rows.append(entry)
    return rows


def compute_stats(data: dict, top: int = 20) -> tuple[dict, dict]:
    tiers = ["1st", "2nd", "3rd"]
    overall = {t: Counter() for t in tiers}
    by_lot  = {key: {t: Counter() for t in tiers} for key in LOTTERY_ORDER}

    for day in data.values():
        for key in LOTTERY_ORDER:
            lot = day.get(key)
            if not lot:
                continue
            prizes = lot.get("prizes", {})
            for t in tiers:
                val = prizes.get(t)
                if val:
                    overall[t][val] += 1
                    by_lot[key][t][val] += 1

    def top_n(counter):
        return counter.most_common(top)

    stats = {
        "all":     {t: top_n(overall[t])           for t in tiers},
        "damacai": {t: top_n(by_lot["damacai"][t]) for t in tiers},
        "magnum":  {t: top_n(by_lot["magnum"][t])  for t in tiers},
        "toto":    {t: top_n(by_lot["toto"][t])    for t in tiers},
    }
    counts = {t: sum(overall[t].values()) for t in tiers}
    return stats, counts


@app.route("/")
def index():
    data = load_results()
    recent = latest_draws(data)
    total_dates = len(data)
    return render_template("index.html", recent=recent, total_dates=total_dates, active_page="results")


def compute_extended_stats(data: dict) -> dict:
    today = datetime.today().date()
    tiers = ["1st", "2nd", "3rd"]

    pos_freq = [{str(d): 0 for d in range(10)} for _ in range(4)]
    sum_dist = Counter()
    balance  = Counter()
    patterns = Counter()
    quads    = set()
    last_seen: dict[str, str] = {}   # number → most recent date string

    for date_str in sorted(data.keys()):
        day = data[date_str]
        for key in LOTTERY_ORDER:
            lot = day.get(key)
            if not lot:
                continue
            prizes = lot.get("prizes", {})
            for t in tiers:
                num = prizes.get(t)
                if not num or len(num) != 4 or not num.isdigit():
                    continue
                # Position frequency
                for i, d in enumerate(num):
                    pos_freq[i][d] += 1
                # Digit sum
                sum_dist[sum(int(d) for d in num)] += 1
                # Even/odd balance
                balance[sum(1 for d in num if int(d) % 2 == 0)] += 1
                # Repeat pattern
                unique = len(set(num))
                if unique == 4:
                    pat = "All Different"
                elif unique == 3:
                    pat = "One Pair"
                elif unique == 2:
                    pat = "Two Pairs" if max(Counter(num).values()) == 2 else "Three of a Kind"
                else:
                    pat = "Four of a Kind"
                    quads.add(num)
                patterns[pat] += 1
                # Hot / cold tracking
                last_seen[num] = date_str

    total = sum(sum_dist.values())

    # Normalise position freq to sorted list of (digit, count, pct)
    pos_freq_out = []
    for pos in range(4):
        pos_total = sum(pos_freq[pos].values())
        sorted_digits = sorted(pos_freq[pos].items(), key=lambda x: -x[1])
        pos_freq_out.append([
            {"digit": d, "count": c, "pct": round(c / pos_total * 100, 1) if pos_total else 0}
            for d, c in sorted_digits
        ])

    # Hot & Cold — compute days_ago from last_seen date
    hot = sorted(last_seen, key=last_seen.get, reverse=True)[:10]
    cold = sorted(last_seen, key=last_seen.get)[:10]
    def enrich(nums):
        out = []
        for n in nums:
            ds = last_seen[n]
            d = datetime.strptime(ds, "%Y-%m-%d").date()
            out.append({"num": n, "date": datetime.strptime(ds, "%Y-%m-%d").strftime("%d %b %Y"),
                        "days_ago": (today - d).days})
        return out

    # Digit sum: sorted list of [sum_val, count]
    sum_list = [[s, sum_dist[s]] for s in range(37)]
    sum_peak = max(sum_dist, key=sum_dist.get) if sum_dist else 18
    sum_max  = max(sum_dist.values()) if sum_dist else 1

    # Pattern breakdown with percentage
    pattern_order = ["All Different", "One Pair", "Two Pairs", "Three of a Kind", "Four of a Kind"]
    pattern_list = [(p, patterns[p], round(patterns[p] / total * 100, 1) if total else 0)
                    for p in pattern_order if p in patterns]

    # Balance labels
    balance_labels = {0: "All Odd", 1: "1 Even", 2: "2 Even", 3: "3 Even", 4: "All Even"}
    balance_list = [(balance_labels[k], balance[k], round(balance[k] / total * 100, 1) if total else 0)
                    for k in range(5)]

    return {
        "pos_freq":   pos_freq_out,
        "pos_total":  total,
        "hot":        enrich(hot),
        "cold":       enrich(cold),
        "sum_list":   sum_list,
        "sum_peak":   sum_peak,
        "sum_max":    sum_max,
        "balance":    balance_list,
        "patterns":   pattern_list,
        "quads":      sorted(quads),
        "total":      total,
    }


@app.route("/analysis")
def analysis():
    data = load_results()
    stats, counts = compute_stats(data)
    ext = compute_extended_stats(data)
    return render_template("analysis.html", stats=stats, counts=counts,
                           ext=ext, total_dates=len(data), active_page="analysis")


@app.route("/search")
def search():
    number = request.args.get("number", "").strip()
    if not number.isdigit() or len(number) != 4:
        return jsonify({"error": "Please enter a valid 4-digit number (0000–9999)."}), 400
    data = load_results()
    matches = search_number(number, data)
    return jsonify({
        "number": number,
        "matches": matches,
        "total_draws": len(data),
    })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
