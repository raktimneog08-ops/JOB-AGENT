"""
CSV storage module for job listings.
Handles reading/writing CSV files, merging with historical data,
and tracking run metadata.
"""

import csv
import io
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Set

from scrapers.base_scraper import ScrapeResult
from utils.logger import get_logger

logger = get_logger()

# CSV column headers
CSV_HEADERS = [
    "Job Title",
    "Company Name",
    "Location",
    "Job URL",
    "Posted Date",
    "Salary Range",
    "Source Platform",
    "Description Snippet",
    "Date Scraped",
    "Status",
    "Run ID",
]

# Default status for new entries
STATUS_NEW = "New"

# Available status options
VALID_STATUSES = {"New", "Applied", "Interviewing", "Rejected", "Offer"}


def get_csv_filename(output_dir: str, filename_format: str = "{month_year}_Job_Listings.csv") -> str:
    """
    Generate CSV filename based on current month and year.

    Args:
        output_dir: Directory where CSV files are stored
        filename_format: Format string with {month_year} placeholder

    Returns:
        Full file path
    """
    now = datetime.now()
    month_year = now.strftime("%B_%Y")  # e.g., "May_2026"
    filename = filename_format.replace("{month_year}", month_year)
    
    # Create directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    return os.path.join(output_dir, filename)


def load_existing_jobs(filepath: str) -> Dict[str, dict]:
    """
    Load existing jobs from a CSV file into a dictionary keyed by Job URL.

    Args:
        filepath: Path to the CSV file

    Returns:
        Dictionary mapping Job URL to row dict
    """
    existing = {}
    
    if not os.path.exists(filepath):
        logger.debug(f"No existing CSV found at {filepath}", module="Storage")
        return existing
    
    try:
        with open(filepath, mode="r", encoding="utf-8", newline="") as f:
            # Filter out comment/metadata lines that start with '#'
            lines = [ln for ln in f.readlines() if not ln.lstrip().startswith("#")]
            if not lines:
                logger.debug(f"CSV {filepath} contains only metadata/comments", module="Storage")
                return existing
            buf = io.StringIO("".join(lines))
            reader = csv.DictReader(buf)
            for row in reader:
                url = (row.get("Job URL") or "").strip()
                if url:
                    existing[url] = row
        
        logger.info(
            f"Loaded {len(existing)} existing jobs from {os.path.basename(filepath)}",
            module="Storage",
        )
    except Exception as ex:
        logger.warning(f"Failed to load existing CSV {filepath}: {ex}", module="Storage")
    
    return existing


def save_jobs_to_csv(
    filepath: str,
    jobs: List[ScrapeResult],
    existing_jobs: Optional[Dict[str, dict]] = None,
    run_id: str = "",
) -> int:
    """
    Save deduplicated jobs to CSV, merging with existing data.

    Args:
        filepath: Path to the CSV file
        jobs: New deduplicated jobs to add
        existing_jobs: Previously stored jobs (keyed by Job URL)
        run_id: Identifier for this run (e.g., "RUN-001")

    Returns:
        Number of new entries added
    """
    if existing_jobs is None:
        existing_jobs = {}
    
    # Track which URLs we've already seen from existing data
    existing_urls: Set[str] = set(existing_jobs.keys())
    new_entries_count = 0
    
    # Combine existing and new jobs
    all_rows = list(existing_jobs.values())
    
    for job in jobs:
        job_dict = job.to_dict()
        job_dict["Run ID"] = run_id
        job_dict["Status"] = STATUS_NEW
        
        url = job_dict.get("Job URL", "").strip()
        
        if url and url in existing_urls:
            # Job already exists - preserve its existing status
            logger.debug(f"Skipping existing job: {job.title} @ {job.company}", module="Storage")
            continue
        
        all_rows.append(job_dict)
        new_entries_count += 1
        if url:
            existing_urls.add(url)
    
    # Write to CSV
    try:
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        
        with open(filepath, mode="w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            writer.writerows(all_rows)
            
            # Append metadata as a comment row
            f.write(f"# Last run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Run ID: {run_id}\n")
            f.write(f"# Total entries: {len(all_rows)}\n")
        
        logger.info(
            f"Saved {len(all_rows)} entries ({new_entries_count} new) to {os.path.basename(filepath)}",
            module="Storage",
        )
    except Exception as ex:
        logger.error(f"Failed to save CSV {filepath}: {ex}", module="Storage", exc_info=True)
        raise
    
    return new_entries_count


def load_jobs_with_status(filepath: str) -> List[Dict]:
    """
    Load all jobs from CSV with their current status.

    Args:
        filepath: Path to CSV file

    Returns:
        List of row dicts with status information
    """
    jobs = []
    
    if not os.path.exists(filepath):
        return jobs
    
    try:
        with open(filepath, mode="r", encoding="utf-8", newline="") as f:
            lines = [ln for ln in f.readlines() if not ln.lstrip().startswith("#")]
            if not lines:
                return jobs
            buf = io.StringIO("".join(lines))
            reader = csv.DictReader(buf)
            for row in reader:
                url = (row.get("Job URL") or "").strip()
                if url:
                    jobs.append(row)
    except Exception as ex:
        logger.warning(f"Failed to load jobs from {filepath}: {ex}", module="Storage")
    
    return jobs


def update_job_status(filepath: str, job_url: str, new_status: str) -> bool:
    """
    Update the status of a specific job in the CSV.

    Args:
        filepath: Path to CSV file
        job_url: The Job URL to update
        new_status: New status value (New, Applied, Interviewing, Rejected, Offer)

    Returns:
        True if update was successful, False otherwise
    """
    if new_status not in VALID_STATUSES:
        logger.warning(
            f"Invalid status '{new_status}'. Valid: {VALID_STATUSES}",
            module="Storage",
        )
        return False
    
    if not os.path.exists(filepath):
        logger.warning(f"CSV {filepath} does not exist", module="Storage")
        return False
    
    try:
        rows = []
        updated = False
        metadata_lines = []
        
        with open(filepath, mode="r", encoding="utf-8", newline="") as f:
            all_lines = f.readlines()
        
        # Separate metadata lines (starting with #) from data lines
        data_lines = []
        for ln in all_lines:
            if ln.lstrip().startswith("#"):
                metadata_lines.append(ln)
            else:
                data_lines.append(ln)
        
        if not data_lines:
            logger.warning(f"CSV {filepath} contains no data rows", module="Storage")
            return False
        
        buf = io.StringIO("".join(data_lines))
        reader = csv.DictReader(buf)
        fieldnames = reader.fieldnames

        for row in reader:
            if (row.get("Job URL") or "").strip() == job_url:
                row["Status"] = new_status
                updated = True
            rows.append(row)
        
        if updated:
            with open(filepath, mode="w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
                # Re-append metadata comment lines
                for meta_line in metadata_lines:
                    f.write(meta_line)
            
            logger.info(f"Updated status for {job_url} to '{new_status}'", module="Storage")
            return True
        else:
            logger.warning(f"Job URL {job_url} not found in {filepath}", module="Storage")
            return False
    
    except Exception as ex:
        logger.error(f"Failed to update status: {ex}", module="Storage")
        return False


def get_last_run_timestamp(filepath: str) -> Optional[str]:
    """
    Extract the last successful run timestamp from CSV metadata.

    Args:
        filepath: Path to CSV file

    Returns:
        Timestamp string if found, None otherwise
    """
    if not os.path.exists(filepath):
        return None
    
    try:
        with open(filepath, mode="r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("# Last run:"):
                    return line.replace("# Last run:", "").strip()
    except Exception:
        pass
    
    return None


def generate_run_id() -> str:
    """
    Generate a unique run ID based on timestamp.
    Format: RUN-YYYYMMDD-HHMMSS
    """
    now = datetime.now()
    return now.strftime("RUN-%Y%m%d-%H%M%S")