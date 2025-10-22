import asyncio
import re
from typing import List, Dict
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en,uk;q=0.8,ru;q=0.7",
}

SOURCES = [
    # Економічна Правда
    ("ЕП • Finances", "https://epravda.com.ua/finances"),
    ("ЕП • Columns",  "https://epravda.com.ua/columns"),
    # Reuters
    ("Reuters • Business",   "https://www.reuters.com/business"),
    ("Reuters • Markets",    "https://www.reuters.com/markets"),
    ("Reuters • Technology", "https://www.reuters.com/technology"),
    # Financial Times
    ("FT • Companies",  "https://www.ft.com/companies"),
    ("FT • Technology", "https://www.ft.com/technology"),
    ("FT • Markets",    "https://www.ft.com/markets"),
    ("FT • Opinion",    "https://www.ft.com/opinion"),
    # BBC
    ("BBC • Business",  "https://www.bbc.com/business"),
]

ABSOLUTE_START = (
    "http://", "https://"
)

def _clean_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    # зрізаємо занадто довгі хвости
    return s[:300]

def _is_probably_article(title: str) -> bool:
    """Відсікаємо сміття за довжиною та змістом."""
    if not title: 
        return False
    t = title.strip()
    if len(t) < 20:
        return False
    # Приберемо очевидну навігацію
    junk = ["Sign in", "Subscribe", "Cookies", "Privacy", "Terms", "Read more"]
    return not any(j in t for j in junk)

async def _fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as r:
        r.raise_for_status()
        return await r.text(errors="ignore")

def _extract_epravda(base_url: str, html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    # типові заголовки: h2/h3 з <a>
    for h in soup.select("h1 a, h2 a, h3 a, article a"):
        href = h.get("href") or ""
        title = _clean_text(h.get_text(" ", strip=True))
        if not href or not title:
            continue
        if not href.startswith(ABSOLUTE_START):
            href = urljoin(base_url, href)
        if "epravda.com.ua" not in href:
            continue
        if _is_probably_article(title):
            items.append({"title": title, "link": href, "source": "Економічна Правда"})
    return items

def _extract_reuters(base_url: str, html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    # Reuters часто використовує h2/h3 з <a> і data-testid
    for a in soup.select('a[data-testid*="Heading"], h2 a, h3 a'):
        href = a.get("href") or ""
        title = _clean_text(a.get_text(" ", strip=True))
        if not href or not title:
            continue
        if not href.startswith(ABSOLUTE_START):
            href = urljoin("https://www.reuters.com", href)
        if "reuters.com" not in href:
            continue
        if _is_probably_article(title):
            items.append({"title": title, "link": href, "source": "Reuters"})
    return items

def _extract_ft(base_url: str, html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    # FT віддає посилання у <a> з ft.com у href; беремо h2/h3 і посилання з карточок
    for a in soup.select("h2 a, h3 a, a[href*='ft.com/content/'], a.o-teaser__heading-link"):
        href = a.get("href") or ""
        title = _clean_text(a.get_text(" ", strip=True))
        if not href or not title:
            continue
        if not href.startswith(ABSOLUTE_START):
            href = urljoin("https://www.ft.com", href)
        if "ft.com" not in href:
            continue
        if _is_probably_article(title):
            items.append({"title": title, "link": href, "source": "Financial Times"})
    return items

def _extract_bbc(base_url: str, html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    # BBC: багато <a> з абсолютними href і нормальним текстом
    for a in soup.select("a[href*='bbc.com']"):
        href = a.get("href") or ""
        title = _clean_text(a.get_text(" ", strip=True))
        if not href or not title:
            continue
        if not href.startswith(ABSOLUTE_START):
            href = urljoin("https://www.bbc.com", href)
        if "bbc.com" not in href:
            continue
        if _is_probably_article(title):
            items.append({"title": title, "link": href, "source": "BBC"})
    return items

def _extract_by_host(source_name: str, url: str, html: str) -> List[Dict]:
    if "epravda.com.ua" in url:
        return _extract_epravda(url, html)
    if "reuters.com" in url:
        return _extract_reuters(url, html)
    if "ft.com" in url:
        return _extract_ft(url, html)
    if "bbc.com" in url:
        return _extract_bbc(url, html)
    return []

async def _parse_one(session: aiohttp.ClientSession, source_title: str, url: str) -> List[Dict]:
    try:
        html = await _fetch_html(session, url)
        items = _extract_by_host(source_title, url, html)
        # підміняємо source як у списку джерел (більше контексту)
        for it in items:
            it["source"] = source_title
        return items
    except Exception:
        return []

async def collect_all_news() -> List[Dict]:
    """
    Парсить ВСІ джерела одночасно та повертає унікальний список статей.
    """
    timeout = aiohttp.ClientTimeout(total=25)
    connector = aiohttp.TCPConnector(limit=10, ssl=False)
    async with aiohttp.ClientSession(timeout=timeout, connector=connector, headers=HEADERS) as session:
        tasks = [
            _parse_one(session, title, url)
            for (title, url) in SOURCES
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    all_items: List[Dict] = []
    seen = set()
    for lst in results:
        for it in lst:
            key = it["link"].split("?")[0]
            if key in seen:
                continue
            seen.add(key)
            all_items.append(it)

    return all_items