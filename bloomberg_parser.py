"""
bloomberg_parser.py
Адаптивний парсер заголовків Bloomberg:
- Playwright (рендер DOM) -> основний шлях
- cloudscraper -> fallback (швидше, якщо сторінка простіша)
Повертає list[dict] формату: [{"title": "...", "url": "..."}, ...]
"""

import os
import asyncio
import logging
from typing import List, Dict, Optional

from bs4 import BeautifulSoup

# optional imports (lazy)
try:
    import cloudscraper
except Exception:
    cloudscraper = None

try:
    from playwright.async_api import async_playwright
except Exception:
    async_playwright = None

LOG = logging.getLogger("bloomberg_parser")
logging.basicConfig(level=logging.INFO)

BLOOMBERG_URL = "https://www.bloomberg.com/"

# strings to ignore
IGNORE_TEXTS = {"More from this issue:", "More from this issue", "Read more", "Subscribe"}


async def _fetch_with_playwright(url: str, timeout: int = 60000) -> Optional[str]:
    """Рендер через Playwright — повертає HTML або None."""
    if not async_playwright:
        LOG.info("Playwright не встановлено — пропускаємо.")
        return None

    LOG.info("🔎 Playwright: намагаємось отримати рендерований HTML...")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="en-US",
            )
            page = await context.new_page()
            await page.goto(url, timeout=timeout)
            # дочекаємось мережевої активності
            try:
                await page.wait_for_load_state("networkidle", timeout=timeout)
            except Exception:
                # іноді networkidle може не спрацювати — все одно беремо content
                LOG.debug("Playwright: networkidle таймаут, продовжуємо")
            html = await page.content()
            await browser.close()
            LOG.info("✅ Playwright: HTML отримано")
            return html
    except Exception as e:
        LOG.error(f"Playwright error: {e}", exc_info=True)
        return None


def _fetch_with_cloudscraper(url: str, timeout: int = 15) -> Optional[str]:
    """Синхронний fetch через cloudscraper як кешований/швидкий варіант."""
    if not cloudscraper:
        LOG.info("cloudscraper не встановлено — пропускаємо.")
        return None

    LOG.info("🔎 cloudscraper: намагаємось отримати HTML...")
    try:
        scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows"})
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
        }
        resp = scraper.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            LOG.info("✅ cloudscraper: HTML отримано")
            return resp.text
        else:
            LOG.warning(f"cloudscraper returned status {resp.status_code}")
            return None
    except Exception as e:
        LOG.error(f"cloudscraper error: {e}", exc_info=True)
        return None


def _extract_candidates_from_soup(soup: BeautifulSoup) -> List[Dict[str, str]]:
    """
    Збирає кандидатні заголовки з DOM:
    - article h1/h2/h3
    - a[href contains '/news/'] (текст посилання)
    - загальні h2/h3 елементи
    Повертає список dict: {"title": title, "url": url_or_empty}
    """
    candidates = []

    # 1) article заголовки
    for article in soup.find_all("article"):
        # шукаємо h1/h2/h3 у статті
        for tag_name in ("h1", "h2", "h3"):
            tag = article.find(tag_name)
            if tag:
                text = tag.get_text(strip=True)
                if text:
                    # знайдемо посилання в середині article, якщо є
                    a = article.find("a", href=True)
                    url = a["href"] if a else ""
                    candidates.append({"title": text, "url": url})

    # 2) посилання на /news/ (часто основні статті мають такі URL)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/news/" in href or "/article/" in href:
            text = a.get_text(strip=True)
            if text and len(text) > 10:
                url = href if href.startswith("http") else f"https://www.bloomberg.com{href}"
                candidates.append({"title": text, "url": url})

    # 3) загальні заголовки h2/h3 (як fallback)
    for tag in soup.find_all(["h2", "h3"]):
        text = tag.get_text(strip=True)
        if text and len(text) > 10:
            # якщо у заголовка є батьківське посилання — беремо його
            url = ""
            parent_a = tag.find_parent("a", href=True)
            if parent_a:
                url = parent_a["href"]
                if not url.startswith("http"):
                    url = f"https://www.bloomberg.com{url}"
            candidates.append({"title": text, "url": url})

    return candidates


def _clean_and_dedupe(candidates: List[Dict[str, str]], max_n: int = 10) -> List[Dict[str, str]]:
    """Фільтрування та дедуплікація кандидатів."""
    seen = set()
    out = []
    for c in candidates:
        t = c.get("title", "").strip()
        if not t or len(t) < 12:
            continue
        # пропускаємо службові підказки
        if t in IGNORE_TEXTS or any(ign in t for ign in IGNORE_TEXTS):
            continue
        # нормалізація
        norm = " ".join(t.split()).lower()
        if norm in seen:
            continue
        seen.add(norm)
        url = c.get("url", "").strip()
        if url and not url.startswith("http"):
            url = f"https://www.bloomberg.com{url}"
        out.append({"title": t, "url": url})
        if len(out) >= max_n:
            break
    return out


async def fetch_bloomberg(top_n: int = 10) -> List[Dict[str, str]]:
    """
    Основна асинхронна функція, що повертає до top_n заголовків.
    Стратегія:
      1) Спроба Playwright (рендер)
      2) Якщо немає Playwright або він провалився — cloudscraper
      3) Парсинг через BeautifulSoup + евристики селекторів
    """
    html = None

    # 1. Playwright (більш надійний)
    html = await _fetch_with_playwright(BLOOMBERG_URL) if async_playwright else None

    # 2. Fallback: cloudscraper
    if not html:
        html = _fetch_with_cloudscraper(BLOOMBERG_URL)

    if not html:
        LOG.warning("Не вдалося отримати HTML ні через Playwright, ні через cloudscraper")
        return []

    # Парсимо HTML
    soup = BeautifulSoup(html, "html.parser")
    candidates = _extract_candidates_from_soup(soup)
    results = _clean_and_dedupe(candidates, max_n=top_n)

    # Якщо немає результатів — пробуємо інший блок (ширше)
    if not results:
        LOG.info("Fallback: шукаємо більш широкі заголовки (meta og:title та title)...")
        meta_title = soup.find("meta", property="og:title")
        if meta_title and meta_title.get("content"):
            results.append({"title": meta_title["content"].strip(), "url": BLOOMBERG_URL})
        page_title = soup.title.string.strip() if soup.title else ""
        if page_title and page_title not in (r["title"] for r in results):
            results.append({"title": page_title, "url": BLOOMBERG_URL})

    LOG.info(f"Знайдено заголовків: {len(results)}")
    return results[:top_n]


# Локальний запуск для тесту
if __name__ == "__main__":
    import asyncio
    r = asyncio.run(fetch_bloomberg(10))
    for i, it in enumerate(r, 1):
        print(f"{i}. {it['title']} -> {it['url']}")