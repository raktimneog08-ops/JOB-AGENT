"""
Tests for the job deduplication engine.
"""

from scrapers.base_scraper import ScrapeResult
from core.job_processor import (
    deduplicate_jobs,
    compute_top_matches,
    normalize_title,
    normalize_company,
    score_job_completeness,
)


def test_normalize_title_removes_senior_and_engineer():
    """Normalize should strip senior/engineer/developer filler words."""
    result = normalize_title("Senior Frontend Engineer")
    assert "frontend" in result
    assert "senior" not in result
    assert "engineer" not in result


def test_normalize_title_handles_empty():
    """Normalize should handle empty string."""
    assert normalize_title("") == ""
    assert normalize_title(None) == ""


def test_normalize_company_removes_suffixes():
    """Normalize should strip legal suffixes."""
    result = normalize_company("Acme Corp Pvt Ltd")
    assert "acme" in result
    assert "pvt" not in result
    assert "ltd" not in result


def test_normalize_company_handles_empty():
    """Normalize should handle empty string."""
    assert normalize_company("") == ""
    assert normalize_company(None) == ""


def test_score_job_completeness_full():
    """A fully populated job should score highly."""
    job = ScrapeResult(
        title="Senior Dev",
        company="Acme",
        location="Remote",
        url="https://example.com/job1",
        posted_date="2 days ago",
        salary_range="$100k-$150k",
        source_platform="Naukri",
        description_snippet="A" * 100,
    )
    score = score_job_completeness(job)
    assert score > 20


def test_score_job_completeness_empty():
    """An empty job should score very low."""
    job = ScrapeResult()
    score = score_job_completeness(job)
    assert score == 0


def test_deduplication_removes_identical_jobs():
    """Identical jobs should be deduplicated to 1."""
    job1 = ScrapeResult(title="Senior React Dev", company="Google", url="https://a.com/1")
    job2 = ScrapeResult(title="Senior React Dev", company="Google", url="https://a.com/2")
    
    unique, dup_count = deduplicate_jobs([job1, job2], threshold=85)
    assert len(unique) == 1
    assert dup_count == 1


def test_deduplication_keeps_different_jobs():
    """Completely different jobs should both be kept."""
    job1 = ScrapeResult(title="Senior React Dev", company="Google", url="https://a.com/1")
    job2 = ScrapeResult(title="DevOps Engineer", company="Amazon", url="https://b.com/1")
    
    unique, dup_count = deduplicate_jobs([job1, job2], threshold=85)
    assert len(unique) == 2
    assert dup_count == 0


def test_deduplication_handles_single_job():
    """A single job should be returned as-is."""
    job = ScrapeResult(title="Senior React Dev", company="Google", url="https://a.com/1")
    unique, dup_count = deduplicate_jobs([job], threshold=85)
    assert len(unique) == 1
    assert dup_count == 0


def test_deduplication_handles_empty_list():
    """An empty list should return empty."""
    unique, dup_count = deduplicate_jobs([], threshold=85)
    assert len(unique) == 0
    assert dup_count == 0


def test_compute_top_matches_returns_sorted():
    """Top matches should be sorted by score descending."""
    job1 = ScrapeResult(title="React Developer", company="A", source_platform="RemoteOK")
    job2 = ScrapeResult(title="Senior React Developer", company="B", source_platform="Naukri")
    job3 = ScrapeResult(title="Data Scientist", company="C", source_platform="WellFound")
    
    matches = compute_top_matches(
        jobs=[job1, job2, job3],
        search_titles=["React Developer"],
        priority_keywords=["React", "TypeScript"],
        filter_keywords=["React"],
        top_n=3,
    )
    
    assert len(matches) == 3
    # Jobs matching "React Developer" search title should score higher
    assert matches[0]["score"] >= matches[1]["score"]
    assert matches[1]["score"] >= matches[2]["score"]


def test_compute_top_matches_limits_results():
    """Top matches should respect top_n parameter."""
    jobs = [
        ScrapeResult(title=f"Job {i}", company="Acme", source_platform="RemoteOK")
        for i in range(10)
    ]
    matches = compute_top_matches(
        jobs=jobs,
        search_titles=["Job"],
        priority_keywords=[],
        filter_keywords=[],
        top_n=3,
    )
    assert len(matches) == 3


def test_compute_top_matches_empty():
    """Empty job list should return empty matches."""
    matches = compute_top_matches(
        jobs=[],
        search_titles=["React Developer"],
        priority_keywords=[],
        filter_keywords=[],
        top_n=5,
    )
    assert matches == []