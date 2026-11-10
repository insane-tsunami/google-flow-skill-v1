# Generated-asset attribution and existing-video recovery

## Root cause

The old submit adapter took one gallery ID snapshot after attachment setup, then
accepted the single new ID of **any** media kind. An uploaded reference's gallery
tile can appear after its attached chip is already ready. Its image ID was
therefore recorded as the submitted video while the real generation card was
still progressing. The subsequent video signature rejection was correct; it
must not be bypassed, retried against the image, or fixed by conversion.

The failed manifest and original blocker evidence remain authoritative historical
records. A reserved submit intent and a paid click are separate facts; this job
had one observed generation click, and this recovery made **zero** new clicks.
No measured credit-balance debit/refund is asserted.

## Fail-closed boundary

- Before the click, require owned reference IDs to reach the gallery and an
  unchanged physical-card/ID snapshot for a bounded quiet window. Existing
  structural progress prevents sealing the baseline. Recheck attachments before
  the wait and immediately before the click; retain byte/account/project checks.
- Snapshot physical DOM nodes, including cards without IDs. A preexisting card
  acquiring media is not a new submission.
- Consider only newly created generated components of the requested media kind.
  Require an observed structural progress lifecycle and a separate exact prompt
  text node, bind that physical card, and retain the binding through completion.
  Prompt equality alone, a ready/new ID alone, card position and the newest card
  are never sufficient. Replacement/disappearance, multiple same-kind cards,
  mixed kinds, old IDs or changing identities stop as uncertain.
- Video identity must come from video media, never an image thumbnail/reference
  inside a video component. A known image component cannot initiate a video
  download. Missing supported type/progress/identity evidence stays uncertain;
  it does not enable another generation.
- Require a bounded unchanged completed identity before returning it. Playwright
  readiness timeouts are reported as sanitized identity timeouts.
- The observed video submenu uses **720p — Tamanho original**. Support that exact
  subtitle as for the original image resolution. Do not choose 270p GIF, enhanced
  1080p/4K, or upgrade controls.

The progress-component contract is exercised in offline fixtures, not claimed to
be accepted by every live Flow layout. In the authenticated recovery, ready video
thumbnails/playback URLs did not expose the generated ID through the old generic
DOM extractor. Unknown live contracts therefore remain a deliberate blocker to
future automatic attribution, not a reason to fall back to prompt/newest logic.
No further paid generation was authorized or used to validate a new contract.

## Existing submitted video: separate explicit reconciliation

A read-only exclusive launch of the authorized dedicated profile confirmed the
explicit account route, account UI label and project title. The service's project
response contained one record with the **exact** authorized prompt hash and
project, created within the original one-click observer's completion window. A
second hospital clip had a different prompt hash and earlier timestamp and was
excluded, despite its similar subject/title.

The exact record was mapped to one generated video tile through its service
thumbnail token and known proxy hosts, with uniqueness checked before hovering.
The same physical tile's scoped detail independently confirmed the full prompt,
Omni 1.2 Flash, video, 8s and 720p. Its download action selected only the original
720p submenu entry. This is not attribution by a truncated title or gallery order.
Signed URLs were held in memory; only sanitized candidate metadata/hashes and an
explicit local reconciliation report were retained.

The downloaded MP4 decoded successfully with real FFmpeg/ffprobe: **720×1280**,
**8.042667 seconds**, H.264 video and one AAC audio stream. Both video and audio
were decoded. The original failed manifest, counters, original blocker evidence
and the older uncertain manifest were preserved byte-for-byte. A separate
recovered output and asset-bound receipt record the proved identity; no manifest
was silently rewritten as successful. The dedicated browser was closed.

This establishes an existing-file recovery, **not** a successful end-to-end public
CLI smoke. Dialogue/ASR, exact wording, repetition, voice quality/identity and
visual fidelity have not been independently verified. No publication, WhatsApp,
merge, profile copying or pilot installation/source modification occurred.

## Verification

Real ephemeral offline Chromium regressions cover delayed upload gallery tiles,
video progress-to-ID binding, same-kind ambiguity, ready prompt-only refusal,
reference gallery readiness, missing-reference refusal, preexisting ID-less
cards, image IDs inside video cards, existing progress refusal, known wrong-kind
download refusal and the original 720p submenu. The synthetic full CLI fixture
now publishes uploaded gallery entries and a generated progress lifecycle rather
than relying on the removed new-ID-only behavior.

The delayed-upload regression was also run with the exact old selection logic
restored in memory: it failed by returning the late uploaded image. The 720p
subtitle regression failed before the selector fix. Test/review/CI results for
the final commit are reported in the PR follow-up, not inferred from a prior head.
