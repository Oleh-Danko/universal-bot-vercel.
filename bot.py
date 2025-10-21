import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import cache_manager

# === Налаштування логів ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot")

# === Твій токен бота ===
BOT_TOKEN = "8392167879:AAG9GgPCXrajvdZca5vJcYopk3HO5w2hBhE"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# === Команда /start ===
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.reply(
        "👋 Привіт! Я бот новин. Використовуй:\n"
        "/news — показати останні новини\n"
        "/update_cache — оновити кеш новин вручну"
    )


# === Команда /update_cache ===
@dp.message_handler(commands=["update_cache"])
async def cmd_update_cache(message: types.Message):
    await message.reply("🔄 Оновлюю кеш новин, зачекай кілька секунд...")
    count = cache_manager.run_cache_update()
    await message.reply(f"✅ Кеш оновлено. Збережено {count} новин.")


# === Команда /news ===
@dp.message_handler(commands=["news"])
async def cmd_news(message: types.Message):
    cache = cache_manager.load_cache()
    articles = cache.get("articles", [])
    if not articles:
        await message.reply("❌ Немає новин у кеші. Спочатку виконай /update_cache.")
        return

    # Сортуємо за джерелами
    articles.sort(key=lambda x: x["source"])
    text = f"🗞 <b>Останні новини ({len(articles)} шт.)</b>\n"
    current_source = None
    count = 0

    for article in articles:
        if article["source"] != current_source:
            current_source = article["source"]
            text += f"\n\n<b>— {current_source} —</b>\n"
        text += f"• <a href='{article['link']}'>{article['title']}</a>\n"
        count += 1
        if count >= 40:  # максимум 40 новин, щоб не перевищити ліміт Telegram
            break

    await message.reply(text, parse_mode="HTML", disable_web_page_preview=True)


# === Автоматичне оновлення кешу кожні 2 години ===
async def scheduler():
    while True:
        try:
            logger.info("🕐 Планове оновлення кешу...")
            cache_manager.run_cache_update()
        except Exception as e:
            logger.error(f"Помилка у scheduler: {e}")
        await asyncio.sleep(7200)  # 2 години


async def on_startup(_):
    asyncio.create_task(scheduler())
    logger.info("✅ Бот запущено успішно.")


if __name__ == "__main__":
    executor.start_polling(dp, on_startup=on_startup)