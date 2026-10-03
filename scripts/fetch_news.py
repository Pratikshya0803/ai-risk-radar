#!/usr/bin/env python3
import hashlib
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
    "security": [
        "security", "hack", "hacked", "cyberattack", "cyber attack",
        "vulnerability", "exploit", "breach", "data leak", "security flaw"
    ],
    "privacy": [
        "privacy", "personal data", "user data", "data exposure",
        "surveillance", "data leak", "privacy violation"
    ],
    "regulatory": [
        "regulator", "regulatory", "fine", "penalty", "government",
        "antitrust", "compliance", "investigation", "ban", "blocked"
    ],
    "legal": [
        "lawsuit", "court", "sued", "legal action", "copyright",
        "copyright infringement", "class action", "judge"
    ],
    "operational": [
        "outage", "downtime", "service disruption", "disruption",
        "unavailable", "down for", "incident", "availability"
    ],
    "safety": [
        "ai safety", "safety concern", "safety concerns", "safety issue",
        "dangerous", "misuse", "harmful", "risk", "jailbreak", "harm"
    ],
}

# These phrases commonly describe normal product/business news rather than a risk event.
POSITIVE_OR_NON_RISK = [
    "introducing ", "introduces ", "announces new", "new feature",
    "new model", "launches", "launch of", "product launch",
    "partnership", "partners with", "funding", "investment",
    "acquires", "acquisition", "raises $", "raises £", "raises €",
    "research paper", "researchers met", "conference", "event",
    "available now", "now available", "expands", "expansion",
    "training ", "hiring ", "job openings"
]

def clean(text):
    return re.sub(r"\s+", " ", (text or "")).strip()

def classify(title):
    text = title.lower()
    for category, terms in RISK_TERMS.items():
        if any(term in text for term in terms):
            return category
    return None

def severity(title):
    text = title.lower()
    high = [
        "breach", "hack", "hacked", "cyberattack", "data leak",
        "lawsuit", "fine", "penalty", "vulnerability", "exploit",
        "blocked", "ban"
    ]
    medium = [
        "investigation", "regulatory", "outage", "privacy",
        "copyright", "safety", "jailbreak", "court"
    ]
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
        headers={"User-Agent": "AI-Risk-Radar/1.1"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()

def stable_id(link):
    return hashlib.sha256(link.encode("utf-8")).hexdigest()[:20]

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
            '(security OR privacy OR breach OR lawsuit OR regulatory '
            'OR outage OR safety OR vulnerability OR copyright OR court)'
        )

        try:
            root = ET.fromstring(fetch_feed(query))
        except Exception as exc:
            print(f"Feed error for {name}: {exc}")
            continue

        for item in root.findall("./channel/item")[:8]:
            title = clean(item.findtext("title"))
            link = clean(item.findtext("link"))
            pub_date = clean(item.findtext("pubDate"))

            if not title or not link or link in known or title in known:
                continue

            title_lower = title.lower()
            category = classify(title)

            # Do not put normal product/business announcements into the risk queue.
            if category is None:
                continue

            # A positive/non-risk phrase is ignored unless the same headline has
            # a concrete risk signal such as breach, lawsuit, outage, etc.
            if any(phrase in title_lower for phrase in POSITIVE_OR_NON_RISK):
                strong_risk = any(
                    term in title_lower
                    for terms in RISK_TERMS.values()
                    for term in terms
                    if len(term) >= 6
                )
                if not strong_risk:
                    continue

            item_record = {
                "id": stable_id(link),
                "platform": name,
                "company": company,
                "type": category,
                "severity": severity(title),
                "headline": title,
                "summary": (
                    "Unverified discovery from a public news feed. "
                    "Manual verification required before publication."
                ),
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

    print(f"Added {len(new_items)} new risk candidates to the pending review queue.")

if __name__ == "__main__":
    main()
