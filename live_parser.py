import re
import asyncio
from typing import List, Dict
import logging

import aiohttp
from bs4 import BeautifulSoup

log = logging.getLogger("news-bot.parser")

EP_FINANCES_URL = "https://epravda.com.ua/finances/"

# Патерн «нормальної» статті Epravda:
# .../finances/slug-813123/
ARTICLE_LINK_RE = re.compile(r"/finances/[^/]*-\d{5,}/?$")

# Фільтр навігації/рубрики/проєкти — їх відсіємо
BLACKLIST_PARTS = (
    "/about",
    "/rules",
    "/projects/",
    "/press-release",
    "/publications/",
    "/columns/",
    "/weeklycharts",
    "/land/",
    "/news/",  # на /finances/ буває лінк на сторінку розділу NEWS — відсіюємо
    "/interview/",
    "/privacy-policy",
    "/mediakit",
    "/about/",
    "/projects/",
)


def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _looks_like_article_href(href: str) -> bool:
    if not href or not href.startswith("http"):
        return False
    # тільки домен epravda
    if "epravda.com.ua" not in href:
        return False
    # чорний список
    if any(x in href for x in BLACKLIST_PARTS):
        return False
    # повинен збігатися з патерном статті
    return bool(ARTICLE_LINK_RE.search(href))


async def _fetch_html(session: aiohttp.ClientSession, url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    async with session.get(url, headers=headers, timeout=20) as resp:
        resp.raise_for_status()
        return await resp.text()


def _extract_desc(block) -> str:
    """
    Шукаємо короткий опис/підзаголовок біля заголовку:
    - <p> всередині блоку
    - елементи з класами '*summary*', '*lead*', 'post_item_*'
    - сусідні <div> з текстом
    """
    # варіант 1: явний підзаголовок
    for sel in ["p", "div", "span"]:
        tag = block.find(sel)
        if tag:
            text = _clean_text(tag.get_text(" ", strip=True))
            if text and len(text) > 25:
                return text

    # варіант 2: подивитися братні елементи
    sib = block.find_next_sibling()
    if sib:
        text = _clean_text(sib.get_text(" ", strip=True))
        if text and len(text) > 25:
            return text

    return ""


def _parse_finances_list(html: str) -> List[Dict]:
    soup = BeautifulSoup(html, "html.parser")

    # Основні контейнери, де зазвичай лежать картки/пости
    containers = []
    possible = [
        ("section", {"id": "main-content"}),
        ("section", {"class": re.compile(r"(list|feed|articles|content)", re.I)}),
        ("div", {"class": re.compile(r"(post|article|list|feed)", re.I)}),
        ("main", {}),
    ]
    for name, attrs in possible:
        found = soup.find(name, attrs=attrs)
        if found:
            containers.append(found)
    if not containers:
        containers = [soup]  # фолбек — шукаємо по всій сторінці

    results: List[Dict] = []
    seen = set()

    # Стратегія:
    # 1) картки статей (article|div) зі всередині — шукаємо заголовкові <a> з href на статтю
    # 2) фолбек — знайти всі <a> з підходящим href по контейнеру
    for root in containers:
        # 1) картки
        for card in root.find_all(["article", "div", "li"], recursive=True):
            a = card.find("a", href=True)
            if not a:
                continue
            href = a["href"]
            if href.startswith("//"):
                href = "https:" + href
            if href.startswith("/"):
                href = "https://epravda.com.ua" + href

            if not _looks_like_article_href(href):
                continue

            title = _clean_text(a.get_text(" ", strip=True))
            # іноді <a><h3>Заголовок</h3></a>
            if not title:
                h = a.find(["h2", "h3", "h4"])
                if h:
                    title = _clean_text(h.get_text(" ", strip=True))

            if not title or len(title) < 8:
                continue

            if href in seen:
                continue
            seen.add(href)

            desc = _extract_desc(card)
            results.append({
                "title": title,
                "link": href,
                "source": "Epravda (Finances)",
                "desc": desc
            })

        # 2) фолбек — усі <a> у контейнері
        for a in root.find_all("a", href=True):
            href = a["href"]
            if href.startswith("//"):
                href = "https:" + href
            if href.startswith("/"):
                href = "https://epravda.com.ua" + href
            if not _looks_like_article_href(href):
                continue

            if href in seen:
                continue

            title = _clean_text(a.get_text(" ", strip=True))
            if not title or len(title) < 8:
                # спроба взяти з дочірніх h2/h3
                h = a.find(["h2", "h3", "h4"])
                if h:
                    title = _clean_text(h.get_text(" ", strip=True))
            if not title or len(title) < 8:
                continue

            # спроба дістати опис з батьківського блоку
            desc = ""
            parent = a.parent
            if parent:
                desc = _extract_desc(parent)

            seen.add(href)
            results.append({
                "title": title,
                "link": href,
                "source": "Epravda (Finances)",
                "desc": desc
            })

    # Легка нормалізація/фільтрація:
    # — викидаємо підозріло короткі заголовки
    filtered = []
    for it in results:
        t = it["title"]
        if len(t) < 8:
            continue
        filtered.append(it)

    # Унікалізуємо ще раз на всяк випадок (за link)
    uniq = []
    seen_links = set()
    for it in filtered:
        if it["link"] in seen_links:
            continue
        seen_links.add(it["link"])
        uniq.append(it)

    # Сортуємо за появою на сторінці (перші зверху)
    return uniq


async def fetch_epravda_finances() -> List[Dict]:
    """
    Повертає список новин виключно з https://epravda.com.ua/finances/
    Кожен елемент: {title, link, source, desc}
    """
    timeout = aiohttp.ClientTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        try:
            html = await _fetch_html(session, EP_FINANCES_URL)
        except Exception as e:
            log.warning("Fetch epravda finances failed: %s", e)
            return []
        return _parse_finances_list(html)


# ===== нижче інші джерела — ВИМКНЕНО (залишені як коментар-шаблон) =====
# async def fetch_bloomberg_latest(): ...
# async def fetch_reuters_business(): ...
# async def fetch_ft_companies(): ...
# і т.д.