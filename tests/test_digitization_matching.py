from pathlib import Path

from api.routers.digitization import _normalized_title


def test_digitization_title_normalization_is_conservative():
    assert _normalized_title("  МАТЕМАТИКА   2 КЛАСС.pdf  ") == "математика 2 класс"
    assert _normalized_title("Ёжик 1 класс.pdf") == "ежик 1 класс"
    assert _normalized_title("Алгебра-7.pdf") != _normalized_title("Алгебра 7.pdf")


def test_worker_does_not_overwrite_on_first_processing():
    source = Path("services/digitization_queue.py").read_text(encoding="utf-8")
    assert 'reset_pages = int(job.get("retry_count") or 0) > 0' in source
    assert "book_not_empty" in source


def test_matching_requires_explicit_batch_confirmation():
    source = Path("api/routers/digitization.py").read_text(encoding="utf-8")
    assert "'matching'" in source
    assert '"/batches/{batch_id}/confirm"' in source
    assert "match_type = 'manual'" in source
    assert "matched_automatic" in source
