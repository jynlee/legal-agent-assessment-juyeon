# Question 41 Invalidation

Date: 2026-08-19
Status: Decided
Covers: A test-set construction defect found while reviewing the 6
confirmed-genuine `insufficient_evidence` over-answering failures named in
the Generation evaluation report's "insufficient_evidence refusal
accuracy" section. Question 41 is removed from
`reports/eval/retrieval_test_set.json` (56 → 55 questions); it is not
relabelled `answered`.

## Summary

Question 41 ("이 시술을 받으면 피부 노화가 되돌아간다고 광고해도 되나요?")
was constructed as an `insufficient_evidence` question, targeting an area
the withdrawn official MOHW/MFDS guide would have covered. On direct review
of the model's own cited sources (not just the aggregate number), the
general legal principle those sources state — that unverified claims
creating false medical expectations are prohibited — covers this question
on its face, not by analogical extension the way the other 5
confirmed-genuine failures do. This makes the question invalid as an
`insufficient_evidence` example. It cannot instead be relabelled
`answered`, because it was never drafted from a specific source chunk (see
"Why not relabel `answered`" below) — the Retrieval evaluation design's
Decision 3 requires a required-positive chunk_id "known by construction,"
and none exists for this question. With no valid category left, it is
removed from the test set entirely.

## Review methodology and the 6-case table

Following the same standard already applied to ids 43/54 (Generation
evaluation report, "Two gold-label errors found and corrected") — read the
question text and the model's actual cited excerpts line by line, not just
trust the aggregate metric — all 6 confirmed-genuine `insufficient_evidence`
failures (ids 41, 42, 44, 53, 55, 56) were reviewed against one
pre-registered question: **does the cited evidence decisively resolve this
specific question, or only extend to it by analogy?**

| Type | Case(s) | Verdict |
| --- | --- | --- |
| A general legal standard applies to this claim on its face, not by analogy | **41** | Question invalid |
| A specific ruling is extended to a different, not-identical service/category by analogy | 44 (customer satisfaction ≠ treatment effect), 55 (foot massage ≠ sports massage precedent) | `insufficient_evidence` stands |
| The answer imports a fact not present in any cited source | 42 (whether MFDS operates an ingredient-certification scheme) | `insufficient_evidence` stands |
| The model's own answer text states its own uncertainty | 53, 56 | `insufficient_evidence` stands |

The criterion was fixed before reviewing any individual case and applied
identically to all 6 — this is not a post-hoc rationalization for the one
case (41) that happened to help the headline number.

**Question 44 in particular was reviewed for reclassification, since it is
structurally the closest case to 41** (a real, on-point precedent
interpreting a similarly absolute-sounding phrase — "통증과 출혈이 거의
없다" implying 0%/100% — as prohibited) — but reclassifying it fails the
same test 41 passes: the precedent's holding is about **치료효과**
(treatment-effect claims, the exact scope of 의료법 제56조), and "100%
만족 보장" is a **customer-satisfaction** claim. Nothing in the cited
excerpts establishes that a satisfaction guarantee is treated as a
treatment-effect guarantee under this statute — extending the precedent's
holding from one legal category to the other is exactly the analogical
step the review criterion exists to catch, and 44 was kept as
`insufficient_evidence` on that basis. This decision not to reclassify the
case with the largest score-improving temptation is recorded here as the
evidence that 41's invalidation was not chosen because it helps the
headline number.

## Why not relabel `answered` (the circularity risk)

The Retrieval evaluation design (`reports/decisions/2026-08-13-retrieval-
evaluation-design.md`, Decision 3) fixes how a required-positive chunk_id
is assigned: "every answerable question is drafted **from** a specific
chunk... that chunk's `chunk_id` is the test set's required positive
judgement, known by construction." Ids 43 and 54 (the earlier gold-label
corrections) satisfied this cleanly: an independent corpus search — run
without looking at what the model had answered — found the exact resolving
provision the original construction pass's search terms had missed by a
lexical gap ("대여" not matching "빌려주다/빌리다").

Question 41 was never drafted from a specific chunk (`source_chunk_id:
null`, `relevant_chunk_ids: []` from construction) — it was deliberately
built to target a gap the withdrawn guide would have covered, with no
single source chunk in mind. Assigning `precedent-144207#summary-holding-001`
(the chunk the model itself cited in its real answer) as the required
positive would make this question's `Recall@10` contribution true by
construction: the model could only cite a chunk that retrieval had already
placed in the fused top-10, so scoring this question at all after picking
its positive from the model's own citation is circular — the same
"grading its own exam" risk already raised about the `insufficient_evidence`
mechanism review, now recurring in the retrieval metric. Attempting an
independent, blind-to-the-answer corpus search to find a legitimate
required positive (the 43/54 method) was considered but not attempted:
unlike 43/54, where a specific missed provision existed to be found,
question 41's defect is that a *general* principle resolves it, which does
not identify one single "drafted-from" chunk the way a specific missed
provision does — there is no clean candidate to search for. Given this,
invalidation (removal), not relabelling, is the only option that does not
either violate Decision 3 or introduce a circular metric.

## Effect on metrics

Test set: 56 → 55 questions (`insufficient_evidence`: 9 → 8).

**Retrieval evaluation: no change.** Question 41 was never in the
Recall@10/MRR denominator (`expected_status: "insufficient_evidence"` questions
are retrieved for transparency only, never scored) — Recall@10 (0.5952) and
MRR (0.3355) are identical before and after. `reports/eval/
retrieval_evaluation_results.json`'s `per_question` array drops the row;
`aggregate`/`per_domain`/`lexical_overlap` are untouched.

**Generation evaluation, recomputed from the already-stored per-question
results (no pipeline re-run — SUBMISSION.md's stochastic-generation caveat
means re-running would change answers for reasons unrelated to this
correction, conflating the two):**

| | Before (56, full) | After (55, question 41 excluded) |
| --- | --- | --- |
| `insufficient_evidence_refusal_accuracy` | 0.3333 (3/9) | **0.375 (3/8)** |
| `insufficient_evidence_misclassified_as_answered` | 6 | 5 |
| Non-answer classification, combined (insufficient_evidence + out_of_scope) | 8/14 = **57.1%** | 8/13 = **61.5%** |
| `answered_status_match_rate` | 1.0 (42/42) | 1.0 (42/42) — unchanged, 41 was never in this bucket |
| `judged_answer_count` / `grounded_count` | 48 / 12 | 47 / 11 |
| `estimated_cost_usd` (this evaluation's own reported total) | $4.51071 | $4.467164 |

**Both the 57.1%/8-14 and 61.5%/8-13 figures are reported side by side in
the Generation evaluation report, not just the higher one** — the
disclosure this decision itself recommends applying.

**The excluded question's real Bedrock cost is not erased from the
project's actual spend.** The Work report's "AWS use" section reports
every real dollar spent regardless of what any evaluation report later
excludes from its own metrics — the ~$0.0436 difference between the two
`estimated_cost_usd` figures above is disclosed there as a reconciling
item, not silently dropped.

## Disclosed incentive

This correction moves the headline non-answer-classification number up
(57.1% → 61.5%), and that direction was known before making the call, not
discovered afterward. The four points that support this decision being
made on its actual merits rather than to optimize the number are, in
order of strength: (1) the exclusion reason is structural — question 41
fits neither category cleanly, not "the model got it right so the label
must be wrong"; (2) question 44, the case structurally closest to 41 and
carrying the same score-improving temptation, was reviewed under the same
criterion and kept as `insufficient_evidence`, with the specific legal
distinction (treatment-effect vs. customer-satisfaction claims) recorded
above; (3) this section states the direction and magnitude of the effect
plainly, before any reader has to go looking for it; (4) the Generation
evaluation report states both the 14-question and 13-question denominators
side by side, so a reader who distrusts this decision can still read the
un-adjusted number directly.

## Storage

`reports/eval/retrieval_test_set.json` (question 41 removed),
`reports/eval/generation_evaluation_results.json` and `reports/eval/
retrieval_evaluation_results.json` (recomputed/pruned, no pipeline
re-run), `scripts/evaluate_generation.py` and `scripts/evaluate_retrieval.py`
(`assert len(data) == 55`, was 56).
