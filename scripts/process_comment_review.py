#!/usr/bin/env python3
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

PENDING_FILE = "data/pending-news.json"
APPROVED_FILE = "data/approved-news.json"
API = "https://api.github.com"
REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["GITHUB_TOKEN"]
ISSUE_NUMBER = os.environ["ISSUE_NUMBER"]
COMMENT = os.environ.get("REVIEW_COMMENT", "").strip().lower()

def api(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        API + path, data=data, method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AI-Risk-Radar"
        })
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
        return json.loads(raw.decode()) if raw else {}

def main():
    if COMMENT not in {"a", "approve", "approved", "r", "reject", "rejected"}:
        print("Comment is not an exact review command. Ignoring.")
        return

    issue = api("GET", f"/repos/{REPO}/issues/{ISSUE_NUMBER}")
    body = issue.get("body") or ""
    marker = "AIRR_ITEM_ID:"
    item_id = next(
        (line.split(marker, 1)[1].replace("-->", "").strip()
         for line in body.splitlines() if marker in line),
        None
    )
    if not item_id:
        raise RuntimeError("AI Risk Radar item ID not found.")

    with open(PENDING_FILE, encoding="utf-8") as f:
        pending = json.load(f)
    with open(APPROVED_FILE, encoding="utf-8") as f:
        approved = json.load(f)

    matches = [x for x in pending if x.get("id") == item_id]
    if not matches:
        print("Candidate already processed or not found.")
        return

    item = matches[0]
    pending = [x for x in pending if x.get("id") != item_id]
    action = "approved" if COMMENT in {"a", "approve", "approved"} else "rejected"

    if action == "approved":
        item["status"] = "VERIFIED"
        item["verified_at"] = datetime.now(timezone.utc).isoformat()
        item["verified_via"] = "Manual GitHub quick-review command"
        item["verification_note"] = "Manually reviewed and approved by the repository owner."
        item["summary"] = "Manually verified AI-risk story. Review the original source for the full details."
        approved.append(item)

    final_label = "approved" if action == "approved" else "rejected"
    api("POST", f"/repos/{REPO}/issues/{ISSUE_NUMBER}/labels", {"labels": [final_label]})
    try:
        api("DELETE", f"/repos/{REPO}/issues/{ISSUE_NUMBER}/labels/pending-review")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    api("POST", f"/repos/{REPO}/issues/{ISSUE_NUMBER}/comments", {
        "body": "Approved — published to the verified dataset." if action == "approved" else "Rejected — removed from the pending review queue."
    })
    api("PATCH", f"/repos/{REPO}/issues/{ISSUE_NUMBER}", {
        "state": "closed",
        "state_reason": "completed"
    })
    print(f"{action}: {item['headline']}")

if __name__ == "__main__":
    main()
