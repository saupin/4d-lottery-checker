"""
Triggered when claude.yml fails.
1. Creates a GitHub issue so Claude auto-investigates and fixes the CI problem.
2. Skips creation if an open [CI] issue already exists (prevents loops).
3. Sends a Telegram alert with links to both the failed run and the fix issue.
"""
import json
import os
import urllib.request
import urllib.error

e   = os.environ
GH  = e["GITHUB_TOKEN"]
REPO = e["GITHUB_REPOSITORY"]
RUN_URL  = e.get("RUN_URL", "")
RUN_ID   = e.get("RUN_ID", "")
BRANCH   = e.get("HEAD_BRANCH", "unknown")

HEADERS_GH = {
    "Authorization": f"Bearer {GH}",
    "Accept": "application/vnd.github+json",
    "Content-Type": "application/json",
}


def gh_get(url):
    req = urllib.request.Request(url, headers=HEADERS_GH)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def gh_post(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=HEADERS_GH)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


# ── 1. Check for existing open [CI] issue to avoid duplicate loops ────────────
search = gh_get(
    f"https://api.github.com/search/issues"
    f"?q=repo:{REPO}+is:issue+is:open+%5BCI%5D+in:title&per_page=5"
)
existing = [i for i in search.get("items", []) if i["title"].startswith("[CI]")]

if existing:
    issue_url = existing[0]["html_url"]
    issue_num = existing[0]["number"]
    print(f"Open CI issue already exists: #{issue_num} — skipping creation.")
else:
    # ── 2. Create fix issue ───────────────────────────────────────────────────
    title = f"[CI] Claude workflow failed — run #{RUN_ID}"
    body = (
        f"The **Claude Code** workflow failed on run [{RUN_ID}]({RUN_URL}).\n\n"
        f"**Branch:** `{BRANCH}`\n"
        f"**Failed run:** {RUN_URL}\n\n"
        f"Please inspect the failure log at the link above, identify the root cause "
        f"(authentication, missing secret, broken script, etc.) and apply the fix to "
        f"the relevant file under `.github/`. Then close this issue."
    )
    issue = gh_post(f"https://api.github.com/repos/{REPO}/issues",
                    {"title": title, "body": body, "labels": ["ci-autofix"]})
    issue_url = issue["html_url"]
    issue_num = issue["number"]
    print(f"Created fix issue: #{issue_num} — {issue_url}")

# ── 3. Telegram alert ─────────────────────────────────────────────────────────
TG_TOKEN = e.get("TG_TOKEN", "")
TG_CHAT  = e.get("TG_CHAT", "")

if TG_TOKEN and TG_CHAT:
    text = (
        f"🔧 CI self-heal triggered\n"
        f"Claude workflow failed — issue #{issue_num} created for auto-fix\n"
        f"Run: {RUN_URL}\n"
        f"Fix issue: {issue_url}"
    )
    payload = json.dumps({
        "chat_id": TG_CHAT,
        "text": text,
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read())
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API error: {result}")
    print("Telegram notified.")
else:
    print("No Telegram secrets — skipping notification.")
