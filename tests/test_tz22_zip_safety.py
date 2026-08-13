from api.routers.digitization import _normalized_title, _safe_name


def test_safe_name_strips_paths():
    assert _safe_name("../../Русский язык.pdf") == "Русский язык.pdf"
    assert _safe_name("folder\\Math.pdf") == "Math.pdf"


def test_normalized_title_matches_filename_and_book_title():
    assert _normalized_title("Математика 1 класс.pdf") == _normalized_title("Математика 1 класс")
