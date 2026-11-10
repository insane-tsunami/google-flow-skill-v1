# Saved character association — attachment-only evidence

Observed 2026-11-10 in the explicitly authorized existing account/project using
its existing Chrome CDP session. No profile copying, account switching, prompt
entry, approval, or generation. Only attachments made by this investigation were
removed; saved media were not deleted. Final readback: zero character chips and
empty prompt; picker returned to the original character preview.

## Observed contract

- Picker: `flow-add-menu-popover-content`, `button[role=option]`, exact
  `.asset-title` and character `.type-subtitle`; selected row is
  `.asset-item-active`. Search narrows results; overflowing virtual results are
  rejected rather than silently treating visible rows as globally unique.
- Detail: scoped `flow-character-preview-pane` exposes variant image URLs,
  `.character-voice-card` with full DOM `.character-voice-name` and
  `.character-voice-description`, and exactly one audio sample. Labels can be
  visually CSS-ellipsized while their full DOM text remains available; actual
  textual ellipses are rejected.
- Important interaction: clicking an already active option attaches immediately.
  Do not click it just to inspect details. Use Include in prompt explicitly after
  reading the association.
- Result: one `flow-character-ingredient-chip`, generic button label `Elemento`,
  image matching the selected row thumbnail. Hover exposes image/audio counts
  only, not names. Neither generic label, counts nor a preview ID is an identity.
- Attached characters disappear from the picker. Revalidation therefore checks
  and removes only this adapter-owned chip, rereads the exact saved association,
  reattaches it, and compares the complete in-memory proof. Any mismatch stops
  before payment. No external identity URLs are written into durable reports.
- Actual implementation `attach_character()` and
  `verify_character(..., saved=True)` both completed successfully against the
  live page, followed by removal of their own chip and empty-prompt readback.

## Body observation correction and limits

The earlier read-only report called the second variant a placeholder. Fresh
selection and visual inspection showed an actual front/side/back full-body
reference, not a placeholder. Both variants were loaded (1024×1536 and
1536×1024). The private screenshot, signed URLs, media IDs and voice description
are deliberately not included here.

CLI selects the saved character package, not a separate named Portrait/Body
variant. It does not infer that every second image is Body or promise fidelity.
Known placeholder/missing variant URLs block; semantic detection of arbitrary
placeholder image contents is not implemented. Entries must contain real saved
variant evidence. Images need no voice; videos require the saved associated
voice with full name/description/sample. `--voice` asserts that association, not
arbitrary replacement. `--character-id` remains unavailable because no saved ID
was exposed; use an exact unique name. No generative acceptance or complete live
CLI image/video pipeline is claimed. Existing Direct/model/credits gates remain.

## Test evidence

New real ephemeral offline Chromium tests first failed at collection because
`attach_character` / `verify_character` did not exist (RED). After implementation
these cover attachment, mismatch, duplicate names, explicit/associated voice,
truncation, placeholder URLs, image-without-voice, saved association drift,
pre-submit zero-payment failure and adapter-owned versus human retained chips.
Synthetic fixtures test the observed contract; they are not live generation.

Independent review initially found a retained-owned-chip retry/batch regression.
The ownership check now preserves the proof long enough to validate and remove
only its own chip; targeted consecutive-boundary and human-preservation tests
were added. Final independent bounded Codex re-review returned
`{"verdict":"PASS","findings":[]}`. Full real offline suites passed:
**257 tests on Python 3.10.22 and 257 on Python 3.14.7**. Ruff lint/format,
compileall and diff whitespace checks passed. The final exact-head remote CI
results are recorded on PR8. These are not live-generation acceptance results.
