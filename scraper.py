#!/usr/bin/env python3
"""
4D Lottery Results Scraper — 4dmoon.com
Fetches DAMACAI, MAGNUM, and SPORTSTOTO results.

Usage:
  python scraper.py                    # most recent draw day
  python scraper.py --date 2026-05-13  # specific date
  python scraper.py --days 3           # last 3 draw days
  python scraper.py --json             # JSON output
"""

import re
import os
import sys
import json
import time
import argparse
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import requests

BASE_URL        = "https://www.4dmoon.com/past-results/{date}"
LATEST_URL      = "https://www.4dmoon.com"
DATE_RE         = re.compile(r'\b(\d{4}-\d{2}-\d{2})\b')

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.4dmoon.com/",
}

# Malaysian 4D draws on Wednesday=2, Saturday=5, Sunday=6
DRAW_DAYS = {2, 5, 6}

FOUR_DIGIT = re.compile(r'\b\d{4}\b')
DRAW_NUM = re.compile(r'#?(\d{3,6}/\d{2})')

LOTTERY_CONFIG = {
    "damacai": {
        "label": "DAMACAI",
        "keywords": ["damacai", "da ma cai", "1+3d"],
    },
    "magnum": {
        "label": "MAGNUM",
        "keywords": ["magnum"],
    },
    "toto": {
        "label": "SPORTSTOTO",
        "keywords": ["sportstoto", "sports toto", "sport toto"],
    },
}


def empty_result(label: str, date_str: str) -> dict:
    return {
        "label": label,
        "date": date_str,
        "draw_number": None,
        "prizes": {
            "1st": None,
            "2nd": None,
            "3rd": None,
            "special": [],
            "consolation": [],
        },
    }


def fetch_page(date_str: str | None) -> BeautifulSoup | None:
    url = LATEST_URL if date_str is None else BASE_URL.format(date=date_str)
    label = date_str or "latest"
    for attempt in range(1, 4):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.HTTPError as e:
            print(f"HTTP error for {label}: {e}", file=sys.stderr)
            break
        except requests.RequestException as e:
            print(f"Request failed for {label} (attempt {attempt}/3): {e}", file=sys.stderr)
            if attempt < 3:
                time.sleep(2)
    return None


def detect_date(soup: BeautifulSoup) -> str | None:
    """Extract the draw date from the page (used when no date is passed in the URL)."""
    # Try canonical URL or og:url meta tag first
    for meta in soup.find_all("meta"):
        content = meta.get("content", "") or ""
        m = DATE_RE.search(content)
        if m:
            return m.group(1)
    # Fall back to scanning visible text near draw headers
    for tag in soup.find_all(["h1", "h2", "h3", "title", "span", "div"]):
        m = DATE_RE.search(tag.get_text())
        if m:
            return m.group(1)
    return None



def _parse_rtb_table(tbl, target_name: str) -> tuple[str | None, dict]:
    """
    Parse one inner <table class="rtb"> that belongs to a known lottery.

    Returns (draw_number, prizes_dict).

    Page structure within each rtb table:
      Row 0 : [logo_img] [LotteryName\\n<span>DrawDate #DrawNum</span>]
      Row 1 : [1st Prize] [2nd Prize] [3rd Prize]   ← prize label row
      Row 2 : [1272]      [1956]      [1905]          ← prize number row
      Row 3 : [Special]   [n1] ... [n10]              ← 10 numbers same row
      Row 4 : [Consolation] [n1] ... [n10]
      (may also split across multiple rows for special/consolation)
    """
    prizes: dict = {"1st": None, "2nd": None, "3rd": None,
                    "special": [], "consolation": []}
    draw_number: str | None = None
    prize_col_order: list[str] = []
    awaiting_prize_numbers = False
    state: str | None = None  # 'special' or 'consolation'

    for row in tbl.find_all('tr'):
        # Only direct-child tds to avoid nested table contamination
        cells = [td.get_text(strip=True) for td in row.find_all('td', recursive=False)]
        if not cells:
            continue

        row_text = ' '.join(cells)
        row_lower = row_text.lower()

        # Header row: contains the lottery name and draw number
        if target_name.lower() in row_lower:
            m = DRAW_NUM.search(row_text)
            if m:
                draw_number = m.group(1)
            continue

        first_lower = cells[0].strip().lower()

        # Prize label row: "1st Prize", "2nd Prize", "3rd Prize"
        if '1st' in row_lower and '2nd' in row_lower:
            prize_col_order = []
            for cell in cells:
                cl = cell.lower()
                if '1st' in cl:
                    prize_col_order.append('1st')
                elif '2nd' in cl:
                    prize_col_order.append('2nd')
                elif '3rd' in cl:
                    prize_col_order.append('3rd')
            awaiting_prize_numbers = True
            state = None
            continue

        # Prize number row (immediately after label row)
        if awaiting_prize_numbers and prize_col_order:
            nums = FOUR_DIGIT.findall(row_text)
            for i, prize_key in enumerate(prize_col_order):
                if i < len(nums):
                    prizes[prize_key] = nums[i]
            awaiting_prize_numbers = False
            continue

        # Special section
        if first_lower.startswith('special'):
            state = 'special'
            nums = FOUR_DIGIT.findall(' '.join(cells[1:]) if len(cells) > 1 else '')
            prizes['special'].extend(nums[:10 - len(prizes['special'])])
            continue

        # Consolation section
        if 'consolation' in first_lower:
            state = 'consolation'
            nums = FOUR_DIGIT.findall(' '.join(cells[1:]) if len(cells) > 1 else '')
            prizes['consolation'].extend(nums[:10 - len(prizes['consolation'])])
            continue

        # Continuation rows for special/consolation (numbers only)
        if state in ('special', 'consolation'):
            nums = FOUR_DIGIT.findall(row_text)
            if nums:
                bucket = prizes[state]
                bucket.extend(nums[:10 - len(bucket)])

    return draw_number, prizes


def scrape_results(date_str: str | None) -> tuple[str | None, dict]:
    """
    Parse the 4dmoon.com page for the given date (or latest if date_str is None).
    Returns (resolved_date, results_dict).
    """
    soup = fetch_page(date_str)
    if soup is None:
        return date_str, {}

    if date_str is None:
        date_str = detect_date(soup)
        if date_str:
            print(f"Detected date from page: {date_str}", file=sys.stderr)
        else:
            print("Warning: could not detect date from latest page", file=sys.stderr)
            date_str = datetime.today().strftime("%Y-%m-%d")

    results = {
        key: empty_result(cfg["label"], date_str)
        for key, cfg in LOTTERY_CONFIG.items()
    }

    TARGETS = {
        "damacai": "Damacai 1+3D",
        "magnum": "Magnum 4D",
        "toto": "SportsToto 4D",
    }

    for key, target_name in TARGETS.items():
        for tbl in soup.find_all('table', class_='rtb'):
            header_text = tbl.get_text()
            # Exact-prefix match: target name must appear at start of section
            # (guards "Magnum 4D" from matching "Magnum 4D Jackpot Gold")
            tbl_lower = header_text.lower()
            t_lower = target_name.lower()
            idx = tbl_lower.find(t_lower)
            if idx == -1:
                continue
            # Character after the target name must not be a letter (space or digit or '(')
            after = tbl_lower[idx + len(t_lower): idx + len(t_lower) + 1]
            if after.isalpha():
                continue
            # Found the right table — parse it
            draw_number, prizes = _parse_rtb_table(tbl, target_name)
            results[key]['draw_number'] = draw_number
            results[key]['prizes'] = prizes
            break  # first match is the primary 4D section

    return date_str, results


def last_draw_dates(n: int) -> list[str]:
    """Return the last n draw dates (Wed/Sat/Sun) working backwards from today."""
    dates: list[str] = []
    day = datetime.today()
    while len(dates) < n:
        if day.weekday() in DRAW_DAYS:
            dates.append(day.strftime("%Y-%m-%d"))
        day -= timedelta(days=1)
    return dates


def all_draw_dates(from_str: str, to_str: str) -> list[str]:
    """Return all draw dates (Wed/Sat/Sun) in the inclusive range [from_str, to_str]."""
    start = datetime.strptime(from_str, "%Y-%m-%d")
    end   = datetime.strptime(to_str,   "%Y-%m-%d")
    dates: list[str] = []
    day = start
    while day <= end:
        if day.weekday() in DRAW_DAYS:
            dates.append(day.strftime("%Y-%m-%d"))
        day += timedelta(days=1)
    return dates


def format_results(results: dict, date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        header_date = dt.strftime("%a, %d %b %Y")
    except ValueError:
        header_date = date_str

    sep = "=" * 46
    lines = [sep, f"  4D Lottery Results - {header_date}", sep]

    for key in ("damacai", "magnum", "toto"):
        data = results.get(key)
        if not data:
            continue

        draw_no = data.get("draw_number")
        prizes = data.get("prizes", {})
        title = data["label"]
        if draw_no:
            title += f"  (#{draw_no})"

        lines.append(f"\n{title}")

        if not any([prizes.get("1st"), prizes.get("2nd"), prizes.get("3rd"),
                    prizes.get("special"), prizes.get("consolation")]):
            lines.append("  No results available.")
            continue

        def fmt(v):
            return v if v else "----"

        lines.append(f"  1st Prize   : {fmt(prizes.get('1st'))}")
        lines.append(f"  2nd Prize   : {fmt(prizes.get('2nd'))}")
        lines.append(f"  3rd Prize   : {fmt(prizes.get('3rd'))}")
        lines.append(f"  Special     : {' '.join(prizes.get('special', [])) or '----'}")
        lines.append(f"  Consolation : {' '.join(prizes.get('consolation', [])) or '----'}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Scrape 4D lottery results (DAMACAI / MAGNUM / SPORTSTOTO) from 4dmoon.com"
    )
    parser.add_argument(
        "--date",
        metavar="YYYY-MM-DD",
        help="Fetch results for this specific date (default: most recent draw day)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        metavar="N",
        help="Fetch results for the last N draw days (default: 1)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of formatted text",
    )
    parser.add_argument(
        "--save",
        metavar="FILE",
        help="Append results to a JSON file (skips dates already stored)",
    )
    parser.add_argument(
        "--from-date",
        metavar="YYYY-MM-DD",
        help="Fetch all draw dates from this date (use with --to-date; default end: today)",
    )
    parser.add_argument(
        "--to-date",
        metavar="YYYY-MM-DD",
        help="End date for --from-date range (default: today)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        metavar="SECONDS",
        help="Sleep between requests to avoid rate limiting (default: 1.0)",
    )
    args = parser.parse_args()

    # Load existing saved data to avoid re-fetching already-stored dates
    saved: dict[str, dict] = {}
    if args.save and os.path.exists(args.save):
        try:
            with open(args.save, encoding="utf-8") as f:
                saved = json.load(f)
        except (json.JSONDecodeError, OSError):
            saved = {}

    if args.from_date:
        to = args.to_date or datetime.today().strftime("%Y-%m-%d")
        dates: list[str | None] = all_draw_dates(args.from_date, to)
    elif args.date:
        dates = [args.date]
    elif args.days == 1:
        # Default: fetch latest page (no date in URL) so we always get published results
        dates = [None]
    else:
        dates = last_draw_dates(args.days)

    total = len(dates)
    all_results: dict[str, dict] = {}
    fetched = skipped = 0
    for i, date_str in enumerate(dates, 1):
        if date_str and args.save and date_str in saved:
            print(f"Skipping {date_str} ({i}/{total})", file=sys.stderr)
            all_results[date_str] = saved[date_str]
            skipped += 1
            continue
        label = date_str or "latest"
        print(f"Fetching {label} ({i}/{total})...", file=sys.stderr)
        resolved_date, result = scrape_results(date_str)
        if resolved_date:
            all_results[resolved_date] = result
            if args.save:
                saved[resolved_date] = result
                with open(args.save, "w", encoding="utf-8") as f:
                    json.dump(saved, f, indent=2, ensure_ascii=False)
        fetched += 1

        if i < total:
            time.sleep(args.delay)

    if total > 1:
        print(f"\nDone. {fetched} fetched, {skipped} skipped.", file=sys.stderr)

    if args.save and fetched > 0:
        print(f"Results saved to {args.save}", file=sys.stderr)

    if args.json:
        print(json.dumps(all_results, indent=2, ensure_ascii=False))
    else:
        for date_str, results in all_results.items():
            print(format_results(results, date_str))
            print()


if __name__ == "__main__":
    main()
