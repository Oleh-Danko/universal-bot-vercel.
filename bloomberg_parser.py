import os
import asyncio
import logging
import requests
from bs4 import BeautifulSoup

# --- Опційні бібліотеки ---
try:
    import cloudscraper
except ImportError:
    cloudscraper = None

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

from aiogram import Bot

# --- Налаштування ---
URL = "https://www.bloomberg.com/markets"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/",
    "DNT": "1",
}

# --- Логер ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("BloombergParser")

# --- Глобальний об'єкт Bot (ініціалізується, якщо токен є) ---
# 🔑 Змінні оточення беруться всередині функції send_admin_alert
# ВИДАЛЕНО: BOT_TOKEN = os.getenv("TOKEN") 
# ВИДАЛЕНО: bot = Bot(token=BOT_TOKEN) 
# ---

async def send_admin_alert(text: str):
    """Надсилає повідомлення адміну у Telegram."""
    # Отримуємо змінні всередині, щоб не було NoneType при імпорті
    ADMIN_ID = os.getenv("ADMIN_ID") 
    BOT_TOKEN = os.getenv("TOKEN")
    
    # Створюємо об'єкт Bot тільки якщо є токен
    if BOT_TOKEN and ADMIN_ID:
        try:
            temp_bot = Bot(token=BOT_TOKEN)
            await temp_bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ [Bloomberg Parser]\n{text}")
            await temp_bot.session.close() # Закриваємо сесію після використання
        except Exception as e:
            logger.error(f"Помилка при відправці логу адміну: {e}")
    else:
        logger.warning("ADMIN_ID або TOKEN не задано – лог у Telegram не відправлено.")


async def fetch_bloomberg():
    """Основна функція — отримує список заголовків новин Bloomberg."""
    html = await _get_html()
    if not html:
        await send_admin_alert("❌ Не вдалося отримати HTML Bloomberg (усі методи провалилися).")
        # ТУТ ТЕЖ ПРИБРАНО raise Exception, щоб не було збою всієї програми
        return []

    # Логіка парсингу: шукаємо заголовки <h3>
    soup = BeautifulSoup(html, "html.parser")
    # Додаємо фільтр довжини, щоб не захопити пусті теги
    titles = [t.get_text(strip=True) for t in soup.select("h3") if len(t.get_text(strip=True)) > 20][:10] 
    
    if not titles:
        await send_admin_alert("⚠️ HTML отримано, але не знайдено жодного заголовка (ймовірно змінилась структура сайту).")
    return titles


async def _get_html():
    """Пробує по черзі різні методи доступу."""
    # --- 1️⃣ requests (Просте виправлення User-Agent) ---
    try:
        logger.info("➡️ Спроба через requests...")
        resp = requests.get(URL, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            return resp.text
        else:
            await send_admin_alert(f"⚠️ requests повернув {resp.status_code}")
            logger.warning(f"requests → {resp.status_code}")
    except Exception as e:
        logger.error(f"requests error: {e}")
        await send_admin_alert(f"❌ requests error: {e}")

    # --- 2️⃣ cloudscraper (Обхід Cloudflare) ---
    if cloudscraper:
        try:
            logger.info("➡️ Спроба через cloudscraper...")
            scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows"})
            resp = scraper.get(URL, timeout=15)
            if resp.status_code == 200:
                return resp.text
            else:
                await send_admin_alert(f"⚠️ cloudscraper повернув {resp.status_code}")
                logger.warning(f"cloudscraper → {resp.status_code}")
        except Exception as e:
            logger.error(f"cloudscraper error: {e}")
            await send_admin_alert(f"❌ cloudscraper error: {e}")
    else:
        logger.warning("cloudscraper не встановлено")
        await send_admin_alert("ℹ️ cloudscraper не встановлено у середовищі.")

    # --- 3️⃣ Playwright (Безголовий браузер) ---
    if async_playwright:
        try:
            logger.info("➡️ Спроба через Playwright...")
            # Playwright повинен запускатися асинхронно
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(extra_http_headers=HEADERS) # Додаємо заголовки сюди
                await page.goto(URL, timeout=30000)
                html = await page.content()
                await browser.close()
                return html
        except Exception as e:
            logger.error(f"playwright error: {e}")
            await send_admin_alert(f"❌ Playwright error: {e}")
    else:
        logger.warning("playwright не встановлено")
        await send_admin_alert("ℹ️ Playwright не встановлено у середовищі.")

    return None