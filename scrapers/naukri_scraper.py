"""
Naukri.com scraper.
India-focused job portal. Extracts job listings from search result pages.
Note: Naukri has anti-bot measures. This scraper uses polite delays and 
session rotation. If blocked, results may be partial.
"""

import re
from datetime import datetime
from typing import List, Optional

from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, ScrapeResult
from utils.logger import get_logger

logger = get_logger()


class NaukriScraper(BaseScraper):
    """Scraper for Naukri.com job listings."""

    BASE_URL = "https://www.naukri.com"

    def __init__(self, delay_min: float = 4.0, delay_max: float = 8.0, use_proxy: bool = False):
        super().__init__(
            platform_name="Naukri",
            delay_min=delay_min,
            delay_max=delay_max,
            max_retries=3,
            use_proxy=use_proxy,
        )

    def build_search_url(self, job_title: str, page: int = 1) -> str:
        """Build Naukri search URL."""
        # Convert "Senior Frontend Developer" -> "senior-frontend-developer"
        slug = job_title.lower().replace(" ", "-")
        slug = re.sub(r"[^a-z0-9-]", "", slug)
        return f"{self.BASE_URL}/{slug}-jobs-{page}"

    def parse_response(self, html: str, job_title: str) -> List[ScrapeResult]:
        """
        Parse Naukri HTML to extract job listings.

        Naukri structure (varies by page structure):
        <div class="jobTuple" data-job-id="...">
            <a class="title" href="...">Job Title</a>
            <a class="subTitle" href="...">Company Name</a>
            <li class="location">
                <span>Location</span>
            </li>
            <li class="salary">
                <span>₹5,00,000 - ₹12,00,000 PA</span>
            </li>
            <span class="job-post-day">Posted 2 days ago</span>
            <div class="job-description">Description text...</div>
        </div>
        """
        results = []
        soup = BeautifulSoup(html, "lxml")

        # Try multiple selectors for job cards (Naukri changes class names frequently)
        job_cards = []
        for selector in [
            "div.jobTuple",
            "article.jobTupleHeader",
            "div[class*='jobTuple']",
            "div[class*='job-card']",
            "div[class*='jobCard']",
            "div[class*='list'] > div[class*='job']",
            "section.job-list > article",
        ]:
            job_cards = soup.select(selector)
            if job_cards:
                break

        # Fallback: find any div with a job title link
        if not job_cards:
            job_cards = []
            for anchor in soup.find_all("a", class_="title"):
                parent = anchor.find_parent(["div", "article", "section"])
                if parent and parent not in job_cards:
                    job_cards.append(parent)

        if not job_cards:
            logger.debug("No job cards found in Naukri response", module="Naukri")
            return results

        for card in job_cards:
            try:
                result = self._extract_job_from_card(card)
                if result and result.title and result.company:
                    results.append(result)
            except Exception as ex:
                logger.debug(f"Failed to parse job card: {ex}", module="Naukri")
                continue

        logger.debug(
            f"Parsed {len(results)} jobs from Naukri response",
            module="Naukri",
        )
        return results

    def _extract_job_from_card(self, card) -> Optional[ScrapeResult]:
        """Extract job details from a single job card element."""
        try:
            # Job title
            title = ""
            title_elem = (
                card.find("a", class_="title")
                or card.find("a", {"class": lambda x: x and "title" in x.lower()})
                or card.find("h2")
                or card.find("h3")
            )
            if title_elem:
                title = self._clean_text(title_elem.get_text())

            # Job URL
            job_url = ""
            if title_elem and title_elem.name == "a":
                href = title_elem.get("href", "")
                if href:
                    job_url = href if href.startswith("http") else f"{self.BASE_URL}{href}"

            # Company name
            company = ""
            company_elem = (
                card.find("a", class_="subTitle")
                or card.find("a", {"class": lambda x: x and "subTitle" in x.lower()})
                or card.find("span", class_="company-name")
                or card.find("a", {"class": lambda x: x and "company" in x.lower()})
            )
            if company_elem:
                company = self._clean_text(company_elem.get_text())

            # Location
            location = ""
            location_elem = (
                card.find("li", class_="location")
                or card.find("span", class_="location")
                or card.find("a", {"class": lambda x: x and "loc" in x.lower()})
            )
            if location_elem:
                location_text = location_elem.get_text(strip=True)
                # Clean location text
                location = re.sub(r'\s+', ' ', location_text).strip()

            # Salary range
            salary_range = ""
            salary_elem = (
                card.find("li", class_="salary")
                or card.find("span", class_="salary")
                or card.find("span", {"class": lambda x: x and "salary" in x.lower()})
            )
            if salary_elem:
                salary_range = self._clean_text(salary_elem.get_text())

            # Posted date
            posted_date = ""
            date_elem = (
                card.find("span", class_="job-post-day")
                or card.find("span", {"class": lambda x: x and ("day" in x.lower() or "date" in x.lower() or "posted" in x.lower())})
                or card.find("span", class_="date")
            )
            if date_elem:
                posted_date = self._clean_text(date_elem.get_text())

            # Description snippet
            description_snippet = ""
            desc_elem = (
                card.find("div", class_="job-description")
                or card.find("div", {"class": lambda x: x and "desc" in x.lower()})
                or card.find("span", class_="job-desc")
            )
            if desc_elem:
                description_snippet = self._clean_text(desc_elem.get_text())

            result = ScrapeResult(
                title=title,
                company=company,
                location=location or "India",  # Default for Naukri if no location
                url=job_url,
                posted_date=posted_date,
                salary_range=salary_range,
                description_snippet=description_snippet[:200],
            )
            return result

        except Exception as ex:
            logger.debug(f"Error extracting job from card: {ex}", module="Naukri")
            return None

    def _clean_text(self, text: str) -> str:
        """Clean extracted text."""
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def search(self, job_title: str, max_results: int = 50) -> List[ScrapeResult]:
        """Override search to add platform tagging and handle Naukri-specific patterns."""
        results = super().search(job_title, max_results)
        for r in results:
            r.source_platform = "Naukri"
            # Clean up salary text for consistency
            if r.salary_range:
                r.salary_range = r.salary_range.replace("\u20b9", "₹").replace("PA", "per annum")
        return results