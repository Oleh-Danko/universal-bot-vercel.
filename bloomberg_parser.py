import asyncio
import logging
import cloudscraper
from bs4 import BeautifulSoup

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

logging.basicConfig(level=logging.INFO)

URL = "https://www.bloomberg.com/"

async def fetch_bloomberg():
    """
    Основна функція парсингу Bloomberg з fallback:
    1️⃣ спроба через Cloudscraper
    2️⃣ якщо блок — через Playwright
    """
    html = None

    # === 1. Спроба через Cloudscraper ===
    try:
        scraper = cloudscraper.create_scraper(delay=10, browser='chrome')
        response = scraper.get(URL, timeout=15)
        if response.status_code == 200:
            html = response.text
            logging.info("[Cloudscraper] Отримано HTML (%d символів)", len(html))
    except Exception as e:
        logging.warning("[Cloudscraper] Помилка: %s", e)

    # === 2. Fallback через Playwright ===
    if (not html or "captcha" in html.lower()) and async_playwright:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(URL, timeout=30000)
                await asyncio.sleep(3)
                html = await page.content()
                await browser.close()
                logging.info("[Playwright] Отримано HTML (%d символів)", len(html))
        except Exception as e:
            logging.warning("[Playwright] Помилка: %s", e)

    # === 3. Діагностика: показати перші 500 символів ===
    if html:
        preview = html[:500].replace("\n", " ")
        logging.info(f"[DIAGNOSTIC] Перші 500 символів HTML:\n{preview}")
    else:
        logging.warning("❌ HTML не отримано. Можливо, блокування з боку Bloomberg.")
        return []

    # === 4. Парсинг HTML ===
    soup = BeautifulSoup(html, "html.parser")
    headlines = _extract_candidates_from_soup(soup)

    logging.info("[Parser] Знайдено %d заголовків", len(headlines))
    return headlines


def _extract_candidates_from_soup(soup: BeautifulSoup):
    """
    Універсальний парсер заголовків Bloomberg.
    """
    candidates = set()

    # === Основні теги ===
    for tag in soup.find_all(["a", "h1", "h2", "h3"], limit=200):
        text = tag.get_text(strip=True)
        if text and len(text.split()) > 2 and not text.startswith("Bloomberg"):
            candidates.add(text)

    # === Посилання з data-component-type ===
    for link in soup.select('a[data-component-type*="Headline"], a[data-type="story"]'):
        text = link.get_text(strip=True)
        if text and len(text.split()) > 2:
            candidates.add(text)

    # === Meta og:title ===
    for meta in soup.find_all("meta", attrs={"property": "og:title"}):
        content = meta.get("content")
        if content:
            candidates.add(content.strip())

    return list(candidates)