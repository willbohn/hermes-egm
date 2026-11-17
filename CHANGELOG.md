# Changelog

## Unreleased

### Added

- Weekly validation against current Hermes main and an upstream maintenance report for Hermes and Google EGM, separate from required pinned-host checks.
- Comprehension returns a required short paraphrase alongside findings, exposed as an additive per-reviewer `paraphrase` field. Nonblank text and the 1,200-character bound are validated locally; any invalid output rejects the whole response.

### Fixed

- Local reviewer-output rejections now include a safe `validation_error` code for unavailable parsed output, schema violations and source-citation failures. Strict citation validation, whole-response rejection and incomplete status are unchanged; raw replies are not logged or repaired.

### Changed

- Comprehension receives and cites only the target document, without supporting-source text or metadata. Design/readiness retain the full selected snapshot; caller inputs, finding fields and aggregate snapshot identity are unchanged.
- Review criteria now explicitly cover self-containment, simplicity and alternatives, risks and mitigations, and concrete implementation decisions. The concurrent lightweight workflow remains distinct from Google's staged EGM protocol.

## 0.3.0 (2026-11-16)

### Added

- `review_timeout_seconds` plugin setting (integer 10–3600, default 90) raises the per-reviewer provider timeout and the coroutine deadline (+5s) for slow local models. Invalid values fall back to the default. The timeout is always passed explicitly; omitting it would defer to the host's own default rather than removing the bound.
- `review_max_tokens` plugin setting (integer 256–16384, default 2400) raises the per-reviewer requested output-token budget. Reasoning models spend thinking tokens from the same completion budget; the raised bound leaves room for the findings JSON after the thinking block. Invalid values fall back to the default.
- Regression tests for reviewer deadlines, accepted range boundaries and invalid settings.
- PR checks on Python 3.11 and 3.14, pinned Hermes validation and weekly development dependency updates.

## 0.2.0 (2026-11-06)

### Added

- Native `egm_review` tool with fresh, tool-free comprehension, design and readiness reviews.
- Explicit document snapshots, checked source citations, duplicate merging and per-reviewer results.
- Seven workflow skills for brainstorming, drafting, review, resolution, iteration, drift reports and project documentation.
- Manual, suggested and project-scoped automatic activation, with persistent automatic-attempt and duplicate limits.
- Quickstart, illustrated workflow guides, example results and verification instructions.
