# Generation Evaluation Design

Date: 2026-08-14
Status: Decided
Covers: ASSIGNMENT.md required work items 7-8 (grounded answers, verifiable
citations, explicit non-answer states), from the evaluation side —
SUBMISSION.md's "Generation evaluation report" requirement: grounding,
citation integrity, unsupported citation/hallucination, insufficient-
evidence refusal, out-of-scope refusal, latency, token use, and cost.

It does not cover: retrieval metrics (already decided and measured,
`reports/decisions/2026-08-13-retrieval-evaluation-design.md`, `reports/
retrieval-evaluation-report.md`); the `dependency_unavailable` state itself
(already covered by unit tests against fake clients that raise the target
exception types, `reports/decisions/2026-08-14-out-of-scope-and-
dependency-unavailable-design.md` — this evaluation exercises the real
pipeline against a healthy backend, not a simulated outage); the retrieval
test set's construction or composition (already fixed, reused unchanged
here).

## Summary of decisions

| Area | Decision |
| --- | --- |
| Scope | All 50 questions from `reports/eval/retrieval_test_set.json`, through the real `LegalAgent.answer_sync` (retrieval + generation), once each |
| Repetition | One real run per question, not multiple trials — "stochastic" in SUBMISSION.md's phrasing describes the *nature* of generation measurement (non-deterministic given the same input) relative to retrieval's determinism, not a mandate to repeat every question multiple times |
| Grounding / unsupported citation / hallucination | An LLM-judge pass (Bedrock Claude Sonnet 4.6 — the same fixed model, not a second model id) rates every real `answered` response's answer text against its own cited excerpts: `grounded` / `partially_grounded` / `unsupported`, with a short justification |
| Citation integrity (narrow sense) | Already structurally enforced in code (`agent.py` discards any cited id not actually retrieved, surfacing the discard via `limitations`) — measured by counting how often `limitations` fires across the real run, not re-implemented |
| insufficient_evidence / out_of_scope refusal accuracy | Direct comparison of each question's actual `status` against `retrieval_test_set.json`'s `expected_status`, across all 50 — this run is also the first real, empirical check of the deferred domain-coverage risk from item 7/8's final review |
| Latency, tokens, cost | Read directly from `LegalAgent.answer_sync`'s existing `on_usage` callback and the response object, per question |
| Storage | `reports/eval/generation_evaluation_results.json` (committed, same pattern as the Retrieval evaluation report's results file); real usage log per run to `reports/usage/` (gitignored) |

## Decision 1: full 50-question real run, one trial per question

Every question in the already-committed, already-approved test set is run
through the real pipeline once: `LegalAgent.answer_sync`, the same method
the retrieval evaluation exercises the retrieval half of, but here run in
full (retrieval + generation) — no separate, evaluation-only pipeline
exists or is created.

**Why the whole 50, not a sample:** the 40 answerable / 5 unanswerable / 5
out-of-scope split is exactly what exercises all three of the response
states this evaluation needs to measure (`answered`, `insufficient_
evidence`, `out_of_scope`) with the same test set already vetted for
leakage and construction method — reusing it keeps this evaluation's
questions traceable to the same disclosed provenance as the Retrieval
evaluation report, rather than requiring a second, separately-justified
sample.

**Why one trial, not repeated measurement:** SUBMISSION.md's Generation
evaluation report section says to "separate deterministic retrieval
measurements from repeated stochastic generation measurements" — read in
context, this is drawing a *methodological* distinction (retrieval given a
frozen index and a fixed query is reproducible call to call; generation,
being an LLM sampling process, is not, so the two must not be measured or
reported as if they had the same reliability) rather than a literal
instruction to run every question multiple times. Running each of the 40
answerable questions three times to characterize variance would roughly
triple this evaluation's real cost for a property (answer-to-answer
variance under the fixed prompt) SUBMISSION.md does not separately ask to
be reported. One real run per question, honestly labelled as a single
real run (not an average across trials), is the accurate and
proportionate scope.

## Decision 2: grounding and hallucination via an LLM-judge, same fixed model

**The problem:** citation integrity in the narrow sense — every cited
`chunk_id` really was retrieved, never invented — is already guaranteed by
`agent.py`'s existing logic (Decision "Citation integrity" below). What is
not guaranteed by any code today is the broader property SUBMISSION.md's
"unsupported citation/hallucination" bullet asks about: whether the
answer's actual prose *content* is something the cited excerpt(s) actually
say, or whether the model added claims, numbers, or conclusions the
excerpts don't support. Nothing in the current pipeline checks this, and it
cannot be checked by a purely mechanical rule (unlike, say, exact chunk_id
matching) — it requires reading the answer against its evidence and
judging whether the claim follows.

**Chosen method:** an LLM-judge pass, run after the main 50-question run
completes, only over the subset that actually returned `answered` (there is
nothing to judge for a refusal — no answer text exists). For each such
response, a separate, explicit judge prompt is built from the question, the
answer text, and the full text of every cited citation's excerpt, asking
Claude to classify the answer as `grounded` (every claim is supported by
the cited excerpts), `partially_grounded` (some claims are supported, some
are not directly traceable to the excerpts), or `unsupported` (the answer
makes claims the excerpts do not support), with a one-to-two sentence
justification.

**Why the same model (Sonnet 4.6), not a cheaper/different one:**
ASSIGNMENT.md's fixed constraints name Sonnet 4.6 as the only Kit-verified
generation model id for this project, and explicitly warn against using an
unverified Opus/Haiku id guessed from a display name. That constraint binds
`LegalAgent`'s own generation step; a judge call is a separate, internal
evaluation-tooling use, not a second "Generation" step in the deliverable
service itself, so it is not literally covered by the same sentence — but
introducing a second model identity into this project (even a supposedly
Kit-provided one, since the id for Opus/Haiku surfaced only in passing
conversation, not through the same `.env.example`-documented channel the
Sonnet id came through) adds a verification burden this evaluation does
not need to take on. Reusing the one model this project has already
verified end-to-end keeps the judge's own reliability inside the same
already-established trust boundary, at the cost of the judge not being a
fully independent second opinion.

**Disclosed limitation, not asserted precision:** an LLM-judge is not
ground truth. It is disclosed in the eventual report exactly as what it
is — an automated, single-model, single-pass classification, not a
human-verified gold standard — following this project's established
practice (`reports/decisions/2026-08-13-retrieval-evaluation-design.md`'s
own LLM-drafted-then-human-reviewed test questions being the nearest
precedent for combining LLM output with an honest disclosure of its
limits). Given this evaluation's real-cost, single-contributor,
under-deadline constraints, this is judged proportionate; a second
independent judge pass or human spot-check is named as a candidate for
"what one more week would allow" in the Work report, not attempted here.

## Decision 3: insufficient_evidence / out_of_scope refusal accuracy, including the deferred domain-coverage check

For every one of the 50 questions, the real `status` this run returns is
compared directly against `retrieval_test_set.json`'s `expected_status`
field — already present on every entry, requiring no new labelling. This
single comparison, run once over all 50 questions, produces:

- **insufficient_evidence refusal accuracy**: of the 5 questions with
  `expected_status: "insufficient_evidence"` (ids 41-45, targeting the
  withdrawn-official-guide gap `DATASET.md` documents), how many actually
  come back `insufficient_evidence`.
- **out_of_scope refusal accuracy**: of the 5 questions with
  `expected_status: "out_of_scope"` (ids 46-50), how many actually come
  back `out_of_scope`.
- **The deferred risk from item 7/8's final review, checked empirically for
  the first time**: whether any of the same 5 `insufficient_evidence`
  questions (ids 41-45) are misclassified as `out_of_scope` instead — the
  named, unverified risk that motivated deferring a prompt change rather
  than guessing at one (`reports/decisions/2026-08-14-out-of-scope-and-
  dependency-unavailable-design.md`'s ruling). This run is exactly the
  empirical check that ruling called for, not a separate task.
- As a byproduct of running all 50: whether any of the 40 answerable
  questions unexpectedly return anything other than `answered` (a
  false-refusal on a question the retrieval evaluation already confirmed
  is answerable-in-principle) is visible in the same result set, without a
  separate check.

## Decision 4: citation integrity (narrow sense) — measured, not re-implemented

`agent.py`'s existing logic already guarantees every `citations` entry in
an `answered` response points to a chunk this call actually retrieved,
and surfaces any discarded, non-real cited id through the response's
`limitations` field rather than silently dropping or fabricating one. This
evaluation does not re-verify that guarantee by re-deriving it (that would
duplicate the unit tests already covering this in `tests/test_agent.py`);
it measures how often the guard actually fires across 50 real
generation calls — a count of `limitations`-non-empty responses, reported
alongside the total `answered` count. A non-zero count is itself a finding
worth reporting (the model attempted a fabricated or stale citation at
least once), not necessarily a defect, since the guard is precisely what
is supposed to catch and correct it.

## Decision 5: latency, tokens, cost — read from existing instrumentation

`LegalAgent.answer_sync`'s `on_usage` callback already reports real
embedding-token estimates and real Bedrock-reported generation input/output
token counts per call; the response object and wall-clock timing around
each call give per-question latency. `scripts/evaluate_generation.py` (new,
following `scripts/evaluate_retrieval.py`'s and `scripts/serve_legal_
agent.py`'s established shape) accumulates these per question into the
committed results file and writes a real per-run usage log to `reports/
usage/`, matching every other real-Bedrock-calling script in this project.
No new instrumentation mechanism is introduced.

## Storage

`reports/eval/generation_evaluation_results.json` (committed, not
gitignored — `reports/eval/` already holds the analogous Retrieval
evaluation results file under the same rationale: SUBMISSION.md's "the
report that cites it belongs in the commit"). Per-run real usage logs go to
the existing, already-gitignored `reports/usage/`.

## Self-review note

The judge prompt's exact wording and JSON response schema, and the exact
shape of `generation_evaluation_results.json` (field names, per-question
vs. aggregate structure), are implementation-time detail for the plan, not
fixed here — same convention this project's prior design notes already
follow (e.g. `reports/decisions/2026-08-13-retrieval-evaluation-design.md`'s
own "exact JSON schema... implementation detail for the plan, not fixed
there").

## Explicitly out of scope for this note

- Repeated-trial variance measurement (Decision 1) — named as future work
  if time allows.
- A second, independent judge model or a human-reviewed grounding
  spot-check (Decision 2) — named as future work / "one more week" content
  for the Work report, not attempted here.
- Any change to `generation.py`'s prompt in response to what this
  evaluation finds — if the domain-coverage risk (Decision 3) turns out to
  be real, fixing it is separate follow-up work informed by this
  evaluation's result, not pre-empted here.
- Per-domain breakdown is not mandated by SUBMISSION.md's Generation
  evaluation report bullet (unlike the Retrieval evaluation report, which
  explicitly asks for it) — the implementation may still report a light
  per-domain grounding table if it comes for free from data already being
  collected, but it is not a requirement this note fixes.

This is a design decision, not yet implementation — no evaluation script
exists yet as of this note.
