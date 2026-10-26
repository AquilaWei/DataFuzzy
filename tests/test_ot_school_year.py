from datetime import date

from datafuzzy.ot.school_year import default_school_year, format_school_year, parse_school_year


def test_autumn_belongs_to_the_school_year_starting_that_september():
    assert default_school_year(date(2026, 10, 26)) == (date(2026, 9, 1), date(2027, 6, 1))


def test_spring_belongs_to_the_school_year_that_started_the_september_before():
    assert default_school_year(date(2027, 3, 1)) == (date(2026, 9, 1), date(2027, 6, 1))


def test_august_already_belongs_to_the_coming_school_year():
    assert default_school_year(date(2026, 8, 15)) == (date(2026, 9, 1), date(2027, 6, 1))


def test_school_year_is_written_as_month_slash_year_range():
    assert format_school_year(date(2026, 9, 1), date(2027, 6, 1)) == "09/2026-06/2027"


def test_school_year_text_reads_back():
    assert parse_school_year(" 9/2026 - 06/2027 ") == (date(2026, 9, 1), date(2027, 6, 1))


def test_unreadable_school_year_gives_none():
    assert parse_school_year("2026-2027") is None
    assert parse_school_year("13/2026-06/2027") is None
