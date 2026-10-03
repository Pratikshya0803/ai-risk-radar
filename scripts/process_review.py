#!/usr/bin/env python3
import json
import os
import urllib.request
from datetime import datetime, timezone

PENDING_FILE = "data/pending-news.json"
APPROVED_FILE = "data/approved-news.json"
API = "https://api.github.com"
REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["GITHUB_TOKEN"]
ISSUE_NUMBER = os.environ["ISSUE_NUMBER"]
ACTION_LABEL = os.environ["ACTION_LABEL"]

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
        return json.loads(response.read().decode()) if response.readable() else {}

def main():
    issue = api("GET", f"/repos/{REPO}/issues/{ISSUE_NUMBER}")
    body = issue.get("body") or ""
    marker = "AIRR_ITEM_ID:"
    item_id = None
    for line in body.splitlines():
        if marker in line:
            item_id = line.split(marker, 1)[1].replace("-->", "").strip()
            break

    if not item_id:
        raise RuntimeError("Could not find AI Risk Radar item ID in issue body.")

    with open(PENDING_FILE, encoding="utf-8") as f:
        pending = json.load(f)
    with open(APPROVED_FILE, encoding="utf-8") as f:
        approved = json.load(f)

    matches = [x for x in pending if x.get("id") == item_id]
    if not matches:
        print("Candidate is already processed or no longer in the pending queue.")
        return

    item = matches[0]
    pending = [x for x in pending if x.get("id") != item_id]

    if ACTION_LABEL == "approved":
        item["status"] = "VERIFIED"
        item["verified_at"] = datetime.now(timezone.utc).isoformat()
        item["verified_via"] = "Manual GitHub issue approval"
        item["verification_note"] = "Manually reviewed and approved by the repository owner."\n        item["summary"] = "Manually verified AI-risk story. Review the original source for the full details."
        approved.append(item)
        print(f"Approved: {item['headline']}")
    else:
        print(f"Rejected: {item['headline']}")

    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(pending, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(APPROVED_FILE, "w", encoding="utf-8") as f:
        json.dump(approved, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Close the review issue after processing. Keep the final label visible.
    api("PATCH", f"/repos/{REPO}/issues/{ISSUE_NUMBER}", {
        "state": "closed",
        "state_reason": "completed"
    })

if __name__ == "__main__":
    main()
