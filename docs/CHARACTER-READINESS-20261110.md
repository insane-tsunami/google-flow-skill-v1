# Character revalidation: attachment-only investigation (2026-11-10)

No generation or Runner was invoked. The existing nonempty composer was retained;
only the investigation's own character chip was attached/removed in the authorized
dedicated account/project. No saved character or voice configuration was edited.
Private proof values stayed in memory; no prompt, signed URLs, voice descriptions,
account identifiers or screenshots are included here.

## Reproduced failures

- Production `verify_character(saved=True)` reproduced the original saved-proof
  error. The sole changed field was **`variants`**: the first proof contained one
  reference path and the reread contained two. It was **not** an ordering-only
  difference. `voice`, `description`, `sample` and `thumbnail` did not differ.
- A read-only observer directly after the first picker proof saw the node count
  increase from one to two on its next DOM read, then remain at two through
  further reads at 100, 300 and 600 ms. This demonstrates a partial DOM snapshot,
  not a change to the saved voice or proof of transient URL rotation.
- A separate race reproduced `Preexisting character attachment; refusing to
  replace it`: the owned chip was still visible immediately after its remove
  click and disappeared before later read-only observations. The click completing
  does not establish that Angular finished removing the chip.

## Narrow fixes and evidence

The picker now requires its nonempty source list to remain unchanged for 300 ms,
with a three-second deadline, before sealing the variants. Continuous mutation
fails closed. This is a bounded rendering quiet window, not an assertion that the
service exposes an authoritative total or can never append later. Exact ordered
variant comparison and all character/voice checks remain in force; a later real
change still blocks. No fields are dropped, sorted away or treated as invisible
saved-character IDs. Mismatch exceptions report only a fixed allowlist of field
names, never proof values.

Owned-chip revalidation now waits, with a three-second deadline, for its verified
chip to become hidden before calling the existing strict attachment function.
It does not clear unknown attachments or relax the preexisting-chip refusal.

Both regressions failed in real ephemeral offline Chromium before their fixes:
one sealed a one-item list while the second node rendered asynchronously; the
other rejected its own asynchronously disappearing chip. Further tests retain
real voice-description/variant-drift rejection and verify sanitized field names,
and continuously changing variants prevent attachment.

After both fixes, a live attachment-only run completed three production saved
roundtrips with two reference paths each and `changed_fields: []`. The original
prompt hash was unchanged and the composer ended with zero character/image chips.
The uncertain batch manifest's SHA-256 remained unchanged; no recovery, reset,
submit, generation, download or credit-consuming action was authorized or run.

This establishes character attachment/revalidation behavior only, not a paid
video-generation pass or reconciliation of the existing uncertain job.
