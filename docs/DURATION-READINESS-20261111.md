# Duration keyboard readback readiness

## Reproduced cause and scope

The preserved 10s smoke stopped before submission with `Duration keyboard readback failed`.
A subsequent read-only observation reported 10s and a displayed 30-credit price;
that observation alone does not establish the timing of the original failure.
No live keyboard reproduction or further job configuration was performed for this fix.

A real ephemeral offline Chromium fixture using the observed nested Material header
and a native range input reproduces this precise failure class: keyboard input
changes the native position immediately, while the scoped seconds label renders
100ms later. The fixture records native position 0 with the old `8s` label after
Home. Previously the adapter accepted this stale pair, sent ArrowRight, and rejected
the unchanged semantic label as a broken keyboard mapping. The new regression
failed on the old production code with the original error. This proves the code
race, not a measured live render delay or a definitive reconstruction of that run.

## Fix and retained safety boundaries

After each keyboard action, wait for the expected native position and a changed
semantic label when the position changes. No additional key is sent before that
transition is confirmed. The wait has a two-second per-transition deadline and a
ten-second total mapping deadline. Frozen labels remain terminal. The maximum
32 positions/keys, explicit seconds parsing, local component scope, finite bounds,
strict native/ARIA contradiction rejection and repeated/ambiguous semantic gates
remain. Already-selected 10s is verified and returns without keyboard input.
Pre-submit duration and cost validation are unchanged. This readiness wait does
not add configuration attempts or change any durable budget.

Offline regressions cover delayed native rendering to 10s, zero-key already-10s,
frozen rendering without another key, and immediate rejection of contradictory
ARIA during the transition, alongside the existing duration/pre-submit suites.

## Operational exclusions

No live generation, approval, download, prompt edit, profile access, configuration
retry, budget extension, manifest reset or job replay is part of this change.
The exhausted 10s job remains exhausted; no successful live CLI video is claimed.
