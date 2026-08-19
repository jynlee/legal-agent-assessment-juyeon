# Work Report

Date: 2026-08-14
Covers: SUBMISSION.md's "Work report" requirements — initial estimate and
milestone plan, actual time by milestone, blocker log, completed/incomplete/
deferred work, AWS use, and what one additional week would allow.

## Initial estimate and milestone plan

No initial estimate or milestone plan existed. Work proceeded item-by-item
from ASSIGNMENT.md's required-work list, in the order the items themselves
depend on each other (chunking before indexing, indexing before retrieval,
retrieval before generation, generation before evaluation), without a
separate estimation or scheduling exercise beforehand.

## Actual time by milestone

No separate time-tracking tool was used. The table below is reconstructed
from real git commit timestamps (`git log`, this repository, first commit
to the latest) and reports elapsed calendar/session spans, not literal
hours-worked — it does not capture reading, thinking, or debugging time
that produced no commit, and does not subtract breaks within a span. This
is disclosed as an honest proxy, not a precise timesheet.

| Milestone (ASSIGNMENT.md item) | Date(s) | Span | Representative commits |
| --- | --- | --- | --- |
| Template setup, access-model settlement, dataset scope decisions | 08-08 | 22:31–23:41 | `049ce0b`..`6acee2b` |
| Item 1: source record schema, release manifest, validator, licence-based scoping (official guides removed) | 08-09 | 00:16–14:46 | `37a7435`..`37bab4e` |
| *(no commits 08-10)* | — | — | — |
| Item 2: record-selection policy, normalization/chunking design, Chunk data model | 08-11 | 14:22–20:20 | `e8d85e8`..`b73880e` |
| Item 2 cont'd: provenance recording, sentinel-record decisions | 08-12 | 10:53–11:57 | `d35dff6`..`0a0d08d` |
| Item 2 cont'd: statute chunking implementation | 08-12 | 14:13–16:38 | `c7cc1fe`..`c79b29b` |
| Item 2 cont'd: judgement chunking implementation, final-review fixes | 08-12 | 16:33–19:41 | `4e5d400`..`7f2008c` |
| Item 3: OpenSearch index mapping and versioned index creation | 08-13 | 13:42–16:11 | `1f378f5`..`f349bd1` |
| Item 4 (part 1): embedding adapter, indexing pipeline, final-review fixes | 08-13 | 16:14–17:48 | `61f7e3a`..`6c1a771` |
| Item 4 (part 2): query embedding, hybrid retrieval, fusion | 08-13 | 18:42–19:12 | `2a7982a`..`3c3bc26` |
| Items 7, 8 (partial), 9: generation, citations, application-service contract | 08-13 | 19:16–20:02 | `2362505`..`c0896e4` |
| Items 5, 6: retrieval test set, pure retrieval evaluation | 08-13 | 20:17–21:31 | `945aee6`..`df3daf5` |
| Item 6 fix: retrieval-evaluation final-review findings | 08-14 | 10:26 | `0788dbe` |
| Item 8 (completion): `out_of_scope` and `dependency_unavailable` states | 08-14 | 10:59–12:05 | `1966bf3`..`e2cebac` |
| Item 10: Architecture report | 08-14 | 13:26 | `1394bef` |
| Environment recovery, index rebuild, real retrieval-evaluation run | 08-14 | 15:34 | `a5ec7ec` |
| Item 10: Retrieval evaluation report | 08-14 | 16:02 | `e44a2cc` |
| Generation-evaluation design, judge module, `max_tokens` fix | 08-14 | 17:47–18:23 | `6b9d09a`..`63638bd` |
| Generation-evaluation script, real run, final review, fix round, re-run | 08-14 | 20:05–20:41 | `fd810f1`..`ff85ab8` |
| Item 10: Generation evaluation report | 08-14 | after 20:41 | (this session, pending commit) |
| Item 10: Work report | 08-14 | after Generation evaluation report | (this document) |

**Heaviest single days**: 08-12 (judgement/statute chunking, ~22 commits)
and 08-13 (indexing through the first retrieval evaluation, ~30 commits,
~13:42–21:31). 08-14 is the longest calendar span (~10:26–20:41+) but
includes a real, disclosed environment-recovery interruption (see Blocker
log) in the middle of it.

## Blocker log

**Access and environment failures, all specific to this contributor's
personal development machine, not a project requirement or a gap in
MZO's setup instructions:**

1. **Native Windows Python SSL block.** The machine this project was
   developed on has endpoint-security software that blocks the standard
   library's SSL module (`_ssl.pyd`) from loading under native Windows
   Python — unrelated to this project's code or dependencies. Every
   `uv run`/`pytest`/boto3 command in this project ran through WSL2
   Ubuntu-24.04 as a workaround from the point this was discovered
   onward. MZO's original setup instructions contain no Windows- or
   WSL-specific step; this is disclosed here and in the Architecture
   report (§7) as a personal-machine workaround.
2. **A native OpenSearch 3.7.0 systemd service squatting port 9200.**
   Discovered twice (2026-08-13 and again 2026-08-14) — a leftover,
   unrelated OpenSearch install on this machine's WSL2 distribution held
   the default port, making the project's own Docker OpenSearch container
   unreachable at its expected address. Never fully resolved with `sudo`
   access to disable the systemd service; worked around by moving the
   project's container to host port 9201 (`.env`, gitignored,
   `OPENSEARCH_URL=http://localhost:9201`) and confirming via a clean
   checkout test that this override never reaches a committed file —
   `.env.example` still documents the default port 9200 for MZO's own
   reproduction.
3. **Docker container instability / WSL2 restarting unpredictably.**
   The project's OpenSearch container was SIGTERM-killed by an unknown
   external cause at least once (2026-08-14, mid Retrieval-evaluation
   report work), and the WSL2 distribution itself restarted
   unpredictably at least 3 separate times during Generation-evaluation
   work on 2026-08-14, silently killing whatever real, in-progress
   Bedrock call was running each time. Working theory (not conclusively
   confirmed within a time-boxed investigation): resource contention with
   an unrelated container workload also running in the same WSL2
   instance on this machine. Practical mitigation adopted: the index was
   rebuilt once (see "AWS use" below) after confirming the corruption was
   real and not recoverable in place; long real-cost runs were
   subsequently launched directly by the controller rather than through
   an intermediate subagent, after two separate cases where a dispatched
   subagent claimed to be "waiting for completion" of a long-running real
   call without actually blocking on it.
4. **`.env`'s CRLF line endings broke `bash source` outright.** Discovered
   2026-08-14 while re-running the Generation evaluation after a code fix
   round: sourcing `.env` in a fresh WSL bash session failed on every
   blank/comment line (`$'\r': command not found`), and would have
   silently appended a trailing `\r` to every exported value (e.g. the
   model id) had any line partially succeeded. Fixed by sourcing through
   `source <(sed 's/\r$//' .env)` rather than editing the file, so no
   committed convention changed. Real-cost impact: none — both failed
   attempts (this one, and a separate one where `BEDROCK_MODEL_ID_SONNET`
   was simply never loaded into a fresh WSL session) failed before any
   AWS call was made.

**Real, in-development Bedrock/OpenSearch API failures — not environment
issues, genuine first-time-encountered constraints of this project's own
integration:**

5. **`_GENERATION_MAX_TOKENS` truncation.** The Generation evaluation's
   first real full-pipeline run hit a genuine truncation on its very
   first question at the original ceiling of 1024 tokens — raised to
   4096 after confirming against ASSIGNMENT.md's fixed constraints that
   this is contributor discretion (commit `63638bd`). See the
   Architecture report §7 item 8.
6. **Bedrock rejects assistant-message prefill on this model/endpoint.**
   Attempting to force the judge model's response into strict JSON by
   seeding the assistant turn with `"{"` was rejected outright:
   `ValidationException: This model does not support assistant message
   prefill.` A top-level `system`-field instruction was used instead,
   which took the judge's JSON parse-failure rate from 57.5% (23 of 40
   judged answers in one real run) to 0% in two subsequent real runs.
7. **Cost-accounting bug zeroed real spend on a mid-run crash.** Found
   during this evaluation's own final code review (not by MZO, not by an
   external audit): `scripts/evaluate_generation.py`'s per-question token
   counters were only added to the run-wide totals at the end of each
   loop iteration, so a crash partway through a question (from finding 5
   or the WSL2 restarts above) silently discarded that question's
   already-real spend from the written usage log. **4 of the 16
   real-call attempts logged in `reports/usage/` recorded
   `estimated_cost_usd: 0.0` despite 19–31 real seconds of elapsed API
   time each** — their true partial spend is real but not recoverable
   from the record. Fixed in commit `ff85ab8` (totals now update the
   moment each real call returns); the two runs that succeeded after
   this fix landed reproduced the same real cost pattern the earlier,
   correctly-accounted runs already showed, so this is judged not to
   have distorted the reported evaluation numbers, only the historical
   cost total below.

**Known instrumentation gaps, disclosed rather than hidden:**

8. **6 untracked Bedrock calls during Task 5–6 development (2026-08-13).**
   One smoke test, one controller direct-verification call, two
   re-verification calls after the 1536-dimension embedding bug fix, and
   two Task 6 implementation/fix-verification calls were made before
   `scripts/index_chunks.py`'s usage instrumentation existed, so none of
   the 6 wrote a `reports/usage/` entry. Found and flagged by the project
   owner, not self-caught. Reconstructed after the fact: ~84 tokens
   total, ~$0.00001 — real but negligible. Every real call from Task 7
   onward is fully instrumented.
9. **2 of the 4 `serve_legal_agent.py` usage logs record no token
   counts.** The earliest two real single-question smoke calls
   (2026-08-13, ~19:33) predate that script's token-capture addition and
   recorded only status and latency. Real, single-question calls —
   negligible cost, not numerically included in the token/cost totals
   below (their status and latency are still real and logged).

**A test-data correctness defect, found and corrected on 2026-08-18:**

10. **2 of the original 5 `insufficient_evidence` gold labels were
    wrong.** Ids 43 and 54 were built as "the corpus cannot resolve this"
    questions, but real re-verification (reading each generated answer's
    actual citations line by line, not just trusting the aggregate
    number) found both are directly resolved by a real statute provision
    the original construction/verification search missed: id 43 by
    의료기기법 제26조 제7항 (near-verbatim on point), id 54 by
    공중위생관리법 제6조 제3항 (missed because the provision uses
    "빌려주다/빌리다," not the "대여" keyword the original verification
    search used). Both were relabelled `answered` with the real resolving
    chunk as required positive, and a real re-run confirmed the model
    answers both correctly. Found by the project owner explicitly asking
    for the "failed" cases to be re-verified rather than accepted as
    model error, not self-caught proactively — the same discipline this
    project applies elsewhere ("measure, don't assume") applied to its
    own test data for the first time here. Full detail in the Generation
    evaluation report's "Two gold-label errors found and corrected."

**A retrieval-quality gap, diagnosed and fixed on 2026-08-18:**

11. **Equal-weight RRF fusion was burying strong single-retriever hits.**
    A per-question diagnosis (real BM25-top-50 and kNN-top-50 lists for all
    42 answerable questions, not just the fused top-10) found dense k-NN
    held the required chunk for 17 of the 23 original Recall@10 misses
    versus BM25's 4 of 23 — the original `k=60`, equal-weight RRF was
    letting unweighted rank-consensus bury k-NN's often well-ranked single
    hits under weaker chunks both retrievers happened to agree on.
    `retrieval.py`'s `reciprocal_rank_fusion` gained an optional per-list
    `weights` parameter (TDD: 2 new tests written red, then green; default
    unchanged so every prior test stayed green); `agent.py` and
    `evaluate_retrieval.py` now weight k-NN 3x BM25. A real re-run raised
    aggregate Recall@10 from 0.4524 to 0.5714 and MRR from 0.2437 to
    0.2809, with no reindex needed. The weight was chosen by replaying the
    same real top-50 lists offline against several weight/k combinations
    against this same 42-question test set — disclosed as direct tuning
    against the project's own eval set, not an independent holdout. Full
    diagnosis and honest limits (6 of 18 remaining misses have the gold
    chunk absent from *both* retrievers' top-50 and cannot be recovered by
    fusion tuning alone) are in the Retrieval evaluation report's "Fusion
    weighting" and updated "Failed-query analysis."
12. **The diagnostic script itself was not usage-instrumented.** 65 real
    Cohere Embed v4 calls (23 for the first miss-only pass, 42 for the
    full-answerable-set pass) were made by a throwaway diagnostic script
    that had no `reports/usage/` writer — an instrumentation gap of the
    same kind as items 8–9 above, caught this time before being pointed
    out rather than after. Reconstructed after the fact from the real
    question texts and `estimate_tokens`: 2,627 tokens, ~$0.000315 — real
    but negligible, folded into the "disclosed separately" line in "AWS
    use" below rather than the fully-instrumented total.

**A real crash reproduced live and fixed on 2026-08-18:**

13. **`parse_answer_response` crashed on real `prompt-v2` output.** The
    fusion-weight re-verification's full 56-question real generation run
    crashed at question 8 (의료법): the model closed its JSON answer with a
    fence and then kept writing prose explanation below it, which
    `json.loads` rejected as "Extra data," raising an unhandled `ValueError`
    that killed the whole run — real Bedrock spend on questions 1–8 lost
    mid-run (crash-safe accounting still recorded it: $0.395997, `status:
    "failed"`, `reports/usage/1787049936405213024-evaluate-generation.json`).
    This is the same failure shape found and fixed once already during the
    reverted `prompt-v5` trial, but that fix was reverted along with
    `prompt-v5`'s prompt wording — it turns out the parsing bug is
    independent of prompt version and was still live in the shipped
    `prompt-v2` path the whole time, just not yet hit by a real question.
    Fixed via TDD (test reproduces the exact crash text verbatim): swapped
    `json.loads` for `json.JSONDecoder().raw_decode`, which parses only the
    first JSON value and ignores trailing content, the same tolerance the
    parser already gives an opening code fence. Confirmed by a clean real
    re-run of all 56 questions with no crash.

**A real production feature added, with a real regression caught and
fixed before being reported as final:**

14. **Semantic reranking added on top of the fusion-weight fix.** Approved
    after an explicit cost/time/effect estimate (recall was estimated at
    roughly 70-80%, up from 57.1%). New module `rerank.py` (the `judge.py`
    pattern: a separate, narrowly-scoped Bedrock call, TDD, 9 new tests),
    wired into `agent.py` (fused pool widened from top-10 to top-25,
    reranked down to top-10 before generation) and
    `scripts/evaluate_retrieval.py` (kept in sync with production for the
    same reason the fusion-weight fix required it). `RuntimeVersions`
    gained a `rerank` field, threaded through every construction site (6
    files) since a rerank prompt is now part of producing a real response,
    the same reproducibility reasoning `prompt` already had. Real result:
    Recall@10 0.5714→**0.5952**, well short of the 70-80% estimate — the
    estimate was optimistic, disclosed as such rather than revised after
    the fact (Retrieval evaluation report's "Reranking"). Real,
    **permanent** per-query cost/latency increase, unlike items 11/13
    above: median retrieval latency rose ~8.5x (525ms→4.5s); a real single
    demo call's rerank step alone cost $0.076, roughly 3-5x the earlier
    cost estimate, because the design uses full candidate excerpts (up to
    2,000 characters each) rather than truncated snippets.
15. **The first real full run after adding reranking broke every
    out_of_scope question.** `out_of_scope_refusal_accuracy: 0.0` (0 of 5),
    down from a perfect 1.0 — found immediately by reading the aggregate
    before reporting anything as final, not shipped and discovered later.
    Root cause: the implementation returned `INSUFFICIENT_EVIDENCE`
    directly whenever the reranker selected zero candidates, which is the
    reranker's correct behavior for an off-topic question (nothing
    retrieved *is* relevant) — but skipped the real generation call
    entirely, and `out_of_scope` classification is that call's own
    judgment on the question itself, independent of what retrieval found.
    Fixed via TDD (2 new tests reproducing both the broken and the correct
    behavior) by removing the early return: an empty reranker selection
    now still reaches generation with zero citations, restoring the exact
    behavior every out_of_scope question always relied on before
    reranking existed. This discarded first run's real cost, $4.574664,
    produced numbers that were never reported as final (see "AWS use"
    below) — a real, disclosed cost of catching a real bug before
    shipping it, not folded silently into the committed totals.
16. **Reranking made a known weakness worse, not better.** Not a bug —
    a real, unintended side effect, disclosed in full in the Generation
    evaluation report's "insufficient_evidence refusal accuracy" section
    ("Reranking made this worse, not better"). Widening the candidate pool
    to give the reranker more to select from also gave the model's
    already-documented over-answering bug more plausible-but-not-
    dispositive evidence to reason from:
    `insufficient_evidence_refusal_accuracy` fell from 0.5556 to 0.3333,
    and `insufficient_evidence_misclassified_as_answered` rose from 4 to
    6. Every other headline number improved (`answered_status_match_rate`
    reached a perfect 1.0, `false_refusal_count` reached 0) — reported
    together, not selectively, so the mixed result is visible rather than
    obscured by the numbers that happened to improve.
17. **A fifth over-answering fix mechanism was piloted cheaply and also
    failed (2026-08-19).** The Generation evaluation report's own
    conclusion (after v3/v4/v5) named a separate, `judge.py`-style Bedrock
    call as the untried category of fix. Before spending a full real
    pipeline run building it, a new `verify.py` module (two prompt
    variants) was piloted against 16 already-saved answers/citations from
    the committed `generation_evaluation_results.json` — no pipeline
    re-run, no production code touched, real Bedrock calls only against
    data already on disk. v1 (shows the answer, asks a lenient sufficiency
    question) caught 0 of 6 known failures; v2 (hides the answer, asks an
    independent stricter question) caught 1 of 6. Neither cleared the
    >=4/6 bar set before starting. **Not adopted — `verify.py` and
    `tests/test_verify.py` were never committed**, `agent.py` and
    `contracts.py` were never touched. Full account:
    Generation evaluation report, "insufficient_evidence refusal
    accuracy" → "A fifth mechanism was tried." Real cost: $0.396321, 32
    Bedrock calls (`temp/pilot_verify.py`, gitignored, not committed).
18. **A test-set construction defect found on human review; question 41
    invalidated, not relabelled (2026-08-19).** Reviewing all 6
    confirmed-genuine `insufficient_evidence` failures' cited sources line
    by line (the same standard already used for ids 43/54) found question
    41's cited source states a *general* principle that covers its claim
    on its face, not by the analogical extension the other 5 failures
    share — making it an invalid `insufficient_evidence` example. Unlike
    ids 43/54, it could not be relabelled `answered`: it was never drafted
    from a specific source chunk, and assigning one now from what the
    model itself cited would make its `Recall@10` contribution true by
    construction — a self-grading risk, not a legitimate correction.
    Removed from the test set entirely (56 → 55 questions;
    `insufficient_evidence`: 9 → 8). Full reasoning, the pre-registered
    review criterion applied identically to all 6 cases, and why the
    structurally-closest case (question 44) was reviewed and deliberately
    *not* reclassified, is in `reports/decisions/2026-08-19-question-41-
    invalidation.md`. Effect: `insufficient_evidence_refusal_accuracy`
    0.3333→0.375; combined non-answer-classification figure
    (`insufficient_evidence` + `out_of_scope`) 57.1%→61.5% — **both
    figures are reported side by side** in the Generation evaluation
    report, not just the corrected one. `reports/eval/
    generation_evaluation_results.json` and `reports/eval/
    retrieval_evaluation_results.json` were recomputed/pruned from the
    already-stored per-question data, not re-run (Recall@10/MRR are
    unaffected — question 41 was never in that denominator).
    `scripts/evaluate_generation.py` and `scripts/evaluate_retrieval.py`
    hardcoded question-count assertions updated 56→55.

## Completed, incomplete, and deliberately deferred work

**Completed** (all 9 required-work items plus item 10's reporting
deliverables):

1. Record-selection and document-kind decisions — done (`reports/decisions/`, record-selection policy).
2. Normalization, chunking, deterministic identity rules — done (`norm-v1`, `chunk-v1`, statute and judgement chunkers).
3. Versioned OpenSearch 3.5-compatible index, reproducibly — done (`index-v1`, built twice, byte-identical cost/count both times).
4. Query embedding, retrieval, fusion, reranking — done (BM25 + exact k-NN + client-side RRF, `k=60`, k-NN weighted 3x BM25; a real Claude Sonnet reranking stage over a widened top-25 pool added 2026-08-18 — see Blocker log items 11 and 14-16, including a real regression caught and fixed before being reported as final).
5. Test set and relevance judgements — done (56 questions, `reports/eval/retrieval_test_set.json`, leakage-checked; grew from 50 to 56 on 2026-08-18, see the Blocker log and "Incomplete / found but not fixed" below for the 2 gold-label corrections made along the way).
6. Quantitative retrieval metrics — done (Recall@10, MRR; nDCG deliberately not computed, justified in the Retrieval evaluation report).
7. Grounded answers via the fixed Bedrock Claude model policy — done (`LegalAgent`, `prompt-v2`).
8. Verifiable citations, `insufficient_evidence`, `out_of_scope`, `dependency_unavailable` — done, all 4 response states implemented and covered by both unit tests and the real Generation evaluation run. A citation-integrity blind spot found during the Generation evaluation's final code review (total-fabrication citations were indistinguishable from an honest refusal) was closed on 2026-08-18 — see "Incomplete / found but not fixed" below for what changed and how it was verified.
9. Single-turn, stateless application-service contract — done (`GeneralLegalRequest`/`GeneralLegalResponse`, `async def answer`).
10. Tests, reproducible commands, architecture decisions, limitations, effort/time/cost evidence — done: 229 tests passing; non-interactive `verify_release.py`, `index_chunks.py`, `evaluate_retrieval.py`, `evaluate_generation.py`, `serve_legal_agent.py`; Architecture, Retrieval evaluation, and Generation evaluation reports committed; this Work report.

**Deliberately deferred** (named explicitly in the relevant report, not
silently skipped):

- **Reranking, and query-time filtering by document kind or chunk type** —
  scoped out against this corpus's small scale (Architecture report §7).
- **Repealed-statute weighting metadata is emitted but not consumed** by
  retrieval or ranking logic yet (Architecture report §7).
- **Managed-domain (SigV4/SSM) connectivity verification** —
  `OPENSEARCH_ACCESS.ko.md` frames this as needed only "when you need to
  prove" managed-domain access, not a SUBMISSION.md requirement; every
  real evaluation and index build in this submission ran against a local
  container. Never completed — blocked on a real managed-domain endpoint
  and app-EC2 instance id this contributor never obtained. Nori
  availability on the managed domain (permission-cleared, per the
  2026-08-14 plugin-permission update recorded in the analyzer decision)
  is correspondingly still mechanically untested.
- **A second, independent LLM-judge pass or human spot-check of
  grounding verdicts** — the Generation evaluation report's judge is a
  single fixed-model, single-pass classification, named as a real
  limitation, not asserted as ground truth.
- **Repeated-trial variance measurement for generation** — each question
  runs once per real evaluation attempt, not multiple trials (Generation
  evaluation design Decision 1); the original 50-question set ran twice
  in practice and reproduced the same status-decision pattern, reported
  as evidence of stability, not a substitute for a formal variance study.

**Found and fixed within this submission, not deferred:**

- **`agent.py`'s "total fabrication" citation path was invisible to
  `limitations_fired_count`.** Found during the Generation evaluation's
  final code review: if the model claimed `answered` with zero
  actually-retrieved cited ids, the response downgraded to a bare
  `insufficient_evidence` with an empty `limitations` field —
  indistinguishable from an honest refusal. Originally judged out of
  scope for an evaluation-tooling fix round and deferred to "one more
  week" in an earlier version of this report; revisited and fixed on
  2026-08-18 once judged a small, contained, low-risk change (it changes
  response *visibility*, not model behavior or any accuracy metric) —
  `agent.py`'s existing partial-fabrication `limitations` pattern was
  extended to the total-fabrication case too. Verified by TDD (2 new
  unit tests plus assertions added to 2 existing tests, confirmed failing
  before the fix and passing after) and by one real full re-run, which
  resolved a real, previously-disclosed unknown rather than a
  hypothetical one: questions 11 and 22 (the false-refusal pair below)
  both show `limitations_count: 0` in the real committed data, proving
  they are honest refusals, not caught fabrication — see the Generation
  evaluation report's "Citation integrity" section for the full data.

**Incomplete / found but not fixed** (real gaps, surfaced by this
project's own review process, disclosed rather than silently left):

- **Two real, opposite-direction refusal-accuracy failures; three
  independent fix attempts, three different mechanisms, all reverted**:
  2 of 42 answerable questions are falsely refused despite successful
  retrieval (`insufficient_evidence refusal accuracy` section's mirror
  finding), and 4 of 9 `insufficient_evidence`-expected questions are
  answered instead of refused (corrected count, after removing 2
  gold-label errors from this bucket — see Blocker log item 10).
  `prompt-v3` (a blanket instruction against answering by analogy)
  improved the over-answering direction (3→2, against the uncorrected
  baseline) but worsened false refusals more (2→8). `prompt-v4` (a
  contrastive worked example instead of a blanket instruction) improved
  nothing and still worsened false refusals (2→6). `prompt-v5`
  (2026-08-18, against the corrected 9-question set): an explicit
  `source_directly_resolves` field the model must commit to before
  `status`, code-checked rather than trusted — directly targeting a real
  root cause found after v3/v4 (id 53's own answer text states its source
  is ambiguous and still returns `status: "answered"` anyway, a
  disconnect between stated reasoning and final decision, not a failure
  to notice the gap). Its first real run crashed on question 53 itself
  (the model emitted a correct JSON verdict, then "Wait, let me
  reconsider...", then a second, contradictory one — an unhandled
  parsing case, fixed: `parse_answer_response` now takes only the first
  JSON value in the text, and the prompt now explicitly forbids
  reconsideration text). The repaired v5's real re-run: no improvement
  (still 4; id 53 itself was answered incorrectly again, without
  crashing) and false refusals rose to 6. Reverted; `prompt-v2` remains in
  production. **All three attempts reverted against the same
  pre-registered bar.** Three independently-mechanized attempts producing
  the identical trade-off (less over-answering always costs more false
  refusal, net negative) is read as evidence the fix does not live at the
  prompt-wording or response-schema level — not attempted a fourth time
  this submission; see "What one additional week would allow" for the
  next, structurally different candidate.
- **Generation-only latency is not isolated from the judge call's added
  latency** in the Generation evaluation report's `answered`-path
  numbers — the deliverable's own single-call response time was not
  separately measured this evaluation.

## AWS use

Self-instrumented from the first real call this project made, per
SUBMISSION.md's requirement (contributors share one IAM user; no billing
or CloudTrail record can attribute usage to a specific contributor).
Source: every file in `reports/usage/` (gitignored; 41 files, one per real
script invocation that made at least one real AWS call). This total
includes every real run made after this report's numbers were first
drafted on 08-14: the `prompt-v3`, `prompt-v4`, and `prompt-v5` trials (all
tried, then reverted — `prompt-v2` is what shipped; `prompt-v5`'s first
attempt crashed mid-run on a real parsing bug, itself fixed, and its
second, completed attempt is one of the "failed" generation-evaluation runs
below), a 2026-08-18 re-verification pass against the local container to
confirm the committed numbers reproduce, the test-set expansion/correction
work (real retrieval and generation evaluation runs against the
growing/corrected 56-question set), the `agent.py` citation-integrity
fix's own real validation run, the fusion-weight fix's real retrieval
re-run, the JSON-parsing crash's real crashed attempt plus its real clean
re-run, and reranking's own real cost: a real demo smoke-test call, two
real retrieval-evaluation runs (rerank kept `evaluate_retrieval.py` in
sync with production), and two real full generation-evaluation runs (a
discarded first run that shipped with the out_of_scope regression still
live, then the real clean re-run after the fix) — Blocker log items 11–16
cover this in full. Every real call is recorded from the first one onward
per this section's requirement, confirmation-only, crashed, and discarded
calls included.

| Category | Runs | Embed tokens (est.) | Generation input tokens | Generation output tokens | Cost |
| --- | --- | --- | --- | --- | --- |
| Index builds (`index_chunks.py`) | 2 | 7,280,846 | — | — | $0.8738 |
| Retrieval evaluations (`evaluate_retrieval.py`, incl. rerank calls) | 9 | 18,263 | 1,577,010 | 14,493 | $4.950616 |
| Generation evaluations (`evaluate_generation.py`) | 19 (13 completed, 6 crashed; 1 of the 13 discarded for the out_of_scope regression) | 28,695 | 8,485,594 | 468,234 | $32.483734 |
| Real demo calls (`serve_legal_agent.py`) | 11 (2 without token capture) | 203 | 65,014 | 2,613 | $0.234260 |
| **Total, fully instrumented** | **41** | **7,328,007** | **10,127,618** | **485,340** | **$38.542410** |

**Reconciling note (2026-08-19, Blocker log item 18):** the table's
Generation-evaluations row above still includes the real cost of question
41's own retrieval+generation+judge calls — this table reports every real
dollar actually spent, regardless of what any evaluation report later
excludes from its own metrics. The Generation evaluation report's own
"Token use and cost" table was recomputed after question 41's invalidation
and shows a ~$0.0436 lower total ($4.51071→$4.467164) for that reason —
the two figures are expected to differ, not a discrepancy.

Plus, disclosed separately rather than folded into the total above
(see Blocker log items 7–9, 12, 17): **~$0.00001** from 6 untracked pre-
instrumentation dev calls, **~$0.000315** from the 65 real embedding calls
made by 2026-08-18's uninstrumented retrieval-miss diagnostic script,
**$0.396321** from the 32 real calls made by 2026-08-19's `verify.py`
pilot (two prompt variants tested against already-saved data, neither
adopted), and an **unknown, likely small** amount of real partial spend
from the 4 original failed Generation-evaluation attempts whose cost was
zeroed by the since-fixed accounting bug (their real elapsed time, 19–31
seconds each, is the only surviving evidence they made real calls at all).

**OpenSearch usage.** One versioned index
(`legal-kit-assessment-jynlee-chunk-v1-index-v1`, `index-v1`), 7,887
chunks per build (7,463 `body` + 424 `summary`), 1 shard / 0 replicas
locally. **Rebuild count: 2** — the original 2026-08-13 production build,
and one full rebuild on 2026-08-14 after the environment failures in
Blocker log items 2–3 made the local container's index unreachable; the
rebuild reproduced the original exactly on every cost/count dimension
(247 embedding calls, 3,640,423 estimated tokens, $0.4369, 0 bulk-index
errors both times), confirming the indexing pipeline is deterministic
given the same corpus and chunking rules. Every real evaluation and demo
run in this submission queried the local container (port 9201, a
personal-machine workaround — see Blocker log item 2); the managed
OpenSearch domain was never actually queried this project (see
"Deliberately deferred" above).

## What one additional week would allow

In priority order, most valuable first:

1. **Fix the over-answering failure — five mechanisms tried, all failed;
   the next one needs a different model identity or a human, not another
   prompt.** `prompt-v3` (blanket instruction), `prompt-v4` (contrastive
   example), `prompt-v5` (a code-checked `source_directly_resolves` field
   inside the same generation call), **reranking** (2026-08-18 — approved
   for a different reason, Recall@10, but widened the candidate pool and
   measurably made this exact failure mode worse:
   `insufficient_evidence_refusal_accuracy` 0.5556→0.3333,
   `insufficient_evidence_misclassified_as_answered` 4→6), and now a
   **separate self-verification call** (2026-08-19 — `verify.py`, piloted
   in two variants against 16 already-saved answers before touching
   production code, per this section's own prior recommendation to try
   exactly this: a lenient variant caught 0 of 6 known failures, a strict
   variant that hid the answer text caught 1 of 6; neither adopted, real
   pilot cost $0.396321) have all been tried and failed to fix this
   without a larger false-refusal cost. The fifth attempt specifically
   tested this section's own prior recommendation — a narrowly-scoped,
   separate Bedrock call, the same pattern `judge.py` uses — and it still
   failed, on both a lenient and a strict prompt. The pilot's own
   diagnostic evidence (v1's verifier re-stated the original answer's
   analogical reasoning back as if it were sufficient; v2's id 53 showed
   the verifier's own justification text arguing "insufficient" while its
   structured field said `true`) points at a **structural** limit, not a
   remaining wording problem: the same model, asked to certify its own
   style of reasoning, tends to confirm it even in an independent call
   with no memory of the original one. What one more week would need to
   try instead is a genuinely different check — either a second,
   independently-sourced-and-verified model identity (this project's
   `.env.example` names only one verified Sonnet id; sourcing and
   verifying a second was out of scope here per the Fixed-constraints
   discipline this project has followed throughout), or a human-reviewed
   spot-check gate, neither of which fits this submission's two-week,
   single-contributor, single-verified-model-id budget.
2. **A second, independent grounding check** — either a genuinely
   different judge model (would require sourcing and verifying a second
   Kit-approved model id) or a human-reviewed spot-check of a sample of
   the 44 judged answers, to test whether the single-model,
   single-pass judge's `partially_grounded` calls hold up under
   independent review. (The `agent.py` citation-integrity gap named in
   an earlier version of this list has since been fixed within this
   submission — see "Found and fixed within this submission" above.)
3. **Isolate generation-only latency** from the judge call's *and now the
   rerank call's* added latency in the `answered`-path numbers (median
   rose from ~14.5s to ~19.6s after reranking), and investigate whether
   the per-domain grounding pattern (no domain fully grounded in the
   latest run; the zero-grounded domain set has now shifted across all
   three real reported runs — see the Generation evaluation report's
   "Grounding" section) is a stable property or sampling noise, with a
   larger per-domain sample.
4. **Complete the managed-domain (SigV4/SSM) connectivity verification**
   once a real managed-domain endpoint and app-EC2 instance id are
   available, including the now-permission-cleared Nori analyzer's actual
   mechanical behavior on that domain.
5. **A formal repeated-trial variance study** for generation — running a
   subset of questions several times each to characterize answer-to-
   answer variance under the fixed prompt, beyond the several full-run
   informal reproductions already reported.
