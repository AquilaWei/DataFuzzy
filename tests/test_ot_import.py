from datetime import date

import pytest

from datafuzzy.core.pipeline import Pipeline
from datafuzzy.ot.db import NotFound, RecordStore
from datafuzzy.ot.exchange import (
    ImportMismatch,
    MissingRecord,
    UnrecognizedHeader,
    apply_import,
    export_range,
    parse_pasted,
    preview_import,
)

KEY = bytes(range(32))
OCT_1 = date(2026, 10, 1)
OCT_8 = date(2026, 10, 8)


@pytest.fixture
def store(tmp_path):
    with RecordStore(tmp_path / "t.db", KEY) as s:
        yield s


@pytest.fixture
def pipeline():
    return Pipeline()


@pytest.fixture
def two_visits(store, pipeline):
    """Student 王小明 with a chart on Oct 1 (REC-1) and Oct 8 (REC-2), exported."""
    student = store.add_student("王小明")
    store.add_record(student.id, OCT_1, zh_text="王小明今天練習剪紙")
    store.add_record(student.id, OCT_8, zh_text="王小明今天練習畫畫")
    return export_range(store, OCT_1, OCT_8, pipeline)


FIRST = "=== REC-1 | [PERSON_A] | 2026-10-01 ===\n"
SECOND = "=== REC-2 | [PERSON_A] | 2026-10-08 ===\n"


def test_parse_splits_text_at_headers():
    blocks = parse_pasted(FIRST + "one\n\n" + SECOND + "two\n")
    assert [(b.record_id, b.code, b.visit_date, b.body) for b in blocks] == [
        (1, "[PERSON_A]", "2026-10-01", "one"),
        (2, "[PERSON_A]", "2026-10-08", "two"),
    ]


def test_parse_ignores_text_before_first_header():
    blocks = parse_pasted("Here is the translation:\n\n" + FIRST + "one\n")
    assert [b.record_id for b in blocks] == [1]


def test_parse_accepts_header_with_extra_spaces():
    blocks = parse_pasted("===  REC-1  |  [PERSON_A]  |  2026-10-01  ===\none\n")
    assert [(b.record_id, b.code) for b in blocks] == [(1, "[PERSON_A]")]


def test_parse_keeps_damaged_header_as_block_without_record_id():
    blocks = parse_pasted("=== REC-1 | [PERSON_A] ===\none\n")
    assert [(b.record_id, b.body) for b in blocks] == [(None, "one")]


def test_text_without_headers_parses_to_nothing():
    assert parse_pasted("just some text") == []


def test_round_trip_restores_original_name_in_english_text(store, two_visits):
    pasted = FIRST + "[PERSON_A] practiced cutting paper today.\n\n" + SECOND + "[PERSON_A] practiced drawing.\n"
    preview = preview_import(store, pasted)
    assert [i.en_text for i in preview.items] == [
        "王小明 practiced cutting paper today.",
        "王小明 practiced drawing.",
    ]


def test_round_trip_restores_header_code_to_student_name(store, two_visits):
    preview = preview_import(store, FIRST + "text\n")
    assert preview.items[0].student_name == "王小明"


def test_apply_writes_restored_english_text_to_records(store, two_visits):
    preview = preview_import(store, FIRST + "[PERSON_A] practiced cutting.\n\n" + SECOND + "[PERSON_A] drew.\n")
    written = apply_import(store, preview)
    assert written == 2
    assert [store.get_record(1).en_text, store.get_record(2).en_text] == [
        "王小明 practiced cutting.",
        "王小明 drew.",
    ]


def test_apply_can_write_only_chosen_records(store, two_visits):
    preview = preview_import(store, FIRST + "one\n\n" + SECOND + "two\n")
    apply_import(store, preview, record_ids={2})
    assert [store.get_record(1).en_text, store.get_record(2).en_text] == ["", "two"]


def test_preview_alone_writes_nothing(store, two_visits):
    preview_import(store, FIRST + "one\n")
    assert store.get_record(1).en_text == ""


def test_restore_still_works_with_a_new_store_instance_after_reopening(tmp_path, pipeline):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        student = store.add_student("王小明")
        store.add_record(student.id, OCT_1, zh_text="王小明今天練習剪紙")
        export_range(store, OCT_1, OCT_1, pipeline)
    with RecordStore(path, KEY) as reopened:
        preview = preview_import(reopened, FIRST + "[PERSON_A] practiced.\n")
    assert preview.items[0].en_text == "王小明 practiced."


def test_missing_record_is_reported_when_not_pasted_back(store, two_visits):
    preview = preview_import(store, FIRST + "one\n")
    assert preview.missing == [MissingRecord(2, "王小明", OCT_8)]


def test_nothing_is_missing_when_every_record_is_pasted_back(store, two_visits):
    preview = preview_import(store, FIRST + "one\n\n" + SECOND + "two\n")
    assert preview.missing == []


def test_header_for_unknown_record_is_reported_as_not_in_export(store, two_visits):
    extra = "=== REC-99 | [PERSON_A] | 2026-10-05 ===\n"
    preview = preview_import(store, FIRST + "one\n\n" + extra + "stray\n")
    assert preview.unrecognized == [UnrecognizedHeader(extra.strip(), "not_in_export")]


def test_extra_header_does_not_block_the_valid_ones(store, two_visits):
    preview = preview_import(store, FIRST + "one\n\n=== REC-99 | [PERSON_A] | 2026-10-05 ===\nstray\n")
    assert [i.record_id for i in preview.items] == [1]


def test_changed_code_in_header_is_reported(store, two_visits):
    header = "=== REC-1 | [PERSON_Z] | 2026-10-01 ==="
    preview = preview_import(store, header + "\none\n\n" + SECOND + "two\n")
    assert preview.unrecognized == [UnrecognizedHeader(header, "header_changed")]


def test_changed_date_in_header_is_reported(store, two_visits):
    header = "=== REC-2 | [PERSON_A] | 2026-10-09 ==="
    preview = preview_import(store, FIRST + "one\n\n" + header + "\ntwo\n")
    assert preview.unrecognized == [UnrecognizedHeader(header, "header_changed")]


def test_record_with_changed_header_is_also_missing(store, two_visits):
    preview = preview_import(store, FIRST + "one\n\n=== REC-2 | [PERSON_A] | 2026-10-09 ===\ntwo\n")
    assert [m.record_id for m in preview.missing] == [2]


def test_repeated_record_header_is_reported_as_duplicate(store, two_visits):
    preview = preview_import(store, FIRST + "one\n\n" + FIRST + "again\n")
    assert preview.unrecognized == [UnrecognizedHeader(FIRST.strip(), "duplicate")]
    assert [i.en_text for i in preview.items] == ["one"]


def test_damaged_header_is_reported_as_malformed(store, two_visits):
    preview = preview_import(store, FIRST + "one\n\n=== REC-2 | [PERSON_A] ===\ntwo\n")
    assert preview.unrecognized == [UnrecognizedHeader("=== REC-2 | [PERSON_A] ===", "malformed")]


def test_existing_different_english_text_is_flagged_as_overwrite(store, two_visits):
    store.update_record(1, en_text="old version")
    preview = preview_import(store, FIRST + "new version\n")
    assert [i.record_id for i in preview.overwriting] == [1]


def test_empty_english_text_is_not_an_overwrite(store, two_visits):
    preview = preview_import(store, FIRST + "new version\n")
    assert preview.overwriting == []


def test_identical_english_text_is_not_an_overwrite(store, two_visits):
    store.update_record(1, en_text="same")
    preview = preview_import(store, FIRST + "same\n")
    assert preview.overwriting == []


def test_code_the_export_never_issued_is_listed_as_unknown(store, two_visits):
    preview = preview_import(store, FIRST + "[PERSON_A] met [PERSON_Z]\n")
    assert preview.items[0].unknown_codes == ["[PERSON_Z]"]


def test_text_without_headers_raises_mismatch(store, two_visits):
    with pytest.raises(ImportMismatch):
        preview_import(store, "no headers at all")


def test_headers_matching_no_saved_export_raise_mismatch(store, two_visits):
    with pytest.raises(ImportMismatch):
        preview_import(store, "=== REC-50 | [PERSON_A] | 2026-01-01 ===\ntext\n")


def test_batch_is_found_by_header_even_when_a_newer_batch_exists(store, pipeline):
    a = store.add_student("王小明")
    store.add_record(a.id, OCT_8, zh_text="王小明剪紙")
    first = export_range(store, OCT_8, OCT_8, pipeline)
    b = store.add_student("陳美玲")
    store.add_record(b.id, OCT_1, zh_text="陳美玲畫畫")
    second = export_range(store, OCT_1, OCT_8, pipeline)  # codes now run the other way round
    preview = preview_import(store, first.text)
    assert preview.batch_id == first.batch_id
    assert second.batch_id != first.batch_id
    assert preview.items[0].student_name == "王小明"


def test_explicit_batch_id_overrides_header_search(store, pipeline):
    a = store.add_student("王小明")
    store.add_record(a.id, OCT_1, zh_text="王小明剪紙")
    first = export_range(store, OCT_1, OCT_1, pipeline)
    export_range(store, OCT_1, OCT_1, pipeline)
    assert preview_import(store, FIRST + "x\n", batch_id=first.batch_id).batch_id == first.batch_id


def test_unknown_explicit_batch_id_raises_not_found(store, two_visits):
    with pytest.raises(NotFound):
        preview_import(store, FIRST + "x\n", batch_id=99)


def test_export_translate_import_round_trip_with_classmate_in_text(store, pipeline):
    a = store.add_student("王小明")
    b = store.add_student("陳美玲")
    store.add_record(a.id, OCT_1, zh_text="王小明和陳美玲一起玩")
    store.add_record(b.id, OCT_1, zh_text="陳美玲獨自玩")
    exported = export_range(store, OCT_1, OCT_1, pipeline)
    pasted = exported.text.replace("[PERSON_A]和[PERSON_B]一起玩", "[PERSON_A] played with [PERSON_B]")
    pasted = pasted.replace("[PERSON_B]獨自玩", "[PERSON_B] played alone")
    apply_import(store, preview_import(store, pasted))
    assert [store.get_record(1).en_text, store.get_record(2).en_text] == [
        "王小明 played with 陳美玲",
        "陳美玲 played alone",
    ]
