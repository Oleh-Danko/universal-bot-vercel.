import asyncio
import logging
import os
import cloudscraper
from bs4 import BeautifulSoup

# Playwright imports
from playwright.async_api import async_playwright

# Налаштування логування (Render бачить print у логах)
logging.basicConfig(level=logging.INFO)

async def fetch_bloomberg():
    """
    Адаптивний парсер Bloomberg:
    1️⃣ Пробує cloudscraper.
    2️⃣ Якщо сторінка заблокована або пуста — fallback до Playwright.
    3️⃣ Виводить перші 500 символів HTML у логах для діагностики.
    4️⃣ Повертає список заголовків.
    """

    url = "https://www.bloomberg.com/"
    html = ""

    # --- Крок 1: Cloudsraper ---
    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, timeout=15)
        response.raise_for_status()

        html = response.text.strip()

        if len(html) < 1000 or "Please enable JavaScript" in html or "Cloudflare" in html:
            logging.warning("⚠️ HTML виглядає підозріло (Cloudflare/захист). Переходимо на Playwright.")
            html = ""
        else:
            logging.info("✅ Отримано HTML через cloudscraper.")
    except Exception as e:
        logging.warning(f"❌ Помилка при використанні cloudscraper: {e}")
        html = ""

    # --- Крок 2: Playwright fallback ---
    if not html:
        logging.info("🔁 Використовуємо Playwright для завантаження сторінки...")
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/115.0.0.0 Safari/537.36"
                ))
                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30000)
                html = await page.content()
                await browser.close()
                logging.info("✅ Отримано HTML через Playwright.")
        except Exception as e:
            logging.error(f"❌ Помилка Playwright: {e}")
            html = ""

    # --- Крок 3: Діагностика отриманого HTML ---
    logging.info(f"📄 Перші 500 символів HTML:\n{html[:500]}\n--- END OF PREVIEW ---")

    # --- Крок 4: Парсинг ---
    if not html:
        logging.warning("⚠️ HTML порожній — повертаємо [].")
        return []

    soup = BeautifulSoup(html, "html.parser")
    titles = _extract_candidates_from_soup(soup)

    logging.info(f"🔹 Знайдено {len(titles)} заголовків Bloomberg.")
    return titles[:10] if titles else []


def _extract_candidates_from_soup(soup: BeautifulSoup) -> list[str]:
    """Пошук усіх можливих варіантів заголовків."""
    candidates = set()

    # --- Варіант 1: data-component-type (найчастіший) ---
    for tag in soup.find_all(attrs={"data-component-type": "Headline"}):
        text = tag.get_text(strip=True)
        if text:
            candidates.add(text)

    # --- Варіант 2: <a> з aria-label або role="heading" ---
    for a in soup.find_all("a", attrs={"role": "heading"}):
        text = a.get_text(strip=True)
        if text:
            candidates.add(text)
    for a in soup.find_all("a", attrs={"aria-label": True}):
        text = a.get_text(strip=True)
        if text:
            candidates.add(text)

    # --- Варіант 3: класові патерни ---
    class_patterns = ["headline", "story", "title", "article"]
    for c in class_patterns:
        for el in soup.find_all(class_=lambda v: v and c in v.lower()):
            text = el.get_text(strip=True)
            if text:
                candidates.add(text)

    # --- Варіант 4: Теги h1, h2 ---
    for h in soup.find_all(["h1", "h2"]):
        text = h.get_text(strip=True)
        if text:
            candidates.add(text)

    # --- Варіант 5: meta og:title ---
    for meta in soup.find_all("meta", attrs={"property": "og:title"}):
        text = meta.get("content")
        if text:
            candidates.add(text.strip())

    # --- Фільтрація ---
    filtered = [
        t for t in candidates
        if len(t) > 5
        and not t.lower().startswith("bloomberg")
        and not "cookies" in t.lower()
        and not "javascript" in t.lower()
    ]

    return list(filtered)


# --- Тестовий запуск локально ---
if __name__ == "__main__":
    results = asyncio.run(fetch_bloomberg())
    print("✅ Результати:", results)