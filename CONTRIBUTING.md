# Contributing

Hermes EGM is an independent Hermes plugin inspired by Elephant/Goldfish design
review. Keep changes focused and use documented Hermes plugin APIs. Preserve the
snapshot-only, tool-free reviewer design. Discuss larger changes before implementation.

## Making a change

1. Create a branch and describe the behavior being changed.
2. Add regression tests for changed behavior. Distinguish fake-provider tests from
   live model checks.
3. Run the unit tests, Ruff, strict mypy and plugin validation commands in the
   [development guide](README.md#development-and-verification).
4. Update affected documentation and `CHANGELOG.md` under Added, Changed, Fixed or Removed.
5. Open a pull request explaining the change and checks performed. Security and
   privacy changes require focused independent review.

AI-assisted contributions are welcome. Disclose material AI assistance in the
pull request and describe the checks performed. This implementation was developed
with Hermes Agent assistance.

## Continuous integration

Pull requests run unit tests on Python 3.11 and 3.14, Ruff, strict mypy, and
validation/registration against a pinned Hermes host. No provider credentials or
live model calls are used in CI. Keep action references pinned to full commit
SHAs. Dependabot checks development tools and Actions weekly; updates still need
passing checks and review. Host pin changes are reviewed separately.

Semgrep checks new pull-request findings and runs full default-branch scans without
provider credentials or a Semgrep account. Findings and scan errors fail the check.

## Releases and catalog updates

Release tags, the plugin manifest and catalog entries must describe the same
source version. Catalog entries use a full commit pin and matching capabilities,
compatibility metadata and artwork links. Validate the pinned source before
submitting an entry or updating an existing submission.

Prepare the manifest version and changelog in a pull request. After its checks
pass and it merges, publish a tag and release at that exact commit. Include an
immutable install command in the release notes. For changes to reviewer requests,
run a bounded manual live-model smoke test with public sample input; CI's fake
provider is not evidence of live inference. Update the catalog in a separate
upstream pull request, never by moving an existing release tag.

Follow the current [Hermes catalog submission guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission).
Catalog review and merging are handled by Hermes maintainers.

## Conduct and security

Keep discussion respectful and focused on the change. Report vulnerabilities
using the process in [SECURITY.md](SECURITY.md), without publishing secrets or
sensitive review inputs.
