# ==========================================================
# Файл: bot.py (Заміна)
# Призначення: Видалення команди /bloomberg та додавання 9 нових RSS-стрічок.
# ==========================================================

import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

import html 
import asyncio # Потрібен для asyncio.to_thread, щоб зробити парсер неблокуючим

from rss_parser import fetch_rss_news 
from bloomberg_parser import fetch_bloomberg_news # Залишаємо імпорт, але функція поверне []

# === CONFIG & INIT ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebhookBot")

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Environment variable BOT_TOKEN is required")

WEBHOOK_BASE = os.getenv("WEBHOOK_URL", "https://universal-bot-live.onrender.com")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === НОВІ RSS ДЖЕРЕЛА (10 джерел) ===
ALL_RSS_FEEDS = {
    # 1. BBC Business (Поточне робоче джерело)
    "BBC Business": "http://feeds.bbci.co.uk/news/business/rss.xml",
    
    # 2. Економічна Правда
    "ЕП Фінанси": "https://www.epravda.com.ua/rss/finances/",
    "ЕП Колонки/Думки": "https://www.epravda.com.ua/rss/columns/", 

    # 3. Reuters 
    "Reuters Бізнес": "http://feeds.reuters.com/reuters/businessNews",
    "Reuters Ринки": "http://feeds.reuters.com/reuters/marketsNews",
    "Reuters Технології": "http://feeds.reuters.com/reuters/technologyNews",

    # 4. Financial Times (FT)
    "FT Компанії": "https://www.ft.com/companies?format=rss",
    "FT Технології": "https://www.ft.com/technology?format=rss",
    "FT Ринки": "https://www.ft.com/markets?format=rss",
    "FT Думки": "https://www.ft.com/opinion?format=rss"
}


# === HANDLERS ===
@dp.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "👋 Привіт! Я бот, запущений на Render. "
        "Надішліть /news, щоб отримати свіжі новини з усіх 10 джерел (BBC, ЕП, Reuters, FT)."
    )

@dp.message(Command("news"))
async def news_cmd(message: Message, bot: Bot):
    await message.answer("⏳ Отримую свіжі новини з 10 RSS-стрічок (BBC, ЕП, Reuters, FT). Це може зайняти до 15 секунд...")
    
    all_news = []
    
    # 1. Створюємо список асинхронних завдань
    tasks = []
    for source_name, url in ALL_RSS_FEEDS.items():
        tasks.append(asyncio.to_thread(fetch_rss_news, url))
        
    try:
        # 2. Виконуємо всі завдання паралельно
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for source_name, result in zip(ALL_RSS_FEEDS.keys(), results):
            if isinstance(result, list):
                for item in result:
                    item['source'] = source_name
                    all_news.append(item)
            else:
                logger.error(f"Помилка при отриманні новин з {source_name}: {result}")


        if not all_news:
            await message.answer("❌ Парсинг не вдався. Новини не знайдено. Перевірте логи.")
            return

        # Сортування: Сортуємо за джерелом
        all_news.sort(key=lambda x: x['source'])
        
        # 3. Групування та Форматування
        current_source = None
        formatted_messages = []
        
        for n in all_news:
            if n['source'] != current_source:
                current_source = n['source']
                formatted_messages.append(f"\n\n\n**-- {current_source} --**") 
            
            # Екрануємо символи для безпечного Markdown
            title_escaped = n['title'].replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')

            link_text = n['link']
            if 'bbc.co.uk' in link_text:
                 link_text = link_text.split('?at_medium')[0]
            
            formatted_messages.append(f"📰 *{title_escaped}*\n[Читати повністю]({link_text})")

        # 4. Відправка повідомлення (розділяємо, якщо воно занадто велике)
        final_text = "\n\n".join(formatted_messages)
        
        if len(final_text) > 4096:
            split_point = len(formatted_messages) // 2
            
            chunk1 = "\n\n".join(formatted_messages[:split_point])
            chunk2 = "\n\n".join(formatted_messages[split_point:])

            await message.answer(
                f"📰 **Загальна кількість новин: {len(all_news)}**\n\n" + chunk1, 
                parse_mode="Markdown", 
                disable_web_page_preview=True
            )
            await message.answer(
                chunk2, 
                parse_mode="Markdown", 
                disable_web_page_preview=True
            )
        else:
            await message.answer(
                f"📰 **Загальна кількість новин: {len(all_news)}**\n\n" + final_text, 
                parse_mode="Markdown", 
                disable_web_page_preview=True
            )


    except Exception as e:
        logger.exception("Помилка в /news: %s", e)
        await message.answer(f"❌ Парсинг не вдався. Деталі помилки: {e}")


# === STARTUP / SHUTDOWN (Async Operations) ===
async def on_startup(app):
    logger.info(f"Setting webhook to {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)
    logger.info("✅ Webhook successfully set.")

async def on_shutdown(app):
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

    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    app.router.add_get("/", handle_health)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    logger.info("🌐 Starting web server on 0.0.0.0:10000 ...")
    
    port = int(os.getenv("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()