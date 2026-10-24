from core.text_utils import clean_answer, format_size, safe_filename, slugify


def test_slugify_basic():
    assert slugify("Physics") == "physics"
    assert slugify("Organic Chemistry!") == "organic-chemistry"
    assert slugify("  AP Calc 2  ") == "ap-calc-2"


def test_slugify_strips_punctuation():
    assert slugify("C++ Basics") == "c-basics"
    assert slugify("---Hello---") == "hello"


def test_clean_answer_removes_citation_markers():
    raw = "Newton's laws apply here.【source】 See the notes.【1†L1-L3】"
    assert "【" not in clean_answer(raw)
    assert "Newton's laws apply here." in clean_answer(raw)
    assert clean_answer(raw).endswith("See the notes.")


def test_clean_answer_trims_whitespace():
    assert clean_answer("  hello  ") == "hello"


def test_safe_filename_strips_path():
    assert safe_filename("/etc/passwd") == "passwd"
    assert safe_filename(None) == "untitled"


def test_format_size():
    assert format_size(500) == "500 B"
    assert format_size(2048).endswith("KB")
