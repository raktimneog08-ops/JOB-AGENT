"""
Firecrawl client wrapper for the job aggregation agent.
Provides JS-rendered page scraping as a fallback when simple HTTP scraping fails.
Requires FIRECRAWL_API_KEY environment variable to be set.
"""

import os
import time
from typing import Optional

from utils.logger import get_logger

logger = get_logger()


class FirecrawlClient:
    """
    Thin wrapper around FirecrawlApp for scraping JS-rendered pages.
    Used as a fallback when anti-bot measures block direct HTTP scraping.

    API key is read from FIRECRAWL_API_KEY environment variable.
    If not configured, the client is disabled and returns None for all calls.
    """

    def __init__(self):
        self.api_key = os.environ.get("FIRECRAWL_API_KEY", "")
        self._client = None
        self._initialized = False

    @property
    def available(self) -> bool:
        """Check if Firecrawl is configured and available."""
        return bool(self.api_key)

    def _get_client(self):
        """Lazy-init the FirecrawlApp client."""
        if not self._initialized:
            if not self.api_key:
                logger.warning(
                    "FIRECRAWL_API_KEY not set. Firecrawl fallback disabled.",
                    module="Firecrawl",
                )
                self._initialized = True
                return None
            try:
                from firecrawl import FirecrawlApp
                self._client = FirecrawlApp(api_key=self.api_key)
                logger.info("Firecrawl client initialized", module="Firecrawl")
            except ImportError:
                logger.warning(
                    "firecrawl-py package not installed. Install with: pip install firecrawl-py",
                    module="Firecrawl",
                )
            except Exception as ex:
                logger.warning(
                    f"Failed to initialize Firecrawl client: {ex}",
                    module="Firecrawl",
                )
            self._initialized = True
        return self._client

    def scrape_url(self, url: str) -> Optional[str]:
        """
        Scrape a URL using Firecrawl's JS-rendered scraping.

        Args:
            url: The URL to scrape

        Returns:
            Rendered HTML as string, or None if failed
        """
        client = self._get_client()
        if not client:
            return None

        try:
            logger.debug(f"Firecrawl scraping: {url[:100]}...", module="Firecrawl")
            result = client.scrape_url(url, params={"pageOptions": {"onlyMainContent": False}})

            if not result:
                logger.debug(f"Firecrawl returned empty result for {url[:100]}", module="Firecrawl")
                return None

            # Firecrawl returns a dict with 'content' or 'html' key
            html = result.get("content") or result.get("html") or ""
            if html:
                logger.debug(f"Firecrawl scraped {len(html)} bytes from {url[:100]}", module="Firecrawl")
                return html
            else:
                logger.debug(f"Firecrawl returned no HTML content for {url[:100]}", module="Firecrawl")
                return None

        except Exception as ex:
            logger.warning(f"Firecrawl scrape failed for {url[:100]}: {ex}", module="Firecrawl")
            return None


# Global singleton instance
_firecrawl_instance: Optional[FirecrawlClient] = None


def get_firecrawl_client() -> FirecrawlClient:
    """Get or create the global Firecrawl client instance."""
    global _firecrawl_instance
    if _firecrawl_instance is None:
        _firecrawl_instance = FirecrawlClient()
    return _firecrawl_instance