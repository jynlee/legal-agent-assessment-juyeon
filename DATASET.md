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

The final release reflects MZO's approved dataset review. It supplies citable,
domain-relevant law.go.kr cases and approved official guides. Duplicated law
PDFs and AI Hub 452 are excluded. AI Hub 71874 is not retrieval evidence and may
be used for evaluation only when MZO confirms that its restricted-use conditions
are satisfied.

Final counts are intentionally not duplicated in this template. The signed
release manifest wins over examples, planning notes, and prose.

## Allowed transformations

You may, with reproducible versioned code:

- select or exclude supplied records and explain the decision;
- normalize text while preserving provenance and citation identity;
- derive chunks and deterministic identities;
- generate embeddings from supplied index-eligible text;
- build local or managed indexes;
- create test queries and relevance judgements that are never indexed.

You may not enlarge the legal evidence coverage. If supplied evidence is
insufficient, represent that limitation in evaluation and runtime behavior.

## Required lineage

Every indexed chunk must be traceable to one supplied record and its source
identity. Derived artifacts record at least:

- dataset release version;
- normalization and chunking version;
- source record and document identifiers;
- chunk identifier and ordinal;
- content hash;
- document kind and citation fields needed by the answer contract.
