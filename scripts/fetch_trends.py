import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

URL = 'https://trends.google.com/trending/rss?geo=CA'
OUT = Path('trends.json')
request = urllib.request.Request(URL, headers={'User-Agent': 'BrowseBloomTrendCollector/1.0 (+https://browsebloom.online/)'})
try:
    with urllib.request.urlopen(request, timeout=25) as response:
        xml = response.read()
    root = ET.fromstring(xml)
    items = []
    for item in root.findall('./channel/item')[:25]:
        title = (item.findtext('title') or '').strip()
        link = (item.findtext('link') or '').strip()
        published = (item.findtext('pubDate') or '').strip()
        if title:
            items.append({'topic': title, 'google_trends_url': link, 'published': published})
    if not items:
        raise ValueError('No trending topics found in RSS response')
    OUT.write_text(json.dumps({'region': 'CA', 'updated_at': datetime.now(timezone.utc).isoformat(), 'topics': items}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Saved {len(items)} topics')
except Exception as error:
    print(f'Trend fetch failed; existing data preserved: {error}')
    raise
