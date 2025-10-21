import json
import asyncio
import os
from datetime import datetime, timedelta
from loguru import logger # Використовуємо loguru для гарного логування

# Імпортуємо фактичні парсери
from rss_parser import fetch_rss_news
from bloomberg_parser import fetch_bloomberg_news 

# === CONFIG ===
CACHE_FILE = "news_cache.json"

# Всі RSS-стрічки, які ми парсимо
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

# ====================================================================

class CacheManager:
    """Клас для роботи з файлом кешу news_cache.json."""
    
    def __init__(self):
        if not os.path.exists(CACHE_FILE):
            logger.warning(f"Файл кешу {CACHE_FILE} не знайдено. Буде створено.")

    def load_cache(self):
        """Завантажує дані кешу з файлу."""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"Кеш завантажено. Час оновлення: {data.get('timestamp')}")
                    # УВАГА: ВИКОРИСТОВУЄМО КЛЮЧ 'articles'
                    if 'articles' in data:
                        return data
                    return {} 
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Помилка завантаження кешу: {e}. Створюю новий кеш.")
                return {}
        return {}

    def save_cache(self, articles_data):
        """Зберігає дані новин у файл кешу з позначкою часу."""
        timestamp = datetime.now().isoformat()
        cache_data = {
            "timestamp": timestamp,
            "articles": articles_data # <<< ВИКОРИСТОВУЄМО ПРАВИЛЬНИЙ КЛЮЧ
        }
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=4)
                logger.info(f"✅ Кеш новин успішно збережено. Час: {timestamp}")
        except IOError as e:
            logger.error(f"Помилка збереження кешу: {e}")


async def fetch_all_news_async():
    """Асинхронно отримує всі новини з усіх джерел."""
    logger.info("Починаю асинхронне отримання новин з усіх RSS-стрічок.")
    all_news = []
    tasks = []
    
    # Додаємо завдання для RSS (викликаємо блокуючі функції через asyncio.to_thread)
    for source_name, url in ALL_RSS_FEEDS.items():
        # fetch_rss_news повертає список статей
        tasks.append(asyncio.to_thread(fetch_rss_news, url)) 
        
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Обробка результатів RSS
        for source_name, result in zip(ALL_RSS_FEEDS.keys(), results):
            if isinstance(result, list):
                for item in result:
                    item['source'] = source_name
                    # Перевірка: елемент має бути словником
                    if isinstance(item, dict):
                        all_news.append(item)
            else:
                logger.error(f"Помилка при отриманні новин з {source_name}: {result}")
        
        # Додаємо Bloomberg (використовуємо to_thread, оскільки вона блокуюча)
        # Припускаємо, що fetch_bloomberg_news знаходиться у bloomberg_parser.py
        bloomberg_news = await asyncio.to_thread(fetch_bloomberg_news)
        if isinstance(bloomberg_news, list):
             for item in bloomberg_news:
                    item['source'] = 'Bloomberg'
                    if isinstance(item, dict):
                        all_news.append(item)

        logger.info(f"✅ Зібрано загалом {len(all_news)} новин.")
        return all_news

    except Exception as e:
        logger.error(f"Глобальна помилка при парсингу: {e}")
        return []

# === ФУНКЦІЯ, ЯКУ БУДЕ ІМПОРТУВАТИ BOT.PY ===
async def run_cache_update():
    """Головна асинхронна функція для оновлення кешу (Fetch + Save)."""
    logger.info("Запущено процес оновлення кешу новин.")
    
    # Виконуємо парсинг
    updated_news = await fetch_all_news_async()
    
    if updated_news:
        # Сортування: якщо статті мають 'pubDate', сортуємо за нею, інакше просто сортуємо за джерелом
        try:
            # Сортуємо в зворотному порядку, щоб найновіші були першими
            updated_news.sort(key=lambda x: x.get('pubDate', ''), reverse=True)
        except TypeError:
            # Fallback на сортування за джерелом, якщо дати не існують
            updated_news.sort(key=lambda x: x['source'])

        # Зберігаємо оновлений кеш
        manager = CacheManager()
        manager.save_cache(updated_news)
    else:
        logger.warning("Не знайдено жодної статті. Кеш не оновлено.")