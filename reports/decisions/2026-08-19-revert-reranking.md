# Revert Reranking

Date: 2026-08-19
Status: Decided
Covers: Reverting the semantic reranking stage added 2026-08-18
(`src/legal_agent_assessment/rerank.py`, its wiring into `agent.py`, and
the matching sync code in `scripts/evaluate_retrieval.py` /
`scripts/evaluate_generation.py`) after six independent attempts at fixing
`insufficient_evidence` over-answering — the failure mode reranking itself
measurably worsened — all failed.

## Summary

Reranking was optional (ASSIGNMENT.md line 16: "any fusion or reranking
you choose"; line 60's "Explicitly not provided" list names "reranking
strategy" explicitly) — implementing it was never a requirement, and
neither is reverting it a compliance issue either way. It was added
2026-08-18 for one reason: raising Recall@10 (0.5714→0.5952). Its real,
measured side effect was worsening
`insufficient_evidence_refusal_accuracy` (0.5556→0.3333 on that day's
9-question denominator) by feeding the model's already-documented
over-answering weakness a wider net of topically-relevant-but-not-dispositive
material. Between 2026-08-18 and 2026-08-19, six independent mechanisms
across four classes were tried to fix that weakness directly
(`prompt-v3`, `prompt-v4`, `prompt-v5`, and two `verify.py` self-verification
variants, plus reranking itself as an unintended contributor) — all
failed. Of every lever considered, reverting reranking was the only one
with **already-measured, zero-additional-cost evidence** for its effect,
since the pre-reranking pipeline had already been run for real
(2026-08-18, second update) before reranking was added on top of it.

## The decision

Revert reranking. `src/legal_agent_assessment/rerank.py` and
`tests/test_rerank.py` deleted; `agent.py`, `contracts.py`
(`RuntimeVersions.rerank` field), and their tests reverted to their
pre-reranking state (`git checkout <pre-reranking commit> -- <files>`,
verified by full quality gate: ruff/mypy/pytest all clean, 233 tests).
`scripts/evaluate_retrieval.py` and `scripts/evaluate_generation.py` were
reverted to the same state and then had the unrelated, already-committed
2026-08-19 fixes (question-count assertions, a stale comment) reapplied on
top, since those commits' changes did not overlap with reranking's code.

## Why this trade, not a different one

| | Before (fusion-weight fix only) | After (+ reranking, reverted) |
| --- | --- | --- |
| Recall@10 | 57.14% | 59.52% |
| `insufficient_evidence_refusal_accuracy` (8-question denominator, question 41 excluded from both) | **50.0%** | 37.5% |
| Combined non-answer-classification (`insufficient_evidence` + `out_of_scope`) | **69.2%** | 61.5% |
| `false_refusal_count` | 1 (id 8) | 0 |
| Real per-query cost/latency | lower (no rerank call) | higher (median retrieval latency ~525ms→~4.5s; rerank cost ~$0.076/call) |

Reverting gives up 2.38 points of Recall@10 and reintroduces one false
refusal (id 8), in exchange for recovering 12.5 points of
`insufficient_evidence_refusal_accuracy` and 7.7 points of the combined
non-answer-classification figure, plus a permanent reduction in per-query
cost and latency.

**Why this direction, not the reverse:** this project's stated mission
(from the 2026-08-10 call notes preserved in this project's own working
history) is demonstrating a legal assistant trustworthy enough to earn
belief through evidence, not assertion — a system that says "I don't have
enough evidence" honestly is a materially smaller failure than one that
gives a confident, plausible-sounding answer built on evidence that does
not actually decide the question. `insufficient_evidence` over-answering
is exactly the second, more damaging failure mode; a single false refusal
(id 8) or a retrieval miss that does not itself produce a wrong answer is
the first, less damaging one. Given a choice between improving a metric
tied to the more damaging failure mode at the cost of a metric tied to the
less damaging one, this project weights the former higher.

## Why revert specifically, not another fix

Six independent mechanisms were tried before this decision, across four
classes, all documented in full in the Generation evaluation report's
"insufficient_evidence refusal accuracy" section:

1. `prompt-v3` (blanket anti-analogy instruction) — reverted, worsened false refusals more than it fixed.
2. `prompt-v4` (contrastive worked example) — reverted, no improvement, worsened false refusals.
3. `prompt-v5` (structural `source_directly_resolves` field) — reverted, no improvement, worsened false refusals.
4. Reranking itself — approved for a different reason (Recall@10), found afterward to worsen this specific weakness as a side effect.
5. `verify.py` v1 (lenient separate-verification call, shown the answer) — piloted cheaply, 0/6 known failures caught.
6. `verify.py` v2 (strict separate-verification call, answer hidden) — piloted cheaply, 1/6 caught.

Every mechanism that tried to fix over-answering *directly* (1, 2, 3, 5,
6) failed. Reranking (4) is different in kind: it did not attempt to fix
the weakness at all — it caused it, as an unintended side effect of an
unrelated, real improvement. Because its cause (a wider, more
semantically-generous candidate pool) and its cost (Recall@10 gain, real
per-query latency/cost) were both already fully measured, undoing it did
not require a new real-cost experiment the way testing any further fix
attempt would have. This is why it is the lever chosen here and not, for
example, a further prompt variant or a narrower reranker pool size (both
considered and set aside as requiring new real-cost pipeline runs with
uncertain payoff, at a point 2 days before the submission deadline).

## What remains true after this revert

`insufficient_evidence_refusal_accuracy` is 50.0% (4/8), not 100% — this
revert recovers the cost reranking specifically added, it does not fix the
underlying over-answering mechanism itself. Six real, independent attempts
at a direct fix (including the judge.py-style separate-call pattern this
project already uses successfully elsewhere) have all failed. This is
disclosed as an open, real limitation, not resolved by this decision — see
the Generation evaluation report's "What remains unresolved" and the Work
report's "What one additional week would allow" for what a genuinely
different fix (a second, independently-verified model identity, or a
human-reviewed check) that this project's two-week, single-verified-model
constraints ruled out would require.

## Storage

Code: `src/legal_agent_assessment/agent.py`, `contracts.py` (reverted);
`rerank.py`, `tests/test_rerank.py` (deleted); `tests/test_agent.py`,
`tests/test_contracts.py` (reverted); `scripts/serve_legal_agent.py`,
`scripts/smoke_contract.py`, `scripts/evaluate_retrieval.py`,
`scripts/evaluate_generation.py` (reverted, with the unrelated 2026-08-19
question-41 fixes reapplied). Data:
`reports/eval/generation_evaluation_results.json`,
`reports/eval/retrieval_evaluation_results.json` (recomputed from the
real, already-stored pre-reranking run, question 41 excluded — no new
pipeline run). Reports: `reports/generation-evaluation-report.md`,
`reports/retrieval-evaluation-report.md`, `reports/work-report.md`
(reranking's own real, historical numbers are kept and clearly marked as
historical, not deleted).
