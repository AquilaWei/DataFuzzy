# Changelog

All notable changes to this project are documented here.
Versions follow `MAJOR.MINOR.PATCH`: MINOR for tested new features, PATCH for bug fixes.

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
