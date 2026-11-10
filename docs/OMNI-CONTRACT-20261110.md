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

## Initial live boundary and configuration budget

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

## Explicit bounded extension and final live stop

The user subsequently authorized **at most two additional configurations** of
the same smoke, not another payment or a reset. The new operational option
`--additional-configuration-attempts 2` requires `--retry-configuration`,
`--max-attempts 10`, one exact job, and an allowlisted failed configuration at
counter 10 without submit/asset/result/output. A durable per-row
`configuration_extension: {base: 10, additional: 2}` records this limited grant.
It cannot be renewed or changed by repeating the flag. The configuration ceiling
is separate from the unchanged download budget, counters/history/fingerprint
are preserved, and submit remains at most one durable intent. Matching-marker
replay validates counters and post-submit consistency. A general guard also
prevents an inconsistent submit-without-asset checkpoint from spending twice.

Extension tests first failed before implementation. Independent review initially
found malformed matching-marker replay could bypass eligibility; six additional
regressions failed before strict counter/state validation and the submit guard,
then passed. The bounded re-review returned PASS. The first extended live
configuration (counter 11) failed immediately reading the character picker after
the add click. A real offline Chromium delayed-popover regression reproduced
zero actionable targets; a strict finite three-second visible wait fixed that
readiness race without relaxing uniqueness/voice/attachment gates. Its separate
bounded review returned PASS.

The second and final extended live configuration (counter **12**) succeeded and
read back Omni 1.2 Flash, 9:16, count 1, one image reference, 8s and visible cost
**24 credits**, with the saved character attached. The Runner durably reserved
`submit: 1` and `uncertain` before entering the submit adapter. Saved character
revalidation then raised **`Saved character or associated voice changed`** at
`elements.verify_character`'s complete-proof comparison. This happened before
the generation click in `UIAdapter.submit`. The sanitized diagnostic does not
establish which proof field differed; do not claim the voice specifically changed.

**Final stop:** state `uncertain`, error `submit_or_identity_unconfirmed`,
configure 12, submit-intent 1, no download counter, asset, result or MP4. The
generation click was not reached; no paid retry was attempted. A credit-balance
ledger was not queried, so the observed 24-credit price is not a measured debit.
The original fingerprint and all eleven recovery-history entries remain.
No further live configuration, reconciliation, reset or generation is permitted
by this exhausted extension. Browser shutdown completed and no dedicated-profile
process remained. This is an identity/association gate, not a login failure or
policy refusal. Audio, duration of a result, fidelity and MP4 validation remain
unproven because no video was generated.

The final exact-command terminal replay returned exit 1 without starting a
browser and left the manifest bytes and counters unchanged. Final isolated
offline Chromium suites passed **351 tests** each on Python 3.14.7 and 3.10.22;
Ruff lint/format, compileall, CLI help and diff checks passed. These are offline
safety evidence, not live video acceptance.
