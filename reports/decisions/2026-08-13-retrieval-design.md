# Query Embedding, Hybrid Retrieval, and Fusion Design

Date: 2026-08-13
Status: Decided
Covers: ASSIGNMENT.md required work item 4 ("Implement query embedding,
retrieval, and any fusion or reranking you choose"), building on the
`legal-kit-assessment-<contributor>-chunk-v1-index-v1` index
(`reports/decisions/2026-08-13-opensearch-mapping-design.md`), which is
already populated with all 7,887 real chunks (182 judgements + 1,625
statutes) and their Cohere Embed v4 1536-dimension embeddings
(`docs/superpowers/plans/2026-08-13-opensearch-indexing-implementation.md`,
merged, final review clean).

It does not cover: the generation prompt's full answer-composition wording,
answer post-processing, or citation-excerpt selection beyond the minimal
insufficient-evidence instruction needed to close the loop with retrieval
(ASSIGNMENT.md item 7); the test set, relevance judgements, or retrieval
metrics themselves (items 5–6); or the `scripts/serve_legal_agent.py` entry
point's exact CLI shape (implementation detail, not a design decision).

## Summary of decisions

| Area | Decision |
| --- | --- |
| Query embedding | Reuse `embedding.py`'s `build_embed_request`, with `input_type="search_query"` — never `"search_document"`, the value already fixed for ingest |
| Hybrid combination | Client-side Reciprocal Rank Fusion (RRF) over two independent `_search` calls (BM25, exact k-NN) — not OpenSearch's server-side `_search/pipeline` normalization processor |
| RRF constant | `k = 60` (the standard value from the original RRF paper) |
| Candidate pool / final result count | BM25 top-50 and k-NN top-50, fused, then the fused top-10 passed to generation |
| Reranking | None — the RRF-fused order is the final order |
| `insufficient_evidence` determination | Two layers: a mechanical floor at the retrieval layer (zero fused hits → `insufficient_evidence`, no generation call), and a generation-layer judgement call delegated to the prompt for every non-empty result set |
| Component structure | Pure query-builders and fusion in `src/legal_agent_assessment/retrieval.py`; pure prompt/response handling in `src/legal_agent_assessment/generation.py`; the concrete `GeneralLegalAgent` implementation in `src/legal_agent_assessment/agent.py`, constructed with injected OpenSearch/Bedrock clients; real client construction stays in a new `scripts/` entry point |

## Decision 1: Hybrid combination is client-side RRF, not a server-side search pipeline

OpenSearch has a native way to combine BM25 and k-NN scores server-side: a
`_search/pipeline` resource with a normalization processor, referenced by a
compound query. This project does not use it.

**Why:** `OPENSEARCH_ACCESS.md` §1 grants contributors OpenSearch read/write
scoped to `legal-kit-*` **indexes** only, and explicitly lists cluster-level
paths outside that boundary as denied even when harmless (`_cat/indices`,
`_cluster/health`, `GET /` all return 403 for a signed request). A search
pipeline is a cluster-level resource (`PUT /_search/pipeline/<id>`), not an
index-scoped one — the same class of resource as the Nori plugin association
this project already investigated and rejected for the identical reason
(`reports/decisions/2026-08-13-opensearch-mapping-design.md` Decision 5).
Nothing in the documented IAM grant confirms a search pipeline would be
permitted on the managed domain, and confirming it would cost a managed-domain
round trip this design does not need to spend: two ordinary `_search` POSTs
against `legal-kit-*` (the same request shape already used everywhere else in
this project) plus a pure Python fusion step accomplish the same result
entirely within the documented grant.

This also sidesteps a real technical problem with combining the two signals
in one query without a normalization step: BM25 scores are unbounded and
corpus-size-dependent, k-NN/`script_score` similarity scores are bounded
differently, and summing them without normalization lets whichever signal has
larger raw magnitude dominate — the exact problem the normalization processor
exists to solve. RRF sidesteps this by construction: it only ever looks at
**rank**, never raw score, so the two signals never need to be placed on a
common scale.

## Decision 2: RRF, `k = 60`, BM25 top-50 + k-NN top-50 → fused top-10

Each query runs two independent `_search` calls against the same index:

- BM25: a `multi_match` query, primary weight on the `text` field (the actual
  chunk content — body or summary), secondary weight on `title`/`case_name`/
  `law_name` (matches a query that names a specific law or case). Exact field
  boosts are an implementation-time tuning knob, not a design decision fixed
  here — record whatever is chosen in the implementation plan and treat it as
  revisable once item 5/6's test set gives real signal, following the same
  "data first, numbers later" principle as Decision 3 below.
- k-NN: `script_score` with the `knn_score` script and `cosinesimil` space
  type, exactly as already committed in
  `reports/decisions/2026-08-13-opensearch-mapping-design.md` Decision 6 —
  this note does not re-decide that, only consumes it.

Each call requests `size: 50`. The two ranked `chunk_id` lists are combined
with the standard Reciprocal Rank Fusion formula:

```
score(chunk) = Σ 1 / (k + rank_in_list)   for each list the chunk appears in
```

with `k = 60`, the constant from the original RRF paper (Cormack, Clarke,
Buettcher, 2009) and the value most retrieval systems default to. Both the
formula and the constant are established, well-documented choices, not a
project-specific guess.

**Why 50 candidates per side, and why that's inexpensive:** the exact k-NN
approach this index uses (Decision 6 of the mapping design — no `method`
block, so no approximate-search engine) computes a similarity score against
**every** document in the index regardless of the requested `size`, then
sorts and truncates to the requested count at the end. Requesting the top-10
directly versus the top-50 costs essentially the same amount of computation —
the corpus being small (7,887 chunks) is what makes the full scan cheap, not
the choice of 50 over 10. The real reason for requesting 50 per side rather
than the 10 that generation will actually see is headroom for item 5/6's
retrieval metrics: Recall@k, MRR, or nDCG cannot be computed for a `k` larger
than the candidate pool that was actually retrieved, so a pool of 50 leaves
room to evaluate at cutoffs up to 50 without re-running retrieval.

The fused list is truncated to its top 10 before being handed to generation
— passing more than the answer actually needs to Claude risks diluting
citation quality (ASSIGNMENT.md item 7's grounding concern) for no offsetting
benefit once the fusion has already done its job of surfacing the most
relevant candidates first.

## Decision 3: No reranking

ASSIGNMENT.md explicitly leaves reranking optional ("Explicitly not
provided": "dense, BM25, hybrid, fusion, or reranking strategy"). This design
does not add one. A reranking pass (most plausibly LLM-as-reranker, since no
other reranking model is fixed by MZO) would mean an additional Bedrock call
per candidate — real cost and latency — to reorder a list that two
complementary signals (exact-term BM25, semantic k-NN) have already fused.
Given this corpus's small size and that the marginal benefit of a third
ranking pass over an already-fused two-signal result is unproven, adding one
now would be un-YAGNI'd complexity against no measured need. If item 5/6's
metrics later show RRF's ranking is measurably weak at the positions that
matter (e.g., low nDCG@5 despite reasonable Recall@50), reranking is a
reasonable follow-up to reconsider with that evidence in hand — not something
to build speculatively now.

## Decision 4: `insufficient_evidence` — a mechanical retrieval floor plus a generation-layer judgement, no retrieval score threshold

ASSIGNMENT.md's "Explicitly not provided" list includes "test queries,
relevance judgements, metrics, cutoffs, or pass bars" — nothing fixes how to
decide `insufficient_evidence` versus `answered`, and no committed test data
exists yet to derive a numeric retrieval-score cutoff from. Inventing one now
would repeat the mistake this project has already corrected once elsewhere
(guessing a Bedrock model ID from a display name, ASSIGNMENT.md's Fixed
constraints) — a plausible-looking number asserted without evidence.

**The design instead splits the decision across two layers:**

1. **Retrieval layer, mechanical, no threshold:** if RRF fusion returns zero
   hits, the response is `insufficient_evidence` immediately, and the
   Bedrock generation call is skipped entirely — saving latency and cost on
   a case retrieval has already fully resolved.
2. **Generation layer, delegated judgement:** for every non-empty result
   set, the fused top-10 chunks are still passed to Claude, but the prompt
   explicitly instructs it to answer `insufficient_evidence` rather than
   fabricate an answer when the supplied chunks do not actually support one
   — not a numeric score check, a judgement call made by the model that is
   about to compose the answer.

**Why this needs two layers, not just the retrieval floor:** `DATASET.md`
documents a specific, already-known failure mode this project's own corpus
gap creates. The official guides (보건복지부·식품의약품안전처) are excluded
from this release for licensing reasons (`DATASET.md`: "The official guides
are not in this release... withdrawn on their licence"), and the same
document names the consequence directly: "Guidance is where an abstract
requirement becomes a judgement about a specific advertising phrase, and the
decisions alone do not carry that. Where an answer needs it, the honest
response is `insufficient_evidence`, not a confident answer built from
statutes and case law that do not reach the question." A question shaped
like "does this specific advertising phrase violate the 표시광고법" will
retrieve real, on-topic statute and case chunks with plausible RRF
scores — retrieval is not empty, and a score cutoff would not catch this
case — but those chunks cannot actually resolve the specific judgement the
question asks for. Only reading the retrieved content against the question
can tell the difference, which is a generation-time judgement, not a
retrieval-score one.

**Why this is the generation layer's job, not retrieval's, per this
project's own documents:** `SUBMISSION.md` places "insufficient-evidence
refusal" under the **Generation evaluation report** heading (alongside
grounding, citation integrity, unsupported-citation/hallucination, and
out-of-scope refusal), not under the Retrieval evaluation report — a
structural signal that MZO already treats this as a generation-quality
concern, not a retrieval-metrics one. `contracts.py`'s
`GeneralLegalResponse.validate_grounding_state` validator enforces the same
shape in code: an `answered` response must carry citations, and only
generation — which sees the actual chunk text, not just a score — is
positioned to know whether the citations it is about to produce genuinely
support an answer.

**Deferred, not rejected:** once item 5/6 produces a real test set and
relevance judgements, the data may show that queries whose top RRF score
falls below some empirically-observed value are reliably refused by
generation anyway — at which point adding a retrieval-layer cutoff becomes a
measured cost optimization (skip the Bedrock call earlier) rather than a
guessed correctness threshold. That is future work, contingent on data this
project does not have yet.

## Decision 5: Component structure — pure query/fusion logic, an injectable `GeneralLegalAgent`, and I/O wiring in `scripts/`

Every module in `src/legal_agent_assessment/` so far is pure — no boto3, no
network, no filesystem (`embedding.py`, `opensearch_index.py`, `chunking.py`,
etc., each say so in their own docstrings) — while every module that talks to
OpenSearch or Bedrock lives in `scripts/`. The concrete class that implements
`GeneralLegalAgent.answer()` cannot itself be pure: answering a question
inherently means calling OpenSearch and Bedrock. Resolving this tension is
this decision's subject.

**The resolution:** `CONTRACT.md` already states the service is "backed by
**replaceable** OpenSearch and Bedrock adapters" — constructor-injected
clients, not clients the class builds for itself. Under that reading:

- `src/legal_agent_assessment/retrieval.py` (pure): `build_bm25_query`,
  `build_knn_query`, `reciprocal_rank_fusion`, and the mapping from an
  OpenSearch hit's `_source` (already carrying every lineage field
  `chunk_to_document` wrote) to both `Citation` and `RetrievalHit`
  (`contracts.py`) — both are populated from the same fused result, not just
  one, so the answer-facing citation and the internal diagnostic hit are
  never out of sync with each other.
- `src/legal_agent_assessment/generation.py` (pure): prompt construction
  (including the insufficient-evidence instruction from Decision 4) and
  Claude response parsing.
- `src/legal_agent_assessment/agent.py` (I/O, but only through injected
  clients): the concrete class implementing `GeneralLegalAgent`. Its
  constructor takes an already-built OpenSearch client and Bedrock client
  (the same `build_client`/`boto3.client("bedrock-runtime", ...)` shapes
  already used by `scripts/create_opensearch_index.py` and
  `scripts/bedrock_embedding.py`) plus the index name and
  `RuntimeVersions` metadata. `answer()` itself is orchestration: build
  queries → call the injected clients → fuse → build the prompt → call the
  injected Bedrock client → parse → assemble `GeneralLegalResponse`. Given a
  fake client in a test, this orchestration is exercised without any real
  network call, matching this repo's established testing convention.
- A new `scripts/` entry point (exact name and CLI shape left to the
  implementation plan) does the actual environment-dependent construction —
  reading `AWS_PROFILE`/`OPENSEARCH_URL`/model IDs from the environment,
  building the real SigV4-signed and Bedrock clients, and instantiating
  `LegalAgent` with them — mirroring exactly how
  `scripts/create_opensearch_index.py` already separates `build_client`
  (reusable) from its own environment-reading `main()`.

This keeps the pure/impure boundary this project has followed everywhere
else intact, satisfies `CONTRACT.md`'s explicit "replaceable adapters"
requirement literally rather than by accident, and gives the query-building
and fusion logic the same synthetic-data unit-test coverage every other pure
module in this repo already has.

## Explicitly out of scope for this note

- The generation prompt's full wording beyond the insufficient-evidence
  instruction, answer composition style, or how excerpts are trimmed into
  `Citation.excerpt` — ASSIGNMENT.md item 7.
- `out_of_scope` and `dependency_unavailable` response-state logic — related
  to item 7/8 but not decided here; this note's two-layer judgement only
  covers the `insufficient_evidence` boundary.
- Test set construction, relevance judgements, and retrieval metrics
  (Recall@k, MRR, nDCG) themselves — ASSIGNMENT.md items 5–6. This note
  fixes the pool sizes and RRF constant those metrics will later be computed
  against, but does not compute them.
- `scripts/`'s new entry point's exact CLI arguments, usage-log shape for
  query-time Bedrock calls (which needs the same `reports/usage/`
  self-instrumentation `scripts/index_chunks.py` already established), or
  BM25 field-boost tuning — implementation-time detail, not fixed here.
- The managed-domain permission question for `_search/pipeline` (Decision 1)
  was reasoned from documented IAM boundaries, not empirically tested against
  the real managed domain — this note treats client-side RRF as the design
  regardless of the answer, so the question is moot for this design, but it
  is not independently confirmed either way.

This is a design decision, not yet implementation — no retrieval or
generation code exists yet as of this note.
