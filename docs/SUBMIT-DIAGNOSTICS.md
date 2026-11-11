# Sanitized submit diagnostics and already-paid reconciliation

## Diagnostic contract

`failure` records a fixed stage, allowlisted exception class, repository-only
basename/line frames and (for a saved-character proof mismatch) fixed field names.
It never formats the original exception, captures locals, persists voice values,
or stores page, media, thumbnail or download URLs. Unknown classes become
`Exception`; exception chains are not expanded.

The production adapter reports authentication, project, references, direct mode,
character, configuration, cost, baseline and click boundaries to the Runner.
The Runner synchronously persists every event through the existing atomic
fsync/rename checkpoint. `baseline_evidence` keeps only physical-card/ID/progress
counts. Lifecycle evidence keeps bounded candidate counts and a bound flag;
unchanged observations do not write repeatedly.

- `not_reached`: this invocation has not reached its instrumented click boundary.
- `uncertain`: intent was persisted immediately before invoking the click.
- `returned`: Playwright's click returned, **not** proof of acceptance or debit.

A write failure at the boundary prevents the subsequent click. Failure after the
click retains uncertainty, even if the asset never appears. Observer teardown is
local only; no paid retry or manifest reset was introduced. Legacy uncertain
manifests remain terminal and are not retroactively assigned new evidence.

There is still no exactly-once browser/server/disk transaction. A crash can occur
between any of those boundaries. These fields improve diagnosis, not billing
measurement or permission to submit again.

## Authenticated read-only finding and recovery

An existing ten-second server generation was independently identified by its
explicit project membership, exact prompt SHA-256, original submission timestamp,
internal model identifier and requested duration. Multiple prompt occurrences
were inside the same owning record, not multiple generations.

Its thumbnail contained no UUID. The server used `lh3.googleusercontent.com`
and the displayed tile used `flow.google.com`; their **entire parsed paths were
identical**, with only account-routing query data on the latter. Exactly one of
eleven physical video tiles matched. Opening that tile independently exposed the
exact requested prompt and model in the detail. No newest-card or prompt-only
selection was used. Private paths/URLs remained in memory.

The original `720p / Tamanho original` menu option produced a real MP4:
720×1280, H.264 video, AAC audio, 10.026667-second container duration. FFmpeg
fully decoded it. Download/reconciliation used a separate private output and
receipt; the failed CLI manifest and its counters were preserved unchanged.
No new generation was submitted and no new credits were consumed. The old
service debit was not measured. This is **not** a successful public-CLI video
smoke or a retroactive diagnosis of the original uninstrumented exception.

A lightweight cached CPU ASR found speech in Portuguese but did not confirm the
complete requested script; it appeared abbreviated/repeated. A frame inspection
confirmed the character and news headline. Accent and lip sync were not verified.
No silent prompt shortening or automatic content-policy evasion was attempted.

The live completed video tile exposes a thumbnail, not the synthetic fixture's
stable media-ID contract. Fresh paid public-CLI lifecycle attribution remains an
external gate; this manual recovery must not relax that gate.

## Verification

Real ephemeral offline Chromium tests inject saved-proof mismatch, post-click
failure, real lifecycle timeout, observer failure and atomic-persistence failure.
They assert durable stages/counters, zero click before boundary failures,
non-repetition after one click, redaction and byte-preserving uncertain replay.
Disabling the production observer makes the character-stage regression fail.
Existing delayed-upload, physical-card, media-kind and progress regressions remain
required. Offline behavior is not authenticated service lifecycle acceptance.
