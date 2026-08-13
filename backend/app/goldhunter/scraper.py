import httpx
from bs4 import BeautifulSoup
import logging
from typing import Optional

logger = logging.getLogger(__name__)

async def fetch_url_content(url: str) -> Optional[str]:
    """
    Fetches the visible text content of a URL for Gold Hunter auditing.
    Extracts Title, H1, Meta description, and all paragraph text.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Remove scripts and styles
            for script in soup(["script", "style", "noscript", "header", "footer", "nav"]):
                script.extract()
                
            title = soup.title.string if soup.title else ""
            meta_desc = ""
            desc_tag = soup.find("meta", attrs={"name": "description"})
            if desc_tag and desc_tag.get("content"):
                meta_desc = desc_tag["content"]
                
            h1 = soup.find("h1")
            h1_text = h1.get_text(separator=" ", strip=True) if h1 else ""
            
            body_text = soup.get_text(separator=" ", strip=True)
            
            content = f"Title: {title}\nMeta Description: {meta_desc}\nH1: {h1_text}\nBody:\n{body_text[:10000]}"
            return content
            
    except Exception as e:
        logger.error(f"Failed to fetch {url} for Gold Hunter: {e}")
        return None
