
#!/usr/bin/env python3
"""
BrowseBloom Focused News Draft Generator
Version 2.0

Reads trends.json, researches Google News RSS,
groups related headlines, and generates ONE
focused HTML research draft.

Free to run. No external Python packages.
No paid API.

IMPORTANT:
- Headlines are not full article evidence.
- This script does not verify underlying claims.
- Generated drafts must be reviewed before publishing.
"""

import json
import re
import html
import math
import hashlib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from collections import Counter


# ==========================================
# CONFIGURATION
# ==========================================

ROOT = Path(__file__).resolve().parent.parent

TRENDS_FILE = ROOT / "trends.json"
DRAFTS_DIR = ROOT / "drafts"

MAX_TRENDS = 10
MAX_NEWS_PER_TREND = 30
MAX_AGE_DAYS = 5

MIN_PUBLISHERS = 2
MIN_CLUSTER_SCORE = 0.43

USER_AGENT = (
    "BrowseBloomResearchBot/2.0 "
    "(news draft research)"
)

# Exclude topics that need more careful editorial handling
# from unattended first-pass drafting.
BLOCKED_TOPIC_WORDS = {
    "suicide",
    "self harm",
    "sexual assault",
    "rape",
    "terror attack"
}

# Reject obvious non-news listings.
BLOCKED_HEADLINE_WORDS = {
    
BLOCKED_HEADLINE_WORDS = {
    "obituary",
    "obituaries",
    "death notice",
    "funeral service",
    "classifieds",
    "horoscope",
    "daily horoscope",
    "lottery results",
    "job openings",
    "real estate listings",

    # Promotional and affiliate content
    "promo code",
    "promotional code",
    "coupon code",
    "discount code",
    "referral code",
    "signup bonus",
    "sign-up bonus",
    "welcome bonus",
    "bonus offer",
    "exclusive offer",
    "special offer",
    "get $",
    "claim your bonus",
    "free bets",
    "best betting sites",
    "betting bonus",
    "odds boost"
}

}

# Common words that do not identify an event.
STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to",
    "in", "on", "at", "for", "from", "by",
    "with", "as", "is", "are", "was", "were",
    "be", "been", "this", "that", "it",
    "its", "their", "his", "her", "after",
    "before", "over", "under", "into",
    "about", "more", "new", "latest",
    "today", "yesterday", "canada",
    "canadian", "news", "report",
    "reports", "says", "say", "said",
    "could", "would", "should",
    "what", "why", "how", "when",
    "where", "who", "will", "now",
    "here", "these", "those",
    "has", "have", "had", "not",
    "than", "then", "up", "out",
    "one", "two", "three",
    "first", "last", "week",
    "year", "years", "day", "days",
    "city", "local", "near",
    "que", "qc", "ont", "ontario"
}


# ==========================================
# UTILITIES
# ==========================================

def utc_now():
    return datetime.now(timezone.utc)


def slugify(text):
    text = text.lower()

    text = re.sub(
        r"[^a-z0-9]+",
        "-",
        text
    )

    return text.strip("-")[:75].strip("-") or "news"


def escape(value):
    return html.escape(str(value), quote=True)


def normalize_spaces(value):
    return " ".join(str(value).split())


def tokenize(text):
    """
    Extract meaningful words for headline comparison.
    """
    words = re.findall(
        r"[a-z0-9]+",
        text.casefold()
    )

    return {
        word
        for word in words
        if len(word) >= 3
        and word not in STOPWORDS
    }


def format_date(value):
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%B %d, %Y")
    except (ValueError, TypeError):
        return ""


def safe_url(value):
    try:
        parsed = urllib.parse.urlparse(value)

        if parsed.scheme == "https" and parsed.netloc:
            return value
    except (ValueError, TypeError):
        pass

    return ""


# ==========================================
# READ GOOGLE TRENDS DATA
# ==========================================

def extract_items(data):
    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    for key in (
        "trends",
        "topics",
        "items",
        "data",
        "results",
        "trending_searches",
        "trendingSearches"
    ):
        value = data.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            nested = extract_items(value)
            if nested:
                return nested

    return []


def read_trends():
    if not TRENDS_FILE.exists():
        raise FileNotFoundError(
            "trends.json was not found."
        )

    with TRENDS_FILE.open(
        "r",
        encoding="utf-8"
    ) as file:
        data = json.load(file)

    items = extract_items(data)

    trends = []
    seen = set()

    for item in items:
        if isinstance(item, str):
            title = item

        elif isinstance(item, dict):
            title = (
                item.get("title")
                or item.get("query")
                or item.get("keyword")
                or item.get("name")
                or item.get("topic")
                or item.get("search_term")
                or item.get("searchTerm")
                or ""
            )

            if isinstance(title, dict):
                title = (
                    title.get("title")
                    or title.get("name")
                    or ""
                )
        else:
            continue

        if not isinstance(title, str):
            continue

        title = normalize_spaces(title)

        if not title:
            continue

        key = title.casefold()

        if key in seen:
            continue

        seen.add(key)
        trends.append(title)

    return trends[:MAX_TRENDS]


# ==========================================
# GOOGLE NEWS RESEARCH
# ==========================================

def fetch_news(topic):
    """
    Retrieve recent Google News RSS headlines
    for a Canadian search topic.
    """

    query = f'"{topic}" when:{MAX_AGE_DAYS}d'

    params = urllib.parse.urlencode({
        "q": query,
        "hl": "en-CA",
        "gl": "CA",
        "ceid": "CA:en"
    })

    url = (
        "https://news.google.com/rss/search?"
        + params
    )

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/xml"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=25
    ) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)

    results = []
    seen = set()

    cutoff = utc_now() - timedelta(
        days=MAX_AGE_DAYS
    )

    for item in root.findall("./channel/item"):
        title = normalize_spaces(
            item.findtext("title", "")
        )

        link = normalize_spaces(
            item.findtext("link", "")
        )

        pub_date = item.findtext(
            "pubDate",
            ""
        )

        source_node = item.find("source")

        publisher = (
            normalize_spaces(source_node.text)
            if source_node is not None
            and source_node.text
            else "Unknown Publisher"
        )

        if not title or not safe_url(link):
            continue

        try:
            published = parsedate_to_datetime(
                pub_date
            )

            if published.tzinfo is None:
                published = published.replace(
                    tzinfo=timezone.utc
                )

            published = published.astimezone(
                timezone.utc
            )

        except (ValueError, TypeError, OverflowError):
            continue

        if published < cutoff:
            continue

        if published > utc_now() + timedelta(hours=1):
            continue

        lower_title = title.casefold()

        if any(
            blocked in lower_title
            for blocked in BLOCKED_HEADLINE_WORDS
        ):
            continue

        # Remove publisher suffix for comparison.
        clean_title = title

        suffix = " - " + publisher

        if title.casefold().endswith(
            suffix.casefold()
        ):
            clean_title = title[:-len(suffix)]

        clean_title = normalize_spaces(
            clean_title
        )

        # Require a meaningful headline.
        tokens = tokenize(clean_title)

        if len(tokens) < 3:
            continue

        # Prevent a topic matching only a tiny
        # unrelated fragment of a headline.
        topic_words = tokenize(topic)

        if topic_words and not (
            topic_words & tokens
        ):
            continue

        duplicate_key = clean_title.casefold()

        if duplicate_key in seen:
            continue

        seen.add(duplicate_key)

        results.append({
            "title": clean_title,
            "publisher": publisher,
            "url": link,
            "published": published.isoformat(),
            "tokens": tokens
        })

        if len(results) >= MAX_NEWS_PER_TREND:
            break

    return results


# ==========================================
# EVENT SIMILARITY
# ==========================================

def headline_similarity(a, b, topic):
    """
    Compare event-specific headline vocabulary.

    Generic topic words are excluded so that
    stories about the same city/person do not
    automatically count as the same event.
    """

    topic_tokens = tokenize(topic)

    words_a = a["tokens"] - topic_tokens
    words_b = b["tokens"] - topic_tokens

    if len(words_a) < 2 or len(words_b) < 2:
        return 0.0

    shared = words_a & words_b

    if len(shared) < 2:
        return 0.0

    union = words_a | words_b

    jaccard = len(shared) / max(
        1,
        len(union)
    )

    containment = len(shared) / max(
        1,
        min(len(words_a), len(words_b))
    )

    return (
        0.4 * jaccard
        + 0.6 * containment
    )


def cluster_articles(articles, topic):
    """
    Build focused clusters using a strong
    pairwise relationship.

    Every article in a cluster must be similar
    to every other article in that cluster.

    This is deliberately conservative.
    """

    clusters = []

    for article in articles:
        placed = False

        for cluster in clusters:
            similarities = [
                headline_similarity(
                    article,
                    member,
                    topic
                )
                for member in cluster
            ]

            if similarities and min(
                similarities
            ) >= MIN_CLUSTER_SCORE:
                cluster.append(article)
                placed = True
                break

        if not placed:
            clusters.append([article])

    return clusters


def distinct_publishers(cluster):
    return {
        article["publisher"].casefold()
        for article in cluster
        if article["publisher"] != "Unknown Publisher"
    }


def cluster_quality(cluster, topic):
    """
    Prefer several publishers covering
    the same event, with recent reporting.
    """

    publishers = distinct_publishers(cluster)

    if len(publishers) < MIN_PUBLISHERS:
        return -1

    # Check headline cohesion.
    similarities = []

    for i in range(len(cluster)):
        for j in range(i + 1, len(cluster)):
            similarities.append(
                headline_similarity(
                    cluster[i],
                    cluster[j],
                    topic
                )
            )

    cohesion = (
        sum(similarities) / len(similarities)
        if similarities else 0
    )

    latest = max(
        datetime.fromisoformat(
            article["published"]
        )
        for article in cluster
    )

    age_hours = max(
        0,
        (utc_now() - latest).total_seconds() / 3600
    )

    recency = math.exp(
        -age_hours / 96
    )

    return (
        len(publishers) * 4
        + len(cluster) * 1.5
        + cohesion * 5
        + recency * 2
    )


def choose_story(trends):
    """
    Search trends in order, choosing the
    strongest coherent event cluster.
    """

    candidates = []

    for topic in trends:
        print(f"\nResearching trend: {topic}")

        if any(
            blocked in topic.casefold()
            for blocked in BLOCKED_TOPIC_WORDS
        ):
            print("Skipped sensitive topic.")
            continue

        try:
            articles = fetch_news(topic)

        except Exception as error:
            print(f"News fetch failed: {error}")
            continue

        print(
            f"Found {len(articles)} eligible headlines."
        )

        clusters = cluster_articles(
            articles,
            topic
        )

        for cluster in clusters:
            quality = cluster_quality(
                cluster,
                topic
            )

            if quality < 0:
                continue

            candidates.append({
                "topic": topic,
                "articles": cluster,
                "quality": quality
            })

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item["quality"],
        reverse=True
    )

    return candidates[0]


# ==========================================
# CREATE FOCUSED ARTICLE DRAFT
# ==========================================

def select_headline(cluster):
    """
    Use a headline from an actual publisher
    rather than inventing an event claim.
    """

    publisher_counts = Counter(
        item["publisher"]
        for item in cluster
    )

    ranked = sorted(
        cluster,
        key=lambda item: (
            -len(item["tokens"]),
            publisher_counts[item["publisher"]],
            -datetime.fromisoformat(
                item["published"]
            ).timestamp()
        )
    )

    return ranked[0]["title"]


def build_article(story):
    topic = story["topic"]

    articles = sorted(
        story["articles"],
        key=lambda item: item["published"],
        reverse=True
    )

    headline = select_headline(articles)

    date_label = utc_now().strftime(
        "%B %d, %Y"
    )

    sources_html = []

    for article in articles:
        url = escape(article["url"])
        title = escape(article["title"])
        publisher = escape(
            article["publisher"]
        )

        published = format_date(
            article["published"]
        )

        sources_html.append(f"""
        <article class="source-card">
          <div class="publisher">
            {publisher}
          </div>

          <h3>{title}</h3>

          <p>Published: {escape(published)}</p>

          <a href="{url}"
             target="_blank"
             rel="noopener noreferrer">
             Read original reporting ↗
          </a>
        </article>
        """)

    sources_markup = "\n".join(
        sources_html
    )

    publisher_count = len(
        distinct_publishers(articles)
    )

    description = (
        f"Browse recent reporting about {topic} "
        "from multiple news publishers."
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>{escape(headline)} | BrowseBloom</title>

<meta name="description"
      content="{escape(description)}">

<meta name="robots" content="noindex, nofollow">

<style>
:root {{
  --green: #245b45;
  --dark: #183f31;
  --ink: #202824;
  --muted: #68736d;
  --cream: #faf9f6;
  --line: #e5e8e3;
}}

* {{
  box-sizing: border-box;
}}

body {{
  margin: 0;
  font-family: Arial, sans-serif;
  background: var(--cream);
  color: var(--ink);
  line-height: 1.7;
}}

a {{
  color: var(--green);
}}

header {{
  background: var(--dark);
  padding: 20px;
}}

.logo {{
  font-family: Georgia, serif;
  font-size: 28px;
  font-weight: bold;
  color: white;
  text-decoration: none;
}}

.container {{
  width: min(850px, calc(100% - 36px));
  margin: auto;
}}

main {{
  padding-top: 48px;
  padding-bottom: 55px;
}}

.label {{
  color: var(--green);
  text-transform: uppercase;
  font-size: 12px;
  font-weight: bold;
  letter-spacing: 1px;
}}

h1 {{
  font-family: Georgia, serif;
  font-size: clamp(32px, 5vw, 46px);
  line-height: 1.2;
  margin: 12px 0 20px;
}}

h2 {{
  font-family: Georgia, serif;
  font-size: 27px;
  margin-top: 35px;
}}

h3 {{
  font-family: Georgia, serif;
  line-height: 1.35;
}}

.intro {{
  font-size: 17px;
  color: #4c5d53;
}}

.metadata {{
  font-size: 13px;
  color: var(--muted);
  margin: 20px 0;
}}

.notice {{
  padding: 20px;
  background: #edf3ed;
  border-left: 4px solid var(--green);
  margin: 28px 0;
}}

.source-card {{
  background: white;
  border: 1px solid var(--line);
  border-radius: 9px;
  padding: 22px;
  margin: 16px 0;
}}

.source-card h3 {{
  margin: 8px 0;
  font-size: 21px;
}}

.source-card p {{
  color: var(--muted);
  font-size: 13px;
}}

.source-card a {{
  font-weight: bold;
  text-decoration: none;
}}

.publisher {{
  font-size: 12px;
  color: var(--green);
  text-transform: uppercase;
  font-weight: bold;
  letter-spacing: .5px;
}}

footer {{
  border-top: 1px solid var(--line);
  padding-top: 20px;
  margin-top: 45px;
  color: var(--muted);
  font-size: 13px;
}}
</style>

</head>

<body>

<header>
  <div class="container">
    <a class="logo"
       href="../index.html">
       BrowseBloom.
    </a>
  </div>
</header>

<main class="container">

  <div class="label">
    Canada News · Research Briefing
  </div>

  <h1>{escape(headline)}</h1>

  <p class="intro">
    Recent news coverage related to
    <strong>{escape(topic)}</strong>
    appears below. These reports were
    grouped because their headlines
    share details suggesting they
    discuss the same event.
  </p>

  <div class="metadata">
    Prepared: {date_label} (UTC)
    · {len(articles)} reports
    · {publisher_count} publishers
  </div>

  <div class="notice">
    <strong>Editorial review required.</strong>

    This page is an automatically generated
    research draft. Its headline comes from
    a publisher's RSS feed.

    The source articles have not been
    independently read or fact-checked.

    Confirm that all linked reports concern
    the same event before publishing.
  </div>

  <h2>The Story Being Reported</h2>

  <p>
    The reports below appear to cover
    a related development involving
    <strong>{escape(topic)}</strong>.
    Their headlines share event-specific
    terms, but the underlying facts
    still require verification.
  </p>

  <h2>Reporting From Multiple Sources</h2>

  {sources_markup}

  <h2>What Happens Next?</h2>

  <p>
    An editor should read the original
    coverage, confirm the timeline,
    identify any differing accounts,
    and explain the significance
    for readers in Canada.
  </p>

  <h2>About This Research Draft</h2>

  <p>
    BrowseBloom collects public news
    headlines to identify stories worth
    researching. Inclusion here does not
    mean BrowseBloom has independently
    verified the reporting.
  </p>

  <footer>
    BrowseBloom · Unpublished editorial draft
  </footer>

</main>

</body>
</html>
"""


# ==========================================
# SAVE ONE DRAFT
# ==========================================

def save_draft(story):
    DRAFTS_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    headline = select_headline(
        story["articles"]
    )

    date_prefix = utc_now().strftime(
        "%Y-%m-%d"
    )

    fingerprint = hashlib.sha256(
        (
            story["topic"].casefold()
            + "|"
            + "|".join(
                sorted(
                    article["title"].casefold()
                    for article in story["articles"]
                )
            )
        ).encode("utf-8")
    ).hexdigest()[:8]

    filename = (
        date_prefix
        + "-"
        + slugify(headline)
        + "-"
        + fingerprint
        + ".html"
    )

    output = DRAFTS_DIR / filename

    if output.exists():
        print(
            "Draft already exists. "
            "No duplicate file created."
        )
        return output

    content = build_article(story)

    output.write_text(
        content,
        encoding="utf-8"
    )

    return output


# ==========================================
# MAIN
# ==========================================

def main():
    print("=" * 55)
    print("BROWSEBLOOM FOCUSED ARTICLE GENERATOR")
    print("=" * 55)

    trends = read_trends()

    if not trends:
        raise SystemExit(
            "No trending topics found."
        )

    print(
        f"Loaded {len(trends)} Canadian trends."
    )

    story = choose_story(trends)

    if story is None:
        print(
            "\nNo sufficiently coherent story "
            "with multiple publishers was found."
        )
        print(
            "No draft created. "
            "Try again after trends update."
        )
        return

    headline = select_headline(
        story["articles"]
    )

    output = save_draft(story)

    print("\n" + "=" * 55)
    print("RESULT")
    print("=" * 55)

    print("Topic:", story["topic"])
    print("Headline:", headline)

    print(
        "Reports:",
        len(story["articles"])
    )

    print(
        "Publishers:",
        len(distinct_publishers(
            story["articles"]
        ))
    )

    print(
        "Quality score:",
        round(story["quality"], 2)
    )

    print(
        "Saved:",
        output.relative_to(ROOT)
    )

    print(
        "Status: UNPUBLISHED DRAFT"
    )

    print("=" * 55)


if __name__ == "__main__":
    main()
