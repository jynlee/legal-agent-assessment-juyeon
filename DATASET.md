# Dataset Contract

## Release delivery

The dataset is delivered outside Git through an approved channel. The release
manifest is authoritative for included files, record counts, source identity,
provenance, acquisition dates, citation coordinates, licence notes, known gaps,
and SHA-256 checksums.

Before implementation:

1. Record the release version and delivery identifier.
2. Verify every supplied checksum.
3. Confirm that no unexpected or unlisted artifact is present.
4. Preserve raw supplied bytes; write derived artifacts to ignored directories.
5. Report a mismatch immediately instead of repairing the release locally.

The final release reflects MZO's approved dataset review. Dataset v2 supplies
citable current statutes and selected aesthetic-domain cases from law.go.kr.
Duplicated law PDFs and AI Hub 452 are excluded. AI Hub 71874 is not retrieval
evidence and may be used for evaluation only when MZO confirms that its
restricted-use conditions are satisfied.

Records whose subject matter sits away from this agent's questions are supplied
but marked outside the default corpus. Including them is a record-selection
decision you may make and explain.

**The official guides are not in this release.** They were approved on their
content and then withdrawn on their licence: one is published under terms that
forbid commercial use and derivative works, and the other's terms could not be
confirmed. Indexing either would mean normalizing and chunking a work whose
licence does not allow it. The schema still defines `official_guide` because
MZO is pursuing separate permission, so read
`coverage_by_document_kind` in the manifest rather than assuming which kinds
arrived.

This costs the release something real. Guidance is where an abstract
requirement becomes a judgement about a specific advertising phrase, and the
decisions alone do not carry that. Where an answer needs it, the honest
response is `insufficient_evidence`, not a confident answer built from
statutes and case law that do not reach the question.

Final counts are intentionally not duplicated in this template. The signed
release manifest wins over examples, planning notes, and prose.

[DATASET_SCHEMA.md](DATASET_SCHEMA.md) describes the shape of one supplied
record — identity, provenance, citation coordinates, usage disposition, the
three ways absence is encoded — and the deterministic checks over a delivery.
Read it before designing normalization or chunking; it carries no counts, so it
does not compete with the manifest.

## Allowed transformations

You may, with reproducible versioned code:

- select or exclude supplied records and explain the decision;
- normalize text while preserving provenance and citation identity;
- derive chunks and deterministic identities;
- generate embeddings from supplied index-eligible text;
- build local or managed indexes;
- create test queries and relevance judgements that are never indexed.

Do not enlarge the legal evidence coverage on your own. The frozen release is
the measurement basis, and a submission measured against a corpus only you hold
cannot be rerun or compared.

Investigating the raw sources is a different matter and is allowed. Decisions
carry a source URL, guides carry an official publication number, and
[README.en.md](README.en.md) names where the corpus came from. If you conclude
the coverage is wrong, explain it to gyro instead of collecting around it: the
release can change. A separate report is not expected.
Until the release changes, represent the limitation in evaluation and runtime
behavior.

## Attribution

Every record carries the publisher statement its source requires, and the
manifest is authoritative for licence terms and attribution conditions. An
answer that quotes supplied text must make its origin visible; naming a case
number is identification, not attribution.

## Required lineage

Every indexed chunk must be traceable to one supplied record and its source
identity. Derived artifacts record at least:

- dataset release version;
- normalization and chunking version;
- source record and document identifiers;
- chunk identifier and ordinal;
- content hash;
- document kind and citation fields needed by the answer contract.
