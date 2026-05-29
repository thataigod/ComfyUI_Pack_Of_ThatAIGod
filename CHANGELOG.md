# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/), and this project adheres to [Semantic Versioning](https://semver.org/).

## [1.2.0] - 2026-05-30

### Added
- Retry with exponential backoff for transient HTTP errors (429, 502, 503) and network errors in LLM streaming
- Mtime-based file content cache in WildcardReader, eliminating redundant disk reads
- Python docstrings on all public classes and functions
- CHANGELOG.md and CONTRIBUTING.md
- Tests for retry logic and wildcard content caching (203 total tests)

### Changed
- Removed `del api_key` security theater (Python strings are immutable)
- Added debug logging to `fetch_openrouter_credits` on failure
- Fixed CI mypy step to run directly in project root instead of temp directory copy hack

### Fixed
- Added `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/` to `.gitignore`

## [1.1.0] - 2026-05-15

### Added
- LLM Chat node with OpenRouter and local LLM support
- LLM Fallback Switch node
- Dynamic Resolution Picker with 12 aspect ratio presets
- Wildcard Reader with deterministic, random, and no-repeat deck modes
- Sequential Image Loader with natural sort ordering
- Upscale By Max Side node
- Truncate LLM Thinking node
- Streaming WebSocket responses for LLM output
- Response caching (last 10 requests)
- Vision support for multimodal LLM models
- Pre-commit hooks (ruff, mypy, trailing whitespace)
- GitHub Actions CI across Python 3.10-3.14
- 194 tests with 99% code coverage
