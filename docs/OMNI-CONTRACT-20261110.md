# Omni duration and uploaded-image contract (2026-11-10)

## Duration

Omni's observed Material control is a native range inside
`.duration-slider-section`, with a nested `.duration-slider-header` containing
`.duration-slider-title` and `.duration-slider-value`. A raw index **5** and
`aria-valuetext="5"` corresponded to rendered **8s**. The raw index is not seconds.

The adapter reads semantic duration only from the scoped rendered label and/or
explicit duration-bearing accessible text. Conflicting or unknown evidence
fails closed. Native live input value/min/max take precedence as control state;
contradictory ARIA position or bounds are rejected, not silently ignored.

If duration is already correct, no keyboard input is sent. Otherwise a finite
range of at most 32 positions is traversed with Home/ArrowRight and observed
semantic readback; no hard-coded index-to-seconds conversion is used. Existing
radio/button/tab duration controls remain supported. Configuration and the
immediate pre-submit boundary share this readback. Price confirmation and drift
rejection remain unchanged.

## Uploaded Elements images

The observed attached image is a `flow-image-ingredient-chip` with a direct
`button.chip-container[aria-label="Elemento"][aria-busy="false"]`, containing
`div.chip-image-wrapper > img.chip-image[alt="Imagem do elemento"]`. It need not
expose `data-media-id`. In this exact component only, the adapter derives the
UUID from the strict HTTPS `flow-content.google/image/<UUID>` path. Generic
images, unknown origins/paths, ambiguous chips and conflicting explicit IDs do
not establish identity. Signed query strings remain in memory and are not
returned as identity or added to reports.

An in-flight chip may not yet contain an image. The observed
`div.chip-image-wrapper > div.chip-placeholder` can coexist with
`aria-busy="false"`; a later read showed the real image. Only the exact busy-button
state or this exact placeholder with zero images is retryable inside the
invocation owning the upload, under the existing finite 60-second deadline.
Neither state is accepted as identity proof; both still reject at preflight or
pre-submit. Once ready, all previous IDs must remain and exactly one new ID must
be established.

## Evidence boundaries

Offline regressions use real ephemeral, offline Chromium and synthetic service
URLs. Observed nested-header, native/ARIA conflict, image-chip identity and busy
readiness regressions each failed before their respective fixes. The first
independent slider review found the ARIA conflict; the fix and its regressions
were re-reviewed PASS. Image identity and its subsequent readiness delta also
received separate bounded PASS reviews. Reviewer exit status alone was never
treated as a PASS.

The first overlapping local suite runs hit the existing two-second synthetic
download deadline (resolution-menu interruption tests); no production timeout or
test deadline was increased. The six resolution-menu tests passed both on the
unchanged baseline and current source when run alone. A subsequent isolated
full Python 3.14 suite passed before the final busy-readiness delta. Final suite
and live smoke outcomes are recorded separately rather than inferred from these
fixtures or reviews.

## Live boundary and configuration budget

The authorized existing smoke retained its original fingerprint and all recovery
history. Its ten configuration attempts failed before submit intent; the report
has no submit or download counter, asset, or result. The final observed failure
was the zero-image placeholder state described above, not a login challenge.

After the placeholder fix, a separate upload-only diagnostic called the actual
production upload/reference functions successfully against the authorized page
and read back exactly one reference. That diagnostic did not call configure or
submit and did not write the smoke manifest. It is attachment acceptance, not a
successful video generation or proof of the voice/audio result.

The current CLI hard-limits `--max-attempts` to 10. Because that preserved budget
is exhausted, no further full smoke retry or generation was performed, and no
budget/manifest workaround was introduced. Completing the smoke requires an
explicitly approved bounded budget extension with retained counters; deleting or
resetting the report is not an acceptable recovery. No MP4 exists for this job.

Existing smoke manifests and recovery counters are preserved. Configuration
retries are explicit, bounded and permitted only before submit intent. No merge,
profile copying, credential changes, policy approval bypass, or WhatsApp
publication is part of this change.
