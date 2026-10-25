
import json
import re
import html
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime


# ==========================================
# BROWSEBLOOM - ARTICLE DRAFT GENERATOR
# Creates ONE draft. Does not publish.
# No paid API required.
# ==========================================

ROOT = Path(__file__).resolve().parent.parent
TRENDS_FILE = ROOT / "trends.json"
DRAFTS_DIR = ROOT / "drafts"

MAX_SOURCES = 5
MAX_TRENDS_TO_TRY = 10
MAX_AGE_DAYS = 7


def read_trends():
    with open(TRENDS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = []

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
                items = value
                break

            if isinstance(value, dict):
                for nested_key in ("trends", "items", "topics"):
                    nested = value.get(nested_key)
                    if isinstance(nested, list):
                        items = nested
                        break

                if items:
                    break
    else:
        items = []

    titles = []

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

        if isinstance(title, str) and title.strip():
            titles.append(title.strip())

    return list(dict.fromkeys(titles))


def get_news(topic):
    query = f'"{topic}" when:7d'

    params = urllib.parse.urlencode({
        "q": query,
        "hl": "en-CA",
        "gl": "CA",
        "ceid": "CA:en"
    })

    url = "https://news.google.com/rss/search?" + params

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "BrowseBloomDraftBot/1.0"
        }
    )

    with urllib.request.urlopen(request, timeout=25) as response:
        xml_data = response.read()

    root = ET.fromstring(xml_data)

    results = []
    seen = set()

    cutoff = datetime.now(timezone.utc) - timedelta(
        days=MAX_AGE_DAYS
    )

    for item in root.findall("./channel/item"):
        headline = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        published = item.findtext("pubDate", "").strip()

        source_node = item.find("source")
        source = (
            source_node.text.strip()
            if source_node is not None and source_node.text
            else "News publisher"
        )

        if not headline or not link or not published:
            continue

        try:
            date = parsedate_to_datetime(published)

            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)

            if date.astimezone(timezone.utc) < cutoff:
                continue

            if date.astimezone(timezone.utc) > (
                datetime.now(timezone.utc)
                + timedelta(hours=1)
            ):
                continue
        except (TypeError, ValueError, OverflowError):
            continue

        headline_key = headline.casefold()

        if headline_key in seen:
            continue

        seen.add(headline_key)

        results.append({
            "headline": headline,
            "link": link,
            "source": source,
            "published": date.isoformat()
        })

        if len(results) >= MAX_SOURCES:
            break

    return results


def slugify(value):
    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        value.lower()
    ).strip("-")

    return slug[:65].strip("-") or "trending-topic"


def build_draft(topic, sources):
    safe_topic = html.escape(topic)
    title = f"Why Is {topic} Trending? Latest News and Sources"

    today = datetime.now(timezone.utc).strftime(
        "%B %d, %Y"
    )

    source_cards = []

    for source in sources:
        headline = html.escape(source["headline"])
        publisher = html.escape(source["source"])
        link = html.escape(
            source["link"],
            quote=True
        )

        published = datetime.fromisoformat(
            source["published"]
        ).strftime("%B %d, %Y")

        source_cards.append(f"""
        <article class="source-card">
          <div class="publisher">{publisher}</div>
          <h3>{headline}</h3>
          <p>Published: {published}</p>
          <a href="{link}"
             target="_blank"
             rel="noopener noreferrer">
             Read original coverage ↗
          </a>
        </article>
        """)

    cards_html = "\n".join(source_cards)

    description = html.escape(
        f"Explore recent news coverage about {topic}, "
        "with links to reporting from multiple publishers.",
        quote=True
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport"
      content="width=device-width, initial-scale=1">

<title>{html.escape(title)} | BrowseBloom</title>
<meta name="description" content="{description}">
<meta name="robots" content="noindex, nofollow">

<style>
* {{ box-sizing: border-box; }}

body {{
  margin: 0;
  background: #faf9f6;
  color: #202824;
  font-family: Arial, sans-serif;
  line-height: 1.7;
}}

header {{
  background: #183f31;
  padding: 18px 25px;
}}

header a {{
  color: white;
  text-decoration: none;
  font-family: Georgia, serif;
  font-size: 26px;
  font-weight: bold;
}}

main {{
  max-width: 850px;
  margin: auto;
  padding: 45px 22px;
}}

.label {{
  color: #245b45;
  text-transform: uppercase;
  font-size: 12px;
  font-weight: bold;
  letter-spacing: 1px;
}}

h1 {{
  font-family: Georgia, serif;
  font-size: clamp(32px, 5vw, 45px);
  line-height: 1.2;
}}

h2, h3 {{
  font-family: Georgia, serif;
}}

.intro {{
  color: #58665e;
  font-size: 17px;
}}

.notice {{
  background: #edf3ed;
  border-left: 4px solid #245b45;
  padding: 18px;
  margin: 25px 0;
}}

.source-card {{
  background: white;
  border: 1px solid #e5e8e3;
  border-radius: 9px;
  padding: 22px;
  margin: 15px 0;
}}

.source-card h3 {{
  font-size: 20px;
  margin: 8px 0;
}}

.source-card p {{
  color: #68736d;
  font-size: 13px;
}}

.source-card a {{
  color: #245b45;
  font-weight: bold;
}}

.publisher {{
  color: #245b45;
  font-size: 12px;
  text-transform: uppercase;
  font-weight: bold;
}}

footer {{
  margin-top: 45px;
  padding-top: 20px;
  border-top: 1px solid #ddd;
  color: #68736d;
  font-size: 13px;
}}
</style>
</head>

<body>

<header>
  <a href="../index.html">BrowseBloom.</a>
</header>

<main>
  <div class="label">Canada · Trending Topic</div>

  <h1>{html.escape(title)}</h1>

  <p class="intro">
    {safe_topic} is appearing among popular
    searches in Canada. Below is a collection
    of recent news headlines related to this
    topic, with links to their original coverage.
  </p>

  <p><strong>Draft prepared:</strong> {today} (UTC)</p>

  <div class="notice">
    <strong>Editorial review required.</strong>
    This is an automatically assembled research
    briefing, not a verified explanation of why
    the topic is trending. Headlines may discuss
    different developments. Read the original
    sources before writing or publishing a
    factual news article.
  </div>

  <h2>Latest Related Coverage</h2>

  {cards_html}

  <h2>What We Know So Far</h2>

  <p>
    Multiple recent reports mention
    <strong>{safe_topic}</strong>.
    These headlines provide starting points
    for research, but do not by themselves
    establish which event caused the
    increase in searches.
  </p>

  <h2>What Needs Verification?</h2>

  <p>
    Before publication, an editor should
    establish the main development, confirm
    dates and facts against the original
    reporting, and add useful context
    for Canadian readers.
  </p>

  <footer>
    BrowseBloom · Unpublished research draft
  </footer>

</main>
</body>
</html>
"""


def main():
    if not TRENDS_FILE.exists():
        raise SystemExit(
            "trends.json not found in repository root."
        )

    trends = read_trends()

    if not trends:
        raise SystemExit(
            "No readable trending topics in trends.json."
        )

    print(f"Found {len(trends)} trending topics.")

    selected_topic = None
    selected_sources = []

    for topic in trends[:MAX_TRENDS_TO_TRY]:
        print(f"Researching: {topic}")

        try:
            sources = get_news(topic)
        except Exception as error:
            print(f"Could not fetch news: {error}")
            continue

        print(f"Found {len(sources)} recent sources.")

        # Require at least two distinct publishers.
        publishers = {
            source["source"].casefold()
            for source in sources
        }

        if len(sources) >= 2 and len(publishers) >= 2:
            selected_topic = topic
            selected_sources = sources
            break

    if not selected_topic:
        raise SystemExit(
            "No topic had two recent sources from "
            "different publishers. No draft created."
        )

    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

    filename = (
        datetime.now(timezone.utc).strftime("%Y-%m-%d")
        + "-"
        + slugify(selected_topic)
        + ".html"
    )

    output = DRAFTS_DIR / filename

    content = build_draft(
        selected_topic,
        selected_sources
    )

    output.write_text(
        content,
        encoding="utf-8"
    )

    print(f"SUCCESS: Created {output.relative_to(ROOT)}")
    print(f"Topic: {selected_topic}")
    print(f"Sources: {len(selected_sources)}")
    print("Status: DRAFT ONLY - NOT PUBLISHED")


if __name__ == "__main__":
    main()
