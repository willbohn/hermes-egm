# How Hermes EGM works

Hermes EGM adds fresh-context design review to Hermes Agent. The main agent uses
its project knowledge to help write a design. Reviewers then examine a fixed copy
of that design and selected source excerpts without the earlier conversation.
This helps expose assumptions that were discussed but never written down.

This guide explains the plugin's inputs, model calls, results and activation
settings. Links to the implementation and tests make each part easy to inspect.
For installation and a first review, see the [Quickstart](../README.md#quickstart).

## The two roles

**The main agent** works with the user, reads relevant project files and prepares
the review input. It can draft documents or apply requested changes using normal
Hermes tools. The seven workflow skills guide this work.

**The reviewers** are separate model requests with no tools. They receive only
the supplied text snapshot, the review instructions and the required output
format. They cannot browse the repository, run commands, edit files or ask another
agent to act. They return findings for the main agent and user to consider.

The three review lenses have different jobs:

| Lens | Focus |
| --- | --- |
| `comprehension` | Missing definitions, contradictions and unstated assumptions. |
| `design` | Complexity, scope, trust boundaries and failure handling. |
| `readiness` | Feasibility, interfaces and testable outcomes, checked against the supplied sources. |

A request can use one, two or all three lenses. Each gets a fresh call through the
active Hermes model route. Different lenses do not imply different model families.

## What installation adds

The [manifest](../plugin.yaml) declares one tool, `egm_review`, and three activation
settings. The [entrypoint](../__init__.py) loads the registration function in
[`hermes_egm/plugin.py`](../hermes_egm/plugin.py), which registers the tool, seven
on-demand skills and a short activation section for the main agent's prompt.

There are no extra runtime packages, required credentials, execution hooks,
middleware or background processes. Importing the plugin and rendering its
activation guidance do not start model requests. The plugin uses documented
Hermes APIs rather than replacing core functions.

## Preparing a snapshot

The caller supplies `target`, `documents` and optionally `lenses`:

```json
{
  "target": "design.md",
  "documents": [
    {"id": "design.md", "text": "The proposed design goes here."},
    {"id": "worker.py", "text": "Relevant source text goes here."}
  ],
  "lenses": ["design", "readiness"]
}
```

These IDs are labels, not paths that the tool opens. `target` must name one of the
supplied documents. Omitting `lenses` selects all three. The optional `automatic`
boolean controls automatic-review admission and is not sent to reviewers.

[`ReviewRequest.parse`](../hermes_egm/review.py) checks field names, types, unique
IDs, nonempty text, supported lenses and the serialized size. It accepts 1–8
documents and at most 48,000 UTF-8 bytes for the serialized target and document
lines. Invalid input is rejected before any model request.

The plugin splits each document into lines and calculates a SHA-256 fingerprint
of the serialized snapshot. The fingerprint identifies the target and supplied
text. It does not include the selected lenses or model, verify file freshness, or
establish where the text came from.

### Source selection and coverage

The main agent chooses the excerpts. Relevant interfaces, failure paths and tests
help reviewers check a design against real constraints. Omitted files and
unstated requirements remain outside the review. A small excerpt can support a
focused review, but it cannot establish whole-repository coverage.

Evidence line numbers start at 1 within each supplied text, which may differ from
line numbers in the original file. When using excerpts, retain the original file
location and offset in the surrounding report.

The plugin does not automatically add chat history, memory or unrelated files.
It also does not redact secrets or distinguish ordinary source text from private
history pasted into a document. The selected input must be suitable for the
configured provider's data-use policy.

## Sending the model requests

[`run_review` and `_review_one`](../hermes_egm/review.py) make one concurrent
`ctx.llm.acomplete_structured` request for each selected lens. Each request contains:

- The same target and document lines.
- A reviewer instruction and the selected lens's rubric.
- A JSON schema for the findings.
- Output and timeout limits, plus a purpose label for the host.

No prior conversation, memory, reviewer discussion or tool list is attached.
Hermes owns authentication and routing; the plugin uses the active route without
requesting a provider override or reading credentials. Configured host fallbacks
and provider data policies still apply. Local inference remains local only when
the effective route and any fallbacks are local.

The plugin requests at most 2,400 output tokens per reviewer by default
(configurable via `review_max_tokens`, 256–16384), sets a 90-second
provider timeout by default (configurable via `review_timeout_seconds`, 10–3600)
and stops awaiting the call five seconds later. It does not retry
or repair responses. Hermes may perform its own retries or fallbacks, and stopping
the wait may not cancel work already running at a provider. These limits bound the
plugin's requests, not the final bill.

## Checking the findings

Each finding contains a severity (`blocker`, `major` or `minor`), title,
explanation, suggested action and 1–3 evidence references. Each reviewer can return
at most eight findings.

[`validate_findings`](../hermes_egm/review.py) checks the full response locally,
including exact field names, permitted values and text lengths. Every evidence
reference must identify a supplied document, a valid integer line number and a
nonempty quote that occurs on that line. If any finding fails validation, that
reviewer's entire response is rejected.

This establishes that quoted evidence exists in the snapshot. It does not decide
whether the reasoning follows from the quote. Reviewers can still misunderstand
a requirement, miss a defect or make an unsupported inference. For an omission,
the reviewer cites the nearest relevant requirement and explains the missing part.

The instructions treat document contents as data rather than commands. Returned
text is still advisory and must not be executed automatically or rendered as
active HTML. The tool has no action path that applies a suggested change.

## Reading the result

The tool returns JSON with per-reviewer results, merged findings, a snapshot
fingerprint and host-reported provider, model and token usage.

Runner reports and automatic-policy denials include `automatic`, which identifies
policy-initiated calls. Invalid-input and host-error responses can omit this marker.

| Result | Meaning |
| --- | --- |
| `status: complete` | Every selected reviewer returned output that passed local validation. |
| `status: partial` | At least one reviewer completed and at least one failed. Valid findings remain available. |
| `status: failed` | No reviewer completed, or the host could not finish the review. |
| `outcome: findings` | A complete review returned at least one accepted finding. |
| `outcome: no_findings` | A complete review returned no accepted findings. The design may still contain defects. |
| `outcome: incomplete` | The requested review did not fully complete. |
| `status: invalid_input` | The input was rejected before model calls. |
| `status: skipped`, `outcome: not_run` | Automatic-review policy declined the request; `reason` explains why. No reviewer started. |

Exact duplicate findings are merged and their contributing lenses are retained.
Similar findings with different wording remain separate. No additional model is
used to reconcile disagreements.

Reviewer failures use short categories such as `invalid_response`, `timeout` or
`provider_error`. Raw exception messages and rejected model output are not copied
into the report. Token totals include usage returned by the host; failed calls
can consume usage that is not represented in those totals.

## Activation modes

Settings are available in **Settings → Plugins → Hermes EGM**.

| Mode | Behavior |
| --- | --- |
| `manual` | The main agent uses EGM only for an explicit review request. |
| `suggest` (default) | The main agent can suggest review when a substantial design is ready, then waits for a request. |
| `auto` | In an allowed starting workspace, the main agent can review a substantial draft before implementation without another confirmation. |

Automatic review is intended for meaningful design decisions, not every edit.
It does not enable automatic fixes, background watching or merge blocking.

The `auto_projects` setting lists existing absolute project directories. An empty
list permits no automatic reviews. The plugin resolves paths and matches the
session's starting workspace against these directories. Descendants are included;
similarly named siblings and symlinks resolving outside the directory are not.
This checks workspace scope, not the origin of pasted document text.

Hermes fixes the activation guidance when a session starts. Start a new session
after enabling automatic review, expanding its scope or increasing its budget,
and when switching projects. Revoking the original allowed root, changing mode or
lowering the budget is checked again at each automatic request.

### Automatic attempt limits

`auto_max_reviews_per_session` accepts 1–3 attempts and defaults to 1. Each attempt
can start up to three reviewer requests. Before an automatic request starts,
[`AutoReviewStore.reserve`](../hermes_egm/auto_store.py) uses a SQLite transaction to
check enrollment, project scope, duplicate snapshots and the remaining budget.
Concurrent requests cannot both consume the final available slot.

The same target/text snapshot cannot be automatically reviewed twice in a session,
even with different lenses. Reopening the database or rebuilding the prompt does
not replenish attempts. An admitted attempt still counts if it fails or is cancelled.
Missing session identity, invalid settings and unavailable storage block automatic
use while leaving explicitly requested manual review available.

The main agent supplies the manual/automatic marker. The enforced limits apply to
calls marked `automatic: true`; manual calls are outside those limits. This is a
workflow control, not authentication or a universal spending limit. The skills
instruct the main agent to preserve that distinction rather than relabel a denied
automatic call as manual.

## Local storage and privacy

Automatic enrollment and admission use Hermes's profile-scoped `plugin_db` helper:

```text
<HERMES_HOME>/plugin-data/hermes-egm/automatic-reviews.sqlite3
```

The database stores hashed session, project-root and snapshot identifiers,
attempt counts and ceilings. It stores no document text, model responses, raw
session IDs or raw workspace paths. Hashing does not make predictable identifiers
anonymous or encrypt them.

Enrollment is limited to 10,000 sessions. At capacity, the store refuses new
enrollments instead of deleting old budgets. State survives plugin updates and
removal; deleting it loses the recorded duplicate and attempt history.

The plugin adds no telemetry or custom network client. Normal Hermes conversation
storage and provider logging can still contain review inputs and results. Python
plugins execute as trusted local code; the tool-free reviewer boundary does not
turn the installed plugin into an operating-system sandbox.

## Example and verification

The [webhook input](../examples/webhook-review.json) is an intentionally incomplete
design for trying the workflow. It illustrates how to supply a target document and
related source text. Returned findings cite lines in those supplied texts; compare
each quote with the input and evaluate the reasoning separately.

[VERIFICATION.md](../VERIFICATION.md) describes the checks and tested environment.
The main test areas are:

| Tests | Coverage |
| --- | --- |
| [`test_plugin.py`](../tests/test_plugin.py) | Registration, input rejection and exclusion of injected parent context. |
| [`test_inputs.py`](../tests/test_inputs.py), [`test_review.py`](../tests/test_review.py) | Snapshot input validation and fingerprints. |
| [`test_findings.py`](../tests/test_findings.py) | Output shape, source IDs, line numbers and literal quotes. |
| [`test_runner.py`](../tests/test_runner.py) | Concurrent calls, duplicate merging, failures and cancellation. |
| [`test_policy.py`](../tests/test_policy.py) | Settings and canonical project scope. |
| [`test_activation.py`](../tests/test_activation.py) | Activation guidance and automatic/manual behavior. |
| [`test_auto_store.py`](../tests/test_auto_store.py) | Persistent budgets, duplicate handling, concurrent reservations and revocation. |

Hermes EGM is an independent implementation of the Elephant/Goldfish approach,
not a full port of Google's distribution. It provides snapshot review and workflow
skills rather than autonomous repository reviewers, secret redaction, semantic
proof or exhaustive code coverage. See [NOTICE](../NOTICE) for attribution and
[SECURITY.md](../SECURITY.md) for security reporting.
