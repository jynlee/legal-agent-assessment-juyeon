# General Legal Agent Assessment Template

> English source. The Korean translation is [README.md](README.md).

This private repository is the common starting point for independent two-week
General Legal Agent implementations. Every contributor receives the same Git
baseline and byte-identical frozen dataset release in a separate private
repository.

The required vertical slice is:

```text
frozen legal dataset
-> reproducible OpenSearch index
-> measured retrieval pipeline
-> grounded Bedrock LLM answer
-> single-turn GeneralLegalAgent application service
```

## Documents

English documents are authoritative. Korean files are translations for human
readers; if the two disagree, the English text governs.

| English (authoritative) | Korean | Contents |
| --- | --- | --- |
| [README.en.md](README.en.md) | [README.md](README.md) | This file |
| [ASSIGNMENT.md](ASSIGNMENT.md) | [ASSIGNMENT.ko.md](ASSIGNMENT.ko.md) | Objective, fixed constraints, prohibited work |
| [DATASET.md](DATASET.md) | [DATASET.ko.md](DATASET.ko.md) | Release delivery, allowed transformations, lineage |
| [CONTRACT.md](CONTRACT.md) | [CONTRACT.ko.md](CONTRACT.ko.md) | Portable application-service boundary |
| [SUBMISSION.md](SUBMISSION.md) | [SUBMISSION.ko.md](SUBMISSION.ko.md) | Required evidence |
| [AGENTS.md](AGENTS.md) | — | Instructions for coding agents ([CLAUDE.md](CLAUDE.md) points here) |

## Start here

1. Read [ASSIGNMENT.md](ASSIGNMENT.md).
2. Verify the delivered dataset as described in [DATASET.md](DATASET.md).
3. Preserve the portable boundary in [CONTRACT.md](CONTRACT.md).
4. Plan the required evidence in [SUBMISSION.md](SUBMISSION.md).
5. Configure the dedicated AWS CLI profile delivered through the approved
   separate channel, then copy `.env.example` to `.env`. Never put access keys
   in `.env`; AWS SDK credential providers resolve the named `AWS_PROFILE`.
6. Run the local checks.

```powershell
uv sync
docker compose up -d opensearch
uv run python scripts/smoke_opensearch.py
uv run python scripts/smoke_contract.py
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

This template fixes environment and integration boundaries, not retrieval
design. It deliberately does not provide canonical chunks, an index mapping, a
retrieval implementation, a test set, relevance labels, prompts, or pass bars.

## Development cautions

Mistakes in this project do not all cost the same. They fall into three tiers.

- **Tier A — symmetric.** Type errors, lint failures, contract violations.
  `mypy` and `pytest` catch them in seconds. The cost of the mistake is the time
  it takes to fix.
- **Tier B — near-symmetric.** A poor chunk size or a weak index mapping. It
  surfaces in your metrics days later and needs a reindex, but your evaluation
  code, prompts, and service layer all survive. The loss is local.
- **Tier C — asymmetric.** The five below. **Any one of them invalidates work
  that has nothing to do with the mistake.**

| Mistake | Found | What it invalidates |
| --- | --- | --- |
| Indexing evaluation queries, expected answers, or relevance labels | MZO rerun | **Every retrieval metric.** The code and design are fine; the numbers are unusable |
| Presenting a source-derived near-copy test as real-user quality | Review | The entire retrieval evaluation report |
| Ingest and query embedding or preprocessing diverge | Possibly never | Every retrieval result |
| Missing chunk lineage | Citation check | Every answer — without provenance, `answered` is not reachable |
| Time, tokens, and cost not recorded as you go | Submission | The work report. **Not reconstructable afterwards** |

Three properties make these asymmetric:

1. **They fail silently.** No crash, no exception. Worse, a leaked index scores
   *better* — the failure signal is indistinguishable from the success signal.
2. **The cost of undoing them grows without bound.** A leak found on day 1 is
   thirty minutes. On day 12 it is a reindex, a re-evaluation, and a rewritten
   report. Unrecorded time and cost eventually cannot be reconstructed at all.
3. **A local mistake causes global loss.** One line in an indexing script can
   invalidate the retrieval report, the generation report, and the architecture
   report at once. The work you lose is not proportional to the work you got
   wrong.

**CI does not protect you here.** `ruff`, `mypy`, and `pytest` cover tier A.
Every disqualifying condition is in tier C, and this template detects none of
them. A green CI run is not evidence that a submission is valid.

Build a cheap detector for each one on day one. They do not need to be good.
They need to make a silent failure loud.

- A test asserting that evaluation query IDs and indexed document IDs do not
  intersect.
- A test asserting that the ingest path and the query path call the same
  normalization function.
- An assertion that fails if any chunk is missing a required lineage field.
- A wrapper around every Bedrock call that appends tokens and latency to an
  append-only log.

## Asking questions

**Contact: gyro (MZO).**

Ask when something is undefined. Questions are expected and are not penalized.
This template deliberately leaves design decisions open, so identifying and
framing what you do not know is part of the work being reviewed — a good
question is worth more than a silent assumption.

A useful question states:

1. what is blocked;
2. which readings are possible;
3. how the outcome differs depending on which reading is chosen;
4. which assumption you will proceed on if no answer arrives.

Do not wait on an answer. If one cannot arrive in time, proceed on your stated
assumption and record both the question and the assumption in the blocker log
required by [SUBMISSION.md](SUBMISSION.md).

Any baseline update that affects the assessment is published to all active
contributors at the same time.
