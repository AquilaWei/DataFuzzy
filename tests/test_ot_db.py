import os
import sqlite3
from datetime import date, datetime

import pytest

from datafuzzy.ot import APP_NAME
from datafuzzy.ot.crypto import Cipher, DecryptionError
from datafuzzy.ot.db import DB_ENV, DuplicateRecord, NotFound, RecordStore, StudentProfile, default_db_path

KEY = bytes(range(32))


@pytest.fixture
def store(tmp_path):
    with RecordStore(tmp_path / "t.db", KEY) as s:
        yield s


def test_app_name_is_theranote():
    assert APP_NAME == "TheraNote"


def test_db_path_follows_environment_override(monkeypatch, tmp_path):
    monkeypatch.setenv(DB_ENV, str(tmp_path / "x.db"))
    assert default_db_path() == tmp_path / "x.db"


def test_db_path_defaults_to_user_data_folder(monkeypatch):
    monkeypatch.delenv(DB_ENV, raising=False)
    assert default_db_path().name == "theranote.db"
    assert "TheraNote" in default_db_path().parts


def test_added_student_is_listed(store):
    student = store.add_student("王小明")
    assert store.students() == [student]


def test_students_are_sorted_by_name(store):
    store.add_student("Cathy")
    store.add_student("albert")
    store.add_student("Bob")
    assert [s.name for s in store.students()] == ["albert", "Bob", "Cathy"]


def test_empty_student_name_is_rejected(store):
    with pytest.raises(ValueError):
        store.add_student("  ")


def test_renamed_student_keeps_id(store):
    student = store.add_student("王小名")
    store.rename_student(student.id, "王小明")
    assert store.get_student(student.id).name == "王小明"


def test_deleting_a_student_removes_their_records(store):
    wang = store.add_student("王小明")
    chen = store.add_student("陳美玲")
    store.add_record(wang.id, date(2026, 10, 1), "A校", "王")
    store.add_record(chen.id, date(2026, 10, 1), "A校", "陳")
    store.delete_student(wang.id)
    assert [s.name for s in store.students()] == ["陳美玲"]
    assert [r.student_id for r in store.records_on(date(2026, 10, 1))] == [chen.id]


def test_deleting_an_unknown_student_raises_not_found(store):
    with pytest.raises(NotFound):
        store.delete_student(99)


def test_new_student_has_an_empty_profile(store):
    student = store.add_student("王小明")
    assert store.get_profile(student.id) == StudentProfile()


def test_profile_is_saved_trimmed(store):
    student = store.add_student("王小明")
    store.set_profile(student.id, StudentProfile(diagnosis=" ADHD, ODD ", age="8", grade="3",
                                                 classroom="301", case_manager="Ms. Lee",
                                                 school_year="09/2026-06/2027", goals="Fine motor\n"))
    assert store.get_profile(student.id) == StudentProfile(
        diagnosis="ADHD, ODD", age="8", grade="3", classroom="301", case_manager="Ms. Lee",
        school_year="09/2026-06/2027", goals="Fine motor")


def test_profile_is_stored_encrypted(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        student = store.add_student("王小明")
        store.set_profile(student.id, StudentProfile(diagnosis="ADHD"))
    assert b"ADHD" not in path.read_bytes()


def test_profile_of_an_unknown_student_raises_not_found(store):
    with pytest.raises(NotFound):
        store.set_profile(99, StudentProfile())


def test_chart_book_from_before_profiles_opens_with_empty_profile(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        student = store.add_student("王小明")
    old = sqlite3.connect(path)
    old.execute("ALTER TABLE student DROP COLUMN profile")
    old.commit()
    old.close()
    with RecordStore(path, KEY) as again:
        assert again.get_profile(student.id) == StudentProfile()


def test_unknown_student_raises_not_found(store):
    with pytest.raises(NotFound):
        store.get_student(99)


def test_added_record_is_read_back_unchanged(store):
    student = store.add_student("王小明")
    added = store.add_record(student.id, date(2026, 10, 1), "新竹國小", "今天練習剪紙 cutting", "")
    assert store.get_record(added.id) == added
    assert added.location == "新竹國小"
    assert added.zh_text == "今天練習剪紙 cutting"


def test_student_can_have_records_on_several_dates(store):
    student = store.add_student("王小明")
    store.add_record(student.id, date(2026, 10, 1))
    store.add_record(student.id, date(2026, 10, 8))
    assert len(store.records_for_student(student.id)) == 2


def test_second_record_on_same_day_raises_duplicate_with_existing_id(store):
    student = store.add_student("王小明")
    first = store.add_record(student.id, date(2026, 10, 1))
    with pytest.raises(DuplicateRecord) as e:
        store.add_record(student.id, date(2026, 10, 1))
    assert e.value.record_id == first.id


def test_two_students_can_share_a_date(store):
    a = store.add_student("甲")
    b = store.add_student("乙")
    store.add_record(a.id, date(2026, 10, 1))
    store.add_record(b.id, date(2026, 10, 1))
    assert len(store.records_on(date(2026, 10, 1))) == 2


def test_record_for_unknown_student_raises_not_found(store):
    with pytest.raises(NotFound):
        store.add_record(99, date(2026, 10, 1))


def test_update_changes_only_the_given_field(store):
    student = store.add_student("王小明")
    record = store.add_record(student.id, date(2026, 10, 1), "A校", "中文", "English")
    updated = store.update_record(record.id, zh_text="新的中文")
    assert (updated.location, updated.zh_text, updated.en_text) == ("A校", "新的中文", "English")


def test_update_keeps_only_latest_english_text(store):
    student = store.add_student("王小明")
    record = store.add_record(student.id, date(2026, 10, 1), en_text="v1")
    store.update_record(record.id, en_text="v2")
    assert store.get_record(record.id).en_text == "v2"


def test_update_sets_updated_at_from_clock(tmp_path):
    times = iter([datetime(2026, 10, 1, 9), datetime(2026, 10, 1, 10)])
    with RecordStore(tmp_path / "t.db", KEY, now=lambda: next(times)) as store:
        student = store.add_student("王小明")
        record = store.add_record(student.id, date(2026, 10, 1))
        updated = store.update_record(record.id, zh_text="x")
    assert (record.updated_at, updated.updated_at) == (datetime(2026, 10, 1, 9), datetime(2026, 10, 1, 10))


def test_update_of_unknown_record_raises_not_found(store):
    with pytest.raises(NotFound):
        store.update_record(99, zh_text="x")


def test_set_en_texts_writes_all_records(store):
    student = store.add_student("王小明")
    a = store.add_record(student.id, date(2026, 10, 1))
    b = store.add_record(student.id, date(2026, 10, 2))
    store.set_en_texts({a.id: "one", b.id: "two"})
    assert [store.get_record(a.id).en_text, store.get_record(b.id).en_text] == ["one", "two"]


def test_set_en_texts_writes_nothing_when_one_id_is_unknown(store):
    student = store.add_student("王小明")
    a = store.add_record(student.id, date(2026, 10, 1))
    with pytest.raises(NotFound):
        store.set_en_texts({a.id: "one", 99: "two"})
    assert store.get_record(a.id).en_text == ""


def test_records_for_student_newest_first(store):
    student = store.add_student("王小明")
    for day in (5, 1, 9):
        store.add_record(student.id, date(2026, 10, day))
    assert [r.visit_date.day for r in store.records_for_student(student.id)] == [9, 5, 1]


def test_records_for_student_oldest_first(store):
    student = store.add_student("王小明")
    for day in (5, 1, 9):
        store.add_record(student.id, date(2026, 10, day))
    assert [r.visit_date.day for r in store.records_for_student(student.id, newest_first=False)] == [1, 5, 9]


def test_students_on_date_lists_only_that_days_students(store):
    a = store.add_student("甲")
    b = store.add_student("乙")
    store.add_record(a.id, date(2026, 10, 1))
    store.add_record(b.id, date(2026, 10, 2))
    assert store.students_on(date(2026, 10, 1)) == [a]


def test_students_on_date_without_records_is_empty(store):
    store.add_student("甲")
    assert store.students_on(date(2026, 10, 1)) == []


def test_dates_with_records_are_marked(store):
    a = store.add_student("甲")
    store.add_record(a.id, date(2026, 10, 1))
    store.add_record(a.id, date(2026, 11, 3))
    assert store.dates_with_records() == {date(2026, 10, 1), date(2026, 11, 3)}


def test_dates_with_records_can_be_limited_to_a_month(store):
    a = store.add_student("甲")
    store.add_record(a.id, date(2026, 10, 1))
    store.add_record(a.id, date(2026, 11, 3))
    assert store.dates_with_records(date(2026, 11, 1), date(2026, 11, 30)) == {date(2026, 11, 3)}


def test_records_between_includes_both_ends_oldest_first(store):
    a = store.add_student("甲")
    for day in (1, 2, 3, 4):
        store.add_record(a.id, date(2026, 10, day))
    found = store.records_between(date(2026, 10, 2), date(2026, 10, 3))
    assert [r.visit_date.day for r in found] == [2, 3]


def test_default_location_is_latest_visit_by_date_not_by_entry_order(store):
    a = store.add_student("甲")
    store.add_record(a.id, date(2026, 10, 8), "新校")
    store.add_record(a.id, date(2026, 10, 1), "舊校")
    assert store.student_default_location(a.id) == "新校"


def test_default_location_skips_visits_without_location(store):
    a = store.add_student("甲")
    store.add_record(a.id, date(2026, 10, 1), "舊校")
    store.add_record(a.id, date(2026, 10, 8), "")
    assert store.student_default_location(a.id) == "舊校"


def test_default_location_of_new_student_is_empty(store):
    a = store.add_student("甲")
    assert store.student_default_location(a.id) == ""


def test_default_location_is_per_student(store):
    a = store.add_student("甲")
    b = store.add_student("乙")
    store.add_record(a.id, date(2026, 10, 1), "A校")
    assert store.student_default_location(b.id) == ""


def test_default_start_time_is_latest_visit_that_has_one(store):
    a = store.add_student("甲")
    b = store.add_student("乙")
    first = store.add_record(a.id, date(2026, 10, 1))
    store.update_record(first.id, start_time="09:30")
    store.add_record(a.id, date(2026, 10, 8))
    assert (store.student_default_start_time(a.id), store.student_default_start_time(b.id)) == (
        "09:30", "")


def test_add_record_keeps_the_start_time(store):
    a = store.add_student("甲")
    record = store.add_record(a.id, date(2026, 10, 1), start_time="14:00")
    assert (record.start_time, store.get_record(record.id).start_time) == ("14:00", "14:00")


def test_all_locations_are_distinct_most_recent_first(store):
    a = store.add_student("甲")
    store.add_record(a.id, date(2026, 10, 1), "A校")
    store.add_record(a.id, date(2026, 10, 2), "B校")
    store.add_record(a.id, date(2026, 10, 3), "A校")
    assert store.all_locations() == ["A校", "B校"]


def test_data_survives_reopening_the_database(tmp_path):
    with RecordStore(tmp_path / "t.db", KEY) as store:
        student = store.add_student("王小明")
        store.add_record(student.id, date(2026, 10, 1), "新竹國小", "中文版", "English")
    with RecordStore(tmp_path / "t.db", KEY) as again:
        record = again.records_for_student(student.id)[0]
    assert (record.location, record.zh_text, record.en_text) == ("新竹國小", "中文版", "English")


def test_database_file_contains_no_plaintext(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        student = store.add_student("王小明")
        store.add_record(student.id, date(2026, 10, 1), "新竹國小", "今天練習剪紙", "practiced cutting")
        store.add_batch({"to_code": {"王小明": "[PERSON_A]"}})
    raw = path.read_bytes()
    assert [s.encode() in raw for s in ("王小明", "新竹國小", "今天練習剪紙", "practiced cutting")] == [False] * 4


def test_database_file_is_private_to_the_user(tmp_path):
    path = tmp_path / "t.db"
    RecordStore(path, KEY).close()
    assert os.stat(path).st_mode & 0o777 == 0o600


def test_opening_with_wrong_key_raises_decryption_error(tmp_path):
    RecordStore(tmp_path / "t.db", KEY).close()
    with pytest.raises(DecryptionError):
        RecordStore(tmp_path / "t.db", bytes(32))


def test_reading_with_wrong_key_raises_decryption_error(store):
    student = store.add_student("王小明")
    store._cipher = Cipher(bytes(32))  # as if the stored data were from another key
    with pytest.raises(DecryptionError):
        store.get_student(student.id)


def test_batch_round_trips_encrypted_after_reopen(tmp_path):
    with RecordStore(tmp_path / "t.db", KEY) as store:
        batch_id = store.add_batch({"to_code": {"王小明": "[PERSON_A]"}})
    with RecordStore(tmp_path / "t.db", KEY) as again:
        assert again.get_batch(batch_id).data == {"to_code": {"王小明": "[PERSON_A]"}}


def test_unknown_batch_raises_not_found(store):
    with pytest.raises(NotFound):
        store.get_batch(99)


def test_deleted_record_is_gone(store):
    student = store.add_student("王小明")
    record = store.add_record(student.id, date(2026, 10, 1))
    store.delete_record(record.id)
    assert store.records_for_student(student.id) == []
    assert store.dates_with_records() == set()


def test_deleting_one_record_keeps_the_others(store):
    student = store.add_student("王小明")
    first = store.add_record(student.id, date(2026, 10, 1))
    second = store.add_record(student.id, date(2026, 10, 8))
    store.delete_record(first.id)
    assert store.records_for_student(student.id) == [second]


def test_deleting_unknown_record_raises_not_found(store):
    with pytest.raises(NotFound):
        store.delete_record(99)


def test_activity_is_saved_and_read_back(store):
    student = store.add_student("王小明")
    record = store.add_record(student.id, date(2026, 10, 1), activity="串珠、剪紙")
    assert store.get_record(record.id).activity == "串珠、剪紙"


def test_update_changes_activity_and_keeps_the_texts(store):
    student = store.add_student("王小明")
    record = store.add_record(student.id, date(2026, 10, 1), "新竹國小", "中文", "English")
    store.update_record(record.id, activity="平衡木")
    again = store.get_record(record.id)
    assert (again.activity, again.location, again.zh_text, again.en_text) == ("平衡木", "新竹國小", "中文", "English")


def test_set_en_texts_keeps_the_activity(store):
    student = store.add_student("王小明")
    record = store.add_record(student.id, date(2026, 10, 1), activity="串珠")
    store.set_en_texts({record.id: "Beading"})
    assert store.get_record(record.id).activity == "串珠"


def test_activity_is_not_plaintext_in_database_file(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        student = store.add_student("王小明")
        store.add_record(student.id, date(2026, 10, 1), activity="感覺統合鞦韆")
    assert "感覺統合鞦韆".encode() not in path.read_bytes()


def test_chart_book_from_before_activities_opens_with_empty_activity(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        student = store.add_student("王小明")
        record = store.add_record(student.id, date(2026, 10, 1), zh_text="舊病歷")
    old = sqlite3.connect(path)
    old.execute("ALTER TABLE record DROP COLUMN activity")
    old.commit()
    old.close()
    with RecordStore(path, KEY) as again:
        assert (again.get_record(record.id).zh_text, again.get_record(record.id).activity) == ("舊病歷", "")
        again.update_record(record.id, activity="新活動")
        assert again.get_record(record.id).activity == "新活動"


def test_excel_folder_is_kept_encrypted_and_survives_reopen(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        assert store.excel_folder() == ""
        store.set_excel_folder("/Users/ot/新竹")
        store.set_excel_folder("/Users/ot/hsinchu")
    assert b"hsinchu" not in path.read_bytes()
    with RecordStore(path, KEY) as again:
        assert again.excel_folder() == "/Users/ot/hsinchu"


def test_moved_record_keeps_its_texts_on_the_new_day(store):
    student = store.add_student("王小明")
    record = store.add_record(student.id, date(2026, 10, 1), "A校", "中文", "English", activity="剪紙")
    store.move_record(record.id, date(2026, 10, 2))
    moved = store.get_record(record.id)
    assert moved.visit_date == date(2026, 10, 2)
    assert (moved.zh_text, moved.en_text, moved.activity) == ("中文", "English", "剪紙")
    assert store.find_record(student.id, date(2026, 10, 1)) is None


def test_record_cannot_move_onto_a_day_already_taken(store):
    student = store.add_student("王小明")
    first = store.add_record(student.id, date(2026, 10, 1))
    other = store.add_record(student.id, date(2026, 10, 2))
    with pytest.raises(DuplicateRecord) as e:
        store.move_record(first.id, date(2026, 10, 2))
    assert e.value.record_id == other.id
    assert store.get_record(first.id).visit_date == date(2026, 10, 1)


def test_start_time_is_saved_cleared_and_kept_by_other_updates(store):
    student = store.add_student("王小明")
    record = store.add_record(student.id, date(2026, 10, 1))
    assert record.start_time == ""
    store.update_record(record.id, start_time="09:30")
    store.update_record(record.id, zh_text="中文")
    store.set_en_texts({record.id: "English"})
    assert store.get_record(record.id).start_time == "09:30"
    store.update_record(record.id, start_time="")
    assert store.get_record(record.id).start_time == ""


def test_chart_book_from_before_start_times_opens_with_none(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        student = store.add_student("王小明")
        record = store.add_record(student.id, date(2026, 10, 1), zh_text="舊病歷")
    old = sqlite3.connect(path)
    old.execute("ALTER TABLE record DROP COLUMN start_time")
    old.commit()
    old.close()
    with RecordStore(path, KEY) as again:
        assert again.get_record(record.id).start_time == ""
        again.update_record(record.id, start_time="14:00")
        assert again.get_record(record.id).start_time == "14:00"
