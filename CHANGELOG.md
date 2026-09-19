# Changelog

All notable changes to this project are documented here.
Versions follow `MAJOR.MINOR.PATCH`: MINOR for tested new features, PATCH for bug fixes.

## [0.6.0] - 2026-09-19

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
