# Changelog

All notable changes to this project are documented here.
Versions follow `MAJOR.MINOR.PATCH`: MINOR for tested new features, PATCH for bug fixes.

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
