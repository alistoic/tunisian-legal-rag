from src.ingestion.cleaner import (clean_text, normalize_arabic,
                                   strip_jort_headers)


def test_strip_jort_headers():
    raw = ("Journal Officiel de la République Tunisienne\n"
           "Article premier — test\n"
           "Page 12\n")
    out = strip_jort_headers(raw)
    assert "Journal Officiel" not in out
    assert "Page 12" not in out
    assert "Article premier" in out


def test_normalize_arabic_diacritics():
    assert normalize_arabic("الأَوَّل") == "الاول"


def test_normalize_arabic_digits():
    assert normalize_arabic("الفصل ٨٨") == "الفصل 88"


def test_normalize_arabic_alef():
    assert normalize_arabic("أحمد") == "احمد"
    assert normalize_arabic("إبراهيم") == "ابراهيم"


def test_clean_text_collapses_whitespace():
    assert clean_text("a   b\n\n\n\nc") == "a b\n\nc"
