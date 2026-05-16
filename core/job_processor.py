"""
Job deduplication engine.
Uses fuzzy matching on (Job Title + Company Name) to identify and remove duplicate
listings across platforms.
"""

import re
from collections import defaultdict
from typing import Dict, List, Tuple

from thefuzz import fuzz
from thefuzz import process as fuzz_process

from scrapers.base_scraper import ScrapeResult
from utils.logger import get_logger

logger = get_logger()


# Company suffix patterns to normalize
COMPANY_SUFFIXES = [
    r'\s+(?:pvt|private|limited|ltd|llc|llp|inc|incorporated|corp|corporation|gmbh|ag|bv|nv|sa|sl)\.?\s*$',
    r'\s+(?:technologies|technology|tech|solutions|software|systems|services|group)\.?\s*$',
    r'\s+(?:india|us|usa|uk|global|international)\.?\s*$',
]

# Source priority for selecting best duplicate
SOURCE_PRIORITY = {
    "Naukri": 3,
    "RemoteOK": 2,
    "WellFound": 1,
}


def normalize_title(title: str) -> str:
    """
    Normalize a job title for dedup comparison.
    - Lowercase
    - Remove special characters
    - Remove extra whitespace
    - Remove common filler words
    """
    if not title:
        return ""

    title = title.lower().strip()

    # Remove special characters except spaces and hyphens
    title = re.sub(r'[^a-z0-9\s\-/]', '', title)

    # Remove common filler words
    filler_words = [
        r'\bremote\b', r'\b(?:senior|sr)\b', r'\b(?:junior|jr)\b',
        r'\blead\b', r'\bprincipal\b', r'\bstaff\b',
        r'\bengineer\b', r'\bdeveloper\b', r'\bsoftware\b',
    ]
    for pattern in filler_words:
        title = re.sub(pattern, '', title)

    # Normalize whitespace
    title = re.sub(r'\s+', ' ', title).strip()

    return title


def normalize_company(company: str) -> str:
    """
    Normalize company name for dedup comparison.
    - Lowercase
    - Remove legal suffixes (Pvt Ltd, Inc, LLC, etc.)
    - Remove common business words
    """
    if not company:
        return ""

    company = company.lower().strip()
    company = re.sub(r'[^a-z0-9\s\.]', '', company)

    # Remove legal suffixes — loop until stable (handles "Pvt Ltd" -> "Pvt" -> "")
    prev = None
    while prev != company:
        prev = company
        for pattern in COMPANY_SUFFIXES:
            company = re.sub(pattern, '', company)

    # Normalize whitespace
    company = re.sub(r'\s+', ' ', company).strip()

    return company


def get_combined_key(job: ScrapeResult) -> str:
    """Create a normalized combined key for fuzzy matching."""
    title_norm = normalize_title(job.title)
    company_norm = normalize_company(job.company)
    return f"{title_norm}|{company_norm}"


def score_job_completeness(job: ScrapeResult) -> int:
    """
    Score a job based on how complete its fields are.
    Used to pick the best version among duplicates.
    """
    score = 0
    if job.title: score += 10
    if job.company: score += 10
    if job.location and job.location not in ("Not specified", ""): score += 8
    if job.url: score += 5
    if job.posted_date: score += 5
    if job.salary_range: score += 8
    if job.description_snippet and len(job.description_snippet) > 50: score += 5
    # Platform priority bonus
    score += SOURCE_PRIORITY.get(job.source_platform, 0) * 3
    return score


def deduplicate_jobs(
    jobs: List[ScrapeResult],
    threshold: int = 85,
) -> Tuple[List[ScrapeResult], int]:
    """
    Deduplicate a list of jobs using fuzzy matching.

    Args:
        jobs: List of ScrapeResult objects from all platforms
        threshold: Similarity threshold (0-100) for considering jobs as duplicates.
                   Default 85 means 85% similarity required.

    Returns:
        Tuple of (deduplicated_jobs, count_of_duplicates_removed)
    """
    total_jobs = len(jobs)

    if total_jobs <= 1:
        return jobs, 0

    # Build normalized keys for each job
    job_keys = [get_combined_key(job) for job in jobs]
    
    # Group jobs by exact normalized key first (optimization)
    exact_groups: Dict[str, List[int]] = defaultdict(list)
    for idx, key in enumerate(job_keys):
        exact_groups[key].append(idx)

    # For groups with multiple exact matches, just keep the best one
    unique_indices = set()
    duplicates_removed_exact = 0

    for key, indices in exact_groups.items():
        if len(indices) == 1:
            unique_indices.add(indices[0])
        else:
            # Keep the best one among exact matches
            best_idx = max(indices, key=lambda i: score_job_completeness(jobs[i]))
            unique_indices.add(best_idx)
            duplicates_removed_exact += len(indices) - 1

    # Now do fuzzy matching among remaining unique keys
    remaining_indices = sorted(unique_indices)
    remaining_keys = [job_keys[i] for i in remaining_indices]

    # Build fuzzy groups using union-find
    parent = list(range(len(remaining_indices)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[py] = px

    # Compare each pair
    for i in range(len(remaining_indices)):
        for j in range(i + 1, len(remaining_indices)):
            key_i = remaining_keys[i]
            key_j = remaining_keys[j]

            # Quick check: if keys are empty, skip
            if not key_i or not key_j:
                continue

            # Use token_sort_ratio which is more robust for reordered words
            similarity = fuzz.token_sort_ratio(key_i, key_j)

            if similarity >= threshold:
                union(i, j)

    # Collect groups
    groups: Dict[int, List[int]] = defaultdict(list)
    for i in range(len(remaining_indices)):
        root = find(i)
        groups[root].append(i)

    # Select best from each group
    final_indices = []
    for group_indices in groups.values():
        best_in_group = max(
            group_indices,
            key=lambda gi: score_job_completeness(jobs[remaining_indices[gi]])
        )
        final_indices.append(remaining_indices[best_in_group])

    # Count fuzzy duplicates
    duplicates_removed_fuzzy = len(remaining_indices) - len(final_indices)
    total_duplicates = duplicates_removed_exact + duplicates_removed_fuzzy

    # Reconstruct deduplicated list
    deduped = [jobs[i] for i in sorted(final_indices)]

    logger.info(
        f"Deduplication: {total_jobs} → {len(deduped)} jobs "
        f"(removed {total_duplicates} duplicates: "
        f"{duplicates_removed_exact} exact, {duplicates_removed_fuzzy} fuzzy)",
        module="JobProcessor",
    )

    return deduped, total_duplicates


def compute_top_matches(
    jobs: List[ScrapeResult],
    search_titles: List[str],
    priority_keywords: List[str],
    filter_keywords: List[str],
    top_n: int = 5,
) -> List[Dict]:
    """
    Score and rank jobs by relevance to search titles and keywords.

    Args:
        jobs: List of deduplicated jobs
        search_titles: List of job titles searched for (from config)
        priority_keywords: Keywords that give high priority score
        filter_keywords: Keywords that give medium priority score
        top_n: Number of top matches to return

    Returns:
        List of dicts with job info and score, sorted by score descending
    """
    scored = []

    for job in jobs:
        score = 0
        title_lower = job.title.lower()
        company_lower = job.company.lower()

        # Exact match with any search title = highest priority
        for search_title in search_titles:
            if search_title.lower() in title_lower:
                score += 10
                break

        # Priority keywords
        for kw in priority_keywords:
            if kw.lower() in title_lower:
                score += 5
            if kw.lower() in company_lower:
                score += 2

        # Filter keywords
        for kw in filter_keywords:
            if kw.lower() in title_lower:
                score += 2

        # Bonus for having salary info
        if job.salary_range:
            score += 3

        # Bonus for recent posting (rough heuristic)
        if job.posted_date:
            if "day" in job.posted_date.lower() or "hour" in job.posted_date.lower():
                score += 2

        scored.append({
            "job": job,
            "score": score,
        })

    # Sort by score descending, take top N
    scored.sort(key=lambda x: x["score"], reverse=True)

    result = []
    for item in scored[:top_n]:
        result.append({
            "title": item["job"].title,
            "company": item["job"].company,
            "source": item["job"].source_platform,
            "score": item["score"],
            "url": item["job"].url,
        })

    return result