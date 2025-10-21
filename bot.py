import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.client.bot import DefaultBotProperties
from cache_manager import CacheManager, run_cache_update

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

# Для aiogram 3.22: parse_mode передається через DefaultBotProperties
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

cache_manager = CacheManager()

@dp.message()
async def start(message: Message):
    await message.reply("Привіт! Я бот для збору новин. Напиши /news щоб отримати останні новини.")

@dp.message()
async def news(message: Message):
    data = cache_manager.load_cache()
    articles = data.get("articles", [])[-10:]  # останні 10 новин
    if not articles:
        await message.reply("Поки що немає новин.")
        return
    text = ""
    for item in articles:
        text += f"<a href='{item['link']}'>{item['title']}</a>\n"
    await message.reply(text, disable_web_page_preview=False)

async def main():
    # Оновлюємо кеш при старті бота
    await run_cache_update()
    # Запускаємо бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())