#!/usr/bin/env python3
"""
4D Lottery Number Checker — Flask web app.
Reads lot_results.json and lets users check a 4-digit number for prizes.
"""

import json
import math
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta
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
DRAW_DAYS = {2, 5, 6}  # Wednesday, Saturday, Sunday


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


def compute_extended_stats(data: dict, lottery: str | None = None) -> dict:
    today = datetime.today().date()
    tiers = ["1st", "2nd", "3rd"]
    keys = [lottery] if lottery else LOTTERY_ORDER

    pos_freq = [{str(d): 0 for d in range(10)} for _ in range(4)]
    sum_dist = Counter()
    balance  = Counter()
    patterns = Counter()
    quads    = set()
    last_seen: dict[str, str] = {}   # number → most recent date string

    for date_str in sorted(data.keys()):
        day = data[date_str]
        for key in keys:
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


def next_draw_date() -> str:
    day = datetime.today() + timedelta(days=1)
    for _ in range(7):
        if day.weekday() in DRAW_DAYS:
            return day.strftime("%a, %d %b %Y")
        day += timedelta(days=1)
    return ""


def build_prediction_model(data: dict, lottery: str | None = None) -> dict:
    tiers = ["1st", "2nd", "3rd"]
    pos_counts = [{str(d): 0 for d in range(10)} for _ in range(4)]
    hist_counts: Counter = Counter()
    appearances: dict = defaultdict(list)
    keys = [lottery] if lottery else LOTTERY_ORDER

    for date_str in sorted(data.keys()):
        day = data[date_str]
        for key in keys:
            lot = day.get(key)
            if not lot:
                continue
            prizes = lot.get("prizes", {})
            for t in tiers:
                num = prizes.get(t)
                if num and len(num) == 4 and num.isdigit():
                    hist_counts[num] += 1
                    appearances[num].append(date_str)
                    for i, d in enumerate(num):
                        pos_counts[i][d] += 1

    pos_totals = [sum(pc.values()) for pc in pos_counts]
    pos_probs = [
        {d: (pos_counts[i][d] / pos_totals[i] if pos_totals[i] else 0.1)
         for d in "0123456789"}
        for i in range(4)
    ]

    today = datetime.today().date()
    last_seen: dict = {}
    avg_gap: dict = {}
    for num, dates in appearances.items():
        last_seen[num] = dates[-1]
        if len(dates) > 1:
            dts = [datetime.strptime(d, "%Y-%m-%d").date() for d in dates]
            gaps = [(dts[j + 1] - dts[j]).days for j in range(len(dts) - 1)]
            avg_gap[num] = sum(gaps) / len(gaps)

    total_days = (today - datetime.strptime(min(data.keys()), "%Y-%m-%d").date()).days
    global_avg_gap = total_days / max(len(hist_counts), 1)

    return {
        "pos_probs": pos_probs,
        "hist_counts": hist_counts,
        "hist_max": max(hist_counts.values()) if hist_counts else 1,
        "last_seen": last_seen,
        "avg_gap": avg_gap,
        "global_avg_gap": global_avg_gap,
        "today": today,
    }


def _colour(score_pct: float) -> tuple[str, str]:
    if score_pct >= 70:  return ("#f5c518", "Very High")
    if score_pct >= 50:  return ("#22c55e", "High")
    if score_pct >= 35:  return ("#06b6d4", "Above Average")
    if score_pct >= 20:  return ("#f59e0b", "Average")
    if score_pct >= 10:  return ("#f97316", "Below Average")
    return ("#64748b", "Low")


def score_number(num: str, model: dict) -> dict:
    pos_prob = 1.0
    for i, d in enumerate(num):
        pos_prob *= model["pos_probs"][i].get(d, 0.001)
    pos_norm = min(pos_prob / (0.1 ** 4), 2.5) / 2.5

    count = model["hist_counts"].get(num, 0)
    hist_norm = count / model["hist_max"]

    today = model["today"]
    if num in model["last_seen"]:
        last = datetime.strptime(model["last_seen"][num], "%Y-%m-%d").date()
        days = (today - last).days
        recency_norm = math.exp(-days / 365)
        last_seen_fmt = last.strftime("%d %b %Y")
    else:
        recency_norm = 0.05
        last_seen_fmt = "Never"
        days = None

    if num in model["avg_gap"] and model["avg_gap"][num]:
        days_since = (today - datetime.strptime(model["last_seen"][num], "%Y-%m-%d").date()).days
        gap_norm = min(days_since / model["avg_gap"][num], 3.0) / 3.0
    elif num in model["last_seen"]:
        days_since = (today - datetime.strptime(model["last_seen"][num], "%Y-%m-%d").date()).days
        gap_norm = min(days_since / model["global_avg_gap"], 3.0) / 3.0
    else:
        gap_norm = 0.4

    composite = 0.15 * pos_norm + 0.60 * hist_norm + 0.15 * recency_norm + 0.10 * gap_norm

    return {
        "num": num,
        "composite": round(composite, 6),
        "pos_norm": round(pos_norm * 100, 1),
        "hist_norm": round(hist_norm * 100, 1),
        "recency_norm": round(recency_norm * 100, 1),
        "gap_norm": round(gap_norm * 100, 1),
        "count": count,
        "last_seen_fmt": last_seen_fmt,
    }


def get_ranked_scores(model: dict) -> list[dict]:
    results = []
    for n in range(10000):
        num = f"{n:04d}"
        s = score_number(num, model)
        results.append(s)
    results.sort(key=lambda x: x["composite"], reverse=True)
    total = len(results)
    top_composite = results[0]["composite"] if results else 1
    for rank, r in enumerate(results, 1):
        percentile = round((1 - rank / total) * 100, 1)
        score_pct = round(r["composite"] / top_composite * 100, 1)
        colour, label = _colour(score_pct)
        r["rank"] = rank
        r["percentile"] = percentile
        r["score_pct"] = score_pct
        r["colour"] = colour
        r["label"] = label
    return results


LOTTERY_KEYS = {"all": None, "damacai": "damacai", "magnum": "magnum", "toto": "toto"}


@app.route("/predict")
def predict():
    data = load_results()
    top20s = {}
    for key, lot in LOTTERY_KEYS.items():
        model = build_prediction_model(data, lot)
        top20s[key] = get_ranked_scores(model)[:20]
    return render_template("predict.html", top20s=top20s, total_dates=len(data),
                           next_draw=next_draw_date(), active_page="predict")


@app.route("/api/score")
def api_score():
    number = request.args.get("number", "").strip()
    lottery = request.args.get("lottery", "all").strip()
    if not number.isdigit() or len(number) != 4:
        return jsonify({"error": "Enter a valid 4-digit number"}), 400
    if lottery not in LOTTERY_KEYS:
        lottery = "all"
    data = load_results()
    model = build_prediction_model(data, LOTTERY_KEYS[lottery])
    ranked = get_ranked_scores(model)
    rank_map = {r["num"]: r for r in ranked}
    return jsonify(rank_map[number])


@app.route("/analysis")
def analysis():
    data = load_results()
    stats, counts = compute_stats(data)
    exts = {k: compute_extended_stats(data, v) for k, v in LOTTERY_KEYS.items()}
    return render_template("analysis.html", stats=stats, counts=counts,
                           exts=exts, total_dates=len(data), active_page="analysis")


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


@app.route("/simulate")
def simulate():
    return render_template("simulate.html", active_page="simulate",
                           next_draw=next_draw_date())




if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
