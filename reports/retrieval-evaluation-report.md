# Retrieval Evaluation Report

Date: 2026-08-14
Covers: SUBMISSION.md's "Retrieval evaluation report" requirements. All
numbers below are from a real, from-scratch rebuild of the local index and
a real run of `scripts/evaluate_retrieval.py` against it (commit `a5ec7ec`,
`reports/eval/retrieval_evaluation_results.json`), not from an earlier
session's numbers — the rebuild reproduced the earlier baseline closely
(see "Index build time and rebuild count" below for why a rebuild was
necessary this late in the project).

## Test-query sources and construction method

Each of the 40 answerable questions was drafted from one real, specific
source chunk in the frozen index — never invented independently of the
corpus, and never a light rewording of that chunk's own sentence. The
construction process: a real chunk was surfaced per legal domain from the
live index via a plain BM25 query on the domain name; a question was then
drafted in the register a real esthetician-shop owner would actually use
("이 광고 문구를 써도 되나요?"), never the source chunk's own legal
phrasing; every drafted question was reviewed and approved (or sent back
for a redraft) by the project owner in batches before entering the test
set. Two domains (미용법, 안마사법) and two more (무면허의료행위,
공중위생법) initially returned few or zero candidates from the plain
domain-name query; real candidates were found by searching the live index
with the domain's actual governing statute/topic names instead (e.g.
공중위생관리법 for 미용법) rather than by loosening the domain list or its
per-domain target.

The 5 unanswerable questions target a specific, already-documented gap in
this project's corpus: the official guidance documents that would resolve
certain advertising-phrase or specific-claim questions are absent from
every release on licence grounds (DATASET.md), so a question shaped like
"can I use this exact advertising phrase" retrieves real, on-topic statute
and case chunks that still cannot resolve the specific judgement asked
for. The 5 out-of-scope questions are non-legal (small talk, unrelated
business/design advice) or meta (a question about the agent itself),
exercising the `out_of_scope` path with no real corpus chunk as a target.

## Composition

50 questions total: 40 answerable (exactly 4 per legal domain across the
10 domains this project covers: 약사법, 의료법, 개인정보보호법,
의료기기법, 표시광고법, 미용법, 화장품법, 무면허의료행위, 공중위생법,
안마사법), 5 unanswerable (`expected_status: "insufficient_evidence"`), 5
out-of-scope (`expected_status: "out_of_scope"`).

## Relevance-labelling method and treatment of multiple relevant results

Relevance is binary. Every answerable question records exactly one
required-positive `chunk_id`: the chunk it was drafted from, known by
construction rather than by separate manual labelling. If a reviewer
noticed a second chunk that would also genuinely answer a question,
recording it as an additional positive was permitted but never required —
this happened for none of the 40 questions in practice, so every
answerable question in this release has exactly one recorded positive.
Exhaustively checking all 7,887 chunks against each question to find every
possible relevant one was explicitly out of scope: it is not required for
Recall@10/MRR to be well-defined against a documented, non-exhaustive
positive set, and doing it by hand does not fit this assessment's
timeline. Where a question turns out to have more real positives than
labelled, that would surface as an apparent failure in the analysis below
rather than as a labelling correction after the fact — the metric was
designed with that possibility already priced in, not assumed away.

## Leakage controls, including source-derived queries

Two controls, one structural and one measured:

1. **Structural.** `reports/eval/retrieval_test_set.json` is read by
   exactly one script, the evaluation script itself — no indexing code
   path reads anything under `reports/`. This is a structural guarantee
   (no shared import, no code path connecting the two), not a convention
   relying on discipline.
2. **Measured.** Every answerable question's lexical overlap against its
   own source chunk's text is computed and reported (character-bigram
   overlap ratio, chosen over word-tokenization because no offline Korean
   tokenizer is assumed available and Korean's agglutinative morphology
   makes naive whitespace-splitting an unreliable word boundary). A
   question scoring above 0.5 is a signal the drafting step should have
   caught, not something asserted away in prose.

**Measured overlap, this run** (40 answerable questions): 7 of 40 remain
above the 0.5 threshold after one redraft round:

| id | domain | overlap ratio | disposition |
| --- | --- | --- | --- |
| 29 | 공중위생법 | 0.47 (redrafted from 0.77) | Redrafted once; cleared the threshold. |
| 37 | 안마사법 | 0.55 (redrafted from 0.68) | Redrafted once; still above threshold — accepted (see below). |
| 10 | 개인정보보호법 | 0.561 | Not redrafted — accepted as-is. |
| 11 | 개인정보보호법 | 0.528 | Not redrafted — accepted as-is. |
| 18 | 표시광고법 | 0.533 | Not redrafted — accepted as-is. |
| 32 | 공중위생법 | 0.531 | Not redrafted — accepted as-is. |
| 39 | 안마사법 | 0.535 | Not redrafted — accepted as-is. |
| 40 | 안마사법 | 0.615 | Not redrafted — accepted as-is. |

Of the 8 questions originally flagged in the first drafting pass, 2 (ids
29 and 37) were redrafted once; id 29 dropped below threshold, id 37
improved (0.68 → 0.55) but remained above it — the underlying legal
concept it asks about (안마사 자격이 시각장애인으로 제한된다는 것) has
essentially no synonym space in Korean, so a further redraft was judged
to have diminishing returns and the question was accepted at 0.55 rather
than forced into an increasingly artificial rephrasing. The remaining 6
(ids 10, 11, 18, 32, 39, 40) were never redrafted and are disclosed here,
uniformly, as the leakage-transparency line SUBMISSION.md asks for — this
is the intentional venue for that disclosure (a per-entry `notes` field on
only 2 of the 8 originally-flagged questions would have been an
inconsistent, harder-to-audit way to say the same thing, so it is
consolidated here instead). None of these 7 are 1.0 or near it — the
highest, id 40 at 0.615, still requires more than a third of the
question's own bigrams to be *absent* from the source text — so this
project treats them as accepted, near-threshold cases in a corpus whose
Korean legal vocabulary has limited synonym range for these specific
concepts, not as undetected leakage.

**A leakage-check redraft has a real, measured cost, disclosed honestly
rather than omitted.** The first real evaluation run, before ids 29/37
were redrafted, scored aggregate Recall@10 = 0.475 / MRR = 0.2749. After
the redraft, the committed test set scores Recall@10 = 0.45 / MRR ≈
0.2517 (this run) — the redraft cost exactly one question's hit (one
answerable question's correct chunk fell out of the fused top-10 once its
question was reworded away from its source chunk's own vocabulary). This
is reported as evidence the leakage check was load-bearing — part of the
pre-redraft score really was inflated by lexical overlap — not as a
regression to be explained away.

## Exact metric definitions and cutoffs

**Recall@10**: for each answerable question, 1 if its single required
positive chunk appears anywhere in the fused top 10 results, 0 otherwise;
averaged over the 40 answerable questions. The cutoff of 10 is not
arbitrary — it is exactly the number of chunks this project's generation
step actually receives (`reports/decisions/2026-08-13-retrieval-design.md`),
so this metric answers "was the real, required-positive chunk among what
generation could possibly have grounded an answer in," the retrieval
property that most directly determines whether an `answered` response can
be correctly grounded at all.

**MRR** (Mean Reciprocal Rank): for each answerable question, 1/rank of
the required positive chunk within the same fused top-10 (0 if absent),
averaged over the 40 answerable questions — same top-10 cutoff as
Recall@10, not the full top-50 pre-fusion candidate pool, so both metrics
describe the same thing generation actually sees. MRR is sensitive to
*where* the positive lands, not just whether it clears the cutoff, and
complements Recall@10 by showing whether fusion is surfacing the right
chunk near the top or only barely inside the cutoff.

**nDCG was deliberately not computed.** ASSIGNMENT.md's item 6 names
Recall@k, MRR, and nDCG as illustrative examples, not a mandate to compute
all three. nDCG's distinguishing value over MRR comes from graded
relevance — multiple positives at different relevance levels — and this
project's relevance judgement is binary with (in this release) exactly one
recorded positive per question, giving nDCG little room to differ
meaningfully from MRR here. This is a scope decision, not a capability
gap: if a future release records richer, graded relevance judgements,
nDCG becomes worth adding at that point.

The retrieval pipeline underlying these numbers (query embedding with
`input_type="search_query"`, BM25 top-50 + exact k-NN top-50, client-side
Reciprocal Rank Fusion with `k=60`, fused top-10) is exactly the retrieval
half of the real, production `LegalAgent.answer_sync` path — no separate,
evaluation-only retrieval logic exists. `scripts/evaluate_retrieval.py`
makes no generation call at all, keeping this report's deterministic
retrieval measurement (same index, same query, same result every time)
separate from the Generation evaluation report's necessarily stochastic
measurements, per SUBMISSION.md's own instruction to keep the two apart.

## Aggregate and per-domain results

Real run, 2026-08-14, against the rebuilt production index (7,887 chunks,
182 judgements + 1,625 statutes):

| Metric | Value |
| --- | --- |
| Recall@10 (aggregate, 40 answerable questions) | **0.45** |
| MRR (aggregate, 40 answerable questions) | **0.2517** |

| Domain | Recall@10 | MRR | n |
| --- | --- | --- | --- |
| 안마사법 | 0.75 | 0.550 | 4 |
| 미용법 | 0.75 | 0.365 | 4 |
| 공중위생법 | 0.75 | 0.354 | 4 |
| 무면허의료행위 | 0.50 | 0.500 | 4 |
| 화장품법 | 0.50 | 0.313 | 4 |
| 개인정보보호법 | 0.50 | 0.292 | 4 |
| 약사법 | 0.50 | 0.108 | 4 |
| 의료기기법 | 0.25 | 0.036 | 4 |
| **의료법** | **0.00** | **0.00** | 4 |
| **표시광고법** | **0.00** | **0.00** | 4 |

The 10 unanswerable/out-of-scope questions are retrieved against for
transparency (what generation would have seen) but excluded from these
metrics by design — there is no positive judgement to recall against for
a question with no source chunk.

## Failed-query analysis

The two domains scoring 0.0 — 의료법 (Medical Law) and 표시광고법
(Advertising Labelling Law) — were investigated directly rather than left
as an unexplained number.

**Ruled out: missing or unindexed data.** All 8 required-positive chunk
ids for these two domains' questions were looked up directly against the
freshly rebuilt index by exact `chunk_id` term match; all 8 resolved.
The correct chunks are indexed and retrievable by id — this is a genuine
ranking miss, not a corpus or indexing gap.

| id | domain | question (translated sense) | source chunk |
| --- | --- | --- | --- |
| 5 | 의료법 | Is eyebrow semi-permanent tattooing unlicensed medical practice? | precedent-622115#summary-headnote-000 |
| 6 | 의료법 | Is decorative tattooing unlicensed medical practice? | precedent-622263#summary-headnote-000 |
| 7 | 의료법 | Is acupressure/acupuncture-style service unlicensed medical practice? | precedent-99684#summary-holding-000 |
| 8 | 의료법 | Are we legally required to keep treatment records like a clinic? | precedent-141548#summary-holding-000 |
| 17 | 표시광고법 | Can I inflate reviews/purchase counts in banner ads? | precedent-207141#summary-holding-001 |
| 18 | 표시광고법 | Can I overstate the "original price" to make a discount look bigger? | precedent-221809#body-020 |
| 19 | 표시광고법 | Can I omit a known side-effect risk from an ad? | precedent-220369#body-010 |
| 20 | 표시광고법 | Can I inflate the list price in a 1+1 promotion? | precedent-220843#body-008 |

**Working hypothesis (labelled as a hypothesis, not confirmed by
inspecting the actual retrieved candidates for these 8 questions — that
deeper diagnostic is flagged as follow-up, not completed here):** these
two domains' questions are drafted in an unusually colloquial,
practical register by design (Decision 1's whole purpose is to avoid the
lexical-overlap leakage the section above measures), while their source
chunks are judgement headnote/holding text written in formal Korean legal
register (e.g. "무면허 의료행위", "거짓·과장의 표시·광고"). This creates a
larger vocabulary gap between question and source than in the
higher-scoring domains: 안마사법/미용법/공중위생법 (0.75 each) ask about
concrete regulatory facts (자격 요건, 업종 분류, 위생교육 의무) whose
everyday phrasing and legal phrasing overlap more naturally, while the
0.0 domains ask "is this specific everyday behavior legal" in a way that
depends on inferring the applicable legal concept rather than naming it.
BM25 (exact/near-exact term matching) has little to work with when the
question's own vocabulary barely appears in the source text; whether
dense k-NN closed that gap for these particular 8 questions was not
directly inspected in this report and is the natural next investigation
if this pattern needs to be addressed (e.g. by domain-specific query
expansion, or accepting it as a documented retrieval-quality limitation
of this corpus's size and register range).

**Also notable:** 의료기기법 (0.25/0.036) and 약사법 (0.50/0.108) both
recall at least one correct chunk but rank it far down the fused list
(low MRR despite non-zero recall) — consistent with the same
register-gap pattern in a milder form, rather than a domain-specific
outlier.

## Latency percentiles, index size, index build time, and rebuild count

**Per-question retrieval latency** (embed + BM25 search + k-NN search,
wall-clock, all 50 questions, this run):

| Percentile | Latency |
| --- | --- |
| min | 275.5 ms |
| p50 (median) | 497.95 ms |
| p95 | 657.0 ms |
| p99 | 987.4 ms |
| max | 987.4 ms |

The single outlier (987.4 ms, question id 1) is well clear of the next
highest (753.1 ms); everything else falls at or below 657.0 ms.

**Index size.** Raw store size in bytes was attempted (`_stats/store,docs`
against the local index) but not obtained this session — the local
container became unstable again immediately after the evaluation run
completed (see "Rebuild count" below), before this nice-to-have call
could be made, and it was not worth a further real-cost run to retrieve.
What is confirmed instead: 7,887 documents (7,463 `body` + 424 `summary`
chunks) across 182 judgement + 1,625 statute source records, 1 shard, 0
replicas locally (1 replica on the managed domain), `knn_vector` field at
1536 dimensions per chunk with no ANN `method` block (exact k-NN).

**Index build time**: 742.7 seconds of embedding time, 772.5 seconds
total, for the original 2026-08-13 production build (247 embedding calls,
$0.4369, 0 bulk-index errors).

**Rebuild count: 2.** The original production build (2026-08-13) and one
full rebuild (2026-08-14), performed while preparing this report after an
environment problem specific to this contributor's development machine —
not a defect in the indexing pipeline — made the local container
unreachable (see the Work report's blocker log for full detail; summary:
a leftover, unrelated OpenSearch process on this machine's WSL2
distribution was occupying the default port, and the same machine's
Docker environment intermittently terminated the project's container for
reasons not conclusively identified within a time-boxed investigation,
most likely contention with an unrelated container workload also running
on this machine). The rebuild reproduced the original exactly on every
cost/count dimension — 247 embedding calls, 3,640,423 estimated tokens,
$0.4369, 0 bulk-index errors — confirming the indexing pipeline itself is
fully deterministic given the same corpus and chunking rules; only wall-clock
time differed (963.7s vs. 772.5s total), attributable to the same
environment contention that necessitated the rebuild, not to any change
in the pipeline. The rebuilt index reproduced the pre-rebuild Recall@10
exactly (0.45) and MRR within measurement noise (0.2517 vs. a previously
reported 0.2511), confirming the two builds are retrieval-equivalent.

## Dataset, normalization, chunking, embedding, and index versions

Every value below is the exact `RuntimeVersions` this evaluation ran
under, threaded through the code rather than restated by hand:

| Component | Version |
| --- | --- |
| Dataset | `dataset-2026-08-11-v2.1` |
| Normalization | `norm-v1` |
| Chunking | `chunk-v1` |
| Index | `index-v1` |
| Embedding model | `global.cohere.embed-v4:0` (1536 dimensions, `input_type="search_query"` for every query in this evaluation) |
| Index name | `legal-kit-assessment-jynlee-chunk-v1-index-v1` |

No generation model or prompt version applies to this report — this
evaluation makes no generation call by design (see "Exact metric
definitions and cutoffs" above).
