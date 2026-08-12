# Record Selection Update for Dataset v2: Judgement Corpus and Sentinel Records

Date: 2026-08-12
Status: Decided
Covers: ASSIGNMENT.md required work item 1 ("Analyze the supplied records and
decide how each document kind is used."), updating
`reports/decisions/2026-08-10-record-selection-and-document-kind-policy.md`
for dataset release `dataset-2026-08-11-v2.1` (schema `source-record-v2`).
Statute record selection is covered separately by
`reports/decisions/2026-08-12-statute-chunking-design.md`.

## Decision 1 (v1) is superseded, not re-applied

The 2026-08-10 note excluded 109 of 1,104 `judgement` records
(`inDefaultCorpus=false`) as domain-irrelevant (tax and industrial-accident
cases picked up by incidental phrase matches). Dataset v2's `judgements.jsonl`
holds 182 records, and `scripts/verify_release.py` reports `default corpus:
182` / `outside default corpus: 0` — DELIVERY.md states this release already
supplies "182 selected aesthetic-domain judgement records," so the
domain-relevance filtering Decision 1 performed is now done upstream by MZO's
own selection, not by us. There is nothing left to exclude on that basis, and
no action is needed to "re-apply" a filter that no longer has anything to
filter.

Decisions 3 and 4 of the 2026-08-10 note (include body-only records; include
no-core-linkage records, carrying `linkedLaws` strength as metadata) are
policy statements independent of which release they were written against and
continue to apply unchanged to the 182 v2 records.

## Decision 2: the 3 sentinel judgement records inside the v2 default corpus are included, not excluded

`scripts/verify_release.py` against `dataset-2026-08-11-v2.1` reports
`sentinel_decision_date: 3` and `sentinel_judgement_type: 3`, all three
inside the default corpus (unlike the v1 release, where all 74 sentinel
records happened to already be excluded by Decision 1 — see the 2026-08-10
note's Decision 2 — so this is a genuinely new situation, not a repeat).

| documentId | Title | caseNumber | Court |
| --- | --- | --- | --- |
| `precedent-393844` | 진료제한등행정처분취소 | 2015구합12687 | 서울행정법원 |
| `precedent-408430` | 개선명령처분취소 | 2019구합7015 | 청주지방법원 |
| `precedent-408454` | 진료제한3개월처분취소 | 2019구합7183 | 청주지방법원 |

All three are first-instance administrative-litigation judgements
(산업재해보상보험법-designated medical institutions contesting an
administrative penalty). Inspected directly: `caseNumber` and `court` are
present and well-formed; `text` is 3,777–7,666 characters of complete,
structured judgement text (【주문】/【청구취지】/【이유】); `headnote` is
empty (ordinary for this provider, not itself a sentinel). Only `decidedOn`
(`"00010101"`) and `judgementType`(`"null"`) are the sentinel placeholders
DATASET_SCHEMA.md describes.

**Decision: include.** Excluding these three would make the system answer
`insufficient_evidence` to a question a real, on-topic, citable judgement
already answers (medical-institution regulatory litigation is squarely
within this agent's domain) — the same reasoning already applied to
repealed statute articles in the 2026-08-12 statute chunking decision, and
the same failure mode README.en.md's Tier table names ("Missing chunk
lineage... without provenance, `answered` is not reachable" — here the
provenance, `caseNumber`/`court`, is intact; only two display fields are
broken).

**How the sentinel fields are handled downstream:** raw `decidedOn`/
`judgementType` values are preserved exactly as delivered in
`data/judgements.jsonl` — nothing here modifies the release. The
requirement is on the not-yet-built judgement chunk-producing function
(`chunk_judgement_record()`, out of scope for both the 2026-08-11 and
2026-08-12 chunking decisions): it must recognize
`JudgementIdentity.has_sentinel_date`/`has_sentinel_judgement_type` (already
defined in `dataset.py`) and carry an explicit unknown rather than surface
`"0001-01-01"` or the literal word `null` in a citation. This mirrors the
statute chunker's `status="repealed"` flag — a metadata signal for
citation-safe rendering, not a data repair.

## Verified against ASSIGNMENT.md and DATASET_SCHEMA.md before deciding

- ASSIGNMENT.md's seven "Prohibited work" items (external corpus/evaluation
  query indexing/near-copy test claims/legal-advice claims/Peitho/credential
  commits/out-of-namespace index operations) — none apply to a
  record-selection and normalization decision on supplied, `index_eligible`
  records.
- DATASET_SCHEMA.md's "Missing values arrive in three shapes" section (the
  document's own words: "**This is the trap most likely to cost you a
  day**") names this exact pattern — `"00010101"` in `decidedOn`, `"null"`
  in `judgementType` — and states explicitly: "Normalizing them is a design
  decision with consequences — **dropping the records, nulling the fields,
  or carrying an explicit unknown are all defensible** — and that decision
  is yours." This decision's "include, carry an explicit unknown downstream"
  is the third of those three pre-named options, not an interpretation
  stretching the document's intent. The same section confirms
  `validate_release` reports sentinels as warnings only ("it does not block
  the delivery").
- DATASET.md's "Allowed transformations" explicitly lists "select or exclude
  supplied records and explain the decision" and "normalize text while
  preserving provenance and citation identity" — this decision is exactly
  that, and this note is the explanation.
- DATASET.md's "Report a mismatch immediately instead of repairing the
  release locally" is respected: the raw sentinel values are left untouched
  in the source records; only a future citation-rendering layer's *display*
  behavior is constrained by this decision, which is normalization/chunking
  territory DATASET_SCHEMA.md assigns to contributors, not release repair.

## Explicitly out of scope for this note

- Implementing `chunk_judgement_record()` itself, including the sentinel-safe
  citation rendering this decision requires of it — no judgement
  chunk-producing function exists yet (see
  `reports/decisions/2026-08-12-statute-chunking-design.md`'s equivalent
  scope note).
- Statute record selection — covered by
  `reports/decisions/2026-08-12-statute-chunking-design.md`.
