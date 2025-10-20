import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

import html 
import asyncio 

from rss_parser import fetch_rss_news 
from bloomberg_parser import fetch_bloomberg_news # Залишаємо імпорт, але функція поверне []

# === CONFIG & INIT ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebhookBot")

# ЛІМІТ ДОВЖИНИ ПОВІДОМЛЕННЯ TELEGRAM
# Встановлюємо 4000, щоб мати запас для Markdown-форматування та заголовків
MAX_MESSAGE_LENGTH = 4000 

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Environment variable BOT_TOKEN is required")

WEBHOOK_BASE = os.getenv("WEBHOOK_URL", "https://universal-bot-live.onrender.com")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === RSS ДЖЕРЕЛА (10 джерел) ===
ALL_RSS_FEEDS = {
    # 1. BBC Business 
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
    
@dp.message(Command("bloomberg"))
async def bloomberg_cmd_deprecated(message: Message):
    # Додано явну обробку команди /bloomberg, щоб запобігти помилкам
    await message.answer(
        "⚠️ Команда /bloomberg більше не підтримується! "
        "Парсер Bloomberg став нестабільним. "
        "Використовуйте /news для отримання новин з усіх 10 надійних джерел (включно з FT та Reuters)."
    )

@dp.message(Command("news"))
async def news_cmd(message: Message, bot: Bot):
    await message.answer("⏳ Отримую свіжі новини з 10 RSS-стрічок (BBC, ЕП, Reuters, FT). Це може зайняти до 15 секунд...")
    
    all_news = []
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
                # Заголовок джерела має бути відокремлений
                formatted_messages.append(f"\n\n\n**-- {current_source} --**") 
            
            # Екрануємо символи для безпечного Markdown
            title_escaped = n['title'].replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')

            link_text = n['link']
            if 'bbc.co.uk' in link_text:
                 link_text = link_text.split('?at_medium')[0]
            
            # Додаємо новину
            formatted_messages.append(f"📰 *{title_escaped}*\n[Читати повністю]({link_text})")

        # 4. НАДІЙНА ВІДПРАВКА ПОВІДОМЛЕНЬ ЧАСТИНАМИ (КРИТИЧНЕ ВИПРАВЛЕННЯ)
        
        # Додаємо загальну інформацію як префікс до першого повідомлення
        initial_prefix = f"📰 **Загальна кількість новин: {len(all_news)}**\n\n"
        
        current_message_parts = [initial_prefix]
        
        # Список, куди будемо зберігати готові блоки повідомлень
        messages_to_send = []
        
        for part in formatted_messages:
            # Спроба додати наступну частину
            test_message = "\n\n".join(current_message_parts + [part])
            
            if len(test_message) > MAX_MESSAGE_LENGTH:
                # Якщо ліміт перевищено, зберігаємо поточний зібраний блок
                messages_to_send.append("\n\n".join(current_message_parts))
                
                # Починаємо новий блок з поточного "part"
                current_message_parts = [part]
            else:
                # Ліміт не перевищено, додаємо частину до поточного блоку
                current_message_parts.append(part)

        # Додаємо останній, незавершений блок
        if current_message_parts and (len(current_message_parts) > 1 or current_message_parts[0] != initial_prefix):
             messages_to_send.append("\n\n".join(current_message_parts))


        # 5. Відправка повідомлень
        
        if messages_to_send:
            for msg_content in messages_to_send:
                # Якщо повідомлення порожнє або містить лише префікс, пропускаємо його
                if len(msg_content.strip()) < len(initial_prefix.strip()) + 5 and msg_content.startswith(initial_prefix):
                    continue

                await message.answer(
                    msg_content, 
                    parse_mode="Markdown", 
                    disable_web_page_preview=True
                )
        else:
            await message.answer("❌ Новини було отримано, але стався внутрішній збій при їх формуванні.")


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