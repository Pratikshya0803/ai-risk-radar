#!/usr/bin/env python3
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

PLATFORMS_FILE = "data/platforms.json"
PENDING_FILE = "data/pending-news.json"
APPROVED_FILE = "data/approved-news.json"

RISK_TERMS = {
    "security": ["security", "hack", "hacked", "cyberattack", "cyber attack", "vulnerability", "exploit", "breach", "incident"],
    "privacy": ["privacy", "personal data", "user data", "data exposure", "surveillance"],
    "regulatory": ["regulator", "regulatory", "fine", "penalty", "government", "antitrust", "compliance", "investigation"],
    "legal": ["lawsuit", "court", "sued", "legal action", "copyright", "copyright infringement", "class action"],
    "operational": ["outage", "downtime", "service disruption", "disruption", "incident", "availability"],
    "safety": ["ai safety", "safety", "dangerous", "misuse", "harmful", "risk", "jailbreak"],
}

def clean(text):
    return re.sub(r"\\s+", " ", (text or "")).strip()

def classify(title):
    text = title.lower()
    for category, terms in RISK_TERMS.items():
        if any(term in text for term in terms):
            return category
    return "operational"

def severity(title):
    text = title.lower()
    high = ["breach", "hack", "cyberattack", "lawsuit", "fine", "penalty", "vulnerability", "exploit"]
    medium = ["investigation", "regulatory", "outage", "privacy", "copyright", "safety"]
    if any(x in text for x in high):
        return "high"
    if any(x in text for x in medium):
        return "medium"
    return "low"

def fetch_feed(query):
    encoded = urllib.parse.quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AI-Risk-Radar/1.0"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()

def main():
    with open(PLATFORMS_FILE, encoding="utf-8") as f:
        platforms = json.load(f)

    with open(PENDING_FILE, encoding="utf-8") as f:
        pending = json.load(f)

    with open(APPROVED_FILE, encoding="utf-8") as f:
        approved = json.load(f)

    known = {
        item.get("url") or item.get("headline")
        for item in pending + approved
    }

    new_items = []

    for platform in platforms:
        name = platform["name"]
        company = platform["company"]

        query = (
            f'"{name}" "{company}" '
            '(security OR privacy OR breach OR lawsuit OR regulatory OR outage OR safety)'
        )

        try:
            root = ET.fromstring(fetch_feed(query))
        except Exception as exc:
            print(f"Feed error for {name}: {exc}")
            continue

        for item in root.findall("./channel/item")[:5]:
            title = clean(item.findtext("title"))
            link = clean(item.findtext("link"))
            pub_date = clean(item.findtext("pubDate"))

            if not title or not link or link in known or title in known:
                continue

            category = classify(title)
            item_record = {
                "id": str(abs(hash(link))),
                "platform": name,
                "company": company,
                "type": category,
                "severity": severity(title),
                "headline": title,
                "summary": "Unverified discovery from a public news feed. Manual verification required before publication.",
                "source": "Google News RSS",
                "url": link,
                "date": pub_date,
                "status": "UNVERIFIED",
                "discovered_at": datetime.now(timezone.utc).isoformat()
            }

            new_items.append(item_record)
            known.add(link)

    pending.extend(new_items)

    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(pending, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Added {len(new_items)} new items to the pending review queue.")

if __name__ == "__main__":
    main()
