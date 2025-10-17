# bloomberg_parser.py
import logging
from typing import List, Dict
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

LOG = logging.getLogger("bloomberg_parser")
LOG.setLevel(logging.INFO)

BLOOMBERG_BASE = "[https://www.bloomberg.com](https://www.bloomberg.com)"
BLOOMBERG_URL = "[https://www.bloomberg.com/](https://www.bloomberg.com/)"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "[https://www.google.com/](https://www.google.com/)",
}

def _norm_link(href: str) -> str:
    if not href:
        return ""
    href = href.strip()
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return urljoin(BLOOMBERG_BASE, href)
    return href

def fetch_bloomberg_news() -> List[Dict[str, str]]:
    """
    Синхронний blocking парсер — повертає list[{"title","link"}, ...] (макс 10)
    Використовуй його з asyncio.to_thread або loop.run_in_executor у боті.
    """
    try:
        # 1. Запит до сайту
        resp = requests.get(BLOOMBERG_URL, headers=HEADERS, timeout=12)
        resp.raise_for_status()
    except Exception as e:
        LOG.exception("HTTP error fetching Bloomberg: %s", e)
        return []

    html_content = resp.text
    soup = BeautifulSoup(html_content, "html.parser")

    candidates = []
    seen = set()

    # 2. Евристики для пошуку новин (фокусуємося на заголовках та посиланнях)
    for article in soup.find_all("article"):
        for tag_name in ("h1", "h2", "h3"):
            t = article.find(tag_name)
            if t:
                title = t.get_text(strip=True)
                a = article.find("a", href=True)
                link = a["href"] if a else ""
                link = _norm_link(link)
                if title and title.lower() not in seen:
                    seen.add(title.lower())
                    candidates.append({"title": title, "link": link})
                if len(candidates) >= 10:
                    return candidates[:10]

    # 3. Додатковий пошук по посиланнях, що містять ключові слова
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if not text or len(text) < 6:
            continue
        lowhref = href.lower()
        if any(x in lowhref for x in ("/news/", "/markets", "/articles/")):
            link = _norm_link(href)
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            candidates.append({"title": text, "link": link})
            if len(candidates) >= 10:
                return candidates[:10]

    # 4. Фінальна дедуплікація та повернення до 10 елементів
    out = []
    added = set()
    for c in candidates:
        t = c.get("title", "").strip()
        l = c.get("link", "").strip()
        if not t:
            continue
        key = t.lower()
        if key in added:
            continue
        added.add(key)
        out.append({"title": t, "link": l})
        if len(out) >= 10:
            break

    return out