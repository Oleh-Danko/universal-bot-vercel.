import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

# === НОВІ ІМПОРТИ (КРИТИЧНО) ===
import html 
import asyncio # Потрібен для asyncio.to_thread, щоб зробити парсер неблокуючим

# === ІМПОРТИ ДЛЯ ФУНКЦІОНАЛУ ===
from rss_parser import fetch_rss_news 
from bloomberg_parser import fetch_bloomberg_news 

# === CONFIG & INIT ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebhookBot")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Environment variable BOT_TOKEN is required")

# КРИТИЧНЕ ВИПРАВЛЕННЯ: Чистий URL без markdown-формату
WEBHOOK_BASE = os.getenv("WEBHOOK_URL", "https://universal-bot-live.onrender.com")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

# Створюємо екземпляри бота та диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === HANDLERS ===
@dp.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "👋 Привіт! Я бот, запущений на Render. Надішліть /news (BBC Business RSS) або /bloomberg (Парсинг), щоб перевірити функціонал."
    )

@dp.message(Command("news"))
async def news_cmd(message: Message, bot: Bot):
    # Спочатку надсилаємо повідомлення, щоб користувач не чекав
    await message.answer("⏳ Отримую свіжі новини з BBC Business (RSS)...")
    
    try:
        # === КРИТИЧНЕ ВИПРАВЛЕННЯ: ЗМІНА RSS-АДРЕСИ НА BBC BUSINESS ===
        BBC_RSS_URL = "http://feeds.bbci.co.uk/news/business/rss.xml" 
        
        # Використовуємо asyncio.to_thread, щоб синхронна функція не блокувала aiohttp.
        news_list = await asyncio.to_thread(fetch_rss_news, BBC_RSS_URL)

        if not news_list:
            await message.answer("❌ Парсинг не вдався. Новини не знайдено.")
            return

        # Форматування новин для Markdown
        formatted_news = []
        for n in news_list:
            # Використовуємо Markdown для коректного відображення посилань
            formatted_news.append(f"📰 *{n['title']}*\n[Читати на BBC]({n['link']})")

        text = "\n\n".join(formatted_news)
        await message.answer(
            text, 
            parse_mode="Markdown", 
            disable_web_page_preview=True
        )

    except Exception as e:
        logger.exception("Помилка в /news: %s", e)
        # Надсилаємо повідомлення про помилку з її деталями
        await message.answer(f"❌ Парсинг не вдався. Деталі помилки: {e}")


@dp.message(Command("bloomberg"))
async def bloomberg_cmd(message: Message):
    """Обробляє команду /bloomberg, отримуючи ТОП-10 новин з Bloomberg (парсинг)."""
    
    # 1. Повідомлення про початок
    await message.answer("🔍 Завантажую ТОП-10 новин з Bloomberg...", 
                         parse_mode="HTML") 

    try:
        # 2. КРИТИЧНО: ДОДАНО 'await' для безпечного виконання blocking-коду
        news_items = await asyncio.to_thread(fetch_bloomberg_news)
        
        if not news_items:
            await message.answer("❌ Не вдалося отримати новини з Bloomberg. Можливо, сайт заблокував запит або змінив структуру.")
            return

        # 3. Форматування та відправка новин
        response_messages = []
        for i, item in enumerate(news_items[:10]): # Обмежуємо 10
            # Екранування символів у заголовку
            title = html.escape(item.get('title', ''))
            
            # Форматуємо новину: номер, заголовок, посилання (Markdown-формат)
            news_text = f"**{i + 1}.** *{title}*\n[Читати повністю]({item['link']})"
            response_messages.append(news_text)
        
        text_to_send = "\n\n".join(response_messages)
        
        # 4. Відправляємо повідомлення
        await message.answer(
            f"🗞️ **ТОП {len(news_items[:10])} новин з Bloomberg**:\n\n{text_to_send}",
            parse_mode="Markdown", 
            disable_web_page_preview=True 
        )

    except Exception as e:
        logger.exception("Помилка в bloomberg_cmd: %s", e)
        await message.answer(f"❌ Виникла помилка під час обробки новин Bloomberg. Деталі: {e}")


# === STARTUP / SHUTDOWN (Async Operations) ===
async def on_startup(app):
    # Встановлюємо webhook
    logger.info(f"Setting webhook to {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)
    logger.info("✅ Webhook successfully set.")

async def on_shutdown(app):
    # Видаляємо webhook перед зупинкою
    logger.info("Deleting webhook...")
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("✅ Shutdown complete.")

# === HEALTH CHECK ===
async def handle_health(request):
    return web.Response(text="✅ OK", status=200)

# === MAIN (Synchronous Server Run) ===
def main():
    app = web.Application()

    # Реєстрація хендлерів Webhook та Диспетчера
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    # Health Check Endpoint
    app.router.add_get("/", handle_health)

    # Реєстрація функцій on_startup та on_shutdown
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    logger.info("🌐 Starting web server on 0.0.0.0:10000 ...")
    
    # Використовуємо змінну оточення $PORT, якщо вона доступна
    port = int(os.getenv("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()