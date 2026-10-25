from datetime import date

import pytest

from datafuzzy.core.pipeline import Pipeline
from datafuzzy.ot.db import RecordStore
from datafuzzy.ot.exchange import export_range

KEY = bytes(range(32))


@pytest.fixture
def store(tmp_path):
    with RecordStore(tmp_path / "t.db", KEY) as s:
        yield s


@pytest.fixture
def pipeline():
    """No model installed: only the built-in rules run."""
    return Pipeline()


def test_export_wraps_each_record_in_a_header_with_id_code_and_date(store, pipeline):
    student = store.add_student("王小明")
    store.add_record(student.id, date(2026, 10, 1), zh_text="今天王小明在教室練習剪紙")
    result = export_range(store, date(2026, 10, 1), date(2026, 10, 1), pipeline)
    assert result.text == "=== REC-1 | [PERSON_A] | 2026-10-01 ===\n今天[PERSON_A]在教室練習剪紙\n"


def test_students_name_is_masked_without_any_model(store, pipeline):
    student = store.add_student("林曉華")
    store.add_record(student.id, date(2026, 10, 1), zh_text="林曉華今天很專心，曉華完成了作業")
    result = export_range(store, date(2026, 10, 1), date(2026, 10, 1), pipeline)
    assert pipeline.pii is None and pipeline.models == {}
    assert "林曉華" not in result.text and "曉華" not in result.text


def test_english_student_name_is_masked_in_chinese_text(store, pipeline):
    student = store.add_student("Kevin Lee")
    store.add_record(student.id, date(2026, 10, 1), zh_text="今天 Kevin Lee 練習握筆，Kevin 很開心")
    result = export_range(store, date(2026, 10, 1), date(2026, 10, 1), pipeline)
    assert "Kevin" not in result.text and "Lee" not in result.text


def test_only_names_are_coded_other_details_stay_readable(store, pipeline):
    student = store.add_student("王小明")
    store.add_record(student.id, date(2026, 10, 1), zh_text="王小明 家長信箱 mom@example.com")
    result = export_range(store, date(2026, 10, 1), date(2026, 10, 1), pipeline)
    assert "mom@example.com" in result.text


def test_same_student_gets_same_code_in_every_record(store, pipeline):
    student = store.add_student("王小明")
    store.add_record(student.id, date(2026, 10, 1), zh_text="王小明剪紙")
    store.add_record(student.id, date(2026, 10, 8), zh_text="王小明畫畫")
    result = export_range(store, date(2026, 10, 1), date(2026, 10, 8), pipeline)
    assert result.text.count("[PERSON_A]") == 4


def test_different_students_get_different_codes(store, pipeline):
    a = store.add_student("王小明")
    b = store.add_student("陳美玲")
    store.add_record(a.id, date(2026, 10, 1), zh_text="王小明剪紙")
    store.add_record(b.id, date(2026, 10, 1), zh_text="陳美玲畫畫")
    result = export_range(store, date(2026, 10, 1), date(2026, 10, 1), pipeline)
    assert "=== REC-1 | [PERSON_A] | 2026-10-01 ===\n[PERSON_A]剪紙" in result.text
    assert "=== REC-2 | [PERSON_B] | 2026-10-01 ===\n[PERSON_B]畫畫" in result.text


def test_other_student_named_in_a_record_is_masked_even_if_exported_earlier(store, pipeline):
    a = store.add_student("王小明")
    b = store.add_student("陳美玲")
    store.add_record(a.id, date(2026, 10, 1), zh_text="王小明和陳美玲一起玩")
    store.add_record(b.id, date(2026, 10, 2), zh_text="陳美玲獨自玩")
    result = export_range(store, date(2026, 10, 1), date(2026, 10, 2), pipeline)
    assert "陳美玲" not in result.text


def test_only_records_in_range_are_exported_oldest_first(store, pipeline):
    student = store.add_student("王小明")
    store.add_record(student.id, date(2026, 10, 9), zh_text="第三")
    store.add_record(student.id, date(2026, 10, 1), zh_text="第一")
    store.add_record(student.id, date(2026, 10, 5), zh_text="第二")
    result = export_range(store, date(2026, 10, 1), date(2026, 10, 5), pipeline)
    assert result.text == (
        "=== REC-2 | [PERSON_A] | 2026-10-01 ===\n第一\n\n"
        "=== REC-3 | [PERSON_A] | 2026-10-05 ===\n第二\n"
    )


def test_empty_range_exports_nothing_and_saves_no_batch(store, pipeline):
    student = store.add_student("王小明")
    store.add_record(student.id, date(2026, 10, 1), zh_text="王小明")
    result = export_range(store, date(2026, 11, 1), date(2026, 11, 30), pipeline)
    assert (result.text, result.batch_id, result.record_count) == ("", None, 0)
    assert store.batches() == []


def test_export_does_not_change_the_stored_chinese_text(store, pipeline):
    student = store.add_student("王小明")
    record = store.add_record(student.id, date(2026, 10, 1), zh_text="王小明剪紙")
    export_range(store, date(2026, 10, 1), date(2026, 10, 1), pipeline)
    assert store.get_record(record.id).zh_text == "王小明剪紙"


def test_export_saves_code_mapping_in_encrypted_batch(store, pipeline):
    student = store.add_student("王小明")
    store.add_record(student.id, date(2026, 10, 1), zh_text="王小明剪紙")
    result = export_range(store, date(2026, 10, 1), date(2026, 10, 1), pipeline)
    batch = store.get_batch(result.batch_id)
    assert batch.data["session"]["to_code"]["王小明"] == "[PERSON_A]"


def test_export_batch_is_not_plaintext_in_database_file(store, pipeline):
    student = store.add_student("王小明")
    store.add_record(student.id, date(2026, 10, 1), zh_text="王小明剪紙")
    export_range(store, date(2026, 10, 1), date(2026, 10, 1), pipeline)
    assert "王小明".encode() not in store.path.read_bytes()
