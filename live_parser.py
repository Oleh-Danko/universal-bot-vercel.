# live_parser.py
import re
import asyncio
import logging
from typing import List, Dict, Tuple
import aiohttp
from bs4 import BeautifulSoup

log = logging.getLogger("live-parser")

# ---------- Налаштування ----------
TIMEOUT = aiohttp.ClientTimeout(total=20)
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,uk;q=0.8"}

MAX_PER_SOURCE = 60  # скільки максимум лінків брати з одного сайту

# ---------- Утиліти фільтрації ----------
BAD_WORDS = {
    "privacy", "cookies", "terms", "contact", "about", "help",
    "subscribe", "newsletter", "signin", "login", "account",
    "advertise", "mediakit", "faq", "jobs", "careers", "events",
    "podcast", "video", "watch-live", "play", "bbc.com/usingthebbc",
    "editorialguidelines", "bbc.co.uk/accessibility", "store", "shop"
}

def looks_like_nav(title: str) -> bool:
    t = title.strip().lower()
    if len(t) < 8:  # “Home”, “More”, “News”
        return True
    # короткі рубрики/розділи без контексту
    if t in {"home", "news", "business", "markets", "opinion", "technology",
             "world", "europe", "africa", "asia", "sport"}:
        return True
    return False

def link_has_bad_words(href: str) -> bool:
    h = href.lower()
    return any(bad in h for bad in BAD_WORDS)

def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()

def accept_len(title: str) -> bool:
    # уникаємо меню типу “Europe”, “Contact us”
    t = title.strip()
    return len(t) >= 15  # ти просив >5-10 символів; ставлю трішки вище, щоб відсіяти сміття

# ---------- Список джерел (URL -> назва для виводу) ----------
SOURCES: List[Tuple[str, str]] = [
    ("https://www.bbc.com/business", "BBC (Business)"),

    ("https://www.reuters.com/business", "Reuters (Business)"),
    ("https://www.reuters.com/markets", "Reuters (Markets)"),
    ("https://www.reuters.com/technology", "Reuters (Technology)"),

    ("https://www.ft.com/companies", "FT (Companies)"),
    ("https://www.ft.com/markets", "FT (Markets)"),
    ("https://www.ft.com/technology", "FT (Technology)"),
    ("https://www.ft.com/opinion", "FT (Opinion)"),

    ("https://epravda.com.ua/finances", "Epravda (Finances)"),
    ("https://epravda.com.ua/columns",  "Epravda (Columns)"),
]

# ---------- Парсери по сайтах ----------
async def fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    try:
        async with session.get(url, headers=HEADERS) as r:
            if r.status != 200:
                raise aiohttp.ClientResponseError(
                    r.request_info, r.history, status=r.status, message="bad status", headers=r.headers
                )
            return await r.text()
    except Exception as e:
        log.warning(f"Fetch failed {url}: {e}")
        return ""

# BBC: беремо тільки справжні статті (мають шаблон /news/articles/...)
def parse_bbc(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = clean_text(a.get_text())
        if not href or not title:
            continue
        if href.startswith("/"):
            href = "https://www.bbc.com" + href
        # тільки сторінки-статті
        if "bbc.com/news/articles/" not in href:
            continue
        if looks_like_nav(title) or link_has_bad_words(href) or not accept_len(title):
            continue

        # опис (саблайн) поруч/всередині картки
        desc = None
        card = a.find_parent(["div", "article", "li"])
        if card:
            p = card.find("p")
            if p:
                desc = clean_text(p.get_text())

        out.append({"title": title, "link": href, "desc": desc})
        if len(out) >= MAX_PER_SOURCE:
            break
    return out

# Reuters: часто 401/403 без UA або з GEO; беремо тільки новини з /business|/markets|/technology/ та
# посилання з явними ідентифікаторами (idUS..., /article/)
def parse_reuters(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = clean_text(a.get_text())
        if not href or not title:
            continue
        if href.startswith("/"):
            href = "https://www.reuters.com" + href
        h = href.lower()
        if not ("reuters.com" in h and (
            "/business/" in h or "/markets/" in h or "/technology/" in h
        )):
            continue
        # намагаємося залишати саме матеріали
        if not ("/id" in h or "/article/" in h or re.search(r"/\d{4}/\d{2}/\d{2}/", h)):
            continue
        if looks_like_nav(title) or link_has_bad_words(href) or not accept_len(title):
            continue

        desc = None
        card = a.find_parent(["div", "article", "li"])
        if card:
            p = card.find("p")
            if p:
                desc = clean_text(p.get_text())

        out.append({"title": title, "link": href, "desc": desc})
        if len(out) >= MAX_PER_SOURCE:
            break
    return out

# FT: беремо промо-статті /content/<uuid>
def parse_ft(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = clean_text(a.get_text())
        if not href or not title:
            continue
        if href.startswith("/"):
            href = "https://www.ft.com" + href
        if "ft.com/content/" not in href:
            continue
        if looks_like_nav(title) or link_has_bad_words(href) or not accept_len(title):
            continue

        desc = None
        card = a.find_parent(["div", "article", "li"])
        if card:
            # FT часто кладе опис у <p> або <span> поруч
            p = card.find("p")
            if p:
                desc = clean_text(p.get_text())

        out.append({"title": title, "link": href, "desc": desc})
        if len(out) >= MAX_PER_SOURCE:
            break
    return out

# Epravda: залишаємо тільки матеріали (не розділи/меню).
# Для finances — лишаємо посилання з /finances/... (а не /about/, /projects/ тощо).
# Для columns — лишаємо посилання з /biznes|/svit|/power|/tehnologiji|/finances/ ДЕ Є СТАТТЯ.
EP_BAD_PARTS = {
    "/about/", "/rules/", "/projects/", "/mediakit/", "/press-release/",
    "/projects/", "/publications/", "/interview/", "/projects/",
    "/weeklycharts/", "/land/", "/projects/", "/club.", "privacy-policy"
}

def _is_epravda_article(href: str, page: str) -> bool:
    # Жорсткі обмеження, щоб не захоплювати “Новини”, “Про проект”, “Підтримати”, тощо
    h = href.lower()
    if not h.startswith("https://epravda.com.ua/"):
        return False
    if any(b in h for b in EP_BAD_PARTS):
        return False
    if page.endswith("/finances"):
        # беремо фінансові матеріали/новини
        return "/finances/" in h
    if page.endswith("/columns"):
        # колонки зазвичай мають рубрики в шляху: /biznes/, /power/, /tehnologiji/, /svit/ тощо + ID в кінці
        return bool(re.search(r"/(biznes|power|tehnologiji|svit|finances)/", h)) and re.search(r"-\d+/?$", h)
    return False

def parse_epravda(html: str, page_url: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: List[Dict] = []
    # Основні заголовки зазвичай у h2/h3 з <a>
    for h in soup.find_all(["h2", "h3", "h4"]):
        a = h.find("a", href=True)
        if not a:
            continue
        href = a["href"]
        title = clean_text(a.get_text())
        if not href or not title:
            continue
        if href.startswith("/"):
            href = "https://epravda.com.ua" + href
        if not _is_epravda_article(href, page_url):
            continue
        if looks_like_nav(title) or link_has_bad_words(href) or not accept_len(title):
            continue

        # опис поруч (якщо є)
        desc = None
        parent = h.parent
        if parent:
            p = parent.find("p")
            if p:
                desc = clean_text(p.get_text())

        out.append({"title": title, "link": href, "desc": desc})
        if len(out) >= MAX_PER_SOURCE:
            break

    # Фолбек: інколи заголовки просто як <a> в картках
    if not out:
        for a in soup.find_all("a", href=True):
            href = a["href"]
            title = clean_text(a.get_text())
            if not href or not title:
                continue
            if href.startswith("/"):
                href = "https://epravda.com.ua" + href
            if not _is_epravda_article(href, page_url):
                continue
            if looks_like_nav(title) or link_has_bad_words(href) or not accept_len(title):
                continue
            desc = None
            card = a.find_parent(["article", "div", "li"])
            if card:
                p = card.find("p")
                if p:
                    desc = clean_text(p.get_text())
            out.append({"title": title, "link": href, "desc": desc})
            if len(out) >= MAX_PER_SOURCE:
                break

    return out

# ---------- Диспетчер по джерелах ----------
async def fetch_source(session: aiohttp.ClientSession, url: str, name: str) -> Tuple[str, List[Dict]]:
    html = await fetch_html(session, url)
    items: List[Dict] = []
    try:
        if not html:
            return name, []

        if name.startswith("BBC"):
            items = parse_bbc(html)
        elif name.startswith("Reuters"):
            items = parse_reuters(html)
        elif name.startswith("FT"):
            items = parse_ft(html)
        elif name.startswith("Epravda"):
            items = parse_epravda(html, url)
        else:
            items = []
    except Exception as e:
        log.warning(f"Parse failed {name}: {e}")
        items = []

    return name, items

async def fetch_all_sources_grouped() -> Dict[str, List[Dict]]:
    grouped: Dict[str, List[Dict]] = {name: [] for _, name in SOURCES}
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        tasks = [fetch_source(session, url, name) for url, name in SOURCES]
        for coro in asyncio.as_completed(tasks):
            name, items = await coro
            grouped[name] = items
    return grouped