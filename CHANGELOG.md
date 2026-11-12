# Changelog

## Unreleased

### Added

- `review_timeout_seconds` plugin setting (integer 10–3600, default 90) raises the per-reviewer provider timeout and the coroutine deadline (+5s) for slow local models. Invalid values fall back to the default. The timeout is always passed explicitly; omitting it would defer to the host's own default rather than removing the bound.
- `review_max_tokens` plugin setting (integer 256–16384, default 2400) raises the per-reviewer requested output-token budget. Reasoning models spend thinking tokens from the same completion budget; the raised bound leaves room for the findings JSON after the thinking block. Invalid values fall back to the default.

## 0.2.0 (2026-11-06)

### Added

- Native `egm_review` tool with fresh, tool-free comprehension, design and readiness reviews.
- Explicit document snapshots, checked source citations, duplicate merging and per-reviewer results.
- Seven workflow skills for brainstorming, drafting, review, resolution, iteration, drift reports and project documentation.
- Manual, suggested and project-scoped automatic activation, with persistent automatic-attempt and duplicate limits.
- Quickstart, illustrated workflow guides, example results and verification instructions.
