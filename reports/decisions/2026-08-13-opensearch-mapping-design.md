# OpenSearch Index Mapping Design

Date: 2026-08-13
Status: Decided
Covers: ASSIGNMENT.md required work item 3 ("Create a versioned OpenSearch
3.5 index reproducibly"), building on the `Chunk` model produced by
`reports/decisions/2026-08-11-normalization-and-chunking-design.md`
(judgement) and `reports/decisions/2026-08-12-statute-chunking-design.md`
(statute). It does not cover query embedding, retrieval, fusion, or
reranking (ASSIGNMENT.md item 4) — only the index a retriever will read
from.

## Summary of decisions

| Area | Decision |
| --- | --- |
| Index topology | One index for both `body` and `summary` chunks, distinguished by `chunk_type` |
| Kind-specific fields | Flattened onto the mapping as nullable top-level fields per document kind, not a generalized `{key, value}` facet array |
| `linked_laws` | Three `keyword[]` fields split by strength: `linked_law_names_core`, `linked_law_names_candidate`, `linked_law_names_unlinked` |
| `decided_on` | `date`, `format: "yyyyMMdd"` — no transformation code needed |
| Text analyzer | `standard`, on both the local container and the managed domain — Nori was considered and rejected |
| Vector field | `knn_vector`, dimension 1536, no `method` block (exact k-NN via query-time `script_score`) |
| Naming | `legal-kit-assessment-<contributor>-<chunking>-<index>`, per `.env.example` |
| Shards / replicas | 1 shard; 0 replicas locally (single node), 1 replica on the managed domain (within the contributor's own namespace) |
| `refresh_interval` | Default (1s) — one-time batch load, not a streaming write pattern |

## Decision 1: One index, not two, for body and summary chunks

`chunk_type` (`body` | `summary`) is a filterable `keyword` field on every
chunk rather than an axis that splits the index. A single query can target
both chunk types at once, or filter to one with a `term` clause, and there
is one mapping schema and one `RuntimeVersions.index` value to reproduce,
not two that must stay in lockstep. Splitting by chunk type would only pay
off if the two needed materially different index-level settings (they do
not — same vector dimension, same analyzer, same shard count), so this
follows YAGNI: build the index that today's retrieval strategy needs, not
one that anticipates a divergence that has not been designed yet.

## Decision 2: Kind-specific fields are flattened, not a generalized facet array

An earlier brainstorming pass (2026-08-11 evening, recorded only in
conversation, not committed) proposed a generalized `{key, value}` array
field for court/law-name/etc. facets, reasoning that OpenSearch's `object`
type risks dynamic-subfield explosion as document kinds are added. That
concern doesn't apply here: `document_kind` is fixed at two values
(`judgement`, `statute`) by the frozen v2 release, and both kinds' fields
are already enumerated in code as `JudgementChunkFields` and
`StatuteChunkFields` (`chunking.py`). A generalized key/value layer would
add nested-query complexity (or `flattened`-type ambiguity) to solve a
scaling problem this project does not have. The mapping instead declares
every field from both kind-specific dataclasses as an explicit, nullable,
top-level field:

- Judgement: `case_name` (`text`+`.keyword`), `court` (`keyword`),
  `decided_on` (`date`, see Decision 4), `case_number` (`keyword`),
  `referenced_provisions` / `referenced_precedents` (`keyword[]`),
  `issue_ordinal` (`integer`)
- Statute: `law_name` (`text`+`.keyword`), `unit_kind` (`keyword`),
  `article_number` / `appendix_number` (`keyword`), `status`
  (`keyword`: `current`|`repealed`), `layout` (`keyword`: `text`|`table`)

A judgement document simply has every statute-only field absent, and vice
versa. Declaring all fields explicitly in the mapping (rather than relying
on dynamic mapping) means this sparsity is intentional and typed, not a
side effect of whichever document happened to be indexed first.

If a third document kind is ever added, extending this list is a one-line
mapping change — the same cost the generalized version would have paid to
add a new key, without carrying nested-query overhead for a case that may
never arrive.

## Decision 3: `linked_laws` becomes three `keyword[]` fields, not a nested type

`Chunk.linked_laws` is `tuple[LawLinkage, ...]` — a variable-length list of
`{law_name, strength}` pairs. `strength` is `dataset.py`'s
`LinkageStrength`, which has **three** values — `core`, `candidate`,
`unlinked` — not the two ("confirmed"/"candidate") this decision
originally stated; that was a citation error from writing this section
without rechecking the enum, caught and fixed 2026-08-13 while planning
the indexing implementation, before any code was written against it. This
is the one genuinely list-shaped field in the mapping (unlike Decision 2's
fields, which are scalar per chunk), so it does need an array-capable
design.

The only query this project currently needs against it is "does this chunk
cite law X" (exact `law_name` match, optionally restricted by strength) —
not a combined `{law_name: X, strength: Y}` structural match that would
require `nested` to avoid cross-pair false matches. Since the three
`strength` values are fixed and known, the strength dimension is folded
into the field name instead of kept as sub-document structure:

```json
{
  "linked_law_names_core": ["약사법", "의료법"],
  "linked_law_names_candidate": ["개인정보보호법"],
  "linked_law_names_unlinked": []
}
```

All three are plain `keyword[]` — a `terms` filter answers the only query
this project needs, with no `nested` query overhead and no risk of the
`object` dynamic-subfield explosion Decision 2 also avoided. Keeping
`unlinked` as its own field (rather than dropping it) matches
`reports/decisions/2026-08-10-record-selection-and-document-kind-policy.md`'s
policy of preserving `linkedLaws` strength as metadata rather than
filtering it away at index time.

## Decision 4: `decided_on` is a `date` field; no sentinel-handling code needed at index time

`JudgementChunkFields.decided_on` is `str | None`. The sentinel placeholder
(`decidedOn == "00010101"`, `dataset.py`'s `SENTINEL_DATE`) is already
resolved to `None` before a `Chunk` exists — `chunking.py` lines 606 and
666 both set `decided_on=None if identity.has_sentinel_date else
identity.decided_on`. By the time a document reaches the index, the field
is either a clean 8-digit string or absent.

This means the mapping can use OpenSearch's native `date` type instead of
falling back to `keyword` to dodge sentinel parsing (the concern that
originally motivated considering `keyword`). Setting `format: "yyyyMMdd"`
lets the compact 8-digit string index directly, with no ISO-8601
transformation step in the indexing code, and `range`/`exists` queries work
correctly against the 3 sentinel-carrying chunks (`precedent-393844`,
`precedent-408430`, `precedent-408454`, per
`reports/decisions/2026-08-12-record-selection-v2-judgement-sentinels.md`)
because the field is simply absent on them, not present with an invented
year-1 date.

## Decision 5: `standard` analyzer, both locally and on the managed domain — Nori considered and rejected

**History:** Nori (한국어 형태소 분석기) was the open question carried over
from the 2026-08-11 evening brainstorming session and initially resolved
(2026-08-13) as "use Nori everywhere, local and managed." Working out the
mechanics of that decision surfaced a permission boundary that changes the
answer.

**The constraint:** `OPENSEARCH_ACCESS.md`'s IAM policy table grants
contributors `legal-kit-*` index read/write and nothing else — plugin or
package management (which associating the Nori package on an AWS managed
OpenSearch domain requires) is not a contributor permission. Nothing in
this project's documentation makes that association available to a
contributor working within the documented boundary.

**Why not "Nori locally, standard on the managed domain":** this was
considered — a contributor-built local Docker image could install the Nori
plugin without needing anything from MZO — but it would mean the local and
managed mappings diverge on the one setting (the analyzer) that most
directly shapes what a query matches. `OPENSEARCH_ACCESS.md` §6 frames the
local container as where an index is normally built and rebuilt, with
managed used only "when you need to prove the pipeline works against it" —
a workflow that assumes the two stay equivalent. A local-only enhancement
that the managed index can never carry would make local search behavior
someplace the managed proof cannot reach, and would need to be maintained
as a permanent special case rather than a temporary gap. `standard` analyzer
everywhere removes the divergence, needs nothing outside documented
contributor permissions, and needs no custom Docker image for the local
container either — `docker-compose.yml` stays unmodified.

**Why this is an acceptable retrieval design, not just a fallback:** the
hybrid retrieval strategy (`reports/decisions/2026-08-11-normalization-and-chunking-design.md`'s
search-strategy note) already assigns exact-term matching
(`referencedProvisions`/`referencedPrecedents`, statute article numbers) to
`keyword` fields, not to Korean-tokenized full-text `match` queries, and
assigns semantic matching to the dense vector. `standard` analyzer BM25 on
`text`/`title` still does useful work — matching Korean legal terms that
appear as space-delimited tokens or Sino-Korean legal vocabulary shared
with the query — it is a weaker morphological match than Nori would give,
not a broken one, and the fields most sensitive to exact-token recall are
already `keyword`, not analyzed text.

## Decision 6: Vector field uses exact k-NN, no engine/method selection

```json
"embedding": {
  "type": "knn_vector",
  "dimension": 1536
}
```

No `method` block (which would select an approximate-search engine —
`faiss`, `lucene`, or `nmslib` — and HNSW parameters `ef_construction`/`m`).
At the corpus's actual scale (7,887 chunks), approximate nearest-neighbor
search buys nothing: brute-force exact k-NN over embeddings this size is
fast enough to not need an ANN graph, and skipping it removes an engine
choice this project does not need to make while giving Recall@k/MRR/nDCG
results that are exact rather than subject to ANN approximation noise —
a cleaner number for a project whose deliverable is the metric itself.

Exact k-NN is invoked at query time via OpenSearch's `script_score` query
with the `knn_score` script (not the `knn` query clause, which requires an
approximate `method`), passing `space_type: "cosinesimil"` as a script
parameter rather than a mapping-time setting — cosine similarity is
correct regardless of whether Cohere Embed v4 vectors are pre-normalized to
unit length, which this design does not assume either way.

`input_type` (`search_document` for ingest, `search_query` for queries,
per ASSIGNMENT.md's Fixed constraints) is an embedding-call-time parameter,
not a mapping concern — noted here only to record that this design does
not need to encode it, not because the constraint is unimportant.

If corpus growth in a future release ever makes exact k-NN too slow, adding
a `method` block is an additive mapping change (a new index version), not a
breaking one — this design intentionally leaves that door open rather than
closing it by picking an engine now.

## Decision 7: Naming, shards, replicas, refresh interval

- **Index name**: `legal-kit-assessment-<contributor>-<chunking>-<index>`,
  exactly the convention `.env.example` documents. `<chunking>` and
  `<index>` track `RuntimeVersions.chunking`/`.index`, so a mapping or
  chunking-rule change ships as a new index name, and old indexes are left
  in place rather than mutated in ways that would break reproducibility of
  a prior run's numbers.
- **Shards**: 1. The corpus is small enough (7,887 chunks) that splitting
  across shards would only fragment the exact k-NN scan (Decision 6) for
  no benefit.
- **Replicas**: 0 on the local single-node container (a replica would sit
  permanently unassigned and hold cluster health at yellow for no reason);
  1 on the managed domain. This is a setting the contributor sets on their
  own index inside their own `legal-kit-assessment-<contributor>-...`
  namespace, not something that requires any permission beyond the
  documented `legal-kit-*` read/write grant.
- **`refresh_interval`**: left at the OpenSearch default (1s). The corpus
  is bulk-loaded once per index build, not written continuously, so there
  is no indexing-throughput case to trade off against search freshness.

## Explicitly out of scope for this note

- Query embedding, retrieval, fusion/reranking (ASSIGNMENT.md item 4) —
  including exactly how BM25 and the exact-k-NN `script_score` query are
  combined into one hybrid query.
- Bulk-indexing code, the `Chunk` → index-document builder function, and
  any script that actually creates the index against the local container
  or the managed domain.
- Test set / relevance judgements / retrieval metrics (ASSIGNMENT.md items
  5–6).

This is a design decision, not yet implementation — no index has been
created and no mapping JSON has been applied against either the local
container or the managed domain as of this note.
