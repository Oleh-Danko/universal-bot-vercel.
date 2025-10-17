import feedparser
import logging

logger = logging.getLogger("RSSParser")

# === ВИДАЛЯЄМО top_n з визначення функції ===
async def fetch_rss_news(rss_url: str) -> list:
    """Парсить RSS-канал і повертає список новин."""
    news_list = []

    logger.info(f"Fetching RSS from: {rss_url}")

    # feedparser робить простий HTTP-запит, який є швидким
    feed = feedparser.parse(rss_url)
    
    # Додаткове логування для діагностики
    logger.info(f"Total entries found in RSS feed: {len(feed.entries)}")

    if feed.entries:
        # === ВИПРАВЛЕННЯ: Видаляємо умову 'if title and link:' ===
        # Це гарантує, що ми включаємо ВСІ 50 елементів, навіть якщо
        # feedparser не може знайти title або link (використовуємо заглушки)
        for entry in feed.entries:
            # Отримуємо заголовок або 'Заголовок відсутній'
            title = entry.get('title', 'Заголовок відсутній')
            # Отримуємо посилання або '#'
            link = entry.get('link', '#')

            # Додаємо елемент БЕЗ ЖОДНИХ УМОВ
            news_list.append({
                "title": title,
                "link": link
            })
            
        logger.info(f"Successfully parsed {len(news_list)} items from RSS.")
    else:
        logger.warning(f"Could not find any entries in RSS feed: {rss_url}")

    return news_list