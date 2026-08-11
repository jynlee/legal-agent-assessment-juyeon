# Record Selection and Document-Kind Policy

Date: 2026-08-10
Status: Decided
Covers: ASSIGNMENT.md required work item 1 ("Analyze the supplied records and
decide how each document kind is used.")

This note records the record-selection decisions made against the frozen
release (`dataset-2026-08-09`, 1,104 `judgement` records, manifest
`data/release-manifest.json`). It is intended to be folded into the
Architecture report's "record-selection and document-kind decisions" section.

## Summary of decisions

| Group | Records | Decision |
| --- | --- | --- |
| `inDefaultCorpus = false` | 109 | **Excluded** from indexing |
| — of which: sentinel `decidedOn`/`judgementType` (subset of the 109) | 74 | N/A — already excluded by the row above, no separate handling needed |
| `inDefaultCorpus = true` (default corpus, indexed) | 995 | **Included** |
| — of which: body-only, all four summary fields empty (subset of the 995) | 319 | **Included**, indexed from `text` |
| — of which: no `core` law linkage (subset of the 995) | 366 | **Included**, `linkedLaws` strengths retained as chunk metadata |

Net result: **995 of 1,104 records (90.1%) are indexed**, all sourced from a
single provider (대법원 / Supreme Court).

## Decision 1: Exclude `inDefaultCorpus = false` (109 records)

MZO ships these 109 records as `index_eligible`, but marks them outside the
baseline scope (`inDefaultCorpus: false`). `DATASET_SCHEMA.md` states this
boundary is a judgement, not a fact, and explicitly permits including them.

A manual sample of 10 of the 109 records showed they are dominated by two
providers unrelated to the target domain (aesthetic-clinic legal questions):

- `지방세법령정보시스템` (local tax law): property/acquisition/resident tax
  exemption disputes. `linkedLaws` values such as `의료법(candidate)` or
  `소비자기본법(unlinked)` come from incidental phrase matches (e.g. "used
  directly for medical business") inside a tax judgment, not from the case
  being about medical or consumer law.
- `근로복지공단산재판례` (industrial-accident compensation): worker's
  compensation claim disputes, again linked to `의료법` only incidentally.

**Decision: exclude all 109.** Including them would add domain-irrelevant
text to the index for no measurable retrieval benefit, since the target
queries are about aesthetic-clinic legal exposure, not tax or workers'
compensation law. `default_corpus()` in `src/legal_agent_assessment/dataset.py`
already implements this filter (`record.in_default_corpus`).

## Decision 2: Sentinel values (`decidedOn = "00010101"`, `judgementType = "null"`) — resolved by Decision 1

Verification (`scripts/verify_release.py`) reported 74 `sentinel_decision_date`
and 74 `sentinel_judgement_type` warnings. Direct inspection shows both sets
are exactly the 74 `근로복지공단산재판례` records, and all 74 are already
inside the 109 excluded by Decision 1 (`inDefaultCorpus: false`).

**No separate sentinel-handling logic is needed.** Once Decision 1 is
applied, the indexed corpus (995 records, 대법원 only) contains zero sentinel
values in `decidedOn` or `judgementType`. This should be asserted with a test
against the frozen release so a future release with sentinels inside the
default corpus does not pass silently.

## Decision 3: Include body-only records (319 of 995)

319 of the 995 default-corpus records (32.1%) have all four judgement summary
fields (`headnote`, `holding`, `referencedProvisions`, `referencedPrecedents`)
empty (`verify_release.py`: `body_only_judgement`).

**Decision: include.** These are ordinary `judgement` records with
`usage=index_eligible`; only the summary fields are missing, and citations are
drawn from `text`, not from the summary fields. Excluding them would discard
a third of the eligible corpus for a reason unrelated to citation validity.

Follow-up for chunking design (not decided here): normalization/chunking code
must not assume the summary fields are populated, and should have a test case
covering a record where all four are empty strings.

## Decision 4: Include no-core-linkage records (366 of 995)

366 of the 995 default-corpus records (36.8%) have no `linkedLaws` entry with
`strength = "core"` (`verify_release.py`: `no_core_linkage`). Breakdown:

- 84 have at least one `candidate` link (plausibly relevant, not established).
- 282 have `unlinked` links only (surfaced via full-text search, no
  established relevance to the target law).

**Decision: include, not filter.** `no_core_linkage` describes the strength
of a law linkage, not a defect in the record; the judgement text itself is a
valid, licensed, `index_eligible` source. Filtering it out at index time would
also work against retrieval ranking (BM25/vector scoring already demotes
genuinely irrelevant chunks at query time), so filtering here would remove
signal without removing risk.

The linkage strength (`core` / `candidate` / `unlinked`) will be carried as
chunk metadata so it is available downstream for:
- citation confidence signalling in generation, and
- relevance-judgement construction: a test query whose expected answer is a
  no-core-linkage record needs a deliberately-considered relevance label
  (per `DATASET_SCHEMA.md`: "a record linked to a law is not therefore a
  decision about that law"), documented in the Retrieval evaluation report's
  relevance-labelling section.

## Verification basis

All counts above were computed directly against `data/judgements.jsonl`
(1,104 records) and cross-checked against `scripts/verify_release.py` output
(987 warnings, 0 errors: `body_only_judgement` 399, `no_core_linkage` 426,
`sentinel_decision_date` 74, `sentinel_judgement_type` 74,
`duplicate_decision` 14 — these totals are over the full 1,104-record release;
the per-default-corpus figures above are the subset after Decision 1).

## Explicitly out of scope for this note

- Chunking strategy (how body text is split, how headnotes are used if
  present) — separate design decision.
- Duplicate-decision handling (`sourceGroupId`, 13 groups / 26 records inside
  the 995) — this is a test/train-split safety constraint, not a
  record-selection decision; documented separately when the test-set design
  (ASSIGNMENT.md item 5) is brainstormed.
- Relevance-judgement construction — referenced above but decided when the
  Retrieval evaluation design is brainstormed.
