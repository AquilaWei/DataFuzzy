import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
MANIFEST = json.loads((ROOT / "chrome-extension" / "manifest.json").read_text())
APP_VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]


def test_the_extension_shows_the_app_s_version():
    assert MANIFEST["version_name"] == APP_VERSION


def test_chrome_s_version_is_the_app_s_first_four_numbers():
    # Chrome takes at most four numbers; the full one is in version_name.
    assert MANIFEST["version"] == ".".join(APP_VERSION.split(".")[:4])


def test_every_icon_the_manifest_names_exists():
    icons = list(MANIFEST["icons"].values()) + list(MANIFEST["action"]["default_icon"].values())
    assert [icon for icon in icons if not (ROOT / "chrome-extension" / icon).exists()] == []


# --- KeepCurrent ----------------------------------------------------------------------------

KC_SCRIPTS = ["kc-match.js", "keepcurrent.js"]


def test_keepcurrent_pages_get_their_own_scripts():
    sites = ["https://www.mykeepcurrent.com/*", "https://mykeepcurrent.com/*"]
    assert set(sites) <= set(MANIFEST["host_permissions"])
    [entry] = [c for c in MANIFEST["content_scripts"] if c["matches"] == sites]
    assert entry["js"] == KC_SCRIPTS
    assert all((ROOT / "chrome-extension" / js).exists() for js in KC_SCRIPTS)


def test_ace_pages_do_not_load_the_keepcurrent_scripts():
    ace = [c for c in MANIFEST["content_scripts"] if "acestudentcare" in c["matches"][0]]
    assert ace and all(js not in c["js"] for c in ace for js in KC_SCRIPTS)


def run_match(expression):
    """`expression` evaluated with kc-match.js loaded, in macOS's JavaScript engine, as JSON."""
    if sys.platform != "darwin" or not shutil.which("osascript"):
        pytest.skip("needs macOS's osascript to run JavaScript")
    source = (ROOT / "chrome-extension" / "kc-match.js").read_text()
    script = f"{source}\nJSON.stringify({expression})"
    out = subprocess.run(["osascript", "-l", "JavaScript", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


GOAL = ("Using a variety of sensory strategies, Dree will participate in non-preferred group tasks. "
        "This goal will be achieved when Dree participates in group tasks for 10 minutes over 10 group tasks.")
OPTIONS = [
    "Participate in non preferred group tasks " + GOAL,
    ("Alerting to name and following routine directions- speech Dree will alert to his name and follow "
    "routine/familiar directions during the day on 10 occasions over 4 consecutive school days"),
    ("Ball Skills Dree will participate in reciprocal catch and throw using a medium ball, accurately catching "
    "and throwing 7 out of 10 repetitions with a partner such as therapist or teacher seated 3-4 feet away."),
]


def match(goals, options=OPTIONS, names=("Dree", "Todd")):
    return run_match(f"TheraNoteKcMatch.matchGoals({json.dumps(list(goals))}, {json.dumps(options)}, "
                     f"{json.dumps(list(names))})")


def test_a_goal_copied_from_the_iep_is_ticked():
    [m] = match([GOAL])
    assert (m["option"], m["tick"], m["score"]) == (0, True, 1)


def test_a_goal_reworded_a_little_is_still_ticked():
    [m] = match([("Student will participate in reciprocal catch and throw with a medium ball, catching and "
                 "throwing 7 of 10 repetitions with a partner (therapist or teacher) 3-4 feet away.")])
    assert (m["option"], m["tick"]) == (2, True)


def test_a_goal_written_with_he_matches_one_written_with_the_name():
    [m] = match([GOAL.replace("Dree participates", "he participates")])
    assert (m["option"], m["tick"]) == (0, True)


def test_an_unrelated_goal_ticks_nothing():
    [m] = match(["Copy upper case letters with correct formation on lined paper."])
    assert (m["option"], m["tick"], m["best"]) == (-1, False, -1)


def test_each_option_is_ticked_for_one_goal_at_most():
    first, second = match([GOAL, GOAL + " Again."])
    assert first["option"] == 0 and second["option"] != 0


def test_a_doubtful_match_is_left_for_the_user_naming_the_likeliest():
    [m] = match(["Dree will follow familiar routine directions in class."])
    assert m["tick"] is False
    assert m["best"] in (1, -1)


DASHBOARD = [{"first": "ava", "last": "lee"}, {"first": "ben", "last": "cho"},
             {"first": "mia", "last": "kim"}, {"first": "mia", "last": "park"}]


def students(first, last=""):
    """The dashboard rows TheraNote's student may be, by their family names."""
    found = run_match(f"TheraNoteKcMatch.students({json.dumps({'first': first, 'last': last})}, "
                      f"{json.dumps(DASHBOARD)})")
    return [row["last"] for row in found]


def test_a_student_is_found_by_the_given_name_alone_whatever_the_case():
    assert students("AVA") == ["lee"]
    assert students("Ava") == ["lee"]


def test_a_family_name_that_differs_does_not_hide_the_only_student_of_that_name():
    assert students("Ben", "Chou") == ["cho"]


def test_students_sharing_a_given_name_are_all_offered_when_theranote_has_no_family_name():
    assert students("mia") == ["kim", "park"]


def test_the_family_name_picks_among_students_sharing_a_given_name():
    assert students("Mia", "PARK") == ["park"]
    assert students("Mia Park") == ["park"]  # the whole name typed as the given name


def test_a_given_name_spelled_otherwise_finds_no_one():
    assert students("Myah") == []


@pytest.mark.parametrize(("text", "minutes"), [
    ("11:00", 660), ("11:00 AM", 660), ("1:05 pm", 785), ("12:15 AM", 15), ("12:30 PM", 750), ("", None), ("soon", None)])
def test_keepcurrent_times_are_read_either_way(text, minutes):
    assert run_match(f"TheraNoteKcMatch.clockMinutes({json.dumps(text)})") == minutes


VISIT = {"date": "2026-11-13", "start": "11:00", "minutes": 30}


@pytest.mark.parametrize(("entry", "state"), [
    ({"start": "11:00 AM", "minutes": "30"}, "same"),
    ({"start": "11:00", "minutes": "30"}, "same"),
    ({"start": "11:00 AM", "minutes": "45"}, "different"),
    ({"start": "1:00 PM", "minutes": "30"}, "different"),
    ({"start": "", "minutes": "30"}, "unknown"),
])
def test_an_entry_of_the_same_day_is_the_same_only_with_the_same_start_and_length(entry, state):
    assert run_match(f"TheraNoteKcMatch.compareEntry({json.dumps(VISIT)}, {json.dumps(entry)})") == state


def test_an_absence_entered_with_no_minutes_is_the_same_as_zero():
    visit = {"date": "2026-11-13", "start": "09:00", "minutes": 0}
    assert run_match(f"TheraNoteKcMatch.compareEntry({json.dumps(visit)}, "
                     f"{json.dumps({'start': '09:00 AM', 'minutes': ''})})") == "same"


def test_keepcurrent_lists_write_dates_month_first():
    assert run_match('TheraNoteKcMatch.usDate("2026-11-03")') == "11/03/2026"
