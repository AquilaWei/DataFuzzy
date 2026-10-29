import json
import os
import sqlite3
from datetime import date, datetime

import pytest

from datafuzzy.ot import APP_NAME
from datafuzzy.ot.crypto import Cipher, DecryptionError
from datafuzzy.ot.db import (
    DB_ENV,
    DuplicateRecord,
    NotFound,
    Plan,
    RecordStore,
    Session,
    StudentProfile,
    default_db_path,
    default_end_time,
    parse_plan_date,
    split_goals,
)

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
                                                 school_year="09/2026-06/2027",
                                                 goals=(" Fine motor\n", "  ", "Self-care"),
                                                 plan_date=" 10/15/2026 "))
    assert store.get_profile(student.id) == StudentProfile(
        diagnosis="ADHD, ODD", age="8", grade="3", classroom="301", case_manager="Ms. Lee",
        school_year="09/2026-06/2027", goals=("Fine motor", "Self-care"), plan_date="10/15/2026")


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


def test_default_slot_is_the_latest_same_weekday_visits(store):
    a = store.add_student("甲")
    store.add_record(a.id, date(2026, 10, 2), start_time="14:00", end_time="14:45")  # Friday
    store.add_record(a.id, date(2026, 10, 5), start_time="09:00", end_time="09:30")  # Monday
    assert store.student_default_slot(a.id, date(2026, 10, 9)) == ("14:00", "14:45")


def test_default_slot_takes_the_most_recent_of_several_same_weekday_visits(store):
    a = store.add_student("甲")
    store.add_record(a.id, date(2026, 10, 2), start_time="14:00", end_time="14:45")
    store.add_record(a.id, date(2026, 10, 9), start_time="15:00", end_time="15:40")
    assert store.student_default_slot(a.id, date(2026, 10, 16)) == ("15:00", "15:40")


def test_default_slot_skips_same_weekday_visits_without_a_time(store):
    a = store.add_student("甲")
    store.add_record(a.id, date(2026, 10, 2), start_time="14:00", end_time="14:45")
    store.add_record(a.id, date(2026, 10, 9))
    assert store.student_default_slot(a.id, date(2026, 10, 16)) == ("14:00", "14:45")


def test_default_slot_from_a_visit_without_an_end_lasts_thirty_minutes(store):
    a = store.add_student("甲")
    store.add_record(a.id, date(2026, 10, 2), start_time="14:00")
    assert store.student_default_slot(a.id, date(2026, 10, 9)) == ("14:00", "14:30")


def test_default_slot_without_a_same_weekday_visit_is_the_latest_start(store):
    a = store.add_student("甲")
    store.add_record(a.id, date(2026, 10, 2), start_time="14:00", end_time="14:45")  # Friday
    store.add_record(a.id, date(2026, 10, 5), start_time="09:00", end_time="10:00")  # Monday
    assert store.student_default_slot(a.id, date(2026, 10, 7)) == ("09:00", "09:30")  # Wednesday


def test_default_slot_of_a_new_student_is_empty(store):
    a = store.add_student("甲")
    assert store.student_default_slot(a.id, date(2026, 10, 9)) == ("", "")


def test_add_record_keeps_the_start_time(store):
    a = store.add_student("甲")
    record = store.add_record(a.id, date(2026, 10, 1), start_time="14:00")
    assert (record.start_time, store.get_record(record.id).start_time) == ("14:00", "14:00")


def test_student_location_is_the_profiles(store):
    a = store.add_student("甲")
    store.add_record(a.id, date(2026, 10, 1), "舊校")
    store.set_profile(a.id, StudentProfile(location="新校"))
    assert store.student_location(a.id) == "新校"


def test_student_location_without_one_in_the_profile_is_the_latest_visits(store):
    a = store.add_student("甲")
    store.add_record(a.id, date(2026, 10, 1), "舊校")
    assert store.student_location(a.id) == "舊校"


def test_all_locations_include_ones_only_set_in_a_profile(store):
    a = store.add_student("甲")
    store.add_record(a.id, date(2026, 10, 1), "A校")
    store.set_profile(store.add_student("乙").id, StudentProfile(location="C校"))
    assert store.all_locations() == ["A校", "C校"]


def test_students_at_a_location_are_those_seen_there_then_those_located_there(store):
    a, b, c = (store.add_student(n) for n in ("甲", "乙", "丙"))
    store.add_record(a.id, date(2026, 10, 1), "A校")
    store.add_record(b.id, date(2026, 10, 2), "A校")
    store.set_profile(c.id, StudentProfile(location="A校"))
    assert store.students_at("A校") == [b.id, a.id, c.id]


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


def test_default_end_time_is_thirty_minutes_after_the_start():
    assert default_end_time("09:45") == "10:15"


def test_default_end_time_stays_within_the_day():
    assert default_end_time("23:45") == "23:59"


def test_no_start_time_gives_no_default_end_time():
    assert default_end_time("") == ""


def test_end_time_is_saved_and_kept_by_other_updates(store):
    student = store.add_student("王小明")
    record = store.add_record(student.id, date(2026, 10, 1), start_time="09:30", end_time="10:00")
    store.update_record(record.id, end_time="10:15")
    store.update_record(record.id, start_time="09:45")
    assert store.get_record(record.id).end_time == "10:15"


def make_old_book(path, drop_end_time=False):
    """Mark the chart book as one from before end times were filled in."""
    old = sqlite3.connect(path)
    if drop_end_time:
        old.execute("ALTER TABLE record DROP COLUMN end_time")
    else:
        old.execute("UPDATE record SET end_time = NULL")
    old.execute("PRAGMA user_version = 0")
    old.commit()
    old.close()


def test_chart_book_from_before_end_times_gets_ends_30_minutes_after_the_start(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        student = store.add_student("王小明")
        record = store.add_record(student.id, date(2026, 10, 1), start_time="09:30")
    make_old_book(path, drop_end_time=True)
    with RecordStore(path, KEY) as again:
        assert again.get_record(record.id).end_time == "10:00"


def test_filling_end_times_leaves_charts_without_a_start_empty(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        student = store.add_student("王小明")
        record = store.add_record(student.id, date(2026, 10, 1), zh_text="沒填時間")
    make_old_book(path)
    with RecordStore(path, KEY) as again:
        assert (again.get_record(record.id).end_time, again.get_record(record.id).zh_text) == ("", "沒填時間")


def test_filling_end_times_keeps_the_end_within_the_day(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        student = store.add_student("王小明")
        record = store.add_record(student.id, date(2026, 10, 1), start_time="23:45")
    make_old_book(path)
    with RecordStore(path, KEY) as again:
        assert again.get_record(record.id).end_time == "23:59"


def test_filling_end_times_keeps_ends_already_set(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        student = store.add_student("王小明")
        record = store.add_record(student.id, date(2026, 10, 1), start_time="09:30", end_time="10:15")
    old = sqlite3.connect(path)
    old.execute("PRAGMA user_version = 0")
    old.commit()
    old.close()
    with RecordStore(path, KEY) as again:
        assert again.get_record(record.id).end_time == "10:15"


def test_end_times_are_filled_only_once(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        student = store.add_student("王小明")
        record = store.add_record(student.id, date(2026, 10, 1), start_time="09:30")
    old = sqlite3.connect(path)
    old.execute("UPDATE record SET end_time = NULL")  # cleared by hand after the fill
    old.commit()
    old.close()
    with RecordStore(path, KEY) as again:
        assert again.get_record(record.id).end_time == ""


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


def test_profile_keeps_any_number_of_session_times_sorted(store):
    student = store.add_student("王小明")
    store.set_profile(student.id, StudentProfile(sessions=(Session(4, "10:00", "10:30"), Session(0, "14:00", "14:30"),
                                                           Session(4, "09:00", "09:30"))))
    assert store.get_profile(student.id).sessions == (
        Session(0, "14:00", "14:30"), Session(4, "09:00", "09:30"), Session(4, "10:00", "10:30"))


def test_profile_from_before_session_times_has_none(store):
    student = store.add_student("王小明")
    store.set_profile(student.id, StudentProfile(diagnosis="ADHD"))
    assert store.get_profile(student.id).sessions == ()


def test_a_session_time_on_the_weekday_comes_before_past_visits(store):
    student = store.add_student("王小明")
    store.add_record(student.id, date(2026, 10, 2), start_time="14:00", end_time="14:45")  # Friday
    store.set_profile(student.id, StudentProfile(sessions=(Session(4, "10:00", "10:30"),)))
    assert store.student_default_slot(student.id, date(2026, 10, 9)) == ("10:00", "10:30")


def test_without_a_session_time_on_the_weekday_past_visits_are_used(store):
    student = store.add_student("王小明")
    store.add_record(student.id, date(2026, 10, 5), start_time="09:00", end_time="09:30")  # Monday
    store.set_profile(student.id, StudentProfile(sessions=(Session(4, "10:00", "10:30"),)))
    assert store.student_default_slot(student.id, date(2026, 10, 12)) == ("09:00", "09:30")


def test_students_are_active_by_default(store):
    assert store.add_student("王小明").active
    assert store.students()[0].active


def test_a_student_can_be_made_inactive_and_active_again(store):
    student = store.add_student("王小明")
    store.set_active(student.id, False)
    assert not store.get_student(student.id).active
    store.set_active(student.id, True)
    assert store.get_student(student.id).active


def test_making_an_unknown_student_inactive_raises_not_found(store):
    with pytest.raises(NotFound):
        store.set_active(99, False)


def test_renaming_keeps_a_student_inactive(store):
    student = store.add_student("王小明")
    store.set_active(student.id, False)
    assert not store.rename_student(student.id, "王大明").active


def test_chart_book_from_before_active_students_has_everyone_active(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        student = store.add_student("王小明")
    old = sqlite3.connect(path)
    old.execute("ALTER TABLE student DROP COLUMN active")
    old.commit()
    old.close()
    with RecordStore(path, KEY) as again:
        assert again.get_student(student.id).active


def test_timetable_lists_active_students_sessions_by_weekday_and_time(store):
    ming, amy, lin = store.add_student("王小明"), store.add_student("Amy"), store.add_student("林曉華")
    store.set_profile(ming.id, StudentProfile(sessions=(Session(4, "10:00", "10:30"), Session(0, "09:00", "09:30"))))
    store.set_profile(amy.id, StudentProfile(sessions=(Session(4, "10:00", "10:45"),)))
    store.set_profile(lin.id, StudentProfile(sessions=(Session(1, "13:00", "13:30"),)))
    store.set_active(lin.id, False)
    assert [(s.weekday, s.start, st.name) for s, st in store.timetable()] == [
        (0, "09:00", "王小明"), (4, "10:00", "Amy"), (4, "10:00", "王小明")]


def test_a_session_keeps_its_classroom_trimmed(store):
    student = store.add_student("王小明")
    store.set_profile(student.id, StudentProfile(sessions=(Session(4, "10:00", "10:30", " 301 "),)))
    assert store.get_profile(student.id).sessions == (Session(4, "10:00", "10:30", "301"),)


def test_a_session_saved_before_classrooms_has_none(store):
    student = store.add_student("王小明")
    blob = store._enc('{"sessions": [{"weekday": 4, "start": "10:00", "end": "10:30"}]}', "student.profile")
    with store._db:
        store._db.execute("UPDATE student SET profile = ? WHERE id = ?", (blob, student.id))
    assert store.get_profile(student.id).sessions == (Session(4, "10:00", "10:30"),)


def test_session_classrooms_lists_each_room_once(store):
    ming, amy = store.add_student("王小明"), store.add_student("Amy")
    store.set_profile(ming.id, StudentProfile(sessions=(Session(4, "10:00", "10:30", "301"), Session(0, "09:00", "09:30"))))
    store.set_profile(amy.id, StudentProfile(sessions=(Session(1, "10:00", "10:30", "301"), Session(2, "09:00", "09:30", "資源班"))))
    assert store.session_classrooms() == ["301", "資源班"]


def write_old_profile(path, student_id, fields):
    """A profile as saved before goals were kept one by one: `goals` is a single text."""
    old = sqlite3.connect(path)
    old.execute("UPDATE student SET profile = ? WHERE id = ?",
                (Cipher(KEY).encrypt(json.dumps(fields, ensure_ascii=False), "student.profile"), student_id))
    old.commit()
    old.close()


def test_profile_from_before_goal_lists_has_its_goals_split_by_number(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        student = store.add_student("王小明")
    write_old_profile(path, student.id, {"diagnosis": "ADHD", "goals": "1. 剪直線\n2. 扣釦子\n3. 寫名字"})
    with RecordStore(path, KEY) as again:
        assert again.get_profile(student.id).goals == ("剪直線", "扣釦子", "寫名字")


def test_profile_from_before_goal_lists_keeps_the_other_fields(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        student = store.add_student("王小明")
    write_old_profile(path, student.id, {"diagnosis": "ADHD", "goals": "Fine motor"})
    with RecordStore(path, KEY) as again:
        assert again.get_profile(student.id) == StudentProfile(diagnosis="ADHD", goals=("Fine motor",))


def test_goals_numbered_on_one_line_are_split():
    assert split_goals("1. Fine motor 2. Self-care") == ("Fine motor", "Self-care")


def test_goals_numbered_without_spaces_are_split():
    assert split_goals("1.寫字2.剪紙") == ("寫字", "剪紙")


def test_goals_numbered_goal_1_goal_2_are_split():
    assert split_goals("Goal 1: cut lines\nGoal 2: write") == ("cut lines", "write")


def test_a_number_out_of_turn_stays_in_the_goal():
    assert split_goals("1. cut 3. lines 2. write") == ("cut 3. lines", "write")


def test_a_decimal_is_not_a_goal_number():
    assert split_goals("Use 1.5 inch grips") == ("Use 1.5 inch grips",)


def test_text_before_goal_1_joins_goal_1_without_a_goals_heading():
    assert split_goals("Goals: in class\n1. cut\n2. write") == ("in class cut", "write")


def test_blank_goals_text_is_no_goals():
    assert split_goals("  ") == ()


def test_profile_is_an_iep_unless_marked_504():
    assert StudentProfile().plan_label == "IEP Date"
    assert StudentProfile(plan_504=True).plan_label == "504 Date"


def test_new_record_is_an_individual_session(store):
    student = store.add_student("王小明")
    assert store.add_record(student.id, date(2026, 10, 1)).session_type == "individual"


def test_session_type_and_goal_scores_are_read_back(store):
    student = store.add_student("王小明")
    record = store.add_record(student.id, date(2026, 10, 1))
    store.update_record(record.id, session_type="group", goal_scores=("75%", "not met"))
    again = store.get_record(record.id)
    assert (again.session_type, again.goal_scores) == ("group", ("75%", "not met"))


def test_an_unknown_session_type_is_refused(store):
    student = store.add_student("王小明")
    record = store.add_record(student.id, date(2026, 10, 1))
    with pytest.raises(ValueError):
        store.update_record(record.id, session_type="pair")


def test_goal_scores_are_stored_encrypted(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        student = store.add_student("王小明")
        store.add_record(student.id, date(2026, 10, 1), goal_scores=("not met",))
    assert b"not met" not in path.read_bytes()


def test_chart_book_from_before_session_types_reads_them_as_individual(tmp_path):
    path = tmp_path / "t.db"
    with RecordStore(path, KEY) as store:
        student = store.add_student("王小明")
        record = store.add_record(student.id, date(2026, 10, 1), session_type="consult")
    old = sqlite3.connect(path)
    old.execute("ALTER TABLE record DROP COLUMN session_type")
    old.execute("ALTER TABLE record DROP COLUMN goal_scores")
    old.commit()
    old.close()
    with RecordStore(path, KEY) as again:
        assert again.get_record(record.id).session_type == "individual"
        assert again.get_record(record.id).goal_scores == ()


def test_plan_dates_read_month_first_with_a_two_or_four_digit_year():
    assert parse_plan_date("10/29/2026") == date(2026, 10, 29)
    assert parse_plan_date("10/29/26") == date(2026, 10, 29)
    assert parse_plan_date("29/10/2026") is None
    assert parse_plan_date("") is None


OLD_PLAN = Plan(False, "10/29/2025", ("剪直線",))
NEW_PLAN = Plan(True, "10/29/2026", ("扣釦子", "寫名字"))


def test_a_new_plan_takes_over_from_its_date():
    profile = StudentProfile().with_plans([NEW_PLAN, OLD_PLAN])
    assert profile.plan_on(date(2026, 10, 28)) == OLD_PLAN
    assert profile.plan_on(date(2026, 10, 29)) == NEW_PLAN


def test_a_day_before_every_plan_falls_under_the_earliest():
    profile = StudentProfile().with_plans([NEW_PLAN, OLD_PLAN])
    assert profile.plan_on(date(2020, 1, 1)) == OLD_PLAN


def test_the_latest_dated_plan_becomes_the_current_one():
    profile = StudentProfile().with_plans([NEW_PLAN, OLD_PLAN])
    assert (profile.plan_504, profile.plan_date, profile.goals, profile.past_plans) == (
        True, "10/29/2026", ("扣釦子", "寫名字"), (OLD_PLAN,))


def test_old_plans_are_kept_with_their_goals(store):
    student = store.add_student("王小明")
    store.set_profile(student.id, StudentProfile(diagnosis="ADHD").with_plans([OLD_PLAN, NEW_PLAN]))
    assert store.get_profile(student.id).plans == (OLD_PLAN, NEW_PLAN)


def test_saving_puts_the_plans_in_date_order(store):
    student = store.add_student("王小明")
    store.set_profile(student.id, StudentProfile(plan_date="10/29/2025", goals=("剪直線",),
                                                 past_plans=(NEW_PLAN,)))
    assert store.get_profile(student.id).plans == (OLD_PLAN, NEW_PLAN)


def test_frequency_reads_as_minutes_a_month():
    assert Plan(frequency=90).frequency_text == "90 mins/month"
    assert Plan().frequency_text == ""


def test_each_plan_keeps_its_frequency(store):
    student = store.add_student("王小明")
    store.set_profile(student.id, StudentProfile().with_plans(
        [Plan(False, "10/29/2025", frequency=30), Plan(False, "10/29/2026", frequency=60)]))
    assert [p.frequency for p in store.get_profile(student.id).plans] == [30, 60]
