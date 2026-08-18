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

## Completed, incomplete, and deliberately deferred work

**Completed** (all 9 required-work items plus item 10's reporting
deliverables):

1. Record-selection and document-kind decisions — done (`reports/decisions/`, record-selection policy).
2. Normalization, chunking, deterministic identity rules — done (`norm-v1`, `chunk-v1`, statute and judgement chunkers).
3. Versioned OpenSearch 3.5-compatible index, reproducibly — done (`index-v1`, built twice, byte-identical cost/count both times).
4. Query embedding, retrieval, fusion — done (BM25 + exact k-NN + client-side RRF, `k=60`). Reranking deliberately not implemented (see below).
5. Test set and relevance judgements — done (56 questions, `reports/eval/retrieval_test_set.json`, leakage-checked; grew from 50 to 56 on 2026-08-18, see the Blocker log and "Incomplete / found but not fixed" below for the 2 gold-label corrections made along the way).
6. Quantitative retrieval metrics — done (Recall@10, MRR; nDCG deliberately not computed, justified in the Retrieval evaluation report).
7. Grounded answers via the fixed Bedrock Claude model policy — done (`LegalAgent`, `prompt-v2`).
8. Verifiable citations, `insufficient_evidence`, `out_of_scope`, `dependency_unavailable` — done, all 4 response states implemented and covered by both unit tests and the real Generation evaluation run.
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

**Incomplete / found but not fixed** (real gaps, surfaced by this
project's own review process, disclosed rather than silently left):

- **`agent.py`'s "total fabrication" citation path is invisible to
  `limitations_fired_count`.** If the model claims `answered` with zero
  actually-retrieved cited ids, the response downgrades to a bare
  `insufficient_evidence` with an empty `limitations` field —
  indistinguishable, in the current response contract, from an honest
  refusal. Found during the Generation-evaluation final code review;
  fixing it needs a production change to the response contract, judged
  out of scope for an evaluation-tooling fix round under this deadline.
  Disclosed in the Generation evaluation report's "Citation integrity"
  section.
- **Two real, opposite-direction refusal-accuracy failures; two prompt
  fixes attempted and reverted; root cause now identified but not yet
  fixed**: 2 of 42 answerable questions are falsely refused despite
  successful retrieval (`insufficient_evidence refusal accuracy`
  section's mirror finding), and 4 of 9 `insufficient_evidence`-expected
  questions are answered instead of refused (corrected count, after
  removing 2 gold-label errors from this bucket — see Blocker log item
  10). Two targeted fixes were tried against the pre-correction baseline,
  both reverted against a pre-registered bar: `prompt-v3` (a blanket
  instruction against answering by analogy) improved the over-answering
  direction (3→2) but worsened false refusals more (2→8); `prompt-v4` (a
  contrastive worked example) did not improve the over-answering
  direction at all and still worsened false refusals (2→6). Both
  reverted; `prompt-v2` remains in production. **Root cause found on
  2026-08-18, after both attempts**: reading the actual generated answer
  for one over-answer case (id 53) shows the model's own prose explicitly
  states the source is ambiguous ("...개인 유튜브 채널 촬영을 포함하는지
  여부는... 불분명합니다") and then still returns `status: "answered"`
  anyway — the failure is not that the model fails to recognize
  insufficient evidence, but a disconnect between its own stated
  uncertainty and its final status decision. This points to a structural
  fix (a code-checked explicit resolution field, not another prompt
  instruction) as the next candidate, not attempted this submission.
- **Generation-only latency is not isolated from the judge call's added
  latency** in the Generation evaluation report's `answered`-path
  numbers — the deliverable's own single-call response time was not
  separately measured this evaluation.

## AWS use

Self-instrumented from the first real call this project made, per
SUBMISSION.md's requirement (contributors share one IAM user; no billing
or CloudTrail record can attribute usage to a specific contributor).
Source: every file in `reports/usage/` (gitignored; 25 files, one per real
script invocation that made at least one real AWS call). This total
includes every real run made after this report's numbers were first
drafted on 08-14: the `prompt-v3` and `prompt-v4` trials (both tried, then
reverted — `prompt-v2` is what shipped), a 2026-08-18 re-verification pass
against the local container to confirm the committed numbers reproduce,
and the test-set expansion/correction work (real retrieval and generation
evaluation runs against the growing/corrected 56-question set, including
one run made before the 2 gold-label corrections and one after).

| Category | Runs | Embed tokens (est.) | Generation input tokens | Generation output tokens | Cost |
| --- | --- | --- | --- | --- | --- |
| Index builds (`index_chunks.py`) | 2 | 7,280,846 | — | — | $0.8738 |
| Retrieval evaluations (`evaluate_retrieval.py`) | 6 | 11,819 | — | — | $0.001417 |
| Generation evaluations (`evaluate_generation.py`) | 12 (8 succeeded, 4 failed) | 15,618 | 3,827,691 | 247,114 | $15.191655 |
| Real demo calls (`serve_legal_agent.py`) | 5 (2 without token capture) | 74 | 18,444 | 858 | $0.06821 |
| **Total, fully instrumented** | **25** | **7,308,357** | **3,846,135** | **247,972** | **$16.135082** |

Plus, disclosed separately rather than folded into the total above
(see Blocker log items 7–9): **~$0.00001** from 6 untracked pre-
instrumentation dev calls, and an **unknown, likely small** amount of
real partial spend from the 4 failed Generation-evaluation attempts whose
cost was zeroed by the since-fixed accounting bug (their real elapsed
time, 19–31 seconds each, is the only surviving evidence they made real
calls at all).

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

1. **Fix the two opposite-direction refusal-accuracy failures with the
   now-identified structural mechanism.** Two prompt-level attempts
   (`prompt-v3`, `prompt-v4`) were tried and reverted before root cause
   was known. The root cause is now identified (see "Incomplete / found
   but not fixed" above): the model can state a source is ambiguous in
   its own prose and still choose `status: "answered"` — a disconnect
   between stated reasoning and final decision, not a failure to
   recognize the gap. The next attempt should force an explicit,
   code-checked intermediate field ("does a source directly resolve this
   exact question: yes/no") and derive `status` from that field rather
   than trusting the model's own status choice directly, then re-run the
   Generation evaluation to confirm without regressing
   `out_of_scope_refusal_accuracy` (currently a clean 1.0) or the
   domain-coverage risk (currently confirmed resolved).
2. **Close the `agent.py` total-fabrication citation-integrity gap** —
   make the response contract distinguish "the model honestly had no
   evidence" from "the model claimed an answer with zero real citations
   and was caught" — a real production change, not an evaluation-tooling
   fix, so it needs its own design/review cycle.
3. **A second, independent grounding check** — either a genuinely
   different judge model (would require sourcing and verifying a second
   Kit-approved model id) or a human-reviewed spot-check of a sample of
   the 44 judged answers, to test whether the single-model,
   single-pass judge's `partially_grounded` calls hold up under
   independent review.
4. **Isolate generation-only latency** from the judge call's added
   latency in the `answered`-path numbers, and investigate whether the
   per-domain grounding pattern (공중위생법 fully grounded, four other
   domains with zero fully-grounded answers this run) is a stable
   property or this run's sampling noise, with a larger per-domain
   sample.
5. **Complete the managed-domain (SigV4/SSM) connectivity verification**
   once a real managed-domain endpoint and app-EC2 instance id are
   available, including the now-permission-cleared Nori analyzer's actual
   mechanical behavior on that domain.
6. **A formal repeated-trial variance study** for generation — running a
   subset of questions several times each to characterize answer-to-
   answer variance under the fixed prompt, beyond the two full runs'
   informal reproduction already reported.
