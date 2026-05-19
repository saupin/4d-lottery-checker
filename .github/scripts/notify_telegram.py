import json
import os
import urllib.request

e = os.environ
claude_outcome = e.get("CLAUDE_OUTCOME", "")
merge_outcome  = e.get("MERGE_OUTCOME", "")

# Determine overall result:
# - merge succeeded  → ✅ deployed
# - claude failed    → ❌ claude error
# - merge failed     → ❌ merge/push error
# - merge skipped (claude ok but no branch / already merged) → ℹ️ nothing to deploy
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

text = (
    f"{icon} {status}\n"
    f"#{e.get('ISSUE_NUM', '?')}: {e.get('ISSUE_TITLE', '')}\n"
    f"{e.get('ISSUE_URL', '')}"
)

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
urllib.request.urlopen(req)
