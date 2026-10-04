#!/usr/bin/env python3
import hashlib
import html
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
        "security breach", "security flaw", "cyberattack", "cyber attack",
        "hack", "hacked", "hacking", "vulnerability", "vulnerabilities",
        "exploit", "exploited", "malware", "credential theft", "data leak"
    ],
    "privacy": [
        "privacy", "personal data", "user data", "data exposure",
        "surveillance", "privacy violation", "data collection", "tracking"
    ],
    "regulatory": [
        "regulator", "regulatory", "fine", "penalty", "government",
        "antitrust", "compliance", "investigation", "ban", "blocked",
        "lawmakers", "regulator", "sanctions"
    ],
    "legal": [
        "lawsuit", "court", "sued", "legal action", "copyright",
        "copyright infringement", "class action", "judge", "litigation",
        "settlement"
    ],
    "operational": [
        "outage", "downtime", "service disruption", "disruption",
        "unavailable", "incident", "service failure", "degraded service"
    ],
    "safety": [
        "ai safety", "safety concern", "safety concerns", "safety issue",
        "dangerous", "misuse", "harmful", "jailbreak", "harm",
        "child safety", "model safety", "safety risk"
    ],
}

# These phrases commonly describe normal product/business news rather than risk.
NON_RISK_PHRASES = [
    "introducing ", "introduces ", "announces new", "new feature",
    "new model", "launches", "launch of", "product launch",
    "partnership", "partners with", "funding", "investment",
    "acquires", "acquisition", "raises $", "raises £", "raises €",
    "research paper", "conference", "event", "available now",
    "now available", "expands", "expansion", "training ", "hiring ",
    "job openings", "new capability", "new integration"
]

STRONG_RISK_TERMS = {
    term
    for terms in RISK_TERMS.values()
    for term in terms
    if len(term) >= 7
}

QUERY_GROUPS = [
    "security breach hack vulnerability exploit cyberattack",
    "privacy data leak user data surveillance",
    "lawsuit court copyright legal action litigation",
    "regulatory regulator fine penalty investigation ban government",
    "outage downtime service disruption incident",
    "AI safety harmful misuse jailbreak child safety"
]

def clean(text):
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def normalize_title(text):
    text = clean(text).lower()
    text = re.sub(r"\s*[-|–—]\s*[^-–—|]+$", "", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def title_tokens(text):
    return set(normalize_title(text).split())

def similar_title(a, b):
    ta, tb = title_tokens(a), title_tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / max(1, min(len(ta), len(tb))) >= 0.82

def classify(text):
    text = text.lower()
    scores = {}
    for category, terms in RISK_TERMS.items():
        scores[category] = sum(1 for term in terms if term in text)
    best = max(scores, key=scores.get)
    return best if scores[best] else None

def matched_terms(text):
    text = text.lower()
    found = []
    for category, terms in RISK_TERMS.items():
        for term in terms:
            if term in text:
                found.append(term)
    return list(dict.fromkeys(found))[:8]

def severity(text):
    text = text.lower()
    high = [
        "breach", "hack", "hacked", "cyberattack", "data leak",
        "lawsuit", "fine", "penalty", "vulnerability", "exploit",
        "blocked", "ban", "sanctions", "credential theft"
    ]
    medium = [
        "investigation", "regulatory", "outage", "privacy",
        "copyright", "safety", "jailbreak", "court", "litigation",
        "disruption", "surveillance"
    ]
    if any(x in text for x in high):
        return "high"
    if any(x in text for x in medium):
        return "medium"
    return "low"

def confidence(text, category, source_name):
    terms = matched_terms(text)
    score = min(95, 35 + len(terms) * 10)
    if category in {"security", "legal", "regulatory"}:
        score += 5
    if source_name:
        score += 5
    score = min(95, score)
    if score >= 75:
        label = "high"
    elif score >= 55:
        label = "medium"
    else:
        label = "low"
    return score, label

def fetch_feed(query):
    encoded = urllib.parse.quote_plus(query)
    url = (
        "https://news.google.com/rss/search?q=" + encoded +
        "&hl=en-US&gl=US&ceid=US:en"
    )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AI-Risk-Radar/2.0 (+https://pratikshya0803.github.io/ai-risk-radar/)"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()

def stable_id(link, title):
    base = (link or title).strip()
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:20]

def source_name(item):
    source = item.find("source")
    return clean(source.text if source is not None else "")

def main():
    with open(PLATFORMS_FILE, encoding="utf-8") as f:
        platforms = json.load(f)
    with open(PENDING_FILE, encoding="utf-8") as f:
        pending = json.load(f)
    with open(APPROVED_FILE, encoding="utf-8") as f:
        approved = json.load(f)

    known_urls = {clean(item.get("url")) for item in pending + approved if item.get("url")}
    known_titles = {normalize_title(item.get("headline", "")) for item in pending + approved}

    new_items = []

    for platform in platforms:
        name = platform["name"]
        company = platform["company"]

        # Several focused queries catch more risk stories than one broad query.
        queries = []
        for group in QUERY_GROUPS:
            queries.append(f'("{name}" OR "{company}") ({group})')

        for query in queries:
            try:
                root = ET.fromstring(fetch_feed(query))
            except Exception as exc:
                print(f"Feed error for {name} [{query}]: {exc}")
                continue

            for item in root.findall("./channel/item")[:8]:
                title = clean(item.findtext("title"))
                link = clean(item.findtext("link"))
                pub_date = clean(item.findtext("pubDate"))
                description = clean(item.findtext("description"))
                publisher = source_name(item)

                if not title or not link:
                    continue

                normalized = normalize_title(title)
                if link in known_urls or normalized in known_titles:
                    continue

                # Avoid duplicate syndicated coverage already captured in another feed.
                if any(similar_title(title, existing.get("headline", "")) for existing in new_items[-150:]):
                    continue

                evidence = f"{title} {description}".lower()
                category = classify(evidence)
                if category is None:
                    continue

                # Normal product/business announcements are excluded unless
                # there is a concrete risk signal in the same story.
                if any(phrase in evidence for phrase in NON_RISK_PHRASES):
                    if not any(term in evidence for term in STRONG_RISK_TERMS):
                        continue

                terms = matched_terms(evidence)
                score, confidence_label = confidence(evidence, category, publisher)

                record = {
                    "id": stable_id(link, title),
                    "platform": name,
                    "company": company,
                    "type": category,
                    "severity": severity(evidence),
                    "headline": title,
                    "summary": (
                        "Unverified discovery. Matched risk signals: " +
                        ", ".join(terms[:5]) +
                        ". Manual verification required before publication."
                    ),
                    "source": "Google News RSS",
                    "source_name": publisher or "Unknown publisher",
                    "url": link,
                    "date": pub_date,
                    "status": "UNVERIFIED",
                    "capture_confidence": confidence_label,
                    "capture_confidence_score": score,
                    "matched_risk_terms": terms,
                    "discovered_at": datetime.now(timezone.utc).isoformat()
                }

                new_items.append(record)
                known_urls.add(link)
                known_titles.add(normalized)

    pending.extend(new_items)

    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(pending, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Added {len(new_items)} new risk candidates to the pending review queue.")

if __name__ == "__main__":
    main()
