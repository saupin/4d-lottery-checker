import json
import os
import urllib.request

e = os.environ
outcome = e.get("OUTCOME", "")
icon = "✅" if outcome == "success" else "❌"
status = "Implementation complete" if outcome == "success" else "Implementation failed"

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
