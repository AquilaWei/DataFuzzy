# Changelog

All notable changes to this project are documented here.
Versions follow `MAJOR.MINOR.PATCH`: MINOR for tested new features, PATCH for bug fixes.

## [0.7.0.25.0] - 2026-10-27

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 變更
- 課表改成有格線的表格：每個星期 × 時段都有框線（沒有學生的格子也有），時段列隔行加底色，左邊的時間欄加底色並放大字體，一眼就看得出每位學生落在哪一天的哪個時段。

## [0.7.0.24.0] - 2026-10-27

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 變更
- 病歷頁整頁可以上下捲動：基本資訊（例如 Goals）很長時，下方的活動與病歷不再被擠壓，往下捲就看得到。
- 「活動」欄會隨字數自動調整高度（至少 3 行），所有內容都直接顯示，不必在小框裡捲動；視窗變窄、文字換行變多時也會跟著長高。
- 對照其他病歷時，兩邊的活動欄取較高的一邊，維持左右對齊。

## [0.7.0.23.1] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 變更
- 「學生教室」改名為「領取教室」，意思是去哪裡找這個孩子。基本資訊顯示為「（領取教室：301）」，課表卡片顯示「領取教室：301」；English 介面為「Pickup room」。已填的資料不受影響。

## [0.7.0.23.0] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 新增
- 每個看診時段可以填「學生教室」：要到哪個教室接學生。下拉選單會列出其他時段用過的教室，也可以直接輸入新的；不填則留空。
- 學生教室會顯示在病歷上方的基本資訊（例如「週五 10:00 AM–10:30 AM（教室：301）」）與課表的每位學生卡片上。

### 修正
- English 介面的四個模式改為一致的名稱：Students／Calendar／Locations／Timetable（原本單複數混用，且「Students」也誤用在新增病歷、Excel 匯出的單一學生欄位上，現在這些欄位是「Student」）。
- 側邊欄的模式切換縮小左右留白，English 名稱不再被截斷。

## [0.7.0.22.0] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 新增
- 學生分「啟用」與「停用」：所有學生預設為啟用；計畫完成後，在學生名單的名字上按右鍵選「停用學生」，之後也可以「啟用學生」改回來。停用的學生排在名單最後、以灰字標示「（停用）」，病歷都保留，仍可查看與新增。
- 新的「課表」模式（學生／日期／地點／課表）：依啟用學生基本資訊裡的看診時段，排出每週哪一天、哪個時段有哪些學生；直欄是星期一到五（週末有排課才出現），橫列是開始時間，同一時段的學生並列。
- 在課表點學生名字，會顯示這位學生的所有病歷；點其中一份即可開啟，也能用「對照其他病歷」同時看兩份。按「‹ 課表」回到課表。
- 在課表模式中修改學生的看診時段（學生頁的「基本資訊」，或病歷上方的「編輯基本資訊」），課表會立即更新；停用、啟用、改名也會同步。
- 課表模式的側邊欄列出「尚未設定看診時段」的啟用學生，點名字可直接看他的病歷、補設定時段。

## [0.7.0.21.0] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 新增
- 學生基本資訊新增「看診時段」：每個時段是星期幾加上開始與結束時間（例如週五 10:00 AM–10:30 AM），不限一個，按「＋ 新增時段」增加、按 ✕ 移除。結束時間預設為開始後 30 分鐘，可自行修改；時間格式不對時會提示，不會關閉視窗。
- 病歷上方的基本資訊會列出所有看診時段。
- 新增病歷的預設時段改為：先看基本資訊裡同一個星期幾的看診時段（同一天有好幾個時取最早的）；沒有設定時才沿用最近一次同星期幾的病歷，再沒有就用最近一次的開始時間。

## [0.7.0.20.0] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 變更
- 日期模式（以及地點模式的病歷清單）的時段更醒目：每一列最左邊是獨立的時間欄，開始時間以粗體強調色顯示、結束時間在下方，再以一條強調色直線和姓名分開；所有列的姓名對齊在同一個位置。沒有填時間的病歷顯示灰色「未填時間」。

## [0.7.0.19.0] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 變更
- 「模型管理」視窗也跟著介面語言切換中英文（標題、說明、下載／刪除按鈕、狀態與錯誤訊息）。原 DataFuzzy 介面的模型管理維持中文。

## [0.7.0.18.0] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 新增
- 「設定」：側邊欄左下角的「設定」按鈕，或 macOS 選單 TheraNote → 設定…（⌘,）。可切換介面語言（中文／English），按確定後視窗立即換成新語言，未存的編輯會先存好；下次開啟沿用這個語言，解鎖畫面也會跟著換。
- 病歷預覽跟著介面語言：中文介面優先顯示中文病歷，English 介面優先顯示英文病歷；該語言沒有內容時顯示另一種。開啟病歷與對照病歷時，也先停在該語言的分頁。
- English 介面的日期顯示 Mon、Tue… 等星期縮寫。

### 已知限制
- 「模型管理」視窗與 DataFuzzy 共用，目前仍只有中文（0.7.0.19.0 已改為跟著切換）。
- Excel 匯出的檔名格式不變（`姓名-開始日期至結束日期.xlsx`）。

## [0.7.0.17.0] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 變更
- 改版前建立、有開始時間但沒有結束時間的病歷，開啟 App 時會自動補上開始後 30 分鐘的結束時間（最晚到 23:59）。沒有開始時間的病歷維持空白，已經有結束時間的不會被改。
- 補填時只讀寫開始與結束時間這兩個欄位，不需要密碼，也不會解密任何病歷內容或學生資料。
- 每個資料庫只補一次；之後手動清空的結束時間不會再被自動填回。

## [0.7.0.16.1] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 修正
- 「對照其他病歷」時，學生基本資訊改為橫跨整個畫面、固定在最上方，不再只出現在左邊那份病歷上。
- 右邊對照的病歷改成跟左邊一樣的排法：日期與地點、開始與結束時間、活動、中英文病歷逐列對齊，方便左右比對。

## [0.7.0.16.0] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 變更
- 新增病歷的預設時段改為參考同一個星期幾：沿用這位學生最近一次同星期幾、有填時間的病歷的開始與結束時間（例如週五的病歷帶入上次週五的時段）。每週兩天不同時段的學生，兩天會各自帶入正確的時段。
- 該次沒有結束時間時，結束時間為開始後 30 分鐘；沒有任何同星期幾的紀錄時，照舊用最近一次的開始時間，結束為 30 分鐘後。

## [0.7.0.15.0] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 變更
- 地點改為學生基本資訊的一部分，每位學生一個地點。病歷編輯畫面不再有地點欄；新增病歷時自動帶入學生的地點。還沒在基本資訊填地點的學生，沿用最近一次病歷的地點。
- 開啟病歷時，最上方顯示學生的基本資訊（姓名、地點、Diagnosis、Age、Grade、Classroom、Case manager、School year、Goals），右上角可「編輯基本資訊」；下方才是這次的日期、時間、活動與中英文病歷，日期旁標示這份病歷記錄的地點。
- 修改學生的地點只影響之後新增的病歷，舊病歷保留原本的地點（地點模式與 Excel 匯出也照舊）。
- 新增病歷視窗選地點後，只列出地點是這裡的學生；地點模式也會列出地點已設在這裡、但還沒有病歷的學生。

## [0.7.0.14.0] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 變更
- 地點模式點學生後，改為顯示這位學生的全部病歷（所有地點，最新在前），不再只限所選地點。每一列以日期為標題，標籤顯示該次的地點。

## [0.7.0.13.0] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 新增
- 病歷編輯畫面右上角新增「對照其他病歷」。清單從目前這份往前排，最接近的上一次在最上面，越往下越舊；比目前還新的病歷排在最後。
- 選好後，那份病歷會以唯讀方式並排顯示在右邊（日期、時間、地點、活動、中英文），中間可拖曳調整寬度，按 ✕ 關閉。各種模式開啟的病歷都能使用。

## [0.7.0.12.0] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 新增
- 病歷新增「結束時間」，在編輯器的開始時間旁邊。新病歷的結束時間預設為開始時間後 30 分鐘。
- 修改開始時間時，結束時間會跟著維持 30 分鐘後；一旦手動改過結束時間，就不再自動跟著變。
- 卡片、日期清單與地點清單的時間顯示為「9:30 AM–10:00 AM」；舊病歷沒有結束時間時只顯示開始時間。結束時間與開始時間一樣不參與匯出。

## [0.7.0.11.0] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 變更
- Excel 匯出改成一位學生一個檔案，檔名為「姓名-開始日期至結束日期.xlsx」（例如 `王小明-2026-10-01至2026-10-31.xlsx`），取代原本「地點-匯出當天日期.xlsx」。
- 匯出視窗新增「地點」與「學生」下拉選單：先選地點，再從在該地點看過的學生中選人加入匯出名單；也可「加入此地點全部」，或選取名單後「移除」。每份檔案只含所選地點、期間內的病歷。
- 同一位學生在兩個地點都被加入時，檔名前面會加上地點以免重名。
- 匯出資料夾改為全部共用一個並記住；原本各地點分開設定的資料夾不再使用，第一次匯出需重新選擇。

## [0.7.0.10.0] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 新增
- 學生頁姓名旁新增「基本資訊」，可填寫 Diagnosis（如 ADHD, ODD）、Age、Grade、Classroom、Case manager、School year（起訖月份與年份，例如 09/2026-06/2027）與 Goals。
- Excel 匯出時，這些資訊會自動填入表單第一列與 Goals 列；沒填 School year 時使用當前學年。表頭標籤改為正確拼字（Diagnosis、School year）。
- 基本資訊與姓名一樣加密儲存；舊的病歷本開啟時會自動加上這個欄位。

## [0.7.0.9.1] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 修正
- 學生病歷卡片在滑鼠移過時的展開動畫變順。卡片陰影改為預先繪製並快取，換卡時所有卡片共用一段動畫；30 張卡片時每格重繪時間從約 52 ms 降到約 8 ms。

## [0.7.0.9.0] - 2026-10-26

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 新增
- 學生名單上按右鍵可「刪除學生…」。刪除前會跳出警告，列出這位學生有幾份病歷，確認後連同所有病歷一併刪除，無法復原。
- 若正在編輯該學生的病歷，刪除時會先關閉編輯器。

## [0.7.0.8.0] - 2026-10-25

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 新增
- 日期模式的當天病歷清單，右上角可切換「依時間」或「依名字」排序。預設依時間，沒填時間的排最後，同時間再依名字排。

## [0.7.0.7.0] - 2026-10-25

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 新增
- 地點模式改成先列出在該地點看過的學生名字；點學生後，才顯示他在這個地點的病歷與份數，左上角「‹ 學生」可返回。
- 開始時間改用 AM／PM 顯示（編輯器、卡片、日期與地點清單）。輸入可寫 `9:30 AM`、`2:05pm`，也接受 `14:05` 這種 24 小時制。
- 資料庫仍以 24 小時制 `HH:MM` 儲存，既有病歷的時間不受影響。

## [0.7.0.6.0] - 2026-10-25

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 新增
- 日期模式與地點模式的「新增病歷」小視窗，改成先選地點，再從在該地點看過的學生中選人，最後確認日期；也可以選「（所有學生）」列出全部學生。
- 日期模式預設為月曆上選的日期，地點則預設為當天已有病歷的地點；地點模式預設為側欄目前選的地點。
- 新病歷的地點使用小視窗選的地點。

## [0.7.0.5.4] - 2026-10-25

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 修正
- 新增病歷時，開始時間也比照地點，預設為該學生上一次病歷的時間（第一份病歷維持空白）。

## [0.7.0.5.3] - 2026-10-25

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 修正
- 拿掉地點欄「點兩下展開清單」的操作。
- 地點欄右側改用地標圖示，提示點那裡可以從用過的地點選取。

## [0.7.0.5.2] - 2026-10-25

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 修正
- 病歷的地點欄：點一下可直接輸入，點兩下會展開用過的地點清單供選取。

## [0.7.0.5.1] - 2026-10-25

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 修正
- 病歷的「開始時間」欄右側加上時鐘圖示，提示點那裡可以選時間。

## [0.7.0.5.0] - 2026-10-25

TheraNote 分支功能測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 新增
- 病歷新增「開始時間」（HH:MM，可從清單選或自行輸入，可留空），顯示在學生卡片與日期、
  地點清單中；資料庫新增 `start_time` 欄，舊資料庫開啟時自動補上。不參與匯出、貼回與 Excel 匯出。
- 側欄新增第三種瀏覽方式「地點」：列出用過的地點（含「未填地點」），選取後依日期由新到舊
  列出該地點的所有病歷，可點開編輯或右鍵刪除。

## [0.7.0.4.0] - 2026-10-25

TheraNote 分支功能測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 新增
- 病歷編輯器中點兩下「中文」或「English」分頁，即複製整份中文或英文病歷。

### 變更
- 日期頁的病歷清單：學生姓名粗體、地點改成彩色小標籤、病歷開頭灰色，三者一眼分得出來。

## [0.7.0.3.1] - 2026-10-25

TheraNote 分支測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 修正
- 日期欄右側加上日曆圖示，提示點那裡可以開啟日曆。

## [0.7.0.3.0] - 2026-10-25

TheraNote 分支功能測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 新增
- 學生頁姓名旁的 ✎ 可修改學生姓名；病歷編輯器日期旁的 ✎ 可修改病歷日期
  （該學生當天已有病歷時拒絕並提示），月曆標記一併更新。

### 變更
- Excel 匯出：所有地點都成功匯出後自動關閉視窗；有略過或失敗時保留視窗顯示原因。

### 修正
- 淺色主題下月曆底色是黑的、日期看不清楚，改用主題底色與文字色。

## [0.7.0.2.0] - 2026-10-25

TheraNote 分支功能測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 新增
- 「Excel 匯出」：依學校表單範本，每個地點產生 `地點-匯出日期.xlsx`，每位學生一個分頁，
  依日期填入 Date／Activity（病歷的活動）／Comment（英文病歷）；超過範本 10 格會自動延伸。
  每個地點各自設定匯出資料夾並加密記住；同名檔案存在時先詢問是否取代；未填地點的病歷不匯出。

## [0.7.0.1.0] - 2026-10-25

TheraNote 分支功能測試版，尚待實機驗收。本次不建立 tag、不發佈。

### 新增
- 病歷卡片與日期清單可按右鍵「刪除病歷…」，確認後刪除，月曆標記一併更新。
  已刪除病歷若出現在之後貼回的文字中，會列為「這筆病歷已刪除」而不寫入。
- 病歷新增「活動」欄，固定在編輯器分頁上方，記錄當天的治療活動與手段；加密保存、
  自動儲存，不參與匯出與貼回。舊資料庫開啟時自動加上此欄。
- TheraNote 專屬圖示：青綠底的病歷紙加愛心。原 DataFuzzy 圖示不變。

## [0.7.0.0.2] - 2026-10-24

TheraNote 分支修正版。本次不建立 tag、不發佈。

### 修正
- macOS 建置失敗：`pyobjc-framework-Security` 的套件未附授權全文，授權檢查因此中止；
  改附 PyObjC 的 MIT 授權全文。已在 Apple Silicon Mac 建出 DMG，安裝後 `--self-test` 通過。

## [0.7.0.0.1] - 2026-10-24

TheraNote 首個分支測試版，尚待實機驗收。本分支採五段版號：前三碼 `0.7.0` 是分支的
基底版本，第四碼是功能驗收版（類似 MINOR），第五碼是測試／修正版（類似 PATCH）。
本次不建立 tag、不發佈。

### 新增
- 以學生或日期瀏覽職能治療病歷，中英文分別編輯、自動儲存；地點可沿用上次或從歷史選取。
- 病歷與匯出代號表加密保存；macOS 以 Touch ID／登入密碼驗證後讀取 Keychain，
  Linux 使用 Secret Service，沒有鑰匙圈的新資料庫可設定密碼。
- 依日期區間匯出病歷並遮蔽姓名；貼回帶標頭的修訂文字後還原姓名，確認後更新英文版。
  代號表持久保存，重開仍可貼回。
- TheraNote 的側邊欄、文件卡片、滑鼠預覽與系統淺深色介面；保留原有模型管理。
- `uv run theranote`、`uv run datafuzzy` 與 `uv run python -m datafuzzy.ot` 開啟 TheraNote；
  原 DataFuzzy 介面仍可用 `uv run python -m datafuzzy` 開啟。
- 建置腳本改產出 TheraNote DMG／AppImage，隨附系統鑰匙圈依賴及第三方授權。

### 待實機驗收
- macOS Touch ID／密碼解鎖、未公證 App 的鑰匙圈提示、外觀與浮起動畫、DMG 啟動，
  以及真實模型下的姓名遮蔽品質。

## [0.7.0] - 2026-10-07

Verified by hand on an Apple Silicon Mac. English names written inside Chinese text are
found; everything below was released as the test builds 0.6.1–0.6.2.

### Added
- New optional model in the model manager, **中英夾雜人名** (XLM-RoBERTa large, about
  578 MB): it reads the context, so English names in Chinese text are found with or
  without spaces, in lowercase, romanized or uncommon (`跟Jason說`, `跟jason說`,
  `Wei-Ting說好`), while `June跟May的報告` stays readable.
- Without a model, common English given names in Chinese text are coded from a list
  (US Social Security baby names, public domain, plus names common in Taiwan such as
  `Kiki`, `Momo`, `Sammi`), as are names after a title (`Dr. Wang說`) and before a
  possessive (`Jason's 電腦`). English-only text is unaffected.

### Fixed
- English words in Chinese text (`stand-up`) are no longer taken for Chinese names.

## [0.6.2] - 2026-10-06

Second test build of English names in Chinese text, for hands-on checks before 0.7.0.

### Added
- New model in the model manager: **中英夾雜人名** (XLM-RoBERTa large, about 578 MB). It
  reads the context, so English names in Chinese text are found even when they are
  lowercase, romanized or not common English names (`跟jason說`, `Wei-Ting說好`,
  `Hsiao-Wen有來嗎`), while `June跟May的報告` stays readable. Optional: install it if
  you work with Chinese text that has English names in it.
- English names common in Taiwan (`Kiki`, `Momo`, `Coco`, `Sammi`, `Queenie`…) are in
  the name list used without a model.
- A name after a title is found in Chinese text (`Dr. Wang說` → `Dr. [PERSON_A]說`).

### Fixed
- With the language set to 中文, English names in the text were not coded without a model
  (`Jason說好`).
- A name with a possessive (`Jason's 電腦`) was missed.

## [0.6.1] - 2026-10-05

Test build of English names in Chinese text, for hands-on checks before 0.7.0.

### Added
- English names written inside Chinese text are found, with or without spaces around
  them (`跟Jason說`, `這是Annie的電腦`, `PM是Emily Chen`). Common English given names
  (from US Social Security baby-name data, public domain) are coded in Chinese text even
  without a model; English-only text is unaffected.

### Fixed
- English words in Chinese text (`stand-up`) are no longer taken for Chinese names.

## [0.6.0] - 2026-09-19

Verified by hand on an Apple Silicon Mac. Since 0.5.1, personal data is found by a model
made for it, only personal data is coded, and everything below was released as the test
builds 0.5.2–0.5.8.

### Added
- Scope "只處理人名": only people are coded; everything else stays readable.
- Dates (including dates of birth), record, policy, account and passport numbers.
- Addresses are found by rule in Taiwan and the US, so house numbers never leak, and US
  Social Security numbers are coded.
- Installers for macOS (Apple Silicon `.dmg`) and Linux (x86_64 `AppImage`), built,
  smoke-tested with the real models and published by GitHub Actions on a `vX.Y.Z` tag.
- Help → About DataFuzzy with the licenses of every bundled package, an app icon, and
  `datafuzzy --version` / `--self-test`.

### Changed
- Personal data is found by [`openai/privacy-filter`](https://huggingface.co/openai/privacy-filter)
  instead of the English NER model; the CKIP Chinese model now finds names only.
  Companies, hospitals, places, diseases and departments stay readable.
- Long text is cut into 1024-token pieces, which keeps memory flat (~1.4 GB) however
  long the document is.

### Fixed
- Form-like text, chat logs and headings: line-by-line detection, form labels are not
  speakers, departments and disease names are not coded, an organization and its
  department share one code.

## [0.5.8] - 2026-09-19

### Fixed
- Long documents use far less memory: the personal-data model now gets pieces of at most
  1024 tokens (cut at line breaks) instead of 4096. The model computes attention over a
  whole piece, so memory grew with its length squared. On a 17,000-character text the
  peak went from 4.6 GB to 1.3 GB and detection got ~40% faster, with identical results.
  Text of any length is still processed in full.
- Memory tests on Linux measured the test runner instead of the model: a child process
  inherits its parent's peak memory (`ru_maxrss`) there. They now read the child's own
  peak (`VmHWM`), and a long-document memory test was added.

## [0.5.7] - 2026-09-19

Test build of the new personal-data model, for hands-on checks on macOS and Linux
before 0.6.0.

### Added
- Scope "只處理人名": only people are coded; emails, phones, addresses, dates, IDs,
  companies and places stay readable. On a 13-document test set: 171/174 names coded,
  nothing else touched (270/270 kept).
- Dates are coded (`[DATE_A]`), including dates of birth, and so are record, policy,
  account and passport numbers that follow no fixed format.

### Changed
- Personal data is found by [`openai/privacy-filter`](https://huggingface.co/openai/privacy-filter)
  (Apache-2.0, q4 ONNX, ~945 MB; ~0.5 GB RAM with both models, up to ~1.7 GB on long text), a model made for personal
  data instead of a news-trained NER. It replaces the English model `dslim/bert-base-NER`;
  the CKIP Chinese model now finds Chinese names only. Download it again from
  模型 → 模型管理.
- Only personal data is coded: companies, hospitals, places, diseases, drugs and
  departments stay readable. Public figures in English text in a public context
  (`Apple hired Steve Jobs`) are not coded; a private person with the same name is.
- On a test set written for this change (13 documents), compared with 0.5.6: IDs 8/20 →
  18/20, dates of birth 0/9 → 8/9, false positives 15 → 1, names 172 → 171 of 174.

### Removed
- The word lists and special cases added to work around the old models: generic
  department words, disease eponyms, code widening, lone-surname extension, the extra
  clause-by-clause pass and organization trimming.

## [0.5.6] - 2026-09-19

### Fixed
- Departments, section headings and common acronyms the English model tagged are left
  readable: `Platform team`, `Legal`, `People Operations`, `TIMELINE`, `CISO`, `DOB`, `IP`.
  A tag made only of such words names no one; company names (`Contoso Health`,
  `Dell Technologies`) are still coded.
- A disease named after a person is no longer coded as that person:
  `Parkinson's disease`, `帕金森氏症`.
- When the model tags the letters of a code (`SEC` in `SEC-2026-0419`, a license plate
  `BRT-2291`), the whole code becomes one `[ID_A]` instead of `[ORG_A]-2026-0419`.

## [0.5.5] - 2026-09-19

### Fixed
- US street addresses are found by a rule, so the house number, unit and ZIP code never
  leak: `742 Maple Grove Avenue, Apt 3B, Austin, TX 78704` → `[LOC_A]` (before:
  `742 [LOC_A], [LOC_B], [LOC_C], [LOC_D] 78704`). Needs a house number and a street
  suffix (Avenue, St, Rd...). Works without a model.
- US Social Security numbers (`219-09-9999`) are coded as `SSN`; numbers that can't be
  SSNs (area 000, 666 or 9xx, group 00, serial 0000) are left alone.
- English form fields at the start of a line (`Ticket:`, `Status:`, `Severity:`...) are
  no longer taken for chat speakers.

## [0.5.4] - 2026-09-19

### Fixed
- Taiwan street addresses are found by a rule, not only by the model, so the house
  number never leaks: `地址：桃園市中壢區中央西路二段 76 號 3 樓` → `地址：[LOC_A]`
  (before, only `桃園市` was coded). The rule needs a road and a house number (`號`),
  so `環北路與新生路口` or `第 3 號病床` are left alone. Works without a model.
- Form fields and roles at the start of a line (`申請人：`, `紀錄人：`) are no longer
  taken for chat speakers, so the word `申請人` stays readable throughout the text.

## [0.5.3] - 2026-09-19

### Fixed
- An organization followed by its department (`羅東博愛醫院 家醫科`) gets the same code
  as the organization on its own, in the same text or an earlier message, so one
  hospital no longer shows up as two: `[ORG_B] 家醫科` … `[ORG_B]`.

## [0.5.2] - 2026-09-19

### Fixed
- Multi-line, form-like text (a medical record with 病歷號、身分證、地址... on separate
  lines) no longer hides organizations and places from the models. The models now see
  one line at a time; on a test record, organizations went from 0/4 to 4/4 and places
  from 1/6 to 6/6.
- A single character is no longer coded as an organization or place (`羅[東]博愛醫院`).

## [0.5.1] - 2026-09-19

Test build of the installers, for hands-on checks on an Apple Silicon Mac before 0.6.0.

### Added
- Installers, built and published by GitHub Actions when a `vX.Y.Z` tag is pushed:
  - macOS 14+ (Apple Silicon): `DataFuzzy-x.y.z-arm64.dmg` (ad-hoc signed, not notarized).
  - Linux (x86_64): `DataFuzzy-x.y.z-x86_64.AppImage`, built on Ubuntu 22.04.
  - No models inside; the build fails if a model file ends up in the bundle. Each
    installer is smoke-tested with the real models before the release is created.
- Help → About DataFuzzy: version, license and the licenses of every bundled package.
  The packaging step fails on a license that can't be combined with GPL-3.0.
- App icon.
- `datafuzzy --version` and `datafuzzy --self-test` (headless check of a build).

## [0.5.0] - 2026-09-19

### Added
- Manual marking: select text the detectors missed in a reply, right-click →
  "標記為敏感資料" → person / organization / location / other. Every reply of that code
  file is updated at once, and later input is coded automatically. Marking a person also
  covers their given name on its own; marking a value un-marked before brings back its
  old code.

### Fixed
- A one-character name fragment from the model (`明`) is no longer replaced everywhere
  in the text (it turned `明天` into `[PERSON_B]天`).
- When the Chinese model tags only a surname (`給[顧]秀`), the given name is included.
- New messages always scroll into view, also after un-marking or marking.

## [0.4.1] - 2026-09-19

### Changed
- Higher name recall (measured on a mixed test set: Chinese ~97.6% → ~98.5%, English
  ~99% → 100%, chat logs → 100%):
  - Person names use a lower confidence threshold (0.25) than other entities (0.4).
  - Chinese text gets a second look clause by clause, which only adds people.
  - Chat logs: once one line-start speaker (`王小明：`, `10:23\t王小明\t`, `[10:23] Emma:`)
    is a known person, the other speakers are coded too.

### Added
- Name recall regression test against the real models.

## [0.4.0] - 2026-09-19

### Added
- Un-mark false positives: click a code in a reply to put the original back in every reply
  of that code file. It is never coded again in that file, and text already copied out
  with the old code still restores.
- Code file panel: rename (double-click), delete (right-click) and a code ↔ original preview.
- Restore mode picks the code file that can restore the most codes in the pasted text.

## [0.3.0] - 2026-09-19

### Added
- Chinese NER (`ckiplab/bert-base-chinese-ner`, GPL-3.0, int8 ONNX) for **person,
  organization and location names**, including compound surnames (歐陽娜娜) and
  nicknames (阿明、老王). ~0.2 s load, <10 ms per sentence.
- Mixed Chinese / English text: in auto mode both models run and their results are merged.
- A Chinese given name on its own gets the full name's code (`王小明`, `小明` → `[PERSON_A]`).
- NER decoding supports BIOES tags as well as BIO.

## [0.2.1] - 2026-09-19

### Fixed
- A first or last name on its own now gets the same code as the full name
  (`John Smith` and later `John` / `Smith` → `[PERSON_A]`), in the same input and later ones.
  A part shared by two people (`John` in John Smith and John Doe) is not linked.
  Restoring a linked code gives the full name.

## [0.2.0] - 2026-09-19

### Added
- English NER (`dslim/bert-base-NER`, int8 ONNX via ONNX Runtime) for **person, organization
  and location names**, running fully on-device (~0.2 s load, ~270 MB RAM).
- Every occurrence of a detected name is replaced, and names already in the code file are
  replaced in later inputs even if the model misses them.
- Model manager dialog: download (resumable, SHA-256 verified), delete, first-launch prompt.
  The installer never contains models; downloads come from pinned Hugging Face revisions.
- `DATAFUZZY_MODELS_DIR` to override the model location.
- Inference runs off the UI thread.

## [0.1.0] - 2026-09-19

### Added
- Chat-style desktop app (PySide6) with **Obfuscate** and **Restore** modes.
- Rule-based detection: email, phone (TW / international), Taiwan national ID (checksum),
  credit card (Luhn), IPv4 / IPv6, URL, passwords and API keys / tokens.
- Stable, per-session codes such as `[EMAIL_A]`, `[IP_B]`.
- Code files encrypted with AES-256-GCM using an in-memory key; deleted on window close,
  SIGINT / SIGTERM, and swept on next launch after a crash.
- Language selector (auto / English / Chinese) with CJK-ratio auto-detection.
