#!/usr/bin/env python3
import json
import os
import urllib.error
import urllib.request

PENDING_FILE = "data/pending-news.json"
API = "https://api.github.com"
REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["GITHUB_TOKEN"]

def api(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Risk-Radar"
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode())

def ensure_label(name, color, description):
    try:
        api("POST", f"/repos/{REPO}/labels", {
            "name": name, "color": color, "description": description
        })
    except urllib.error.HTTPError as exc:
        # 422 means the label already exists; anything else is a real error.
        if exc.code != 422:
            raise

def main():
    ensure_label("pending-review", "f59e0b", "AI Risk Radar candidate awaiting manual verification")
    ensure_label("approved", "22c55e", "Manually verified and approved for publication")
    ensure_label("rejected", "ef4444", "Manually rejected and excluded from publication")

    with open(PENDING_FILE, encoding="utf-8") as f:
        pending = json.load(f)

    changed = False
    for item in pending:
        if item.get("issue_number"):
            continue

        body = f"""## AI Risk Radar — Manual Verification Required

**Platform:** {item["platform"]}  
**Company:** {item["company"]}  
**Risk type (automatic):** {item["type"]}  
**Severity estimate (automatic):** {item["severity"]}  
**Published date:** {item["date"] or "Unknown"}  
**Source:** {item["source"]}

### Headline
{item["headline"]}

### Source
{item["url"]}

### ⚡ Quick review
This story was automatically discovered and classified. **It has NOT been verified and must not be published until manually checked.**

**Fastest phone workflow:**
- Comment **a** = approve
- Comment **r** = reject

You can also type **approve** or **reject**, or use the labels if you prefer.

<!-- AIRR_ITEM_ID: {item["id"]} -->
"""

        issue = api("POST", f"/repos/{REPO}/issues", {
            "title": f"[AI RISK REVIEW] {item['headline'][:180]}",
            "body": body,
            "labels": ["pending-review"]
        })

        item["issue_number"] = issue["number"]
        item["issue_url"] = issue["html_url"]
        changed = True
        print(f"Created review issue #{issue['number']} for {item['headline']}")

    if changed:
        with open(PENDING_FILE, "w", encoding="utf-8") as f:
            json.dump(pending, f, indent=2, ensure_ascii=False)
            f.write("\n")

if __name__ == "__main__":
    main()
