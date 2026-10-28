"""The interface language. The interface is written in Chinese; `tr` looks the Chinese text up
in ENGLISH when the language is English, and falls back to the Chinese when a text is missing
(tests/test_ot_i18n.py checks that none is).

The language is one app-wide setting, read once at start-up (load_language) and changed from
the settings dialog, after which the main window is rebuilt; widgets read it when they are made.
It is kept in QSettings, not the encrypted database, because the unlock prompt needs it before
there is a key, and it says nothing about anyone.
"""

from __future__ import annotations

from PySide6.QtCore import QSettings

from .. import APP_NAME

LANGUAGES = {"zh": "中文", "en": "English"}
SETTING = "ui/language"

_language = "zh"  # app-wide on purpose: see the module docstring


def language() -> str:
    return _language


def set_language(code: str) -> None:
    """Use `code` (a LANGUAGES key) for widgets made from now on. Raises ValueError otherwise."""
    global _language
    if code not in LANGUAGES:
        raise ValueError(f"unknown language {code!r}")
    _language = code


def _settings() -> QSettings:
    return QSettings(APP_NAME, APP_NAME)


def load_language() -> None:
    """Use the language saved by save_language; Chinese if none (or an unknown one) was saved."""
    saved = _settings().value(SETTING, "zh", str)
    set_language(saved if saved in LANGUAGES else "zh")


def save_language(code: str) -> None:
    set_language(code)
    _settings().setValue(SETTING, code)


MODES = ("學生", "日期", "地點", "課表")
MODES_ENGLISH = ("Students", "Calendar", "Locations", "Timetable")


def mode_names() -> list[str]:
    """The four modes' names for the switch. Kept apart from ENGLISH because the same Chinese
    words also label single fields ("學生" is "Student" next to a drop-down)."""
    return list(MODES_ENGLISH if _language == "en" else MODES)


def tr(text: str, **values: object) -> str:
    """`text` (the Chinese) in the interface language, with `values` filled into its {fields}."""
    if _language == "en":
        text = ENGLISH.get(text, text)
    return text.format(**values) if values else text


ENGLISH = {
    # main window
    "學生": "Student",
    "日期": "Date",
    "地點": "Location",
    "新增學生": "Add student",
    "新增病歷": "New chart",
    "匯出": "Export",
    "貼回": "Paste back",
    "Excel 匯出": "Excel export",
    "設定": "Settings",
    "設定…": "Settings…",
    "選擇一位學生，或新增學生開始記錄。": "Pick a student, or add one to start charting.",
    "模型管理…": "Models…",
    "關於 {app}": "About {app}",
    "說明": "Help",
    "學生姓名": "Student name",
    "修改姓名": "Rename",
    "刪除學生…": "Delete student…",
    "刪除學生": "Delete student",
    "要刪除 {name} 嗎？\n這位學生的 {count} 份病歷（中英文內容）都會一併刪除，無法復原。":
        "Delete {name}?\nAll {count} of this student's charts (Chinese and English) will be deleted. "
        "This cannot be undone.",
    "已有病歷": "Chart exists",
    "{name} 在 {day} 已經有一份病歷。要開啟它嗎？": "{name} already has a chart on {day}. Open it?",
    "刪除病歷": "Delete chart",
    "刪除病歷…": "Delete chart…",
    "要刪除 {name} 在 {day} 的病歷嗎？\n中英文內容都會一併刪除，無法復原。":
        "Delete {name}'s chart of {day}?\nBoth the Chinese and the English will be deleted. "
        "This cannot be undone.",
    "（所有學生）": "(All students)",
    "課表": "Timetable",
    "‹ 課表": "‹ Timetable",
    "尚未設定看診時段": "No session time yet",
    "停用學生": "Make inactive",
    "啟用學生": "Make active",
    "{name}（停用）": "{name} (inactive)",
    "還沒有學生設定看診時段。在學生的「基本資訊」加入看診時段，就會出現在課表上。":
        "No student has a session time yet. Add session times in a student's profile and they "
        "appear here.",
    "{students} 位學生 · {sessions} 個時段": "{students} students · {sessions} sessions",
    "查看 {name} 的所有病歷": "See all of {name}'s charts",
    # settings
    "介面語言": "Language",
    "病歷預覽會優先顯示這個語言的內容。": "Chart previews show this language first.",
    # editor
    "‹ 返回": "‹ Back",
    "修改日期": "Change date",
    "對照其他病歷": "Compare",
    "在右邊並排顯示這位學生的另一份病歷": "Show another of this student's charts on the right",
    "地點：{place}": "Location: {place}",
    "未填": "not set",
    "未填地點": "No location",
    "例如 9:30 AM": "e.g. 9:30 AM",
    "例如 10:00 AM": "e.g. 10:00 AM",
    "今天的治療活動與手段（只留在本機，不會匯出）":
        "Today's activities and methods (kept on this computer, never exported)",
    "中文病歷（可中英夾雜）": "Chinese chart (may mix in English)",
    "中文": "Chinese",
    "點兩下「中文」或「English」複製整份病歷": "Double-click a tab to copy the whole chart",
    "開始時間": "Start",
    "結束時間": "End",
    "活動": "Activities",
    "這位學生沒有其他病歷": "This student has no other charts",
    "已複製中文病歷": "Chinese chart copied",
    "已複製英文病歷": "English chart copied",
    "複製英文病歷": "Copy English chart",
    "{name} 在 {day} 已經有一份病歷，日期沒有更改。":
        "{name} already has a chart on {day}; the date was not changed.",
    "編輯中…": "Editing…",
    "時間請填成 9:30 AM 這樣的格式": "Enter times like 9:30 AM",
    "已儲存 {time}": "Saved {time}",
    # comparison
    "對照": "Compare",
    "關閉對照": "Close comparison",
    "（沒有記錄活動）": "(no activities recorded)",
    "（沒有中文病歷）": "(no Chinese chart)",
    "（沒有英文病歷）": "(no English chart)",
    # student, date and location views
    "基本資訊": "Profile",
    "Diagnosis、Grade、Goals 等，Excel 匯出時填入表頭":
        "Diagnosis, Grade, Goals and more; fills the header of the Excel export",
    "最新在前": "Newest first",
    "最舊在前": "Oldest first",
    "這位學生還沒有病歷。按「新增病歷」開始記錄。": "No charts yet. Press “New chart” to start.",
    "{count} 份病歷": "{count} charts",
    "依時間": "By time",
    "依名字": "By name",
    "未填時間": "No time",
    "這天沒有病歷。": "No charts on this day.",
    "{count} 位學生有病歷": "{count} students charted",
    "‹ 學生": "‹ Students",
    "回到這個地點的學生清單": "Back to the students at this location",
    "{count} 位學生": "{count} students",
    "{count} 份病歷（所有地點）": "{count} charts (all locations)",
    "（尚無內容）": "(empty)",
    "週{weekday}": "{weekday}",
    # profile
    "{name} 的基本資訊": "{name}'s profile",
    "學校或診所；新病歷會帶入": "School or clinic; new charts use it",
    "到": "to",
    "編輯基本資訊": "Edit profile",
    "看診時段": "Sessions",
    "領取教室": "Pickup room",
    "去哪裡找這個孩子": "Where to find the child for the session",
    "（領取教室：{room}）": " (pickup: {room})",
    "領取教室：{room}": "Pickup: {room}",
    "＋ 新增時段": "+ Add session",
    "移除這個時段": "Remove this session",
    "＋ 新增目標": "+ Add goal",
    "移除這個目標": "Remove this goal",
    "例如 能獨立扣好三顆釦子": "e.g. Buttons three buttons on their own",
    "504 計畫（不勾是 IEP）": "504 plan (an IEP if unticked)",
    "目標表現": "Goal scores",
    "（基本資料還沒有目標）": "(No goals in the profile yet)",
    "（未填日期）": "(no date)",
    "切換顯示其他 IEP/504 計畫和它的目標": "Show another IEP/504 plan and its goals",
    "＋ 新的計畫": "＋ New plan",
    "IEP/504 快到期時，填入新的日期和目標；舊的會保留": "When the IEP/504 is about to expire, enter the new date and goals; the old ones are kept",
    "刪除這份計畫": "Delete this plan",
    "刪除計畫": "Delete plan",
    "要刪除「{plan}」和它的目標嗎？": "Delete “{plan}” and its goals?",
    "IEP/504 日期請填成 10/29/2026 這樣的格式": "Enter IEP/504 dates like 10/29/2026",
    "有多份 IEP/504 計畫時，每份都要填日期": "With more than one IEP/504 plan, each needs a date",
    "兩份 IEP/504 計畫的日期不能相同": "Two IEP/504 plans cannot have the same date",
    "例如 75%": "e.g. 75%",
    "留空表示沒有記錄，匯出成 --": "Leave blank when not recorded; exported as --",
    "例如 10:30 AM": "e.g. 10:30 AM",
    # unlock and start-up
    f"這台電腦沒有可用的系統鑰匙圈。請設定一組密碼來保護 {APP_NAME} 的病歷。\n"
    "忘記密碼就無法讀回資料，請自行妥善保存。":
        f"This computer has no system keychain to use. Set a password to protect the charts in "
        f"{APP_NAME}.\nWithout it the data cannot be read back, so keep it safe.",
    f"輸入密碼以解鎖 {APP_NAME}。": f"Enter the password to unlock {APP_NAME}.",
    "密碼不正確，請再試一次。": "Wrong password. Try again.",
    "兩次輸入的密碼不一致。": "The two passwords differ.",
    "解鎖 {app}": "Unlock {app}",
    "密碼": "Password",
    "確認密碼": "Confirm",
    f"已取消解鎖。資料沒有被讀取，{APP_NAME} 將關閉。":
        f"Unlock cancelled. No data was read; {APP_NAME} will quit.",
    "無法解鎖：{reason}\n資料沒有被讀取，" + APP_NAME + " 將關閉。":
        "Could not unlock: {reason}\nNo data was read; " + APP_NAME + " will quit.",
    "取得的金鑰打不開這個資料庫（{path}）。\n可能是鑰匙圈被重設，或密碼不是當初設定的那組。"
    f"資料沒有被改動，{APP_NAME} 將關閉。":
        "The key does not open this database ({path}).\nThe keychain may have been reset, or the "
        f"password is not the one first set. Nothing was changed; {APP_NAME} will quit.",
    # about
    "<p>加密保存職能治療病歷，匯出時以可還原的代號遮蔽姓名。</p>":
        "<p>Keeps occupational therapy charts encrypted, and hides names behind reversible codes "
        "on export.</p>",
    "<p>以 DataFuzzy 為核心。NER 模型由使用者在「模型管理」下載，各自適用其授權。</p>":
        "<p>Built on DataFuzzy. NER models are downloaded by the user under “Models”, each under "
        "its own license.</p>",
    "<p><b>第三方授權</b></p>": "<p><b>Third-party licenses</b></p>",
    # model manager (shared with DataFuzzy, which keeps it in Chinese)
    "模型管理": "Models",
    "英文": "English",
    "中英夾雜": "Mixed Chinese and English",
    "所有語言": "All languages",
    "{lang} · {size} MB · 授權 {license} · 來源 {source}":
        "{lang} · {size} MB · License {license} · Source {source}",
    "取消": "Cancel",
    "下載中…": "Downloading…",
    "刪除": "Delete",
    "✅ 已安裝": "✅ Installed",
    "下載": "Download",
    "未安裝": "Not installed",
    "已取消（下次會從中斷處繼續）": "Cancelled (the next download resumes where it stopped)",
    "檔案驗證失敗，已刪除，請重新下載": "The file failed verification and was deleted. Download it again.",
    "下載失敗：{error}": "Download failed: {error}",
    "模型用來辨識<b>人名、地址、生日、帳號</b>等個人資料，下載後完全在本機執行。<br>"
    "未安裝模型時仍可使用，但只會以規則偵測 Email、電話、IP 等格式化資料。<br>"
    "<span style='color:gray;'>下載模型是本軟體唯一會連網的時機。</span>":
        "Models find personal details such as <b>names, addresses, birthdays and account numbers</b>, "
        "and run entirely on this computer once downloaded.<br>"
        "Without a model the app still works, but only rules catch formatted data such as email "
        "addresses, phone numbers and IPs.<br>"
        "<span style='color:gray;'>Downloading a model is the only time this app goes online.</span>",
    "存放位置：{root}": "Stored in: {root}",
    # export and paste back
    "標頭格式不正確": "malformed header",
    "這份匯出沒有這筆病歷": "not in this export",
    "標頭的代號或日期被改過": "code or date in the header was changed",
    "同一筆出現第二次": "appears twice",
    "這筆病歷已刪除": "chart was deleted",
    "匯出病歷": "Export charts",
    "選擇日期範圍後按「匯出」。學生與文中的人名會換成代號。":
        "Pick the dates and press “Export”. Student and other names become codes.",
    "一鍵複製": "Copy all",
    "從": "From",
    "開始日期晚於結束日期。": "The start date is after the end date.",
    "匯出中…": "Exporting…",
    "這段期間沒有病歷。": "No charts in this period.",
    "已匯出 {count} 份病歷，人名已換成代號。": "Exported {count} charts with names replaced by codes.",
    "（偵測模型未安裝：只有學生姓名保證被替換，其他人名可能漏掉，請先到「模型管理」下載。）":
        " (No detection model installed: only student names are sure to be replaced and other "
        "names may slip through. Download one under “Models” first.)",
    "匯出失敗：{message}": "Export failed: {message}",
    "已複製 ✓": "Copied ✓",
    "覆蓋英文版": "Replace English",
    "有 {count} 份病歷已有英文版，貼回後會被取代（只保留最新一版）。要覆蓋嗎？":
        "{count} charts already have an English version, which pasting back replaces (only the "
        "latest is kept). Replace them?",
    "貼回英文版": "Paste back English",
    "把翻譯／修正後、含「=== REC-… ===」標頭的文字貼在這裡":
        "Paste the translated or corrected text here, with its “=== REC-… ===” headers",
    "檢查": "Check",
    "套用": "Apply",
    "無法對應到匯出：{error}": "Does not match an export: {error}",
    "　⚠ 會覆蓋既有英文版": "  ⚠ replaces the English version",
    "可套用 {count} 份病歷。": "{count} charts can be applied.",
    "沒貼回：{name} · {day}": "Not pasted back: {name} · {day}",
    "不認得的標頭（{reason}）：{header}": "Unknown header ({reason}): {header}",
    "不認得的代號 {codes}：{name} · {day}": "Unknown codes {codes}: {name} · {day}",
    "已取消，沒有寫入。": "Cancelled; nothing was written.",
    "已寫入 {count} 份英文版。": "Wrote {count} English versions.",
    "取代檔案": "Replace file",
    "「{name}」已經存在，要取代嗎？": "“{name}” already exists. Replace it?",
    "Excel 匯出資料夾": "Excel export folder",
    "加入": "Add",
    "加入此地點全部": "Add all here",
    "病歷數": "Charts",
    "移除": "Remove",
    "選擇資料夾…": "Choose folder…",
    "在 Finder 中顯示": "Show in Finder",
    "匯出資料夾：": "Export folder:",
    "每位學生一個檔案（姓名-開始日期至結束日期.xlsx），只含所選地點的病歷。":
        "One file per student (name-start至end.xlsx), with only the picked location's charts.",
    "\n有 {count} 份病歷沒有填地點，不會匯出。": "\n{count} charts have no location and are not exported.",
    "{name}（{count} 份）": "{name} ({count})",
    "（尚未設定）": "(not set)",
    "略過{label}：這段期間沒有病歷。": "Skipped {label}: no charts in this period.",
    "略過{label}：沒有取代既有檔案。": "Skipped {label}: the existing file was kept.",
    "{label}寫入失敗：{error}": "{label} could not be written: {error}",
    "已匯出：{path}": "Exported: {path}",
    "沒有可匯出的學生。": "No students to export.",
}

WEEKDAYS_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
