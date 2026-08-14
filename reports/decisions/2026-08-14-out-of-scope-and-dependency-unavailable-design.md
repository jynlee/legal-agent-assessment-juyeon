# `out_of_scope` and `dependency_unavailable` Response-State Design

Date: 2026-08-14
Status: Decided
Covers: the two response states `reports/decisions/2026-08-13-retrieval-design.md`
explicitly deferred — its own "Explicitly out of scope" section named
"`out_of_scope` / `dependency_unavailable` response-state logic (item 7/8)
— only the `insufficient_evidence` boundary is decided here." This note
closes that gap.

It does not cover: any change to the already-decided `answered` /
`insufficient_evidence` boundary (retrieval-design.md Decision 4, unchanged);
the retrieval test set or its 5 `out_of_scope` questions (already committed,
`reports/eval/retrieval_test_set.json`, `reports/decisions/2026-08-13-retrieval-evaluation-design.md`);
generation-quality evaluation itself (the Generation evaluation report,
future work, not this note).

## Summary of decisions

| Area | Decision |
| --- | --- |
| `out_of_scope` detection | Fold into the existing single generation call — expand the prompt to a 3-way status (`answered` / `insufficient_evidence` / `out_of_scope`), not a separate classification call or a pre-retrieval filter |
| `out_of_scope` retrieval cost | Retrieval still runs in full for every question, including obviously out-of-scope ones — accepted, not optimized away |
| `out_of_scope` diagnostic data | `retrieval_hits` populated on `out_of_scope` responses, same as `insufficient_evidence` |
| `dependency_unavailable` scope | One `try`/`except` around all of `LegalAgent.answer_sync`, not per-call-site handling |
| `dependency_unavailable` exception list | Narrow: `opensearchpy.exceptions.ConnectionError`/`ConnectionTimeout`, `botocore.exceptions.EndpointConnectionError`/`ConnectTimeoutError`/`ReadTimeoutError` — connection/timeout failures only, nothing else |
| `dependency_unavailable` diagnostic data | `retrieval_hits` always empty, regardless of how far the call got before failing |
| Prompt versioning | `generation.PROMPT_VERSION` bumps `"prompt-v1"` → `"prompt-v2"` |

## Decision 1: `out_of_scope` is a third generation-call outcome, not a separate classification step

Two shapes were considered: (a) fold `out_of_scope` into the same Bedrock
call that already decides `answered` vs `insufficient_evidence`
(`generation.py`'s prompt/parser), or (b) add a cheap pre-retrieval
classification pass (a separate Bedrock call, or a rule-based filter) that
short-circuits retrieval and generation entirely for obviously off-topic
questions.

**Chosen: (a), fold into the existing call.** This is consistent with
`retrieval-design.md` Decision 4's own precedent — that decision already
delegates the harder `insufficient_evidence` judgement (statute/case chunks
that are on-topic but don't resolve the specific question) to the same
single generation call, on the reasoning that only a call that sees the
actual retrieved text is positioned to make that judgement. `out_of_scope`
is the same shape of problem: telling a genuinely off-topic question
("오늘 날씨가 어때요?") apart from an on-topic-but-uncovered one ("직원 급여를
인상하려면 어떻게 협상해야 하나요?" — a real legal/business question, just
outside this corpus's 10 domains) needs the same kind of judgement, not a
different mechanism.

**Cost this accepts:** exact k-NN always returns its requested `size` of
nearest neighbors regardless of actual relevance (mapping design Decision 6
— this is not new to this note), so every question pays for one embedding
call and two `_search` calls before generation ever sees it, even pure
small talk. A pre-retrieval filter (option b) would save this for the
clearly-off-topic cases. This project's corpus and query volume are small
enough (an assessment run against ~1,800 records, not a production service)
that the saved cost is not worth a second Bedrock call, a second prompt to
version and test, and a second place `out_of_scope` could disagree with what
generation itself would have said given the same question — YAGNI.

**Consequence for `agent.py`:** the current code collapses every
non-`ANSWERED` `parsed.status` into `AnswerStatus.INSUFFICIENT_EVIDENCE`
(`answer_sync`, the block right after `parse_answer_response` returns). This
was correct when only two statuses existed; with a third, it must branch on
`parsed.status` directly and return whichever of `INSUFFICIENT_EVIDENCE` or
`OUT_OF_SCOPE` the parser actually produced — not a design decision so much
as a bug this design creates if left unfixed, called out here so the
implementation plan doesn't miss it.

**Diagnostic data:** `out_of_scope` responses carry `retrieval_hits`
populated, matching `insufficient_evidence`'s existing behavior. Both are
decided inside the same generation call, after retrieval already ran, so
the hits are already in hand — dropping them would discard real diagnostic
value for no reason (e.g., confirming that a weather question's k-NN
neighbors were, as expected, unrelated legal chunks the model correctly
disregarded).

## Decision 2: `dependency_unavailable` — one broad `try`/`except`, a narrow exception list

**Scope of the `try`/`except`:** all of `answer_sync`'s body, not
per-call-site (`_embed_query`, the two `_search` calls, `_generate`
individually). Every failure mode this state exists for — OpenSearch
unreachable, Bedrock unreachable — collapses to the identical response
shape regardless of which call failed, so branching the exception handling
by call site would add real code (three or four `try` blocks instead of
one) for a distinction the response contract does not expose to the caller
anyway. `GeneralLegalResponse` has no field naming which dependency failed.

**Exception list, deliberately narrow:**

- OpenSearch (`opensearchpy.exceptions`): `ConnectionError`, `ConnectionTimeout`.
- Bedrock (`botocore.exceptions`): `EndpointConnectionError`, `ConnectTimeoutError`, `ReadTimeoutError`.

These are the exception types that specifically mean "the service could not
be reached at all" — not "the service responded with an error." Explicitly
**not** caught: `opensearchpy.exceptions.TransportError` and its other
subclasses (`NotFoundError`, `RequestError`, `AuthenticationException`,
`AuthorizationException` — a wrong index name, a malformed query body, or a
namespace violation surface as these, and should fail loudly as the bugs
they are, not be reported to a caller as a generic infrastructure outage),
and `botocore.exceptions.ClientError` (Bedrock's catch-all for a request
that *did* reach the service but was rejected — throttling, validation
errors, model-access errors — again real conditions this project wants
visible during development and grading, not silently reclassified).

**Why narrow, checked against this project's own risk list:** this project
tracks a documented "quiet failure" pattern — README.md's table of failure
modes only discovered late, after they have already invalidated other work.
A broad exception catch here would recreate exactly that shape of risk: a
real bug (e.g., an index-name typo that starts querying the wrong,
possibly out-of-namespace index — the exact concern `ASSIGNMENT.md`'s
namespace-scoping prohibition exists for) would be silently absorbed into a
plausible-looking `dependency_unavailable` response instead of raising and
being caught during development or CI. The narrow list only catches
failures where nothing about the request itself could be wrong — the
service genuinely could not be reached — which is the only condition this
response state is meant to represent.

**Diagnostic data:** `retrieval_hits` is always empty on this path,
regardless of whether retrieval had already succeeded before a later
Bedrock call failed. This matches `insufficient_evidence`'s and
`out_of_scope`'s existing pattern of a single response-construction point
per outcome, and keeps the `except` block simple — it does not need to
thread a partially-populated `retrieval_hits` value out of the `try` block
across every possible failure point. The cost is a real one (a partial
success — retrieval worked, only generation failed — reports no more
diagnostic detail than a total failure) but this project's assessment scope
does not need that finer distinction, and nothing downstream (the Work
report's blocker log, the Generation evaluation report) depends on it.

## Decision 3: prompt version bump

`generation.PROMPT_VERSION` moves from `"prompt-v1"` to `"prompt-v2"` when
the prompt template changes to add the `out_of_scope` option. This is
`RuntimeVersions.prompt`'s entire purpose (`contracts.py`) — a stored
answer names the exact prompt that produced it — and the template's own
docstring already states the convention ("Bumped whenever `_PROMPT_TEMPLATE`
changes"). Noted here only so the implementation plan does not miss it as a
one-line, easy-to-forget part of this change.

## Explicitly out of scope for this note

- Whether a numeric confidence or score should ever gate `out_of_scope`
  (e.g., "if the model is uncertain, prefer `insufficient_evidence`") — no
  such distinction exists in `contracts.py` or `ASSIGNMENT.md`, and the test
  set's own five `out_of_scope` questions (pure small talk, an
  outside-the-10-domains legal question, business/design advice, a
  meta-question about the agent) are all unambiguous enough that this
  question does not need answering now.
- Retry/backoff behavior for a `dependency_unavailable` condition — this
  design defines the response shape for a caller, not a resilience policy;
  `ASSIGNMENT.md` does not ask for one, and adding retry logic without a
  measured need would be the same un-YAGNI'd complexity
  `retrieval-design.md` Decision 3 already declined for reranking.
- The Generation evaluation report's own analysis of how well these two
  states actually fire against the test set — that is the report's job,
  once this logic exists to measure.

This is a design decision, not yet implementation — no code implementing
`out_of_scope`/`dependency_unavailable` exists yet as of this note.
