# Normalization and Chunking Design

Date: 2026-08-11
Status: Decided
Covers: ASSIGNMENT.md required work item 2 ("Normalize the corpus and chunk
it under explicit, versioned rules")

This note records the normalization and chunking decisions made against the
995 default-corpus `judgement` records selected by
`select_records_for_indexing()` (see
`reports/decisions/2026-08-10-record-selection-and-document-kind-policy.md`).
It is intended to be folded into the Architecture report's
"normalization and chunking" section. It does not cover embedding, index
mapping, or retrieval.

## Summary of decisions

| Area | Decision |
| --- | --- |
| Chunk kinds | Two: `body` (from `text`) and `summary` (one per numbered issue in `headnote`/`holding`) |
| Body chunking | Structure-aware: split on section headers and `<br/>` paragraphs, pack to 800–1,500 characters, no overlap |
| Section-header matching | Whitespace-tolerant regex on the original text (e.g. `【\s*이\s*유\s*】`), not a whitespace-stripped copy |
| Oversized structural unit | Recursive fallback to its next-lower boundary (sentence/paragraph), not a fixed-width cut |
| Unnumbered `headnote`/`holding` | Treated as issue `1`; this is the majority shape (53.8%), not an edge case |
| `headnote[N]` / `holding[N]` | Kept as separate chunks, linked by shared `issue_ordinal` metadata |
| `referencedProvisions` / `referencedPrecedents` | Excluded from embedded text; kept verbatim as chunk metadata for a future lexical (non-vector) index field |
| Chunk IDs | Deterministic: `{document_id}#{chunk_type}-{ordinal:03d}` |

## Decision 1: Two chunk kinds, both indexed

`body` chunks come from `text`. `summary` chunks come from `headnote` and
`holding`, one per numbered issue. Both are indexed — not headnote/holding
as metadata-only — so a short factual query can match a summary chunk
directly instead of only ever surfacing whole-document body chunks.

A `body_only` record (all four judgement summary fields empty — 319 of 995,
32.1%) produces `body` chunks only; this requires no special case, since
zero issues in an empty field naturally yields zero `summary` chunks.

## Decision 2: Structure-aware body chunking, 800–1,500 characters, no overlap

Judgement text on the frozen release ranges from 485 to 558,135 characters
(median 4,789; p90 19,369; p99 105,336), paragraph-delimited by `<br/>`
(never `\n`), with bracketed section headers (`【이유】`, `【주문】`, ...) and
numbered sub-sections (`1.`, `가.`, `(1)`, ...) already present in the text.

Chunking follows these boundaries — section header, then sub-section, then
`<br/>` paragraph — and packs consecutive paragraphs to a target of
800–1,500 characters. No overlap is used: the boundaries are structural, not
arbitrary fixed-width cuts, so the usual reason for overlap (recovering
context lost to a mid-sentence cut) mostly does not apply. No overlap also
means no chunk shares text with another by construction, which keeps the
required evaluation-leak detection (checking indexed chunk text against
eval query/answer text) simpler.

If a single structural unit itself exceeds 1,500 characters, it is split
recursively at its next-lower boundary rather than cut at a fixed offset.
This only matters for the long tail (p99 ≥ 105,336 characters).

**Addendum (2026-08-13, from the judgement chunking implementation's final
whole-branch review):** packing paragraphs to the character budget without
also respecting the digit-level sub-section boundary let a single chunk's
text span multiple numbered items while its `locator` named only the first
one. Measured against the real release once `chunk_body` existed: 1,075 of
2,834 body chunks (37.9%, across 150/182 records) spanned more than one
marker path this way; the worst case (`이유 > 3 > 나 > (2)`) actually
covered 25 distinct paths. This contradicted this decision's own stated
boundary order ("section header, then sub-section, then paragraph") — the
code honored only the section boundary. Fixed by flushing the pack group
whenever the digit-level component of the locator changes (not on every
locator change — paragraphs sharing one digit, like `이유 > 1 > 가` and
`이유 > 1 > 나`, still pack together), implemented as a grouping step in
`chunk_body` between `_tag_paragraphs` and `_pack_located` rather than a
change to either of those functions.

**Addendum (2026-08-13): `_DIGIT_MARKER` false-matched Korean dates.** The
regex (`^(\d+)\.\s*`, later `^(\d+)\.(?!\d)\s*` after a Task 2 fix round for
decimals) still matched a paragraph opening with a date like `"2011. 6.경
..."` or `"1994. 1. 7. 법률 ..."` as a digit marker equal to the year,
because the lookahead only rejected another digit immediately after the
period, not a date's `<space><digit>.` continuation. Measured: 79
paragraphs across 41/182 records; because a digit marker resets any open
hangul/paren sub-labels, 690 further paragraphs inherited the bogus level
until the next real marker, corrupting 143/2,834 body-chunk locators (5.0%)
across 39 records. Fixed by bounding the digit count to 1-2 (a sub-section
marker is never a 4-digit year) and rejecting a marker immediately followed
by another `<digit(s)>.` group: `^(\d{1,2})\.(?!\d)(?!\s*\d{1,2}\.)\s*`.

## Decision 3: Section headers are matched with a whitespace-tolerant regex, in place

Bracketed section headers in this corpus are typeset with inter-character
spacing as a convention — `【이유】` almost never appears unpadded. Measured
directly against the 995 default-corpus records: an exact, unpadded string
match finds `이유` in only 24/995 and `주문` in 24/995. Matching with a whitespace-tolerant pattern (`re.compile(r"【\s*이\s*유\s*】")`)
against the same, unmodified text finds `이유` in 995/995 and `주문` in
992/995.

The match must run against the record's original text, not a
whitespace-stripped copy: chunking needs the header's exact character
position to split on, and stripping whitespace from the whole document
would also collapse ordinary word spacing in the prose that gets embedded
and shown as citation excerpts. A whitespace-tolerant regex gets the same
detection rate without either problem.

The 3 records where `주문` is still undetected fall back to
`<br/>`-paragraph-only packing for that section, with no header-based
locator path for the affected chunks.

## Decision 4: Unnumbered `headnote`/`holding` is the primary case

Of 676 default-corpus records with a non-empty `headnote`, 364 (53.8%) carry
no `[N]` issue marker at all — this is the majority shape, not a fallback
edge case, and must be tested as such. Any unnumbered field is treated as a
single issue numbered `1`.

`headnote[N]` and `holding[N]` are kept as separate chunks rather than
merged into one, each carrying `issue_ordinal = N` so they can be paired or
cited together downstream without committing to a merge now.

Issue-number alignment between `headnote` and `referencedProvisions` was
checked directly: of 671 default-corpus records with both fields non-empty,
0 mismatches once the same unnumbered-defaults-to-issue-1 rule is applied to
both sides (an initial check without that rule showed 7 apparent mismatches,
all records where `headnote` was unnumbered and `referencedProvisions`
carried an explicit `[1]`; applying the same fallback to both resolves
them). Issue-number metadata matching is safe to rely on for this release.

## Decision 5: `referencedProvisions`/`referencedPrecedents` are excluded from embedded text, not discarded

These fields are lists of statute/case citations, not prose; embedding them
risks adding semantically flat noise to the vector space. They are kept
verbatim as metadata on the matching `summary` chunk (matched by
`issue_ordinal`), so a later indexing design can place them in a separate
non-vector, keyword/text (BM25-searchable) field — keeping a query like
"의료법 제27조 관련 판례" reachable through lexical search without embedding
the citation list itself.

**Addendum (2026-08-13): `extract_issues` silently dropped citations on two
real shapes.** The original implementation assigned into a `dict[int, str]`
(`issues[number] = text`), so a field with a genuinely repeated `[N]` marker
overwrote rather than accumulated (6 field-instances on the real release).
Separately, adjacent markers with no text between them — `"[1][2] <citation>
/[1] <more> /[2] <more>"`, a real shape in `referencedPrecedents` meaning
the first citation applies to *both* issues — were parsed as `[1]` owning
empty text and `[2]` owning the shared citation, then both get overwritten
by the later `[1]`/`[2]` groups; the shared citation was lost from whichever
issue's dict entry didn't survive to be the final write (7 field-instances
carry this grouped shape). Fixed by treating a run of adjacent markers as
one group whose following text is shared by every number in the run, and
accumulating (not overwriting) when the same number's text is encountered
again — verified against the real record carrying this exact shape.

## Decision 6: Deterministic IDs and lineage

`chunk_id = f"{document_id}#{chunk_type}-{ordinal:03d}"` (e.g.
`precedent-000001#body-002`), with ordinals restarting per `chunk_type` per
document. Every chunk records the dataset release version,
`normalization_version`/`chunking_version` (versioned constants bumped when
these rules change), the source `document_id`, `chunk_id` and ordinal, a
`content_hash` of the chunk's own text, `document_kind`, and the judgement
identity fields needed for citation. `summary` chunks additionally carry
`issue_ordinal` and the verbatim provisions/precedents text for that issue.
`linked_laws` is carried through unfiltered, per Decision 4 of the
record-selection note.

`Citation.locator` is populated from this structure so a citation's source
is visible beyond a case number (per DATASET.md's attribution requirement):
the section path for `body` chunks (e.g. `"이유 > 1 > 가"`), and
`"판시사항 [N]"` / `"판결요지 [N]"` for `summary` chunks.

**Addendum (2026-08-13): locator-dedup suffix changed from ordinal-based to
per-locator-occurrence-based, in both chunkers.** `chunk_body`'s
unconditional dedup safety net (mirroring `chunk_statute_record`'s) was
designed as a guard against a rare collision, but measured against the real
release it fires on 874/2,834 body chunks (30.8%) — the primary
disambiguator for a large minority of chunks, not a last resort, because a
single 【이유】 section legitimately restarts "1." numbering many times
(often inside quoted statute text; the worst case, `이유 > 1`, recurs 37
times in one record). The original `" #{ordinal + 1}"` suffix used the
chunk's absolute position in the record, so two unrelated "1." occurrences
became `이유 > 1` and `이유 > 1 #37` — unique, but the number reads as "the
37th piece of this locator" when it is not. Changed to a per-locator
occurrence counter (`이유 > 1`, `이유 > 1 (2)`, `이유 > 1 (3)`, ...) in both
`chunk_body` and `chunk_statute_record`, via one shared private helper, so
the two chunkers stay consistent.

## Verification basis

All counts above were computed directly against `data/judgements.jsonl`,
filtered to the 995 records with `inDefaultCorpus: true`. Bracket-header and
issue-number checks were re-run twice with different methods (raw string
counting and compiled regex matching against the same records) and produced
identical figures.

## Explicitly out of scope for this note

- Embedding calls and index mapping — separate design decision.
- `sourceGroupId` split-safety handling for duplicate decisions (14 groups /
  26 records inside the 995) — a test/train-split concern, decided when the
  test-set design (ASSIGNMENT.md item 5) is brainstormed.
- Further filtering by `linkedLaws` strength or summary-field presence —
  already settled (carried through, not filtered) by Decisions 3 and 4 of
  the record-selection note.

Full design rationale and the brainstorming trail are kept locally at
`docs/superpowers/specs/2026-08-11-chunking-design.md`. That path is
gitignored (`docs/superpowers/`), matching how the record-selection work was
handled: brainstorming/plan scratch stays local, and the decided outcome is
committed here instead.
