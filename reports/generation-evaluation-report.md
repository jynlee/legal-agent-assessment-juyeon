# Generation Evaluation Report

Date: 2026-08-14
Covers: SUBMISSION.md's "Generation evaluation report" requirements —
grounding, citation integrity, unsupported citation/hallucination,
insufficient-evidence refusal, out-of-scope refusal, latency, token use, and
cost — with deterministic retrieval measurement kept separate (see the
[Retrieval evaluation report](retrieval-evaluation-report.md)) from the
necessarily stochastic generation measurements below.

All numbers are from a real, full-pipeline run of `LegalAgent.answer_sync`
(retrieval + real Bedrock generation) against all 56 questions in
`reports/eval/retrieval_test_set.json` (`reports/eval/
generation_evaluation_results.json`). Method is fixed by
`reports/decisions/2026-08-14-generation-evaluation-design.md`.

**2026-08-18 update.** The test set grew from 50 to 56 questions, and 2 of
the original 5 `insufficient_evidence` questions (ids 43, 54) were found
to have incorrect gold labels on real re-verification — both are directly
resolved by a real statute provision the original construction pass's
search terms missed — and were relabelled `answered`. All numbers below
are from the real re-run against the corrected 56-question set. See
"insufficient_evidence refusal accuracy" below for the full story and why
it changes this report's central finding.

**2026-08-18, second update (same day).** Two real fixes landed after the
update above: a retrieval fusion-weight fix (Retrieval evaluation report's
"Fusion weighting") and a JSON-parsing robustness fix for a real crash hit
mid-re-verification (Work report's Blocker log item 13). Every number below
is from the real re-run made after both fixes. Net effect versus the first
2026-08-18 update: `answered_status_match_rate` 0.9524→0.9762,
`false_refusal_count` 2→1 (now just id 8), grounding mix shifted slightly
(`grounded` 16→14, `partially_grounded` 28→31) as expected from a real
retrieval change altering which chunks generation sees;
`insufficient_evidence_refusal_accuracy` is unchanged at 0.5556 — the
over-answering root cause (see below) is independent of retrieval quality.

**2026-08-18, third update (same day).** A semantic reranking stage was
added to retrieval (Retrieval evaluation report's "Reranking"), raising
Recall@10 further (0.5714→0.5952). Every number below is from the real
re-run made after reranking, and after a real regression it introduced
(every `out_of_scope` question started failing; found, root-caused, and
fixed via TDD before this run) was fixed. This update's net effect is
mixed, not uniformly positive, and is reported as such:
`answered_status_match_rate` reached a perfect 1.0 and `false_refusal_count`
dropped to 0, but `insufficient_evidence_refusal_accuracy` *fell* from
0.5556 to **0.3333** and `insufficient_evidence_misclassified_as_answered`
*rose* from 4 to **6** — reranking, by successfully surfacing more
topically-relevant candidates from a wider pool, appears to have handed the
model *more* plausible-but-not-dispositive evidence for exactly the
insufficient_evidence questions where this project's already-documented
over-answering bug (see "insufficient_evidence refusal accuracy" below)
gets triggered, making that specific weakness worse rather than better.
This was not the intended effect and is disclosed plainly rather than
buried under the improved headline numbers.

## Methodology, restated briefly

Every one of the 56 questions runs through the real, production
`LegalAgent.answer_sync` once — the same method
`scripts/serve_legal_agent.py` uses for one real question, run here over
all 56, making no separate evaluation-only pipeline. For every response
that comes back `answered`, a second real Bedrock call (the same fixed
Sonnet model, `legal_agent_assessment.judge`) classifies whether the
answer's actual prose content is supported by its own cited excerpts:
`grounded` / `partially_grounded` / `unsupported`. Refusal accuracy is a
direct comparison of each question's real `status` against the test set's
`expected_status` field. One real run per question, not repeated trials —
see "Reproducibility" below for why, and for what running it twice in
practice showed.

## Grounding

Of the 48 responses that came back `answered` (all 42
`expected_status: "answered"` questions, since `false_refusal_count` is now
0 — see "False refusals" below — plus 6 questions expected
`insufficient_evidence` that were over-answered instead — see
"insufficient_evidence refusal accuracy" below), the judge classified:

| Verdict | Count | Share of judged answers |
| --- | --- | --- |
| `grounded` | 12 | 25.0% |
| `partially_grounded` | 36 | 75.0% |
| `unsupported` | 0 | 0.0% |
| `judge_parse_error` | 0 | — |

**Zero `unsupported` answers** — the judge never classified an answer as
making claims the cited excerpts do not support at all, across all three
real runs so far. But
**`partially_grounded` is the large majority (75.0%), not the exception** —
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
included since it comes free from data already collected). These 10
`domain` labels are a reporting split, not 10 separate statutes -- the
corpus's actual governing law is 8 statutes; `미용법` and `무면허의료행위`
are topical subsets of 공중위생관리법 and 의료법 respectively. See the
[Retrieval evaluation report](retrieval-evaluation-report.md)'s
"Composition" section for the full statute list and how the split was
confirmed:

| Domain | grounded | partially_grounded | unsupported | n |
| --- | --- | --- | --- | --- |
| 공중위생법 | 3 | 2 | 0 | 5 |
| 미용법 | 3 | 2 | 0 | 5 |
| 안마사법 | 3 | 2 | 0 | 5 |
| 의료법 | 1 | 3 | 0 | 4 |
| 약사법 | 1 | 4 | 0 | 5 |
| 표시광고법 | 1 | 5 | 0 | 6 |
| 개인정보보호법 | 0 | 4 | 0 | 4 |
| 무면허의료행위 | 0 | 4 | 0 | 4 |
| 의료기기법 | 0 | 5 | 0 | 5 |
| 화장품법 | 0 | 5 | 0 | 5 |

No domain has every answer fully `grounded` this run; four domains
(개인정보보호법, 무면허의료행위, 의료기기법, 화장품법) had zero fully
`grounded` answers — every one of their answered questions drew at least
one judge-flagged overreach. This is the *third* different zero-grounded
domain set across this project's real, officially-reported full runs (an
earlier 4-domain set: 의료법, 표시광고법, 화장품법, 개인정보보호법; then a
3-domain set: 의료기기법, 화장품법, 개인정보보호법; now this run's
4-domain set) — consistent with this section's own point that per-domain
grounding is disclosed as each run's real result, not asserted as a stable
property without a larger sample (see "future work" below). 화장품법,
의료기기법, and 개인정보보호법 now appear as zero-grounded across all
three reported runs; 무면허의료행위 newly joins this run, while 표시광고법
and 의료법 (zero-grounded in the earlier runs) each now have exactly 1
fully-grounded answer — consistent with sampling noise on a 4-6-
question-per-domain sample rather than a stable domain-specific defect,
though the 3-domain persistence (화장품법/의료기기법/개인정보보호법) across
every run so far is worth treating as a real signal, not purely noise, if
a larger sample becomes available. 공중위생법's own count includes id 53
(the insufficient_evidence question this domain over-answered — judged
`grounded` even though the status itself was wrong, since the judge only
checks whether prose matches citations, not whether refusal was the
correct status). This is disclosed as a real, domain-correlated pattern in
this run, not investigated further here (a larger sample per domain, or a
second judge pass, would be needed to say whether it is a stable
per-domain property or this run's noise — named as future work below).

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
fabricating one. Across all 56 real calls this run, **`limitations_fired_count:
0`** — the guard never had to intervene on a *partial* fabrication (some
cited ids real, some not).

**Gap found during an earlier evaluation's final code review, closed on
2026-08-18.** `agent.py` used to have a second, separate fabricated-citation
path this metric could not see: if the model claimed `status: "answered"`
but *none* of its cited ids were actually retrieved (total fabrication,
not partial), the response downgraded to a bare `insufficient_evidence`
with an *empty* `limitations` field — indistinguishable from the model
honestly saying "I don't have enough evidence." Fixed by extending the
same `limitations`-surfacing pattern already used for partial fabrication
to this total-fabrication path too, so the two cases are now
distinguishable in the response itself: an honest refusal (the model's
own `status` was already `insufficient_evidence`) always carries an empty
`limitations`; a caught total-fabrication attempt (`status: "answered"`
downgraded because zero cited ids were real) always carries exactly one
`limitations` entry naming what was claimed.

**This closed a real, previously-disclosed unknown, not just a
hypothetical one.** Questions 11 and 22 (see "False refusals" below) both
came back `insufficient_evidence` with `citation_count: 0` in every real
run of this evaluation, including this one, and the fix now makes their
nature provable rather than merely likely: both have `limitations_count:
0` in this run's committed data — **honest refusals, not caught
fabrication attempts.** `limitations_fired_count: 0` across all 56
questions confirms no total-fabrication case occurred anywhere in this
run either. The retrieval-evaluation-informed guess in the prior version
of this report (that the honest-refusal reading was "more likely") is
now a measured fact rather than an inference.

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

**0.3333 (3 of 9 correct) after reranking, worse than 0.5556 before it.**
The category grew from 5 to 9 questions on 2026-08-18 (see the Retrieval
evaluation report's "Composition" and "Test-query sources and construction
method" for the 6 new questions' construction and domain-coverage
rationale) and 2 of the original 5 (ids 43, 54) were found to be
mislabelled and moved out of this category — see "Two gold-label errors
found and corrected" below before reading this number as a trend against
the original 0.4. The table below is the current, post-reranking run; see
"Reranking made this worse, not better" at the end of this section for the
pre-reranking comparison (0.5556, 5/9) and why.

| id | domain | question | actual status | correct? |
| --- | --- | --- | --- | --- |
| 41 | 표시광고법 | "피부 노화가 되돌아간다"고 광고해도 되나요? | `answered` | ❌ |
| 42 | 화장품법 | "식약처 인증 성분 사용" 문구를 써도 되나요? | `answered` | ❌ |
| 44 | 표시광고법 | "100% 만족 보장" 문구를 붙여도 되나요? | `answered` | ❌ |
| 45 | 표시광고법 | "피부과 전문의가 추천"했다고 광고해도 되나요? | `insufficient_evidence` | ✅ |
| 51 | 무면허의료행위 | 왁싱으로 제모해도 무면허의료행위인가요? | `insufficient_evidence` | ✅ |
| 52 | 무면허의료행위 | 바늘 없는 속눈썹 펌도 무면허의료행위인가요? | `insufficient_evidence` | ✅ |
| 53 | 공중위생법 | 개인 유튜브 촬영을 위한 출장 시술도 되나요? | `answered` | ❌ |
| 55 | 안마사법 | 무자격 직원의 발마사지 시술도 되나요? | `answered` | ❌ |
| 56 | 약사법 | SNS 체험단 무상 증정도 '판매'로 규제받나요? | `answered` | ❌ |

**Two gold-label errors found and corrected, disclosed in full rather than
quietly fixed.** Ids 43 and 54 were originally built into this test set
(43 on 8/13, 54 earlier on 8/18) as `insufficient_evidence` questions and
both were among the "misclassified" failures this report first recorded.
Root-causing those failures — reading the model's actual cited sources
line by line, not just the aggregate number — surfaced that both were
wrong: id 43's question ("의료기기 수준의 효과가 있다고 홍보해도
되나요?") is directly and almost verbatim resolved by 의료기기법 제26조
제7항 ("누구든지 의료기기가 아닌 것의... 의료기기와 유사한 성능이나 효능
및 효과 등이 있는 것으로 잘못 인식될 우려가 있는... 광고를 하여서는 아니
된다"); id 54's question (면허 대여) is directly resolved by
공중위생관리법 제6조 제3항 ("면허증을... 빌려주어서는 아니 되고...
빌려서는 아니 된다"). Both provisions exist in the corpus and were missed
by the original construction/verification search terms (a lexical search
for "대여" does not match "빌려주다/빌리다," a related but different
Korean verb). Both were relabelled `answered` with the real resolving
chunk as their required positive, and both were then re-checked in a real
generation run: the model answered both correctly with real, relevant
citations. This is the same standard this project has applied to itself
throughout (see the Work report's blocker log) — a bad gold label is a
defect in the evaluation, not a defect in the model, and treating the two
differently is exactly the discipline "measure, don't assume" requires.

**The failure mode, on the 6 confirmed-genuine failures (41, 42, 44, 53,
55, 56) after reranking (was 4: 42, 44, 53, 55, before it).** All 6
questions retrieved real, reranker-selected candidates — not a retrieval
gap, and the reranker did its own job correctly (selecting genuinely
topical candidates). The mechanism is the same one already identified
before reranking existed: several reason by analogy from a real but
not-dispositive source (a general prohibition, a related precedent about a
different specific phrase or service), and id 53 remains the clearest
direct evidence of it: the model's own answer text states **"'방송 등의
촬영'이 개인 유튜브 채널 촬영을 포함하는지 여부는 제공된 자료만으로는
명확히 판단하기 어렵습니다... 불분명합니다"** — the model explicitly
recognizes the gap in its own reasoning — and then still returns `status:
"answered"` anyway. This means the failure is not primarily that the model
fails to notice insufficient evidence; id 53 shows it can notice and say
so in prose. The failure is a **disconnect between the model's own stated
uncertainty and its final status decision**.
`insufficient_evidence_misclassified_as_answered: 6` in the committed
aggregate records the confirmed count.

**Separately, `insufficient_evidence_misclassified_as_out_of_scope: 0`.**
This is the deferred risk from item 7/8's final review (the concern that
the `out_of_scope` prompt instruction, having no explicit domain list,
might misclassify a genuinely in-scope-but-unanswerable question as
`out_of_scope` instead). This evaluation is the first real, empirical
check of that risk, and it did not materialize — confirmed identically
across four independent real runs now (the original `fd810f1`/`ff85ab8`
runs, the 2026-08-18 fusion-weight-fix run, and this reranking run against
a larger and corrected question set). No prompt change is needed for that
specific risk.

**Three revisions were tried and reverted, using three different
mechanisms.** `prompt-v3` added an explicit anti-analogy instruction; a
real re-run showed `insufficient_evidence_misclassified_as_answered`
improve from 3 to 2 but `false_refusal_count` worsen from 2 to 8 (net
status errors 5→10). `prompt-v4` replaced that with a contrastive worked
example in an unrelated hypothetical domain; no improvement on the target
metric (stayed at 3), `false_refusal_count` 2→6. **Caveat on v3/v4:** both
were measured against the original 5-question `insufficient_evidence`
set, which included the 2 now-corrected mislabels (43, 54) — their "3
misclassified" baseline was partly inflated by bad labels, not purely
model error; neither was rerun against the corrected set, so their exact
counts should be read against the uncorrected baseline, not the current
one.

`prompt-v5` (2026-08-18, against the corrected 9-question set, so its
counts are directly comparable to this report's other numbers) tried a
structural mechanism instead of a wording change: an explicit
`source_directly_resolves: true | false` field the model must commit to
before `status`, with `parse_answer_response` overriding `status` to
`insufficient_evidence` whenever that field is not `true` — regardless of
what `status` itself claimed. This directly targeted id 53's disconnect
between stated reasoning and final status. Its first real run crashed
instead of completing: on id 53 itself, the model emitted one complete
JSON object (`source_directly_resolves: false`, correctly refusing), then
"Wait, let me reconsider...", then a second, contradictory JSON object
(`source_directly_resolves: true`, answering) — `json.loads` raised on the
trailing content and the run stopped at question 53 of 56. Fixed two ways
before retrying: `parse_answer_response` now parses only the first JSON
value in the text (`json.JSONDecoder.raw_decode`) rather than raising on
trailing content, and the prompt's closing instruction was strengthened to
explicitly forbid "reasoning, commentary, reconsideration" after the JSON
object. The repaired v5 completed a full real run:
`insufficient_evidence_misclassified_as_answered` stayed at 4 (no
improvement — id 53 itself was answered incorrectly again, this time
without crashing) and `false_refusal_count` rose to 6. Reverted against
the same pre-registered bar as v3/v4; `prompt-v2` remains in production.

**Conclusion after three independent attempts.** A blanket instruction, a
contrastive example, and a structural code-checked field are three
meaningfully different mechanisms, and all three produced the same
trade-off: any intervention that reduces over-answering increases false
refusals by more than it fixes, with no net improvement. This is read as
evidence that the fix this specific failure mode needs is not at the
prompt-wording or response-schema level at all — three attempts is enough
to stop, per this project's own "measure, don't assume" discipline, rather
than iterate a fourth variation on the same mechanism class. A genuinely
different category of fix (see the Work report's "What one additional
week would allow") would need to stop asking the same generation call to
both answer and self-certify; the existing `judge.py` post-hoc grounding
check already demonstrates this project's own pattern for that: a
separate, narrowly-scoped Bedrock call, in its own context, asked only
whether a specific source resolves a specific question — not bundled into
the same call already committed to producing an answer.

**Reranking made this worse, not better (2026-08-18, same day as the three
attempts above).** A semantic reranking stage (Retrieval evaluation
report's "Reranking") was added afterward for a different reason entirely
-- raising Recall@10 -- and was not intended to touch this failure mode at
all. Before reranking:
`insufficient_evidence_refusal_accuracy` was 0.5556 (5/9),
`insufficient_evidence_misclassified_as_answered` was 4 (ids 42, 44, 53,
55). After: 0.3333 (3/9), misclassified count 6 (ids 41, 42, 44, 53, 55,
56) -- two new failures (41, 56) that were answered correctly before. This
is read as the over-answering mechanism being fed by a wider net, not a
new mechanism: reranking's whole design pulls in more genuinely
*topically*-relevant candidates from a widened top-25 pool instead of the
old top-10, which is exactly more raw material for "reason by analogy from
a real but not-dispositive source" to work with. This was not anticipated
before implementing reranking and is disclosed here rather than only in
the top-of-report update block, since a reader focused specifically on
this failure mode needs the connection made explicit: **the fourth attempt
this project made at fixing over-answering (reranking, aimed at a
different problem) made it measurably worse, joining the first three
(v3/v4/v5) as evidence this failure mode needs the judge.py-style
separate-call fix named above, not further changes to what generation
retrieves.**

## False refusals

Not part of SUBMISSION.md's named bullet list, but visible as a byproduct
of running all 56 questions and reported here because it is a real,
non-obvious finding. **2026-08-18 update, after reranking:**
`false_refusal_count: 0` — every one of the 42 answerable questions is now
correctly answered, improved from 1 (id 8) after the fusion-weight/
JSON-parsing fixes and 2 before those. Unlike the insufficient_evidence
regression above, reranking helped this specific metric: a wider,
reranked candidate pool means fewer answerable questions land with weak or
borderline retrieval support, so generation has less reason to
under-refuse. No table is shown here since there is nothing left to list.

## out_of_scope refusal accuracy

**1.0 (5 of 5 correct)**, confirmed on this real run after a real
regression was caught and fixed the same day. Reranking's first real
56-question run scored **0.0 (0 of 5)** — every out_of_scope question
failed. Root cause (full story in the Retrieval evaluation report's
"Reranking"): the implementation returned `INSUFFICIENT_EVIDENCE` directly
whenever the reranker selected zero candidates, which skipped the real
generation call entirely for every out_of_scope question (the reranker
correctly finds nothing relevant for an off-topic question, since nothing
retrieved *is* relevant) — but out_of_scope classification is that
generation call's own judgment on the question itself, independent of
retrieval, and skipping the call meant the model was never asked. Fixed
via TDD, confirmed by this real re-run: all 5 non-legal/meta questions
(ids 46-50) correctly returned `out_of_scope` again, with no false
positives among the answerable or insufficient_evidence questions either
(`insufficient_evidence_misclassified_as_out_of_scope: 0`, and no
answerable question returned `out_of_scope` in this run's data). Included
here rather than only in the Retrieval evaluation report because this
metric is this report's own named bullet, and a reader checking only this
report for out_of_scope accuracy should not have to cross-reference to
learn it briefly regressed to zero.

## Latency

Wall-clock, per question, this run (retrieval + generation, and the judge
call where one happened — the judge call is not part of the deliverable's
own response latency, but this evaluation's per-question `latency_ms` is
measured around the whole loop iteration including it, so the two
`answered`-path numbers below are judge-inclusive):

**After reranking** (adds a real Bedrock round-trip to every question,
refusal or not, unlike before):

| | n | min | median | max |
| --- | --- | --- | --- | --- |
| All 56 questions | 56 | 2,661.1 ms | 18,811.4 ms | 32,684.0 ms |
| `answered` only | 48 | 8,164.5 ms | 19,567.2 ms | 32,684.0 ms |
| Refusal (`insufficient_evidence`/`out_of_scope`) | 8 | 2,661.1 ms | 3,074.6 ms | 5,325.6 ms |

| Percentile (all 56) | Latency |
| --- | --- |
| p50 | 18,811.4 ms |
| p95 | 25,509.5 ms |
| p99 | 26,553.7 ms |

Median latency for a refusal rose from ~1.4-1.9s (before reranking) to
~3.1s — still fast, but no longer near-instant, since even a refusal now
makes a real rerank call before generation can decide there is nothing to
answer from. `answered` responses rose from a median ~14.5s to ~19.6s,
still dominated by the judge call stacked on top of generation, now with
the rerank call added before both. The deliverable's own single-call
latency (generation only, no judge) is not separately isolated in this
run's instrumentation and would need a small follow-up measurement to
report precisely.

## Token use and cost

Self-instrumented, per SUBMISSION.md's requirement (contributors share one
IAM user; billing/CloudTrail cannot attribute usage, so every real call in
this evaluation is recorded from `LegalAgent.answer_sync`'s own `on_usage`
callback and the judge call's real Bedrock response, the moment each call
returns — not reconstructed afterward).

| | Value |
| --- | --- |
| Embed tokens (estimated, query embedding only) | 2,148 |
| Generation input tokens (real, rerank + answer + judge calls) | 1,273,104 |
| Generation output tokens (real, rerank + answer + judge calls) | 46,076 |
| **Estimated cost** | **$4.51071** |
| Wall-clock elapsed (full 56-question run) | 968.04 s (~16.1 min) |

Numbers above are from the 2026-08-18 run made after reranking (Retrieval
evaluation report's "Reranking") and its out_of_scope regression fix (Work
report's Blocker log). Cost more than doubled versus the pre-reranking run
($2.032707 → $4.51071) and wall-clock time grew ~35% (714.53s → 968.04s) —
the rerank call's own prompt is large (full candidate excerpts, up to 25
per question), a real and permanent cost/latency increase for every future
real query, not a one-time evaluation expense. A discarded first attempt
at this run (before the out_of_scope fix) cost a real, separately-disclosed
$4.574664 producing numbers that were never reported as final — see the
Work report's "AWS use." An earlier crashed attempt (the JSON-parsing bug,
before reranking existed) cost a real, separately-disclosed $0.395997
before failing — also in "AWS use."

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

**2026-08-18 addendum.** The above compares two runs against the original
50-question set, before the fusion-weight fix. The current committed run
(after the fusion-weight and JSON-parsing fixes, against the now-56-question
set) has a *different* mismatch set — false refusal: id 8 only (was 11, 22);
misclassified as answered: ids 42, 44, 53, 55 (was 42, 43, 44; 43 was
separately relabelled `answered` on 2026-08-18, so it can no longer appear
in this category by construction). This is expected, not a regression: a
real retrieval change shifts which questions have full retrieval success in
the first place, which is a precondition for either failure mode, so the
specific ids composing a 4-5-question mismatch set are not expected to stay
fixed across a real pipeline change — the aggregate counts (misclassified
count still 4; false refusals improved 2→1) are the load-bearing numbers,
not id-level identity.

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

`reports/eval/generation_evaluation_results.json` (committed) —
full per-question results including answer text, citations, grounding
verdict and justification, and token/latency figures for all 56 questions.
Real per-run usage logs (gitignored, per this project's shared-IAM
instrumentation convention) are in `reports/usage/`. Rerun with:

```
OPENSEARCH_URL=http://localhost:9200 \
uv run python scripts/evaluate_generation.py --contributor <your-contributor-id>
```

against a rebuilt index (see the Retrieval evaluation report's index-build
instructions) — this is a real-cost script (~$2.06 per full run), not
exercised by the automated test suite, matching `scripts/evaluate_retrieval.py`'s
own convention.
