# live_parser.py
import asyncio
import re
from typing import List, Dict, Tuple
import aiohttp
from bs4 import BeautifulSoup

# --- Джерела (рівно ті, що ти вимагав) ---
SOURCES = {
    "Epravda (Finances)": "https://epravda.com.ua/finances",
    "Epravda (Columns)": "https://epravda.com.ua/columns",
    "Reuters (Business)": "https://www.reuters.com/business",
    "Reuters (Markets)": "https://www.reuters.com/markets",
    "Reuters (Technology)": "https://www.reuters.com/technology",
    "FT (Companies)": "https://www.ft.com/companies",
    "FT (Technology)": "https://www.ft.com/technology",
    "FT (Markets)": "https://www.ft.com/markets",
    "FT (Opinion)": "https://www.ft.com/opinion",
    "BBC (Business)": "https://www.bbc.com/business",
}

# --- Заголовки для обману антиботів і 401 у Reuters/FT/BBC ---
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,uk;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# --- Фільтри сміття у шляхах ---
BAD_PATH_PARTS = {
    "privacy", "cookies", "terms", "about", "contact", "help", "faq", "signup",
    "subscribe", "newsletters", "account", "advert", "advertising", "policy",
    "store", "shop", "sitemap", "index", "live", "video", "watch-live", "audio",
    "bbcverify", "weather", "sport", "travel", "culture", "reel", "innovation",
    "usingthebbc", "pages", "mediakit", "projects", "press-release", "aboutthebbc"
}
BAD_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico", ".css", ".js", ".mp3", ".mp4", ".mov", ".m3u8")

# --- Ключові слова у новинних URL, щоб лишилось саме «news» ---
GOOD_URL_HINTS = {
    "/news", "/article", "/story", "/stories", "/business", "/markets", "/technology",
    "/companies", "/opinion", "/economy", "/finance", "/finances", "/biznes", "/svit",
    "/power", "/publications", "/tehnologiji"
}

TITLE_MIN_LEN = 15    # щоб відсіяти «Home», «Europe», «Login», «About» тощо
TITLE_MAX_LEN = 220   # просто безпека, щоб не брати надто довгі заголовки
MAX_PER_SOURCE = 120  # максимум на джерело (щоб не завалювати чат)


def _is_bad_url(url: str) -> bool:
    if not url or url.startswith("#") or url.startswith("javascript:"):
        return True
    if any(url.endswith(ext) for ext in BAD_EXTS):
        return True
    low = url.lower()
    if any(part in low for part in BAD_PATH_PARTS):
        return True
    return False


def _looks_like_news_url(url: str) -> bool:
    low = url.lower()
    return any(hint in low for hint in GOOD_URL_HINTS)


def _clean_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    # прибираємо зайві крапки/дефіси в кінці
    s = re.sub(r"[–—\-•\·\|:\s]+$", "", s)
    return s


def _pick_description(a_tag, container) -> str:
    """Пробуємо знайти опис поруч: найближчий <p>, або summary-спан/див."""
    # 1) найближчий наступний <p>
    if container:
        p = container.find("p")
        if p:
            desc = _clean_text(p.get_text(" ", strip=True))
            if len(desc) >= 20:
                return desc
        # іноді summary у <div> або <span>
        for cand in container.find_all(["div", "span"], limit=4):
            text = _clean_text(cand.get_text(" ", strip=True))
            if len(text) >= 30 and len(text) <= 260:
                return text

    # 2) подивимось без контейнера — у батьківських елементах до 2 рівнів
    parent = a_tag.parent
    depth = 0
    while parent and depth < 2:
        p = parent.find("p")
        if p:
            desc = _clean_text(p.get_text(" ", strip=True))
            if len(desc) >= 20:
                return desc
        parent = parent.parent
        depth += 1
    return ""


def _collect_by_selectors(soup: BeautifulSoup, selectors: List[Tuple[str, str]]) -> List[Dict]:
    """Універсальний збір за CSS-селекторами: [(selector, source_name), ...] — але тут source_name не потрібен."""
    items = []
    seen = set()

    for sel, _ in selectors:
        for node in soup.select(sel):
            # шукаємо <a>
            a = node if node.name == "a" else node.find("a", href=True)
            if not a or not a.get("href"):
                continue

            url = a["href"]
            title = _clean_text(a.get_text(" ", strip=True))

            if not title or len(title) < TITLE_MIN_LEN or len(title) > TITLE_MAX_LEN:
                continue
            if _is_bad_url(url):
                continue

            # абсолютити часткові URL
            # (залишимо як є — у наших джерел зазвичай абсолютні посилання; якщо ні, браузер все одно зрозуміє)
            if not _looks_like_news_url(url):
                # якщо селектор уже "точний" (всередині статей), можна дозволити
                # але краще відсіяти, щоб не тягнути меню
                continue

            key = (title, url)
            if key in seen:
                continue
            seen.add(key)

            desc = _pick_description(a, node if node.name != "a" else a.parent)
            items.append({"title": title, "url": url, "desc": desc})

    return items


async def _fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    for _ in range(2):
        try:
            async with session.get(url, headers=DEFAULT_HEADERS, timeout=20) as r:
                if r.status == 200:
                    return await r.text()
                # інколи 401/403 — спробуємо вдруге
        except asyncio.TimeoutError:
            pass
        except Exception:
            pass
    return ""


# ---- Парсери під кожне джерело ----

def _sel_bbc() -> List[Tuple[str, str]]:
    # Беремо тільки блоки з новинами (те, що містить /news/ або /articles/)
    return [
        ('a[href*="/news/"]', "BBC"),
        ('a[href*="/articles/"]', "BBC"),
        ('article a[href*="/business/"]', "BBC"),
    ]

def _sel_reuters() -> List[Tuple[str, str]]:
    # MediaStoryCard / headings; суворо фільтруємо по /business|/markets|/technology
    return [
        ('article a[href*="/business/"]', "Reuters"),
        ('article a[href*="/markets/"]', "Reuters"),
        ('article a[href*="/technology/"]', "Reuters"),
        ('.media-story-card a[href*="/business/"]', "Reuters"),
        ('.media-story-card a[href*="/markets/"]', "Reuters"),
        ('.media-story-card a[href*="/technology/"]', "Reuters"),
    ]

def _sel_ft() -> List[Tuple[str, str]]:
    # FT: тізери з data-trackable=heading-link, та інші варіанти
    return [
        ('a[data-trackable="heading-link"]', "FT"),
        ('.o-teaser__heading a', "FT"),
        ('.o-teaser a', "FT"),
    ]

def _sel_epravda() -> List[Tuple[str, str]]:
    # EP: блоки статей на сторінках /finances і /columns
    return [
        ('article a[href*="/finances/"]', "EP"),
        ('article a[href*="/biznes/"]', "EP"),
        ('article a[href*="/power/"]', "EP"),
        ('article a[href*="/tehnologiji/"]', "EP"),
        ('.article a[href*="/finances/"]', "EP"),
        ('.article a[href*="/columns/"]', "EP"),
        ('a[href*="/finances/"]', "EP"),
        ('a[href*="/columns/"]', "EP"),
    ]


async def parse_one(session: aiohttp.ClientSession, name: str, url: str) -> Tuple[str, List[Dict]]:
    html = await _fetch_html(session, url)
    if not html:
        return name, []

    soup = BeautifulSoup(html, "html.parser")

    # вибір селекторів під джерело
    if "BBC" in name:
        selectors = _sel_bbc()
    elif "Reuters" in name:
        selectors = _sel_reuters()
    elif "FT" in name:
        selectors = _sel_ft()
    elif "Epravda" in name:
        selectors = _sel_epravda()
    else:
        selectors = [('article a', name), ('h2 a', name), ('h3 a', name)]

    items = _collect_by_selectors(soup, selectors)

    # додатковий фільтр (без меню/футера)
    cleaned = []
    seen = set()
    for it in items:
        title = it["title"]
        url_i = it["url"]
        if _is_bad_url(url_i):
            continue
        if len(title) < TITLE_MIN_LEN:
            continue
        if not _looks_like_news_url(url_i):
            continue

        key = (title, url_i)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(it)

        if len(cleaned) >= MAX_PER_SOURCE:
            break

    return name, cleaned


async def fetch_live_grouped() -> List[Tuple[str, List[Dict]]]:
    """Повертає [(назва_джерела, [{title,url,desc}, ...]), ...]"""
    async with aiohttp.ClientSession() as session:
        tasks = [parse_one(session, name, url) for name, url in SOURCES.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    grouped: List[Tuple[str, List[Dict]]] = []
    for i, res in enumerate(results):
        name = list(SOURCES.keys())[i]
        if isinstance(res, Exception):
            grouped.append((name, []))
        else:
            grouped.append(res)
    return grouped


def format_grouped_to_chunks(grouped: List[Tuple[str, List[Dict]]], max_chunk_len: int = 3500) -> List[str]:
    """Формуємо список текстових повідомлень ≤ max_chunk_len, згруповано по джерелах.
       Формат рядка: • Заголовок — опис (URL)"""
    chunks: List[str] = []
    buf = "📰 Актуальні новини (живий парсинг)\n"
    for source_name, items in grouped:
        # пропускаємо порожні джерела
        if not items:
            continue
        block_header = f"\n\n<b>{source_name}</b>\n"
        if len(buf) + len(block_header) > max_chunk_len:
            chunks.append(buf)
            buf = block_header
        else:
            buf += block_header

        for it in items:
            title = _clean_text(it["title"])
            desc = _clean_text(it.get("desc", ""))
            url = it["url"]

            line = f"• {title}"
            if desc and len(desc) >= 20:
                # короткий опис
                line += f" — {desc}"
            line += f" ({url})\n"

            if len(buf) + len(line) > max_chunk_len:
                chunks.append(buf)
                buf = line
            else:
                buf += line

    if buf.strip():
        chunks.append(buf)

    # Якщо взагалі нічого
    if not chunks:
        chunks = ["⚠️ Не вдалося знайти новини. Спробуй ще раз трохи пізніше."]

    return chunks