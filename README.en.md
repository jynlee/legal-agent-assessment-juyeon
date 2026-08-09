# General Legal Agent Assessment Template

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

| English | Korean | Contents |
| --- | --- | --- |
| [README.en.md](README.en.md) | [README.md](README.md) | This file |
| [ASSIGNMENT.md](ASSIGNMENT.md) | [ASSIGNMENT.ko.md](ASSIGNMENT.ko.md) | Objective, fixed constraints, prohibited work |
| [DATASET.md](DATASET.md) | [DATASET.ko.md](DATASET.ko.md) | Release delivery, allowed transformations, lineage |
| [DATASET_SCHEMA.md](DATASET_SCHEMA.md) | [DATASET_SCHEMA.ko.md](DATASET_SCHEMA.ko.md) | Supplied record shape, missing-value conventions, manifest, checks |
| [CONTRACT.md](CONTRACT.md) | [CONTRACT.ko.md](CONTRACT.ko.md) | Portable application-service boundary |
| [SUBMISSION.md](SUBMISSION.md) | [SUBMISSION.ko.md](SUBMISSION.ko.md) | Required evidence |
| [OPENSEARCH_ACCESS.md](OPENSEARCH_ACCESS.md) | [OPENSEARCH_ACCESS.ko.md](OPENSEARCH_ACCESS.ko.md) | Managed domain access and shared-credential rules |
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

## The dataset and where it comes from

The corpus has two public origins. Court decisions come from the 법제처
국가법령정보 OPEN API at law.go.kr, searched against four target laws — 의료법,
표시·광고의 공정화에 관한 법률, 소비자기본법, and 안마사에 관한 규칙. Decisions
whose full text that API does not publish were not collected. The official
guides are government publications issued by 보건복지부 and 식품의약품안전처.

MZO delivers this as a frozen release, and **the frozen release is the
measurement basis**. Build and measure your submission from it. That is what
lets MZO's rerun reproduce your numbers, and what makes a difference between
two contributors attributable to design rather than to who collected more.

**Looking at the raw sources is allowed**, which is why they are named here.
Every decision carries its own source URL, so you can check any one of them
against the original, and the guides carry their official publication number.
The API is open, but its `OC` id is issued per developer, so query it directly
only with an id you registered yourself.

If you conclude the coverage is wrong — something missing, or something
included that does not belong — **explain it to gyro. Coverage can change.** A
separate report is not expected; a clear explanation is enough. What is not
useful is quietly collecting around the release, because then your reported
numbers describe a corpus nobody else has.

Every record carries the publisher statement its source requires. Surface it:
an answer that cites a decision without naming where the text came from is not
a complete citation. Licence terms and attribution conditions are settled by
the release manifest.

## OpenSearch 3.5 baseline

This assessment replaces the legacy OpenSearch 2.17 baseline with **OpenSearch
3.5**. Build local and managed indexes that are compatible with 3.5. Do not copy
2.17 mappings or assumptions without revalidating them against 3.5.

## Repository provisioning from a tag

MZO freezes the contributor starting point as an immutable tag such as
`assessment-v1` after the dataset release, model access, and smoke checks are
ready. MZO then creates one separate private repository per contributor from the
exact tagged tree. Contributors do not share branches or see one another's work.

The contributor repository records the source tag and commit in its initial
commit. Work continues on that repository's `master` branch; feature branches
and pull requests are optional. The final submission is identified by one exact
commit SHA. A later baseline correction receives a new tag and is distributed
to every active contributor at the same time.

MZO provisioning outline:

```text
legal-agent-assessment-template @ assessment-v1
        |-- contributor-a private repository
        |-- contributor-b private repository
        `-- contributor-c private repository
```

Do not create contributor repositories from an untagged moving branch.

## Development cautions: Tier

The following silent failures invalidate otherwise unrelated work. Add a cheap
detector for each one before building the full pipeline.

| Mistake | Found | What it invalidates |
| --- | --- | --- |
| Indexing evaluation queries, expected answers, or relevance labels | MZO rerun | Every retrieval metric |
| Presenting a source-derived near-copy test as real-user quality | Review | The entire retrieval evaluation report |
| Missing chunk lineage | Citation check | Every answer — without provenance, `answered` is not reachable |
| Time, tokens, and cost not recorded as you go | Submission | The work report; the shared IAM user makes it unattributable, so it cannot be reconstructed afterwards |
| Developing against the managed domain without SigV4 | Policy tightening, or a rerun elsewhere | Every OpenSearch call — unsigned requests pass locally and on staging today |

Minimum detectors:

- Reject every index input whose provenance/type is evaluation-only or whose
  path comes from the evaluation artifact tree.
- Verify that every indexed record belongs to the frozen corpus manifest, and
  detect exact or near-duplicate query/expected-answer text in indexed chunks.
- Make ingest and query call the same versioned normalization and embedding
  configuration.
- Reject any chunk missing required lineage fields.
- Append tokens, latency, model ID, and cost inputs for every Bedrock call as the
  call happens.

A green CI run is not proof that these conditions hold.

## Asking questions

**Contact: gyro (MZO).**

Ask when something is undefined.

A useful question states:

1. what is blocked;
2. which readings are possible;
3. how the outcome differs depending on which reading is chosen;
4. which assumption you will proceed on if no answer arrives.


Any baseline update that affects the assessment is published to all active
contributors at the same time.
