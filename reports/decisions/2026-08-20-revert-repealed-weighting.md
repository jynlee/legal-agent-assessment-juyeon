# Revert Repealed-Statute BM25/kNN Reweighting

Date: 2026-08-20
Status: Decided
Covers: Reverting the `status="repealed"` fusion-reweighting feature
(`reciprocal_rank_fusion`'s `list_id_multipliers` parameter, its wiring
into `agent.py`/`evaluate_retrieval.py`, and their tests) after a real
measurement against three actual repealed-article questions showed it
makes ranking worse, not better.

## Summary

`status="repealed"` metadata has been emitted at chunking time since
2026-08-12 (statute chunking design Decision 3) but was never consumed by
any retrieval logic -- a design hand-off dropped across three decision
docs, found 2026-08-20. Decision 3's own stated intent was to "weight
BM25 (exact article-number matching) over dense-vector similarity" for
these chunks, on the assumption that a repeal placeholder's short,
formulaic text ("제19조 삭제 <2011.3.30>") carries little embedding
meaning but *is* exactly matchable by article number. This is not a
SUBMISSION.md/ASSIGNMENT.md requirement -- grepped against every
contributor-facing doc (ASSIGNMENT.md, README(.en).md, DATASET.md,
DATASET_SCHEMA.md, CONTRACT.md, SUBMISSION.md, AGENTS.md): zero mentions
of "repealed" or "폐지" anywhere. It was a self-designed enhancement, and
MZO's own reference scorer (`legal-agent-assessment-template`) implements
no equivalent either (its BM25 query is `title^2, text` only, with no
field for repeal status in its canonical payload schema).

Implemented 2026-08-20: BM25's contribution for a repealed chunk was
boosted 3.0x, kNN's damped to 1/3x -- swapping the two retrievers'
effective weights for exactly these chunks, reusing the already-tuned 3.0
rather than a new number. 237/237 tests passed, ruff/mypy clean, and a
live re-run across the real 42-question retrieval test set showed zero
regression (byte-identical top-10 for every question) -- but also proved
nothing, since no repealed chunk appeared in any of those 42 questions'
top-50 candidates at all.

## Why it was reverted

Tested directly against three real repealed-article questions built from
actual `status="repealed"` records in the corpus (약사법 제19조, 제32조):

| Question | BM25 raw rank | kNN raw rank | Fused rank, before | Fused rank, after |
| --- | --- | --- | --- | --- |
| "약사법 제19조가 뭔가요?" | not found (top-50) | 30 | 32 | 74 |
| "약사법 제19조는 어떻게 됐나요?" | not found (top-50) | 12 | 21 | 55 |
| "약사법 제32조는 지금도 유효한가요?" | not found (top-50) | 2 | 6 | 52 |

Decision 3's premise was backwards: BM25 (under this project's standard
analyzer, not Nori -- see architecture-report.md limitation 4) never
found any of these three chunks in its own top-50 at all, while kNN
found all three reasonably well (rank 2-30). The fix boosted a retriever
that contributed nothing and damped the one retriever that was actually
working -- fused rank got 2-9x worse in every case, not better.

## The decision

Revert. `src/legal_agent_assessment/retrieval.py`,
`src/legal_agent_assessment/agent.py`, `scripts/evaluate_retrieval.py`,
`tests/test_retrieval.py`, `tests/test_agent.py`,
`reports/architecture-report.md`, and this decision's addendum to
`reports/decisions/2026-08-12-statute-chunking-design.md` were reverted
to their pre-change state (`git checkout -- <files>`, all uncommitted at
the time). Verified: 233/233 tests pass, matching the pre-change
baseline exactly.

`status="repealed"` metadata remains emitted and indexed but unconsumed,
same as before this attempt -- architecture-report.md limitation 5 is
unchanged from its pre-2026-08-20 text.

## What a working fix would need to look like

Diagnosed, not attempted (deadline-constrained): BM25's `multi_match`
over free text does not reliably surface an exact article number like
"제19조" -- plausibly a standard-analyzer tokenization gap (the same
class of issue architecture-report.md limitation 4 already names), or
dilution from "약사법" matching thousands of other chunks from the same
law. A structural fix, not a reweighting one, is the more promising
direction: the index already carries a parsed `article_number` keyword
field (`opensearch_index.py`); extracting an article-number pattern from
the query text and exact-filtering or boosting on that field would not
depend on free-text tokenization finding "제19조" at all. Untested; named
here as the next thing to try if this is revisited.

## Verification basis

All three test questions were run for real against the live index
(`legal-kit-assessment-jynlee-chunk-v1-index-v1`) with real Bedrock
embedding calls (3 calls, ~$0.00001) and real OpenSearch BM25/kNN
searches, comparing `reciprocal_rank_fusion`'s output with and without
the reverted multipliers on identical retrieved candidate sets.
