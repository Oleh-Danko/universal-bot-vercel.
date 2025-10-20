import json
import asyncio
import os
from datetime import datetime, timedelta
from loguru import logger
import httpx 
import feedparser 

from rss_parser import fetch_rss_news
# Парсер Bloomberg не використовується
# from bloomberg_parser import fetch_bloomberg_news

# === CONFIG ===
CACHE_FILE = "news_cache.json"
CACHE_LIFETIME = timedelta(hours=1) # Зробимо 1 годину для тестування

ALL_RSS_FEEDS = {
    # Виправлення: використовуємо HTTP для максимальної сумісності
    "BBC Business": "http://feeds.bbci.co.uk/news/business/rss.xml",
    
    "ЕП Фінанси": "https://www.epravda.com.ua/rss/finances/",
    "ЕП Колонки/Думки": "https://www.epravda.com.ua/rss/columns/", 

    "Reuters Бізнес": "http://feeds.reuters.com/reuters/businessNews",
    "Reuters Ринки": "http://feeds.reuters.com/reuters/marketsNews",
    "Reuters Технології": "http://feeds.reuters.com/reuters/technologyNews",

    "FT Компанії": "https://www.ft.com/companies?format=rss",
    "FT Технології": "https://www.ft.com/technology?format=rss",
    "FT Ринки": "https://www.ft.com/markets?format=rss",
    "FT Думки": "https://www.ft.com/opinion?format=rss"
}

# ====================================================================

class CacheManager:
    """Менеджер для роботи з файлом кешу новин."""
    
    def __init__(self):
        # Перевірка наявності файлу кешу при ініціалізації
        if not os.path.exists(CACHE_FILE):
             logger.warning(f"Файл кешу {CACHE_FILE} не знайдено. Буде створено.")

    def load_cache(self):
        """Завантажує дані кешу з файлу."""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"Кеш завантажено. Час оновлення: {data.get('timestamp')}")
                    return {"timestamp": data.get("timestamp"), "articles": data.get("news", [])}
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"Помилка завантаження кешу: {e}. Створюю пустий словник.")
                return {"timestamp": None, "articles": []}
        return {"timestamp": None, "articles": []}

    def save_cache(self, news_data):
        """Зберігає дані новин у файл кешу з позначкою часу."""
        timestamp = datetime.now().isoformat()
        cache_data = {
            "timestamp": timestamp,
            "news": news_data
        }
        try:
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=4)
                logger.info(f"✅ Кеш новин успішно збережено. Час: {timestamp}")
        except IOError as e:
            logger.error(f"Помилка збереження кешу: {e}")

    async def fetch_all_news_async(self):
        """Асинхронно отримує всі новини з усіх джерел."""
        logger.info("Починаю асинхронне отримання новин з усіх RSS-стрічок.")
        all_news = []
        tasks = []
        
        for source_name, url in ALL_RSS_FEEDS.items():
            # Використовуємо asyncio.to_thread для блокуючих операцій (як fetch_rss_news)
            tasks.append(asyncio.to_thread(fetch_rss_news, url))
            
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for source_name, result in zip(ALL_RSS_FEEDS.keys(), results):
                if isinstance(result, list):
                    for item in result:
                        item['source'] = source_name
                        all_news.append(item)
                else:
                    logger.error(f"Помилка при отриманні новин з {source_name}: {result}")

            logger.info(f"✅ Зібрано загалом {len(all_news)} новин.")
            return all_news

        except Exception as e:
            logger.error(f"Глобальна помилка при парсингу: {e}")
            return []

    async def update_cache(self):
        """Оновлює кеш, отримуючи нові статті та зберігаючи їх."""
        logger.info("Starting cache update...")
        start_time = datetime.now()
        
        all_news = await self.fetch_all_news_async()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        if all_news:
             self.save_cache(all_news)
             logger.info(f"Cache update finished. Total articles: {len(all_news)}. Duration: {duration:.2f} seconds.")
             return True
        else:
            logger.warning("Не вдалося отримати жодної новини. Кеш не оновлено.")
            return False

# ====================================================================

if __name__ == "__main__":
    # Логіка для запуску через cron job (для оновлення кешу)
    manager = CacheManager()
    logger.info("Запущено процес оновлення кешу новин.")
    # Виконуємо парсинг
    asyncio.run(manager.update_cache())