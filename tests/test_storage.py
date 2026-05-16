import os
import tempfile
import io
import csv
from core import storage


def test_csv_loader_ignores_comments(tmp_path):
    sample = "# metadata: generated\n# source: test\nJob URL,Job Title,Company Name,Location\nhttps://example.com/job1,Senior Dev,Acme,Remote\n"
    p = tmp_path / "sample.csv"
    p.write_text(sample, encoding="utf-8")

    loaded = storage.load_existing_jobs(str(p))
    assert any('https://example.com/job1' == url for url in loaded.keys())


if __name__ == '__main__':
    import pytest
    pytest.main([__file__])
