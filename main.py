#!/usr/bin/env python3
"""
Job Aggregation Agent - Main entry point.
Orchestrates the scraping, deduplication, storage, and notification pipeline.
"""

import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scrapers.remoteok_scraper import RemoteOKScraper
from scrapers.naukri_scraper import NaukriScraper
from scrapers.wellfound_scraper import WellFoundScraper
from scrapers.base_scraper import ScrapeResult

from core.job_processor import deduplicate_jobs, compute_top_matches
from core.storage import (
    get_csv_filename,
    load_existing_jobs,
    save_jobs_to_csv,
    generate_run_id,
)
from core.notifier import send_slack_notification, send_error_notification
from utils.logger import get_logger


def load_config(config_path: str = "config/settings.json") -> dict:
    """Load configuration from JSON file."""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    """Main orchestrator function."""
    start_time = time.time()
    
    # Load configuration
    config = load_config()
    
    # Initialize logger
    log_level = config.get("log_level", "INFO")
    logger = get_logger(log_level)
    
    logger.info("=" * 60, module="Main")
    logger.info("🚀 Job Aggregation Agent Starting", module="Main")
    logger.info(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", module="Main")
    logger.info("=" * 60, module="Main")
    
    # Extract config values
    job_titles = config.get("job_titles", [])
    max_results = config.get("max_results_per_platform", 50)
    output_dir = config.get("csv_output_dir", "data")
    csv_filename_format = config.get("csv_filename_format", "{month_year}_Job_Listings.csv")
    dedup_threshold = config.get("dedup_similarity_threshold", 85)
    priority_keywords = config.get("keywords_priority", [])
    filter_keywords = config.get("keywords_filter", [])
    delay_min = config.get("polite_delay_min_seconds", 3)
    delay_max = config.get("polite_delay_max_seconds", 6)
    
    # Get Slack webhook URL from environment
    slack_webhook_env = config.get("slack_webhook_url_env", "SLACK_WEBHOOK_URL")
    slack_webhook_url = os.environ.get(slack_webhook_env, "")
    
    if not job_titles:
        logger.error("No job titles configured in settings.json", module="Main")
        return
    
    logger.info(f"Job titles to search: {job_titles}", module="Main")
    logger.info(f"Max results per platform: {max_results}", module="Main")
    logger.info(f"Slack webhook: {'Configured' if slack_webhook_url else 'Not configured'}", module="Main")
    
    # Initialize scrapers
    logger.info("Initializing scrapers...", module="Main")
    scrapers = [
        ("RemoteOK", RemoteOKScraper(delay_min=delay_min, delay_max=delay_max, use_proxy=False)),
        ("Naukri", NaukriScraper(delay_min=delay_min + 1, delay_max=delay_max + 2, use_proxy=False)),
        ("WellFound", WellFoundScraper(delay_min=delay_min, delay_max=delay_max, use_proxy=False)),
    ]
    
    # Phase 1: Scrape all platforms
    all_raw_jobs: List[ScrapeResult] = []
    platform_counts: Dict[str, int] = {}
    platform_errors: Dict[str, str] = {}
    
    logger.info("-" * 60, module="Main")
    logger.info("PHASE 1: Scraping job listings", module="Main")
    logger.info("-" * 60, module="Main")
    
    for platform_name, scraper in scrapers:
        logger.info(f"\n  📍 Scraping {platform_name}...", module="Main")
        platform_jobs = []
        
        for title in job_titles:
            try:
                results = scraper.search(title, max_results=max_results // len(job_titles) + 1)
                platform_jobs.extend(results)
                logger.info(
                    f"  ✓ '{title}': {len(results)} results from {platform_name}",
                    module="Main",
                )
            except Exception as ex:
                error_msg = f"Error scraping {platform_name} for '{title}': {ex}"
                logger.error(error_msg, module="Main", exc_info=True)
                platform_errors[platform_name] = str(ex)[:100]
        
        # Deduplicate within the same platform first
        if platform_jobs:
            unique_platform_jobs, internal_dupes = deduplicate_jobs(
                platform_jobs, threshold=dedup_threshold
            )
            all_raw_jobs.extend(unique_platform_jobs)
            platform_counts[platform_name] = len(unique_platform_jobs)
            
            logger.info(
                f"  📊 {platform_name}: {len(platform_jobs)} raw → {len(unique_platform_jobs)} unique "
                f"({internal_dupes} internal duplicates removed)",
                module="Main",
            )
        else:
            platform_counts[platform_name] = 0
            logger.warning(f"  ⚠️ No results from {platform_name}", module="Main")
    
    # Phase 2: Cross-platform deduplication
    logger.info("-" * 60, module="Main")
    logger.info("PHASE 2: Cross-platform deduplication", module="Main")
    logger.info("-" * 60, module="Main")
    
    total_raw = len(all_raw_jobs)
    unique_jobs, total_duplicates = deduplicate_jobs(all_raw_jobs, threshold=dedup_threshold)
    
    logger.info(
        f"📊 Deduplication: {total_raw} → {len(unique_jobs)} unique "
        f"({total_duplicates} duplicates removed)",
        module="Main",
    )
    
    # Phase 3: Save to CSV
    logger.info("-" * 60, module="Main")
    logger.info("PHASE 3: Saving to CSV", module="Main")
    logger.info("-" * 60, module="Main")
    
    csv_path = get_csv_filename(output_dir, csv_filename_format)
    run_id = generate_run_id()
    
    # Load existing jobs to merge
    existing_jobs = load_existing_jobs(csv_path)
    
    # Save new jobs
    new_entries_count = save_jobs_to_csv(
        filepath=csv_path,
        jobs=unique_jobs,
        existing_jobs=existing_jobs,
        run_id=run_id,
    )
    
    total_unique_after_merge = len(existing_jobs) + new_entries_count
    logger.info(
        f"📁 CSV saved to: {csv_path}", module="Main"
    )
    logger.info(
        f"📊 {new_entries_count} new entries added ({total_unique_after_merge} total unique)",
        module="Main",
    )
    
    # Phase 4: Compute top matches
    logger.info("-" * 60, module="Main")
    logger.info("PHASE 4: Computing top matches", module="Main")
    logger.info("-" * 60, module="Main")
    
    top_matches = compute_top_matches(
        jobs=unique_jobs,
        search_titles=job_titles,
        priority_keywords=priority_keywords,
        filter_keywords=filter_keywords,
        top_n=5,
    )
    
    if top_matches:
        logger.info("⭐ Top 5 matching jobs:", module="Main")
        for i, match in enumerate(top_matches, 1):
            logger.info(
                f"  {i}. {match['title']} @ {match['company']} "
                f"({match['source']}) - Score: {match['score']}",
                module="Main",
            )
    else:
        logger.info("No top matches to display", module="Main")
    
    # Phase 5: Send notification
    logger.info("-" * 60, module="Main")
    logger.info("PHASE 5: Sending notification", module="Main")
    logger.info("-" * 60, module="Main")
    
    duration = time.time() - start_time
    overall_status = "✅ Success"
    
    if platform_errors:
        overall_status = "⚠️ Partial (some platforms had errors)"
    
    if slack_webhook_url:
        notification_sent = send_slack_notification(
            webhook_url=slack_webhook_url,
            platform_counts=platform_counts,
            duplicates_removed=total_duplicates,
            top_matches=top_matches,
            new_entries_total=new_entries_count,
            total_unique=total_unique_after_merge,
            duration_seconds=duration,
            status=overall_status,
        )
        if notification_sent:
            logger.info("✅ Slack notification sent", module="Main")
        else:
            logger.warning("⚠️ Failed to send Slack notification", module="Main")
    else:
        logger.info("⏭️ Slack webhook not configured. Skipping notification.", module="Main")
    
    # Summary
    logger.info("=" * 60, module="Main")
    logger.info("📊 RUN SUMMARY", module="Main")
    logger.info("=" * 60, module="Main")
    logger.info(f"  Duration: {_format_duration(duration)}", module="Main")
    logger.info(f"  Status: {overall_status}", module="Main")
    for platform, count in sorted(platform_counts.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"  {platform}: {count} new jobs", module="Main")
    logger.info(f"  Duplicates removed: {total_duplicates}", module="Main")
    logger.info(f"  New entries in CSV: {new_entries_count}", module="Main")
    logger.info(f"  Total unique listings: {total_unique_after_merge}", module="Main")
    logger.info(f"  CSV file: {csv_path}", module="Main")
    logger.info("=" * 60, module="Main")
    
    # Report any errors
    if platform_errors:
        logger.warning("⚠️ Platform Errors:", module="Main")
        for platform, error in platform_errors.items():
            logger.warning(f"  {platform}: {error}", module="Main")
    
    logger.info("✅ Job Agent Run Complete", module="Main")


def _format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


if __name__ == "__main__":
    main()