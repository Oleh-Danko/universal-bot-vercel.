import requests
import feedparser
import logging

logger = logging.getLogger("RSSParser")

def fetch_rss_news(url: str = "http://feeds.bbci.co.uk/news/world/rss.xml") -> list[dict]:
    """
    Отримує всі доступні новини з RSS-стрічки.
    Без жодного обмеження — повертає повний список feed.entries.
    """
    try:
        # Отримання RSS
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # Парсинг RSS через feedparser
        feed = feedparser.parse(response.content)
        news_list = []

        for entry in feed.entries:
            title = getattr(entry, 'title', None)
            link = getattr(entry, 'link', None)
            summary = getattr(entry, 'summary', '')
            published = getattr(entry, 'published', '')

            if title and link:
                news_list.append({
                    "title": title,
                    "link": link,
                    "summary": summary,
                    "published": published,
                    "source": feed.feed.get("title", "Unknown Source")
                })

        logger.info(f"✅ Завантажено {len(news_list)} новин із RSS: {url}")
        return news_list

    except Exception as e:
        logger.error(f"❌ Помилка під час парсингу RSS ({url}): {e}")
        return []