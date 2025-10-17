import feedparser
import logging

logger = logging.getLogger("RSSParser")

async def fetch_rss_news(rss_url: str) -> list:
    """Парсить RSS-канал і повертає список новин."""
    news_list = []

    logger.info(f"Fetching RSS from: {rss_url}")

    feed = feedparser.parse(rss_url)
    
    logger.info(f"Total entries found in RSS feed: {len(feed.entries)}")

    if feed.entries:
        # ПОВЕРТАЄМО ФІЛЬТР, ЯКИЙ ГАРАНТУЄ СТАБІЛЬНІСТЬ (25 новин)
        for entry in feed.entries:
            title = entry.get('title')
            link = entry.get('link')

            if title and link:
                news_list.append({
                    "title": title,
                    "link": link
                })
        logger.info(f"Successfully parsed {len(news_list)} items from RSS.")
    else:
        logger.warning(f"Could not find any entries in RSS feed: {rss_url}")

    return news_list