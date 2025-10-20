import requests
import feedparser
import logging

# Кількість новин не обмежена (None), але для безпеки встановлено високий ліміт.
MAX_NEWS_ITEMS = 50 
logger = logging.getLogger("RSSParser")

def fetch_rss_news(url: str) -> list[dict]:
    """
    Отримує та парсить RSS-стрічку за заданим URL.
    ЛІМІТ ВІДСУТНІЙ, повертає усі доступні новини (до MAX_NEWS_ITEMS).
    """
    try:
        # Отримання даних RSS
        response = requests.get(url, timeout=10)
        response.raise_for_status() # Перевіряємо на помилки HTTP
        
        # Парсинг стрічки
        feed = feedparser.parse(response.content)
        
        news_list = []
        # Обробляємо всі наявні записи або до MAX_NEWS_ITEMS
        entries_to_process = feed.entries
        if MAX_NEWS_ITEMS is not None:
             entries_to_process = feed.entries[:MAX_NEWS_ITEMS]

        for entry in entries_to_process:
            # Додаємо лише, якщо є необхідні поля
            title = getattr(entry, 'title', None)
            link = getattr(entry, 'link', None)

            if title and link:
                news_list.append({
                    'title': title,
                    'link': link,
                })

        logger.info(f"Successfully fetched {len(news_list)} items from RSS.")
        return news_list

    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request error for RSS: {req_err}")
    except Exception as e:
        logger.error(f"General error during RSS parsing: {e}")
    
    return []