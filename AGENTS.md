# hermes-egm

Independent Hermes-native implementation of Elephant/Goldfish design review.
Attribution and distribution details are in [NOTICE](NOTICE).

## Invariants

- Use only documented Hermes plugin APIs. No core monkeypatches or credential reads.
- Goldfish review receives explicitly supplied document/source snapshots, never implicit chat or memory. No reviewer tools, shell execution, file mutation, or automatic repair.
- Fail closed on malformed model output; incomplete review is not a passing review.
- Return advisory findings and preserve incomplete/error states; do not apply suggestions automatically.
- Keep production dependencies and persistent state minimal; test all trust boundaries.
- Preserve third-party license and provenance for any reused material.

## Source map and checks

- `hermes_egm/plugin.py`: native tool, seven skills, frozen per-session routing guidance.
- `hermes_egm/policy.py`: strict operator settings and canonical project scope.
- `hermes_egm/auto_store.py`: atomic automatic-attempt limits; no text/result storage.
- `hermes_egm/review.py`: snapshot, model requests, validation and aggregation.
- `tests/`: deterministic fake-provider unit tests; `examples/`: public demo input.
- `.github/workflows/`: PR checks and reusable pinned-host validation; no model credentials.
- `README.md`: data flow, usage, limits and development setup.
- `docs/REVIEW_GUIDE.md`: implementation and data-flow guide; `VERIFICATION.md`: test coverage and integration checks.

From this repository root, after the README's development setup:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check hermes_egm tests __init__.py
.venv/bin/ruff format --check hermes_egm tests __init__.py
.venv/bin/mypy -p hermes_egm
hermes plugins validate "$PWD" --install-deps
hermes plugins doctor "$PWD" --ci
```

Use `mypy -p hermes_egm`: the repository's hyphenated name and loader `__init__.py`
are not a normal Python package root. Only documented plugin APIs (including
`plugins.plugin_storage.plugin_db`) are allowed; no internal core imports or monkeypatches.
Automatic intent is agent-declared; its limits apply only to automatic calls. Scope
identifies session-start workspace, not document provenance. Reserve before usage; never refund
an admitted attempt on failure/cancellation or reset budgets on re-enrollment.
Follow [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md); record user-visible
changes in [CHANGELOG.md](CHANGELOG.md).
