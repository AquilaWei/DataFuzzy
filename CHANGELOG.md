# Changelog

All notable changes to this project are documented here.
Versions follow `MAJOR.MINOR.PATCH`: MINOR for tested new features, PATCH for bug fixes.

## [0.1.0] - 2026-09-19

### Added
- Chat-style desktop app (PySide6) with **Obfuscate** and **Restore** modes.
- Rule-based detection: email, phone (TW / international), Taiwan national ID (checksum),
  credit card (Luhn), IPv4 / IPv6, URL, passwords and API keys / tokens.
- Stable, per-session codes such as `[EMAIL_A]`, `[IP_B]`.
- Code files encrypted with AES-256-GCM using an in-memory key; deleted on window close,
  SIGINT / SIGTERM, and swept on next launch after a crash.
- Language selector (auto / English / Chinese) with CJK-ratio auto-detection.
