"""
Naukri.com scraper.
India-focused job portal. Extracts job listings from search result pages.
Note: Naukri has anti-bot measures. This scraper uses polite delays and 
session rotation. If blocked, results may be partial.
"""

import re
import os
from datetime import datetime
from typing import List, Optional

import json

import requests
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
        """Build Naukri API search URL."""
        # Use the jobapi/v2/search endpoint directly
        keyword = job_title.lower()
        return f"{self.BASE_URL}/jobapi/v2/search?keyword={requests.utils.quote(keyword)}&pageNo={page}"

    def parse_response(self, html: str, job_title: str) -> List[ScrapeResult]:
        """
        Parse Naukri API JSON response to extract job listings.

        The API returns JSON, not HTML. If JSON parsing fails,
        it falls back to HTML parsing (for Firecrawl fallback responses).
        """
        results = []

        # Try JSON API response first
        try:
            data = json.loads(html)
            job_list = data.get("list", [])
            if not job_list:
                logger.debug("No jobs list in Naukri API response", module="Naukri")
                return results

            for item in job_list:
                try:
                    result = self._extract_job_from_api_item(item)
                    if result and result.title and result.company:
                        # Apply keyword filter: only include if job title matches
                        if job_title.lower() in result.title.lower():
                            results.append(result)
                except Exception as ex:
                    logger.debug(f"Failed to parse Naukri API item: {ex}", module="Naukri")
                    continue

            logger.debug(
                f"Parsed {len(results)} jobs from Naukri API for '{job_title}'",
                module="Naukri",
            )
            return results
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback: parse as HTML (Firecrawl rendered pages, legacy)
        soup = BeautifulSoup(html, "lxml")
        job_cards = []
        for selector in [
            "div.srp-jobtuple-wrapper",
            "div.cust-job-tuple",
            "div.srp-jobtuple-wrapper[data-job-id]",
            "div.jobTuple",
            "article.jobTupleHeader",
            "div[class*='jobTuple']",
        ]:
            job_cards = soup.select(selector)
            if job_cards:
                break

        if not job_cards:
            job_cards = []
            for anchor in soup.find_all("a", class_="title"):
                parent = anchor.find_parent(["div", "article", "section"])
                if parent and parent not in job_cards:
                    job_cards.append(parent)

        if not job_cards:
            logger.debug("No job cards found in Naukri HTML response", module="Naukri")
            return results

        for card in job_cards:
            try:
                result = self._extract_job_from_card(card)
                if result and result.title and result.company:
                    results.append(result)
            except Exception as ex:
                logger.debug(f"Failed to parse job card: {ex}", module="Naukri")
                continue

        logger.debug(f"Parsed {len(results)} jobs from Naukri HTML", module="Naukri")
        return results

    def _extract_job_from_api_item(self, item: dict) -> Optional[ScrapeResult]:
        """Extract job details from a single Naukri API job item."""
        try:
            title = item.get("JOB_SPEC", "") or item.get("post", "")
            if not title:
                return None

            company = item.get("companyName", "") or item.get("staticCompanyName", "")

            location = item.get("city", "") or item.get("locality", "")

            salary_range = ""
            min_sal = item.get("minSal")
            max_sal = item.get("maxSal")
            if (min_sal is not None and min_sal != 0) or (max_sal is not None and max_sal != 0):
                parts = []
                if min_sal and min_sal != 0:
                    parts.append(f"₹{int(min_sal):,}")
                if max_sal and max_sal != 0:
                    parts.append(f"₹{int(max_sal):,}")
                if parts:
                    salary_range = " - ".join(parts)

            posted_date = item.get("addDate", "") or item.get("dateAdded", "")

            # Build job URL: Naukri uses jobId to construct URL
            job_id = item.get("jobId") or item.get("REFNO")
            if job_id:
                job_url = f"{self.BASE_URL}/job-details/{job_id}"
            else:
                job_url = ""

            description = item.get("jobDesc", "") or item.get("tupleDesc", "")

            result = ScrapeResult(
                title=self._clean_text(title),
                company=self._clean_text(company),
                location=self._clean_text(location) or "India",
                url=job_url,
                posted_date=posted_date,
                salary_range=salary_range,
                description_snippet=self._clean_text(description)[:200],
            )
            return result

        except Exception as ex:
            logger.debug(f"Error extracting from Naukri API item: {ex}", module="Naukri")
            return None

    def _extract_job_from_card(self, card) -> Optional[ScrapeResult]:
        """Extract job details from a single job card element."""
        try:
            # Job title
            title = ""
            title_elem = (
                card.select_one("a.title")
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
                card.select_one("a.comp-name")
                or card.select_one("a.comp-name.mw-25")
                or card.find("a", class_="subTitle")
                or card.find("span", class_="company-name")
                or card.find("a", {"class": lambda x: x and "company" in x.lower()})
            )
            if company_elem:
                company = self._clean_text(company_elem.get_text())

            # Location
            location = ""
            location_elem = (
                card.select_one("span.locWdth")
                or card.select_one("span.location")
                or card.find("li", class_="location")
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
                card.select_one("span.sal-wrap")
                or card.select_one("span[title*='Lacs']")
                or card.find("li", class_="salary")
                or card.find("span", class_="salary")
                or card.find("span", {"class": lambda x: x and "salary" in x.lower()})
            )
            if salary_elem:
                salary_range = self._clean_text(salary_elem.get_text())

            # Posted date
            posted_date = ""
            date_elem = (
                card.select_one("span.job-post-day")
                or card.find("span", {"class": lambda x: x and ("day" in x.lower() or "date" in x.lower() or "posted" in x.lower())})
                or card.find("span", class_="date")
            )
            if date_elem:
                posted_date = self._clean_text(date_elem.get_text())

            # Description snippet
            description_snippet = ""
            desc_elem = (
                card.select_one("span.job-desc")
                or card.find("div", class_="job-description")
                or card.find("div", {"class": lambda x: x and "desc" in x.lower()})
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
        """Override search to call the Naukri job API directly with proper JSON headers."""
        all_results = []
        page = 1

        while len(all_results) < max_results:
            api_url = self.build_search_url(job_title, page)
            logger.debug(f"Naukri API request: {api_url}", module="Naukri")

            # The API requires JSON Accept header
            from utils.user_agents import get_random_user_agent
            api_headers = {
                "User-Agent": get_random_user_agent(),
                "Accept": "application/json",
                "Referer": "https://www.naukri.com/",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
            }
            # Temporarily patch session headers for this request
            old_headers = dict(self.session.headers)
            self.session.headers.update(api_headers)
            try:
                html = self.make_request(api_url)
            finally:
                # Restore original headers
                self.session.headers.update(old_headers)

            if not html:
                logger.warning(f"No response from Naukri API for '{job_title}' page {page}", module="Naukri")
                break

            page_results = self.parse_response(html, job_title)
            for r in page_results:
                r.source_platform = "Naukri"
                if r.salary_range:
                    r.salary_range = r.salary_range.replace("\u20b9", "₹").replace("PA", "per annum")
            all_results.extend(page_results)

            if len(page_results) < 5:
                # Few results, likely no more pages
                break

            self._polite_delay()
            page += 1
            if page > 20:
                break

        results = all_results[:max_results]

        # If no results from simple requests-based parsing, try Firecrawl JS-rendered fallback
        if not results:
            from utils.firecrawl_client import get_firecrawl_client
            firecrawl = get_firecrawl_client()
            
            if firecrawl.available:
                logger.info("No results; attempting Firecrawl-rendered fetch for Naukri.", module="Naukri")
                search_url = self.build_search_url(job_title, 1)
                html = firecrawl.scrape_url(search_url)
                
                if html:
                    page_results = self.parse_response(html, job_title)
                    for r in page_results:
                        r.source_platform = "Naukri"
                        if r.salary_range:
                            r.salary_range = r.salary_range.replace("\u20b9", "₹").replace("PA", "per annum")
                    results.extend(page_results)
                else:
                    logger.warning("Firecrawl returned no content for Naukri search.", module="Naukri")
            else:
                logger.warning(
                    "Firecrawl not available (FIRECRAWL_API_KEY not set). "
                    "Skipping JS-rendered Naukri fallback.",
                    module="Naukri",
                )

        return results[:max_results]