import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

import html 
import asyncio 

# >>> НОВИЙ ІМПОРТ: Менеджер кешу <<<
from cache_manager import CacheManager 

# === CONFIG & INIT ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebhookBot")

# ЛІМІТ ДОВЖИНИ ПОВІДОМЛЕННЯ TELEGRAM
MAX_MESSAGE_LENGTH = 4000 

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Environment variable BOT_TOKEN is required")

WEBHOOK_BASE = os.getenv("WEBHOOK_URL", "https://universal-bot-live.onrender.com")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# >>> НОВА ІНІЦІАЛІЗАЦІЯ: МЕНЕДЖЕР КЕШУ <<<
cache_manager = CacheManager()


# === HANDLERS ===
@dp.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "👋 Привіт! Я бот, запущений на Render. "
        "Надішліть /news, щоб отримати свіжі новини з усіх 10 джерел (BBC, ЕП, Reuters, FT)."
    )
    
@dp.message(Command("bloomberg"))
async def bloomberg_cmd_deprecated(message: Message):
    await message.answer(
        "⚠️ Команда /bloomberg більше не підтримується! "
        "Парсер Bloomberg став нестабільним. "
        "Використовуйте /news для отримання новин з усіх 10 надійних джерел (включно з FT та Reuters)."
    )

# >>> НОВИЙ ОБРОБНИК /NEWS (читає кеш) <<<
@dp.message(Command("news"))
async def news_cmd(message: Message):
    await message.answer("✅ Завантажую кеш новин. Це займає менше секунди...")
    
    try:
        # 1. Завантажуємо кеш, який був збережений у фоновому процесі 
        cache_data = cache_manager.load_cache()
        articles = cache_data.get('articles', [])
        
        # Обрізаємо час для красивого відображення
        timestamp = cache_data.get('timestamp', 'Невідомо')
        if timestamp != 'Невідомо':
            timestamp = timestamp[:16].replace('T', ' ')

        if not articles:
            await message.answer("❌ Кеш новин порожній. Спробуйте пізніше. Можливо, фоновий процес ще не спрацював.")
            return

        # 2. Формування повідомлення (обмежуємо до 5 статей на джерело)
        
        # Сортуємо, щоб джерела йшли послідовно
        articles.sort(key=lambda x: x['source'])
        
        current_source = None
        formatted_messages = []
        source_counts = {} 
        
        for n in articles:
            source_name = n['source']
            if source_counts.get(source_name, 0) >= 5: # Ліміт 5 статей на джерело
                continue
                
            if source_name != current_source:
                current_source = source_name
                # Заголовок джерела
                formatted_messages.append(f"\n\n\n**-- {current_source} --**") 
            
            # Екрануємо символи для безпечного Markdown
            title_escaped = n['title'].replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')

            # Очищення посилання BBC
            link_text = n['link']
            if 'bbc.co.uk' in link_text:
                 link_text = link_text.split('?at_medium')[0]
            
            formatted_messages.append(f"📰 *{title_escaped}*\n[Читати повністю]({link_text})")
            source_counts[source_name] = source_counts.get(source_name, 0) + 1

        # 3. НАДІЙНА ВІДПРАВКА ПОВІДОМЛЕНЬ ЧАСТИНАМИ 
        
        initial_prefix = f"📰 **Останні новини (оновлено: {timestamp}). Загалом у кеші: {len(articles)} статей.**\n\n"
        current_message_parts = [initial_prefix]
        messages_to_send = []
        
        for part in formatted_messages:
            test_message = "\n\n".join(current_message_parts + [part])
            
            if len(test_message) > MAX_MESSAGE_LENGTH:
                messages_to_send.append("\n\n".join(current_message_parts))
                current_message_parts = [part] # Починаємо новий блок
            else:
                current_message_parts.append(part)

        # Додаємо останній, незавершений блок
        if current_message_parts and (len(current_message_parts) > 1 or current_message_parts[0] != initial_prefix):
             messages_to_send.append("\n\n".join(current_message_parts)) 

        # 4. Відправка повідомлень
        if messages_to_send:
            for msg_content in messages_to_send:
                if msg_content.strip():
                    await message.answer(
                        msg_content, 
                        parse_mode="Markdown", 
                        disable_web_page_preview=True
                    )
        else:
            await message.answer("❌ Новини було отримано, але стався внутрішній збій при їх формуванні.")

    except Exception as e:
        logger.exception("Помилка в /news: %s", e)
        await message.answer(f"❌ Помилка при читанні кешу: {e}")

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

    port = int(os.getenv("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()