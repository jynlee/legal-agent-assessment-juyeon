# Architecture Report

Date: 2026-08-14
Covers: SUBMISSION.md's "Architecture report" requirements, against the
completed implementation of ASSIGNMENT.md items 1-8. This document
synthesizes the project's `reports/decisions/` notes (each cited by name)
into the single narrative SUBMISSION.md asks for; it does not re-argue
decisions already made there, only reports them.

## 1. Record-selection and document-kind decisions

Two document kinds are indexed: `judgement` and `statute`. A third
(`official_guide`) is defined in the dataset schema but present in no
release to date — the official guides were withdrawn on licence grounds
before this project's frozen dataset was cut (see §7), so the schema stays
ready for a future grant without needing a schema change.

**Baseline provenance.** The repository was built from tag `assessment-v3`
(commit `37bab4ec92c89e796d1b06d1e6955449ca92b46c`, dataset schema
`source-record-v1`), then carried forward to `assessment-v4` (commit
`b73880e9baaf4353489725e6eeb4f0ea7d70a7b8`, schema `source-record-v2`)
after MZO expanded the assignment's scope to include statutes partway
through the engagement. `assessment-v4` was verified to be an ancestor of
this submission's `master`, with no files removed or modified relative to
the v4 tree (`reports/decisions/2026-08-12-baseline-provenance.md`).

**Judgement record selection.** The dataset went through two release
generations, and the selection policy for each is recorded separately
because the second superseded, rather than repeated, the first:

- *v1* (1,104 records, schema v1): 109 records with `inDefaultCorpus=false`
  were excluded — tax and industrial-accident cases that matched this
  project's legal domains only through incidental keyword overlap in
  `linkedLaws`, not genuine subject-matter relevance. This left 995 records
  (90.1%), all Supreme Court decisions. Two further categories were
  deliberately *included*, not excluded: records whose summary fields
  (`headnote`/`holding`) were empty (319/995 — citations are drawn from the
  full judgement `text`, not the summary, so an empty summary is not a
  reason to drop a record) and records with no core statute linkage
  (366/995 — `linkedLaws` strength is retained as chunk metadata rather
  than used as a filter, since removing weakly-linked records would remove
  retrievable signal without removing any real leakage risk; BM25/vector
  scoring already demotes irrelevant chunks at query time).
- *v2* (`dataset-2026-08-11-v2.1`, schema v2, the release this submission
  is built on): 182 judgement records, every one already
  `inDefaultCorpus=true`. MZO moved domain-relevance filtering upstream of
  the release itself, so v1's Decision 1 (the 109-record exclusion) is
  **superseded, not re-applied** to v2 — there is nothing left to exclude
  on that basis. v1's other policy (include body-only and no-core-linkage
  records, carrying metadata rather than filtering) is release-independent
  and still governs v2 unchanged.
- Three v2 judgement records (`precedent-393844`, `precedent-408430`,
  `precedent-408454`) carry sentinel placeholder values for `decidedOn`
  and `judgementType` while their case number, court, and full text remain
  intact and on-topic (first-instance administrative litigation over
  medical-institution regulatory penalties). These were included, with the
  sentinel fields carried as an explicit unknown, per the dataset schema's
  documented option for exactly this case — rather than excluded outright
  or silently coerced to a fabricated value.

**Statute record selection.** All 1,625 statute records in the v2 release
are `inDefaultCorpus=true`; no selection filter is applied.

**Net indexed corpus:** 182 judgements + 1,625 statutes = 1,807 source
records, producing 7,887 indexed chunks (7,463 body + 424 summary).

**Structural leakage boundary.** Record selection is enforced by two
deterministic functions: a baseline filter, and a second function that
*raises* (rather than silently filtering) on any record found under an
`evaluation_only`, `restricted`, or evaluation-artifact-tree marker. The
dataset schema itself refuses to construct a `restricted` record flagged
`index_eligible` at all — the invalid state is unrepresentable, not just
disallowed by convention. This project's own risk register treats a
pipeline that quietly filtered such records as strictly worse than one
that fails loudly: a silent filter would keep producing plausible-looking
recall numbers while actually measuring leakage.

**Known limitation carried forward, not resolved here.** 14 groups (26
records) in the v2 release are the same underlying judgement registered
under different case-serial identifiers (`sourceGroupId` collisions). This
is a train/test-split-safety concern handled in the retrieval test-set
design (§ Retrieval evaluation report), not in record selection itself.

## 2. Normalization, chunking, and deterministic identity rules

**Judgement chunking** produces two chunk kinds: `body` (from the full
judgement text) and `summary` (one chunk per numbered issue in the
headnote/holding). Body chunks use a structure-aware split (section header,
then sub-section, then paragraph break) packed into 800-1,500 character
units with no overlap — chunk boundaries follow the document's own
structure rather than a fixed sliding window, which also has the side
benefit of simplifying leakage detection later, since no two chunks share
text by construction. An oversized structural unit falls back recursively
to the next-finer boundary.

Two properties of the source text were verified empirically rather than
assumed, because the assumed version was wrong: matching section headers
like 【이유】 with an exact string match only found the header in 24 of 995
records (2.4%), while a whitespace-tolerant version of the same regex found
it in 995 of 995. Separately, unnumbered headnote/holding text (implicitly
"issue 1") turned out to be the *majority* shape — 53.8% of the 676 records
with non-empty headnotes — not the edge case an unverified design would
have treated it as. **Population note:** both of these measurements were
taken against the 995-record judgement population selected under the v1
dataset release, before MZO's later scope expansion narrowed the actual
indexed judgement set to the 182 records of the v2 release this submission
is built on (§1); neither has been independently re-run against those 182
records specifically. The regex/majority-shape properties being measured
are properties of this corpus's underlying text-formatting conventions
rather than of which records were selected, so they are expected to still
hold, but that expectation is not itself a re-measurement — flagged here
rather than assumed silently.

`referencedProvisions` and `referencedPrecedents` are excluded from the
text that gets embedded (they read as semantically flat noise to an
embedding model) but are retained verbatim as chunk metadata, reserved for
a future exact-match keyword field.

**Real bugs caught only by testing against the actual release data**, not
by synthetic fixtures, during this plan's final whole-branch review: a
paragraph-packing pass that ignored digit-level sub-section boundaries
(affecting 37.9% of body chunks before the fix); a digit-marker regex that
false-matched Korean dates like "2011. 6.경" as section markers (5.0% of
chunks); an issue-extraction routine that silently dropped citations under
repeated or adjacent issue-number markers; and a locator-deduplication
suffix that fired far more often than its "rare collision" design assumed
(30.8% of chunks). Unlike the two measurements above, these percentages
were measured directly against the actual v2, 182-record judgement corpus
(the addendum recording them cites chunk and record counts against 182
records explicitly), so they describe the data this submission actually
indexes. All four were found and fixed before this data reached the index
— the general pattern behind all four is the same lesson this project
applied repeatedly: synthetic test fixtures did not surface any of them,
and only re-running the final review against the real frozen release did.

**Statute chunking** uses a single chunk kind, since statutes have no
headnote/holding equivalent. 91.8% of statute records (1,492/1,625) stay
under the 1,500-character threshold and become exactly one chunk. For
longer statutes, table regions are protected from the marker-splitting
pass *before* that pass runs — a box-drawing table row that happens to
start with a valid marker character would otherwise be silently torn apart
into undersized, malformed pieces with no fallback ever triggering. 116
repealed articles — 7.5% of the 1,551 article-type records, 7.1% of the
full 1,625-record statute corpus — are included and tagged, not excluded
— a repeal notice like "제19조 삭제 <2011.3.30>" is a
real, correctly groundable answer to a question about whether an article
is still in force, and excluding it would force an incorrect
`insufficient_evidence` refusal on an answerable question. That tag is
currently emitted but not yet consumed downstream (see §7, limitation 5).

**Shared identity and versioning.** Every chunking rule change is tracked
through versioned constants threaded into every response's
`RuntimeVersions` field, so a stored answer names the exact normalization,
chunking, and index rules that produced it — this is the project's
mechanism for the "deterministic identity" SUBMISSION.md asks about. One
concrete, deliberately-guarded risk: the normalization-version constant
used for judgement text cleaning and the one used for chunking are
tracked separately and can legitimately differ; the code that assembles
`RuntimeVersions` calls this out explicitly to prevent the two from being
confused with each other.

## 3. Index mapping, retrieval, fusion, filtering, and reranking

**Index mapping.** Body and summary chunks share a single OpenSearch
index, distinguished by a `chunk_type` keyword field rather than split
into two indexes — there is no divergent index-level setting between them
that would justify the split. Document-kind-specific fields (judgement vs.
statute) are flattened as nullable top-level fields rather than a
generalized key/value facet array, since this project has exactly two
document kinds and a generalized structure would be solving a scaling
problem it doesn't have. `linked_laws` strength is represented as three
separate keyword-array fields (core/candidate/unlinked) rather than a
nested type, since the only query this needs to answer is "does this
chunk cite law X at strength Y," which a plain `terms` filter already
handles.

The vector field uses exact (brute-force) k-NN with no `method` block —
at this corpus's scale (7,887 chunks), approximate nearest-neighbor search
buys no meaningful speed and would introduce approximation noise into
exactly the Recall@k/MRR numbers this project's evaluation reports on;
exact k-NN keeps those numbers clean.

**Text analyzer.** Both the local and managed OpenSearch indexes use the
`standard` analyzer. A Korean-specific morphological analyzer (Nori) was
considered and rejected — twice, for two different reasons at two
different points in the project:

- Initially, whether an index mapping is even allowed to *reference*
  Nori (which ships bundled by default on AWS managed OpenSearch, but
  whose *use* from a mapping was never tested against this project's
  documented, index-scoped IAM permission grant) was an open question,
  and the project chose not to spend a managed-domain round trip
  resolving it for a benefit judged partial anyway — the fields most
  sensitive to exact-token matching (statute article numbers,
  `referencedProvisions`, `referencedPrecedents`) are already `keyword`
  fields, not analyzed text, so Nori's incremental gain would be limited
  to full-text `text`/`title` matching quality.
- On 2026-08-14, MZO explicitly authorized contributors to add any
  OpenSearch plugin judged necessary, resolving that permission question
  directly. The decision to stay on `standard` was **kept anyway** — the
  benefit analysis above did not depend on the permission question and
  remains unchanged, and switching at this point in the project would
  require rebuilding the index and re-running the full retrieval
  evaluation (50 real Bedrock calls) against an already-verified,
  already-corrected Recall@10/MRR baseline, with the submission deadline
  close and all four required reports still to be written. This is
  reported here as a deliberate, time-budget-aware decision made with
  full information, not as an unresolved gap.

**Retrieval and fusion.** Query embedding reuses the same request-building
function ingest uses, with `input_type="search_query"` — never
`"search_document"`, the ingest-side value ASSIGNMENT.md fixes separately
for the two directions. The two signals are combined with client-side
Reciprocal Rank Fusion over two independent `_search` calls (BM25 and
exact k-NN), rather than OpenSearch's server-side `_search/pipeline`
normalization processor — a search pipeline is a cluster-level resource
outside this project's documented index-scoped IAM grant, the same
permission-boundary reasoning that applied to the analyzer question above.
RRF also sidesteps a real scoring problem: BM25 scores are unbounded and
corpus-size-dependent while k-NN similarity scores are bounded
differently, and RRF avoids needing to reconcile the two by only ever
looking at rank, never raw score.

The fusion constant is `k=60`, the standard value from the original RRF
paper (Cormack, Clarke, Buettcher, 2009), not a tuned or guessed value.
Each side of the fusion requests its top 50 results (free for exact k-NN,
since its cost is independent of the requested size) — the real reason for
50 rather than a smaller number is to leave headroom for retrieval metrics
computed at cutoffs up to 50 without needing to re-run retrieval. The
fused list is truncated to its top 10 before being handed to generation,
since passing more than that risks diluting citation quality for no
offsetting benefit once fusion has already done its ranking work.

**Filtering.** No query-time filtering is applied beyond the two `_search`
calls described above — every query searches the full index regardless of
document kind or chunk type. This is a deliberate scope decision (YAGNI,
consistent with the project's stated preference to add complexity only
against a measured need) rather than a decision-doc-recorded design
choice; it is reported here plainly as "no filtering applied," not framed
as a considered-and-rejected alternative, since no design note frames it
that way either.

**Reranking.** None in the submitted pipeline — but this was a real,
measured decision arrived at during the project, not the starting
position kept unexamined throughout. ASSIGNMENT.md explicitly leaves
reranking optional. A semantic reranking stage (a separate Claude Sonnet
call selecting genuinely relevant candidates from a widened top-25 pool,
the `judge.py` pattern applied before generation instead of after) was
implemented and measured on 2026-08-18: it raised Recall@10 from 57.14%
to 59.52%, at a real, permanent per-query cost (rerank call ~$0.076,
median retrieval latency 525ms→4.5s) — but it also measurably worsened
`insufficient_evidence_refusal_accuracy` (0.5556→0.3333 on that day's
denominator), an unintended side effect: a wider, more semantically
generous candidate pool gave the generation step more
plausible-but-not-dispositive material to reason from. After six further
independent attempts at fixing that weakness directly all failed
(Generation evaluation report, "insufficient_evidence refusal accuracy"),
reranking was reverted on 2026-08-19 as the one lever with
already-measured, zero-additional-cost evidence for its effect —
`insufficient_evidence_refusal_accuracy` recovered to 50.0%, the best
value measured across this project, at the cost of giving back the
Recall@10 gain. Full reasoning for the trade-off direction:
`reports/decisions/2026-08-19-revert-reranking.md`. The code
(`src/legal_agent_assessment/rerank.py`) was deleted with the revert, not
kept dormant — this section describes real, since-removed work, not a
design that was never built.

**`insufficient_evidence` determination** sits across two layers: a
mechanical retrieval-layer floor (zero fused results triggers an immediate
refusal with no generation call spent), and a generation-layer judgement
delegated to the prompt for every non-empty result set. This split exists
because a retrieval-score threshold cannot distinguish "no relevant
sources" from "relevant-looking sources that don't actually answer this
specific question" — the latter is a real, documented gap in this
project's own dataset (the withdrawn official guides mean some questions
retrieve real, on-topic statute and case text with plausible fusion scores
that still cannot resolve the specific judgement asked for), and only a
step that reads the retrieved text against the question can tell the
difference. This is also why SUBMISSION.md itself places
"insufficient-evidence refusal" under the Generation evaluation report
rather than the Retrieval evaluation report — a structural signal that
this determination is a generation-quality property, not a retrieval-score
one.

## 4. Embedding and LLM adapter boundaries

**Embedding.** The embedding module is pure — no network calls, no boto3
import — and builds Bedrock Cohere Embed v4 request bodies with an
explicitly requested 1536-dimension output on every call. This is not
cosmetic: the endpoint's unrequested default output is 1024-dimensional, a
mismatch confirmed empirically against the real endpoint and caught by a
smoke test before the production indexing run (see §7, limitation 3).
Response parsing accepts either observed Cohere response shape and asserts
the expected count and dimension explicitly, so any future drift in the
endpoint's response shape fails with a clear, named error rather than a
silent `KeyError` or a silently wrong vector dimension reaching the index.
A conservative token-count approximation (character count, since no
offline tokenizer for this model is available) paces requests against the
account's shared embedding quota — pacing, not retrying, since a
per-minute quota exhausted this minute cannot be retried away within that
minute.

**LLM adapter.** The generation module is likewise pure, responsible only
for prompt construction and response parsing; its prompt version is a
versioned constant threaded into every response's `RuntimeVersions.prompt`
field, so a stored answer names the exact prompt text that produced it.

**The adapter boundary itself.** `LegalAgent`, the concrete implementation
of the `GeneralLegalAgent` contract, takes its OpenSearch and Bedrock
clients as constructor parameters and never constructs them itself. This
is the literal mechanism behind CONTRACT.md's requirement that the service
be "backed by replaceable OpenSearch and Bedrock adapters": swapping
either client for a different implementation that satisfies the same call
shape requires zero changes to `LegalAgent`'s orchestration logic. In
practice this also means the orchestration logic is fully exercised in
tests against fake clients with the same call shape, with no real network
call ever made in the test suite. Real client construction — reading AWS
profile, region, model IDs, and the OpenSearch URL from the environment,
and building SigV4-signed / boto3 clients from them — happens in exactly
one place, the `scripts/` entry point that serves real requests; no other
module reads environment variables or imports `boto3`/`opensearch-py`.

**Fixed model constraints.** The embedding model, its dimension, and the
generation model ID are fixed by ASSIGNMENT.md and recorded in this
project's environment template with an explicit warning against guessing
an Opus or Haiku model ID from a display name — only the one generation
model ID MZO has verified and published may be used.

## 5. Grounding, citations, refusal, and failure behavior

The response contract defines four outcomes: `answered`,
`insufficient_evidence`, `out_of_scope`, and `dependency_unavailable`. A
model-level validator enforces the grounding invariant structurally rather
than by convention: an `answered` response is required to carry non-empty
answer text and at least one citation, and every other status is required
to carry neither — violating either direction raises an error at
construction time, so an ungrounded "answer" or a "refusal" that quietly
carries answer text cannot exist as a valid response object in the first
place. A separate diagnostic field, distinct from citations, carries the
underlying fused retrieval ranks and scores on any status for internal
inspection; it is never shown to a consumer as evidence.

**The `answered` path.** Citations claimed by the generation model are
matched only against chunks this agent itself actually retrieved in that
call's fused results — matched on the indexed chunk identifier, never on
the search engine's own internal document id, specifically because those
two identifiers are equal today only by an indexing-time choice that could
change; depending on that equality would make a future re-index silently
degrade every answer to a refusal with healthy-looking diagnostics and no
visible error. If the model claims `answered` but cites nothing this agent
actually retrieved, the response falls back to `insufficient_evidence`
rather than fabricating a citation. If some cited ids are real and others
are not, the answer stands on its real citations, and the invented ones
are surfaced through a `limitations` field rather than silently dropped.

**Refusal paths.** `insufficient_evidence` is reached by any of three
routes converging on the same status: the mechanical zero-hit floor, the
generation-layer judgement described in §3, or the answered-but-nothing-
real-cited fallback above. `out_of_scope`, added to close ASSIGNMENT.md's
remaining item, is folded into the same generation call rather than a
separate classification step — consistent with the reasoning already
applied to `insufficient_evidence`, since only a call that has seen the
actual retrieved text is positioned to judge whether a question belongs to
this assistant's domain at all. Retrieval still runs in full even for
obviously off-topic questions, since exact k-NN always returns its
requested number of results regardless of actual relevance and cannot be
skipped without a separate pre-filtering step, which was judged unneeded
complexity for this project's scale. `dependency_unavailable` wraps the
entire answering routine in a single exception handler catching exactly
five specific connection- and timeout-level exception types from the
OpenSearch and Bedrock client libraries — deliberately narrow, so that a
real bug (a wrong index name, a malformed request, an authentication
failure) continues to raise visibly rather than being silently reported to
a caller as a generic infrastructure outage.

**Named risk, since empirically verified and resolved.** The `out_of_scope`
prompt instruction does not give the model an explicit list of the ten
legal domains this assistant covers, so there was a real, once-unverified
risk that a question genuinely within scope but unresolvable by this
corpus — the exact case the retrieval evaluation's test set includes
questions to exercise, expecting `insufficient_evidence` — could instead
be misclassified as `out_of_scope`. This was flagged here as a named,
deliberately deferred risk rather than fixed speculatively, with a plan to
verify it empirically before relying on any `out_of_scope` numbers in the
Generation evaluation report. That verification has since happened: the
Generation evaluation report's real, full-pipeline run measured
`insufficient_evidence_misclassified_as_out_of_scope: 0`, confirmed
identically across three independent real runs (the original 5-question
`insufficient_evidence` set, and the 2026-08-18 run against the corrected,
9-question set). The risk did not materialize; no prompt change was made
in response, since there was nothing to fix. (What the same runs did find,
in the opposite direction — real over-answers instead of refusals on some
of those questions, and 2 of the original 5 having been mislabelled
outright, found and corrected on 2026-08-18 — is a different, real finding
disclosed in the Generation evaluation report's "insufficient_evidence
refusal accuracy" section, not a domain-coverage problem.)

## 6. Portability boundaries and known Peitho adaptation work

CONTRACT.md requires `GeneralLegalAgent.answer()` to be a single-turn,
stateless, database-free, async, JSON-serializable service boundary,
independent of Peitho, FastAPI, an ORM, dependency injection, or `ITool`,
backed by replaceable OpenSearch and Bedrock adapters. This codebase
satisfies that boundary concretely, not just by absence of imports:

- The contract module (request/response/citation/version types) imports
  nothing beyond Pydantic and the standard library — no framework object
  of any kind appears in its public signatures, so any Python host capable
  of calling an `async def answer(request) -> response` function can use
  this service as-is.
- `LegalAgent`'s constructor takes its OpenSearch and Bedrock clients as
  parameters rather than building them — the literal mechanism of
  "replaceable adapters" described above.
- Every module that touches the network, the filesystem, or environment
  variables lives outside the core package, in the project's `scripts/`
  entry points — with the single, structurally necessary exception of the
  agent implementation itself, which still only calls clients handed to
  it, never constructs them.
- No Peitho import, database session, authentication or tenancy layer,
  dependency-injection framework, or `ITool` implementation exists
  anywhere in the core package — a standing prohibition this project
  checked against repeatedly over its course, not merely at submission
  time.

**Known Peitho adaptation work.** A future integration into the Peitho
runtime would need to: wrap this agent implementation (or an equivalent
`GeneralLegalAgent` implementation) behind whatever service-registration
mechanism Peitho expects; construct the real OpenSearch and Bedrock
clients using Peitho's own credential and configuration resolution instead
of this project's environment-variable reads; and route the version and
usage information this project currently writes to flat JSON log files
into Peitho's own logging and observability surface instead. No
source-level change to the contract module, the agent's orchestration
logic, the retrieval module, the generation module, or the embedding
module should be required for that integration — the adapter boundary
described above is exactly where that work would land, by design.

## 7. Dependencies, licences, security assumptions, and operational limitations

**Dependencies.** Runtime dependencies are `boto3`, `opensearch-py`, and
`pydantic`; development dependencies are `mypy`, `pytest`, and `ruff`. An
optional dependency group used only by MZO's own release-building tooling
is excluded from the default install. The Python version is pinned exactly
by the dependency lock regardless of the host's system Python. No
dependency was added beyond the template's starting set over the course
of this project.

**Licences.** The dataset schema's admission field governs what may be
indexed at all — a record marked both restricted and index-eligible
cannot even be constructed as a valid object, a schema-level guarantee
rather than a runtime check. The official guides that would otherwise
cover certain advertising-claim and licensing questions are absent from
every release this project has worked with, withdrawn on licence grounds
rather than content grounds, while MZO pursues separate permission — this
is a known, documented gap in the corpus, not an omission on this
project's part, and it is the direct cause of the `insufficient_evidence`
questions this project's evaluation set deliberately includes.

**Security assumptions.** All contributors to this assessment share a
single, time-limited programmatic AWS IAM user with no console access. Its
policy boundary — verified against AWS's own policy simulator — permits
invoking the fixed set of approved Bedrock models and reading/writing only
`legal-kit-*`-prefixed OpenSearch indexes; it explicitly denies access to
every other AWS service this project might otherwise touch, every other
OpenSearch index, and any infrastructure-management or IAM action. Every
OpenSearch request from this project is signed even where the current
domain configuration would still accept an unsigned one, since that
looser policy is expected to tighten and building on the unsigned
shortcut would fail silently and later than useful. Because the IAM user
is shared, no billing or request log can attribute usage to a specific
contributor — the only record of this project's own AWS usage is the
self-written instrumentation it produces on every real embedding and
generation call, which is why usage logs exist as a first-class output of
every script that makes a real call. The shared embedding quota (300,000
tokens per minute for the whole account, not per contributor) is paced
against directly rather than relied on retries to absorb.

**Operational limitations.**

1. *WSL2 is a personal-machine workaround, not a project requirement.*
   Native Windows Python on the machine this project was developed on hit
   an OS-level security policy blocking the standard library's SSL module
   from loading — traced to that machine's own endpoint-security software,
   unrelated to this project's code or dependencies. The original,
   MZO-authored setup instructions contain no Windows- or WSL-specific
   step at all. Every command after this blocker was discovered ran
   through WSL2 as a workaround. This is disclosed here, and in the Work
   report's blocker log, as an access/environment failure specific to one
   contributor's machine; clean-checkout setup instructions in this
   submission follow the original, OS-agnostic form, with a footnote for
   any Windows contributor who hits the same block.
2. *`out_of_scope` domain-coverage risk* — see §5. Named, deliberately
   deferred pending empirical verification, and since resolved: the
   Generation evaluation report's real run confirmed, across two
   independent executions, that the risk did not materialize
   (`insufficient_evidence_misclassified_as_out_of_scope: 0`).
3. *1536-dimension embedding bug, caught before it reached production.*
   The embedding endpoint's default, unrequested output dimension (1024)
   silently mismatched the already-created vector index mapping (1536); a
   smoke test caught this before the production indexing run, and the
   fix — always requesting the dimension explicitly — is now the only
   code path that builds an embedding request.
4. *Nori analyzer not used, by deliberate choice, not blocker.* See §3.
   The permission question that originally motivated staying on the
   standard analyzer has since been resolved in this project's favor; the
   decision to stay on the standard analyzer anyway reflects the remaining
   cost/benefit judgement, made explicitly and with full information, not
   an unresolved gap.
5. *Repealed-statute weighting metadata is emitted but not yet consumed.*
   Repealed statute articles are tagged as such at chunking time, intended
   to eventually weight lexical matching over dense-vector matching for
   these placeholder-text chunks; no part of the current index mapping or
   retrieval logic currently reads that tag differently from any other
   chunk. This is real, currently inert metadata, named here as future
   work rather than left undocumented.
6. *No query-time filtering by document kind or chunk type.* A
   deliberate scope decision made against this corpus's small scale, not
   a gap discovered late. Reranking is a different case, not a
   never-attempted scope decision: it was implemented, measured, and
   reverted after a real, unintended side effect on
   `insufficient_evidence_refusal_accuracy` — see §3.
7. *Managed-domain Nori availability is now permitted but still
   mechanically untested.* MZO's authorization removes the policy
   uncertainty; no index-creation call using a Nori analyzer has actually
   been issued against the real managed domain, so whether it would work
   mechanically remains genuinely unverified, independent of item 4 above.
8. *Generation token ceiling raised from 1024 to 4096, caught by a real
   run, not anticipated in advance.* `agent.py`'s `_GENERATION_MAX_TOKENS`
   was initially set to 1024; the Generation evaluation report's first
   real full-pipeline run hit a genuine truncation on its very first
   question (a 약사법 answer whose citations and reasoning did not fit),
   surfaced as an explicit `RuntimeError` naming the cause rather than a
   silently malformed response — `_generate`'s `stop_reason == "max_tokens"`
   check (§3) is exactly what made this failure legible instead of an
   opaque JSON-parse error. Raised to 4096 after confirming against
   ASSIGNMENT.md's fixed constraints that prompt/response-shape tuning is
   explicitly contributor discretion, not a boundary this project is
   fixed against moving. Bedrock bills only the tokens actually generated,
   so the higher ceiling costs nothing on every response that does not
   need it.

**Rebuild-without-private-state.** Every environment-dependent value —
AWS profile and region, model IDs, the OpenSearch URL, dataset version —
is read from the environment at the single entry-point layer described in
§4, never hardcoded elsewhere in the codebase. Every response names the
exact dataset, normalization, chunking, index, embedding-model,
generation-model, and prompt versions that produced it, so an answer's
provenance is recoverable from the response itself rather than from
contributor memory, IDE state, or an untracked notebook. The one caveat to
this claim is limitation 1 above; disclosing the WSL2 workaround honestly
is itself part of satisfying this requirement, not a threat to it.
