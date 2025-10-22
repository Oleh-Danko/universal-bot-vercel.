import asyncio
import logging
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

log = logging.getLogger("live-parser")

# 10 джерел (з твого списку)
SOURCES = [
    ("Epravda (Finances)",  "https://www.epravda.com.ua/finances/"),
    ("Epravda (Columns)",   "https://www.epravda.com.ua/columns/"),
    ("Reuters (Business)",  "https://www.reuters.com/business/"),
    ("Reuters (Markets)",   "https://www.reuters.com/markets/"),
    ("Reuters (Tech)",      "https://www.reuters.com/technology/"),
    ("FT (Companies)",      "https://www.ft.com/companies"),
    ("FT (Technology)",     "https://www.ft.com/technology"),
    ("FT (Markets)",        "https://www.ft.com/markets"),
    ("FT (Opinion)",        "https://www.ft.com/opinion"),
    ("BBC (Business)",      "https://www.bbc.com/business"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

TIMEOUT = aiohttp.ClientTimeout(total=15)

def _abs_link(base: str, href: str) -> str:
    if not href:
        return ""
    return urljoin(base, href)

def _clean_items(items):
    """Прибираємо дублі, пусті, дуже короткі заголовки."""
    seen = set()
    out = []
    for it in items:
        key = (it["title"], it["link"])
        if not it["title"] or not it["link"]:
            continue
        if len(it["title"]) < 6:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def _pick_selectors(name: str):
    """
    Підібрані стійкі селектори для кожного сайту (максимально прості).
    Повертає список CSS-селекторів (в порядку спроб).
    """
    if name.startswith("Epravda"):
        # типові статті ЕП
        return [
            "article h3 a",           # основні картки
            ".article__title a",      # старі шаблони
            "a.article__link",        # інколи так
            "a[href^='https://www.epravda.com.ua/']"
        ]
    if name.startswith("Reuters"):
        return [
            "a[data-testid='Heading']",   # картки-тизери
            "article a[href^='/markets/']",
            "article a[href^='/business/']",
            "article a[href^='/technology/']",
            "a.story-card",               # fallback
            "a[href^='https://www.reuters.com/']"
        ]
    if name.startswith("FT"):
        return [
            "a[data-trackable='heading']",
            "a.js-teaser-heading-link",
            "a.o-teaser__heading",           # старий формат
            "a[href^='https://www.ft.com/']"
        ]
    if name.startswith("BBC"):
        return [
            "[data-testid='promo'] a[href]",
            "a[href^='/business-']",
            "a[href^='https://www.bbc.com/business']",
        ]
    # загальний резерв
    return ["article a[href]", "h3 a[href]", "a[href]"]

async def _fetch_one(session: aiohttp.ClientSession, name: str, url: str) -> list[dict]:
    items = []
    try:
        async with session.get(url, headers=HEADERS) as resp:
            html = await resp.text(errors="ignore")
    except Exception as e:
        log.warning("❌ %s: помилка запиту: %s", name, e)
        return items

    try:
        soup = BeautifulSoup(html, "html.parser")
        selectors = _pick_selectors(name)

        found = []
        for sel in selectors:
            found = soup.select(sel)
            if found:
                break

        for a in found[:400]:  # перестраховка від надмірного шуму
            href = a.get("href") or ""
            title = (a.get_text(" ", strip=True) or "").strip()
            link = _abs_link(url, href)
            if title and link.startswith(("http://", "https://")):
                items.append({"title": title, "link": link, "source": name})

        # якщо перший набір дав замало — спробуємо ще загально
        if len(items) < 20:
            for a in soup.find_all("a", href=True)[:800]:
                title = (a.get_text(" ", strip=True) or "").strip()
                link = _abs_link(url, a["href"])
                if title and link.startswith(("http://", "https://")):
                    items.append({"title": title, "link": link, "source": name})

    except Exception as e:
        log.warning("❌ %s: помилка парсингу: %s", name, e)

    items = _clean_items(items)
    log.info("✅ %s: зібрано %d", name, len(items))
    return items

async def fetch_all_sources() -> list[dict]:
    """
    Паралельно тягнемо всі 10 сторінок і зливаємо результати.
    Без кешу. Актуально на момент виклику.
    """
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        tasks = [asyncio.create_task(_fetch_one(session, name, url)) for name, url in SOURCES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items: list[dict] = []
    for res in results:
        if isinstance(res, list):
            all_items.extend(res)
        else:
            log.warning("Помилка джерела: %s", res)

    # загальне очищення + трішки сортування: джерело, потім довжина назви
    all_items = _clean_items(all_items)
    all_items.sort(key=lambda x: (x["source"], len(x["title"])))
    # ліміт зверху, щоб не зробити 10к рядків
    return all_items[:1200]

def chunk_messages(text: str, limit: int = 4000):
    """
    Ріже довгий текст на шматки ≤ limit, по рядках.
    """
    lines = text.splitlines(keepends=False)
    buf = ""
    for ln in lines:
        if len(buf) + len(ln) + 1 > limit:
            yield buf
            buf = ""
        buf += (ln + "\n")
    if buf.strip():
        yield buf