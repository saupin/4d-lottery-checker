import json
import os
import urllib.request

e = os.environ
claude_outcome = e.get("CLAUDE_OUTCOME", "")
merge_outcome  = e.get("MERGE_OUTCOME", "")
run_url        = e.get("RUN_URL", "")

if merge_outcome == "success":
    icon   = "✅"
    status = "Merged to master — deploying"
elif claude_outcome == "failure":
    icon   = "❌"
    status = "Claude failed to implement (check Actions log)"
elif merge_outcome == "failure":
    icon   = "❌"
    status = "Merge to master failed (check Actions log)"
else:
    icon   = "ℹ️"
    status = "Claude ran but nothing new to merge"

lines = [
    f"{icon} {status}",
    f"#{e.get('ISSUE_NUM', '?')}: {e.get('ISSUE_TITLE', '')}",
    e.get("ISSUE_URL", ""),
]
if run_url:
    lines.append(f"Run: {run_url}")

text = "\n".join(l for l in lines if l)

payload = json.dumps({
    "chat_id": e["TG_CHAT"],
    "text": text,
    "disable_web_page_preview": True,
}).encode()

req = urllib.request.Request(
    f"https://api.telegram.org/bot{e['TG_TOKEN']}/sendMessage",
    data=payload,
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req) as resp:
    result = json.loads(resp.read())

if not result.get("ok"):
    raise RuntimeError(f"Telegram API error: {result}")

print("Telegram notification sent.")
