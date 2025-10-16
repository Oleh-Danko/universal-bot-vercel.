# bloomberg_parser.py
import asyncio
import logging
from typing import List, Optional

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("bloomberg_parser")

# optional libs
try:
    import cloudscraper
except Exception:
    cloudscraper = None

try:
    from bs4 import BeautifulSoup
except Exception:
    raise

try:
    from playwright.async_api import async_playwright
except Exception:
    async_playwright = None

BLOOMBERG_URL = "https://www.bloomberg.com/"

async def fetch_bloomberg(top_n: int = 10) -> List[str]:
    """
    Adaptive fetcher:
      - Try cloudscraper (fast)
      - If HTML looks blocked or too short -> fallback to playwright (rendered DOM)
    Returns list of titles (strings), up to top_n.
    Logs first 500 chars of HTML for diagnosis.
    """
    html = ""
    # 1) cloudscraper
    if cloudscraper:
        try:
            LOG.info("[cloudscraper] trying cloudscraper.get")
            scraper = cloudscraper.create_scraper()
            resp = scraper.get(BLOOMBERG_URL, timeout=15)
            resp.raise_for_status()
            html = resp.text or ""
            LOG.info("[cloudscraper] received %d chars", len(html))
        except Exception as e:
            LOG.warning("[cloudscraper] error: %s", e)
            html = ""

    # Quick heuristics to detect protection or empty fetch
    blocked_indicators = ["Please enable JavaScript", "Cloudflare", "bot", "captcha", "Access Denied"]
    if not html or any(ind.lower() in html[:1000].lower() for ind in blocked_indicators) or len(html) < 1500:
        LOG.info("[fetch_bloomberg] cloudscraper failed/suspicious -> trying Playwright fallback")
        html = ""

        if async_playwright:
            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
                    context = await browser.new_context(user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                    ))
                    page = await context.new_page()
                    await page.goto(BLOOMBERG_URL, wait_until="networkidle", timeout=30000)
                    # small delay to allow dynamic content to mount
                    await asyncio.sleep(1.0)
                    html = await page.content()
                    await browser.close()
                    LOG.info("[playwright] received %d chars", len(html) if html else 0)
            except Exception as e:
                LOG.warning("[playwright] error: %s", e)
                html = ""
        else:
            LOG.warning("[fetch_bloomberg] playwright not available in runtime")

    # Diagnostic preview: first 500 chars
    preview = (html or "")[:500].replace("\n", " ").replace("\r", " ")
    LOG.info("[DIAGNOSTIC] HTML preview (first 500 chars):\n%s", preview)

    if not html:
        LOG.error("[fetch_bloomberg] final HTML empty -> cannot parse")
        return []

    # Parse with BeautifulSoup
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        LOG.exception("BeautifulSoup parse error: %s", e)
        return []

    candidates = _extract_candidates_from_soup(soup)
    if not candidates:
        LOG.warning("[fetch_bloomberg] no candidates found after extraction")
    # return top_n
    return candidates[:top_n]


def _extract_candidates_from_soup(soup) -> List[str]:
    """
    Robust extraction:
      - meta og:title
      - elements with data-component-type containing 'Headline'
      - links with '/news/' or '/article/'
      - h1/h2/h3 tags
      - class name patterns headline/story/title
    Returns ordered list (deduped).
    """
    seen = set()
    out = []

    def add(text: str):
        if not text:
            return
        t = " ".join(text.split()).strip()
        if len(t) < 8:
            return
        key = t.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(t)

    # meta og:title
    for meta in soup.find_all("meta", attrs={"property": "og:title"}):
        content = meta.get("content")
        add(content)

    # data-component-type headlines
    for el in soup.find_all(attrs={"data-component-type": True}):
        attr = el.get("data-component-type", "")
        if "headline" in attr.lower() or "Headline" in attr:
            add(el.get_text(strip=True))

    # links to /news/ or /article/
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/news/" in href or "/article/" in href:
            add(a.get_text(strip=True))

    # h1/h2/h3 tags
    for tag in soup.find_all(["h1", "h2", "h3"]):
        add(tag.get_text(strip=True))

    # class pattern fallback
    patterns = ["headline", "story", "title", "article"]
    for p in patterns:
        for el in soup.find_all(class_=lambda c: c and p in c.lower()):
            add(el.get_text(strip=True))

    return out