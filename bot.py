import os
import logging
import asyncio 
from aiohttp import web
from datetime import datetime # Додано для використання datetime.now()

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.client.default import DefaultBotProperties 

# >>> ВИПРАВЛЕНО ІМПОРТ: тепер використовуємо функцію з CacheManager
from cache_manager import CacheManager, run_cache_update 

# === CONFIG & INIT ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WebhookBot")

# ЛІМІТ ДОВЖИНИ ПОВІДОМЛЕННЯ TELEGRAM
# Хоча використовуємо 4000, змінна залишається, але не використовується в логіці chunking, щоб уникнути плутанини
MAX_MESSAGE_LENGTH = 4000 

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Environment variable BOT_TOKEN is required")

# Використовуйте змінну оточення, встановлену на Render, або замініть на свій URL
WEBHOOK_BASE = os.getenv("WEBHOOK_URL", "https://universal-bot-live.onrender.com")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

# Ініціалізація Бота та Диспетчера
# Змінюємо default parse_mode на None, оскільки в news_cmd використовуємо HTML
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=None)) 
dp = Dispatcher()

# ІНІЦІАЛІЗАЦІЯ: МЕНЕДЖЕР КЕШУ
cache_manager = CacheManager()


# === ФОНОВА ЗАДАЧА: ПАРСЕР ===
async def run_parser_background():
    """Запускає оновлення кешу у нескінченному циклі з інтервалом."""
    
    # ПЕРША ЗАГРУЗКА ПРИ СТАРТІ (Чекаємо, щоб вона завершилася, щоб кеш не був порожнім)
    logger.info("Starting initial cache update (running run_cache_update())...")
    # Викликаємо функцію, яка виконує парсинг та зберігає кеш
    await run_cache_update() 
    logger.info("Initial cache update finished.")
    
    # ПОДАЛЬШИЙ ЦИКЛ ОНОВЛЕННЯ (раз на 60 хвилин)
    while True:
        await asyncio.sleep(3600) # Чекаємо 1 годину
        try:
            logger.info("Starting scheduled cache update...")
            await run_cache_update()
            logger.info("Scheduled cache update finished.")
        except Exception as e:
            logger.error(f"Error during scheduled cache update: {e}")


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

# ОБРОБНИК /NEWS (читає кеш)
# ПОВНІСТЮ ВИПРАВЛЕНА ФУНКЦІЯ: ВИДАЛЕНО ЛІМІТ 5 СТАТЕЙ, ВПРОВАДЖЕНО CHUNKING LOGIC
@dp.message(Command("news"))
async def news_cmd(message: Message):
    await message.answer("✅ Завантажую кеш новин. Це займає менше секунди...")
    
    try:
        # 1. Завантажуємо кеш
        cache_data = cache_manager.load_cache()
        articles = cache_data.get('articles', [])
        
        # Обробка часу
        timestamp = cache_data.get('timestamp', 'Невідомо')
        if isinstance(timestamp, str) and timestamp != 'Невідомо':
            timestamp = timestamp[:16].replace('T', ' ')

        if not articles:
            await message.answer("❌ Кеш новин порожній. Спробуйте пізніше. Можливо, фоновий процес ще не спрацював.")
            return

        total_count = len(articles)
        
        # 2. Сортуємо для коректного групування за джерелами 
        articles.sort(key=lambda x: x['source'])
        
        
        # --- ЛОГІКА РОЗБИТТЯ ПОВІДОМЛЕНЬ (Chunking) ---
        
        TELEGRAM_CHUNK_LIMIT = 4000
        formatted_chunk = ""
        sent_count = 0
        current_source_title = None
        
        # Первинне повідомлення про статус (відправляємо окремо для чистоти)
        initial_prefix = f"📰 <b>Останні новини</b> (оновлено: {timestamp}). <b>Загалом у кеші: {total_count} статей.</b>\n\n"
        await message.answer(initial_prefix, parse_mode="HTML")
        
        # 3. Основний цикл ітерації по ВСІХ статтях (Ліміт 5 статей видалено)
        for article in articles:
            
            # a) Формування Заголовка Джерела (якщо змінилося)
            source_header = ""
            if article['source'] != current_source_title:
                source_header = f"\n\n-- {article['source']} --\n\n"
                current_source_title = article['source']
            
            # b) Очищення посилання BBC та підготовка посилання
            link_text = article['link']
            if 'bbc.co.uk' in link_text:
                 link_text = link_text.split('?at_medium')[0]
                 
            # c) Форматування Тексту Статті (використовуємо HTML)
            article_text = f"📰 <b>{article['title']}</b>\n<a href='{link_text}'>Читати повністю</a>\n" 

            
            # d) ПЕРЕВІРКА ЛІМІТУ (Chunking Logic)
            # Якщо додавання наступного блоку (заголовка + статті) перевищить ліміт:
            if len(formatted_chunk) + len(source_header) + len(article_text) > TELEGRAM_CHUNK_LIMIT:
                
                # i. Надсилаємо поточний накопичений блок
                if formatted_chunk.strip():
                    await message.answer(formatted_chunk, parse_mode="HTML", disable_web_page_preview=True)
                    await asyncio.sleep(0.3) # Захист від Flood Control
                
                # ii. Починаємо новий блок з поточних заголовка джерела та статті
                formatted_chunk = source_header + article_text
            
            else:
                # iii. Додаємо до поточного блоку
                formatted_chunk += source_header + article_text
            
            sent_count += 1 

        # 4. ВІДПРАВКА ОСТАННЬОГО БЛОКУ (Фінальний Flush)
        if formatted_chunk.strip():
            await message.answer(formatted_chunk, parse_mode="HTML", disable_web_page_preview=True)

        # 5. Фінальне повідомлення (Підтвердження, що надіслано ВСІ статті)
        await message.answer(f"✅ Успішно надіслано всі {sent_count} новини із кешу. Загальна кількість: {total_count} статей.")


    except Exception as e:
        logger.exception("Критична помилка в /news: %s", e)
        await message.answer(f"❌ Критична помилка при обробці команди /news: {e}")

# Кінець функції news_cmd


# === STARTUP / SHUTDOWN (Async Operations) ===
async def on_startup(app):
    logger.info(f"Setting webhook to {WEBHOOK_URL}")
    await bot.set_webhook(WEBHOOK_URL)
    logger.info("✅ Webhook successfully set.")
    
    # !!! КЛЮЧОВИЙ МОМЕНТ: ЗАПУСК ПАРСЕРА ЯК ФОНОВОЇ ЗАДАЧІ !!!
    asyncio.create_task(run_parser_background())
    logger.info("✅ Parser background task scheduled.")

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