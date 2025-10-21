import aiohttp
from bs4 import BeautifulSoup

RSS_SOURCES = [
    "https://epravda.com.ua/finances",
    "https://epravda.com.ua/columns",
    "https://www.reuters.com/business",
    "https://www.reuters.com/markets",
    "https://www.reuters.com/technology",
    "https://www.ft.com/companies",
    "https://www.ft.com/technology",
    "https://www.ft.com/markets",
    "https://www.ft.com/opinion",
    "https://www.bbc.com/business",
]

async def fetch_rss_news():
    results = []
    async with aiohttp.ClientSession() as session:
        for url in RSS_SOURCES:
            try:
                async with session.get(url) as response:
                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")
                    for a in soup.find_all("a", href=True):
                        title = a.get_text(strip=True)
                        link = a["href"]
                        if title and link:
                            results.append({"title": title, "link": link, "source": url})
            except:
                continue
    return results