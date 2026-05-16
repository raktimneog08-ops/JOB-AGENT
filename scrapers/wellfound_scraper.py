"""
WellFound.com (formerly AngelList) scraper.
Uses the public /api/jobs/search endpoint for primary data extraction.
Falls back to sitemap XML parsing when API is rate-limited.
"""

import json
import re
from datetime import datetime
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, ScrapeResult
from utils.logger import get_logger

logger = get_logger()


class WellFoundScraper(BaseScraper):
    """
    Scraper for WellFound.com (AngelList) job listings.
    
    Primary: Public API at /api/jobs/search
    Fallback: Sitemap XML parsing
    
    Note: Full job descriptions require login. We capture what's publicly available.
    """

    BASE_URL = "https://wellfound.com"
    API_URL = "https://wellfound.com/api/jobs/search"
    SITEMAP_URL = "https://wellfound.com/sitemap.xml"

    def __init__(self, delay_min: float = 3.0, delay_max: float = 6.0, use_proxy: bool = False):
        super().__init__(
            platform_name="WellFound",
            delay_min=delay_min,
            delay_max=delay_max,
            use_proxy=use_proxy,
        )

    def build_search_url(self, job_title: str, page: int = 1) -> str:
        """Build WellFound API search URL."""
        return f"{self.API_URL}?query={requests.utils.quote(job_title)}&page={page}"

    def parse_response(self, html: str, job_title: str) -> List[ScrapeResult]:
        """
        Parse WellFound API JSON response.

        Expected API response structure:
        {
            "jobs": [
                {
                    "id": 123,
                    "title": "Senior Frontend Engineer",
                    "company": {
                        "name": "Startup Inc",
                        "location": "San Francisco, CA"
                    },
                    "salary_min": 100000,
                    "salary_max": 150000,
                    "equity_min": 0.01,
                    "equity_max": 0.05,
                    "remote": true,
                    "url": "/jobs/123",
                    "created_at": "2026-05-15T10:00:00Z"
                }
            ]
        }
        """
        results = []

        try:
            data = json.loads(html)
        except json.JSONDecodeError as ex:
            # If JSON fails, try parsing as HTML (sitemap fallback)
            logger.debug(
                f"API response not JSON, trying HTML/sitemap parsing: {ex}",
                module="WellFound",
            )
            return self._parse_sitemap_response(html, job_title)

        jobs = data.get("jobs") or data.get("data", [])
        if not jobs and isinstance(data, list):
            jobs = data

        if not jobs:
            logger.debug("No jobs found in WellFound API response", module="WellFound")
            return results

        for job in jobs:
            try:
                result = self._extract_job_from_api(job)
                if result and result.title and result.company:
                    results.append(result)
            except Exception as ex:
                logger.debug(f"Failed to parse WellFound job: {ex}", module="WellFound")
                continue

        logger.debug(
            f"Parsed {len(results)} jobs from WellFound API for '{job_title}'",
            module="WellFound",
        )
        return results

    def _extract_job_from_api(self, job: dict) -> Optional[ScrapeResult]:
        """Extract job details from a single WellFound API job object."""
        try:
            # Title
            title = job.get("title", "") or job.get("name", "")

            # Company
            company_obj = job.get("company", {}) or job.get("startup", {})
            if isinstance(company_obj, dict):
                company = company_obj.get("name", "")
            else:
                company = str(company_obj) if company_obj else ""

            # Location
            location = ""
            if isinstance(company_obj, dict):
                location = company_obj.get("location", "") or ""
            # Also check top-level location
            if not location:
                location = job.get("location", "") or job.get("locations", "")

            # Determine if remote
            is_remote = job.get("remote", False) or job.get("remote_ok", False)
            if is_remote and location:
                location = f"Remote / {location}"
            elif is_remote:
                location = "Remote"
            elif not location:
                location = "Not specified"

            # Salary range
            salary_min = job.get("salary_min") or job.get("salary_minimal")
            salary_max = job.get("salary_max") or job.get("salary_maximal")
            salary_range = ""
            if salary_min or salary_max:
                parts = []
                if salary_min:
                    parts.append(f"${int(salary_min):,}")
                if salary_max:
                    parts.append(f"${int(salary_max):,}")
                if parts:
                    salary_range = " - ".join(parts)

            # Equity
            equity_min = job.get("equity_min") or job.get("min_equity")
            equity_max = job.get("equity_max") or job.get("max_equity")
            if equity_min or equity_max:
                equity_parts = []
                if equity_min:
                    equity_parts.append(f"{float(equity_min)*100:.1f}%")
                if equity_max:
                    equity_parts.append(f"{float(equity_max)*100:.1f}%")
                if equity_parts:
                    equity_str = " - ".join(equity_parts)
                    if salary_range:
                        salary_range += f" + Equity ({equity_str})"
                    else:
                        salary_range = f"Equity: {equity_str}"

            # Job URL
            job_id = job.get("id")
            job_url = ""
            if job_id:
                job_url = f"{self.BASE_URL}/jobs/{job_id}"
            else:
                url_path = job.get("url", "")
                if url_path:
                    job_url = url_path if url_path.startswith("http") else f"{self.BASE_URL}{url_path}"

            # Posted date
            posted_date = job.get("created_at", "") or job.get("createdAt", "") or job.get("date", "")

            # Description snippet (may be limited without login)
            description = job.get("description", "") or job.get("overview", "") or ""
            if description:
                description = self._clean_text(description)[:200]

            result = ScrapeResult(
                title=title,
                company=company,
                location=location,
                url=job_url,
                posted_date=posted_date,
                salary_range=salary_range,
                description_snippet=description,
            )
            return result

        except Exception as ex:
            logger.debug(f"Error extracting job from API: {ex}", module="WellFound")
            return None

    def _parse_sitemap_response(self, html: str, job_title: str) -> List[ScrapeResult]:
        """Fallback: Parse sitemap XML for job URLs."""
        results = []
        soup = BeautifulSoup(html, "xml")

        # Find all URLs in sitemap
        urls = soup.find_all("url") or soup.find_all("loc")
        if not urls:
            # Try namespaced XML
            urls = soup.find_all("ns0:url") or soup.find_all("ns0:loc")

        # Filter for job URLs
        job_urls = []
        keyword = job_title.lower()
        for url_elem in urls:
            loc = url_elem.find("loc")
            if loc:
                url = loc.get_text(strip=True)
                if "/jobs/" in url and keyword in url.lower():
                    job_urls.append(url)

        # Process each job URL (limited to first 10 to avoid rate limits)
        for url in job_urls[:10]:
            try:
                page_html = self.make_request(url)
                if page_html:
                    result = self._extract_job_from_page(page_html, url)
                    if result:
                        results.append(result)
                    self._polite_delay()
            except Exception as ex:
                logger.debug(f"Failed to fetch job page {url}: {ex}", module="WellFound")
                continue

        return results

    def _extract_job_from_page(self, html: str, url: str) -> Optional[ScrapeResult]:
        """Extract job details from a WellFound job page HTML."""
        try:
            soup = BeautifulSoup(html, "lxml")

            # Title
            title = ""
            title_elem = (
                soup.find("h1")
                or soup.find("meta", {"property": "og:title"})
            )
            if title_elem:
                if title_elem.name == "meta":
                    title = title_elem.get("content", "")
                else:
                    title = title_elem.get_text(strip=True)

            # Company
            company = ""
            company_elem = (
                soup.find("meta", {"property": "og:site_name"})
                or soup.find("a", {"class": lambda x: x and "company" in x.lower()})
            )
            if company_elem:
                if company_elem.name == "meta":
                    company = company_elem.get("content", "")
                else:
                    company = company_elem.get_text(strip=True)

            # Description from meta
            description = ""
            desc_elem = soup.find("meta", {"name": "description"})
            if desc_elem:
                description = desc_elem.get("content", "")

            result = ScrapeResult(
                title=title or "Unknown Position",
                company=company or "Unknown Company",
                location="Not specified",
                url=url,
                posted_date="",
                salary_range="",
                description_snippet=description[:200] if description else "",
            )
            return result

        except Exception as ex:
            logger.debug(f"Error extracting job from page: {ex}", module="WellFound")
            return None

    def _clean_text(self, text: str) -> str:
        """Clean extracted text."""
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def search(self, job_title: str, max_results: int = 50) -> List[ScrapeResult]:
        """Override search to add platform tagging."""
        results = super().search(job_title, max_results)
        for r in results:
            r.source_platform = "WellFound"
        return results