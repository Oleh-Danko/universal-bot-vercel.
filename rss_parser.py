import feedparser
import logging

logger = logging.getLogger("RSSParser")

async def fetch_rss_news(rss_url: str) -> list:
    """Парсить RSS-канал і повертає список новин, обробляючи до 50 елементів."""
    news_list = []

    logger.info(f"Fetching RSS from: {rss_url}")

    feed = feedparser.parse(rss_url)
    
    # BBC RSS-стрічки часто містять до 50 елементів
    total_entries = len(feed.entries)
    logger.info(f"Total entries found in RSS feed: {total_entries}")

    if total_entries:
        # Ітеруємо по всіх знайдених елементах
        for entry in feed.entries:
            # Використовуємо .get() для безпечного доступу, надаючи заглушки
            title = entry.get('title', 'Заголовок відсутній')
            link = entry.get('link', '#')

            # Додаємо елемент, лише якщо є хоча б один ключовий компонент (заголовок або посилання)
            if title != 'Заголовок відсутній' or link != '#':
                news_list.append({
                    "title": title,
                    "link": link
                })
        
        logger.info(f"Successfully parsed {len(news_list)} items from RSS.")
    else:
        logger.warning(f"Could not find any entries in RSS feed: {rss_url}")

    return news_list