"""
Base scraper class providing common functionality for all job platform scrapers.
Handles session management, rate limiting, retry logic, and proxy rotation.
"""

import abc
import random
import time
from typing import Any, Dict, List, Optional

import requests

from utils.logger import get_logger
from utils.user_agents import get_browser_headers
from utils.proxy_rotator import ProxyRotator

logger = get_logger()


class ScrapeResult:
    """Container for a single scraped job listing."""

    def __init__(
        self,
        title: str = "",
        company: str = "",
        location: str = "",
        url: str = "",
        posted_date: str = "",
        salary_range: str = "",
        source_platform: str = "",
        description_snippet: str = "",
    ):
        self.title = title.strip() if title else ""
        self.company = company.strip() if company else ""
        self.location = location.strip() if location else ""
        self.url = url.strip() if url else ""
        self.posted_date = posted_date.strip() if posted_date else ""
        self.salary_range = salary_range.strip() if salary_range else ""
        self.source_platform = source_platform.strip() if source_platform else ""
        self.description_snippet = description_snippet.strip() if description_snippet else ""

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for CSV storage."""
        return {
            "Job Title": self.title,
            "Company Name": self.company,
            "Location": self.location,
            "Job URL": self.url,
            "Posted Date": self.posted_date,
            "Salary Range": self.salary_range,
            "Source Platform": self.source_platform,
            "Description Snippet": self.description_snippet[:200] if self.description_snippet else "",
            "Date Scraped": time.strftime("%Y-%m-%d %H:%M:%S"),
            "Status": "New",
        }

    def __repr__(self) -> str:
        return f"ScrapeResult(title='{self.title}', company='{self.company}', source='{self.source_platform}')"


class BaseScraper(abc.ABC):
    """
    Abstract base class for job platform scrapers.
    Subclasses must implement `build_search_url()` and `parse_response()`.
    """

    def __init__(
        self,
        platform_name: str,
        delay_min: float = 3.0,
        delay_max: float = 6.0,
        max_retries: int = 3,
        use_proxy: bool = False,
        proxy_rotator: Optional[ProxyRotator] = None,
    ):
        self.platform_name = platform_name
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.max_retries = max_retries
        self.use_proxy = use_proxy
        self.proxy_rotator = proxy_rotator or (ProxyRotator(validate_on_start=False) if use_proxy else None)
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create a new requests session with browser-like headers."""
        session = requests.Session()
        session.headers.update(get_browser_headers())
        # Disable SSL warnings for proxy connections
        session.verify = True
        return session

    def _rotate_session(self):
        """Create a new session with fresh headers to avoid fingerprinting."""
        old_session = self.session
        self.session = self._create_session()
        if old_session:
            try:
                old_session.close()
            except Exception:
                pass

    def _polite_delay(self):
        """Sleep for a random duration to avoid rate limiting."""
        delay = random.uniform(self.delay_min, self.delay_max)
        logger.debug(f"Waiting {delay:.1f}s before next request...", module=self.platform_name)
        time.sleep(delay)

    @abc.abstractmethod
    def build_search_url(self, job_title: str, page: int = 1) -> str:
        """
        Build the search URL for a given job title and page.

        Args:
            job_title: The job title to search for
            page: Page number for pagination

        Returns:
            Complete URL string
        """
        pass

    @abc.abstractmethod
    def parse_response(self, html: str, job_title: str) -> List[ScrapeResult]:
        """
        Parse the HTML response and extract job listings.

        Args:
            html: Raw HTML from the search results page
            job_title: The job title that was searched

        Returns:
            List of ScrapeResult objects
        """
        pass

    def make_request(self, url: str) -> Optional[str]:
        """
        Make an HTTP request with retry logic, session rotation, and proxy support.

        Args:
            url: The URL to request

        Returns:
            Response text if successful, None otherwise
        """
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                # Rotate session between retries to avoid fingerprinting
                if attempt > 1:
                    self._rotate_session()
                    logger.debug(f"Retry attempt {attempt}/{self.max_retries}", module=self.platform_name)

                # Prepare request kwargs
                kwargs = {
                    "timeout": 30,
                    "headers": get_browser_headers(),
                }

                # Add proxy if enabled
                if self.use_proxy and self.proxy_rotator:
                    proxy = self.proxy_rotator.get_proxy()
                    if proxy:
                        kwargs["proxies"] = proxy
                        logger.debug(f"Using proxy for request", module=self.platform_name)
                    else:
                        logger.debug("No proxy available, using direct connection", module=self.platform_name)

                # Make the request
                resp = self.session.get(url, **kwargs)

                # Handle rate limiting
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", "60"))
                    logger.warning(
                        f"Rate limited (429). Waiting {retry_after}s...",
                        module=self.platform_name,
                    )
                    time.sleep(retry_after)
                    continue

                # Handle other client/server errors
                if resp.status_code >= 400:
                    logger.warning(
                        f"HTTP {resp.status_code} for {url[:80]}...",
                        module=self.platform_name,
                    )
                    if resp.status_code in (403, 404):
                        # Don't retry on Forbidden or Not Found
                        return None
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue

                # Success
                resp.raise_for_status()
                # Prefer raw bytes decoded as UTF-8 with replacement to avoid codec errors
                try:
                    return resp.content.decode("utf-8", errors="replace")
                except Exception:
                    return resp.text

            except requests.exceptions.ProxyError as ex:
                last_error = ex
                logger.warning(
                    f"Proxy error (attempt {attempt}): {ex}",
                    module=self.platform_name,
                )
                self._rotate_session()
                time.sleep(2)

            except requests.exceptions.ConnectionError as ex:
                last_error = ex
                logger.warning(
                    f"Connection error (attempt {attempt}): {ex}",
                    module=self.platform_name,
                )
                time.sleep(2 ** attempt)

            except requests.exceptions.Timeout as ex:
                last_error = ex
                logger.warning(
                    f"Timeout (attempt {attempt})", module=self.platform_name
                )
                time.sleep(2 ** attempt)

            except requests.exceptions.RequestException as ex:
                last_error = ex
                logger.warning(
                    f"Request error (attempt {attempt}): {ex}",
                    module=self.platform_name,
                )
                time.sleep(2 ** attempt)

        logger.error(
            f"All {self.max_retries} attempts failed for {url[:80]}... Last error: {last_error}",
            module=self.platform_name,
        )
        return None

    def search(self, job_title: str, max_results: int = 50) -> List[ScrapeResult]:
        """
        Search for a job title across multiple pages.

        Args:
            job_title: The job title to search for
            max_results: Maximum number of results to return

        Returns:
            List of ScrapeResult objects
        """
        all_results = []
        page = 1

        while len(all_results) < max_results:
            search_url = self.build_search_url(job_title, page)
            logger.debug(
                f"Searching page {page} for '{job_title}': {search_url[:100]}...",
                module=self.platform_name,
            )

            html = self.make_request(search_url)
            if not html:
                logger.warning(
                    f"No response for page {page} of '{job_title}'",
                    module=self.platform_name,
                )
                break

            page_results = self.parse_response(html, job_title)
            if not page_results:
                logger.debug(
                    f"No results on page {page} for '{job_title}'",
                    module=self.platform_name,
                )
                break

            # Tag results with source platform
            for result in page_results:
                result.source_platform = self.platform_name

            all_results.extend(page_results)
            logger.info(
                f"Page {page}: {len(page_results)} jobs for '{job_title}' (total: {len(all_results)})",
                module=self.platform_name,
            )

            # Polite delay before next page
            self._polite_delay()
            page += 1

            # Safety break to avoid infinite loops
            if page > 20:
                logger.warning(
                    f"Reached page 20 limit for '{job_title}'", module=self.platform_name
                )
                break

        # Trim to max_results
        return all_results[:max_results]