# Verification

This page describes the plugin's test coverage and recorded integration checks.
For the implementation and data flow, see [How Hermes EGM works](docs/REVIEW_GUIDE.md).

## Reproduce the checks

After the [development setup](README.md#development-and-verification), run:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check hermes_egm tests __init__.py
.venv/bin/ruff format --check hermes_egm tests __init__.py
.venv/bin/mypy -p hermes_egm
hermes plugins validate "$PWD" --install-deps
```

The unit suite uses deterministic tests and a fake model facade to
exercise input and output validation, request isolation, concurrency, failures,
activation policy and persistent attempt limits. These tests do not measure the
quality of a model's design advice.

## Automated checks

The [Checks workflow](.github/workflows/checks.yml) runs on pull requests and
pushes to `main`. It runs the unit suite on Python 3.11 and 3.14, plus Ruff and
strict mypy on Python 3.14. The reusable [Hermes validation workflow](.github/workflows/hermes-validation.yml)
installs the pinned host's locked dependencies, validates the plugin and runs
Plugin Doctor in a separate Hermes home without provider credentials. Doctor
checks discovery, import and registration, not live model inference or automatic
admission end to end.

The host pin is Hermes v0.23.1, commit
`3b421578588243f920886e6fe79a6faa87ea026e`. Local validation and Doctor passed
against this revision. This pin does not prove every build above the manifest's
minimum version is compatible. CI run logs are the current verification record;
the integration results below describe the earlier release environment.

## Recorded integration checks for v0.2.0

| Check | Recorded result |
| --- | --- |
| Unit suite | 47 tests passed. |
| Ruff lint and formatting | Passed. |
| Strict mypy | Passed for all five package source files. |
| Hermes plugin validation | All 15 checks passed, with no warnings; scanner verdict `safe`. |
| Plugin Doctor | Discovery, import and registration passed; one tool and no execution hooks. |
| Public GitHub installation | Installed through the normal Hermes plugin installer; installed source matched the requested commit. |
| Native activation and storage | Default settings, session enrollment, reservation, duplicate/limit denial and revocation checked through real host APIs with outbound networking blocked. |
| Live manual review | Fresh Hermes sessions discovered and invoked the native tool through the active provider. |

The native activation check exercised registration, settings, prompt rendering,
the tool registry and Hermes's SQLite helper. It made no model requests. Live
provider calls were manual; unattended automatic model selection has not been
verified end to end.

## Example input

The repository includes a [public webhook design](examples/webhook-review.json)
for trying the review workflow. Its intentionally incomplete requirements make it
useful for checking input selection and source citations. It is not a benchmark of
reviewer quality.

## Tested environment

- Linux.
- Hermes `v0.22.7+689.g5248c8d`, upstream commit
  `5248c8d30c9c4695a2749d2c31243438342c4f41` for the recorded integration checks.
- Hermes Python 3.14.9; development checks on Python 3.14.10.
- Ruff 0.14.14 and mypy 1.18.2.
- No third-party runtime dependencies added by the plugin.

The plugin requires Python 3.11+ and a Hermes build with the documented plugin
LLM API; the manifest declares Hermes `>=0.22.7`. Development builds sharing a
version number can differ. macOS and Windows smoke tests have not been run.

## Coverage and limits

The checks cover malformed inputs, unexpected fields, source-quote validation,
partial failures, cancellation, canonical project scope, missing session identity,
revocation, concurrent reservations, persistent limits, repeated enrollment and
storage failure. They also check that host-supplied parent context is not forwarded
to reviewers and that rejected input starts no model requests.

Source inspection of the tested Hermes host confirmed that structured requests
build fresh messages from the supplied prompts, schema and inputs. The plugin
performs its own output validation, including when the host's optional
`jsonschema` dependency is absent.

The seven workflow skills are registered and present. Every prose workflow has
not been exercised as a separate end-to-end scenario. The results do not establish
compatibility with every provider adapter or future Hermes build, resistance to
every prompt injection, semantic correctness of findings, or hard billing limits.
