"""
RemoteOK.com scraper.
RemoteOK provides a clean HTML structure with job listings in table rows.
"""

import re
from datetime import datetime
from typing import List, Optional

import json
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper, ScrapeResult
from utils.logger import get_logger

logger = get_logger()


class RemoteOKScraper(BaseScraper):
    """Scraper for RemoteOK.com job listings."""

    BASE_URL = "https://remoteok.com"

    def __init__(self, delay_min: float = 3.0, delay_max: float = 6.0, use_proxy: bool = False):
        super().__init__(
            platform_name="RemoteOK",
            delay_min=delay_min,
            delay_max=delay_max,
            use_proxy=use_proxy,
        )

    def build_search_url(self, job_title: str, page: int = 1) -> str:
        """Build RemoteOK search URL. RemoteOK uses slug-like URL paths."""
        # Use JSON feed for reliable results
        return f"{self.BASE_URL}/remote-jobs.json"

    def parse_response(self, html: str, job_title: str) -> List[ScrapeResult]:
        """
        Parse RemoteOK HTML to extract job listings.

        RemoteOK structure:
        <tr class="job" data-url="/remote-job/...">
            <td class="image"><img/></td>
            <td class="company"><h3>Company</h3></td>
            <td class="position"><h2>Job Title</h2></td>
            <td class="tags">
                <h3>salary</h3>
                <h3>location</h3>
            </td>
            <td class="date"><time datetime="...">...</time></td>
        </tr>
        """
        results = []

        # Try JSON feed first. Some responses include a prefix; try to locate the JSON array start.
        try:
            data = json.loads(html)
        except Exception:
            data = None
            try:
                start = html.find('[')
                if start != -1:
                    data = json.loads(html[start:])
            except Exception:
                data = None

        if isinstance(data, list):
            # First element may be metadata; filter real job objects
            for item in data:
                if not isinstance(item, dict):
                    continue
                # skip metadata entries
                if item.get("last_updated") and item.get("legal"):
                    continue

                title = item.get("position") or item.get("title") or ""
                company = item.get("company") or ""
                location = item.get("location") or item.get("tags") or "Remote"
                slug = item.get("slug") or ""
                job_id = item.get("id") or ""
                job_url = ""
                if slug:
                    job_url = f"{self.BASE_URL}/remote-jobs/{slug}"
                elif job_id:
                    job_url = f"{self.BASE_URL}/remote-jobs/{job_id}"

                description = item.get("description") or ""
                # Basic filtering: match job_title substring in position
                if title and job_title.lower() in title.lower():
                    result = ScrapeResult(
                        title=self._clean_text(title),
                        company=self._clean_text(company),
                        location=(location if isinstance(location, str) else "Remote"),
                        url=job_url,
                        posted_date=item.get("date", ""),
                        salary_range="",
                        description_snippet=self._clean_text(description)[:200],
                    )
                    results.append(result)

            logger.debug(f"Parsed {len(results)} jobs from RemoteOK JSON feed", module="RemoteOK")
            return results

        # Fallback: HTML parsing (legacy)
        soup = BeautifulSoup(html, "lxml")
        job_rows = soup.select("tr.job") or soup.find_all("tr", class_="job")
        if not job_rows:
            logger.debug("No job rows found in RemoteOK HTML response", module="RemoteOK")
            return results

        for row in job_rows:
            try:
                result = self._extract_job_from_row(row)
                if result and result.title and result.company:
                    results.append(result)
            except Exception as ex:
                logger.debug(f"Failed to parse job row: {ex}", module="RemoteOK")
                continue

        logger.debug(f"Parsed {len(results)} jobs from RemoteOK HTML response", module="RemoteOK")
        return results

    def _extract_job_from_row(self, row) -> Optional[ScrapeResult]:
        """Extract job details from a single <tr class='job'> element."""
        try:
            # Job URL
            url_elem = row.get("data-url") or ""
            job_url = f"{self.BASE_URL}{url_elem}" if url_elem else ""

            # Job title - usually in <td class="position"> <h2>
            title = ""
            position_cell = row.find("td", class_="position")
            if position_cell:
                h2 = position_cell.find("h2")
                if h2:
                    title = self._clean_text(h2.get_text())

            # Fallback: try itemprop
            if not title:
                title_elem = row.find("[itemprop='title']")
                if title_elem:
                    title = self._clean_text(title_elem.get_text())

            # Company name
            company = ""
            company_cell = row.find("td", class_="company")
            if company_cell:
                h3 = company_cell.find("h3")
                if h3:
                    company = self._clean_text(h3.get_text())

            # Also check itemprop
            if not company:
                company_elem = row.find("[itemprop='hiringOrganization']")
                if company_elem:
                    company = self._clean_text(company_elem.get_text())

            # Location - RemoteOK jobs are remote, but may specify timezone
            location = "Remote"
            tags_cell = row.find("td", class_="tags")
            if tags_cell:
                tag_items = tags_cell.find_all("h3")
                for tag in tag_items:
                    text = tag.get_text(strip=True)
                    # If tag doesn't look like a salary (no $ or k), it might be location
                    if text and "$" not in text and "k" not in text.lower():
                        if any(zone in text.lower() for zone in ["remote", "us", "eu", "asia", "americas", "worldwide"]):
                            location = text
                            break

            # Salary range - look for salary tags
            salary_range = ""
            if tags_cell:
                tag_items = tags_cell.find_all("h3")
                for tag in tag_items:
                    text = tag.get_text(strip=True)
                    if text and ("$" in text or "k" in text.lower()):
                        salary_range = text
                        break

            # Alternative: look for salary in broader context
            if not salary_range:
                desc_cell = row.find("td", class_="description")
                if desc_cell:
                    text = desc_cell.get_text()
                    salary_match = re.search(r'\$[\d,]+(?:k|K)?(?:\s*-\s*\$?[\d,]+(?:k|K)?)?', text)
                    if salary_match:
                        salary_range = salary_match.group()

            # Posted date
            posted_date = ""
            date_cell = row.find("td", class_="date")
            if date_cell:
                time_elem = date_cell.find("time")
                if time_elem:
                    posted_date = time_elem.get("datetime", "") or time_elem.get_text(strip=True)

            # Description snippet
            description_snippet = ""
            desc_cell = row.find("td", class_="description")
            if not desc_cell:
                desc_cell = row.find("td", {"class": lambda x: x and "description" in x})
            if desc_cell:
                description_snippet = self._clean_text(desc_cell.get_text())

            # Build result
            result = ScrapeResult(
                title=title,
                company=company,
                location=location,
                url=job_url,
                posted_date=posted_date,
                salary_range=salary_range,
                description_snippet=description_snippet[:200],
            )
            return result

        except Exception as ex:
            logger.debug(f"Error extracting job from row: {ex}", module="RemoteOK")
            return None

    def _clean_text(self, text: str) -> str:
        """Clean extracted text by removing extra whitespace."""
        if not text:
            return ""
        # Remove extra whitespace and newlines
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def search(self, job_title: str, max_results: int = 50) -> List[ScrapeResult]:
        """
        Override search to add platform tagging.
        Uses the base class request method with retry/proxy/session support,
        then tries to parse JSON feed first, falling back to HTML parsing.
        """
        # Try JSON feed first via parent's make_request (includes retries, proxy, session)
        url = self.build_search_url(job_title, 1)
        html = self.make_request(url)
        if html:
            try:
                results = self.parse_response(html, job_title)
                for r in results:
                    r.source_platform = "RemoteOK"
                if results:
                    return results[:max_results]
            except Exception:
                pass

        # Fallback to parent implementation (HTML parsing)
        results = super().search(job_title, max_results)
        for r in results:
            r.source_platform = "RemoteOK"
        return results
