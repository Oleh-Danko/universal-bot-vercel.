import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiohttp import web 

# 🔑 Токен береться зі змінних оточення Render (це безпечно)
TOKEN = os.environ.get("TOKEN") 

if not TOKEN:
    print("Помилка: Не знайдено змінну оточення TOKEN. Перевірте Render settings.")
    exit(1)

# Режим розбору Markdown для форматування
bot = Bot(token=TOKEN, parse_mode='Markdown')
dp = Dispatcher()

# --- Обробники команд ---

@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "👋 Привіт! Я бот, запущений на Render. Я не сплю, бо маю веб-сервер!\n"
        "Надішліть /news, щоб перевірити, чи працює основна логіка."
    )

@dp.message(Command("news"))
async def news_command(message: types.Message):
    # Тут буде Playwright-парсер, але поки що це просто тестова відповідь
    await message.answer(
        "⏳ Бот працює на Render!\n"
        "Парсинг ще не інтегровано, але бот відповідає і працює 24/7."
    )

# --- Web Server для Render (щоб не засинав) ---

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
