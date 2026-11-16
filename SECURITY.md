# Security

Supported scope: the current 0.3.x implementation. Reviewers receive explicit text
snapshots through Hermes's host-owned LLM route. They have no tools. The plugin has
no custom network client, credential reader, project-file reader/writer, background
process or self-updater. Installed Python plugins remain trusted code, not OS sandboxes.

Do not send credentials, private history or data disallowed by your provider's terms.
There is no automatic redactor. Host/provider retries, routing, logging and retention
remain their responsibility. A cancelled wait may leave a provider request running.

Automatic calls require operator opt-in, an enrolled host session in an allowed
starting workspace, and an atomic duplicate/budget reservation. The plugin stores
only hashed session/root/snapshot identifiers and counters in its profile-scoped
SQLite data file. Invalid settings/state fail closed for automatic use. Manual
reviews still work when explicitly requested. Failed/cancelled admitted automatic
attempts are not refunded. These are attempt limits, not a billing guarantee.

The main agent declares manual versus automatic intent. Calls marked manual are
outside the automatic-only attempt limits. Project scope
matches session-start directory metadata, not supplied-text provenance. The plugin
is advisory workflow automation, not a data-loss-prevention or permission system.
No review text/results are retained in its admission database; host logging differs.

Model output remains untrusted even after JSON/citation validation. Do not automatically
execute suggestions or render returned text as active HTML. A literal citation is not
proof that a conclusion is correct; findings still require evaluation.

Report a vulnerability privately through the repository's Security Advisory channel
when available. Otherwise request a private contact channel without posting exploit
details or secrets publicly. Never attach auth files or real sensitive review inputs.
