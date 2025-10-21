import re
import asyncio
import logging
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

log = logging.getLogger("html-parser")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,uk;q=0.8"
}

SOURCES = [
    ("Економічна Правда — Finances",  "https://epravda.com.ua/finances"),
    ("Економічна Правда — Columns",   "https://epravda.com.ua/columns"),
    ("Reuters — Business",            "https://www.reuters.com/business"),
    ("Reuters — Markets",             "https://www.reuters.com/markets"),
    ("Reuters — Technology",          "https://www.reuters.com/technology"),
    ("Financial Times — Companies",   "https://www.ft.com/companies"),
    ("Financial Times — Technology",  "https://www.ft.com/technology"),
    ("Financial Times — Markets",     "https://www.ft.com/markets"),
    ("Financial Times — Opinion",     "https://www.ft.com/opinion"),
    ("BBC — Business",                "https://www.bbc.com/business"),
]

ABS_URL_RE = re.compile(r"^https?://", re.I)

def _abs(base: str, href: str) -> str:
    if not href:
        return ""
    href = href.strip()
    if ABS_URL_RE.match(href):
        return href
    return urljoin(base, href)

def _clean_title(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()

def _looks_like_article_link(href: str) -> bool:
    if not href:
        return False
    # відсіюємо сміття/навігацію
    bad = ("/video", "/live", "/signup", "/login", "#", "mailto:", "javascript:")
    return not any(b in href for b in bad)

async def _fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status != 200:
                log.warning("GET %s -> %s", url, r.status)
                return ""
            return await r.text()
    except Exception as e:
        log.warning("Fetch failed %s: %s", url, e)
        return ""

def _extract_generic(soup: BeautifulSoup, base: str, domain_hint: str = "") -> list[dict]:
    """
    Дуже термостійкий збір усіх 'a' з осмисленим текстом.
    Далі вже фільтруємо хардкодом по доменах, якщо треба.
    """
    items = []
    seen = set()
    for a in soup.find_all("a", href=True):
        title = _clean_title(a.get_text(" ", strip=True))
        if not title or len(title) < 5:
            continue
        href = _abs(base, a["href"])
        if not _looks_like_article_link(href):
            continue
        key = (title, href)
        if key in seen:
            continue
        # додаткові доменні підказки, щоб уникати зайвого
        if domain_hint and domain_hint not in urlparse(href).netloc:
            continue
        items.append({"title": title, "link": href})
        seen.add(key)
    return items

def _filter_domain_specific(source_name: str, url: str, items: list[dict]) -> list[dict]:
    """ Трохи чистимо зайві посилання для кожного сайту. """
    netloc = urlparse(url).netloc

    def keep_reuters(href: str) -> bool:
        # Реальні матеріали — під /business /markets /technology /world тощо, без розділів типу /signup
        return bool(re.match(r"^https?://(www\.)?reuters\.com/.+", href))

    def keep_ft(href: str) -> bool:
        # Заголовки FT мають вигляд https://www.ft.com/content/<uuid> або розділи /companies /technology /markets /opinion
        return ("ft.com" in href) and ("/content/" in href or any(seg in href for seg in ("/companies", "/technology", "/markets", "/opinion")))

    def keep_bbc(href: str) -> bool:
        return ("bbc.com" in href) and not any(x in href for x in ["/live", "/sounds", "/iplayer"])

    def keep_epravda(href: str) -> bool:
        return ("epravda.com.ua" in href) and not any(x in href for x in ["/rss", "/video", "/ads"])

    kept = []
    for it in items:
        href = it["link"]
        ok = True
        if "reuters.com" in netloc:
            ok = keep_reuters(href)
        elif "ft.com" in netloc:
            ok = keep_ft(href)
        elif "bbc.com" in netloc:
            ok = keep_bbc(href)
        elif "epravda.com.ua" in netloc:
            ok = keep_epravda(href)

        if ok:
            kept.append(it)

    # легка дедуплікація по посиланню
    dedup, seen = [], set()
    for it in kept:
        if it["link"] not in seen:
            dedup.append(it)
            seen.add(it["link"])
    return dedup

async def _scrape_source(session: aiohttp.ClientSession, source_name: str, url: str) -> list[dict]:
    html = await _fetch_html(session, url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")

    # Основний універсальний збір
    domain = urlparse(url).netloc
    items = _extract_generic(soup, base=url, domain_hint=domain)

    # Додатково: спроба зчитати <meta property="og:title"> на випадок "великої" статті
    meta_title = soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"name":"og:title"})
    meta_url   = soup.find("meta", attrs={"property": "og:url"}) or soup.find("meta", attrs={"name":"og:url"})
    if meta_title and meta_url:
        t = _clean_title(meta_title.get("content", ""))
        u = meta_url.get("content", "")
        if t and u:
            items.append({"title": t, "link": u})

    # Фільтр під домен
    items = _filter_domain_specific(source_name, url, items)

    # Додати поле source
    for it in items:
        it["source"] = source_name

    log.info("Parsed %s -> %d items", source_name, len(items))
    return items

async def fetch_all_sources() -> list[dict]:
    """
    Тягнемо ВСІ 10 джерел, паралельно, з обмеженням на кількість одночасних з'єднань.
    """
    timeout = aiohttp.ClientTimeout(total=25)
    connector = aiohttp.TCPConnector(limit=10, ssl=False)
    sem = asyncio.Semaphore(6)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector, headers=HEADERS) as session:
        async def wrap(name, url):
            async with sem:
                try:
                    return await _scrape_source(session, name, url)
                except Exception as e:
                    log.warning("Source failed %s: %s", name, e)
                    return []

        tasks = [wrap(name, url) for name, url in SOURCES]
        results = await asyncio.gather(*tasks, return_exceptions=False)

    # плаский список
    flat = [item for sub in results for item in sub]

    # фінальна дедуплікація за (title, link)
    seen = set()
    unique = []
    for it in flat:
        key = (it["title"], it["link"])
        if key in seen:
            continue
        unique.append(it)
        seen.add(key)

    # обмеження зверху НЕ ставимо (мета — 300+), але порядок збережемо
    return unique