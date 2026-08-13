# Retrieval Test Set, Relevance Judgements, and Metrics Design

Date: 2026-08-13
Status: Decided
Covers: ASSIGNMENT.md required work items 5 ("Build a test set and
relevance judgements suitable for your retrieval claim") and 6 ("Define and
compute quantitative retrieval metrics such as Recall@k, MRR, or nDCG"),
against the already-completed hybrid RRF retrieval pipeline
(`reports/decisions/2026-08-13-retrieval-design.md`,
`docs/superpowers/plans/2026-08-13-retrieval-implementation.md`, both
merged and pushed).

It does not cover: generation evaluation (grounding, citation integrity,
hallucination — ASSIGNMENT.md item 7's own report axis per `SUBMISSION.md`);
the Architecture/Work report documents themselves (this note is raw
material for the eventual Retrieval evaluation report, not the report);
reranking (already rejected, `reports/decisions/2026-08-13-retrieval-design.md`
Decision 3).

## Summary of decisions

| Area | Decision |
| --- | --- |
| Query construction | LLM-drafted (Claude reads one source chunk, writes a realistic esthetician-shop-owner-style question that chunk answers), human-reviewed and approved per query — never a near-verbatim rephrasing of the chunk's own text |
| Composition | 50 total: 40 answerable (4 per legal domain × 10 domains), 5 deliberately unanswerable (targeting the known official-guide licensing gap), 5 out-of-scope (non-legal questions) |
| Relevance judgement | Binary; the source chunk a question was drafted from is the required positive; additional relevant chunks may be noted optionally, exhaustive pooling against all 7,887 chunks is explicitly out of scope and documented as a limitation |
| Metrics | Recall@10 (matches the fused top-10 that generation actually receives) and MRR; nDCG not computed (binary relevance makes it largely redundant with MRR here) |
| Leakage controls | (1) the test-set file is never read by any indexing script, structurally, not just by convention; (2) an automated lexical-overlap check between each question and its source chunk's text, run as part of the evaluation script and reported in its output |
| Storage | `reports/eval/retrieval_test_set.json`, committed (not gitignored) — required for MZO's rerun per `SUBMISSION.md`, but read only by the evaluation script, never by `scripts/index_chunks.py` or any indexing path |
| Evaluation script | `scripts/evaluate_retrieval.py` — pure retrieval only (BM25 + k-NN + RRF fusion, reusing `retrieval.py` directly), no generation call, matching `SUBMISSION.md`'s instruction to separate deterministic retrieval measurement from stochastic generation measurement; self-instruments usage/cost like `scripts/index_chunks.py` and `scripts/serve_legal_agent.py` already do, since it makes 50 real Bedrock embedding calls |

## Decision 1: LLM-drafted, human-approved, realistic-user-phrased questions — not chunk paraphrases

**Why not a direct rephrasing of chunk text:** `README.md`'s quiet-failure table names "출처에서 파생된 근사 복제 테스트를 실사용 품질로 제시" (presenting a source-derived near-copy test as real-user quality) as a failure discovered only at review time, invalidating the entire retrieval evaluation report. A question built by lightly rewording a chunk's own sentence shares most of its vocabulary with that chunk, so BM25 retrieves it almost by construction — the resulting Recall@10/MRR numbers would measure lexical-overlap detection, not the semantic retrieval this project's hybrid design (mapping design Decision 6, k-NN via Cohere embeddings) exists to provide.

**Why LLM-drafted rather than fully manual:** this project's actual target audience, established in the original client call (`reports/decisions/`... — see `[[project_legal_agent_assessment]]` memory, "에스테틱샵 원장님들의 신뢰성 우려"), is a non-lawyer small-business owner asking practical questions ("이 광고 문구 써도 되나요?"), not a lawyer quoting statute language. Reliably producing 50 questions in that register, across 10 unfamiliar legal domains, by hand within this assessment's time budget is not realistic for one contributor. Claude reads one source chunk and drafts a question in that practical register; a human reviews and approves (or rejects and asks for a redraft) each one before it enters the test set — the human judgement step, not the drafting step, is what keeps this from being an unreviewed LLM artifact.

**Why this doesn't violate "no synthetic legal evidence":** ASSIGNMENT.md's prohibition targets the *dataset* — adding external corpus records, web-search results, or synthetic legal evidence to what gets indexed and cited as a source. A test question is not evidence and is never indexed (Decision 5); the *chunk* it is checked against remains the project's real, frozen, MZO-supplied text throughout.

## Decision 2: 50 questions — 40 answerable across 10 domains, 5 unanswerable, 5 out-of-scope

`SUBMISSION.md`'s Retrieval evaluation report explicitly requires disclosing "answerable, unanswerable, and out-of-scope composition" — a test set that is only answerable questions cannot support that disclosure, and cannot exercise the `insufficient_evidence`/`out_of_scope` paths this project's contract (`contracts.py`'s `AnswerStatus`) defines.

- **40 answerable, 4 per domain** across the 10 legal domains named in the original client scope (약사법, 의료법, 개인정보보호법, 의료기기법, 표시광고법, 미용법, 화장품법, 무면허의료행위, 공중위생법, 안마사법) — enough per domain to report "aggregate and per-domain results" (`SUBMISSION.md`) meaningfully without an exhaustive-labelling effort this assessment's timeline does not support.
- **5 deliberately unanswerable**, shaped around the already-identified, already-verified corpus gap: `DATASET.md`'s exclusion of the official guides for licensing reasons, and the exact scenario `reports/decisions/2026-08-13-retrieval-design.md` Decision 4 already validated end-to-end (a real run against the live pipeline correctly produced `insufficient_evidence` for a 표시광고법 phrase-specific question). These 5 are not source-derived from any chunk (there is no source chunk — that is the point), so Decision 1's leakage concern does not apply to them; their "ground truth" relevance judgement is simply "no chunk in this corpus should be judged relevant."
- **5 out-of-scope**, non-legal questions (e.g., unrelated small-talk or a different professional domain entirely) to exercise `out_of_scope` — noting explicitly that `out_of_scope` *response-state logic* itself is not yet implemented in `agent.py` (deferred, `reports/decisions/2026-08-13-retrieval-design.md`'s own scope note) — these 5 establish the test-set composition SUBMISSION.md asks for now, ahead of that later implementation, rather than being blocked on it.

## Decision 3: Binary relevance, source chunk as the required positive, no exhaustive pooling

`SUBMISSION.md` asks for "relevance-labelling method and treatment of multiple relevant results" to be disclosed — this decision is that method.

Because every answerable question is drafted *from* a specific chunk (Decision 1), that chunk's `chunk_id` is the test set's required positive judgement, known by construction rather than needing separate manual labelling. If, while reviewing a drafted question, the human reviewer or Claude notices another chunk in the corpus would also genuinely answer it (e.g., a closely related provision), that `chunk_id` may optionally be added as an additional positive — but exhaustively checking all 7,887 chunks against each of the 50 questions to find every possible relevant one is explicitly out of scope: it is not required for Recall@10/MRR to be computable (both are well-defined against a "known positives" set that is a documented subset, not a claimed-complete one), and doing it by hand is not a two-week-assessment-scale effort. `SUBMISSION.md`'s "failed-query analysis" is where a question that turns out to have more real positives than were labelled would surface, if it does.

## Decision 4: Recall@10 and MRR; nDCG not computed

`ASSIGNMENT.md` item 6 asks for metrics "such as Recall@k, MRR, or nDCG" — an illustrative list, not a mandate to compute all three, and explicitly asks the contributor to explain *why* each chosen metric and cutoff is appropriate.

- **Recall@10**: cutoff chosen to match exactly what generation actually receives (`reports/decisions/2026-08-13-retrieval-design.md` Decision 2's fused top-10) — this metric answers "is the real, required-positive chunk among what the answer-generation step actually saw," which is the retrieval property that most directly determines whether an `answered` response *can* be correctly grounded.
- **MRR**: sensitive to *where* in the ranking the positive lands, not just whether it's in the top 10 — a useful complement to Recall@10 for judging whether RRF (Decision 2 of the retrieval design) is actually surfacing the right chunk near the top, not just squeaking it into position 10.
- **nDCG not computed**: nDCG's distinguishing value over MRR comes from graded relevance (multiple positives at different relevance levels) — Decision 3's binary, single-required-positive judgement set gives it little room to differ meaningfully from MRR here. Not computing it is a scope decision, not a capability gap; if item 5/6 evolves to richer graded judgements later, nDCG becomes worth adding then.

## Decision 5: Leakage controls — structural non-indexing plus an automated overlap check

`SUBMISSION.md` explicitly requires disclosing "leakage controls, including source-derived queries" as its own line item, separate from "relevance-labelling method" — this decision is that disclosure's substance.

1. **Structural, not conventional:** `reports/eval/retrieval_test_set.json` is read by exactly one script (`scripts/evaluate_retrieval.py`, Decision 6) that never calls any indexing function. `scripts/index_chunks.py`'s `load_records`/`select_records_for_indexing`/chunking pipeline has no code path that reads anything under `reports/`. This is a structural guarantee (there is no import, no shared file-reading code, nothing to accidentally wire together), not a "remember not to" convention — the closest failure mode this project has already lived through was exactly this class of "looks fine, is silently wrong" risk (the indexing plan's final review caught a missing-index case that would have silently auto-created the wrong mapping and still reported success — `docs/superpowers/plans/2026-08-13-opensearch-indexing-implementation.md`'s Task 7 fix), so this decision deliberately avoids relying on discipline alone.
2. **Automated overlap check:** `scripts/evaluate_retrieval.py` computes, for each answerable question, a simple lexical-overlap measure between the question text and its source chunk's `text` (e.g., longest common substring length, or a token-overlap ratio — the exact measure is an implementation detail for the plan, not fixed here) and reports it per question and in aggregate. This directly implements `README.md`'s stated minimum detection criterion ("평가 질의·예상 답변 text와 indexed chunk 사이의 동일·근사 중복 탐지") rather than only asserting compliance in prose. A question scoring above a reasonable overlap threshold is a signal the human-review step (Decision 1) should have caught, not a silent pass.

## Decision 6: Evaluation script — pure retrieval, self-instrumented usage/cost

`scripts/evaluate_retrieval.py` (new): loads `reports/eval/retrieval_test_set.json`, and for each question, runs exactly the retrieval half of `agent.py`'s `answer_sync` — embed the query (`input_type="search_query"`, reusing `embedding.build_embed_request`/`parse_embed_response`, never `"search_document"`), `build_bm25_query`/`build_knn_query`/`reciprocal_rank_fusion` from `retrieval.py` (top-50/top-50/`k=60`, fused top-10, exactly matching the retrieval design's already-decided constants) — but stops there: no prompt is built, no Bedrock generation call happens. `SUBMISSION.md` explicitly asks to "separate deterministic retrieval measurements from repeated stochastic generation measurements," and retrieval (given a frozen index and a fixed query) is deterministic in a way a Claude generation call is not — computing Recall@10/MRR against only the deterministic half keeps that separation real rather than nominal.

This script embeds 50 real queries via real Bedrock calls — the same class of real, small-scale AWS usage `scripts/serve_legal_agent.py` already makes per query, and the same self-instrumentation obligation applies (`SUBMISSION.md`'s Work report: "AWS use: embedding calls, generation calls, input/output tokens... It can only come from instrumentation you write yourself"). The script writes a usage log to `reports/usage/` on the same pattern `scripts/index_chunks.py`/`scripts/serve_legal_agent.py` already established (embedding call count, estimated tokens, estimated cost, elapsed time), including on a failure path.

Output: per-question Recall@10 (0 or 1, since there is exactly one required positive per answerable question under Decision 3)/MRR contribution, aggregate Recall@10/MRR, and a per-domain breakdown (grouped by the domain each answerable question was drafted for) — the raw material `SUBMISSION.md`'s "aggregate and per-domain results" and "failed-query analysis" lines ask the eventual Retrieval evaluation report to present.

## Explicitly out of scope for this note

- The exact JSON schema of `reports/eval/retrieval_test_set.json` field-by-field, the exact lexical-overlap formula (Decision 5), and `scripts/evaluate_retrieval.py`'s CLI shape — implementation-time detail for the plan, not fixed here.
- Writing the actual 50 questions — that is this plan's own deliverable, done as part of implementation (with human review per question, Decision 1), not pre-decided in this design note.
- The `out_of_scope`/`dependency_unavailable` response-state logic the 5 out-of-scope questions anticipate testing later — still deferred to a future item 7/8 task, unchanged from `reports/decisions/2026-08-13-retrieval-design.md`.
- The Retrieval evaluation report document itself (`SUBMISSION.md`'s deliverable) — this note supplies the design its numbers will be computed under, not the report's prose.

This is a design decision, not yet implementation — no test-set file or evaluation script exists yet as of this note.
