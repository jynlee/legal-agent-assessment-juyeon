# Statute Chunking Design

Date: 2026-08-12
Status: Decided
Covers: ASSIGNMENT.md required work item 2 ("Normalize the corpus and chunk
it under explicit, versioned rules"), extended to the `statute` document kind
added by dataset release `dataset-2026-08-11-v2.1` (schema `source-record-v2`).

This note records the chunking decisions made against all 1,625 `statute`
records in `data/statutes.jsonl` (`inDefaultCorpus=true` on every record; no
additional record-selection filter applies, unlike the 995/1,104 judgement
filter in `reports/decisions/2026-08-10-record-selection-and-document-kind-policy.md`).
It complements, and does not replace,
`reports/decisions/2026-08-11-normalization-and-chunking-design.md`, which
covers `judgement` chunking. It is intended to be folded into the
Architecture report's "normalization and chunking" section alongside that
note. It does not cover embedding, index mapping, or retrieval.

## Summary of decisions

| Area | Decision |
| --- | --- |
| Chunk kind | One: `ChunkType.BODY`, reused as-is — statutes have no headnote/holding-equivalent structured summary |
| Unsplit records | 1,492/1,625 (91.8%) stay below the 1,500-character threshold and become exactly one chunk |
| Split ordering | Table regions are detected and protected **before** marker search runs, not after |
| Oversized protected span | Line-preserving size-budget packing, tagged `layout="table"` |
| Repealed articles (116 records) | Included, not excluded; tagged `status="repealed"` for BM25-first downstream weighting |
| `Chunk` model | Kind-specific fields split into `JudgementChunkFields \| StatuteChunkFields`, not flattened with `\| None` |
| Locator | Same section-path convention as judgement chunks: `"제1조"`, `"제2조 > 1"`, `"별표 8 (조각 2/5)"` |

## Decision 1: One chunk kind, most records unsplit

Statute records already arrive at citable-unit granularity (one record per
article or appendix — DATASET_SCHEMA.md), the opposite starting point from
judgements, which arrive as one whole document needing internal splitting.
So chunking here is a minority-case problem: only records at or above 1,500
characters are split at all.

Measured on the frozen v2 release:

| | Count | Text length (chars) |
| --- | --- | --- |
| `article` | 1,551 | median 387, max 4,802, 87 (5.6%) exceed 1,500 |
| `appendix` | 74 | median 2,019, max 44,761, 46 (62%) exceed 1,500 |

No new `ChunkType` is introduced. A statute chunk is conceptually body text
in the same sense a judgement `body` chunk is, so `ChunkType.BODY` is reused.

## Decision 2: Table regions are protected before marker search, not after

19 `appendix` records contain box-drawing table characters
(`┌┬┐│└┴┘├┤┼─━`) on a line that *also* matches a 가/나/다-style enumeration
marker (e.g. `│마. 법 제5조를 위반하여│...` — a table row whose first cell
happens to start with a valid marker). A marker-first split treats this as a
syntactically valid split point and tears the table row apart — silently,
because the split succeeds and produces pieces under the size threshold, so
no "marker not found" or "still too large" fallback condition ever fires to
catch it.

The chunking order is therefore:

1. Below 1,500 characters: the record's `text` becomes one chunk, unmodified.
2. At or above 1,500 characters: scan for box-drawing table characters first
   and mark each contiguous run of table-formatted lines as a **protected
   span** (start/end offsets), before any marker search runs.
3. Search for 호/목 markers (숫자+`.`, 가/나/다-sequence+`.`, appendix Roman
   numerals Ⅰ/Ⅱ/Ⅲ) only in text **outside** protected spans, and split
   there.
4. If a resulting piece — including a protected span taken whole — is still
   at or above 1,500 characters, fall back to line-preserving, size-budget
   packing (never splitting a line, since a line may be one table row),
   tagging every chunk from it `layout="table"`. Pieces not produced this
   way carry `layout="text"`.

Protecting the table region first, rather than trying to detect a bad split
after the fact, removes the table text from the marker search entirely — the
marker regex cannot fire inside it, so the silent-success case in the
previous paragraph cannot occur.

## Decision 3: Repealed articles are included, tagged, not excluded

116 `article` records (7.1%) are repealed placeholders — the entire `text`
is a pattern like `"제19조 삭제 <2011.3.30>"`, all under 30 characters
(always below the split threshold, so Decision 2 always produces exactly one
chunk for them).

Excluding them would make the system answer `insufficient_evidence` to "약사법
제19조가 뭔가요?" when a direct, correctly-grounded answer exists ("이 조문은
2011년 삭제되었습니다") — the opposite of the grounding-over-refusal mission
this assessment measures. Checked against ASSIGNMENT.md's "Prohibited work"
(record selection and chunking strategy within supplied coverage are
explicitly contributor-owned, per "Explicitly not provided") — no prohibited
item applies to keeping a supplied, in-scope record.

Every chunk built from a repealed record carries `status="repealed"`, a
signal for the (not-yet-designed) index-mapping step to weight BM25
(exact article-number matching) over dense-vector similarity — a repeal
placeholder's embedding carries little independent semantic content. This
note only emits the flag; the indexing behavior that consumes it is a
separate design.

## Decision 4: `Chunk` model split into a kind-specific nested union

The existing `Chunk` dataclass has judgement-only required fields
(`case_name`, `court`, `decided_on`, `case_number`,
`referenced_provisions`, `referenced_precedents`) with no defaults, so a
statute chunk cannot be constructed with it as shipped.

Kind-specific fields move into `JudgementChunkFields | StatuteChunkFields`,
mirroring the `SourceIdentity = JudgementIdentity | GuideIdentity |
StatuteIdentity` discriminated-union pattern already used in `dataset.py`,
rather than making every field `| None` on one flat dataclass — the flat
option was rejected because it lets the type checker miss a judgement chunk
built with statute fields set, or vice versa.

`StatuteChunkFields` carries `law_name`, `unit_kind`, `article_number`,
`appendix_number`, `status` (`"current" | "repealed"`), and `layout`
(`"text" | "table"`). `linked_laws` stays a common `Chunk` field — it comes
from `SourceRecord.linkedLaws`, present at the top level for every document
kind, not from `JudgementIdentity`. `chunk_id` keeps the existing
`"{document_id}#{chunk_type}-{ordinal:03d}"` pattern; `document_id` is
already unique per article/appendix, so there is no new collision risk.

## Decision 5: Locator follows the judgement section-path convention

| Case | Locator example |
| --- | --- |
| Unsplit record (91.8%) | `"제1조"`, `"별표 8"` — the record's own title |
| Marker-split piece | `"제2조 > 1"` |
| Table-fallback piece | `"별표 8 (조각 2/5)"` |

## Verification basis

All counts above were computed directly against `data/statutes.jsonl`
(1,625 records, the full file — every record is `inDefaultCorpus=true`).
The table/marker collision count (19 records) was verified by matching a
가/나/다-sequence-only marker regex (`가나다라마바사아자차카타파하`) against
each line, restricted to lines that also contain a box-drawing character,
re-run once against a looser single-syllable marker regex (19 became 19;
an even looser "any Korean syllable + period" variant over-matched to 19
as well in this check but was rejected as too permissive for the design
itself). Repealed-placeholder count (116) and length distributions were
computed by direct iteration over every record, not sampling.

## Explicitly out of scope for this note

- Embedding calls, index mapping, and whether table-layout or repealed
  chunks are embedded via dense vector, BM25, or both — deferred to the
  index-mapping design; this note only emits the `layout`/`status`
  metadata that design will consume.
- The disposition of the 3 `judgement` records with a sentinel `decidedOn`
  and `judgementType` while `inDefaultCorpus=true` (`precedent-393844`,
  `precedent-408430`, `precedent-408454`) — a separate record-selection
  decision, not yet made.
- Implementing `judgement` chunk-producing logic. As of this note,
  `chunking.py` holds only the `Chunk` model and `split_paragraphs`; no
  record-to-chunk function exists yet for either document kind.

Full design rationale and the brainstorming trail are kept locally at
`docs/superpowers/specs/2026-08-12-statute-chunking-design.md`. That path is
gitignored (`docs/superpowers/`), matching how the judgement chunking and
record-selection work was handled: brainstorming/plan scratch stays local,
and the decided outcome is committed here instead.
