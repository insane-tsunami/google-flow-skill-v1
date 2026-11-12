# Image reference upload picker — 2026-11-12

## Real DOM diagnosis (no generation)

The previous `Control unresolved or ambiguous (0 actionable targets)` arose at
`upload_reference` → `control(panel, "upload")`. **Zero matches, not duplicate
controls and not a Flow policy refusal.** The active image composer displayed
Nano Banana 2.1, 9:16, x1. Its add picker now contains:

```html
<flow-add-menu-popover-content>
  <flow-add-menu-side-nav>
    <button type="button" class="sidebar-upload-btn">
      <span class="upload-container">
        <mat-icon aria-hidden="true">upload</mat-icon>
        <span class="upload-text">Fazer upload de mídia</span>
      </span>
    </button>
  </flow-add-menu-side-nav>
</flow-add-menu-popover-content>
```

This is a `button`, accessible name `Fazer upload de mídia`; the icon is hidden
from accessibility. Previous localized exact-name alternatives omitted that
name. Scoped visible exact-name counts before the fix: option=0, button=0,
menuitem=0. With the observed name: option=0, button=1, menuitem=0.
Generated Angular attributes, description IDs, media URLs and private data are
omitted; the regression retains the observed structural classes and icon/name.

## Fix and offline evidence

Add the actual PT-BR label. When the visible side-nav owner exists, require one
owner and one actionable `button.sidebar-upload-btn` with a recognized exact
accessible name. Do not fall back to unrelated picker actions, test IDs or
same-named gallery/detail buttons. Legacy picker roles remain supported when
this owner is absent. No force-click, selector guesses or relaxed identity gate.

- Eight new offline Chromium regressions cover image/initial/final file choosers,
  irrelevant same-named button/tooltip, duplicate button/owner, missing button,
  unknown name and disabled control; failures produce zero wrong/submit clicks.
- The existing eight image+reference+saved-character full-configuration cases now
  use this sidebar DOM and retain reference/character/model/cost drift rejection.
- RED on original code: 8 failed. In-memory sabotage loading original selectors
  **and reloading their safe_ui caller**: 8 failed; fixed code: 8 passed. No
  on-disk production edits during sabotage.
- Complete suites: **421 passed Python 3.14.7; 421 passed Python 3.10.22**.
  Ruff lint/format, compileall and whitespace checks passed.
- Independent read-only Codex review explicitly returned `VERDICT: PASS`, no
  actionable findings; review was static and did not execute tests.

## Authenticated configuration-only proof

The public CLI status returned `authenticated` for the specifically authorized
dedicated profile. The exact existing account/project/title were verified before
inspection. No account switch, new project, checkpoint replay or retry extension.
A separate bounded adapter `configure` invocation (not Runner/submit) succeeded:

- Image Nano Banana 2.1; 9:16; count=1; one local reference; exact saved character.
- Model/reference/character proof re-read successfully; displayed cost=0.
- Exactly **one real upload**, **zero generation clicks**, **zero paid submits**.
  A displayed cost is not a measured credit debit; no generation was requested.
- Only proved owned chips were removed and awaited hidden. A fresh read-only
  visit verified zero chips, empty editor textContent and unchanged blank prompt.
  Chromium exposes innerText as a newline even for this empty editor; an initial
  strict `innerText == ""` diagnostic was false, not evidence of retained text.
- Source PNG hash unchanged. Dedicated browser closed. Original failed manifest,
  counters, files and profile sources preserved; upload adds a gallery asset,
  not a generated output. That gallery asset was not deleted.

This proves authenticated configuration/attachment, **not generation or final
image editing**. No paid job, merge or deployment was performed. Exact-head remote
CI is recorded in the PR thread separately, not inferred from local tests.
