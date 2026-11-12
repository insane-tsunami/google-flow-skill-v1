# Character variant slots: ProofChanged(variants) root cause (2026-11-12)

No generation, submit, download or credit-consuming action ran. The uncertain
job `claudete_exploradora_tempestade_20261112_uma01` (configure 1, submit
intent 1, click `not_reached`, failure `ProofChanged[variants]`) was not reset
or replayed; its manifest SHA-256 was unchanged after every observation. Only
the investigation's own character chip was attached/removed in the authorized
dedicated account/project with an empty composer; final state zero chips.
URLs were compared in memory and reported only as per-run salted hashes.

## Evidence

- Fresh picker open, sampled every 100 ms for 8 s: at 0.07 s one variant image
  (loaded), at 0.78 s a second one. Both stayed on the same host with constant
  path and query for the rest of the window; the two have distinct paths and
  distinct natural orientations (portrait vs landscape). No signed-URL
  rotation, no thumbnail-size substitution, no further change.
- Redacted structure of the pane: `.character-thumbnail-row[role=group]` holds
  one `button.character-thumbnail-button` per variant, labelled
  "Miniatura da variante do personagem N". At 0.2 s slot 2 already exists but
  contains `div.character-thumbnail-placeholder`; its image arrives with a fetch
  at ~0.73–0.75 s. The service therefore declares cardinality 2 before the
  image renders.

## Root cause

`picker_character` counted only `.character-thumbnail-image` nodes and sealed
after a 300 ms quiet window. The placeholder slot phase (~0.5–0.7 s) can exceed
that window, so the first proof sealed one variant and the later saved reread
saw two: a partial-DOM render artefact, not a true change of the character.

## Fix

When the variant row exists, every declared slot must contain exactly one
image and no placeholder, and no image may exist outside the slots; the slot
structure participates in the quiet window and the existing 3 s deadline.
Unresolved placeholders still fail closed; exact ordered comparison, wrong
name rejection and real variant drift (`fields: variants`) are unchanged.

Offline Chromium regressions in `tests/test_character_variant_slots.py` fail
on the previous code and pass with the fix. Live, post-fix: three production
saved roundtrips each sealed two variants with no drift.
