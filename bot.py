import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.client.default import DefaultBotProperties # <<< НОВИЙ ІМПОРТ

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

# Використовуйте змінну оточення, встановлену на Render, або замініть на свій URL
WEBHOOK_BASE = os.getenv("WEBHOOK_URL", "https://universal-bot-live.onrender.com")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_BASE}{WEBHOOK_PATH}"

# >>> ВИПРАВЛЕНО: Використовуємо DefaultBotProperties для aiogram 3.7+
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="Markdown")) 
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

# >>> ОБРОБНИК /NEWS (читає кеш) <<<
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
            
            # Екрануємо символи для безпечного Markdown (дуже важливо!)
            # Це важливо для коректного відображення символів _, *, [ та ` у Telegram
            title_escaped = n['title'].replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')

            # Очищення посилання BBC від трекінгових параметрів
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
                # Повідомлення занадто довге, відправляємо поточний блок
                messages_to_send.append("\n\n".join(current_message_parts))
                current_message_parts = [part] # Починаємо новий блок з цієї частини
            else:
                current_message_parts.append(part)

        # Додаємо останній, незавершений блок
        # Перевіряємо, чи є щось, крім початкового префікса
        if current_message_parts and (len(current_message_parts) > 1 or current_message_parts[0] != initial_prefix):
             messages_to_send.append("\n\n".join(current_message_parts)) 

        # 4. Відправка повідомлень
        if messages_to_send:
            for msg_content in messages_to_send:
                if msg_content.strip():
                    await message.answer(
                        msg_content, 
                        # parse_mode="Markdown", # Це вже встановлено за замовчуванням у Bot init
                        disable_web_page_preview=True