# Source Record Schema

[DATASET.md](DATASET.md) governs how the release is delivered and what you may
do with it. This document describes what one delivered record looks like, so
that normalization and chunking can be designed before the release arrives.

The contract is the Pydantic models in
`src/legal_agent_assessment/dataset.py`, with deterministic checks in
`src/legal_agent_assessment/dataset_validation.py`. This prose explains them;
where the two disagree, the models are the contract and the signed release
manifest outranks both.

## What this document fixes, and what it leaves open

MZO fixes the **input** side: source identity, provenance, citation
coordinates, admission, usage disposition, and release integrity. Fixing it
keeps the comparison from turning into an exercise in parsing heterogeneous
files, and it is what lets MZO rerun every submission.

MZO fixes nothing downstream of that. Record selection within the supplied
coverage, normalization, chunking, index mapping, retrieval, test sets,
relevance judgements, metrics, and prompts are yours, as
[ASSIGNMENT.md](ASSIGNMENT.md) states. Every indexed chunk must trace back to
exactly one source record; the chunk's identifier, ordinal, boundaries, and
metadata shape are your outputs, not fields of this schema.

No counts appear in this document. The release manifest is authoritative for
every number.

## Format and naming

Records are JSONL, one object per line, UTF-8. Field names are English
`camelCase`; the collector maps source-native Korean keys at the boundary.
Python attributes are `snake_case`, so `model_dump(by_alias=True)` produces the
wire form and `model_validate` accepts it.

Unknown fields are refused. A field you did not expect is a delivery problem to
report, not something to route around.

## The record

Every record carries these, regardless of kind:

| Field | Meaning |
| --- | --- |
| `documentId` | Stable, unique identity for one supplied document |
| `sourceGroupId` | Split safety: records that are the same underlying decision share one |
| `documentKind` | `judgement` or `official_guide` |
| `title` | Human-readable name |
| `text` | The supplied source text, as delivered |
| `contentHash` | `sha256:<64 lowercase hex>` of `text` |
| `identity` | Citation coordinates, discriminated by `documentKind` |
| `provenance` | Provider, publisher statement, URL, reference, acquisition time, text extraction, optional retained artifact |
| `admission` | `exempt`, `licensed`, or `restricted` |
| `attribution` | Required when `admission` is `licensed` |
| `usage` | `index_eligible` or `evaluation_only` |
| `inDefaultCorpus` | Whether the record is in MZO's baseline coverage |
| `linkedLaws` | Target laws and this record's relationship to each |
| `limitations` | Known gaps, stated rather than repaired |

One record is one whole source document. A 108-page guide arrives as a single
record holding its full text; splitting it into citable units is chunking.

`rawArtifactPath` and `rawArtifactHash` are optional and are set together or
not at all. Retaining the response bytes is a separate decision from recording
where the text came from; a path without a hash would read as "artifact
retained" while being uncheckable.

### Permission and scope are different questions

`usage` is a permission and a hard boundary. `evaluation_only` material must
never reach an index, and nothing you decide changes that.

`inDefaultCorpus` is scope. Some records are supplied deliberately while
sitting outside MZO's baseline coverage: they surfaced through full-text search
against the target laws and are citable and index-eligible, but their subject
matter sits away from the questions this agent is built to answer. MZO's
default is to leave them out.

**You may include them.** Widening the corpus to supplied records outside the
default is ordinary record selection, which [DATASET.md](DATASET.md) already
lists as an allowed transformation, and the reason it is allowed is that the
boundary is a judgement rather than a fact. Explain the decision either way.
This is not "adding corpus data" — the prohibition in
[ASSIGNMENT.md](ASSIGNMENT.md) is about material from outside the release.

`default_corpus(records)` gives the baseline. `select_index_inputs(records)`
governs what may be indexed at all, and it does not consult `inDefaultCorpus`.
A record can be outside the default corpus and perfectly indexable; an
`evaluation_only` record is neither.

### Judgement identity

`caseSerial`, `caseName`, `caseNumber`, `court`, `caseCategory`, `decidedOn`
(`YYYYMMDD`), `judgementType`, plus four summary and cross-reference fields:
`headnote`, `holding`, `referencedProvisions`, `referencedPrecedents`.

**`caseSerial` is the key. `caseNumber` is not**, and the reason matters more
than the rule.

Case numbers repeat, and where they do, the records share the court and the
decision date as well. These are not different decisions that reused a label:
they are **the same decision registered twice under different serial numbers**,
with text that is byte-identical in some pairs and differs only slightly in the
rest.

That makes it a split-safety problem, not a bookkeeping one. Put one of a pair
in your test set and index the other, and your retrieval system will find a
near-copy of the answer and your run will score it as recall — the outcome
[ASSIGNMENT.md](ASSIGNMENT.md) prohibits presenting as real-user quality.
Deduplicating by `caseSerial` does not help, because the two records have
different serials; that is exactly how they got in.

Records that are the same decision carry the same `sourceGroupId`. Keep a group
whole on one side of any split. The validator reports duplicate decisions that
do not yet share a group as `ungrouped_duplicate_decision`, and grouped ones as
`duplicate_decision` — the second is not a defect, it is a constraint on how
you may split.

### Guide identity

**No release currently contains this kind.** The official guides were approved
on their content and withdrawn on their licence, and MZO is pursuing separate
permission. The contract keeps the kind defined so that granting permission
adds records rather than changing the schema. `coverage_by_document_kind` in
the manifest is what tells you which kinds a release actually holds; code
against it rather than against this section.

`issuingAuthority`, `issuingDivision`, `officialNumber`,
`officialNumberScheme`, `edition`, `issuedOn`, `pageCount`, `legallyBinding`,
`nonBindingStatement`.

A guide has no case number, court, or decision date. It has an issuing
authority and an official number — but the approved guides are numbered by
different authorities under different systems, so `officialNumberScheme` says
which system a number belongs to. Without it the number is a string that cannot
be resolved back to a register.

`issuedOn` keeps the precision its colophon states: `YYYY`, `YYYY-MM`, or
`YYYY-MM-DD`. A guide whose front matter gives only a month is delivered as
`YYYY-MM`. Padding it to a day would invent a source fact.

`legallyBinding` is fixed to `false`, and `nonBindingStatement` carries the
sentence in which the document says so itself. Guides are interpretation, not
law: index them as a distinct kind and distinguish them in citations. An answer
that presents guidance as binding is wrong even when the retrieval was right.

## Missing values arrive in three shapes

**This is the trap most likely to cost you a day.** Every key is present on
every record, so `if "holding" in record:` is always true and tells you
nothing. Absence is encoded three ways, and only the first announces itself:

| Shape | Where | Why it is dangerous |
| --- | --- | --- |
| `""` | The four judgement summary and cross-reference fields | Honest. A truthiness check finds it. |
| `"00010101"` in `decidedOn` | One provider's judgements | Eight digits, valid `YYYYMMDD`. `strptime` succeeds and yields 1 January of year 1. A "since 2020" filter drops those records **correctly**, leaving no error to debug. |
| `"null"` in `judgementType` | The same records | A four-character string, not a null. It is non-empty, so an emptiness check passes it, and it renders into a citation as the word `null`. |

The release preserves all three exactly as collected. Normalizing them is a
design decision with consequences — dropping the records, nulling the fields,
or carrying an explicit unknown are all defensible — and that decision is
yours. What MZO owes you is that the conventions are stated rather than
discovered.

`validate_release` reports sentinels as warnings, never errors. A warning
describes the corpus; it does not block the delivery.

## Law linkage is one-to-many, and membership is not relevance

`linkedLaws` pairs each target law with a `strength`:

- `core` — the law is an actual ground of the decision;
- `candidate` — plausibly relevant, not established as a ground;
- `unlinked` — the record surfaced through full-text search and mentions the
  law without deciding on it.

A record can link several laws. A filter that models the relationship as a
single value will silently mishandle every multi-law record.

More consequentially: **a record linked to a law is not therefore a decision
about that law.** A substantial share of the corpus carries no `core` link at
all — it matched a full-text search and nothing more. `record.core_laws` gives
the grounds; `linkedLaws` gives the matches. Treating the second as the first
inflates whatever you measure against it.

## Provider variation

Records come from more than one provider, and field fidelity varies sharply
between them. One provider supplies headnotes and holdings for most records;
another supplies neither for any of its records, along with the sentinel date
and disposition described above. A meaningful share of judgements arrive with
all four summary fields empty — full text and nothing else.

`provenance.provider` identifies which provider a record came from, so
fidelity, domain fit, and sentinel presence are all derivable from a single
field rather than by inference. `validate_release` reports body-only records
as `body_only_judgement`.

Your normalization has to work when the summary fields are absent, because for
part of the corpus they always are.

## Text shape

Judgement text is long and unevenly distributed. On the pre-freeze candidate
set the median was roughly 5,000 characters, the 99th percentile above 100,000,
and the longest record above 500,000 — a spread of three orders of magnitude.
The tail dominates whatever you derive from it: at one fixed chunk size the top
decile of records produced about half of all chunks. These figures describe the
candidate set, not the release; the manifest is authoritative.

Paragraph structure is carried by literal `<br/>` markup, present in nearly
every record. Newline characters are present in a minority. Anything that
splits on `\n` will see most judgements as one unbroken line.

Guide text, when a release carries it, is Markdown produced by a document
parser reading the PDF pages rather than a PDF text layer.
`provenance.extraction` names the tool, engine, model, and settings, because
that tool is versioned software: upgrade it and the text moves, which moves
`contentHash`. MZO runs it once and delivers the result, so no contributor
needs the parser and everyone holds the same bytes.

MZO does not publish a chunk size, a chunking strategy, or retrieval results.
Deciding those from the data is the assessment.

## The release manifest

`ReleaseManifest` records the dataset and schema versions, freeze timestamp,
delivery identity, every file with its SHA-256, byte size and record count,
coverage broken down by document kind, provider and usage, inclusion and
exclusion dispositions with reasons, licence and restricted-use notes, and
known gaps.

It is authoritative. Where a number in any document, note, or example
contradicts it, it wins.

## Checks

`validate_release(records, manifest)` returns findings without raising, so one
pass surfaces every problem:

- **Errors** block. Duplicate `documentId`, a `contentHash` that does not match
  the supplied text, a record count or coverage breakdown that disagrees with
  the manifest. Report these to MZO; do not repair the release locally.
- **Warnings** describe. Sentinels, duplicate decisions, body-only records, and
  records with no `core` linkage. These are the shapes you have to decide how
  to handle.

`select_index_inputs(records, evaluation_artifact_roots=...)` is the boundary
between supplied material and anything that reaches an embedding call or an
index. It **raises** rather than filtering, on any record that is
`evaluation_only`, `restricted`, or sourced from the evaluation artifact tree.

Filtering would be worse than useless here. A pipeline wired wrong would keep
producing plausible numbers, and the recall it reported would be measuring
leakage. Raising stops the run at the point where the mistake is still
attributable.

The schema also refuses `restricted` material that claims `index_eligible`
usage at model construction, so the combination cannot exist in a valid record.

Two further leakage controls are yours, because they operate on chunks rather
than source records: verify that every indexed chunk belongs to a record in the
frozen manifest, and detect exact or near-duplicate evaluation query and
expected-answer text among indexed chunks. Checking whether query IDs intersect
document IDs does not do this — they are different namespaces, and the check
passes while the leakage remains.

## Settled scope decisions

- Records whose subject matter sits away from this agent's questions stay in
  the release and are marked `inDefaultCorpus: false`. Including them is your
  call, as described above.
- No further law is being collected. The target law coverage is closed.
- The official guides are out of the release on licence grounds, not content
  grounds. The kind stays defined; the manifest's coverage says what arrived.

## Open items

- MZO is seeking separate permission for the official guides. If it is granted
  they enter a later release as `official_guide` records; the schema does not
  change, because the kind is already defined.
- Evaluation-only material enters the release only once MZO confirms that its
  restricted-use conditions are satisfied, as [DATASET.md](DATASET.md) states.
  The schema is ready for it either way: `restricted` admission with
  `evaluation_only` usage cannot be constructed as index-eligible, and
  `select_index_inputs` refuses it.

Neither changes this contract. Counts are delegated to the manifest precisely
so that settling them does not.

Ask gyro when something here blocks you. State what is blocked, which readings
are possible, how the outcome differs, and which assumption you will proceed
on. See [README.en.md](README.en.md).
