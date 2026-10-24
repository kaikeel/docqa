# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) · Versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- Project scaffold: uv-managed Python 3.12 package `docqa`, ruff, mypy (strict), pytest with an
  80% coverage gate, and a test guard that blocks real API clients and network access (T1).
- Domain models, error hierarchy and `Settings.from_env` with documented defaults (T2).
- Loaders for `.md`, `.txt` and `.pdf` (per page) and an overlapping, word-boundary-aware chunker (T3).
