# Service-record attribution — draft, paid generation deliberately gated

**This change is not a definitive live submit fix.** The default generation RPC
contract is absent, so a fresh job stops **before the paid click**. No CLI flag
can bypass that guard. Do not deploy this branch or claim paid end-to-end success.
The remaining blocker is the generation invocation's real RPC/configuration
schema, not an invisible asset ID: stable owning records and existing-result
mapping/download have now been exercised against the authenticated service.

## Reproduced cause and observed identity

The old public submit method remembers physical DOM nodes. Re-materializing an
old image tile makes it a second "new" generated card and raises `Multiple
generated cards: attribution uncertain`, even when one genuine result exists.
The exact pre-change submit method from the PR11 base was restored only in an
ephemeral test process. The public offline CLI regression failed with that exact
error, then passed without the sabotage. No production files were reverted.

The passive observer consumes normal browser responses, never issues an API
request, and accepts only the frozen account's successful JSON batchexecute
responses. Observed positional owning records expose:

- `[0]`: stable owning result ID; `[1]`: explicit project; `[2]`: history group.
- `[5][0]`: seconds/nanoseconds; `[5][5]`: thumbnail.
- Image prompt `[5][6][2][0][0]`, numeric model `[6][0][8]`; no global numeric
  model-name mapping is invented. Video prompt/model use their distinct layout.
- Image selected full media: `flow-image-editor .image-container >
  img.read-only-image`, with a signed `flow-content.google/image/<owning-ID>`
  URL. The owning ID, not the group ID, must agree. Signature values stay in RAM.

Decimal response frames count UTF-16 units plus the two framing newline units,
not UTF-8 bytes. ASCII, accents and supplementary emoji regress this. Recursive
JSON decoding stops at a recognized owning record: prompt-authored JSON cannot
become another authoritative record. Observer headers/body, snapshot flushing,
pre-submit baseline and result verification have finite deadlines. Continuous
unrelated responses cannot extend a flush indefinitely.

## Mapping and downloading an existing result

The entire canonical thumbnail path must match one physical requested-kind tile.
Only the observed proxy hosts, exact account query and known size suffixes are
accepted. Unknown URLs and duplicate physical mappings fail closed. A hidden
edit-history result may bind through **explicit same-project/same-kind service
group membership** to one gallery cover, then to its unique exact history output
thumbnail and own full prompt. Input/reference thumbnails are excluded.

Image selection additionally proves the selected full-content owning ID (or the
exact supported thumbnail path), opens the observed resource-info action and
checks the scoped info panel's exact full prompt and cleaned named model. The
composer's current model is never result metadata. The legitimate scoped editor
route is verified separately; it does not widen accepted `--project-url` inputs.
A project title must first have been verified on its gallery, not confused with
the editor's asset title.

Video download is scoped to the exact proved history **clip**, never the scene
builder's possibly stale/combined header export. The observed video editor has
no independent public named-model metadata: the composer is not used as proof.
No internal model alias is invented.

Download/resume reobserves the stable record and checks immutable ownership
metadata while allowing the thumbnail location to rotate. It then rebinds the
fresh path. Original 1K image / 720p video choices, transfer limits, media decode,
PNG conversion, hash, asset-bound receipt and exclusive publication reuse the
existing production machinery. Local receipt recovery still precedes exhausted
remote retry budgets. There is no newest-card or prompt-only selection.

An authenticated, existing-image read-only validation exercised the production
observer, group/card/detail mapper and downloader in a separate diagnostic output.
The resulting PNG matched the prior independently recovered file byte-for-byte.
Historical manifests/receipts remained byte-identical; the dedicated browser was
closed. A separate existing-video validation also used the production observer,
exact history-clip mapper and original 720p downloader and matched the prior MP4
byte-for-byte; its named model comes from the original sealed configuration and
independent prior receipt, not nonexistent video info-panel metadata. This was
**zero new generation**, not a live public submit smoke.
Private prompts, identifiers, signed URLs, screenshots and assets are not fixtures.

## Durable submit boundary and the unresolved contract

Runner persists the job/request hash, frozen project/account, prompt hashes,
effective configuration, reference hashes, baseline record hashes and intent
before the existing synchronous before-click checkpoint. Submit is never
repeated automatically. A recognized provider-installed
`GenerationInvocationContract` must identify the actual RPC and exact prompt and
configuration slots. Configuration equality includes model/type/ratio/count,
duration, reference IDs and declared character/voice. A prompt-bearing search,
list RPC or arbitrary nested string is insufficient. Only the matching `wrb.fr`
frame from that captured request's own response may supply the result record.
Unknown/multi-invocation contracts fail closed. Verified ownership proof is
persisted separately from volatile location evidence for download/resume.

**No real paid-generation request schema was present in the retained recovery
evidence.** Its responses were read-only project/list records. Establishing a
real generation contract requires a legitimately retained prior capture or passive
observation during a future, separately authorized generation. Neither a toy RPC
name nor a model-code guess substitutes for that evidence. No generation was
performed to obtain it in this task. Offline CLI fixtures install an explicitly
synthetic contract solely in their test process; it is not the production default.

Empty projects without a recognized owning-record baseline remain unsupported.
A handle-only asynchronous submit response needs its own observed operation-to-
record contract; none is invented. Identical concurrent requests cannot establish
exclusive authorship; no exactly-once service transaction is claimed. A crash
before durable owning proof remains uncertain and cannot cause another paid click.

## Optional historical evidence audit (not a download command)

```text
python flow.py reconcile --report /path/batch_report.json \
  --evidence /path/independent.json --output /path/new-audit.json
```

This explicitly offline audit binds exact historical report bytes and one
uncertain job to independently retained proof hashes. The output is separately
and exclusively created mode 0600. It does not authenticate supplied assertions,
open a browser, download, clear uncertainty, renew a budget or submit anything.
Hash-shaped assertions alone never authorize a service download.

## Verification scope

Real ephemeral offline Chromium public CLI tests exercise the conditional
submit/download path for images and videos, re-materialized/reordered cards,
direct/grouped history, rotated locations, original-resolution download, real
media decoding, budget-one publication interruption and zero-repay replay.
Additional regressions cover malformed service framing, prompt JSON injection,
wrong project/account/type, duplicate records/physical groups, unknown RPCs,
configuration mismatch, stalled response reads, bounded flushing and exact editor
routes. The independent review is parsed for its actual verdict; CLI exit zero is
not approval. Exact-head local/CI results and remaining blockers belong in the PR.
