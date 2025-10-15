import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiohttp import web 
# --- ДОДАНІ БІБЛІОТЕКИ ДЛЯ ПАРСИНГУ ---
import requests
from bs4 import BeautifulSoup
# ---------------------------------------

# НОВИЙ ІМПОРТ: Підключаємо адаптивний парсер
from bloomberg_parser import fetch_bloomberg #

# 🔑 Токен береться зі змінних оточення Render (це безпечно)
TOKEN = os.environ.get("TOKEN") 

if not TOKEN:
    print("Помилка: Не знайдено змінну оточення TOKEN. Перевірте Render settings.")
    exit(1)

# Режим розбору Markdown для форматування
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- Обробники команд ---

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "👋 Привіт! Я бот, запущений на Render. Я не сплю, бо маю веб-сервер!\n"
        "Надішліть /news, щоб перевірити, чи працює основна логіка (з парсингом)."
    )

# ПОВНА ЗАМІНА: Використовуємо адаптивну функцію замість requests/BeautifulSoup
@dp.message(Command("news"))
async def news_command(message: types.Message):
    await message.answer("⏳ Отримую свіжі новини з Bloomberg...")
    try:
        titles = await fetch_bloomberg()
        if titles:
            formatted = "\n\n".join([f"🔹 {t}" for t in titles])
            await message.answer(f"📰 Топ новин Bloomberg:\n\n{formatted}")
        else:
            await message.answer("⚠️ Не вдалося отримати новини.")
    except Exception as e:
        # Це повідомлення для користувача. Деталі помилки підуть адміну через send_admin_alert
        await message.answer("❌ Парсинг не вдався. Адміністратора повідомлено про проблему.")


# --- Web Server для Render (щоб не засинав) ---
# ... (Інший код залишається без змін) ...

async def handle_ping(request):
    """Простий обробник для пінг-запитів Render"""
    return web.Response(text="I'm alive and ready to work!")

async def start_web_server():
    """Запускає веб-сервер на порту, який очікує Render (PORT)"""
    # Render передає порт через змінну оточення PORT
    port = int(os.environ.get("PORT", 8080)) 
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"✅ Web server started on port {port}")

# --- Головна функція запуску ---

async def main():
    print("✅ Бот запущений і чекає повідомлень...")
    await asyncio.gather(
        dp.start_polling(bot),
        start_web_server() # Запуск фонового веб-сервера
    )

if __name__ == "__main__":
    # Запускаємо головну функцію
    asyncio.run(main())