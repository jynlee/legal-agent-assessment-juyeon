# Generation Evaluation Report

Date: 2026-08-14
Covers: SUBMISSION.md's "Generation evaluation report" requirements —
grounding, citation integrity, unsupported citation/hallucination,
insufficient-evidence refusal, out-of-scope refusal, latency, token use, and
cost — with deterministic retrieval measurement kept separate (see the
[Retrieval evaluation report](retrieval-evaluation-report.md)) from the
necessarily stochastic generation measurements below.

All numbers are from a real, full-pipeline run of `LegalAgent.answer_sync`
(retrieval + real Bedrock generation) against all 55 questions in
`reports/eval/retrieval_test_set.json` (`reports/eval/
generation_evaluation_results.json`). Method is fixed by
`reports/decisions/2026-08-14-generation-evaluation-design.md`.

**2026-08-18 update.** The test set grew from 50 to 56 questions, and 2 of
the original 5 `insufficient_evidence` questions (ids 43, 54) were found
to have incorrect gold labels on real re-verification — both are directly
resolved by a real statute provision the original construction pass's
search terms missed — and were relabelled `answered`.

**2026-08-18, second update (same day).** Two real fixes landed after the
update above: a retrieval fusion-weight fix (Retrieval evaluation report's
"Fusion weighting") and a JSON-parsing robustness fix for a real crash hit
mid-re-verification (Work report's Blocker log item 13). Versus the first
2026-08-18 update: `answered_status_match_rate` 0.9524→0.9762,
`false_refusal_count` 2→1 (now just id 8), grounding mix shifted slightly
as expected from a real retrieval change altering which chunks generation
sees; `insufficient_evidence_refusal_accuracy` unchanged at 0.5556 — the
over-answering root cause (see below) is independent of retrieval quality.
**This is the state every number below now reflects again**, after the
reranking stage described in the next two updates was added, evaluated,
and reverted.

**2026-08-18, third update (same day) — semantic reranking added.** A
reranking stage (Retrieval evaluation report's "Reranking") was added on
top of the fusion-weight fix, raising Recall@10 further (0.5714→0.5952).
Its net effect was mixed: `answered_status_match_rate` reached a perfect
1.0 and `false_refusal_count` dropped to 0, but
`insufficient_evidence_refusal_accuracy` *fell* from 0.5556 to 0.3333 and
`insufficient_evidence_misclassified_as_answered` *rose* from 4 to 6 —
reranking, by successfully surfacing more topically-relevant candidates
from a wider pool, handed the model *more* plausible-but-not-dispositive
evidence for exactly the questions where this project's over-answering
weakness gets triggered, making that specific weakness worse.

**2026-08-19 — two mechanisms piloted to fix the over-answering weakness
directly, both failed** (full account preserved below, "insufficient_evidence
refusal accuracy" → "Mechanisms tried and reverted"): a lenient and a
strict variant of a separate self-verification Bedrock call (`verify.py`,
never committed) caught 0 of 6 and 1 of 6 known failures respectively.

**2026-08-19 — question 41 invalidated, not relabelled.** Reviewing those
6 failures' cited sources by hand (the same standard already applied to
ids 43/54) found question 41 was an invalid `insufficient_evidence`
example — its cited source states a general principle that resolves the
claim on its face, not by analogy like the other 5. Removed from the test
set entirely (56 → 55 questions; `insufficient_evidence`: 9 → 8), not
relabelled — full reasoning in
`reports/decisions/2026-08-19-question-41-invalidation.md`.

**2026-08-19, fourth update — reranking reverted.** With both direct fixes
for the over-answering weakness having failed, and the weakness's own
history tracing straight back to reranking's side effect, reranking itself
was reconsidered against the one lever with *already-measured, zero-cost*
evidence: removing it. Recall@10 gives up 2.38 points (59.52%→57.14%) and
`false_refusal_count` goes back to 1 (id 8), but
`insufficient_evidence_refusal_accuracy` recovers from 37.5% to **50.0%**
and the combined non-answer-classification figure
(`insufficient_evidence` + `out_of_scope`) recovers from 61.5% to **69.2%**
— judged the better trade for this project's stated mission (an honest
"I don't have enough evidence" is a materially smaller failure than a
confident, plausible-sounding wrong answer). `rerank.py` and its wiring
into `agent.py` were reverted (`src/legal_agent_assessment/rerank.py`
deleted); every number below is the real, already-measured pre-reranking
run (2026-08-18, second update, above) with question 41 excluded, not a
new pipeline run. Full reasoning:
`reports/decisions/2026-08-19-revert-reranking.md`.

**2026-08-19, fifth update (same day) — self-consistency voting tried and
cleanly ruled out.** A seventh mechanism, structurally different from the
first six (statistical instability across repeated sampling, rather than
another self-judgment call), was piloted: the real pipeline run three
times per question over the 8 `insufficient_evidence` questions plus a
10-question control sample. Result: **zero disagreement across all 18
questions' 3 runs each** — the same 4 known failures came back `answered`
every time, with no exceptions. This is a clean negative result, not an
inconclusive one: it rules out sampling instability as the mechanism,
and is read as further evidence of a systematic bias rather than
model uncertainty. Real cost: $1.282819 (54 real calls). No numbers below
changed — this did not touch production code. Full account:
"insufficient_evidence refusal accuracy" below, "A seventh attempt."

## Methodology, restated briefly

Every one of the 55 questions runs through the real, production
`LegalAgent.answer_sync` once — the same method
`scripts/serve_legal_agent.py` uses for one real question, run here over
all 55, making no separate evaluation-only pipeline. For every response
that comes back `answered`, a second real Bedrock call (the same fixed
Sonnet model, `legal_agent_assessment.judge`) classifies whether the
answer's actual prose content is supported by its own cited excerpts:
`grounded` / `partially_grounded` / `unsupported`. Refusal accuracy is a
direct comparison of each question's real `status` against the test set's
`expected_status` field. One real run per question, not repeated trials —
see "Reproducibility" below for why, and for what running it twice in
practice showed.

## Grounding

Of the 45 responses that came back `answered` (41 of the 42
`expected_status: "answered"` questions — see "False refusals" below for
the one exception, id 8 — plus 4 questions expected `insufficient_evidence`
that were over-answered instead — see "insufficient_evidence refusal
accuracy" below), the judge classified:

| Verdict | Count | Share of judged answers |
| --- | --- | --- |
| `grounded` | 14 | 31.1% |
| `partially_grounded` | 31 | 68.9% |
| `unsupported` | 0 | 0.0% |
| `judge_parse_error` | 0 | — |

**Zero `unsupported` answers** — the judge never classified an answer as
making claims the cited excerpts do not support at all, across every real
run of this evaluation. But **`partially_grounded` is still the large
majority (68.9%), not the exception** — this is disclosed as the headline
finding here, not smoothed over by the absence of outright `unsupported`
verdicts. Reading the judge's justification text for the
`partially_grounded` cases shows a consistent pattern: not fabrication,
but overreach on a specific sub-claim inside an otherwise well-supported
answer. Two real examples:

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
| 의료법 | 2 | 1 | 0 | 3 |
| 약사법 | 2 | 2 | 0 | 4 |
| 표시광고법 | 1 | 4 | 0 | 5 |
| 개인정보보호법 | 0 | 4 | 0 | 4 |
| 무면허의료행위 | 0 | 4 | 0 | 4 |
| 의료기기법 | 0 | 5 | 0 | 5 |
| 화장품법 | 0 | 5 | 0 | 5 |

No domain has every answer fully `grounded` this run; four domains
(개인정보보호법, 무면허의료행위, 의료기기법, 화장품법) had zero fully
`grounded` answers — every one of their answered questions drew at least
one judge-flagged overreach. This is disclosed as this run's real result,
not asserted as a stable per-domain property without a larger sample (see
"future work" below) — the specific zero-grounded set has shifted across
this project's earlier reported runs too, consistent with sampling noise
on a 3-5-question-per-domain sample. 공중위생법's own count includes id 53
(the insufficient_evidence question this domain over-answered — judged
`grounded` even though the status itself was wrong, since the judge only
checks whether prose matches citations, not whether refusal was the
correct status).

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
fabricating one. Across all 55 real calls this run, **`limitations_fired_count:
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
run of this evaluation, and the fix makes their nature provable rather
than merely likely: both have `limitations_count: 0` in this run's
committed data — **honest refusals, not caught fabrication attempts.**
`limitations_fired_count: 0` across all 55 questions confirms no
total-fabrication case occurred anywhere in this run either.

## Unsupported citation / hallucination

Read together with "Grounding" above: **zero answers were classified
`unsupported`** — the judge never found an answer making a claim the cited
excerpts do not support at all. The 31 `partially_grounded` answers are
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

**0.5 (4 of 8 correct) after reranking was reverted and question 41 was
invalidated — the best measured value across this project's real runs.**
The category grew from 5 to 9 questions on 2026-08-18 (see the Retrieval
evaluation report's "Composition" and "Test-query sources and construction
method" for the 6 new questions' construction and domain-coverage
rationale), 2 of the original 5 (ids 43, 54) were found to be mislabelled
and moved out of this category on 2026-08-18 (see "Two gold-label errors
found and corrected" below), and 1 of the 6 new questions (id 41) was
found to be an invalid example and removed from the test set entirely on
2026-08-19 (see "A test-set construction defect: question 41" below) — the
category now holds 8 questions.

| id | domain | question | actual status | correct? |
| --- | --- | --- | --- | --- |
| 42 | 화장품법 | "식약처 인증 성분 사용" 문구를 써도 되나요? | `answered` | ❌ |
| 44 | 표시광고법 | "100% 만족 보장" 문구를 붙여도 되나요? | `answered` | ❌ |
| 45 | 표시광고법 | "피부과 전문의가 추천"했다고 광고해도 되나요? | `insufficient_evidence` | ✅ |
| 51 | 무면허의료행위 | 왁싱으로 제모해도 무면허의료행위인가요? | `insufficient_evidence` | ✅ |
| 52 | 무면허의료행위 | 바늘 없는 속눈썹 펌도 무면허의료행위인가요? | `insufficient_evidence` | ✅ |
| 53 | 공중위생법 | 개인 유튜브 촬영을 위한 출장 시술도 되나요? | `answered` | ❌ |
| 55 | 안마사법 | 무자격 직원의 발마사지 시술도 되나요? | `answered` | ❌ |
| 56 | 약사법 | SNS 체험단 무상 증정도 '판매'로 규제받나요? | `insufficient_evidence` | ✅ |

Note id 56: correctly refused in this (reranking-reverted) run, unlike the
reranking-era run reported earlier this same day — see "Mechanisms tried
and reverted" below for why reranking specifically flipped this one from
correct to incorrect.

**A test-set construction defect: question 41 invalidated, not relabelled
(2026-08-19).** Question 41 ("피부 노화가 되돌아간다"고 광고해도 되나요?")
was reviewed as part of reading all 6 then-confirmed failures' cited
sources line by line (below), the same standard already applied to ids
43/54. Unlike the other 5, its cited source
(`precedent-144207#summary-holding-001`) states a *general* principle —
unverified claims creating false medical expectations are prohibited —
that covers this specific claim on its face, not by analogical extension
to a different specific case the way the other 5 do. This makes it an
invalid `insufficient_evidence` example. It could not simply be
relabelled `answered` the way ids 43/54 were, because — unlike 43/54,
which were independently traced to a specific missed statute provision —
question 41 was never drafted from a specific source chunk
(`source_chunk_id: null` from construction). Assigning one now from what
the model itself cited would make its `Recall@10` contribution true by
construction, the same self-grading concern raised throughout this
section applied to the retrieval metric instead. With no valid category
left, it is removed from the test set entirely (56 → 55 questions). Full
reasoning, including the pre-registered review criterion applied
identically to all 6 cases and why question 44 — the case structurally
closest to 41, and carrying the same score-improving temptation — was
reviewed and *not* reclassified, is in
`reports/decisions/2026-08-19-question-41-invalidation.md`.

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

**The failure mode, on the 4 confirmed-genuine failures (42, 44, 53,
55).** Reading the model's own answer text for each: several reason by
analogy from a real but not-dispositive source (a general prohibition, a
related precedent about a different specific phrase or service), and id
53 remains the clearest direct evidence of it: the model's own answer text
states **"'방송 등의 촬영'이 개인 유튜브 채널 촬영을 포함하는지 여부는
제공된 자료만으로는 명확히 판단하기 어렵습니다... 불분명합니다"** — the
model explicitly recognizes the gap in its own reasoning — and then still
returns `status: "answered"` anyway. This means the failure is not
primarily that the model fails to notice insufficient evidence; id 53
shows it can notice and say so in prose. The failure is a **disconnect
between the model's own stated uncertainty and its final status
decision**. `insufficient_evidence_misclassified_as_answered: 4` in the
committed aggregate records the confirmed count.

**Separately, `insufficient_evidence_misclassified_as_out_of_scope: 0`.**
This is the deferred risk from item 7/8's final review (the concern that
the `out_of_scope` prompt instruction, having no explicit domain list,
might misclassify a genuinely in-scope-but-unanswerable question as
`out_of_scope` instead). This evaluation is the first real, empirical
check of that risk, and it did not materialize — confirmed identically
across every independent real run of this project (the original
`fd810f1`/`ff85ab8` runs, this fusion-weight-fix run, and the reranking
run that was later reverted). No prompt change is needed for that
specific risk.

**Mechanisms tried and reverted — seven independent attempts across five
mechanism classes, all before landing on the current state.**

`prompt-v3` added an explicit anti-analogy instruction; a real re-run
showed `insufficient_evidence_misclassified_as_answered` improve from 3 to
2 but `false_refusal_count` worsen from 2 to 8 (net status errors 5→10).
`prompt-v4` replaced that with a contrastive worked example in an
unrelated hypothetical domain; no improvement on the target metric
(stayed at 3), `false_refusal_count` 2→6. **Caveat on v3/v4:** both were
measured against the original 5-question `insufficient_evidence` set,
which included the 2 now-corrected mislabels (43, 54) — their "3
misclassified" baseline was partly inflated by bad labels, not purely
model error.

`prompt-v5` (2026-08-18, against the corrected 9-question set) tried a
structural mechanism instead of a wording change: an explicit
`source_directly_resolves: true | false` field the model must commit to
before `status`, with `parse_answer_response` overriding `status` to
`insufficient_evidence` whenever that field is not `true`. This directly
targeted id 53's disconnect between stated reasoning and final status.
Its first real run crashed instead of completing: on id 53 itself, the
model emitted one complete JSON object (`source_directly_resolves: false`,
correctly refusing), then "Wait, let me reconsider...", then a second,
contradictory JSON object (`source_directly_resolves: true`, answering) —
`json.loads` raised on the trailing content and the run stopped mid-set.
Fixed two ways before retrying: `parse_answer_response` now parses only
the first JSON value in the text (`json.JSONDecoder.raw_decode`) rather
than raising on trailing content, and the prompt's closing instruction was
strengthened to explicitly forbid "reasoning, commentary, reconsideration"
after the JSON object. The repaired v5 completed a full real run:
`insufficient_evidence_misclassified_as_answered` stayed at 4 (no
improvement — id 53 itself was answered incorrectly again, this time
without crashing) and `false_refusal_count` rose to 6. Reverted against
the same pre-registered bar as v3/v4; `prompt-v2` remains in production.

**Conclusion after these three (in-call) attempts.** A blanket
instruction, a contrastive example, and a structural code-checked field
are three meaningfully different mechanisms, and all three produced the
same trade-off: any intervention that reduces over-answering increases
false refusals by more than it fixes. This pointed at a fix outside the
single generation call: a separate, narrowly-scoped Bedrock call, the same
pattern `judge.py` already uses for post-hoc grounding — asked only
whether a specific source resolves a specific question, not bundled into
the same call already committed to producing an answer.

**A fourth attempt (reranking, 2026-08-18) took a different approach to
the same idea and made things measurably worse, not better.** Reranking
was added for a different reason entirely -- raising Recall@10 -- but its
own real result mechanically fed the over-answering weakness a wider net
of plausible-but-not-dispositive material:
`insufficient_evidence_refusal_accuracy` fell from 0.5556 to 0.3333 (and,
after question 41's later invalidation, the pre/post-reranking comparison
on the corrected 8-question denominator is 0.5 vs. 0.375),
`insufficient_evidence_misclassified_as_answered` rose 4→5. This is read
as the over-answering mechanism being fed by a wider net, not a new
mechanism: reranking's whole design pulls in more genuinely
*topically*-relevant candidates from a widened top-25 pool instead of the
old top-10, which is exactly more raw material for "reason by analogy from
a real but not-dispositive source" to work with.

**A fifth and sixth attempt (2026-08-19) tested the judge.py-style
separate-call idea directly, and both failed too.** Two prompt variants
for a new `verify.py` module (never committed) were piloted against 16
already-saved answers -- no pipeline re-run, no production code change,
real Bedrock calls only against data already on disk:

- **v1** showed the verifier the model's own answer text and asked a
  lenient sufficiency question. Result: **0 of 6** known failures caught
  (against the 6 confirmed-genuine failures known at the time, before
  question 41's invalidation), 10 of 10 correct answers correctly kept.
  Every one of the 6 was "justified" by the verifier re-stating the
  original answer's own analogical reasoning as if it were sufficient
  evidence -- the verifier anchored on the answer it was shown rather than
  independently judging the sources.
- **v2** removed the answer text entirely and asked the verifier to decide
  sufficiency from the question and citations alone, explicitly instructed
  to flag a well-reasoned analogical extension as insufficient even when
  convincing. Result: **1 of 6** caught (id 44), 10 of 10 correct answers
  still correctly kept. One internal inconsistency was observed on id 53:
  the verifier's own justification text concluded "유추 적용이 필요하므로
  불충분하다" (analogical application is needed, therefore insufficient)
  while its structured `sufficient` field still returned `true` -- the
  same disconnect between stated reasoning and a committed decision this
  report already documented in the base model itself (id 53, above),
  reproducing on a second, independently-designed call.

Neither variant cleared the pre-registered bar (>=4 of 6 known failures
caught, without losing any of the 10 correct answers) set before running
either pilot. **Not adopted; no agent.py or contracts.py change was made.**
Total real cost across both pilots: $0.396321, 32 real Bedrock calls (see
Work report Blocker log item 17 and "AWS use").

**In hindsight, one data point in this pilot corroborates question 41's
later invalidation, independently.** Neither v1 nor v2 ever flagged
question 41 as insufficient (`sufficient: true` in both runs) — at the
time this read as 2 more misses for the verifier. After the 2026-08-19
human review found question 41's cited source genuinely does resolve it
on its face, this is better read the other way: the verifier was
*correct* both times, on a case that was not actually a failure to catch.
This evidence played no role in deciding to invalidate the question — it
is noted only because it is a real, independent data point that happens
to agree with that later, separately-reasoned conclusion.

**The revert (2026-08-19).** At this point in the day, six mechanisms
across four classes (in-call prompt/schema changes; a wider-net retrieval
change; a lenient separate-call check; a strict separate-call check) had
all either failed to improve `insufficient_evidence_refusal_accuracy`
without a larger false-refusal cost, or -- reranking's case -- actively
worsened it as an unintended side effect of a change made for a different
reason. Of these, reranking was the only one with a *known, reversible*
root cause and *already-measured* data for what reverting it would look
like -- no new real cost was needed to evaluate this option, unlike every
other mechanism tried. `insufficient_evidence_refusal_accuracy` recovering
from 0.375 to **0.5**, and the combined non-answer-classification figure
from 61.5% to **69.2%**, at the cost of Recall@10 (59.52%→57.14%) and
`false_refusal_count` (0→1), was judged the better trade for this
project's stated mission: an honest refusal is a materially smaller
failure than a confident, plausible-sounding wrong answer built on
evidence that does not actually decide the question. Full reasoning,
including why this was judged the better trade specifically (not just a
tie-breaker), is in
`reports/decisions/2026-08-19-revert-reranking.md`.

**A seventh attempt (2026-08-19, same day): self-consistency voting,
tested and cleanly ruled out.** Every prior attempt asked the model to
judge its own output, in one form or another. This one instead asked
whether the model's *decision itself* is unstable -- running the real
`LegalAgent.answer_sync` three times per question (real retrieval + real
generation, no code change) over the 8 `insufficient_evidence` questions
plus a 10-question correctly-answered control sample (one per domain,
same sampling design as the `verify.py` pilots), and checking whether
`status` ever disagreed across the three runs. If it had, an
instability-based gate (majority vote, or "any disagreement forces
`insufficient_evidence`") would have been a genuinely new mechanism class
-- a statistical signal rather than another self-judgment call. It did
not: **all 18 questions returned identical status on all 3 runs, with
zero exceptions** -- the same 4 known failures (42, 44, 53, 55) came back
`answered` every single time, and all 10 control questions came back
`answered` every single time. Majority vote therefore scores identically
to a single run (4/8 correct). This is read as evidence *against* the
instability hypothesis specifically, not an inconclusive result: the
model is not wavering on these questions in a way sampling can detect --
it reaches the same conclusion by the same route every time, which
argues for a systematic bias in how it weighs this specific class of
evidence, not sampling noise. Real cost: 54 real calls (18 questions ×
3), $1.282819 (see Work report Blocker log item 21 and "AWS use").

**What remains unresolved.** Even after the revert, 4 of 8
`insufficient_evidence` questions are still over-answered (50%, not
100%). The revert recovers the score reranking cost, but does not itself
fix the underlying mechanism -- **seven** real, independent attempts
across five mechanism classes (in-call prompt/schema changes; a
wider-net retrieval change; a lenient separate-call check; a strict
separate-call check; self-consistency sampling) have all failed, the last
one returning a clean, unambiguous null result rather than an inconclusive
one. See the Work report's "What one additional week would allow" for
what a genuinely different fix (a different, independently-verified model
identity, or a human-reviewed check) that this project's own two-week,
single-verified-model-id constraints ruled out attempting here would
require.

## False refusals

Not part of SUBMISSION.md's named bullet list, but visible as a byproduct
of running all 55 questions and reported here because it is a real,
non-obvious finding. **`false_refusal_count: 1`** — question 8 is the one
answerable question this run refuses.

**Checked directly, not assumed: this is a genuine generation-layer
failure, not a retrieval failure honestly reported.** The initial
hypothesis (checked 2026-08-19) was that question 8 might have `recall_at_10:
0` — retrieval never surfacing the gold chunk, making the refusal the
honest, correct response. The real, committed data says the opposite:
`retrieval_evaluation_results.json` records `recall_at_10: 1` for question
8 (the gold chunk `precedent-141548#summary-holding-000` ranked 8th, well
inside the top-10), and the same run's `generation_evaluation_results.json`
confirms `retrieval_hit_count: 10` — the model received a full set of 10
real candidates, including the one that actually resolves the question,
and still returned `status: insufficient_evidence` with `citation_count: 0`
rather than citing it. **This is the one case across this project's real
runs where the model refused despite having the evidence it needed** — the
opposite failure direction from the `insufficient_evidence` over-answering
weakness discussed at length above, and disclosed with the same rigor:
checking the hypothesis against real data changed the conclusion, and the
corrected conclusion — not the more flattering original guess — is what is
reported. Question 11 and 22 (also `citation_count: 0`,
`limitations_count: 0`) previously appeared in this bucket under different
retrieval conditions but are correctly answered in this run.

## out_of_scope refusal accuracy

**1.0 (5 of 5 correct)** — all 5 non-legal/meta questions (ids 46-50)
correctly returned `out_of_scope`, with no false positives among the
answerable or insufficient_evidence questions either
(`insufficient_evidence_misclassified_as_out_of_scope: 0`, and no
answerable question returned `out_of_scope` in this run's data). This
metric was briefly regressed to 0.0 during the reranking experiment (an
empty reranker selection short-circuited straight to
`INSUFFICIENT_EVIDENCE`, skipping the real generation call that alone
decides `out_of_scope`) — found, root-caused, and fixed via TDD before
that regression was ever reported as final; moot now that reranking itself
has been reverted, but the underlying lesson (out_of_scope classification
is generation's own judgment on the question, independent of what
retrieval found) remains a real, disclosed finding — full story in the
Retrieval evaluation report's "Reranking" (historical) section.

## Latency

Wall-clock, per question, this run (retrieval + generation, and the judge
call where one happened — the judge call is not part of the deliverable's
own response latency, but this evaluation's per-question `latency_ms` is
measured around the whole loop iteration including it, so the two
`answered`-path numbers below are judge-inclusive):

| | n | min | median | max |
| --- | --- | --- | --- | --- |
| All 55 questions | 55 | 1,388.4 ms | 14,375.0 ms | 22,344.7 ms |
| `answered` only | 45 | 7,917.2 ms | 15,179.4 ms | 22,344.7 ms |
| Refusal (`insufficient_evidence`/`out_of_scope`) | 10 | 1,388.4 ms | 1,803.8 ms | 2,493.9 ms |

**Recomputed 2026-08-19 from the real, already-stored per-question
`latency_ms` values** (question 41 excluded) — not a new pipeline run.
Reranking's own added round-trip (median refusal latency ~1.4-1.9s→~3.1s,
`answered` median ~14.5s→~19.6s while it was in production) no longer
applies now that `rerank.py` has been reverted: every number in this table
is real, measured time from the pre-reranking pipeline, which is what
production now runs. A p50/p95/p99 percentile breakdown is not reported
here (the exact interpolation method used for the reranking-era table was
not preserved in committed code, and this project's convention has been to
disclose that gap rather than guess at a method) — min/median/max above
are exact, direct computations from the committed per-question data.

## Token use and cost

Self-instrumented, per SUBMISSION.md's requirement (contributors share one
IAM user; billing/CloudTrail cannot attribute usage, so every real call in
this evaluation is recorded from `LegalAgent.answer_sync`'s own `on_usage`
callback and the judge call's real Bedrock response, the moment each call
returns — not reconstructed afterward).

| | Value |
| --- | --- |
| Embed tokens (estimated, query embedding only) | 2,115 |
| Generation input tokens (real, answer + judge calls) | 499,762 |
| Generation output tokens (real, answer + judge calls) | 35,016 |
| **Estimated cost** | **$2.02478** |

Numbers above are the real 2026-08-18 pre-reranking run (fusion-weight and
JSON-parsing fixes applied), recomputed 2026-08-19 with question 41
excluded from the already-stored per-question data — not a pipeline
re-run. This is the real, permanent cost this pipeline now runs at going
forward: reranking's own added cost (more than doubling this figure to
$4.467164, per its own now-historical measurement) no longer applies,
since `rerank.py` was reverted. Per-question token counts are recorded in
the committed results file (`reports/eval/generation_evaluation_results.json`,
`embed_estimated_tokens` / `generation_input_tokens` /
`generation_output_tokens` on every entry) — their sum reproduces the
aggregate exactly, a property checked directly against this run's data
before writing this report. Rates: Cohere Embed v4 $0.12/M tokens, Claude
Sonnet input $3.00/M tokens, output $15.00/M tokens (same rates as
`scripts/serve_legal_agent.py` and the index-build cost already reported
in the Retrieval evaluation report).

**Historical cost record, not erased.** Reranking's own real costs while
it was in production remain part of this project's real spend and are
reported in the Work report's "AWS use," including a discarded buggy first
run ($4.574664) and an earlier crashed JSON-parsing attempt ($0.395997) —
disclosed there in full regardless of what the current pipeline costs now.

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
set as it stood that day) has a *different* mismatch set — false refusal:
id 8 only (was 11, 22); misclassified as answered: ids 42, 44, 53, 55 (was
42, 43, 44; 43 was separately relabelled `answered` on 2026-08-18, so it
can no longer appear in this category by construction). This is expected,
not a regression: a real retrieval change shifts which questions have full
retrieval success in the first place, which is a precondition for either
failure mode, so the specific ids composing a 4-5-question mismatch set
are not expected to stay fixed across a real pipeline change — the
aggregate counts (misclassified count still 4; false refusals improved
2→1) are the load-bearing numbers, not id-level identity.

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
history). There is no reranking row: `rerank.py` and `RuntimeVersions.rerank`
were reverted 2026-08-19 (see the update block at the top of this report).

## Storage and reproduction

`reports/eval/generation_evaluation_results.json` (committed) —
full per-question results including answer text, citations, grounding
verdict and justification, and token/latency figures for all 55 questions.
Real per-run usage logs (gitignored, per this project's shared-IAM
instrumentation convention) are in `reports/usage/`. Rerun with:

```
OPENSEARCH_URL=http://localhost:9200 \
uv run python scripts/evaluate_generation.py --contributor <your-contributor-id>
```

against a rebuilt index (see the Retrieval evaluation report's index-build
instructions) — this is a real-cost script (~$2.02 per full run), not
exercised by the automated test suite, matching `scripts/evaluate_retrieval.py`'s
own convention.
