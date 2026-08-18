# Generation Evaluation Report

Date: 2026-08-14
Covers: SUBMISSION.md's "Generation evaluation report" requirements —
grounding, citation integrity, unsupported citation/hallucination,
insufficient-evidence refusal, out-of-scope refusal, latency, token use, and
cost — with deterministic retrieval measurement kept separate (see the
[Retrieval evaluation report](retrieval-evaluation-report.md)) from the
necessarily stochastic generation measurements below.

All numbers are from a real, full-pipeline run of `LegalAgent.answer_sync`
(retrieval + real Bedrock generation) against all 50 questions in
`reports/eval/retrieval_test_set.json`, committed at `ff85ab8`
(`reports/eval/generation_evaluation_results.json`). Method is fixed by
`reports/decisions/2026-08-14-generation-evaluation-design.md`.

## Methodology, restated briefly

Every one of the 50 questions runs through the real, production
`LegalAgent.answer_sync` once — the same method
`scripts/serve_legal_agent.py` uses for one real question, run here over
all 50, making no separate evaluation-only pipeline. For every response
that comes back `answered`, a second real Bedrock call (the same fixed
Sonnet model, `legal_agent_assessment.judge`) classifies whether the
answer's actual prose content is supported by its own cited excerpts:
`grounded` / `partially_grounded` / `unsupported`. Refusal accuracy is a
direct comparison of each question's real `status` against the test set's
`expected_status` field. One real run per question, not repeated trials —
see "Reproducibility" below for why, and for what running it twice in
practice showed.

## Grounding

Of the 41 responses that came back `answered` (see "insufficient_evidence
refusal accuracy" below for why 41 and not 40), the judge classified:

| Verdict | Count | Share of judged answers |
| --- | --- | --- |
| `grounded` | 9 | 22.0% |
| `partially_grounded` | 32 | 78.0% |
| `unsupported` | 0 | 0.0% |
| `judge_parse_error` | 0 | — |

**Zero `unsupported` answers** — the judge never classified an answer as
making claims the cited excerpts do not support at all. But
**`partially_grounded` is the large majority (78%), not the exception** —
this is disclosed as the headline finding here, not smoothed over by the
absence of outright `unsupported` verdicts. Reading the judge's
justification text for the `partially_grounded` cases shows a consistent
pattern: not fabrication, but overreach on a specific sub-claim inside an
otherwise well-supported answer. Two real examples:

- Question 1 (약사법, packaging/repackaging cosmetics as unlicensed
  manufacture): the judge flagged that the answer characterized one cited
  precedent (`precedent-118895`) as a "lower court" ruling in implicit
  contrast to another, when the source excerpt itself does not state that
  court relationship — the underlying legal conclusion was correctly
  drawn, but a framing detail was asserted beyond what the excerpt says.
- Question 44 (표시광고법, "100% satisfaction guaranteed" in a before/after
  ad): the judge flagged that the answer implied a cited precedent
  confirmed the ad was impermissible, when the cited precedent's summary
  actually held the opposite for that specific ad — the legal standard
  quoted was correctly grounded, but the outcome characterization was not.

**Per-domain grounding** (not required by SUBMISSION.md for this report,
included since it comes free from data already collected):

| Domain | grounded | partially_grounded | unsupported | n |
| --- | --- | --- | --- | --- |
| 공중위생법 | 4 | 0 | 0 | 4 |
| 의료기기법 | 1 | 4 | 0 | 5 |
| 의료법 | 1 | 3 | 0 | 4 |
| 미용법 | 1 | 3 | 0 | 4 |
| 안마사법 | 1 | 3 | 0 | 4 |
| 개인정보보호법 | 1 | 2 | 0 | 3 |
| 약사법 | 0 | 4 | 0 | 4 |
| 표시광고법 | 0 | 5 | 0 | 5 |
| 화장품법 | 0 | 4 | 0 | 4 |
| 무면허의료행위 | 0 | 4 | 0 | 4 |

공중위생법 is the only domain with every answer fully `grounded`; four
domains (약사법, 표시광고법, 화장품법, 무면허의료행위) had zero fully
`grounded` answers this run — every one of their answered questions drew
at least one judge-flagged overreach. This is disclosed as a real,
domain-correlated pattern in this run, not investigated further here (a
larger sample per domain, or a second judge pass, would be needed to say
whether it is a stable per-domain property or this run's noise — named as
future work below).

**Method limitation, disclosed plainly.** This is a single-model,
single-pass, automated classification (`reports/decisions/2026-08-14-
generation-evaluation-design.md` Decision 2) — not a human-verified gold
standard, and the same fixed Sonnet model that generated some of these
answers is also the one judging them (a real, accepted trade-off: this
project's only other verified model identity is Sonnet, so introducing a
second model as judge would add an unverified-identity risk this
evaluation chose not to take on, per the design doc). A second independent
judge pass or a human spot-check of a sample would tighten this; neither
was attempted here.

## Citation integrity

`agent.py`'s existing logic already discards any cited `chunk_id` that was
not actually retrieved in that call, surfacing the discard through the
response's `limitations` field rather than silently dropping or
fabricating one. Across all 50 real calls this run, **`limitations_fired_count:
0`** — the guard never had to intervene on a *partial* fabrication (some
cited ids real, some not).

**Disclosed gap, found during this evaluation's own final code review, not
asserted away.** `agent.py` has a second, separate fabricated-citation
path that this metric cannot see: if the model claims `status: "answered"`
but *none* of its cited ids were actually retrieved (total fabrication,
not partial), the response is downgraded to a bare `insufficient_evidence`
with an *empty* `limitations` field — indistinguishable, in this run's
data, from the model honestly saying "I don't have enough evidence."
Concretely: questions 11 and 22 both came back `insufficient_evidence`
with `citation_count: 0`, and this evaluation's committed data cannot tell
whether that was an honest refusal or a caught total-fabrication attempt
(see "False refusals" below — the retrieval evaluation's own data suggests
the honest-refusal reading is more likely for these two, but the response
contract does not currently make this provable either way). Closing this
gap needs a production change to `agent.py`'s response contract exposing
the total-fabrication case distinctly, which is out of scope for this
evaluation and named under "What one more week would allow" in the Work
report — not attempted here.

## Unsupported citation / hallucination

Read together with "Grounding" above: **zero answers were classified
`unsupported`** — the judge never found an answer making a claim the cited
excerpts do not support at all. The 32 `partially_grounded` answers are
the more accurate place to look for hallucination-adjacent risk in this
run: every one of them has at least one claim the judge could not trace to
its citations, even though none crossed into wholesale unsupported
territory. Treating `partially_grounded` as "no meaningful risk" because
it is not `unsupported` would overstate this run's result — the honest
summary is: no answer this run invented a claim wholesale, but the
majority of answers included at least one claim (a framing detail, an
outcome characterization, an inferred general statement) that outran what
its cited excerpts specifically say.

## insufficient_evidence refusal accuracy

**0.4 (2 of 5 correct).** Of the 5 questions with `expected_status:
"insufficient_evidence"` (ids 41-45, targeting the documented gap where
the official guidance documents that would resolve certain
advertising-phrase questions are absent from every release on licence
grounds — DATASET.md, and see the Retrieval evaluation report's "Test-query
sources and construction method"):

| id | domain | question | actual status | correct? |
| --- | --- | --- | --- | --- |
| 41 | 표시광고법 | "피부 노화가 되돌아간다"고 광고해도 되나요? | `insufficient_evidence` | ✅ |
| 42 | 화장품법 | "식약처 인증 성분 사용" 문구를 써도 되나요? | `answered` | ❌ |
| 43 | 의료기기법 | "의료기기 수준의 효과"라고 홍보해도 되나요? | `answered` | ❌ |
| 44 | 표시광고법 | "100% 만족 보장" 문구를 붙여도 되나요? | `answered` | ❌ |
| 45 | 표시광고법 | "피부과 전문의가 추천"했다고 광고해도 되나요? | `insufficient_evidence` | ✅ |

**The failure mode, investigated rather than left as a bare number.** All
5 questions retrieved a full 10 hits (`retrieval_hit_count: 10`) — this is
not a retrieval gap, retrieval is doing its job and surfacing real,
on-topic statute and precedent chunks. The 3 misclassified questions (42,
43, 44) each received a generation-model answer built from those real,
on-topic chunks, reasoning by analogy to a related but not dispositive
precedent — the judge's own grounding verdicts for these three
(`partially_grounded`, `grounded`, `partially_grounded`) confirm the
answers are largely faithful to what was retrieved. The model is not
hallucinating law; it is **answering a specific-fact judgment call the
retrieved evidence does not actually resolve**, rather than recognizing
the gap and refusing. This is exactly the corpus gap the test set's design
intentionally targets (DATASET.md's withdrawn-guide gap): the model has
enough context to sound authoritative but not enough to be correct with
certainty, and its current prompt does not push it toward refusing in that
specific situation strongly enough.
`insufficient_evidence_misclassified_as_answered: 3` in the committed
aggregate records this directly.

**Separately, `insufficient_evidence_misclassified_as_out_of_scope: 0`.**
This is the deferred risk from item 7/8's final review (the concern that
the `out_of_scope` prompt instruction, having no explicit domain list,
might misclassify a genuinely in-scope-but-unanswerable question as
`out_of_scope` instead). This evaluation is the first real, empirical
check of that risk, and it did not materialize — confirmed identically
across two independent real runs (this committed run, and the earlier
run before this report's code fixes, `fd810f1`). No prompt change is
needed for that specific risk.

**A prompt revision was tried and reverted based on this finding.**
`prompt-v3` added an explicit anti-analogy instruction telling the model
not to answer by reasoning from a related-but-not-dispositive precedent.
Re-running all 50 questions showed `insufficient_evidence_misclassified_as_answered`
improved from 3 to 2, but `false_refusal_count` (see below) worsened
from 2 to 8 and `answered_status_match_rate` dropped from 0.95 to 0.8 —
a net worsening from 5 to 10 total status errors. `prompt-v3` was
reverted; `prompt-v2` (this report's committed numbers) remains in
production.

## False refusals

Not part of SUBMISSION.md's named bullet list, but visible as a byproduct
of running all 50 questions and reported here because it is a real,
non-obvious finding: **2 of the 40 answerable questions were incorrectly
refused** (`false_refusal_count: 2`, `answered_status_match_rate: 0.95`).

| id | domain | question | actual status |
| --- | --- | --- | --- |
| 11 | 개인정보보호법 | 매장 회원 정보 관리 시 개인정보보호법상 지킬 것 | `insufficient_evidence` |
| 22 | 화장품법 | 매장 판매 화장품도 품질관리기준을 지켜야 하는지 | `insufficient_evidence` |

Cross-referenced against the Retrieval evaluation report's own per-question
results (`reports/eval/retrieval_evaluation_results.json`): **both
questions' required-positive chunk was present in the fused top-10**
(`recall_at_10: 1` for both — id 11 at rank 6, id 22 at rank 4). Retrieval
delivered the correct source chunk to generation in both cases; generation
still declined to answer. This is a genuine generation-side over-caution
finding, not a retrieval failure — the opposite failure direction from the
insufficient_evidence section above (there, the model answered when it
should have refused; here, it refused when it had what it needed to
answer). Both directions are real and disclosed; neither is investigated
to a root cause beyond what is stated here, and both are named as
candidates for prompt-tuning follow-up in the Work report rather than
guessed at and changed here.

## out_of_scope refusal accuracy

**1.0 (5 of 5 correct).** All 5 non-legal/meta questions (ids 46-50)
correctly returned `out_of_scope`, with no false positives among the
answerable or insufficient_evidence questions either
(`insufficient_evidence_misclassified_as_out_of_scope: 0`, and no
answerable question returned `out_of_scope` in this run's data).

## Latency

Wall-clock, per question, this run (retrieval + generation, and the judge
call where one happened — the judge call is not part of the deliverable's
own response latency, but this evaluation's per-question `latency_ms` is
measured around the whole loop iteration including it, so the two
`answered`-path numbers below are judge-inclusive):

| | n | min | median | max |
| --- | --- | --- | --- | --- |
| All 50 questions | 50 | 1,445.8 ms | 13,931.0 ms | 24,510.8 ms |
| `answered` only | 41 | 7,610.4 ms | 14,477.1 ms | 24,510.8 ms |
| Refusal (`insufficient_evidence`/`out_of_scope`) | 9 | 1,445.8 ms | 1,740.9 ms | 1,902.6 ms |

| Percentile (all 50) | Latency |
| --- | --- |
| p50 | 13,931.0 ms |
| p95 | 19,067.2 ms |
| p99 | 22,031.1 ms |

Refusals are consistently fast (~1.4-1.9s) — the model reaches a
no-evidence or out-of-scope decision quickly. `answered` responses take an
order of magnitude longer (median ~14.5s), dominated by the judge call
(a second real Bedrock round-trip) stacked on top of the generation call
itself; the deliverable's own single-call latency (generation only, no
judge) is not separately isolated in this run's instrumentation and would
need a small follow-up measurement to report precisely.

## Token use and cost

Self-instrumented, per SUBMISSION.md's requirement (contributors share one
IAM user; billing/CloudTrail cannot attribute usage, so every real call in
this evaluation is recorded from `LegalAgent.answer_sync`'s own `on_usage`
callback and the judge call's real Bedrock response, the moment each call
returns — not reconstructed afterward).

| | Value |
| --- | --- |
| Embed tokens (estimated, query embedding only) | 1,887 |
| Generation input tokens (real, answer + judge calls) | 465,591 |
| Generation output tokens (real, answer + judge calls) | 29,958 |
| **Estimated cost** | **$1.846369** |
| Wall-clock elapsed (full 50-question run) | 610.82 s (~10.2 min) |

Per-question token counts are recorded in the committed results file
(`reports/eval/generation_evaluation_results.json`, `embed_estimated_tokens`
/ `generation_input_tokens` / `generation_output_tokens` on every entry) —
their sum reproduces the aggregate exactly, a property checked directly
against this run's data before writing this report. Rates: Cohere Embed v4
$0.12/M tokens, Claude Sonnet input $3.00/M tokens, output $15.00/M tokens
(same rates as `scripts/serve_legal_agent.py` and the index-build cost
already reported in the Retrieval evaluation report).

## Reproducibility

Per Decision 1 of the design doc, this evaluation runs each question once,
not repeated trials — generation is a stochastic sampling process, so a
single real run is reported honestly as a single real run, not averaged
across trials SUBMISSION.md does not separately require. In practice, this
question set was run twice against materially the same code (an earlier
successful run, `fd810f1`, before this report's own instrumentation fixes,
and the committed run, `ff85ab8`, after them) — **both runs reproduced the
identical set of 5 status-decision mismatches** (same ids: 11, 22 false
refusals; 42, 43, 44 misclassified answers), while individual grounding
verdicts shifted slightly (`grounded_count` 13→9, `partially_grounded_count`
28→32) as expected for a resampled generation. This is reported as
evidence the refusal-accuracy findings above are a stable property of the
current prompt and corpus, not an artifact of one unlucky sample — not as
a formal repeated-trial variance measurement, which remains named as
future work.

## Versions

| Component | Version |
| --- | --- |
| Dataset | `dataset-2026-08-11-v2.1` |
| Normalization | `norm-v1` |
| Chunking | `chunk-v1` |
| Index | `index-v1` |
| Embedding model | `global.cohere.embed-v4:0` |
| Generation model | `global.anthropic.claude-sonnet-4-6` |
| Answer prompt | `prompt-v2` |
| Judge prompt | `judge-prompt-v2` |
| Index name | `legal-kit-assessment-jynlee-chunk-v1-index-v1` |

`prompt-v2` and `judge-prompt-v2` are both real, committed-history version
bumps: `prompt-v2` reflects item 7/8's out_of_scope/insufficient_evidence
3-way status expansion; `judge-prompt-v2` reflects the real, in-production
fix (a `system`-field JSON-only instruction) that took the judge's own
JSON parse-failure rate from 57.5% to 0% during this evaluation's
development (see the SDD ledger for the full real-cost troubleshooting
history).

## Storage and reproduction

`reports/eval/generation_evaluation_results.json` (committed, `ff85ab8`) —
full per-question results including answer text, citations, grounding
verdict and justification, and token/latency figures for all 50 questions.
Real per-run usage logs (gitignored, per this project's shared-IAM
instrumentation convention) are in `reports/usage/`. Rerun with:

```
OPENSEARCH_URL=http://localhost:9200 \
uv run python scripts/evaluate_generation.py --contributor <your-contributor-id>
```

against a rebuilt index (see the Retrieval evaluation report's index-build
instructions) — this is a real-cost script (~$1.85 per full run), not
exercised by the automated test suite, matching `scripts/evaluate_retrieval.py`'s
own convention.
