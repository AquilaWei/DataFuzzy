# Changelog

All notable changes to this project are documented here.
Versions follow `MAJOR.MINOR.PATCH`: MINOR for tested new features, PATCH for bug fixes.

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
